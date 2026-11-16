"""PHP package and module compatibility across supported distributions."""
from pathlib import Path
import subprocess
import tempfile
import unittest

PHP = (Path(__file__).resolve().parents[1] / "sources/functions/php").read_text()


class PhpCompatibilityTests(unittest.TestCase):
    def run_shell(self, command, source=PHP):
        return subprocess.run(["bash", "-eu", "-c", source + "\n" + command],
                              capture_output=True, text=True, check=True).stdout

    def test_package_for_supported_releases(self):
        for codename in ("focal", "jammy", "noble", "bullseye", "bookworm", "resolute"):
            with self.subTest(codename=codename):
                output = self.run_shell('_os_codename() { echo ' + codename + '; }; php_opcache_package')
                self.assertEqual(output, "" if codename == "resolute" else "php-opcache")

    def test_separate_module_is_enabled_and_bundled_module_needs_no_phpenmod(self):
        with tempfile.TemporaryDirectory() as directory:
            module = Path(directory) / "8.3/mods-available/opcache.ini"
            module.parent.mkdir(parents=True)
            module.touch()
            source = PHP.replace("/etc/php/", directory + "/")
            output = self.run_shell(
                'phpenmod() { printf "%s\\n" "$*"; }; '
                'enable_php_opcache 8.3; enable_php_opcache 8.5', source)
            self.assertEqual(output, "-v 8.3 opcache\n")


if __name__ == "__main__":
    unittest.main()
