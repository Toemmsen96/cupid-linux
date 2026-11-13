#!/bin/sh
# Save what we can from the stock Android install before replacing it.
# Run with the phone booted into MIUI/HyperOS with USB debugging on.
#
#   scripts/dump-stock.sh [outdir]      default: stock-dump/
#
# Without root this grabs build properties and the partition list (MIUI also
# allows the stock devicetree, HyperOS 3 does not). With root (Magisk/KernelSU,
# e.g. a Magisk-patched stock boot.img started once with `fastboot boot`) it
# also saves:
#   - the stock devicetree, kernel cmdline and bootconfig
#   - touchscreen and GPU firmware from /vendor/firmware
#   - the WLAN MAC from persist
#   - the sensor stack files (SLPI libraries, configs, per-unit registry)
#   - raw images of the device-unique partitions (persist with sensor/audio/
#     camera calibration, modem EFS with IMEI/RF calibration, ...), verified
#     against the phone by SHA-256. Nothing is written to the phone.
set -e
. "$(dirname "$0")/env.sh"
need adb sha256sum

out="${1:-$REPO/stock-dump}"
mkdir -p "$out"

# Device-unique partitions worth keeping; missing ones are skipped.
PARTS="persist persistbak modemst1 modemst2 fsg fsc devinfo cdt countrycode secdata spunvm"

adb wait-for-device
echo "==> device: $(adb shell getprop ro.product.device) $(adb shell getprop ro.build.version.incremental)"

# `adb shell` re-joins its arguments, so the su command must be one quoted word.
root=false
adb shell "su -c id" 2>/dev/null | grep -q 'uid=0' && root=true
echo "    root: $root"
rootcat() { adb exec-out "su -c 'cat $1'" 2>/dev/null; }

# fetch FILE OUT: as shell first, then as root; drop empty or error-only output.
fetch() {
	adb exec-out "cat $1" > "$2" 2>/dev/null || true
	if { [ ! -s "$2" ] || grep -qs 'Permission denied\|No such file' "$2"; } && $root; then
		rootcat "$1" > "$2" || true
	fi
	if [ ! -s "$2" ] || grep -qs 'Permission denied\|No such file' "$2"; then
		rm -f "$2"
		return 1
	fi
}

echo "==> stock devicetree"
if fetch /sys/firmware/fdt "$out/cupid-stock.dtb"; then
	if command -v dtc >/dev/null 2>&1; then
		dtc -I dtb -O dts -o "$out/cupid-stock.dts" "$out/cupid-stock.dtb" 2>/dev/null || true
	fi
else
	echo "    not readable (needs root); take the dtb from the stock fastboot ROM instead"
fi

echo "==> properties and partitions"
adb shell getprop > "$out/getprop.txt"
adb shell "ls -l /dev/block/bootdevice/by-name/" > "$out/partitions.txt" 2>/dev/null ||
	adb shell "ls -l /dev/block/by-name/" > "$out/partitions.txt"
for f in partitions cmdline bootconfig; do
	fetch "/proc/$f" "$out/$( [ $f = partitions ] && echo proc-partitions || echo $f ).txt" ||
		echo "    /proc/$f: not readable without root"
done

if ! $root; then
	echo "==> firmware, WLAN MAC, partition images: need root, skipped"
	echo
	echo "Saved to $out"
	ls -la "$out"
	exit 0
fi

echo "==> firmware"
for f in st_fts_l3.ftb st_fts_l3_thp.ftb stm_fts_production_limits.csv \
	a730_sqe.fw a730_zap.mbn gmu_gen70000.bin; do
	fetch "/vendor/firmware/$f" "$out/$f" && echo "    $f" || echo "    $f: not found"
done

echo "==> WLAN MAC"
for p in /mnt/vendor/persist/qca6490/wlan_mac.bin /persist/qca6490/wlan_mac.bin; do
	fetch "$p" "$out/wlan_mac.bin" && { echo "    $(cat "$out/wlan_mac.bin")"; break; }
done
[ -f "$out/wlan_mac.bin" ] || echo "    not found"

echo "==> partition images"
mkdir -p "$out/partitions"
for p in $PARTS; do
	adb shell "su -c '[ -e /dev/block/by-name/$p ]'" 2>/dev/null || { echo "    $p: not present"; continue; }
	adb exec-out "su -c 'dd if=/dev/block/by-name/$p bs=1M 2>/dev/null'" > "$out/partitions/$p.img"
	remote=$(adb shell "su -c 'sha256sum /dev/block/by-name/$p'" | cut -d' ' -f1)
	local_=$(sha256sum "$out/partitions/$p.img" | cut -d' ' -f1)
	if [ "$remote" = "$local_" ]; then
		echo "    $p ($(($(wc -c < "$out/partitions/$p.img") / 1024)) KiB) sha256 OK"
	else
		echo "    $p: CHECKSUM MISMATCH, run again" >&2
	fi
done
(cd "$out/partitions" && sha256sum *.img > SHA256SUMS)

# Sensor stack (SLPI): the DSP-side libraries, the sensor configs and this
# unit's sensor registry/calibration (persist). Needed for hexagonrpcd +
# libssc; the registry is per-device factory data, keep it private.
echo "==> sensor stack (dsp libraries, sensor configs, sensor registry)"
for d in /vendor/dsp/sdsp /vendor/etc/sensors /mnt/vendor/persist/sensors; do
	name="$(echo "$d" | tr / _ | sed 's/^_//')"
	adb exec-out "su -c 'tar -C / -cf - ${d#/} 2>/dev/null'" > "$out/$name.tar"
	if [ -s "$out/$name.tar" ]; then
		echo "    $d ($(($(wc -c < "$out/$name.tar") / 1024)) KiB)"
	else
		rm -f "$out/$name.tar"
		echo "    $d: not found"
	fi
done

echo
echo "Saved to $out"
ls -la "$out"
