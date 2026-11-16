// SPDX-License-Identifier: GPL-3.0-or-later
Ext.ns('Deluge.plugins');
Deluge.plugins.SwizzinQuota = Ext.extend(Deluge.Plugin, {
    name: 'SwizzinQuota',

    onEnable: function() {
        this.active = true;
        this.pending = false;
        this.storage = null;
        this.task = {run: this.refresh, interval: 2000, scope: this};
        Ext.TaskMgr.start(this.task);
        this.refresh();
    },

    onDisable: function() {
        this.active = false;
        if (this.task) Ext.TaskMgr.stop(this.task);
        if (this.statusbar && this.statusbar.update === this.wrapper)
            this.statusbar.update = this.originalUpdate;
        this.statusbar = null;
        this.storage = null;
    },

    refresh: function() {
        if (!this.active || this.pending || !deluge.client.swizzinquota ||
            !deluge.client.swizzinquota.get_storage || !deluge.statusbar) return;
        if (!this.statusbar) {
            this.statusbar = deluge.statusbar;
            this.originalUpdate = this.statusbar.update;
            var plugin = this;
            var originalUpdate = this.originalUpdate;
            this.wrapper = function() {
                originalUpdate.apply(this, arguments);
                if (plugin.active) plugin.render();
            };
            this.statusbar.update = this.wrapper;
        }
        this.pending = true;
        deluge.client.swizzinquota.get_storage({
            success: function(storage) {
                this.pending = false;
                if (!this.active) return;
                this.storage = storage;
                this.render();
            },
            failure: function() {
                this.pending = false;
                this.storage = null;
                if (this.active) this.render();
            },
            scope: this
        });
    },

    render: function() {
        var item = this.statusbar && this.statusbar.items.get('statusbar-freespace');
        var storage = this.storage;
        if (!item) return;
        if (!storage || storage.free < 0 || storage.total < 0) {
            item.setText('Space: unavailable');
            return;
        }
        var label = storage.mode === 'quota' ? 'Quota' : 'Disk';
        var size = Deluge.Formatters.size;
        item.setText(label + ': ' + size(storage.used, true) + ' / ' + size(storage.total, true)
            + ' | Free: ' + size(storage.free, true));
        item.setTooltip(storage.mode === 'quota'
            ? 'User quota on the download filesystem. Free space is capped by physical disk availability.'
            : 'Physical disk space on the download filesystem.');
    }
});
Deluge.registerPlugin('SwizzinQuota', Deluge.plugins.SwizzinQuota);
