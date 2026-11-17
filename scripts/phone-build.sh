#!/bin/sh
# Build packages natively on the phone with abuild (no pmbootstrap, no sudo
# on the host) and optionally install them there.
#
#   scripts/phone-build.sh [-i] PACKAGE...
#
# PACKAGE is a directory name under pmaports/device/testing or
# pmaports/temp. -i installs the built packages afterwards (a kernel
# package flashes the boot partition on installation; reboot to use it).
#
# Phone: CUPID_PHONE (user@address, from cupid.env). One-time setup there:
#   sudo apk add abuild alpine-sdk && sudo addgroup $USER abuild
#   abuild-keygen -a -n && sudo cp ~/.config/abuild/*.rsa.pub /etc/apk/keys/
# The phone fetches sources and makedepends itself: keep it on Wi-Fi.
set -e
. "$(dirname "$0")/env.sh"
PHONE="$CUPID_PHONE"
[ -n "$PHONE" ] || die "set CUPID_PHONE (user@address) in cupid.env"
install=
[ "$1" = "-i" ] && { install=1; shift; }
[ $# -gt 0 ] || { sed -n 2,14p "$0"; exit 2; }

for pkg in "$@"; do
	for d in "$REPO/pmaports/device/testing/$pkg" "$REPO/pmaports/temp/$pkg"; do
		[ -d "$d" ] && break
	done
	[ -d "$d" ] || { echo "no package directory for $pkg" >&2; exit 1; }
	echo "== $pkg"
	tar c -C "$(dirname "$d")" "$pkg" | ssh "$PHONE" \
		"mkdir -p ~/aports && cd ~/aports && rm -rf '$pkg' && tar x"
	# A system unit, not the SSH session: logind kills a session's
	# processes when it ends, so a dropped connection would end the build.
	# --wait still reports the result here.
	ssh "$PHONE" 'sudo systemd-run --quiet --wait --collect --unit="cupid-build-'"$pkg"'" \
		--uid="$(id -u)" --gid="$(id -g)" --setenv=HOME="$HOME" \
		--working-directory="$HOME/aports/'"$pkg"'" \
		nice sh -c "abuild -r > \"$HOME/build-'"$pkg"'.log\" 2>&1"' || {
		ssh "$PHONE" "tail -30 ~/build-'$pkg'.log"
		echo "$pkg failed, log: ~/build-$pkg.log on the phone" >&2
		exit 1
	}
	ssh "$PHONE" "grep -h '^>>> .*Create .*\.apk' ~/build-'$pkg'.log"
done

if [ -n "$install" ]; then
	# Every subpackage of the built packages that is installed now.
	ssh "$PHONE" 'cd ~/packages/aports/aarch64 && sudo apk add -u --repository ~/packages/aports $(for p in '"$*"'; do
		. ~/aports/$p/APKBUILD 2>/dev/null; for s in $pkgname $subpackages; do s=${s%%:*}; apk info -e $s >/dev/null && echo $s; done; done)'
fi
