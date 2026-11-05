"""Focused regressions for offline troubleshooting and repair."""
import fcntl
from pathlib import Path
import runpy
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
                    code, detail = app['repair_connection']('eth0', 'Ethernet', 'profile', None, Mock(), [])
                    other_code, _ = app['repair_connection']('eth1', 'Ethernet', 'profile', None, Mock(), [])
                self.assertEqual(code, 1)
                self.assertIn('already running', detail)
                self.assertEqual(other_code, 0)
                self.assertEqual(repair.call_args.args[0], 'eth1')
                repair.assert_called_once()

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
