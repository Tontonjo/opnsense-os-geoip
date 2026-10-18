# os-geoip

<img width="632" height="430" alt="image" src="https://github.com/user-attachments/assets/4f3d3390-665a-431c-977e-7188fd0e5c63" />


## Tonton Jo  
### Join the community:
[![Youtube](https://badgen.net/badge/Youtube/Subscribe)](http://youtube.com/channel/UCnED3K6K5FDUp-x_8rwpsZw?sub_confirmation=1)
[![Discord Tonton Jo](https://badgen.net/discord/members/h6UcpwfGuJ?label=Discord%20Tonton%20Jo%20&icon=discord)](https://discord.gg/h6UcpwfGuJ)
### Support my work, give a thanks and help the youtube channel:
[![Ko-Fi](https://badgen.net/badge/Buy%20me%20a%20Coffee/Link?icon=buymeacoffee)](https://ko-fi.com/tontonjo)
[![Infomaniak](https://badgen.net/badge/Infomaniak/Affiliated%20link?icon=K)](https://www.infomaniak.com/goto/fr/home?utm_term=6151f412daf35)
[![Express VPN](https://badgen.net/badge/Express%20VPN/Affiliated%20link?icon=K)](https://www.xvuslink.com/?a_fid=TontonJo)

Version: 2.1.0 (plugin 2.1)

OPNsense plugin that builds the country lists used by **GeoIP aliases** from the free
[IP to Country database of IPLocate.io](https://github.com/iplocate/ip-address-databases/tree/main/ip-to-country),
updated daily.

No MaxMind account, license key or download URL is needed, and no MaxMind data is used.

IP address data powered by [IPLocate.io](https://www.iplocate.io), licensed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

This plugin replaces **os-rir-geoip** (version 1.x, lists built from the RIR statistics).

## Features

- Works with your existing GeoIP aliases (Firewall: Aliases, type GeoIP).
- Daily automatic update (enabled by default at 03:17), or on demand with **Update now**.
- Status with progress percentage, and statistics: countries, total ranges, IPv4 ranges, IPv6 ranges.
- Safe updates: if the database cannot be downloaded or looks incomplete, the current lists are kept.
- Country lookup: enter an IP address or a hostname on the plugin page to get its country code
  (every IPv4 and IPv6 address of a hostname is shown), based on the current lists.

## Requirements

- OPNsense with SSH access as root.
- Outbound HTTPS from the firewall to `github.com` and `media.githubusercontent.com` (about 9 MB per update).
- No URL of your own in Firewall: Aliases: GeoIP settings (otherwise OPNsense overwrites the lists).
  The plugin sets its own local URL there (`file:///var/db/osgeoip/lists`), see *Good to know*.

## Installation

The plugin is built on the firewall from this repository, using the OPNsense plugins build tree.
Connect to the firewall with SSH as root and choose option **8) Shell**.

```sh
# 1. git and the OPNsense plugins build tree (/usr/plugins)
pkg install -y git
opnsense-code plugins

# 2. This repository
git clone https://github.com/Tontonjo/opnsense-os-geoip.git /root/opnsense-os-geoip
cp -R /root/opnsense-os-geoip/security/geoip /usr/plugins/security/

# 3. Build and install the package
cd /usr/plugins/security/geoip
make package
pkg add work/pkg/os-geoip-*.pkg

# 4. Register the plugin in System: Firmware: Plugins
/usr/local/opnsense/scripts/firmware/register.php install os-geoip
```

Step 4 is needed because the package is installed with `pkg add` instead of the firmware page. Without it, the plugin is listed as **misconfigured**.

Then reload the web interface (Ctrl+F5): the page is in **Firewall: GeoIP**.

## Quick start

1. **Firewall: Aliases: GeoIP settings**: clear any URL of your own, then click **Apply**.
2. **Firewall: GeoIP**: click **Update now** and wait for the status **OK**.
3. Optional: change the hour of the automatic update (enabled at install, 03:17 by default), then click **Save**.
4. Use your GeoIP aliases in firewall rules as usual.

## Update

```sh
cd /root/opnsense-os-geoip && git pull
rm -rf /usr/plugins/security/geoip
cp -R /root/opnsense-os-geoip/security/geoip /usr/plugins/security/
cd /usr/plugins/security/geoip && make upgrade
```

## Uninstall

1. **Firewall: GeoIP**: untick **Automatic update** and click **Save** (removes the scheduled task).
2. Remove the package and its registration (the plugin URL is cleared from Firewall: Aliases: GeoIP settings):

```sh
pkg delete -y os-geoip
/usr/local/opnsense/scripts/firmware/register.php remove os-geoip
```

## Good to know

- The IPLocate.io database holds about 2.1 million networks (about 0.8 million IPv4 and 1.4 million IPv6),
  much more detailed than the RIR statistics. A GeoIP alias with many countries can exceed the PF table limit:
  if an alias fails to load, raise **Firewall: Settings: Advanced: Firewall Maximum Table Entries**.
- An update takes less than a minute on a typical firewall and uses little memory (the database is read line by line).
- The plugin sets the URL of Firewall: Aliases: GeoIP settings to `file:///var/db/osgeoip/lists`, on **Save** with
  automatic update enabled, on **Update now**, and at the first install (automatic update enabled by default).
  OPNsense never downloads anything from this local URL, but it then
  considers the GeoIP source as configured: the message "In order to use GeoIP, you need to configure a source"
  no longer appears, and the GeoIP settings tab shows the date and number of ranges of the last update.
  The URL of the former os-rir-geoip plugin is replaced automatically.
- The **Update GeoIP** button of Firewall: Aliases: GeoIP settings resets these statistics to zero (the lists are kept).
  Use **Update now** on the plugin page instead.
- If the lists are not updated for more than 24 hours, OPNsense also resets these statistics when it reloads a GeoIP alias.

This project is not affiliated with OPNsense, Deciso, MaxMind or IPLocate.io.
