#!/usr/local/bin/php
<?php

/**
 * apply_defaults.php
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
 * --------------------------------------------------------------------------------------
 *
 * Applies the default settings on a first install, from the package install script:
 * automatic update enabled, so the scheduled task is created in System: Settings: Cron
 * and the GeoIP URL of Firewall: Aliases is set to the plugin URL.
 * Settings saved at least once (also kept after a removal) are left unchanged,
 * so a user who disabled the automatic update keeps that choice on upgrade or reinstall.
 *
 * Usage: apply_defaults.php
 */

require_once 'script/load_phalcon.php';

use OPNsense\Core\Config;
use OPNsense\OsGeoip\OsGeoip;

if (isset(Config::getInstance()->object()->OPNsense->osgeoip)) {
    echo "settings already stored, left unchanged\n";
    exit(0);
}

$mdlOsGeoip = new OsGeoip();
$error = $mdlOsGeoip->syncCronJob();
if ($error !== '') {
    fwrite(STDERR, $error . "\n");
    exit(1);
}

if ((string)$mdlOsGeoip->general->enabled === '1' && !OsGeoip::syncGeoipUrl(true)) {
    echo "a GeoIP URL entered by the user is set, left unchanged\n";
}
exit(0);
