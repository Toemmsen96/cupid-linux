# 02 Build

## Layout

Everything is isolated from any existing pmbootstrap setup:

- `work/pmbootstrap.cfg`: the config for this repository (`scripts/pmb` and
  the other scripts pass it with `-c`).
- `work/pmaports/`: a clone of upstream pmaports with a `cupid` branch on top
  of `main` (the edge channel). The packages from `pmaports/` here are rsynced
  into it by `scripts/sync.sh` and committed.
- `~/.local/var/pmbootstrap-cupid/`: the work directory (chroots, package
  cache, ccache). Override with `CUPID_PMB_WORK`.
- `out/`: the exported images.

## Steps

```sh
scripts/setup.sh                 # once; re-run after "git pull" in this repo
scripts/build.sh                 # packages + image + vbmeta
```

`build.sh` runs `sync.sh`, builds `firmware-xiaomi-cupid`,
`device-xiaomi-cupid`, the selected kernel package and the overlays in
`pmaports/temp/` (`TEMP_PACKAGES` in `scripts/env.sh`: libcamera with the
camera support, ModemManager with the GPS fix, hexagonrpcd with the audio PD,
and the phosh microphone indicator plugin), then
`pmbootstrap install --single-partition`, `pmbootstrap export out/` and
`avbtool make_vbmeta_image`.

Useful variants:

| Command | Effect |
|---|---|
| `scripts/build.sh kernel` | rebuild only the selected kernel package |
| `scripts/build.sh image` | skip the explicit package build and only (re)install the image |
| `scripts/build.sh kconfig` | run pmbootstrap's kconfig check against the kernel config |
| `CUPID_UI=console scripts/build.sh` | console UI, the safest first boot |
| `CUPID_KERNEL=mainline scripts/build.sh` | the Linux 7.3 kernel (what the phone runs now) |
| `CUPID_KERNEL=next scripts/build.sh` | the 6.17 fork kernel |
| `scripts/pmb build --arch aarch64 libcamera` | rebuild one overlay package (`--arch` matters for "arch all" packages) |
| `CUPID_PASSWORD=secret scripts/build.sh` | user password in the image (else pmbootstrap asks; can live in `cupid.env`) |

The kernel variant and UI are stored in the config, so `scripts/pmb config
kernel next` and `scripts/pmb config ui phosh` work as well.

## Building on the phone

Package updates for a running phone can be built on the phone itself with
`abuild`, without pmbootstrap and without root on the host:
`scripts/phone-build.sh [-i] PACKAGE...` copies the package directories over
SSH, builds them there and with `-i`
installs them (a kernel package flashes the boot partition; reboot to use
it). Meant for small packages: a kernel takes about an hour there, as the
phone throttles to a fraction of its clock under a sustained full load. The one-time setup on the phone is in the script's header. The phone
downloads sources and build dependencies itself, so keep it on Wi-Fi.

## Editing packages

Edit under `pmaports/device/testing/` (and `pmaports/temp/` for the
overlays of upstream packages) in this repository, not in
`work/pmaports/`. `sync.sh` recomputes the sha512 of local source files and
copies the directories over. After changing the devicetree, check it without
a kernel build:

```sh
curl -L https://github.com/sm8450-mainline/linux/archive/bf1d29fced6e156dd6090a9b6600a8c44259c114.tar.gz | tar xz -C /tmp
scripts/check-dts.sh pmaports/device/testing/linux-postmarketos-qcom-sm8450-cupid/sm8450-xiaomi-cupid.dts /tmp/linux-bf1d29fced6e156dd6090a9b6600a8c44259c114
```

For the kernel config: `scripts/pmb kconfig edit linux-postmarketos-qcom-sm8450-cupid`
opens menuconfig in the chroot and writes the result back into
`work/pmaports/`; copy the file back into this repository afterwards.

## Test images: WiFi, sudo and SSH host key baked in

Every flash otherwise starts from zero: WiFi has to be set up by hand, sudo
asks for the password, and the SSH host key changes. For test builds keep
those in a private overlay:

```sh
scripts/local-pull.sh                    # from the running phone ($CUPID_PHONE), once
scripts/build.sh                          # injects local/rootfs/ into the image
```

`local-pull.sh` copies the phone's NetworkManager connections (with their
WiFi passwords; system connections come up at boot, before anyone logs in)
and its SSH host keys into `local/rootfs/`, and writes a NOPASSWD sudo rule
for the image's user. Anything else placed under `local/rootfs/` is copied
too, owned by root with the file's own mode. `build.sh` injects it after
`pmbootstrap export` with `scripts/inject-local.sh` (debugfs on the image
file, no root needed); `scripts/inject-local.sh` alone redoes it on an
existing `out/xiaomi-cupid.img`. `CUPID_NO_LOCAL=1 scripts/build.sh` builds a
clean image.

`local/` is gitignored and holds secrets: do not commit, upload or share
images built with it.

## Why --single-partition

A fastboot device boots `boot.img` from the boot partition; the root
filesystem is found by its `pmOS_root` label. With the default (split) install
pmbootstrap also produces a separate boot filesystem image that has no
partition to go to on this device, and the combined image carries a nested
partition table that the initramfs has to probe with loop devices. The
single-partition image is one filesystem with `/boot` inside it, flashed to
`userdata` as is. That is the layout pmbootstrap documents for "devices that
boot without mounting the boot file system (e.g. Android boot images or
fastboot)".
