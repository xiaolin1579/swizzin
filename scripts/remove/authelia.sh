#!/bin/bash
# Authelia remover for swizzin
# Licensed under GNU General Public License v3.0 GPL-3 (in short)

#shellcheck source=sources/functions/utils
. /etc/swizzin/sources/functions/utils
#shellcheck source=sources/functions/authelia
. /etc/swizzin/sources/functions/authelia

echo_progress_start "Disabling SSO on applications"
if [[ -d $SWIZ_AUTHELIA_STATE/enabled ]]; then
    for app in "$SWIZ_AUTHELIA_STATE/enabled"/*; do
        [[ -e $app ]] || continue
        authelia_disable_app "$(basename "$app")"
    done
fi
echo_progress_done "SSO disabled on applications"

echo_progress_start "Stopping Authelia"
systemctl disable --now -q "$SWIZ_AUTHELIA_SERVICE" >> "$log" 2>&1 || echo_log_only "Could not disable ${SWIZ_AUTHELIA_SERVICE} service"
echo_progress_done "Authelia stopped"

echo_progress_start "Removing nginx configuration"
# Restore the original files backed up by scripts/nginx/authelia.sh, if any.
backup_dir="$SWIZ_AUTHELIA_STATE/nginx-backup"
for name in authelia.conf authelia-location.conf authelia-authrequest.conf; do
    case $name in
        authelia.conf) target="$SWIZ_AUTHELIA_NGINX_APPS/$name" ;;
        *) target="$SWIZ_AUTHELIA_NGINX_SNIPPETS/$name" ;;
    esac
    if [[ -f $backup_dir/$name ]]; then
        cp -a "$backup_dir/$name" "$target"
    else
        rm -f "$target"
    fi
done
if [[ -f /install/.nginx.lock ]] && nginx -t >> "$log" 2>&1; then
    systemctl reload nginx >> "$log" 2>&1
fi
echo_progress_done "nginx configuration removed"

echo_progress_start "Removing Authelia package"
apt_remove --purge authelia
rm -f /etc/apt/sources.list.d/authelia.list
rm -f /usr/share/keyrings/authelia-security.gpg
echo_progress_done "Authelia package removed"

rm -rf "$SWIZ_AUTHELIA_STORAGE"
rm -rf "$SWIZ_AUTHELIA_STATE"
rm -f /install/.authelia.lock

echo_success "Authelia removed"
echo_warn "TOTP/WebAuthn enrolments and Authelia sessions have been deleted"
