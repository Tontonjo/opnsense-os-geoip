<?php

/**
 * SettingsController.php
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
 */

namespace OPNsense\OsGeoip\Api;

use OPNsense\Base\ApiMutableModelControllerBase;
use OPNsense\OsGeoip\OsGeoip;

/**
 * Reads and saves the plugin settings, and keeps the scheduled task in
 * System: Settings: Cron in line with them.
 */
class SettingsController extends ApiMutableModelControllerBase
{
    protected static $internalModelName = 'osgeoip';
    protected static $internalModelClass = 'OPNsense\OsGeoip\OsGeoip';

    /**
     * Saves the settings, then creates, updates or removes the scheduled task.
     * When the automatic update is enabled, also sets the GeoIP URL to the plugin URL.
     */
    public function setAction()
    {
        $result = parent::setAction();
        if (($result['result'] ?? '') === 'saved') {
            $cronResult = $this->getModel()->syncCronJob();
            if ($cronResult !== '') {
                $result['cron'] = $cronResult;
            }
            if ((string)$this->getModel()->general->enabled === '1' && !OsGeoip::syncGeoipUrl(true)) {
                $result['geoip'] = gettext(
                    'A URL is set in Firewall: Aliases: GeoIP settings. Clear it, so that this plugin can provide the GeoIP lists.'
                );
            }
        }
        return $result;
    }
}
