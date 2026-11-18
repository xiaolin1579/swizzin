#!/usr/bin/env bash
#shellcheck source=sources/functions/tests
. /etc/swizzin/sources/functions/tests
#shellcheck source=sources/functions/authelia
. /etc/swizzin/sources/functions/authelia

check_service "authelia" || BAD="true"
check_port "9091" || BAD="true"

if [[ -f /install/.nginx.lock ]]; then
    check_nginx "authelia" || BAD="true"
fi

echo_log_only "Validating Authelia configuration"
authelia_validate_config "$SWIZ_AUTHELIA_CONFIG" >> "$log" 2>&1 || {
    echo_warn "Authelia configuration is invalid"
    BAD="true"
}

evaluate_bad "authelia"
