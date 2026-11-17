#!/bin/sh
# Build the postmarketOS image for the Xiaomi 12.
#
#   scripts/build.sh              packages (incl. pmaports/temp overlays) + image + vbmeta, into out/
#   scripts/build.sh kernel       (re)build the selected kernel package only
#   scripts/build.sh image        skip the explicit package build, just install
#   scripts/build.sh kconfig      run pmbootstrap's kconfig check on the kernel
#
# Environment: see scripts/env.sh. CUPID_PASSWORD (cupid.env) sets the user
# password in the image; without it pmbootstrap asks for one.
# If local/rootfs/ exists (scripts/local-pull.sh), its files go into the image:
# WiFi, passwordless sudo and SSH host keys for testing. CUPID_NO_LOCAL=1
# skips that.
set -e
. "$(dirname "$0")/env.sh"

need pmbootstrap avbtool
[ -f "$CFG" ] || die "no config yet, run scripts/setup.sh"

"$REPO/scripts/sync.sh"

# Allow switching the kernel/UI from the environment without editing the cfg.
[ -n "$CUPID_KERNEL" ] && pmb config kernel "$CUPID_KERNEL" >/dev/null
[ -n "$CUPID_UI" ] && pmb config ui "$CUPID_UI" >/dev/null

kernel_variant="$(pmb config kernel)"
case "$kernel_variant" in
	next) kernel_pkg="linux-postmarketos-qcom-sm8450-cupid-next" ;;
	mainline) kernel_pkg="linux-postmarketos-qcom-sm8450-cupid-mainline" ;;
	*) kernel_pkg="linux-postmarketos-qcom-sm8450-cupid" ;;
esac
echo "==> kernel variant: $kernel_variant ($kernel_pkg), ui: $(pmb config ui)"

case "$1" in
	kconfig)
		pmb kconfig check "$kernel_pkg"
		exit
		;;
	kernel)
		shift
		pmb build "$kernel_pkg" "$@"
		exit
		;;
	image)
		;;
	"")
		echo "==> building packages (the kernel takes a while)"
		pmb build firmware-xiaomi-cupid device-xiaomi-cupid "$kernel_pkg"
		# Overlays of upstream packages (pmaports/temp: libcamera with the
		# camera support, ModemManager with the GPS fix); "arch all" ones
		# default to the host architecture, so ask for the phone's.
		[ -z "$TEMP_PACKAGES" ] || pmb build --arch aarch64 $TEMP_PACKAGES
		;;
	*)
		die "unknown command: $1"
		;;
esac

# Switching kernels (stable, next, mainline) in an existing rootfs chroot fails: both
# packages own /boot/vmlinuz and the dtbs, so apk refuses to add the new one
# and leaves a half-installed rootfs. Start the chroots fresh in that case
# (zap keeps the built packages).
rootfs_db="$WORK/chroot_rootfs_xiaomi-cupid/lib/apk/db/installed"
if [ -r "$rootfs_db" ] &&
	grep -E '^P:linux-postmarketos-qcom-sm8450-cupid(-next|-mainline)?$' "$rootfs_db" |
	grep -qvx "P:$kernel_pkg"; then
	echo "==> rootfs has another kernel installed, zapping the chroots first"
	pmb -y zap
fi

echo "==> installing image"
# --single-partition: boot and root in one filesystem, flashed to userdata as
# is. That is what the initramfs expects on a fastboot device, and it avoids
# the nested partition table the combined image would otherwise carry.
if [ -n "$CUPID_PASSWORD" ]; then
	pmb install --single-partition --password "$CUPID_PASSWORD"
else
	pmb install --single-partition
fi

echo "==> exporting to $OUT"
mkdir -p "$OUT"
# A previous run's local overlay left a regular file where export puts its
# symlink.
[ -L "$OUT/xiaomi-cupid.img" ] || rm -f "$OUT/xiaomi-cupid.img"
pmb export "$OUT"

# Private test settings (WiFi, passwordless sudo, SSH host keys) from local/,
# see scripts/local-pull.sh. CUPID_NO_LOCAL=1 builds a clean image.
if [ -z "$CUPID_NO_LOCAL" ]; then
	echo "==> local overlay"
	"$REPO/scripts/inject-local.sh"
fi

# The image must be a cleanly unmounted filesystem. A process that creates a
# new mount namespace while pmbootstrap has the image mounted (a Steam game's
# pressure-vessel sandbox, flatpak, podman, ...) copies that mount; the
# umount then only detaches it on the host, ext4 never checkpoints its
# journal, and img2simg exports a filesystem that is mostly empty until the
# journal is replayed. It boots into the initramfs debug shell with half the
# top-level directories missing. Seen on 2026-11-12.
check_image() {
	img="$(readlink -f "$OUT/xiaomi-cupid.img")"
	command -v simg2img >/dev/null 2>&1 && command -v debugfs >/dev/null 2>&1 &&
		command -v e2fsck >/dev/null 2>&1 && command -v dumpe2fs >/dev/null 2>&1 || {
		echo "warning: simg2img/debugfs missing (android-tools, e2fsprogs), image not checked" >&2
		return 0
	}
	raw="$(mktemp "${TMPDIR:-/tmp}/cupid-rootfs.XXXXXX")"
	trap 'rm -f "$raw"' EXIT
	if file -b "$img" | grep -q 'Android sparse'; then
		simg2img "$img" "$raw"
	else
		cp --sparse=always "$img" "$raw"
	fi
	bad=""
	dumpe2fs -h "$raw" 2>/dev/null | grep '^Filesystem features:' | grep -q needs_recovery &&
		bad="$bad journal-not-checkpointed"
	e2fsck -fn "$raw" >/dev/null 2>&1 || bad="$bad fsck-errors"
	for p in /sbin /lib /home /usr/lib/systemd/systemd /etc/fstab; do
		out="$(debugfs -c -R "stat $p" "$raw" 2>&1)"
		echo "$out" | grep -qE 'File not found|not open|while (opening|reading)' &&
			bad="$bad missing:$p"
	done
	rm -f "$raw"
	if [ -n "$bad" ]; then
		echo "error: the exported image is incomplete:$bad" >&2
		echo "Something kept the image mounted in another mount namespace while" >&2
		echo "pmbootstrap built it (Steam game, flatpak, podman/toolbox...). Close" >&2
		echo "it and run: scripts/build.sh image   (do not flash this image)" >&2
		exit 1
	fi
	echo "    image check ok (clean ext4, root filesystem complete)"
}
echo "==> checking the image"
check_image

echo "==> vbmeta with verification disabled"
# flags 3 = HASHTREE_DISABLED | VERIFICATION_DISABLED, flashed to both slots
# by scripts/flash.sh.
avbtool make_vbmeta_image --flags 3 --padding_size 4096 \
	--output "$OUT/vbmeta-disabled.img"

echo
echo "==> images in $OUT"
ls -lL "$OUT"
echo
echo "Next: put the phone in fastboot (power off, hold Volume-Down + Power) and run scripts/flash.sh"
