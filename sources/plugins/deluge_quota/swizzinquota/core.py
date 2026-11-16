# SPDX-License-Identifier: GPL-3.0-or-later
from deluge import component
from deluge.core.rpcserver import export
from deluge.plugins.pluginbase import CorePluginBase

from .storage import storage_info


class Core(CorePluginBase):
    def enable(self):
        pass

    def disable(self):
        pass

    @export
    def get_storage(self):
        # No path/UID RPC parameters: always read this daemon user's download filesystem.
        return storage_info(component.get('Core').config['download_location'])
