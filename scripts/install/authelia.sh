#!/bin/bash
# Authelia installer for swizzin
# Licensed under GNU General Public License v3.0 GPL-3 (in short)
#
# Installs Authelia from the official APT repository and integrates it with
# nginx using auth_request. Users are generated from the existing swizzin user
# database so that `box adduser`/`deluser`/`chpasswd` keep working.
#
# Unattended variables:
#   AUTHELIA_DOMAIN  - external domain, defaults to LE_HOSTNAME and then to
#                      server_name in /etc/nginx/sites-enabled/default
#   AUTHELIA_POLICY  - one_factor or two_factor (default: two_factor)

if [[ $EUID -ne 0 ]]; then
    echo_error "Authelia installation requires root"
    exit 1
fi

if [[ ! -f /install/.nginx.lock ]]; then
    echo_warn "Authelia requires nginx for the swizzin integration"
    if ask "Install nginx first?" Y; then
        bash /usr/local/bin/swizzin/install/nginx.sh || exit 1
    else
        exit 1
    fi
fi

#shellcheck source=sources/functions/utils
. /etc/swizzin/sources/functions/utils
#shellcheck source=sources/functions/users
. /etc/swizzin/sources/functions/users
#shellcheck source=sources/functions/authelia
. /etc/swizzin/sources/functions/authelia

domain="${AUTHELIA_DOMAIN:-${LE_HOSTNAME:-}}"
if [[ -z $domain ]]; then
    domain=$(grep -h "server_name" /etc/nginx/sites-enabled/default 2> /dev/null |
        head -1 | awk '{print $2}' | tr -d ';')
fi
if [[ -z $domain || $domain == "_" ]]; then
    if [[ -t 0 ]]; then
        echo_query "Enter the domain name used to access this server (e.g. box.example.com)"
        read -r domain
    else
        echo_error "AUTHELIA_DOMAIN is required for unattended installs"
        exit 1
    fi
fi
domain=${domain#http://}
domain=${domain#https://}
domain=${domain%%/*}

if [[ ! $domain =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
    echo_error "Authelia requires a real domain name (not an IP address): ${domain}"
    echo_info "Configure Let's Encrypt or set AUTHELIA_DOMAIN to a hostname first"
    exit 1
fi

policy="${AUTHELIA_POLICY:-}"
if [[ -z $policy ]]; then
    if [[ -t 0 ]]; then
        if ask "Require two-factor authentication for SSO?" Y; then
            policy="two_factor"
        else
            policy="one_factor"
        fi
    else
        policy="two_factor"
    fi
fi
case "$policy" in
    one_factor | two_factor) ;;
    *)
        echo_error "AUTHELIA_POLICY must be one_factor or two_factor"
        exit 1
        ;;
esac

echo_info "Authelia domain: ${domain}"
echo_info "Access policy:   ${policy}"

echo_progress_start "Adding the Authelia APT repository"
apt_install ca-certificates curl gnupg
if [[ ! -f /usr/share/keyrings/authelia-security.gpg ]]; then
    curl -fsSL https://www.authelia.com/keys/authelia-security.gpg \
        -o /usr/share/keyrings/authelia-security.gpg >> "$log" 2>&1 || {
        echo_error "Could not download the Authelia repository key"
        exit 1
    }
fi
chmod 0644 /usr/share/keyrings/authelia-security.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/authelia-security.gpg] https://apt.authelia.com stable main" \
    > /etc/apt/sources.list.d/authelia.list
apt_update
echo_progress_done "APT repository added"

echo_progress_start "Installing Authelia"
apt_install authelia
if ! check_installed authelia; then
    echo_error "Authelia package is not installed"
    exit 1
fi
echo_progress_done "Authelia installed"

echo_progress_start "Writing Authelia configuration"
mkdir -p "$SWIZ_AUTHELIA_STATE" "$SWIZ_AUTHELIA_STORAGE"
chown authelia:authelia "$SWIZ_AUTHELIA_STORAGE"
chmod 0750 "$SWIZ_AUTHELIA_STORAGE"
authelia_write_config "$domain" "$policy" || exit 1
authelia_sync_users || exit 1
echo_progress_done "Configuration written"

echo_progress_start "Starting Authelia"
systemctl enable -q --now "$SWIZ_AUTHELIA_SERVICE" >> "$log" 2>&1

healthy="false"
for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:9091/api/health > /dev/null 2>&1; then
        healthy="true"
        break
    fi
    sleep 1
done
if [[ $healthy != "true" ]]; then
    echo_error "Authelia did not become healthy"
    journalctl -u "$SWIZ_AUTHELIA_SERVICE" -n 30 --no-pager 2> /dev/null | tail -30
    exit 1
fi
echo_progress_done "Authelia is running"

echo_progress_start "Configuring nginx"
bash /etc/swizzin/scripts/nginx/authelia.sh || exit 1
echo_progress_done "nginx configured"

echo_success "Authelia installed"
echo_info "Portal: $(authelia_url)"
echo_info "Use \`box sso enable <app>\` to protect an installed application"
echo_info "Set up TOTP from the portal on your first login when using two_factor"
touch /install/.authelia.lock
