#!/bin/bash
# Authelia upgrade script for swizzin
# Licensed under GNU General Public License v3.0 GPL-3 (in short)

if [[ ! -f /install/.authelia.lock ]]; then
    echo_error "Authelia does not appear to be installed"
    exit 1
fi

#shellcheck source=sources/functions/authelia
. /etc/swizzin/sources/functions/authelia

echo_progress_start "Updating APT repositories"
apt_update
echo_progress_done "APT repositories updated"

echo_progress_start "Upgrading Authelia"
# apt_install skips already installed packages, so --only-upgrade is a no-op
# with that helper. Call apt-get directly to make `box upgrade authelia` work.
DEBIAN_FRONTEND=noninteractive apt-get install --only-upgrade -y authelia >> "$log" 2>&1 || {
    echo_error "Could not upgrade Authelia, see ${log}"
    exit 1
}
echo_progress_done "Authelia upgraded"

echo_progress_start "Validating configuration"
authelia_validate_config "$SWIZ_AUTHELIA_CONFIG" >> "$log" 2>&1 || {
    echo_error "The installed Authelia version rejected the current configuration"
    echo_info "Review ${SWIZ_AUTHELIA_CONFIG} before restarting Authelia"
    exit 1
}
echo_progress_done "Configuration valid"

echo_progress_start "Restarting Authelia"
systemctl restart "$SWIZ_AUTHELIA_SERVICE" >> "$log" 2>&1
healthy="false"
for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:9091/api/health > /dev/null 2>&1; then
        healthy="true"
        break
    fi
    sleep 1
done
if [[ $healthy != "true" ]]; then
    echo_error "Authelia did not become healthy after the upgrade"
    exit 1
fi
echo_progress_done "Authelia restarted"

authelia_reapply
authelia_reload_nginx

echo_success "Authelia upgraded"
