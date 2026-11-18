#!/bin/bash
# Re-apply Authelia SSO snippets after a swizzin update.
# This runs last (99-) so that app update scripts which regenerate their nginx
# configuration cannot silently drop the auth_request include.

if [[ ! -f /install/.authelia.lock ]]; then
    exit 0
fi

#shellcheck source=sources/functions/authelia
. /etc/swizzin/sources/functions/authelia

authelia_reapply
authelia_reload_nginx || echo_warn "Could not reload nginx after re-applying Authelia SSO"

exit 0
