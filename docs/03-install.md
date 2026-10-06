# 03 Install

## What gets flashed

With the phone in fastboot (power off, then hold Volume-Down + Power):

```sh
scripts/flash.sh
```

| Step | Partition | Why |
|---|---|---|
| vbmeta with verification disabled | `vbmeta_a`, `vbmeta_b` | ABL otherwise rejects the unsigned kernel. Both slots, because ABL switches slots after repeated boot failures and the other slot would still enforce. |
| erase | `dtbo_a`, `dtbo_b`, `vendor_boot_a`, `vendor_boot_b` | ABL applies the dtbo overlays and the vendor_boot devicetree on top of the boot image's devicetree, which corrupts a mainline dtb and bootloops. Documented on the postmarketOS wiki for cupid; a bisect on the Xiaomi 12 Pro confirmed it. |
| `boot.img` | `boot_<current slot>` | kernel, initramfs and dtb (header v2, dtb both appended and in the v2 dtb region, which is the copy ABL uses) |
| `xiaomi-cupid.img` | `userdata` | the single-partition root filesystem, labelled `pmOS_root` |

The script refuses to run on a locked bootloader or on a device whose
`product` is not `cupid`, prints the plan and asks you to type `ERASE`.
Nothing touches the bootloader (`xbl`, `abl`), so Volume-Down + Power always
reaches fastboot again.

Kernel-only reflash after a rebuild: `scripts/flash.sh kernel`. Root-only:
`scripts/flash.sh rootfs`. Do not mix a new `boot.img` with an old rootfs
without reflashing both: the boot image's cmdline names the root filesystem by
UUID and each `pmbootstrap install` generates a new one.

The equivalent manual pmbootstrap commands are `scripts/pmb flasher
flash_vbmeta` (current slot only), `scripts/pmb flasher flash_kernel` and
`scripts/pmb flasher flash_rootfs`; the erase step has no pmbootstrap
equivalent.

## Alternatives from the wiki

The postmarketOS wiki installs cupid as `fastboot set_active b`, erase
`vendor_boot` and `dtbo`, then flash the combined image to `cust` (if under
2 GB) or `super`. That keeps Android's userdata but replaces the Android
system in super. This repository flashes userdata instead (the Xiaomi 12 Pro
procedure), which keeps super intact; pick one, not both. To follow the wiki
variant: `scripts/build.sh` with `scripts/pmb install --no-split` in place of
the single-partition install, then `scripts/pmb flasher flash_rootfs
--partition super`.

## First boot

- About 30 s after the reboot the phone shows up as a USB network device.
  `ssh <user>@172.16.42.1` (user and password from `scripts/pmb config`,
  default password `147147`). The first boot takes a couple of minutes while
  the filesystem is resized and the user is created.
- A black screen with SSH working is the first milestone. Then look at
  `dmesg` for the panel (`panel-l3-42-02-0a-dsc`), touch (`fts`), WiFi
  (`ath11k`, `PCIe Gen.2 x1 link up`) and the remoteprocs.
- Change the password: `passwd`.

## Getting Android back

Download the stock fastboot ROM for your region and firmware version
(`cupid_*_images_*.tgz`) and, in fastboot:

```sh
fastboot flash vbmeta_a images/vbmeta.img
fastboot flash vbmeta_b images/vbmeta.img
fastboot flash dtbo_a images/dtbo.img
fastboot flash dtbo_b images/dtbo.img
fastboot flash vendor_boot_a images/vendor_boot.img
fastboot flash vendor_boot_b images/vendor_boot.img
fastboot flash boot_a images/boot.img
fastboot flash boot_b images/boot.img
fastboot erase userdata
fastboot reboot
```

Or run the ROM's `flash_all.bat`/`flash_all.sh`, which rewrites every
partition including super. Both leave the bootloader unlocked.
