"""Regression checks for zero-space formatting and statusbar lifecycle."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'sources/plugins/deluge_quota/swizzinquota/data/quota.js'


@unittest.skipUnless(shutil.which('node'), 'Node is needed for WebUI checks')
class WebUITests(unittest.TestCase):
    def test_zero_quota_rpc_failure_and_plugin_disable(self):
        program = r'''
const vm = require('vm');
const assert = require('assert');
const item = {setText(text){this.text=text;},setTooltip(text){this.tooltip=text;}};
let reply = {mode:'quota',used:30,total:40,free:0};
let fail = false;
let stopped = 0;
const originalUpdate = function(){item.text='Original disk display';};
const bar = {update:originalUpdate,items:{get:()=>item}};
let Plugin;
const context = vm.createContext({
  Ext:{ns(){},extend(base,definition){return definition;},TaskMgr:{start(){},stop(){stopped++;}}},
  Deluge:{plugins:{},Plugin:function(){},registerPlugin(name,p){Plugin=p;},
    Formatters:{size(value,showZero){return !value&&!showZero?'':String(value);}}},
  deluge:{statusbar:bar,client:{swizzinquota:{get_storage(options){
    if(fail)options.failure.call(options.scope);else options.success.call(options.scope,reply);
  }}}}
});
vm.runInContext(SOURCE,context);
const plugin=Object.create(Plugin);
plugin.onEnable();
assert.strictEqual(item.text,'Quota: 30 / 40 | Free: 0');
bar.update({free_space:900});
assert.strictEqual(item.text,'Quota: 30 / 40 | Free: 0');
reply={mode:'disk',used:100,total:1000,free:900};plugin.refresh();
assert.strictEqual(item.text,'Disk: 100 / 1000 | Free: 900');
fail=true;plugin.refresh();
assert.strictEqual(item.text,'Space: unavailable');
bar.update({free_space:900});
assert.strictEqual(item.text,'Space: unavailable');
plugin.onDisable();
assert.strictEqual(bar.update,originalUpdate);
assert.strictEqual(stopped,1);
bar.update({free_space:900});
assert.strictEqual(item.text,'Original disk display');
// Preserve another plugin's wrapper without making re-enable recursive.
fail=false;
plugin.onEnable();
const firstWrapper=bar.update;
bar.update=function(){firstWrapper.apply(this,arguments);};
plugin.onDisable();
plugin.onEnable();
bar.update({free_space:900});
assert.strictEqual(item.text,'Disk: 100 / 1000 | Free: 900');
plugin.onDisable();
'''.replace('SOURCE', json.dumps(SCRIPT.read_text()))
        result = subprocess.run(['node', '-e', program], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
