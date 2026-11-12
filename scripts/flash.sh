#!/bin/sh
# Flash postmarketOS to a Xiaomi 12 (cupid) over fastboot.
#
#   scripts/flash.sh            full install: vbmeta, dtbo/vendor_boot erase,
#                               boot, userdata. Asks before erasing.
#   scripts/flash.sh kernel     boot.img only (after a kernel rebuild)
#   scripts/flash.sh rootfs     userdata only
#   scripts/flash.sh --yes ...  skip the confirmation
#
# Needs an unlocked bootloader and the phone in fastboot (power off, then hold
# Volume-Down + Power). Nothing here touches the bootloader itself; Volume-Down
# + Power always gets back to fastboot. Restoring Android needs the stock
# fastboot ROM (boot, dtbo, vendor_boot, vbmeta, userdata), see docs/03-install.md.
#
# Why each step exists:
#  - vbmeta_a/b with verification disabled: ABL otherwise rejects the unsigned
#    kernel outright, on either slot (the device switches slots after repeated
#    boot failures).
#  - dtbo and vendor_boot erased: ABL applies the dtbo overlays and the
#    vendor_boot devicetree on top of the boot image's devicetree, which
#    corrupts a mainline dtb and bootloops. Documented on the postmarketOS wiki
#    for cupid and confirmed on the Xiaomi 12 Pro.
#  - userdata gets the single-partition image: a bare filesystem labelled
#    pmOS_root that the initramfs finds without any nested partition table.
set -e
. "$(dirname "$0")/env.sh"

need fastboot

yes=0
if [ "$1" = "--yes" ] || [ "$1" = "-y" ]; then
	yes=1
	shift
fi
mode="${1:-all}"

boot="$OUT/boot.img"
rootfs="$OUT/xiaomi-cupid.img"
vbmeta="$OUT/vbmeta-disabled.img"

for f in "$boot" "$rootfs" "$vbmeta"; do
	case "$mode" in
		kernel) [ "$f" = "$rootfs" ] && continue ;;
		rootfs) [ "$f" = "$boot" ] && continue ;;
	esac
	[ -e "$f" ] || die "$f missing, run scripts/build.sh first"
done

dev="$(fastboot devices | awk 'NF {print $1; exit}')"
[ -n "$dev" ] || die "no device in fastboot. Power off, then hold Volume-Down + Power."

getvar() {
	fastboot getvar "$1" 2>&1 | awk -F': ' -v k="$1" '$1 == k {print $2; exit}'
}

unlocked="$(getvar unlocked)"
case "$unlocked" in
	yes) ;;
	no) die "bootloader is locked. Unlock it with Mi Unlock first (docs/01-prerequisites.md)." ;;
	*) echo "warning: bootloader reports unlocked='$unlocked', continuing" ;;
esac

slot="$(getvar current-slot)"
[ -n "$slot" ] || slot=a
product="$(getvar product)"
echo "device: $dev  product: ${product:-?}  slot: $slot"
case "$product" in
	cupid|"") ;;
	*) die "this is not a cupid (product=$product), refusing" ;;
esac

echo
echo "Plan ($mode):"
case "$mode" in
	all)
		echo "  vbmeta_a, vbmeta_b   <- $vbmeta  (verification off)"
		echo "  dtbo_a, dtbo_b       erased"
		echo "  vendor_boot_a, _b    erased"
		echo "  boot_$slot              <- $boot"
		echo "  userdata             <- $rootfs  (erases everything on it)"
		;;
	kernel) echo "  boot_$slot              <- $boot" ;;
	rootfs) echo "  userdata             <- $rootfs  (erases everything on it)" ;;
	*) die "unknown mode: $mode" ;;
esac
echo

if [ "$yes" = 0 ] && [ "$mode" != kernel ]; then
	printf 'Type ERASE to continue: '
	read -r answer
	[ "$answer" = "ERASE" ] || die "aborted"
fi

if [ "$mode" = all ]; then
	echo "==> vbmeta (both slots)"
	# The image is built with flags 3 (verity + verification disabled) by
	# build.sh, so no --disable-verity/--disable-verification here: fastboot
	# 37 fails on that header-only image with "Failed to find AVB_MAGIC".
	fastboot flash vbmeta_a "$vbmeta"
	fastboot flash vbmeta_b "$vbmeta"
	echo "==> erasing dtbo and vendor_boot (both slots)"
	for p in dtbo_a dtbo_b vendor_boot_a vendor_boot_b; do
		fastboot erase "$p" || echo "warning: erase $p failed (missing partition?)"
	done
fi

if [ "$mode" = all ] || [ "$mode" = kernel ]; then
	echo "==> boot_$slot"
	fastboot flash "boot_$slot" "$boot"
fi

if [ "$mode" = all ] || [ "$mode" = rootfs ]; then
	echo "==> userdata (a few minutes)"
	fastboot flash userdata "$rootfs"
fi

echo "==> rebooting"
fastboot reboot

cat <<EOF

First boot takes a couple of minutes (filesystem resize, user creation).
 - USB network comes up after ~30 s: ssh $(pmb config user 2>/dev/null || echo user)@172.16.42.1
 - If the screen stays black, that is not necessarily a failure: try SSH first.
 - If it falls back to fastboot: fastboot getvar slot-retry-count:$slot (see docs/04-troubleshooting.md)
EOF
