#!/bin/sh
# One-time setup: a private pmbootstrap config and work directory for cupid, a
# pmaports checkout with a "cupid" branch on top of main (edge), and the
# packages from this repository synced into it.
#
#   scripts/setup.sh            first time, or to re-sync
#   scripts/setup.sh --rebase   also rebase the cupid branch on current main
#
# Safe to run again. Does not touch ~/.config/pmbootstrap_v3.cfg or
# ~/.local/var/pmbootstrap.
set -e
. "$(dirname "$0")/env.sh"

need pmbootstrap git rsync python3

mkdir -p "$REPO/work" "$OUT"

# --- pmaports checkout -------------------------------------------------------
if [ ! -d "$PMAPORTS/.git" ]; then
	echo "==> cloning pmaports into $PMAPORTS"
	ref=""
	for cache in "$HOME/.local/var/pmbootstrap/cache_git/pmaports"; do
		[ -d "$cache/.git" ] && ref="--reference-if-able $cache"
	done
	# shellcheck disable=SC2086
	git clone $ref "$PMAPORTS_URL" "$PMAPORTS"
fi

echo "==> updating pmaports"
git -C "$PMAPORTS" fetch -q origin main
if git -C "$PMAPORTS" rev-parse --verify -q "$BRANCH" >/dev/null; then
	git -C "$PMAPORTS" checkout -q "$BRANCH"
	if [ "$1" = "--rebase" ]; then
		git -C "$PMAPORTS" rebase origin/main
	fi
else
	git -C "$PMAPORTS" checkout -q -b "$BRANCH" origin/main
fi
echo "    pmaports: $(git -C "$PMAPORTS" log -1 --format='%h %cd %s' --date=short)"

# --- work directory ------------------------------------------------------------
# pmbootstrap init would create these interactively; the layout is just a
# version file and a cache_git directory owned by the user.
work_version="$(python3 -c 'import pmb.config; print(pmb.config.work_version)')"
mkdir -p "$WORK/cache_git"
chmod 700 "$WORK"
[ -f "$WORK/version" ] || echo "$work_version" > "$WORK/version"

# --- pmbootstrap config --------------------------------------------------------
if [ ! -f "$CFG" ]; then
	echo "==> writing $CFG"
	old="$HOME/.config/pmbootstrap_v3.cfg"
	get() { [ -f "$old" ] && sed -n "s/^$1 = //p" "$old" | head -n1; }
	locale="$(get locale)"
	timezone="$(get timezone)"
	user="$(get user)"
	cat > "$CFG" <<EOF
[pmbootstrap]
aports = $PMAPORTS
work = $WORK
device = xiaomi-cupid
kernel = ${CUPID_KERNEL:-stable}
ui = ${CUPID_UI:-phosh}
user = ${user:-$USER}
hostname = cupid
ssh_keys = True
locale = ${locale:-en_US.UTF-8}
timezone = ${timezone:-UTC}
jobs = $(nproc)
ccache_size = 10G
extra_packages = none
is_default_channel = True
auto_zap_misconfigured_chroots = yes

[providers]

[mirrors]
EOF
else
	echo "==> keeping existing $CFG"
fi

# --- packages ------------------------------------------------------------------
"$REPO/scripts/sync.sh"

echo
echo "==> pmbootstrap configuration"
pmb config | sed -n '/^\[pmbootstrap\]/,/^$/p' | grep -E '^(aports|work|device|kernel|ui|user|hostname|locale|timezone|jobs) '
echo
echo "Done. Next: scripts/build.sh"
