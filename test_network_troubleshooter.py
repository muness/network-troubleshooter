"""Focused regressions for offline troubleshooting and repair."""
from contextlib import redirect_stderr, redirect_stdout
import fcntl
from io import StringIO
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

app = runpy.run_path(str(Path(__file__).with_name('network-troubleshooter')))
env = app['diagnose'].__globals__


class NetworkTests(unittest.TestCase):
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

    def test_configured_portal_helper_gets_the_selected_adapter(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp)
            (config / 'portal.json').write_text('{"wifi":["/usr/bin/helper","--open-device"]}')
            run = Mock(return_value=(0, ''))
            with patch.dict(env, CONFIG_DIR=config, run=run):
                app['launch_portal']('wlan1', 'Wi-Fi', 'http://probe.example/')
            run.assert_called_once_with('/usr/bin/helper', '--open-device', 'wlan1',
                                        'http://probe.example/', timeout=15)


if __name__ == '__main__':
    unittest.main()
