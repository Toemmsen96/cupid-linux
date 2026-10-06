#!/bin/sh
# Copy the packages from this repository into the pmaports checkout.
#
# The repository is the source of truth: edit pmaports/ here, then run this
# (build.sh runs it for you). Checksums of local source files are refreshed in
# place before copying, so "PLACEHOLDER" entries and stale sums are fixed
# without a download.
set -e
. "$(dirname "$0")/env.sh"

need rsync python3
[ -d "$PMAPORTS/device/testing" ] || die "pmaports checkout missing, run scripts/setup.sh"

refresh_checksums() {
	python3 - "$1" <<'PY'
import hashlib, os, re, sys
d = sys.argv[1]
p = os.path.join(d, "APKBUILD")
s = open(p).read()
m = re.search(r'sha512sums="\n(.*?)"\n', s, re.S)
if not m:
    sys.exit(0)
out = []
changed = False
for line in m.group(1).splitlines():
    parts = line.split()
    if len(parts) != 2:
        out.append(line)
        continue
    old, name = parts
    f = os.path.join(d, name)
    if os.path.isfile(f):
        new = hashlib.sha512(open(f, "rb").read()).hexdigest()
        if new != old:
            changed = True
        out.append(f"{new}  {name}")
    else:
        if old == "PLACEHOLDER":
            print(f"warning: {name}: not a local file and no checksum set", file=sys.stderr)
        out.append(line)
if changed:
    s = s[:m.start(1)] + "\n".join(out) + "\n" + s[m.end(1):]
    open(p, "w").write(s)
    print(f"    refreshed checksums in {p}")
PY
}

for pkg in $PACKAGES; do
	src="$REPO/pmaports/device/testing/$pkg"
	[ -d "$src" ] || die "missing $src"
	refresh_checksums "$src"
	rsync -a --delete "$src/" "$PMAPORTS/device/testing/$pkg/"
	echo "    synced $pkg"
done

git -C "$PMAPORTS" add -A device/testing
if ! git -C "$PMAPORTS" diff --cached --quiet; then
	git -C "$PMAPORTS" -c user.name=cupid-linux -c user.email=cupid-linux@localhost \
		commit -q -m "cupid: sync packages from cupid-linux" >/dev/null
	echo "    committed to pmaports branch $BRANCH"
fi
