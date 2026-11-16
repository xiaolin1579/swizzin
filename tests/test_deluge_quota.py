"""Quota calculation and mount selection without requiring a quota-enabled mount."""
import ctypes
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, mock_open, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('quota_storage', ROOT / 'sources/plugins/deluge_quota/swizzinquota/storage.py')
STORAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STORAGE)
MiB = 1024 * 1024


class QuotaTests(unittest.TestCase):
    def test_mount_device_matches_device_and_deepest_component(self):
        mounts = [
            '1 0 8:1 / / rw - ext4 /dev/root rw',
            '2 1 8:1 / /home/tester rw - ext4 /dev/user rw',
            '3 1 8:2 / /home/tester/downloads rw - ext4 /dev/wrong rw',
            '4 1 8:1 / /home/tester2 rw - ext4 /dev/other-user rw',
            r'5 1 8:1 / /home/tester/download\040space rw - ext4 /dev/space rw',
        ]
        self.assertEqual(STORAGE.mount_device('/home/tester/downloads', os.makedev(8, 1), mounts), '/dev/user')
        self.assertEqual(STORAGE.mount_device('/home/tester/download space/file', os.makedev(8, 1), mounts), '/dev/space')
        self.assertEqual(STORAGE.mount_device('/elsewhere', os.makedev(8, 1), mounts), '/dev/root')
        self.assertIsNone(STORAGE.mount_device('/elsewhere', os.makedev(9, 9), mounts))

    def quota_query(self, soft, hard, used, failure=False):
        def query(command, device, uid, pointer):
            self.assertEqual(command, 0x80000700)
            self.assertEqual(device, b'/dev/test')
            self.assertEqual(uid, 12345)
            quota = pointer._obj
            quota.bsoftlimit, quota.bhardlimit, quota.curspace = soft, hard, used
            return -1 if failure else 0
        library = SimpleNamespace(quotactl=Mock(side_effect=query))
        with patch.object(STORAGE.ctypes, 'CDLL', return_value=library), patch.object(STORAGE.os, 'geteuid', return_value=12345):
            return STORAGE.user_quota('/dev/test')

    def test_quota_uses_current_uid_and_converts_kib_limits_to_bytes(self):
        self.assertEqual(ctypes.sizeof(STORAGE.Dqblk), 72)
        self.assertEqual(self.quota_query(100, 120, 500), (500, 100 * 1024))
        self.assertEqual(self.quota_query(0, 120, 500), (500, 120 * 1024))
        self.assertEqual(self.quota_query(100, 0, 500), (500, 100 * 1024))
        self.assertEqual(self.quota_query(120, 100, 500), (500, 100 * 1024))
        self.assertIsNone(self.quota_query(0, 0, 500))
        self.assertIsNone(self.quota_query(100, 120, 500, failure=True))
        with patch.object(STORAGE.ctypes, 'CDLL', side_effect=OSError('unsupported')):
            self.assertIsNone(STORAGE.user_quota('/dev/test'))

    def info(self, quota, available=500):
        disk = SimpleNamespace(f_bavail=available, f_frsize=MiB, f_blocks=1000)
        with patch.object(STORAGE.os.path, 'realpath', return_value='/home/tester/downloads'), \
                patch.object(STORAGE.os.path, 'exists', return_value=True), \
                patch.object(STORAGE.os, 'statvfs', return_value=disk), \
                patch.object(STORAGE.os, 'stat', return_value=SimpleNamespace(st_dev=os.makedev(8, 1))), \
                patch('builtins.open', mock_open(read_data='1 0 8:1 / / rw - ext4 /dev/test rw')), \
                patch.object(STORAGE, 'user_quota', return_value=quota):
            return STORAGE.storage_info('/home/tester/downloads')

    def test_no_quota_falls_back_to_disk(self):
        self.assertEqual(self.info(None), {'mode': 'disk', 'used': 500 * MiB, 'total': 1000 * MiB, 'free': 500 * MiB})

    def test_finite_quota_over_limit_and_physical_disk_cap(self):
        self.assertEqual(self.info((30 * MiB, 100 * MiB)), {'mode': 'quota', 'used': 30 * MiB, 'total': 100 * MiB, 'free': 70 * MiB})
        self.assertEqual(self.info((120 * MiB, 100 * MiB))['free'], 0)
        self.assertEqual(self.info((30 * MiB, 100 * MiB), available=5)['free'], 5 * MiB)
        self.assertEqual(self.info((30 * MiB, 100 * MiB), available=0)['free'], 0)

    def test_unknown_path_does_not_report_false_free_space(self):
        self.assertEqual(STORAGE.storage_info('')['free'], -1)
        with patch.object(STORAGE.os, 'statvfs', side_effect=OSError('unreadable')):
            self.assertEqual(STORAGE.storage_info('/tmp')['free'], -1)


if __name__ == '__main__':
    unittest.main()
