"""Verify service restoration and install ordering with shell command doubles."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'sources/functions/deluge'


class QuotaInstallTests(unittest.TestCase):
    def configure(self, active='yes', failure='no', version='2.1.1'):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'deluge.sh'
            source.write_text(SOURCE.read_text().replace('/etc/swizzin/scripts/deluge.quota.py', '/dev/null'))
            trace = Path(directory) / 'trace'
            result = subprocess.run(['/bin/bash', '-c', r'''
source "$1"
users=(alice)
log="$TRACE.log"
echo_info() { :; }; echo_error() { :; }; echo_progress_start() { :; }; echo_progress_done() { :; }
deluged() { echo "deluged $TEST_VERSION"; }
systemctl() {
    echo "$*" >> "$TRACE"
    if [[ $1 == is-active ]]; then [[ $TEST_ACTIVE == yes ]]; else return 0; fi
}
python3() { touch "$3"; }
install() { echo "install $1" >> "$TRACE"; }
runuser() { echo enable >> "$TRACE"; [[ $TEST_FAILURE != yes ]]; }
deluge_quota_plugin
''', 'test', str(source)], env={**os.environ, 'TRACE': str(trace), 'TEST_ACTIVE': active,
                    'TEST_FAILURE': failure, 'TEST_VERSION': version}, capture_output=True, text=True)
            calls = trace.read_text().splitlines() if trace.exists() else []
            return result, calls

    def test_active_services_stop_before_enable_and_restart_afterwards(self):
        result, calls = self.configure()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(calls.index('stop deluge-web@alice'), calls.index('stop deluged@alice'))
        self.assertLess(calls.index('stop deluged@alice'), calls.index('enable'))
        self.assertLess(calls.index('enable'), calls.index('start deluged@alice'))
        self.assertLess(calls.index('start deluged@alice'), calls.index('start deluge-web@alice'))

    def test_failure_still_restores_both_services(self):
        result, calls = self.configure(failure='yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('start deluged@alice', calls)
        self.assertIn('start deluge-web@alice', calls)

    def test_inactive_services_are_not_started(self):
        result, calls = self.configure(active='no')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('enable', calls)
        self.assertFalse(any(c.startswith(('start ', 'stop ')) for c in calls))

    def test_legacy_deluge_is_left_unchanged(self):
        result, calls = self.configure(version='1.3.15')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
