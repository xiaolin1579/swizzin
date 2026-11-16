# SPDX-License-Identifier: GPL-3.0-or-later
"""Read the effective user's Linux quota on the download filesystem."""
import ctypes
import os
import re


class Dqblk(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        'bhardlimit', 'bsoftlimit', 'curspace', 'ihardlimit', 'isoftlimit',
        'curinodes', 'btime', 'itime')] + [('valid', ctypes.c_uint32)]


def unescape_mount(value):
    return re.sub(r'\\([0-7]{3})', lambda match: chr(int(match.group(1), 8)), value)


def mount_device(path, device_id, lines):
    """Match the actual device and deepest mount, including bind mounts."""
    device_number = '{}:{}'.format(os.major(device_id), os.minor(device_id))
    selected, longest = None, -1
    for line in lines:
        before, separator, after = line.partition(' - ')
        fields, filesystem = before.split(), after.split()
        if not separator or len(fields) < 6 or len(filesystem) < 2 or fields[2] != device_number:
            continue
        mount = os.path.normpath(unescape_mount(fields[4]))
        if path != mount and not path.startswith(mount.rstrip('/') + '/'):
            continue
        if len(mount) > longest:
            selected, longest = unescape_mount(filesystem[1]), len(mount)
    return selected


def user_quota(device):
    if not device:
        return None
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        query = libc.quotactl
        query.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(Dqblk)]
        query.restype = ctypes.c_int
        quota = Dqblk()
        # QCMD(Q_GETQUOTA, USRQUOTA). Linux block limits are in KiB.
        if query(0x80000700, os.fsencode(device), os.geteuid(), ctypes.byref(quota)):
            return None
        limits = [limit for limit in (quota.bsoftlimit, quota.bhardlimit) if limit]
        return (quota.curspace, min(limits) * 1024) if limits else None
    except (AttributeError, OSError):
        return None


def storage_info(path):
    unknown = {'mode': 'disk', 'used': -1, 'total': -1, 'free': -1}
    if not path:
        return unknown
    try:
        path = os.path.realpath(os.path.expanduser(path))
        while not os.path.exists(path):
            parent = os.path.dirname(path)
            if parent == path:
                return unknown
            path = parent
        disk = os.statvfs(path)
        available = disk.f_bavail * disk.f_frsize
        total = disk.f_blocks * disk.f_frsize
        result = {'mode': 'disk', 'used': max(0, total - available), 'total': total, 'free': available}
        try:
            with open('/proc/self/mountinfo') as mounts:
                device = mount_device(path, os.stat(path).st_dev, mounts)
            quota = user_quota(device)
        except OSError:
            quota = None
        if quota:
            used, limit = quota
            maximum = (1 << 63) - 1
            result = {'mode': 'quota', 'used': min(used, maximum), 'total': min(limit, maximum),
                      'free': min(available, max(0, limit - used))}
        return result
    except OSError:
        return unknown
