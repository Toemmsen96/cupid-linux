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
`device-xiaomi-cupid` and the selected kernel package, then
`pmbootstrap install --single-partition`, `pmbootstrap export out/` and
`avbtool make_vbmeta_image`.

Useful variants:

| Command | Effect |
|---|---|
| `scripts/build.sh kernel` | rebuild only the selected kernel package |
| `scripts/build.sh image` | skip the explicit package build and only (re)install the image |
| `scripts/build.sh kconfig` | run pmbootstrap's kconfig check against the kernel config |
| `CUPID_UI=console scripts/build.sh` | console UI, the safest first boot |
| `CUPID_KERNEL=next scripts/build.sh` | the experimental 6.17 kernel |
| `CUPID_PASSWORD=secret scripts/build.sh` | user password in the image (default `147147`) |

The kernel variant and UI are stored in the config, so `scripts/pmb config
kernel next` and `scripts/pmb config ui phosh` work as well.

## Editing packages

Edit under `pmaports/device/testing/` in this repository, not in
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
