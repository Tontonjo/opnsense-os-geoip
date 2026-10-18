{#
 # index.volt
 # Version: 2.0.0
 #
 # Copyright (C) 2026 Async IT
 # All rights reserved. BSD 2-Clause License, see the plugin source files.
 #
 # Firewall: GeoIP page: settings, manual update, statistics and country lookup.
 #
 # Changelog:
 #   2.0.0  Renamed for os-geoip (API /api/osgeoip), IPLocate.io attribution (required by CC BY-SA 4.0).
 #   1.3.0  Country lookup.
 #}

<script>
    $(document).ready(function () {
        const POLL_INTERVAL = 3000;
        const MAX_START_POLLS = 20;   // polls allowed before a started update becomes visible
        let updateRequestedAt = 0;
        let startPolls = 0;

        /** Formats a number with thousands separators, or a dash when missing. */
        function formatNumber(value) {
            return (value === null || value === undefined) ? '-' : Number(value).toLocaleString();
        }

        /** Formats a UNIX timestamp as a local date and time, or a dash when missing. */
        function formatDate(timestamp) {
            return timestamp ? new Date(timestamp * 1000).toLocaleString() : '-';
        }

        /** Displays the status returned by /api/osgeoip/service/status. */
        function renderStatus(data) {
            const labels = {
                'never': "{{ lang._('Never updated') }}",
                'ok': "{{ lang._('OK') }}",
                'warning': "{{ lang._('Warning') }}",
                'error': "{{ lang._('Error') }}"
            };
            const classes = {'ok': 'label-success', 'warning': 'label-warning', 'error': 'label-danger'};
            const status = data.running ? 'running' : (data.status || 'never');
            const runningLabel = "{{ lang._('Update running...') }}"
                + (data.progress !== null && data.progress !== undefined ? ' ' + data.progress + ' %' : '');

            $('#osgeoip_status')
                .attr('class', 'label ' + (data.running ? 'label-info' : (classes[status] || 'label-default')))
                .text(data.running ? runningLabel : (labels[status] || status));
            $('#osgeoip_message').text(data.message || '');
            $('#osgeoip_last_success').text(formatDate(data.last_success));
            $('#osgeoip_last_attempt').text(formatDate(data.last_attempt));
            $('#osgeoip_duration').text(data.duration ? data.duration + ' s' : '-');
            $('#osgeoip_countries').text(formatNumber(data.countries));
            $('#osgeoip_ranges_total').text(formatNumber(data.ranges_total));
            $('#osgeoip_ranges_ipv4').text(formatNumber(data.ranges_ipv4));
            $('#osgeoip_ranges_ipv6').text(formatNumber(data.ranges_ipv6));
            $('#osgeoip_url_warning').toggle(data.geoip_url_set === true);
            $('#updateAct').prop('disabled', data.running === true);
        }

        /** Reads the status, and keeps polling while an update is starting or running. */
        function refreshStatus() {
            ajaxGet('/api/osgeoip/service/status', {}, function (data) {
                renderStatus(data);

                const waitingForStart = updateRequestedAt > 0
                    && (data.last_attempt || 0) < updateRequestedAt
                    && startPolls++ < MAX_START_POLLS;

                if (data.running || waitingForStart) {
                    setTimeout(refreshStatus, POLL_INTERVAL);
                } else {
                    updateRequestedAt = 0;
                    $('#updateAct_progress').removeClass('fa fa-spinner fa-pulse');
                }
            });
        }

        mapDataToFormUI({'frm_general_settings': '/api/osgeoip/settings/get'});
        refreshStatus();

        $('#saveAct').click(function () {
            saveFormToEndpoint('/api/osgeoip/settings/set', 'frm_general_settings', function (data) {
                if (data.cron) {
                    BootstrapDialog.show({
                        type: BootstrapDialog.TYPE_WARNING,
                        title: "{{ lang._('Scheduled task') }}",
                        message: data.cron
                    });
                }
                if (data.geoip) {
                    BootstrapDialog.show({
                        type: BootstrapDialog.TYPE_WARNING,
                        title: "{{ lang._('GeoIP') }}",
                        message: data.geoip
                    });
                }
                refreshStatus();
            });
        });

        $('#updateAct').click(function () {
            $('#updateAct').prop('disabled', true);
            $('#updateAct_progress').addClass('fa fa-spinner fa-pulse');
            ajaxCall('/api/osgeoip/service/update', {}, function () {
                // Seconds, as the update script stores UNIX timestamps.
                updateRequestedAt = Math.floor(Date.now() / 1000) - 1;
                startPolls = 0;
                refreshStatus();
            });
        });

        /** Looks up the country of the IP address or hostname entered in the lookup field. */
        function lookupCountry() {
            const target = $('#lookup_target').val().trim();
            const $results = $('#lookup_results').empty();
            $('#lookup_message').text('');
            if (target === '') {
                return;
            }

            $('#lookupAct').prop('disabled', true);
            $('#lookupAct_progress').addClass('fa fa-spinner fa-pulse');
            ajaxGet('/api/osgeoip/service/lookup', {'target': target}, function (data) {
                $('#lookupAct').prop('disabled', false);
                $('#lookupAct_progress').removeClass('fa fa-spinner fa-pulse');

                if (data.status !== 'ok') {
                    $('#lookup_message').text(data.message || "{{ lang._('Lookup failed') }}");
                    return;
                }
                (data.results || []).forEach(function (item) {
                    $results.append($('<tr>')
                        .append($('<td>').text(item.address))
                        .append($('<td>').text(item.country || "{{ lang._('Not found') }}")));
                });
            });
        }

        $('#lookupAct').click(lookupCountry);
        $('#lookup_target').keypress(function (event) {
            if (event.which === 13) {
                lookupCountry();
            }
        });
    });
</script>

<div class="alert alert-warning" role="alert" id="osgeoip_url_warning" style="display: none;">
    {{ lang._('A URL is set in Firewall: Aliases: GeoIP settings. OPNsense would overwrite the lists built by this plugin, so updates are refused. Clear the URL, then start an update: the plugin then sets its own local URL.') }}
</div>

<div class="content-box">
    {{ partial("layout_partials/base_form", ['fields': generalForm, 'id': 'frm_general_settings']) }}
    <div class="col-md-12">
        <hr/>
        <button class="btn btn-primary" id="saveAct" type="button">
            <b>{{ lang._('Save') }}</b> <i id="saveAct_progress"></i>
        </button>
        <br/><br/>
    </div>
</div>

<div class="content-box">
    <table class="table table-striped opnsense_standard_table_form">
        <thead>
            <tr>
                <th colspan="2">{{ lang._('Statistics') }}</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td style="width: 22%;">{{ lang._('Status') }}</td>
                <td><span id="osgeoip_status" class="label label-default">-</span> <span id="osgeoip_message"></span></td>
            </tr>
            <tr>
                <td>{{ lang._('Last successful update') }}</td>
                <td id="osgeoip_last_success">-</td>
            </tr>
            <tr>
                <td>{{ lang._('Last attempt') }}</td>
                <td id="osgeoip_last_attempt">-</td>
            </tr>
            <tr>
                <td>{{ lang._('Duration') }}</td>
                <td id="osgeoip_duration">-</td>
            </tr>
            <tr>
                <td>{{ lang._('Countries') }}</td>
                <td id="osgeoip_countries">-</td>
            </tr>
            <tr>
                <td>{{ lang._('Total ranges') }}</td>
                <td id="osgeoip_ranges_total">-</td>
            </tr>
            <tr>
                <td>{{ lang._('IPv4 ranges') }}</td>
                <td id="osgeoip_ranges_ipv4">-</td>
            </tr>
            <tr>
                <td>{{ lang._('IPv6 ranges') }}</td>
                <td id="osgeoip_ranges_ipv6">-</td>
            </tr>
        </tbody>
    </table>
    <div class="col-md-12">
        <button class="btn btn-default" id="updateAct" type="button">
            <b>{{ lang._('Update now') }}</b> <i id="updateAct_progress"></i>
        </button>
        <br/><br/>
    </div>
</div>

<div class="content-box">
    <table class="table table-striped opnsense_standard_table_form">
        <thead>
            <tr>
                <th colspan="2">{{ lang._('Country lookup') }}</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td style="width: 22%;">{{ lang._('IP address or hostname') }}</td>
                <td>
                    <input type="text" id="lookup_target" maxlength="253" style="width: 300px; display: inline-block;"/>
                    <button class="btn btn-default" id="lookupAct" type="button">
                        <b>{{ lang._('Lookup') }}</b> <i id="lookupAct_progress"></i>
                    </button>
                    <span id="lookup_message" class="text-danger"></span>
                </td>
            </tr>
        </tbody>
        <tbody id="lookup_results"></tbody>
    </table>
</div>

<!-- Attribution required by the CC BY-SA 4.0 license of the IPLocate.io database. -->
<div class="col-md-12 text-muted">
    <small>{{ lang._('IP address data powered by') }} <a href="https://www.iplocate.io" target="_blank" rel="noopener noreferrer">IPLocate.io</a> (CC BY-SA 4.0).</small>
</div>
