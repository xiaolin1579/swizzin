#!/bin/bash
# Enable quota-aware WebUI display without rebuilding an installed Deluge 2.x.
if [[ $EUID -ne 0 ]]; then
    echo "Run this command as root."
    exit 1
fi
if [[ ! -f /install/.deluge.lock ]]; then
    echo "Deluge is not installed."
    exit 1
fi
#shellcheck source=sources/globals.sh
. /etc/swizzin/sources/globals.sh
#shellcheck source=sources/functions/deluge
. /etc/swizzin/sources/functions/deluge
users=($(_get_user_list))
deluge_quota_plugin || exit 1
echo_success "Deluge disk quota display enabled. Refresh the WebUI."
