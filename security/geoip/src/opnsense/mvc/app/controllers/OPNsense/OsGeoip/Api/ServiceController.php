<?php

/**
 * ServiceController.php
 * Version: 2.0.0
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

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Backend;
use OPNsense\OsGeoip\OsGeoip;

/**
 * Starts an update, returns the statistics of the last update and looks up the country of an address.
 */
class ServiceController extends ApiControllerBase
{
    /**
     * Sets the GeoIP URL to the plugin URL, then starts an update in the background
     * (POST only, CSRF protected). The page then polls statusAction() until the update is finished.
     * With a URL entered by the user, the update script refuses to run and reports it.
     */
    public function updateAction()
    {
        if (!$this->request->isPost()) {
            return ['status' => 'error', 'message' => 'POST request required'];
        }

        OsGeoip::syncGeoipUrl(true);
        (new Backend())->configdRun('osgeoip update', true);
        return ['status' => 'started'];
    }

    /**
     * Returns the statistics of the last update, and whether an update is running.
     */
    public function statusAction()
    {
        $response = (new Backend())->configdRun('osgeoip status');
        $status = json_decode((string)$response, true);

        if (!is_array($status)) {
            return ['status' => 'error', 'message' => 'unable to read the plugin status'];
        }
        return $status;
    }

    /**
     * Returns the country code of an IP address, or of every address of a hostname,
     * found in the current lists. The target is also validated by the lookup script.
     */
    public function lookupAction()
    {
        $target = trim((string)$this->request->get('target'));
        if (strlen($target) > 253 || !preg_match('/^[A-Za-z0-9_:][A-Za-z0-9_.:-]*$/', $target)) {
            return ['status' => 'error', 'message' => gettext('Enter a valid IP address or hostname.')];
        }

        $response = (new Backend())->configdpRun('osgeoip lookup', [$target]);
        $result = json_decode((string)$response, true);

        if (!is_array($result)) {
            return ['status' => 'error', 'message' => 'unable to read the lookup result'];
        }
        return $result;
    }
}
