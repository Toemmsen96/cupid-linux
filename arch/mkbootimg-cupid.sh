#!/bin/sh
# Assemble an Android boot image for cupid from an Arch kernel and initramfs,
# with the same layout as the postmarketOS deviceinfo: header v2, page size
# 4096, dtb appended to the kernel and in the v2 dtb region (ABL reads the
# latter). Run on the phone after installing linux-cupid, or anywhere with
# mkbootimg (android-tools).
#
#   arch/mkbootimg-cupid.sh [vmlinuz] [initramfs] [dtb] [out]
set -e
kernel="${1:-/boot/vmlinuz-cupid}"
initrd="${2:-/boot/initramfs-cupid.img}"
dtb="${3:-/boot/dtbs/qcom/sm8450-xiaomi-cupid.dtb}"
out="${4:-boot-cupid.img}"
command -v mkbootimg >/dev/null || { echo "mkbootimg not found (android-tools)"; exit 1; }

root="$(findmnt -no UUID / 2>/dev/null || true)"
cmdline="pcie_aspm.policy=performance root=UUID=$root rw rootwait"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
cat "$kernel" "$dtb" > "$tmp"

mkbootimg \
	--kernel "$tmp" \
	--ramdisk "$initrd" \
	--dtb "$dtb" \
	--cmdline "$cmdline" \
	--base 0x00000000 \
	--kernel_offset 0x00008000 \
	--ramdisk_offset 0x01000000 \
	--second_offset 0x00000000 \
	--tags_offset 0x00000100 \
	--dtb_offset 0x01f00000 \
	--pagesize 4096 \
	--header_version 2 \
	-o "$out"
echo "wrote $out (cmdline: $cmdline)"
echo "flash: fastboot flash boot_<slot> $out   or on the phone:"
echo "       dd if=$out of=/dev/disk/by-partlabel/boot_a bs=1M conv=fsync"
