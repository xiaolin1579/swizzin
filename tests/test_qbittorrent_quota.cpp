// Regression tests for user quota selection; no privileged filesystem is needed.
#include "sources/patches/qbittorrent/swizzinquota.h"

#include <cassert>
#include <cerrno>
#include <iostream>

namespace
{
    dqblk reply {};
    int result = 0;
    int calls = 0;
}

extern "C" int quotactl(int command, const char *device, int id, caddr_t data) noexcept
{
    assert(command == QCMD(Q_GETQUOTA, USRQUOTA));
    assert(device && *device);
    assert(id == static_cast<int>(geteuid()));
    ++calls;
    if (result)
    {
        errno = result;
        return -1;
    }
    *reinterpret_cast<dqblk *>(data) = reply;
    return 0;
}

int main()
{
    using Swizzin::quotaAwareSpace;
    constexpr std::int64_t GiB = 1024LL * 1024 * 1024;
    constexpr std::uint64_t GiBBlocks = 1024 * 1024;
    auto space = quotaAwareSpace("/dev/test", 500 * GiB, 1000 * GiB);
    assert(!space.quota && space.available == 500 * GiB && space.used == 500 * GiB);

    reply.dqb_bhardlimit = 100 * GiBBlocks;
    reply.dqb_curspace = 30 * GiB;
    space = quotaAwareSpace("/dev/test", 500 * GiB, 1000 * GiB);
    assert(space.quota && space.total == 100 * GiB && space.used == 30 * GiB && space.available == 70 * GiB);
    // A full disk must never be reported as free just because quota remains.
    assert(quotaAwareSpace("/dev/test", 5 * GiB, 1000 * GiB).available == 5 * GiB);
    assert(quotaAwareSpace("/dev/test", 0, 1000 * GiB).available == 0);

    reply.dqb_bsoftlimit = 80 * GiBBlocks;
    assert(quotaAwareSpace("/dev/test", 500 * GiB, 1000 * GiB).total == 80 * GiB);
    reply.dqb_bhardlimit = 0;
    assert(quotaAwareSpace("/dev/test", 500 * GiB, 1000 * GiB).available == 50 * GiB);
    reply.dqb_bhardlimit = 60 * GiBBlocks;
    assert(quotaAwareSpace("/dev/test", 500 * GiB, 1000 * GiB).total == 60 * GiB);

    reply.dqb_curspace = 100 * GiB;
    assert(quotaAwareSpace("/dev/test", 500 * GiB, 1000 * GiB).available == 0);
    reply.dqb_bhardlimit = reply.dqb_bsoftlimit = 0;
    assert(!quotaAwareSpace("/dev/test", 500 * GiB, 1000 * GiB).quota);

    for (int error : {ESRCH, ENOSYS, EOPNOTSUPP, EPERM, ENOENT})
    {
        result = error;
        space = quotaAwareSpace("/dev/test", 500 * GiB, 1000 * GiB);
        assert(!space.quota && space.available == 500 * GiB);
    }
    result = 0;
    reply.dqb_bhardlimit = std::numeric_limits<std::uint64_t>::max();
    reply.dqb_curspace = 1;
    space = quotaAwareSpace("/dev/test", 500 * GiB, 1000 * GiB);
    assert(space.quota && space.available == 500 * GiB && space.total > 0);

    const int before = calls;
    assert(quotaAwareSpace(nullptr, 100, 200).available == 100);
    assert(quotaAwareSpace("", 100, 200).available == 100);
    assert(quotaAwareSpace("/dev/test", -1, -1).available == -1);
    assert(calls == before);
    std::cout << "PASS: quota selection, units, user identity, zero/unlimited/over-limit, disk cap, failures, overflow\n";
}
