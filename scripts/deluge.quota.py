#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the standard Deluge plugin egg or enable it in a stopped user's config."""
import argparse
from pathlib import Path
import zipfile


def build(destination):
    package = Path(__file__).resolve().parents[1] / 'sources/plugins/deluge_quota'
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as egg:
        for path in sorted((package / 'swizzinquota').rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                egg.write(path, str(path.relative_to(package)))
        egg.writestr('EGG-INFO/PKG-INFO', 'Metadata-Version: 1.2\nName: SwizzinQuota\nVersion: 1.0\nSummary: Automatic user disk quota for Deluge WebUI\n')
        egg.writestr('EGG-INFO/top_level.txt', 'swizzinquota\n')
        egg.writestr('EGG-INFO/entry_points.txt', '[deluge.plugin.core]\nSwizzinQuota = swizzinquota:CorePlugin\n\n[deluge.plugin.web]\nSwizzinQuota = swizzinquota:WebUIPlugin\n')
        egg.writestr('EGG-INFO/zip-safe', '')


def enable(directory):
    from deluge.config import Config
    directory = Path(directory)
    if not (directory / 'core.conf').is_file():
        raise RuntimeError('Deluge core.conf is missing')
    config = Config('core.conf', config_dir=str(directory))
    plugins = config.get('enabled_plugins')
    if not isinstance(plugins, list):
        raise RuntimeError('Deluge enabled_plugins is missing or invalid; configuration was not changed')
    if 'SwizzinQuota' not in plugins:
        config['enabled_plugins'] = plugins + ['SwizzinQuota']
        if not config.save():
            raise RuntimeError('Could not save Deluge plugin configuration')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--build', metavar='EGG')
    group.add_argument('--enable', metavar='CONFIG_DIRECTORY')
    args = parser.parse_args()
    if args.build:
        build(args.build)
    else:
        enable(args.enable)
