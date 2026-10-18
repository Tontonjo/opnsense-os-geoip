#!/usr/local/bin/python3

"""
    osgeoip.py
    Version: 2.0.0

    Copyright (C) 2026 Async IT
    All rights reserved.

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are met:

    1. Redistributions of source code must retain the above copyright notice,
       this list of conditions and the following disclaimer.

    2. Redistributions in binary form must reproduce the above copyright
       notice, this list of conditions and the following disclaimer in the
       documentation and/or other materials provided with the distribution.

    THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
    INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
    AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
    AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
    OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
    SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
    INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
    CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
    ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
    POSSIBILITY OF SUCH DAMAGE.

    --------------------------------------------------------------------------------------

    Builds the per country lists used by OPNsense GeoIP aliases from the free
    IP to Country database of IPLocate.io (CC BY-SA 4.0, https://www.iplocate.io).
    No MaxMind data is used.

    Source: a zip file holding one CSV file, updated daily, with the columns
    network (CIDR), continent_code, country_code, country_name. The networks are
    already minimal and do not overlap, so they are written as they are.

    OPNsense reads GeoIP aliases from /usr/local/share/GeoIP/alias/<CC>-<IPv4|IPv6>
    (one network per line) and refreshes them when the mtime of the NL-IPv4 file is
    newer than the alias cache. This script writes those files directly, then
    refreshes the GeoIP aliases.

    OPNsense also reads alias.stats to know whether a GeoIP source exists, and resets
    it when the configured GeoIP URL does not match alias._source_hash.md5. The plugin
    sets the GeoIP URL to LOCAL_GEOIP_URL (see geoip_url.php) and writes both files,
    so that Firewall: Aliases no longer reports a missing GeoIP source.

    Commands:
        update   rebuild the lists, then refresh the GeoIP aliases
        status   print the statistics of the last update as JSON, with the progress
                 percentage while an update is running
        sync     write the OPNsense GeoIP source files from the last successful update
        lookup   print as JSON the country of an IP address, or of every address of a
                 hostname, found in the current lists (used by the plugin page)

    Changelog:
        2.0.0  Plugin renamed os-geoip (was os-rir-geoip, script rirgeoip.py).
               Source replaced: IPLocate.io IP to Country database instead of the RIR
               statistics. Streamed parsing (low memory), faster lookup.
        1.3.0  lookup command: country of an IP address or hostname.
        1.2.0  OPNsense GeoIP source files (alias.stats, source hash) written, sync
               command, the plugin URL is no longer reported as a foreign URL.
        1.1.0  Progress percentage reported during updates (progress.json).
        1.0.0  Initial version.
"""

import argparse
import configparser
import csv
import datetime
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import syslog
import tempfile
import time
import urllib.request
import zipfile

# IPLocate.io IP to Country database (GitHub LFS file, redirected to media.githubusercontent.com).
SOURCE_URL = 'https://github.com/iplocate/ip-address-databases/raw/main/ip-to-country/ip-to-country.csv.zip'
SOURCE_NAME = 'IPLocate.io'
# Below this number of networks the download is considered incomplete or broken,
# and the current lists are kept (the database holds about 2 million networks).
MIN_NETWORKS = 100000

# OPNsense GeoIP locations (see /usr/local/opnsense/scripts/filter/lib/alias/geoip.py).
TARGET_DIR = '/usr/local/share/GeoIP/alias'
GEOIP_CONF = '/usr/local/etc/filter_geoip.conf'
GEOIP_STATS = '/usr/local/share/GeoIP/alias.stats'
GEOIP_SOURCE_HASH = '/usr/local/share/GeoIP/alias._source_hash.md5'
# GeoIP URL set by the plugin: not http, so OPNsense never downloads anything from it.
# Keep in line with OsGeoip::LOCAL_GEOIP_URL (OsGeoip.php).
LOCAL_GEOIP_URL = 'file:///var/db/osgeoip/lists'
# URL set by the former os-rir-geoip plugin, also accepted as a plugin URL.
LEGACY_GEOIP_URLS = ('file:///var/db/rirgeoip/lists',)
ANCHOR_FILE = 'NL-IPv4'   # file whose mtime triggers the refresh of GeoIP aliases
UPDATE_TABLES = '/usr/local/opnsense/scripts/filter/update_tables.py'
PYTHON = '/usr/local/bin/python3'

# Plugin state.
STATE_DIR = '/var/db/osgeoip'
STATS_FILE = STATE_DIR + '/stats.json'
LOCK_FILE = STATE_DIR + '/update.lock'
PROGRESS_FILE = STATE_DIR + '/progress.json'
DOWNLOAD_FILE = STATE_DIR + '/download.zip'

DOWNLOAD_TIMEOUT = 300
DOWNLOAD_CHUNK = 65536
REFRESH_TIMEOUT = 900
COUNTRY_FILE_PATTERN = re.compile(r'^[A-Z]{2}-IPv[46]$')
COUNTRY_CODE_PATTERN = re.compile(r'^[A-Z]{2}$')
# Hostname accepted by the lookup command: labels of letters, digits, '_' and '-', not starting with '-'.
HOSTNAME_PATTERN = re.compile(r'^(?=.{1,253}\.?$)[A-Za-z0-9_][A-Za-z0-9_-]{0,62}(\.[A-Za-z0-9_][A-Za-z0-9_-]{0,62})*\.?$')

# Address family, address size in bits and list suffix, by IP version.
FAMILIES = {
    4: (socket.AF_INET, 32, 'IPv4'),
    6: (socket.AF_INET6, 128, 'IPv6'),
}

# Share of the progress bar used by each step (percent): download, list writing, alias refresh.
PROGRESS_DOWNLOAD = 40
PROGRESS_WRITE = 55

DEFAULT_STATS = {
    'status': 'never',
    'message': '',
    'last_attempt': None,
    'last_success': None,
    'duration': None,
    'countries': 0,
    'ranges_total': 0,
    'ranges_ipv4': 0,
    'ranges_ipv6': 0,
}


class UpdateError(Exception):
    """Error that aborts the update without touching the current lists."""


class LookupFailure(Exception):
    """Error returned to the plugin page by the lookup command."""


class Progress:
    """Writes the progress percentage of a running update, only when its integer value changes."""

    def __init__(self):
        self._last = None

    def set(self, percent):
        value = max(0, min(100, int(percent)))
        if value == self._last:
            return
        self._last = value
        temporary_path = PROGRESS_FILE + '.tmp'
        with open(temporary_path, 'w') as handle:
            json.dump({'progress': value}, handle)
        os.replace(temporary_path, PROGRESS_FILE)

    @staticmethod
    def clear():
        try:
            os.remove(PROGRESS_FILE)
        except OSError:
            pass

    @staticmethod
    def read():
        try:
            with open(PROGRESS_FILE) as handle:
                return json.load(handle).get('progress')
        except (OSError, ValueError, AttributeError):
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(message, priority=syslog.LOG_NOTICE):
    syslog.syslog(priority, message)


def read_stats():
    stats = dict(DEFAULT_STATS)
    try:
        with open(STATS_FILE) as handle:
            stats.update(json.load(handle))
    except (OSError, ValueError):
        pass
    return stats


def write_file_atomic(path, content):
    """Writes a file atomically, so readers never see a partial file."""
    temporary_path = path + '.tmp'
    with open(temporary_path, 'w') as handle:
        handle.write(content)
    os.replace(temporary_path, path)


def write_stats(stats):
    os.makedirs(STATE_DIR, exist_ok=True)
    write_file_atomic(STATS_FILE, json.dumps(stats))


def parse_address(address):
    """Parses an IP address. Returns (version, address as an integer), or None when invalid."""
    version = 6 if ':' in address else 4
    try:
        return version, int.from_bytes(socket.inet_pton(FAMILIES[version][0], address), 'big')
    except (OSError, ValueError):
        return None


def parse_network(network):
    """
    Parses a network in CIDR notation.
    Returns (version, start address as an integer, prefix length), or None when invalid.
    The host bits are cleared, so the result is always a valid network.
    """
    address, separator, prefix = network.partition('/')
    parsed = parse_address(address)
    if not separator or not prefix.isdigit() or parsed is None:
        return None
    version, start = parsed
    host_bits = FAMILIES[version][1] - int(prefix)
    if host_bits < 0:
        return None
    return version, (start >> host_bits) << host_bits, int(prefix)


def format_network(version, start, prefix):
    """Formats a network parsed by parse_network() in canonical CIDR notation."""
    family, bits, _ = FAMILIES[version]
    return '%s/%d' % (socket.inet_ntop(family, start.to_bytes(bits // 8, 'big')), prefix)


def foreign_geoip_url_configured():
    """Returns True when a GeoIP URL other than the plugin one is set in Firewall: Aliases: GeoIP settings."""
    if not os.path.isfile(GEOIP_CONF):
        return False
    config = configparser.ConfigParser(interpolation=None)
    try:
        config.read(GEOIP_CONF)
        url = config.get('settings', 'url', fallback='').strip()
    except configparser.Error:
        return False
    return url not in ('', LOCAL_GEOIP_URL) + LEGACY_GEOIP_URLS


def publish_geoip_source(stats):
    """
    Writes the files OPNsense uses to describe its GeoIP source:
    - alias._source_hash.md5: md5 of LOCAL_GEOIP_URL, so OPNsense considers the source
      unchanged and does not reset alias.stats when it refreshes a GeoIP alias;
    - alias.stats: number of ranges and date shown in Firewall: Aliases: GeoIP settings,
      a non zero number of ranges removes the "configure a source" message.
    Does nothing when no successful update has written the lists yet.
    """
    if not stats.get('last_success') or not os.path.isfile(os.path.join(TARGET_DIR, ANCHOR_FILE)):
        return

    file_count = sum(1 for name in os.listdir(TARGET_DIR) if COUNTRY_FILE_PATTERN.match(name))
    core_stats = {
        'address_count': stats.get('ranges_total') or 0,
        'file_count': file_count,
        'timestamp': datetime.datetime.fromtimestamp(stats['last_success']).isoformat(),
        'locations_filename': None,
        'address_sources': {'IPv4': SOURCE_NAME, 'IPv6': SOURCE_NAME},
    }
    write_file_atomic(GEOIP_SOURCE_HASH, hashlib.md5(LOCAL_GEOIP_URL.encode()).hexdigest())
    write_file_atomic(GEOIP_STATS, json.dumps(core_stats))


def is_update_running():
    """Returns True when another process holds the update lock."""
    if not os.path.isfile(LOCK_FILE):
        return False
    with open(LOCK_FILE, 'a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_source(on_progress):
    """
    Downloads the source zip file to DOWNLOAD_FILE. on_progress receives the
    downloaded fraction (0 to 1) when the server announces the file size.
    """
    try:
        response = urllib.request.urlopen(SOURCE_URL, timeout=DOWNLOAD_TIMEOUT)
        total_size = int(response.headers.get('Content-Length') or 0)
        read_size = 0
        with response, open(DOWNLOAD_FILE, 'wb') as handle:
            while True:
                chunk = response.read(DOWNLOAD_CHUNK)
                if not chunk:
                    break
                handle.write(chunk)
                read_size += len(chunk)
                if total_size:
                    on_progress(read_size / total_size)
    except OSError as error:
        raise UpdateError('download failed for %s: %s' % (SOURCE_URL, error))

    if total_size and read_size != total_size:
        raise UpdateError('incomplete download: %d of %d bytes' % (read_size, total_size))


def open_source_csv(archive):
    """Returns (binary member, size, text reader) of the CSV file of the source zip file."""
    members = [info for info in archive.infolist() if info.filename.lower().endswith('.csv')]
    if len(members) != 1:
        raise UpdateError('unexpected source archive content: %s' % ', '.join(archive.namelist()[:5]))
    member = archive.open(members[0])
    return member, members[0].file_size or 1, io.TextIOWrapper(member, encoding='utf-8', errors='replace', newline='')


# ---------------------------------------------------------------------------
# Write lists
# ---------------------------------------------------------------------------

def write_country_files(on_progress):
    """
    Reads the downloaded CSV file line by line and writes one file per country and
    protocol in a temporary folder, then moves them into the OPNsense GeoIP folder.
    The anchor file is moved last, so that the GeoIP aliases are only refreshed once
    every list is in place. on_progress receives the share of the CSV file read (0 to 1).
    Returns the statistics of the written lists.
    """
    os.makedirs(TARGET_DIR, exist_ok=True)
    work_dir = tempfile.mkdtemp(prefix='.osgeoip-', dir=os.path.dirname(TARGET_DIR))
    handles = {}
    counts = {4: 0, 6: 0}
    countries = set()

    try:
        try:
            archive = zipfile.ZipFile(DOWNLOAD_FILE)
        except (OSError, zipfile.BadZipFile) as error:
            raise UpdateError('invalid source archive: %s' % error)

        with archive:
            member, total_size, text = open_source_csv(archive)
            reader = csv.reader(text)
            header = [name.strip().lower() for name in next(reader, [])]
            if 'network' not in header or 'country_code' not in header:
                raise UpdateError('unexpected source format, header: %s' % ','.join(header))
            network_column = header.index('network')
            country_column = header.index('country_code')
            min_columns = max(network_column, country_column) + 1

            for line_number, row in enumerate(reader, start=1):
                if line_number % 50000 == 0:
                    on_progress(member.tell() / total_size)
                if len(row) < min_columns:
                    continue
                country_code = row[country_column].strip().upper()
                parsed = parse_network(row[network_column].strip())
                if parsed is None or not COUNTRY_CODE_PATTERN.match(country_code):
                    continue   # malformed record, or network without country

                version = parsed[0]
                key = '%s-%s' % (country_code, FAMILIES[version][2])
                handle = handles.get(key)
                if handle is None:
                    handle = handles[key] = open(os.path.join(work_dir, key), 'w')
                handle.write(format_network(*parsed) + '\n')
                counts[version] += 1
                countries.add(country_code)
            text.close()

        for handle in handles.values():
            handle.close()
        handles.clear()

        if counts[4] + counts[6] < MIN_NETWORKS:
            raise UpdateError('only %d networks found in the source data, current lists kept' % (counts[4] + counts[6]))

        new_files = set(os.listdir(work_dir))
        for file_name in sorted(new_files - {ANCHOR_FILE}):
            os.replace(os.path.join(work_dir, file_name), os.path.join(TARGET_DIR, file_name))

        # Lists of countries that no longer exist in the source data are removed.
        for file_name in os.listdir(TARGET_DIR):
            if COUNTRY_FILE_PATTERN.match(file_name) and file_name not in new_files:
                os.remove(os.path.join(TARGET_DIR, file_name))

        if ANCHOR_FILE in new_files:
            anchor_path = os.path.join(TARGET_DIR, ANCHOR_FILE)
            os.replace(os.path.join(work_dir, ANCHOR_FILE), anchor_path)
            os.utime(anchor_path)
    finally:
        for handle in handles.values():
            handle.close()
        shutil.rmtree(work_dir, ignore_errors=True)

    return {
        'countries': len(countries),
        'ranges_ipv4': counts[4],
        'ranges_ipv6': counts[6],
        'ranges_total': counts[4] + counts[6],
    }


def refresh_geoip_aliases():
    """Reloads the GeoIP aliases in PF. Returns an error message, or an empty string."""
    try:
        result = subprocess.run(
            [PYTHON, UPDATE_TABLES, '--types', 'geoip'],
            capture_output=True, text=True, timeout=REFRESH_TIMEOUT
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return 'lists updated, but the alias refresh failed: %s' % error

    if result.returncode != 0:
        return 'lists updated, but the alias refresh failed: %s' % result.stderr.strip()[:200]
    return ''


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def resolve_target(target):
    """Returns the IP addresses of an IP address or hostname (A and AAAA records), as strings, without duplicates."""
    if parse_address(target) is not None:
        return [target]

    if not HOSTNAME_PATTERN.match(target):
        raise LookupFailure('invalid IP address or hostname')
    try:
        infos = socket.getaddrinfo(target, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as error:
        raise LookupFailure('unable to resolve %s: %s' % (target, error))

    addresses = []
    for info in infos:
        # IPv6 link local addresses may carry a zone suffix (%interface).
        address = info[4][0].split('%')[0]
        if address not in addresses:
            addresses.append(address)
    return addresses


def find_countries(addresses):
    """
    Returns a dictionary {address: country code}, with an empty code when the address
    is in no list (private, reserved or unknown range). Each country list is read
    at most once, and the search stops as soon as every address is found.
    """
    countries = {address: '' for address in addresses}
    # (address, version, address as an integer) of each address to find.
    pending_all = [(address,) + parse_address(address) for address in addresses]

    for file_name in sorted(os.listdir(TARGET_DIR)):
        if not COUNTRY_FILE_PATTERN.match(file_name):
            continue
        version = 4 if file_name.endswith('IPv4') else 6
        bits = FAMILIES[version][1]
        pending = [item for item in pending_all if item[1] == version and not countries[item[0]]]
        if not pending:
            continue

        with open(os.path.join(TARGET_DIR, file_name)) as handle:
            for line in handle:
                parsed = parse_network(line.strip())
                if parsed is None:
                    continue   # empty or malformed line
                host_bits = bits - parsed[2]
                for item in [item for item in pending if item[2] >> host_bits == parsed[1] >> host_bits]:
                    countries[item[0]] = file_name[:2]
                    pending.remove(item)
                if not pending:
                    break

        if all(countries.values()):
            break
    return countries


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def command_update():
    os.makedirs(STATE_DIR, exist_ok=True)
    lock_handle = open(LOCK_FILE, 'a')
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print('an update is already running')
        return 1

    started = time.time()
    progress = Progress()
    progress.set(0)
    stats = read_stats()
    stats['last_attempt'] = int(started)
    write_stats(stats)

    try:
        if foreign_geoip_url_configured():
            raise UpdateError(
                'a GeoIP URL is set in Firewall: Aliases: GeoIP settings. '
                'OPNsense would overwrite these lists: clear the URL, then update again.'
            )

        log('downloading %s' % SOURCE_URL)
        download_source(lambda fraction: progress.set(fraction * PROGRESS_DOWNLOAD))
        progress.set(PROGRESS_DOWNLOAD)

        stats.update(write_country_files(
            lambda fraction: progress.set(PROGRESS_DOWNLOAD + fraction * PROGRESS_WRITE)
        ))
        stats['last_success'] = int(time.time())
        # Published before the alias refresh, so the refresh keeps alias.stats, and after,
        # in case the GeoIP URL was not set to the plugin URL yet and the refresh reset it.
        publish_geoip_source(stats)
        stats['message'] = refresh_geoip_aliases()
        publish_geoip_source(stats)
        progress.set(100)
        stats['status'] = 'ok' if stats['message'] == '' else 'warning'
        stats['duration'] = round(time.time() - started, 1)
        log('update done: %d countries, %d IPv4 ranges, %d IPv6 ranges' % (
            stats['countries'], stats['ranges_ipv4'], stats['ranges_ipv6']
        ))
    except (UpdateError, OSError, ValueError, csv.Error, zipfile.BadZipFile) as error:
        # The current lists are kept, so the aliases keep their previous content.
        stats['status'] = 'error'
        stats['message'] = str(error)
        log('update failed: %s' % error, syslog.LOG_ERR)
    finally:
        try:
            os.remove(DOWNLOAD_FILE)
        except OSError:
            pass

    write_stats(stats)
    Progress.clear()
    print(stats['message'] or 'OK')
    return 0 if stats['status'] != 'error' else 1


def command_status():
    stats = read_stats()
    stats['running'] = is_update_running()
    stats['progress'] = Progress.read() if stats['running'] else None
    stats['geoip_url_set'] = foreign_geoip_url_configured()
    print(json.dumps(stats))
    return 0


def command_sync():
    try:
        publish_geoip_source(read_stats())
    except OSError as error:
        print('unable to write the GeoIP source files: %s' % error)
        return 1
    print('OK')
    return 0


def command_lookup(target):
    result = {'status': 'ok', 'message': '', 'target': target, 'results': []}
    try:
        if not os.path.isfile(os.path.join(TARGET_DIR, ANCHOR_FILE)):
            raise LookupFailure('no country list yet: start an update first')
        addresses = resolve_target(target)
        countries = find_countries(addresses)
        result['results'] = [{'address': address, 'country': countries[address]} for address in addresses]
    except (LookupFailure, OSError) as error:
        result['status'] = 'error'
        result['message'] = str(error)

    print(json.dumps(result))
    return 0 if result['status'] == 'ok' else 1


def main():
    parser = argparse.ArgumentParser(description='GeoIP country lists built from the IPLocate.io database')
    parser.add_argument('command', choices=['update', 'status', 'sync', 'lookup'])
    parser.add_argument('target', nargs='?', default='', help='IP address or hostname (lookup command)')
    args = parser.parse_args()

    syslog.openlog('osgeoip', facility=syslog.LOG_LOCAL4)
    commands = {
        'update': command_update,
        'status': command_status,
        'sync': command_sync,
        'lookup': lambda: command_lookup(args.target.strip()),
    }
    return commands[args.command]()


if __name__ == '__main__':
    sys.exit(main())
