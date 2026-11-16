// SPDX-License-Identifier: GPL-3.0-or-later
// Linux user quota accounting for the filesystem containing the save path.
#pragma once

#include <algorithm>
#include <cstdint>
#include <limits>

#if defined(__linux__)
#include <sys/quota.h>
#include <unistd.h>
#endif

namespace Swizzin
{
struct StorageSpace
{
    std::int64_t available = -1;
    std::int64_t used = -1;
    std::int64_t total = -1;
    bool quota = false;
};

inline StorageSpace quotaAwareSpace(const char *device, const std::int64_t diskAvailable,
    const std::int64_t diskTotal)
{
    StorageSpace result {diskAvailable, (diskTotal >= 0 && diskAvailable >= 0) ? diskTotal - diskAvailable : -1,
        diskTotal, false};
#if defined(__linux__)
    if ((diskAvailable < 0) || !device || !*device)
        return result;

    struct dqblk quota {};
    // Query only the effective user's quota. No root helper or sudo is needed.
    if (::quotactl(QCMD(Q_GETQUOTA, USRQUOTA), device, static_cast<int>(::geteuid()),
            reinterpret_cast<caddr_t>(&quota)) != 0)
        return result;

    // A zero limit means unlimited. Respect whichever configured limit is lower.
    std::uint64_t limit = quota.dqb_bhardlimit;
    if (quota.dqb_bsoftlimit && (!limit || (quota.dqb_bsoftlimit < limit)))
        limit = quota.dqb_bsoftlimit;
    if (!limit)
        return result;

    // Linux reports block limits in KiB and current usage in bytes.
    constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
    const std::uint64_t limitBytes = (limit > (maximum / 1024)) ? maximum : (limit * 1024);
    const std::uint64_t remaining = (quota.dqb_curspace >= limitBytes) ? 0 : (limitBytes - quota.dqb_curspace);
    constexpr auto signedMaximum = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    result.available = static_cast<std::int64_t>(std::min(remaining, static_cast<std::uint64_t>(diskAvailable)));
    result.used = static_cast<std::int64_t>(std::min(static_cast<std::uint64_t>(quota.dqb_curspace), signedMaximum));
    result.total = static_cast<std::int64_t>(std::min(limitBytes, signedMaximum));
    result.quota = true;
    return result;
#else
    return result;
#endif
}
}
