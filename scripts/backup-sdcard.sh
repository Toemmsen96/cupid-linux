#!/bin/sh
# Copy the phone's internal storage (/sdcard) to DEST before flashing.
#
#   scripts/backup-sdcard.sh DEST [DIR...]     DIR relative to /sdcard, default all
#
# Re-runnable: files already in DEST with the same size are skipped, so after
# a dropped connection just run it again. Files Android will not let adb read
# are skipped instead of aborting the copy (adb pull stops at the first one).
# Android/data and Android/obb are left out: app-private since Android 11 and
# unreadable over adb without root. Android/media (WhatsApp media) is copied.
#
# Several devices attached: export ANDROID_SERIAL=<serial or ip:port>.
set -e
. "$(dirname "$0")/env.sh"
need adb tar comm

[ -n "$1" ] || die "usage: $0 DEST [DIR...]"
dest="$1"
shift
mkdir -p "$dest"

dirs=""
for d in "${@:-.}"; do
	d="${d#./}"
	d="${d%/}"
	# "." must stay "." ("./." makes find print "././x", which breaks the
	# Android/data prune and the path comparison below)
	case "$d" in
	. | "") dirs="$dirs ." ;;
	*) dirs="$dirs './$d'" ;;
	esac
done

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export LC_ALL=C

# "<size> <path>" per file, path relative to /sdcard, sorted for comm.
list_remote() {
	adb shell "cd /sdcard && find $dirs \( -path ./Android/data -o -path ./Android/obb \) -prune \
		-o -type f -exec stat -c '%s %n' {} + 2>/dev/null" | sed 's| \./| |' | sort
}
list_local() {
	(cd "$dest" && find . -type f -printf '%s %P\n') | sort
}
missing() {
	list_remote > "$tmp/remote"
	list_local > "$tmp/local"
	comm -23 "$tmp/remote" "$tmp/local" > "$tmp/missing"
}

adb wait-for-device
echo "==> comparing phone and $dest"
missing
n=$(wc -l < "$tmp/missing")
bytes=$(awk '{ s += $1 } END { print s + 0 }' "$tmp/missing")
echo "    $(wc -l < "$tmp/remote") files on the phone, $n to copy ($((bytes / 1048576)) MiB)"

if [ "$n" -gt 0 ]; then
	cut -d' ' -f2- "$tmp/missing" > "$tmp/list"
	adb push "$tmp/list" /data/local/tmp/backup-list >/dev/null 2>&1
	echo "==> copying"
	adb exec-out 'tar -cf - -C /sdcard -T /data/local/tmp/backup-list 2>/dev/null' |
		tar -xf - -C "$dest" ||
		echo "warning: transfer interrupted, run the script again to continue" >&2
	adb shell rm -f /data/local/tmp/backup-list || true

	echo "==> checking"
	missing
	n=$(wc -l < "$tmp/missing")
fi

if [ "$n" -eq 0 ]; then
	echo "All files copied."
else
	cp "$tmp/missing" "$dest.missing.txt"
	echo "$n files not copied (unreadable or interrupted), listed in $dest.missing.txt:"
	head -20 "$tmp/missing"
fi
