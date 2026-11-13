# cupid-linux: mainline Linux for the Xiaomi 12 (cupid)

A postmarketOS port of the Xiaomi 12 (`xiaomi-cupid`, Snapdragon 8 Gen 1 /
SM8450) that fixes the issues listed on the device's postmarketOS wiki page,
packaged so it can be built and flashed from this repository. Arch Linux ARM
on the same kernel is the next step, see [docs/06-arch-linux.md](docs/06-arch-linux.md).

Everything here runs on top of upstream pmaports (edge): the packages in
[pmaports/](pmaports/) are an overlay that the scripts sync into a private
pmaports branch, with their own pmbootstrap config and work directory, so an
existing pmbootstrap setup on the machine is not touched.

## Quick start

```sh
scripts/setup.sh      # pmaports checkout + private pmbootstrap config (once)
scripts/build.sh      # kernel, device and firmware packages, image, vbmeta -> out/
scripts/flash.sh      # phone in fastboot: vbmeta, erase dtbo/vendor_boot, boot, userdata
```

Read [docs/01-prerequisites.md](docs/01-prerequisites.md) first: the bootloader
must be unlocked (Mi Unlock, days to weeks of waiting), and flashing erases
userdata. [docs/03-install.md](docs/03-install.md) explains every fastboot step
and how to get Android back.

Before flashing, save what is unique to the phone: `scripts/backup-sdcard.sh DEST`
copies internal storage over adb, and `scripts/dump-stock.sh DEST` saves build
properties and the partition list, plus, with root (a Magisk-patched stock
`boot.img` started once with `fastboot boot`), the stock devicetree, firmware,
WLAN MAC and checksummed images of `persist` and the modem EFS.

`build.sh` verifies the finished image (clean ext4, root filesystem complete)
and refuses to hand out a broken one; `flash.sh` refuses while pmbootstrap is
still running. Do not start Steam games, flatpak or podman containers during
`build.sh`: a new mount namespace can pin the image mount and leave it half
written.

## Status on real hardware

First booted on a Xiaomi 12 (2201123G, EEA, HyperOS 3 firmware) on 2026-11-12.

| Works | Partial / open | Not working |
|---|---|---|
| boot, USB networking + SSH, storage, display (120 Hz), touch, GPU (Adreno 730, phosh), WiFi, Bluetooth, battery level, USB-C headphones, zram swap | display shows sporadic corruption on interaction; modem registers on LTE/5G and gets bearers, but no data flows yet | internal speakers, camera, sensors, haptics, NFC, fingerprint |

The details, measurements and what was ruled out are in
[docs/05-hardware-status.md](docs/05-hardware-status.md); fixes for problems
seen after flashing are in [docs/04-troubleshooting.md](docs/04-troubleshooting.md).

## What this port changes versus the wiki state

The postmarketOS wiki (snapshot of November 2025) lists the device as
"mainline heavy WIP": flashing, USB networking, storage, 3D acceleration,
WiFi, Bluetooth, camera flash and IR work; screen, touch, battery, audio,
modem, sensors, haptics, NFC, OTG and FDE are broken. The device package there
pins a 2023 kernel that predates the cupid devicetree. This repository:

| Area | Change | Source |
|---|---|---|
| Kernel | sm8450-mainline `next-new` at 6.13-rc3, the tree the Xiaomi 12 Pro (zeus) port was verified on. Has the cupid devicetree, the cupid panel driver and the ST FTS touch driver. A 6.17-rc1 `next` variant is packaged as an experiment. | `linux-postmarketos-qcom-sm8450-cupid[-next]` |
| Boot | `qcom,msm-id` / `qcom,board-id` in the devicetree (ABL will not boot a dtb without them), vbmeta with verification disabled on both slots, `dtbo` and `vendor_boot` erased, single-partition image on userdata. | devicetree, `scripts/flash.sh`, `scripts/build.sh` |
| Touch | Driver patches: one full-duplex SPI transfer per read (GENI returned zeros for the stock two-transfer shape), super-resolution coordinate decode, palm rejection. Devicetree: `fts,irq-flags` with `IRQF_ONESHOT`, touch rails always on. Firmware `st_fts_l3.ftb` packaged (driver refuses to probe without it). Module autoloaded. | patches 0002, 0003; `firmware-xiaomi-cupid-touchscreen` |
| WiFi | PCIe link-training retry with endpoint reset, ath11k firmware reset on WMI wedge, missing `vddpmumx`/`vddpmucx` PMU supplies, `max-link-speed = <2>`, WCN rails always on, ASPM forced to `performance`, NetworkManager power save off. | patches 0004, 0005; devicetree; deviceinfo cmdline; device package |
| Bluetooth | Controller comes up unconfigured (no `local-bd-address`); `bootmac` from `soc-qcom` assigns an address at boot. | device package depends |
| Audio | ADSP service races fixed (GPR callback before probe, PDR ack order, SPF readiness poll), DAPM audio routing from the SM8450 HDK, UCM profile for card `sm8450/Xiaomi-12`, topology symlink to the HDK topology. USB-C headphones work (verified on cupid); the internal speakers over tertiary TDM remain an unsolved SoC/firmware problem. | patches 0006, 0007, 0008; devicetree; device package |
| Battery | `CONFIG_BATTERY_QCOM_BATTMGR` and `pmic-glink` so the ADSP battery manager reports charge level and state. The cupid firmware never answers `model_name`/`time_to_full_avg`; those reads blocked a second each (~70 errors a minute), the driver now stops asking after three timeouts. | kernel config, patch 0010 |
| Display | Runs at 120 Hz like stock (selectable 60/90/120 via `panel_l3_42_02_0a_dsc.refresh_rate`); at 60 Hz the OLED's PWM dimming flickered. Brightness is kept while the panel is off instead of failing and leaving DSI in HS mode. DSI byte clock rounded to the PLL rate (upstream backport). | patches 0011, 0014, 0015 |
| Modem data | IPA v5.1 support backported from the pending upstream "SM8450 IPA support" series, devicetree node enabled; IPA runtime PM kept on because its first suspend hangs. | patches 0012, 0013; device package udev rule |
| Swap | zstd/lz4 zram backends (pmOS asks for zstd, the kernel only had LZO). | kernel config |
| Thermal | 85 C passive cooling maps for all CPU zones (`sm8450.dtsi` has none, so the SoC could only hit its critical trip). | devicetree |
| A/B slots | `soc-qcom-qbootctl` marks the slot successful; the previous cupid package never built its openrc subpackage, so ABL rolled back after about seven boots. | device package |
| Phosh | Display scale 2, punch-hole cutout definition for gmobile. | device package `-phosh` |
| Firmware | Fetched from GitHub instead of git.mainlining.org (which has been returning 502); the modem blob is included in GitHub's archive despite being in LFS. | `firmware-xiaomi-cupid` |

Not addressed yet: camera (no SM8450 CAMSS on mainline), fingerprint, NFC,
FM, fast charging (vendor charge pumps; expect USB-PD rates), internal
speakers (CS35L41 over TDM, an AudioReach gap), sensors (need the SLPI and a
userspace sensor stack), haptics. Open investigations: the display corruption
(TE is clean at 120 Hz; stock drives DSC with 10 bpc over RGB101010, which
6.13's DSI host cannot do yet) and modem data (uplink reaches IPA, nothing comes
back). Details per component are in
[docs/05-hardware-status.md](docs/05-hardware-status.md).

## Layout

```
pmaports/device/testing/
  device-xiaomi-cupid/                    deviceinfo, UCM, phosh, modules, NM config
  firmware-xiaomi-cupid/                  remoteproc/GPU/IPA blobs + touch firmware
  linux-postmarketos-qcom-sm8450-cupid/   6.13-rc3 kernel: config, devicetree, patches
  linux-postmarketos-qcom-sm8450-cupid-next/  6.17-rc1 kernel (experimental)
scripts/      setup, sync, build, flash, stock dump, sdcard backup, devicetree check, pmb wrapper
docs/         prerequisites, build, install, troubleshooting, hardware status, Arch, firmware
arch/         Arch Linux ARM rootfs builder and kernel PKGBUILD (phase 2)
```

Build output lands in `out/` (symlinks into the pmbootstrap work directory):
`boot.img`, `xiaomi-cupid.img`, `vbmeta-disabled.img`, kernel, initramfs and dtb.

## Choosing the kernel and UI

```sh
scripts/pmb config kernel next     # or: stable (default, 6.13-rc3)
scripts/pmb config ui console      # black screen + SSH is the safest first boot
scripts/build.sh image             # re-install without rebuilding packages
```

`scripts/pmb` is pmbootstrap with this repository's config; any pmbootstrap
command works through it (`scripts/pmb log`, `scripts/pmb chroot`, ...).

## Credits

- [sm8450-mainline](https://github.com/sm8450-mainline) (Jens Reidel and
  contributors): the kernel fork, the cupid devicetree and panel driver, the
  firmware repository and the original pmaports packages.
- [postmarketOS-zeus](https://github.com/Blaze414/postmarketOS-zeus): the
  Xiaomi 12 Pro bring-up, from which the kernel patches, the boot recipe, the
  UCM profile and most of the fixes above are taken.
- [TheMuppets](https://github.com/TheMuppets/proprietary_vendor_xiaomi_cupid):
  the touchscreen firmware files.
- Esteban Urrutia and Nazar Kompanets: the IPA v5.1 support for SM8450
  ("SM8450 IPA support", pending upstream), backported here as 0012/0013.
