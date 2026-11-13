# 01 Prerequisites

## Bootloader unlock

Nothing can be flashed on a locked Xiaomi bootloader. On HyperOS this takes
an application to Xiaomi plus a waiting period, so start early. What it took
for the cupid this port was brought up on (EEA unit, HyperOS 3, November
2026):

1. **A Xiaomi account at least 30 days old**, with a **phone number** linked to
   it. Without the number the unlock fails with code 20041 ("your MI ID is not
   associated with a phone number"); it can be added at
   https://account.xiaomi.com/pass/serviceLogin?checkSafePhone=true when the
   phone settings do not offer it.
2. **Apply for unlock permission** in the Xiaomi Community app ("Unlock
   bootloader", region set to Global). Applications are only accepted right
   after 00:00 Beijing time (17:00 CET / 18:00 CEST) and the daily quota is
   gone within seconds; "Application quota limit reached" means try again the
   next day. A successful application is valid for a year.
3. Settings, About phone, tap the HyperOS version seven times. Then Developer
   options, **Mi Unlock status, "Add account and device"**, with a SIM inserted,
   WiFi off and mobile data on. Before the application is approved this says
   "Couldn't add, go to Mi Community"; afterwards it binds the account and
   starts the timer.
4. **Wait 72 hours.** Running the unlock earlier fails with code 20036
   ("please unlock 72 hours later"). Do not add the account in Mi Unlock
   status again, that restarts the wait; signing out of the Xiaomi account
   or logging out of the unlock tool may do the same.
5. Phone in fastboot (power off, hold Volume-Down + Power), then unlock. The
   Windows Mi Unlock Tool works, and so does
   [miunlock](https://github.com/offici5l/MiUnlockTool) on Linux
   (`pip install miunlock`, log in with the same account, press Enter at
   each prompt). Code 20031 means step 3 was not done.

Unlocking wipes the phone and permanently drops Widevine to L3 for streaming
apps. `fastboot getvar unlocked` must print `yes` before continuing.

## Backups

Flashing erases userdata. Also save things that are hard to get back:

- `scripts/backup-sdcard.sh DEST` copies internal storage over adb
  (resumable; app-private `Android/data` is not readable without root).
- `scripts/dump-stock.sh DEST` while Android is still installed. Without root
  HyperOS 3 only allows the build properties and the partition list. Root
  without installing anything: patch the stock `boot.img` from the ROM with
  Magisk and start it once with `fastboot boot` (needs the unlocked
  bootloader; a normal reboot returns to stock). With root the script also
  saves the stock devicetree, touch/GPU firmware, the WLAN MAC, the sensor
  stack files and checksummed images of `persist` (sensor, audio, camera
  calibration) and the modem EFS (IMEI, RF calibration). Keep those images
  private and safe; they are the only repair path for this unit.
- Download the stock fastboot ROM for your exact build (`ro.product.mod_device`
  and the HyperOS version from `getprop.txt`), e.g.
  `cupid_eea_global_images_OS3.0.3.0.VLCEUXM_..._eea_....tgz` from Xiaomi's
  CDN (`bigota.d.miui.com/<version>/<file>`), and check its MD5. It is the
  only way to restore Android later, see [03-install.md](03-install.md).

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
