#!/bin/sh
# Generate the voice call firmware for the kernel's voice front end (kernel
# patch 0042, "Voice Call Switch") from this phone's own stock calibration
# database, the Forte ACDB on the vendor partition. The file holds Xiaomi's
# and Qualcomm's calibration, so it is built here and never shipped.
#
# Runs at boot; does nothing when the ACDB and the generator are unchanged
# since the last run.
set -eu

LIB=/usr/share/cupid-voicecall
OUT=/lib/firmware/updates/qcom/sm8450/Xiaomi-12-voice.bin
STAMP=/var/lib/cupid-voicecall/stamp
ACDB=etc/acdbdata/Forte/Forte_acdb_cal.acdb

work=$(mktemp -d)
mnt="$work/vendor"
mkdir "$mnt"
cleanup() {
	umount "$mnt" 2>/dev/null || true
	rm -rf "$work"
}
trap cleanup EXIT

# The initramfs maps the Android dynamic partitions (make-dynpart-mappings).
# Stock's vendor may sit in either slot.
found=
for dev in /dev/mapper/vendor_a /dev/mapper/vendor_b; do
	[ -b "$dev" ] || continue
	mount -t erofs -o ro "$dev" "$mnt" 2>/dev/null || continue
	if [ -f "$mnt/$ACDB" ]; then
		cp "$mnt/$ACDB" "$work/acdb"
		found=$dev
	fi
	umount "$mnt"
	[ -n "$found" ] && break
done
if [ -z "$found" ]; then
	echo "no stock vendor partition with $ACDB: call audio unavailable" >&2
	exit 0
fi

stamp=$(cat "$work/acdb" "$LIB/voicecall/voicecall.py" "$LIB/acdb/acdb.py" \
	"$LIB/acdb/vcpm_cal.py" "$LIB/acdb/names.json" | sha256sum | cut -d' ' -f1)
if [ -f "$OUT" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$stamp" ]; then
	echo "$OUT up to date"
	exit 0
fi

# Handset: earpiece on the tertiary TDM speaker backend, handset microphone
# on codec DMA TX3, stock graphs with ECNS, full calibration tables.
python3 -I -B "$LIB/voicecall/voicecall.py" build "$work/acdb" \
	"$LIB/acdb/names.json" "$work/graphs" handset >/dev/null
python3 -I -B "$LIB/voicecall/voicecall.py" firmware "$work/graphs" "$work/voice.bin"

mkdir -p "$(dirname "$OUT")" "$(dirname "$STAMP")"
install -m644 "$work/voice.bin" "$OUT.tmp"
mv "$OUT.tmp" "$OUT"
echo "$stamp" > "$STAMP"
echo "generated $OUT from $found"
