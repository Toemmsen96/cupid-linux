#!/bin/sh
# Compile a cupid devicetree against an extracted kernel tree, without building
# the kernel. Catches syntax errors and dangling labels in seconds.
#
#   scripts/check-dts.sh <path/to/sm8450-xiaomi-cupid.dts> <kernel-tree>
#
# The kernel tree is an extracted tarball of the commit the package pins, e.g.
#   curl -L https://github.com/sm8450-mainline/linux/archive/<commit>.tar.gz | tar xz
set -e
dts="$1"
tree="$2"
[ -f "$dts" ] && [ -d "$tree/arch/arm64/boot/dts/qcom" ] || {
	echo "usage: $0 <dts> <kernel-tree>" >&2
	exit 1
}
command -v dtc >/dev/null || { echo "dtc not found (install dtc)" >&2; exit 1; }

qcom="$tree/arch/arm64/boot/dts/qcom"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp" "$qcom/__check.dts"' EXIT
cp "$dts" "$qcom/__check.dts"
(cd "$qcom" && cpp -nostdinc -I "$tree/include" -I "$tree/scripts/dtc/include-prefixes" \
	-undef -D__DTS__ -x assembler-with-cpp __check.dts -o "$tmp/pp.dts")
dtc -I dts -O dtb -o "$tmp/out.dtb" "$tmp/pp.dts" 2>&1 | grep -v '^.*Warning (' || true
[ -s "$tmp/out.dtb" ] && echo "ok: $(stat -c %s "$tmp/out.dtb") bytes" || { echo "FAILED"; exit 1; }
