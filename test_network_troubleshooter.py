"""Focused regressions for offline troubleshooting and repair."""
from contextlib import redirect_stderr, redirect_stdout
import fcntl
from io import StringIO
from pathlib import Path
import re
import runpy
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

app = runpy.run_path(str(Path(__file__).with_name('network-troubleshooter')))
env = app['diagnose'].__globals__
wake = runpy.run_path(str(Path(__file__).with_name('wake-usb-ethernet')))['wake']


class NetworkTests(unittest.TestCase):
    def test_no_carrier_surfaces_usb_driver_mode_and_device_scoped_resets(self):
        def configuration(number, interface_class):
            return bytes((9, 2, 18, 0, 1, number, 0, 128, 50,
                          9, 4, 0, 0, 0, interface_class, 0, 0, 0))

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            usb = root / '3-2.1'
            interface = usb / '3-2.1:1.0'
            interface.mkdir(parents=True)
            adapter = root / 'net' / 'eth0'
            adapter.mkdir(parents=True)
            (adapter / 'device').symlink_to(interface)
            (interface / 'subsystem').symlink_to(root / 'usb')
            (interface / 'driver').symlink_to(root / 'drivers' / 'cdc_ncm')
            for name, value in [('idVendor', '1234'), ('idProduct', '5678'), ('bConfigurationValue', '1')]:
                (usb / name).write_text(value + '\n')
            (usb / 'power').mkdir()
            (usb / 'power/runtime_status').write_text('active\n')

            journal = ['usb 3-2: reset hub', 'usb 3-2.10: reset sibling',
                       'usb 3-2.1: reset SuperSpeed USB device number 4',
                       'cdc_ncm 3-2.1:1.0: adapter message',
                       'usb 3-2.1: reset SuperSpeed USB device number 4']

            def command(*args):
                if args[0] == 'nmcli':
                    return 0, 'GENERAL.STATE:20 (unavailable)\nWIRED-PROPERTIES.CARRIER:off'
                if args[0] == 'journalctl':
                    self.assertIn('-k', args)
                    return 0, '\n'.join(line for line in journal if re.search(args[-1], line))
                if args[:2] == ('ip', '-j'):
                    return 2, 'No route'
                self.fail(f'Unexpected command {args}')

            cdc_mode = configuration(1, 2)
            for extra, vendor_hint in [(configuration(4, 255), True), (configuration(4, 2), False),
                                       (configuration(4, 255)[:-1], False)]:
                with self.subTest(extra=extra):
                    (usb / 'descriptors').write_bytes(cdc_mode + extra)
                    details = []
                    with patch.dict(env, SYS_NET=adapter.parent, USB_BUS=root / 'usb',
                                    run=command, usb_wake_available=lambda _: False):
                        result = app['diagnose']('eth0', 'Ethernet', details=details)
                    status, hint = result[1]['Link']
                    self.assertEqual(status, 'No cable link')
                    self.assertIn('Check the Ethernet cable', hint)
                    self.assertIn('repeated resets', hint)
                    self.assertEqual('native driver support for 1234:5678' in hint, vendor_hint)
                    evidence = '\n'.join(details)
                    self.assertIn('driver cdc_ncm, configuration 1', evidence)
                    self.assertIn('USB runtime power state: active', evidence)
                    self.assertIn('adapter message', evidence)
                    self.assertNotIn('reset sibling', evidence)
                    self.assertNotIn('reset hub', evidence)
                    self.assertNotIn('1234:5678', app['redacted_report']('Ethernet', result, []))

    def test_gateway_and_sign_in_still_work_without_public_route(self):
        def command(*args, **kwargs):
            if args[:2] == ('nmcli', '-t'):
                return 0, ('GENERAL.STATE:100 (connected)\nWIRED-PROPERTIES.CARRIER:on\n'
                           'IP4.ADDRESS[1]:192.0.2.5/24\nIP4.GATEWAY:192.0.2.1')
            if args[0] == 'ping':
                self.assertEqual(args[1:5], ('-4', '-n', '-I', 'eth0'))
                self.assertEqual(args[-1], '192.0.2.1')
                return 0, ''
            if args[0] == 'ip':
                return 2, 'No route'
            if args[:2] == ('nmcli', '-w'):
                return 0, 'full'  # Another adapter is online.
            if args[:2] == ('nmcli', '-g'):
                return 0, '3 (limited)\n0 (unknown)'
            self.fail(f'Unexpected command {args}')

        with patch.dict(env, run=command, portal_url=lambda: 'http://probe.example/'):
            _, rows, _, portal = app['diagnose']('eth0', 'Ethernet')
        self.assertEqual(rows['Gateway'][0], 'Replied')
        self.assertEqual(rows['Ping'][0], 'Skipped')
        self.assertEqual(rows['Sign-in'][0], 'Unverified')
        self.assertEqual(portal, 'http://probe.example/')

    def test_system_route_can_differ_from_the_working_selected_adapter(self):
        def command(*args, **kwargs):
            if args[:2] == ('nmcli', '-t'):
                return 0, ('GENERAL.STATE:100 (connected)\nWIRED-PROPERTIES.CARRIER:on\n'
                           'IP4.ADDRESS[1]:192.0.2.5/24\nIP6.ADDRESS[1]:2001:db8::5/64')
            if args[0] == 'ip':
                if args[1] == '-j':
                    self.assertNotIn('oif', args)
                    return 0, '[{"dev":"tun0"}]' if args[2] == '-4' else '[{"dev":"eth0"}]'
                self.assertEqual(args[-2:], ('oif', 'eth0'))
                return 0, ''
            if args[0] == 'curl':
                return 0, '200'
            return 0, ''

        with patch.dict(env, run=command):
            result = app['diagnose']('eth0', 'Ethernet')
        rows = result[1]
        self.assertEqual(rows['Route'], ('Found', 'IPv4, IPv6'))
        self.assertEqual(rows['System route'][0], 'Mixed')
        self.assertIn('IPv4 to 1.1.1.1 via tun0', rows['System route'][1])
        self.assertIn('IPv6 to 2606:4700:4700::1111 via eth0', rows['System route'][1])
        self.assertEqual(rows['Internet'][0], 'Reached')

    def test_gateway_ping_timeout_distinguishes_failed_pending_and_known_neighbors(self):
        for entry, expected in [
            ('[{"state":["FAILED"]}]', 'neighbor resolution failed'),
            ('[{"state":["INCOMPLETE"]}]', 'neighbor resolution pending'),
            ('[{"state":["STALE"],"lladdr":"02:00:00:00:00:01"}]', 'link-layer address known'),
            ('[]', 'neighbor state unknown'),
        ]:
            with self.subTest(entry=entry):
                run = Mock(side_effect=[(1, ''), (0, entry)])
                with patch.dict(env, run=run):
                    self.assertEqual(app['gateway_check']('eth0', {'IP6.GATEWAY': 'fe80::1%eth0'}),
                                     ('No reply', f'fe80::1 (no reply, {expected})'))
                run.assert_called_with('ip', '-j', '-6', 'neigh', 'show', 'to', 'fe80::1', 'dev', 'eth0')

    def test_missing_address_reports_activation_reason_and_pending_state(self):
        for state, reason, status, note in [
            ('120 (failed)', '17 (DHCP client failed)', 'Missing', 'DHCP client failed'),
            ('120 (failed)', '5 (IP configuration could not be reserved)', 'Missing', 'could not be reserved'),
            ('70 (connecting (getting IP configuration))', '0 (No reason given)', 'Pending', 'still configuring'),
        ]:
            with self.subTest(state=state, reason=reason):
                def command(*args):
                    if args[:2] == ('ip', '-j'):
                        return 2, 'No route'
                    self.assertIn('GENERAL.REASON', args[5])
                    return 0, (f'GENERAL.STATE:{state}\nGENERAL.REASON:{reason}\n'
                               'WIRED-PROPERTIES.CARRIER:on')

                with patch.dict(env, run=command):
                    rows = app['diagnose']('eth0', 'Ethernet')[1]
                self.assertEqual(rows['IP address'][0], status)
                self.assertIn(note, rows['IP address'][1])
                self.assertNotIn('DHCP server', rows['IP address'][1])

    def test_ethernet_link_only_flags_counter_growth_on_the_same_interface(self):
        for after_index, after_crc, expected in [('7', '8', True), ('7', '5', False),
                                                  ('8', '8', False), ('7', '0', False)]:
            with self.subTest(after_index=after_index, after_crc=after_crc):
                with tempfile.TemporaryDirectory() as temp:
                    adapter = Path(temp) / 'eth0'
                    (adapter / 'statistics').mkdir(parents=True)
                    for attribute, value in [('ifindex', '7'), ('speed', '2500'), ('duplex', 'full'),
                                             ('statistics/rx_crc_errors', after_crc)]:
                        (adapter / attribute).write_text(value)

                    def diagnose_adapter(*args):
                        (adapter / 'ifindex').write_text(after_index)
                        return '', {'Link': ('Up', '')}, '', ''

                    with patch.dict(env, SYS_NET=adapter.parent, diagnose_adapter=diagnose_adapter,
                                    system_route_check=lambda _: ('Unverified', '')):
                        history = {'eth0': ('7', {'receive CRC errors': 5})}
                        link = app['diagnose']('eth0', 'Ethernet', ethernet_history=history)[1]['Link'][1]
                self.assertIn('2,500 Mbps, full duplex', link)
                self.assertEqual('Since the last check: receive CRC errors +3' in link, expected)

    def test_custom_dns_compares_links_without_changing_the_public_https_probe(self):
        def command(*args, **kwargs):
            if args[:2] == ('nmcli', '-t'):
                return 0, ('GENERAL.STATE:100 (connected)\nWIRED-PROPERTIES.CARRIER:on\n'
                           'IP4.ADDRESS[1]:192.0.2.5/24')
            if args[:2] == ('resolvectl', 'domain'):
                return 0, 'Link 7 (eth0): ~office.example'
            if args[0] == 'resolvectl':
                if args[-1] == 'private.office.example':
                    return (1, 'Lookup timed out') if '-i' in args else (
                        0, 'private.office.example: 192.0.2.42 -- link: tun0')
                self.assertEqual(args[-1], 'archlinux.org')
                return 0, 'archlinux.org IN A 192.0.2.80 -- link: eth0'
            if args[0] == 'curl':
                self.assertIn('archlinux.org:443:192.0.2.80', args)
                self.assertIn('if!eth0', args)
                self.assertEqual(args[-1], 'https://archlinux.org/')
                return 0, '200'
            return 0, ''

        with tempfile.TemporaryDirectory() as temp, patch.dict(
                env, run=command, STATE_DIR=Path(temp), recovery_settings=lambda: None,
                adapters=lambda: ([('eth0', 'Ethernet', 'connected')], '')), patch.object(
                    sys, 'argv', ['network-troubleshooter', '--device', 'eth0', '--dns-target',
                                  'private.office.example', '--redacted-report']):
            with redirect_stderr(StringIO()), redirect_stdout(StringIO()) as stdout:
                self.assertEqual(app['main'](), 0)
            report = next(Path(temp).glob('network-*.txt')).read_text()
        self.assertIn('Internet — Reached', stdout.getvalue())
        self.assertIn('DNS target — Unverified', stdout.getvalue())
        self.assertIn('System resolver: answer via tun0', report)
        self.assertIn('~office.example', report)
        self.assertNotIn('office.example', stdout.getvalue())

    def test_redacted_report_drops_raw_evidence(self):
        before = ('Example SSID', {'Link': ('Joined', 'Example SSID')}, 'private-uuid', '')
        after = ('Offline', {'Gateway': ('No reply', '192.0.2.1 (no reply)')}, '', '')
        result = app['redacted_report']('Wi-Fi', after, [('Repair result', 1, 'token and hostname')], before)
        self.assertIn('Repair result — exit 1', result)
        for private in ('Example SSID', '192.0.2.1', 'token', 'hostname', 'private-uuid'):
            self.assertNotIn(private, result)

    def test_second_repair_cannot_touch_the_locked_adapter(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)
            locks = state / 'locks'
            locks.mkdir()
            with (locks / 'eth0.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                repair = Mock(return_value=(0, ''))
                with patch.dict(env, STATE_DIR=state, repair_locked=repair):
                    code, detail = app['repair_connection']('eth0', 'Ethernet', 'profile', None, Mock())
                    other_code, _ = app['repair_connection']('eth1', 'Ethernet', 'profile', None, Mock())
                self.assertEqual(code, 1)
                self.assertIn('already running', detail)
                self.assertEqual(other_code, 0)
                self.assertEqual(repair.call_args.args[0], 'eth1')
                repair.assert_called_once()

    def test_repair_is_visible_without_a_saved_profile(self):
        result = ('Ethernet link is down', {'Link': ('No cable link', 'Check the cable.')}, '', '')
        desktop = Mock(return_value=Mock(returncode=12))
        with patch.dict(env, desktop=desktop):
            self.assertEqual(app['show']('eth0', 'Ethernet', result), 12)
        self.assertIn('--button=Repair connection:12', desktop.call_args.args)
        self.assertIn('--button=DNS target:18', desktop.call_args.args)

    def test_repair_refuses_to_switch_profiles_after_diagnosis(self):
        attempt = Mock()
        with patch.dict(env, active_profile=Mock(return_value=('100', 'different-profile'))):
            code, detail = app['repair_locked']('wld0', 'Wi-Fi', 'saved-profile', None, attempt)
        self.assertEqual(code, 1)
        self.assertIn('active profile changed', detail)
        attempt.assert_not_called()

    def test_repair_reports_why_driver_recovery_was_skipped(self):
        command = Mock()
        with patch.dict(env, active_profile=Mock(return_value=('50', 'saved-profile')),
                        reconnect_profile=Mock(return_value=(3, 'Activation timed out.')),
                        driver_recovery_blocker=Mock(return_value='Autoconnect is off.'),
                        run=command):
            code, detail = app['repair_locked'](
                'wld0', 'Wi-Fi', 'saved-profile', ('saved-profile', 'brcmfmac', 'recover.service'),
                lambda label, operation: operation())
        self.assertEqual(code, 3)
        self.assertIn('Driver recovery skipped. Autoconnect is off.', detail)
        command.assert_not_called()

    def test_cli_repair_reaches_recovery_and_checks_internet_afterward(self):
        profile = '9afb388e-62de-4794-8d16-c3c751318ae4'
        config = ('wld0', profile, 'brcmfmac', 'recover.service')
        disconnected = ('Wi-Fi is disconnected', {'Link': ('Disconnected', '')}, '', '')
        connected = ('Internet access unverified',
                     {'Link': ('Joined', ''), 'Internet': ('Unverified', ''), 'Sign-in': ('Not detected', '')},
                     profile, '')
        stdout = StringIO()
        stderr = StringIO()
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)

            def report():
                return next(state.glob('network-*.txt')).read_text()

            def restart(*args, **kwargs):
                self.assertEqual(args, ('/usr/bin/pkexec', '/usr/bin/systemctl', '--wait', 'start',
                                        'recover.service'))
                self.assertIn('Reconnect saved profile (exit 3)', report())
                self.assertIn('In progress', report())
                return 0, ''

            with patch.dict(env, STATE_DIR=state, recovery_settings=lambda: config,
                            adapters=lambda: ([('wld0', 'Wi-Fi', 'connecting')], ''),
                            diagnose=Mock(side_effect=(disconnected, connected)),
                            report_text=Mock(side_effect=('offline snapshot', 'after snapshot')),
                            profile_matches_kind=Mock(return_value=True),
                            active_profile=Mock(side_effect=(('50', profile), ('50', profile), ('100', profile))),
                            reconnect_profile=Mock(return_value=(3, 'Activation timed out.')),
                            driver_recovery_blocker=Mock(return_value=''), recovery_unit_loaded=lambda unit: True,
                            run=restart), patch.object(sys, 'argv', ['network-troubleshooter', '--device', 'wld0',
                                                                     '--repair', '--yes', '--redacted-report']):
                with redirect_stderr(stderr), redirect_stdout(stdout):
                    self.assertEqual(app['main'](), 1)
            self.assertIn('After repair\nafter snapshot', report())
            self.assertIn('Before repair\noffline snapshot', report())
            self.assertNotIn('In progress', report())
        self.assertIn('Internet — Unverified', stdout.getvalue())
        self.assertIn('did not pass the internet check', stderr.getvalue())

    def test_cli_repairs_usb_ethernet_with_no_carrier_or_profile(self):
        device = 'renamed-eth0'
        offline = ('Ethernet link is down', {'Link': ('No cable link', 'Wake the USB adapter.')}, '', '')
        online = ('Internet access verified', {'Link': ('Up', ''), 'Sign-in': ('Not detected', ''),
                                              'Internet': ('Reached', '')}, 'profile', '')
        run = Mock(return_value=(0, 'Ethernet link detected after waking.'))
        reconnect = Mock()
        with tempfile.TemporaryDirectory() as temp, patch.dict(
                env, STATE_DIR=Path(temp), recovery_settings=lambda: None,
                adapters=lambda: ([(device, 'Ethernet', 'unavailable')], ''),
                usb_wake_available=lambda name: name == device, run=run,
                active_profile=Mock(return_value=('100', 'profile')),
                diagnose=Mock(side_effect=(offline, online)), report_text=lambda *args: 'Test snapshot',
                reconnect_profile=reconnect), patch.object(
                    sys, 'argv', ['network-troubleshooter', '--device', device, '--repair', '--yes']):
            with redirect_stderr(StringIO()), redirect_stdout(StringIO()) as stdout:
                self.assertEqual(app['main'](), 0)
            self.assertIn('Internet — Reached', stdout.getvalue())
            report = next(Path(temp).glob('network-*.txt')).read_text()
            self.assertIn('Wake USB Ethernet', report)
            self.assertIn('NetworkManager activated the wired connection', report)
        run.assert_called_once_with('/usr/bin/pkexec', '--disable-internal-agent',
                                    env['USB_WAKE_HELPER'], device, timeout=None)
        reconnect.assert_not_called()

    def test_other_ethernet_with_no_carrier_never_prompts_for_authentication(self):
        result = ('Ethernet link is down', {'Link': ('No cable link', 'Check the cable.')}, '', '')
        repair = Mock()
        with tempfile.TemporaryDirectory() as temp, patch.dict(
                env, STATE_DIR=Path(temp), recovery_settings=lambda: None,
                adapters=lambda: ([('eth0', 'Ethernet', 'unavailable')], ''),
                usb_wake_available=lambda name: False, repair_connection=repair,
                diagnose=lambda *args, **kwargs: result, report_text=lambda *args: 'Test snapshot'), patch.object(
                    sys, 'argv', ['network-troubleshooter', '--repair', '--yes']):
            with redirect_stderr(StringIO()) as stderr, redirect_stdout(StringIO()):
                self.assertEqual(app['main'](), 1)
            self.assertIn('Check the cable.', stderr.getvalue())
        repair.assert_not_called()

    def test_configured_portal_helper_gets_the_selected_adapter(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp)
            (config / 'portal.json').write_text('{"wifi":["/usr/bin/helper","--open-device"]}')
            run = Mock(return_value=(0, ''))
            with patch.dict(env, CONFIG_DIR=config, run=run):
                app['launch_portal']('wlan1', 'Wi-Fi', 'http://probe.example/')
            run.assert_called_once_with('/usr/bin/helper', '--open-device', 'wlan1',
                                        'http://probe.example/', timeout=15)


class USBWakeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.net = Path(directory.name) / 'net'
        self.adapter = self.net / 'eth0'
        self.adapter.mkdir(parents=True)
        (self.adapter / 'type').write_text('1\n')
        (self.adapter / 'uevent').write_text('INTERFACE=eth0\n')
        self.carrier = self.adapter / 'carrier'
        self.carrier.write_text('0\n')
        self.usb = Path(directory.name) / 'adapter'
        self.interface = self.usb / 'interface'
        self.interface.mkdir(parents=True)
        usb_bus = Path(directory.name) / 'usb'
        usb_bus.mkdir()
        (self.interface / 'subsystem').symlink_to(usb_bus)
        (self.interface / 'uevent').write_text('DEVTYPE=usb_interface\nDRIVER=cdc_ether\n')
        (self.adapter / 'device').symlink_to(self.interface)
        (self.usb / 'power').mkdir()
        (self.usb / 'power/control').write_text('auto\n')
        (self.usb / 'power/runtime_status').write_text('suspended\n')
        net = patch.dict(wake.__globals__, NET=self.net, USB=usb_bus)
        net.start()
        self.addCleanup(net.stop)

    def test_read_only_check_matches_usb_ethernet_without_a_vendor_id_or_specific_driver(self):
        self.assertIn('USB wake is available', wake('eth0', check=True))
        (self.interface / 'uevent').write_text('DEVTYPE=usb_interface\nDRIVER=r8152\n')
        self.assertIn('USB wake is available', wake('eth0', check=True))
        self.assertEqual((self.usb / 'power/control').read_text(), 'auto\n')

    def test_rejects_usb_wifi_and_non_usb_ethernet(self):
        (self.adapter / 'uevent').write_text('DEVTYPE=wlan\nINTERFACE=eth0\n')
        with self.assertRaisesRegex(ValueError, 'not Ethernet'):
            wake('eth0', check=True)
        (self.adapter / 'uevent').write_text('INTERFACE=eth0\n')
        (self.interface / 'subsystem').unlink()
        (self.interface / 'subsystem').symlink_to(self.interface)
        with self.assertRaisesRegex(ValueError, 'not connected over USB'):
            wake('eth0', check=True)

    def test_rechecks_carrier_and_suspend_state_after_authentication(self):
        with patch('os.geteuid', return_value=0):
            (self.usb / 'power/runtime_status').write_text('active\n')
            with self.assertRaisesRegex(ValueError, 'already awake'):
                wake('eth0', check=False)
            self.carrier.write_text('1\n')
            self.assertIn('already has a link', wake('eth0', check=False))
        self.assertEqual((self.usb / 'power/control').read_text(), 'auto\n')

    def test_restores_usb_policy_when_the_link_returns_or_times_out(self):
        for link_returns in (True, False):
            with self.subTest(link_returns=link_returns):
                control = Mock(wraps=StringIO('auto\n'))
                control.__enter__ = Mock(return_value=control)
                control.__exit__ = Mock(return_value=False)
                self.carrier.write_text('0\n')

                def open_attribute(name, *args, **kwargs):
                    if name == 'power/control':
                        return control
                    return open(name, *args, **kwargs)

                def wait(seconds):
                    if link_returns:
                        self.carrier.write_text('1\n')

                clock = Mock(monotonic=Mock(side_effect=[0, 0, 1 if link_returns else 13]), sleep=wait)
                with patch.dict(wake.__globals__, open=open_attribute, time=clock), patch('os.geteuid', return_value=0):
                    if link_returns:
                        self.assertIn('Ethernet link detected', wake('eth0', check=False))
                    else:
                        with self.assertRaisesRegex(ValueError, 'Still no Ethernet link'):
                            wake('eth0', check=False)
                self.assertEqual([call.args[0] for call in control.write.call_args_list], ['on\n', 'auto\n'])


if __name__ == '__main__':
    unittest.main()
