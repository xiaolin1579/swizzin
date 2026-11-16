# SPDX-License-Identifier: GPL-3.0-or-later
from pkg_resources import resource_filename
from deluge.plugins.pluginbase import WebPluginBase


class WebUI(WebPluginBase):
    scripts = [resource_filename(__package__, 'data/quota.js')]
    debug_scripts = scripts
