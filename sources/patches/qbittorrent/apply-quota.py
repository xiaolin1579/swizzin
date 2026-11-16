#!/usr/bin/env python3
"""Add user-quota storage reporting to qBittorrent 4.1–5.3 source trees.

Validate all upstream edit points before writing any file. Unknown layouts fail
closed instead of producing a partially patched build.
"""
import re
import sys
from pathlib import Path


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unexpected upstream edit point: ' + old)
    return text.replace(old, new, 1)


def apply(root):
    names = ['src/base/utils/fs.cpp', 'src/base/utils/fs.h',
             'src/webui/api/synccontroller.cpp', 'src/webui/www/private/scripts/client.js']
    originals = {name: (root / name).read_text() for name in names}
    if any('swizzin_storage' in text or 'Swizzin::StorageSpace' in text for text in originals.values()):
        raise ValueError('Source tree already contains a quota patch')
    updates = dict(originals)
    cpp, header, sync, client = names
    match = re.search(r'qint64 Utils::Fs::freeDiskSpaceOnPath\(const (QString|Path) &path\)\n\{.*?\n\}',
                      updates[cpp], re.S)
    if not match:
        raise ValueError('Unknown freeDiskSpaceOnPath implementation')
    path_type = match.group(1)
    path_value = 'usedPath.data()' if path_type == 'Path' else 'usedPath'
    parent = ('        usedPath = usedPath.parentPath();' if path_type == 'Path' else
              '''        const QString parent = QFileInfo(usedPath).absolutePath();
        if (parent == usedPath)
            break;
        usedPath = parent;''')
    replacement = '''qint64 Utils::Fs::freeDiskSpaceOnPath(const TYPE &path)
{
    return diskSpaceInfo(path).available;
}

Swizzin::StorageSpace Utils::Fs::diskSpaceInfo(const TYPE &path)
{
    TYPE usedPath = path;
    // A new save directory may not exist yet. Use its nearest existing ancestor.
    while (!usedPath.isEmpty())
    {
        const QStorageInfo storage(VALUE);
        if (storage.bytesAvailable() >= 0)
            return Swizzin::quotaAwareSpace(storage.device().constData(), storage.bytesAvailable(), storage.bytesTotal());
PARENT
    }
    return {};
}'''.replace('TYPE', path_type).replace('VALUE', path_value).replace('PARENT', parent)
    updates[cpp] = updates[cpp][:match.start()] + replacement + updates[cpp][match.end():]
    updates[header] = once(updates[header], '#include <QString>', '#include <QString>\n\n#include "swizzinquota.h"')
    declaration = 'qint64 freeDiskSpaceOnPath(const ' + path_type + ' &path);'
    updates[header] = once(updates[header], declaration, declaration + '\n    Swizzin::StorageSpace diskSpaceInfo(const ' + path_type + ' &path);')
    includes = '#include "base/utils/fs.h"\n'
    if path_type == 'Path':
        includes += '#include "base/path.h"\n'
    updates[sync] = once(updates[sync], '#include "synccontroller.h"', '#include "synccontroller.h"\n\n' + includes)
    session_header = (root / 'src/base/bittorrent/session.h').read_text()
    if re.search(r'\bsavePath\(\) const', session_header):
        save_path = 'savePath'
    elif re.search(r'\bdefaultSavePath\(\) const', session_header):
        save_path = 'defaultSavePath'
    else:
        raise ValueError('Unknown session save-path API')
    helper = '''namespace
{
    void updateSwizzinStorageSpace(QVariantMap &state)
    {
        const auto space = Utils::Fs::diskSpaceInfo(BitTorrent::Session::instance()->SAVE_PATH());
        state[QStringLiteral("free_space_on_disk")] = static_cast<qlonglong>(space.available);
        state[QStringLiteral("swizzin_storage")] = QVariantMap
        {
            {QStringLiteral("mode"), space.quota ? QStringLiteral("quota") : QStringLiteral("disk")},
            {QStringLiteral("used"), static_cast<qlonglong>(space.used)},
            {QStringLiteral("total"), static_cast<qlonglong>(space.total)},
            {QStringLiteral("free"), static_cast<qlonglong>(space.available)}
        };
    }
'''
    updates[sync] = once(updates[sync], 'namespace\n{', helper.replace('SAVE_PATH', save_path))
    updates[sync], count = re.subn(
        r'^(    )((?:m_maindataSnapshot\.)?serverState)\[KEY_TRANSFER_FREESPACEONDISK\] = [^\n]+;$',
        lambda m: m.group(0) + '\n    updateSwizzinStorageSpace(' + m.group(2) + ');', updates[sync], flags=re.M)
    if count == 0:
        # Early 4.1 releases predate the upstream free-space field entirely.
        marker = '    QVariantMap serverState = getTranserInfo();'
        updates[sync] = once(updates[sync], marker, marker + '\n    updateSwizzinStorageSpace(serverState);')
    elif count not in (1, 2):
        raise ValueError('Unknown sync free-space fields')
    lines = [line for line in updates[client].splitlines()
             if 'freeSpaceOnDisk' in line and 'serverState.free_space_on_disk' in line]
    if len(lines) > 1:
        raise ValueError('Unknown WebUI free-space display')
    if not lines:
        # Add a footer slot to releases that did not yet display disk space.
        anchors = [line for line in updates[client].splitlines() if "$('DHTNodes').set(" in line]
        if len(anchors) != 1:
            raise ValueError('Unknown WebUI footer')
        index = 'src/webui/www/private/index.html'
        html = (root / index).read_text()
        if 'id="freeSpaceOnDisk"' not in html:
            marker = '<td id="DHTNodes">'
            html = once(html, marker, '<td id="freeSpaceOnDisk"></td><td class="statusBarSeparator"></td>' + marker)
        updates[index] = html
        lines = anchors
        append_anchor = True
    else:
        append_anchor = False
    unit = 'window.qBittorrent.Misc.friendlyUnit' if 'window.qBittorrent.Misc.friendlyUnit' in updates[client] else 'friendlyUnit'
    updates[client], declarations = re.subn(
        r'((?:var|let|const) serverState = \{\};)',
        r'\1\n    var swizzinStorageCache = {};', updates[client])
    if declarations != 1:
        raise ValueError('Unknown WebUI server-state declaration')
    javascript = '''        // Older sync APIs send partial nested maps; keep unchanged quota fields.
        var swizzinDelta = serverState.swizzin_storage;
        if (swizzinDelta) {
            for (var swizzinKey in swizzinDelta) {
                if (Object.prototype.hasOwnProperty.call(swizzinDelta, swizzinKey))
                    swizzinStorageCache[swizzinKey] = swizzinDelta[swizzinKey];
            }
        }
        var swizzinStorage = swizzinStorageCache;
        var swizzinFreeSpace = document.getElementById("freeSpaceOnDisk");
        if (swizzinStorage && (swizzinStorage.free >= 0) && (swizzinStorage.total >= 0)) {
            var swizzinLabel = (swizzinStorage.mode === "quota") ? "Quota" : "Disk";
            swizzinFreeSpace.textContent = swizzinLabel + ": " + UNIT(swizzinStorage.used)
                + " / " + UNIT(swizzinStorage.total) + " | Free: " + UNIT(swizzinStorage.free);
            swizzinFreeSpace.title = (swizzinStorage.mode === "quota")
                ? "User quota on the default save filesystem. Free space is capped by physical disk availability."
                : "Physical disk space on the default save filesystem.";
        }
        else {
            swizzinFreeSpace.textContent = "QBT_TR(Free space: %1)QBT_TR[CONTEXT=HttpServer]"
                .replace("%1", UNIT(serverState.free_space_on_disk));
            swizzinFreeSpace.title = "";
        }'''.replace('UNIT', unit)
    updates[client] = once(updates[client], lines[0], javascript + ('\n' + lines[0] if append_anchor else ''))
    quota = Path(__file__).with_name('swizzinquota.h').read_text()
    for name, text in updates.items():
        (root / name).write_text(text)
    (root / 'src/base/utils/swizzinquota.h').write_text(quota)


if __name__ == '__main__':
    try:
        apply(Path(sys.argv[1] if len(sys.argv) > 1 else '.'))
    except (OSError, ValueError) as error:
        sys.exit('Could not apply qBittorrent quota support: ' + str(error))
    print('Enabled automatic user disk quota detection')
