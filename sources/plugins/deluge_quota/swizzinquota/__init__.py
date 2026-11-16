# SPDX-License-Identifier: GPL-3.0-or-later
from deluge.plugins.init import PluginInitBase


class CorePlugin(PluginInitBase):
    def __init__(self, plugin_name):
        from .core import Core
        self._plugin_cls = Core
        super().__init__(plugin_name)


class WebUIPlugin(PluginInitBase):
    def __init__(self, plugin_name):
        from .webui import WebUI
        self._plugin_cls = WebUI
        super().__init__(plugin_name)
