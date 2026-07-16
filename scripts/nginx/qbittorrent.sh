#!/bin/bash
# nginx setup for qbittorrent
#shellcheck source=sources/functions/utils
. /etc/swizzin/sources/functions/utils
users=($(_get_user_list))

if [[ ! -f /etc/nginx/apps/qbtindex.conf ]]; then
    cat > /etc/nginx/apps/qbtindex.conf << DIN
location /qbittorrent.downloads {
    alias /home/\$remote_user/torrents/qbittorrent;
    include /etc/nginx/snippets/fancyindex.conf;
    auth_basic "What's the password?";
    auth_basic_user_file /etc/htpasswd;

  location ~* \.php\$ {

  }
}
DIN
fi

if [[ ! -f /etc/nginx/apps/qbittorrent.conf ]]; then
    cat > /etc/nginx/apps/qbittorrent.conf << 'QBTN'
location /qbt {
    return 301 /qbittorrent/;
}

location /qbittorrent/ {
    proxy_pass              http://$remote_user.qbittorrent;
    proxy_http_version      1.1;
    proxy_set_header        X-Forwarded-Host        $http_host;
    http2_push_preload on;
    auth_basic "What's the password?";
    auth_basic_user_file /etc/htpasswd;

    # รองรับการ Rewrite สำหรับทุกเวอร์ชัน
    rewrite ^/qbittorrent/(.*) /$1 break;
    proxy_cookie_path / "/qbittorrent/; Secure";

    # การจัดการ CSRF สำหรับเวอร์ชัน 4.1.x ถึง 5.2.x
    # สำหรับเวอร์ชันใหม่ๆ (5.x) แนะนำให้ไปปิด "Enable Cross-site request forgery (CSRF) protection"
    # ในหน้า WebUI Options ของ qBittorrent แทนการใช้ proxy_hide_header
    proxy_set_header   Referer            "";
    proxy_set_header   Origin             "";
}
QBTN
fi

for user in ${users[@]}; do
    port=$(grep 'WebUI\\Port' /home/${user}/.config/qBittorrent/qBittorrent.conf | cut -d= -f2)
    cat > /etc/nginx/conf.d/${user}.qbittorrent.conf << QBTUC
upstream ${user}.qbittorrent {
  server 127.0.0.1:${port};
}
QBTUC
    if grep -q 'WebUI\\Address=\*' /home/${user}/.config/qBittorrent/qBittorrent.conf; then
        active=$(systemctl is-active qbittorrent@${user})
        if [[ $active == "active" ]]; then
            systemctl stop qbittorrent@${user} >> ${log} 2>&1
        fi
        sed -i 's|WebUI\\Address=.*|WebUI\\Address=127.0.0.1|g' /home/${user}/.config/qBittorrent/qBittorrent.conf
        if [[ $active == "active" ]]; then
            systemctl start qbittorrent@${user} >> ${log} 2>&1
        fi
    fi
done
