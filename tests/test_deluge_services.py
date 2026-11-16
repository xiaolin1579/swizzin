"""Regression checks for Deluge service commands without a systemd host.

Run with: python3 -m unittest discover -s tests -p 'test_deluge_services.py'
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'sources/functions/deluge'


class DelugeServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.units = self.root / 'units'
        self.units.mkdir()
        self.source = self.root / 'deluge.sh'
        self.source.write_text(SOURCE.read_text().replace('/etc/systemd/system', str(self.units)))

    def binaries(self, prefix, version='2.1.1'):
        directory = self.root / prefix / 'bin'
        directory.mkdir(parents=True, exist_ok=True)
        for name in ('deluged', 'deluge-web'):
            executable = directory / name
            executable.write_text(f'#!/bin/sh\necho "{name} {version}"\n')
            executable.chmod(0o755)
        return directory

    def configure(self, directory, command='_configure_deluge_services'):
        return subprocess.run(
            ['/bin/bash', '-c', '''
source "$1"
echo_error() { echo "$*" >&2; }
systemctl() { [[ $* == daemon-reload ]]; }
users=()
DELUGE_VERSION=repo
log="$2"
''' + command, 'test', str(self.source), str(self.root / 'test.log')],
            env={**os.environ, 'PATH': str(directory) + ':/usr/bin:/bin'},
            capture_output=True, text=True,
        )

    def assert_commands(self, directory, web_args=' -d'):
        daemon = (self.units / 'deluged@.service').read_text()
        web = (self.units / 'deluge-web@.service').read_text()
        self.assertIn(f'ExecStart={directory}/deluged -d\n', daemon)
        self.assertIn(f'ExecStart={directory}/deluge-web{web_args}\n', web)

    def test_source_install_uses_local_prefix(self):
        directory = self.binaries('usr/local')
        result = self.configure(directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_commands(directory)

    def test_repo_upgrade_updates_both_existing_templates(self):
        local = self.binaries('usr/local')
        self.assertEqual(self.configure(local).returncode, 0)
        unit = self.units / 'deluged@.service'
        unit.write_text(unit.read_text() + '\n# custom setting\n')
        repo = self.binaries('usr')
        result = self.configure(repo, 'dweb_check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_commands(repo)
        self.assertIn('# custom setting', unit.read_text())

    def test_legacy_webui_does_not_use_foreground_flag(self):
        directory = self.binaries('usr/local', '1.3.15')
        result = self.configure(directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_commands(directory, '')

    def test_missing_webui_preserves_existing_templates(self):
        directory = self.binaries('usr/local')
        self.assertEqual(self.configure(directory).returncode, 0)
        before = {p: p.read_text() for p in self.units.iterdir()}
        (directory / 'deluge-web').unlink()
        result = self.configure(directory)
        self.assertNotEqual(result.returncode, 0)
        for path, contents in before.items():
            self.assertEqual(path.read_text(), contents)

    def test_invalid_version_does_not_create_templates(self):
        directory = self.binaries('usr/local', 'unknown')
        result = self.configure(directory)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.units.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
