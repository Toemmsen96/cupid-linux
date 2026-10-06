# 01 Prerequisites

## Bootloader unlock

Nothing can be flashed on a locked Xiaomi bootloader. If the phone is not
unlocked yet, start this first; the waiting period is set by Xiaomi and has
grown over the years (historically 7 days, 30 days or more on recent HyperOS).

1. Settings, About phone, tap the MIUI/HyperOS version seven times.
2. Developer options, Mi Unlock status, add the account and device. This binds
   the Mi account to the phone and starts the timer.
3. After the timer expires, put the phone in fastboot (power off, hold
   Volume-Down + Power) and run the Mi Unlock Tool on a Windows machine with
   the same account.

Unlocking wipes the phone and permanently drops Widevine to L1 for streaming
apps. `fastboot getvar unlocked` must print `yes` before continuing.

## Backups

Flashing erases userdata. Also save things that are hard to get back:

- Run `scripts/dump-stock.sh` while Android is still installed. It pulls the
  stock devicetree (`/sys/firmware/fdt`), the partition list and properties.
  With root it also saves the touch firmware and the WLAN MAC.
- Download the stock fastboot ROM for your variant from Xiaomi (the `.tgz`
  with `images/`). It is the only way to restore Android later, see
  [03-install.md](03-install.md).

## Host

- Linux. pmbootstrap needs Linux namespaces and loop devices; macOS and WSL2
  do not work.
- Packages: `pmbootstrap` (3.x), `git`, `rsync`, `python3`, `android-tools`
  (`fastboot`, `adb`), `avbtool` (packaged with android-tools on Arch, or
  `pip install avbtool`), `dtc` for `scripts/check-dts.sh`.
- Passwordless or cached `sudo`: pmbootstrap runs its chroots as root.
- About 15 GB of disk for the work directory and 30 to 60 minutes for the
  first kernel build on a fast desktop.

`scripts/setup.sh` checks for the tools it needs.
