#!/bin/bash
# Authelia nginx configuration
# Licensed under GNU General Public License v3.0 GPL-3 (in short)
#
# This script creates the portal reverse proxy, the internal authz endpoint and
# the snippet that `box sso enable <app>` includes in application locations.

if [[ ! -f /install/.nginx.lock ]]; then
    echo_error "nginx does not appear to be installed, Authelia requires nginx"
    exit 1
fi

#shellcheck source=sources/functions/authelia
. /etc/swizzin/sources/functions/authelia

# Keep the backup outside of the temporary directory so the remover can restore
# any pre-existing configuration when Authelia is uninstalled.
backup_dir="$SWIZ_AUTHELIA_STATE/nginx-backup"
rm -rf "$backup_dir"
mkdir -p "$backup_dir"
for file in \
    "$SWIZ_AUTHELIA_NGINX_APPS/authelia.conf" \
    "$SWIZ_AUTHELIA_NGINX_SNIPPETS/authelia-location.conf" \
    "$SWIZ_AUTHELIA_NGINX_SNIPPETS/authelia-authrequest.conf"; do
    if [[ -f $file ]]; then
        cp -a "$file" "$backup_dir/$(basename "$file")"
    fi
done

restore_backup() {
    for file in \
        "$SWIZ_AUTHELIA_NGINX_APPS/authelia.conf" \
        "$SWIZ_AUTHELIA_NGINX_SNIPPETS/authelia-location.conf" \
        "$SWIZ_AUTHELIA_NGINX_SNIPPETS/authelia-authrequest.conf"; do
        if [[ -f $backup_dir/$(basename "$file") ]]; then
            cp -a "$backup_dir/$(basename "$file")" "$file"
        else
            rm -f "$file"
        fi
    done
    rm -rf "$backup_dir"
}

echo_progress_start "Writing Authelia nginx configuration"

mkdir -p "$SWIZ_AUTHELIA_NGINX_APPS" "$SWIZ_AUTHELIA_NGINX_SNIPPETS"

cat > "$SWIZ_AUTHELIA_NGINX_SNIPPETS/authelia-location.conf" << 'EOF'
# Managed by swizzin: internal endpoint used by auth_request
location /internal/authelia/authz {
    internal;
    proxy_pass http://127.0.0.1:9091/api/authz/auth-request;

    proxy_set_header X-Original-Method $request_method;
    proxy_set_header X-Original-URL $scheme://$host$request_uri;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header Content-Length "";
    proxy_set_header Connection "";

    proxy_pass_request_body off;
    proxy_next_upstream error timeout invalid_header http_500 http_502 http_503;
    proxy_redirect http:// $scheme://;
    proxy_http_version 1.1;
    proxy_cache_bypass $cookie_session;
    proxy_no_cache $cookie_session;
    proxy_buffers 4 32k;
    client_body_buffer_size 128k;

    send_timeout 5m;
    proxy_read_timeout 240;
    proxy_send_timeout 240;
    proxy_connect_timeout 240;
}
EOF

cat > "$SWIZ_AUTHELIA_NGINX_SNIPPETS/authelia-authrequest.conf" << 'EOF'
# Managed by swizzin: require an Authelia session for this location
auth_request /internal/authelia/authz;

auth_request_set $authelia_user $upstream_http_remote_user;
auth_request_set $authelia_groups $upstream_http_remote_groups;
auth_request_set $authelia_name $upstream_http_remote_name;
auth_request_set $authelia_email $upstream_http_remote_email;
auth_request_set $authelia_redirect $upstream_http_location;

proxy_set_header Remote-User $authelia_user;
proxy_set_header Remote-Groups $authelia_groups;
proxy_set_header Remote-Name $authelia_name;
proxy_set_header Remote-Email $authelia_email;

error_page 401 =302 $authelia_redirect;
EOF

cat > "$SWIZ_AUTHELIA_NGINX_APPS/authelia.conf" << 'EOF'
# Managed by swizzin: Authelia portal and authz endpoint
location /authelia {
    proxy_pass http://127.0.0.1:9091;
    proxy_http_version 1.1;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-URI $request_uri;
    proxy_set_header X-Original-URL $scheme://$host$request_uri;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "";

    proxy_buffering off;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    client_max_body_size 10m;
}

include /etc/nginx/snippets/authelia-location.conf;
EOF

if ! nginx -t >> "$log" 2>&1; then
    restore_backup
    echo_error "nginx configuration test failed after installing Authelia"
    nginx -t
    exit 1
fi

systemctl reload nginx >> "$log" 2>&1
echo_progress_done "Authelia nginx configuration installed"
