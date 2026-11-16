#!/bin/sh
# Copy the private overlay in local/rootfs/ into the exported rootfs image.
#
#   scripts/inject-local.sh            inject into out/xiaomi-cupid.img
#   scripts/inject-local.sh IMAGE      inject into another image file
#
# For testing builds: WiFi connections, the passwordless sudo rule and fixed
# SSH host keys, so a freshly flashed phone is on WiFi before anyone logs in,
# accepts sudo without a password and keeps the host key known_hosts already
# has. local/ is gitignored; scripts/local-pull.sh fills it from a running
# phone. Every file lands owned by root:root with its mode from local/rootfs/
# (so keep NetworkManager connections and private keys at 0600). Directories
# that already exist in the image keep their owner and mode; missing ones are
# created root:root 0755.
#
# Works on the image file itself with debugfs: no root, no loop mount.
set -e
. "$(dirname "$0")/env.sh"

overlay="$REPO/local/rootfs"
[ -d "$overlay" ] && [ -n "$(find "$overlay" -type f -print -quit)" ] || {
	echo "    no local overlay ($overlay), image left as is"
	exit 0
}
need debugfs simg2img img2simg e2fsck

img="${1:-$OUT/xiaomi-cupid.img}"
[ -e "$img" ] || die "no image at $img"
src="$(readlink -f "$img")"

# Work on a raw copy next to out/ (the rootfs is several GB; /tmp is often a
# small tmpfs), then replace $img with a regular file. A symlink into the
# pmbootstrap work dir is replaced, the image in the work dir stays clean.
raw="$OUT/.inject-raw.img"
cmds="$OUT/.inject-cmds"
trap 'rm -f "$raw" "$raw.sparse" "$cmds"' EXIT
sparse=0
if file -b "$src" | grep -q 'Android sparse'; then
	sparse=1
	simg2img "$src" "$raw"
else
	cp --sparse=always "$src" "$raw"
fi

exists() {
	debugfs -R "stat \"$1\"" "$raw" 2>&1 | grep -q '^Inode:'
}

: > "$cmds"
# directories first, parents before children
(cd "$overlay" && find . -mindepth 1 -type d | sed 's|^\./|/|' | sort) |
while IFS= read -r d; do
	exists "$d" && continue
	{
		echo "mkdir \"$d\""
		echo "sif \"$d\" uid 0"
		echo "sif \"$d\" gid 0"
		echo "sif \"$d\" mode 040755"
	} >> "$cmds"
done
(cd "$overlay" && find . -type f | sed 's|^\./|/|' | sort) |
while IFS= read -r f; do
	mode="$(stat -c '%a' "$overlay$f")"
	dir="$(dirname "$f")"
	name="$(basename "$f")"
	{
		echo "cd \"$dir\""
		echo "rm \"$name\""
		echo "write \"$overlay$f\" \"$name\""
		echo "sif \"$name\" uid 0"
		echo "sif \"$name\" gid 0"
		echo "sif \"$name\" mode 0100$mode"
	} >> "$cmds"
	echo "    + $f ($mode)"
done

# rm of a file that is not there yet only prints an error; real failures
# show up in the read-back below.
debugfs -w -f "$cmds" "$raw" >/dev/null 2>&1 || true

(cd "$overlay" && find . -type f | sed 's|^\./|/|') |
while IFS= read -r f; do
	debugfs -R "stat \"$f\"" "$raw" 2>/dev/null | grep -q 'User: *0 *Group: *0' ||
		die "injecting $f failed"
done
e2fsck -fn "$raw" >/dev/null 2>&1 || die "filesystem errors after injecting, not using it"

rm -f "$img"
if [ "$sparse" = 1 ]; then
	img2simg "$raw" "$raw.sparse"
	mv "$raw.sparse" "$img"
else
	mv "$raw" "$img"
fi
echo "    local overlay injected into $img"
