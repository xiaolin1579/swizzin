"""Check source adaptation and fail-before-writing behavior of the quota patcher."""
import importlib.util
from pathlib import Path
import tempfile
import json
import shutil
import subprocess
import unittest

PACKAGE = Path(__file__).resolve().parents[1] / 'sources/patches/qbittorrent'
SPEC = importlib.util.spec_from_file_location('quota_patch', PACKAGE / 'apply-quota.py')
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)


class QuotaPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def source(self, path_type='Path', snapshots=True, legacy_js=False):
        files = {
            'src/base/utils/fs.cpp': 'qint64 Utils::Fs::freeDiskSpaceOnPath(const TYPE &path)\n{\n    return 0;\n}\n'.replace('TYPE', path_type),
            'src/base/utils/fs.h': '#include <QString>\n    qint64 freeDiskSpaceOnPath(const TYPE &path);\n'.replace('TYPE', path_type),
            'src/webui/api/synccontroller.cpp': '#include "synccontroller.h"\nnamespace\n{\n}\nvoid update()\n{\n    serverState[KEY_TRANSFER_FREESPACEONDISK] = getFreeDiskSpace();\n}\n',
            'src/webui/www/private/scripts/client.js': "        $('freeSpaceOnDisk').set('html', friendlyUnit(serverState.free_space_on_disk));\n" if legacy_js else '        document.getElementById("freeSpaceOnDisk").textContent = window.qBittorrent.Misc.friendlyUnit(serverState.free_space_on_disk);\n',
        }
        files['src/base/bittorrent/session.h'] = ('QString defaultSavePath() const;' if path_type == 'QString' else 'Path savePath() const;')
        if snapshots:
            files['src/webui/api/synccontroller.cpp'] += '    m_maindataSnapshot.serverState[KEY_TRANSFER_FREESPACEONDISK] = m_freeDiskSpace;\n'
        files['src/webui/www/private/scripts/client.js'] = 'const serverState = {};\n' + files['src/webui/www/private/scripts/client.js']
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return files

    def test_path_api_with_incremental_and_initial_snapshots(self):
        self.source()
        PATCH.apply(self.root)
        sync = (self.root / 'src/webui/api/synccontroller.cpp').read_text()
        self.assertIn('updateSwizzinStorageSpace(serverState);', sync)
        self.assertIn('updateSwizzinStorageSpace(m_maindataSnapshot.serverState);', sync)
        self.assertEqual((self.root / 'src/base/utils/swizzinquota.h').read_text(),
                         (PACKAGE / 'swizzinquota.h').read_text())

    def test_legacy_qstring_and_global_formatter(self):
        self.source('QString', snapshots=False, legacy_js=True)
        PATCH.apply(self.root)
        cpp = (self.root / 'src/base/utils/fs.cpp').read_text()
        self.assertIn('defaultSavePath()', (self.root / 'src/webui/api/synccontroller.cpp').read_text())
        self.assertIn('QFileInfo(usedPath).absolutePath()', cpp)
        self.assertIn('if (parent == usedPath)', cpp)
        client = (self.root / 'src/webui/www/private/scripts/client.js').read_text()
        self.assertIn('friendlyUnit(swizzinStorage.used)', client)
        self.assertNotIn('window.qBittorrent', client)

    def test_early_41_adds_missing_api_and_footer_slot(self):
        self.source('QString', snapshots=False, legacy_js=True)
        sync = self.root / 'src/webui/api/synccontroller.cpp'
        sync.write_text(sync.read_text().replace(
            '    serverState[KEY_TRANSFER_FREESPACEONDISK] = getFreeDiskSpace();',
            '    QVariantMap serverState = getTranserInfo();'))
        client = self.root / 'src/webui/www/private/scripts/client.js'
        client.write_text("var serverState = {};\n        $('DHTNodes').set('html', serverState.dht_nodes);\n")
        index = self.root / 'src/webui/www/private/index.html'
        index.write_text('<table><tr><td id="DHTNodes"></td></tr></table>')
        PATCH.apply(self.root)
        self.assertIn('updateSwizzinStorageSpace(serverState);', sync.read_text())
        self.assertIn('id="freeSpaceOnDisk"', index.read_text())
        self.assertIn("$('DHTNodes').set(", client.read_text())
        self.assertIn('swizzinStorage', client.read_text())

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the JavaScript delta test')
    def test_partial_sync_maps_preserve_unchanged_quota_fields(self):
        self.source()
        PATCH.apply(self.root)
        lines = (self.root / 'src/webui/www/private/scripts/client.js').read_text().splitlines()
        declarations = '\n'.join(lines[:2])
        renderer = '\n'.join(lines[2:])
        program = r'''
const vm = require('vm');
const assert = require('assert');
const element = {};
const context = vm.createContext({
    document: {getElementById: () => element},
    window: {qBittorrent: {Misc: {friendlyUnit: String}}}
});
vm.runInContext(DECLARATIONS + '\nfunction render() {\n' + RENDERER + '\n}', context);
vm.runInContext('serverState.swizzin_storage = {mode:"quota",used:30,total:40,free:10}; render();', context);
assert.strictEqual(element.textContent, 'Quota: 30 / 40 | Free: 10');
vm.runInContext('serverState.swizzin_storage = {free:0}; render();', context);
assert.strictEqual(element.textContent, 'Quota: 30 / 40 | Free: 0');
vm.runInContext('serverState.swizzin_storage = {mode:"disk",used:100,total:1000,free:900}; render();', context);
assert.strictEqual(element.textContent, 'Disk: 100 / 1000 | Free: 900');
'''.replace('DECLARATIONS', json.dumps(declarations)).replace('RENDERER', json.dumps(renderer))
        result = subprocess.run(['node', '-e', program], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_webui_does_not_partially_patch_sources(self):
        originals = self.source()
        name = 'src/webui/www/private/scripts/client.js'
        originals[name] = '// unknown upstream UI\n'
        (self.root / name).write_text(originals[name])
        with self.assertRaises(ValueError):
            PATCH.apply(self.root)
        for name, text in originals.items():
            self.assertEqual((self.root / name).read_text(), text)
        self.assertFalse((self.root / 'src/base/utils/swizzinquota.h').exists())

    def test_reapplication_is_rejected_without_modification(self):
        self.source()
        PATCH.apply(self.root)
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaises(ValueError):
            PATCH.apply(self.root)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
