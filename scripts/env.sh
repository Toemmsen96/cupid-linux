# shellcheck shell=sh
# Shared settings for the cupid-linux scripts. Source this, do not run it.
#
# Everything lives in its own pmbootstrap work directory and config file so
# that an existing pmbootstrap setup on this machine is left untouched.
#
# Override by exporting before running a script:
#   CUPID_PMB_WORK   pmbootstrap work dir (chroots, package cache, ccache)
#   CUPID_PMAPORTS   pmaports checkout that carries the cupid branch
#   CUPID_UI         postmarketOS UI (phosh, gnome-mobile, console, ...)
#   CUPID_KERNEL     kernel variant: stable (6.13, recommended) or next (6.17)
#   CUPID_PASSWORD   password for the user account in the image

REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${CUPID_PMB_WORK:-$HOME/.local/var/pmbootstrap-cupid}"
PMAPORTS="${CUPID_PMAPORTS:-$REPO/work/pmaports}"
CFG="$REPO/work/pmbootstrap.cfg"
OUT="$REPO/out"
BRANCH="cupid"
PMAPORTS_URL="https://gitlab.postmarketos.org/postmarketOS/pmaports.git"

# The package directories this repository carries on top of pmaports.
PACKAGES="device-xiaomi-cupid firmware-xiaomi-cupid linux-postmarketos-qcom-sm8450-cupid linux-postmarketos-qcom-sm8450-cupid-next"

pmb() {
	pmbootstrap -c "$CFG" "$@"
}

die() {
	echo "error: $*" >&2
	exit 1
}

need() {
	for tool in "$@"; do
		command -v "$tool" >/dev/null 2>&1 || die "$tool not found in PATH"
	done
}
