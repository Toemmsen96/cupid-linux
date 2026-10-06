#!/bin/sh
# Build the postmarketOS image for the Xiaomi 12.
#
#   scripts/build.sh              packages + image + vbmeta, into out/
#   scripts/build.sh kernel       (re)build the selected kernel package only
#   scripts/build.sh image        skip the explicit package build, just install
#   scripts/build.sh kconfig      run pmbootstrap's kconfig check on the kernel
#
# Environment: see scripts/env.sh. CUPID_PASSWORD sets the user password in the
# image (default 147147, change it with passwd after the first login).
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
		;;
	*)
		die "unknown command: $1"
		;;
esac

echo "==> installing image"
# --single-partition: boot and root in one filesystem, flashed to userdata as
# is. That is what the initramfs expects on a fastboot device, and it avoids
# the nested partition table the combined image would otherwise carry.
pmb install --single-partition --password "${CUPID_PASSWORD:-147147}"

echo "==> exporting to $OUT"
mkdir -p "$OUT"
pmb export "$OUT"

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
