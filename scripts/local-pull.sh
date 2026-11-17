#!/bin/sh
# Fill the private overlay local/rootfs/ for scripts/inject-local.sh.
#
#   scripts/local-pull.sh [HOST]   user@address, default $CUPID_PHONE (cupid.env)
#
# Copies from a running phone (needs sudo there):
#   - the NetworkManager connections (WiFi passwords included) as system
#     connections, so WiFi comes up at boot without a login;
#   - the SSH host keys, so a reflash keeps the host key known_hosts has;
# and writes a passwordless sudo rule for the image's user.
#
# local/ is gitignored and holds secrets: never commit or publish it.
set -e
. "$(dirname "$0")/env.sh"

host="${1:-$CUPID_PHONE}"
[ -n "$host" ] || die "usage: $0 user@phone"
user="$(pmb config user 2>/dev/null || true)"
[ -n "$user" ] || user="${host%@*}"

overlay="$REPO/local/rootfs"
umask 077
mkdir -p "$overlay/etc/NetworkManager/system-connections" \
	"$overlay/etc/ssh" "$overlay/etc/sudoers.d"

echo "==> NetworkManager connections"
for f in $(ssh "$host" 'sudo find /etc/NetworkManager/system-connections -name "*.nmconnection" -type f'); do
	ssh "$host" "sudo cat '$f'" > "$overlay$f"
	chmod 600 "$overlay$f"
	echo "    $f"
done

echo "==> SSH host keys"
for f in $(ssh "$host" 'ls /etc/ssh/ssh_host_*_key'); do
	ssh "$host" "sudo cat '$f'" > "$overlay$f"
	chmod 600 "$overlay$f"
	ssh "$host" "cat '$f.pub'" > "$overlay$f.pub"
	chmod 644 "$overlay$f.pub"
	echo "    $f"
done

echo "==> passwordless sudo for $user"
echo "$user ALL=(ALL) NOPASSWD: ALL" > "$overlay/etc/sudoers.d/90-$user-nopasswd"
chmod 440 "$overlay/etc/sudoers.d/90-$user-nopasswd"

echo
echo "local overlay in $overlay, injected by scripts/build.sh"
echo "(or scripts/inject-local.sh for an existing image). Keep it private."
