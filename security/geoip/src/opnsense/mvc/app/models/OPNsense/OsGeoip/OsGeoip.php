<?php

/**
 * OsGeoip.php
 * Version: 2.1.0
 *
 * Copyright (C) 2026 Async IT
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
 * AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 * AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
 * OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 *
 * Changelog:
 *   2.1.0  syncCronJob() moved here from SettingsController (also used at install).
 *   2.0.0  Renamed OsGeoip (was RirGeoip), URL of the former os-rir-geoip plugin replaced.
 *   1.1.0  LOCAL_GEOIP_URL and syncGeoipUrl().
 */

namespace OPNsense\OsGeoip;

use OPNsense\Base\BaseModel;
use OPNsense\Core\Backend;
use OPNsense\Core\Config;
use OPNsense\Cron\Cron;
use OPNsense\Firewall\Alias;

/**
 * Settings of the GeoIP plugin (fields are defined in OsGeoip.xml).
 */
class OsGeoip extends BaseModel
{
    /**
     * GeoIP URL set in Firewall: Aliases: GeoIP settings while the plugin provides the lists.
     * Not http, so OPNsense never downloads anything from it. Keep in line with osgeoip.py.
     */
    public const LOCAL_GEOIP_URL = 'file:///var/db/osgeoip/lists';

    /**
     * URLs set by the former os-rir-geoip plugin, handled as plugin URLs (replaced or cleared).
     */
    public const LEGACY_GEOIP_URLS = ['file:///var/db/rirgeoip/lists'];

    private const CRON_ORIGIN = 'OsGeoip';
    private const CRON_COMMAND = 'osgeoip update';
    private const CRON_DESCRIPTION = 'Update GeoIP country lists (IPLocate.io)';
    private const CRON_MINUTE = '17';

    /**
     * Creates, updates or removes the scheduled task in System: Settings: Cron
     * according to the automatic update settings, then saves the configuration.
     * Returns an error message, or an empty string.
     */
    public function syncCronJob(): string
    {
        $mdlCron = new Cron();
        $uuid = (string)$this->general->cronUuid;
        $job = $uuid !== '' ? $mdlCron->getNodeByReference('jobs.job.' . $uuid) : null;

        if ((string)$this->general->enabled === '1') {
            if ($job === null) {
                $uuid = $mdlCron->newDailyJob(self::CRON_ORIGIN, self::CRON_COMMAND, self::CRON_DESCRIPTION, '*', '1');
                $job = $mdlCron->getNodeByReference('jobs.job.' . $uuid);
                $this->general->cronUuid = $uuid;
            }
            $job->minutes = self::CRON_MINUTE;
            $job->hours = (string)$this->general->hour;
            $job->enabled = '1';
        } elseif ($job !== null) {
            $mdlCron->jobs->job->del($uuid);
            $this->general->cronUuid = '';
        } elseif ($uuid !== '') {
            // The task was removed manually in System: Settings: Cron.
            $this->general->cronUuid = '';
        } else {
            return '';
        }

        if ($mdlCron->performValidation()->count() > 0) {
            return 'unable to update the scheduled task';
        }

        $mdlCron->serializeToConfig();
        $this->serializeToConfig(false, true);
        Config::getInstance()->save();

        $backend = new Backend();
        $backend->configdRun('template reload OPNsense/Cron');
        $backend->configdRun('cron restart');

        return '';
    }

    /**
     * Sets the GeoIP URL of Firewall: Aliases to the plugin URL ($enable = true) or clears it.
     * Without a GeoIP source, OPNsense reports "you need to configure a source" in Firewall: Aliases.
     * A URL entered by the user is never changed.
     * Returns false when such a URL is set, true otherwise.
     */
    public static function syncGeoipUrl(bool $enable): bool
    {
        $mdlAlias = new Alias();
        $current = trim((string)$mdlAlias->geoip->url);
        $pluginUrls = array_merge(['', self::LOCAL_GEOIP_URL], self::LEGACY_GEOIP_URLS);
        if (!in_array($current, $pluginUrls, true)) {
            return false;
        }

        $target = $enable ? self::LOCAL_GEOIP_URL : '';
        if ($current !== $target) {
            $mdlAlias->geoip->url = $target;
            $mdlAlias->serializeToConfig(false, true);
            Config::getInstance()->save();
            (new Backend())->configdRun('template reload OPNsense/Filter');
        }

        if ($enable) {
            // Writes the GeoIP source files from the last update, when there is one.
            (new Backend())->configdRun('osgeoip sync');
        }
        return true;
    }
}
