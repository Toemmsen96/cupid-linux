#!/bin/sh
# Save what we can from the stock Android install before replacing it.
# Run with the phone booted into MIUI/HyperOS with USB debugging on.
#
#   scripts/dump-stock.sh [outdir]      default: stock-dump/
#
# Without root this grabs the stock devicetree (the most valuable file for
# devicetree work), the partition list, build properties and the WLAN MAC.
# With root (Magisk/KernelSU) it also pulls the touchscreen firmware from
# /vendor/firmware, which lets you verify the copy packaged from LineageOS.
set -e
. "$(dirname "$0")/env.sh"
need adb

out="${1:-$REPO/stock-dump}"
mkdir -p "$out"

adb wait-for-device
echo "==> device: $(adb shell getprop ro.product.device) $(adb shell getprop ro.build.version.incremental)"

echo "==> stock devicetree"
adb pull /sys/firmware/fdt "$out/cupid-stock.dtb"
if command -v dtc >/dev/null 2>&1; then
	dtc -I dtb -O dts -o "$out/cupid-stock.dts" "$out/cupid-stock.dtb" 2>/dev/null || true
fi

echo "==> properties and partitions"
adb shell getprop > "$out/getprop.txt"
adb shell "ls -l /dev/block/bootdevice/by-name/" > "$out/partitions.txt" 2>/dev/null || \
	adb shell "ls -l /dev/block/by-name/" > "$out/partitions.txt"
adb shell cat /proc/partitions > "$out/proc-partitions.txt"
adb shell cat /proc/cmdline > "$out/cmdline.txt" 2>/dev/null || true

echo "==> firmware (needs root; skipped if unavailable)"
if adb shell su -c id >/dev/null 2>&1; then
	for f in st_fts_l3.ftb st_fts_l3_thp.ftb stm_fts_production_limits.csv \
		a730_sqe.fw a730_zap.mbn gmu_gen70000.bin; do
		adb shell su -c "cat /vendor/firmware/$f" > "$out/$f" 2>/dev/null && echo "    $f" || rm -f "$out/$f"
	done
	adb shell su -c "cat /persist/qca6490/wlan_mac.bin" > "$out/wlan_mac.bin" 2>/dev/null || rm -f "$out/wlan_mac.bin"
else
	echo "    no root, skipped"
fi

echo
echo "Saved to $out"
ls -la "$out"
