# 06 Arch Linux

The goal is Arch Linux on the phone. The plan keeps the postmarketOS pieces
that are hard to replace and swaps the userspace:

1. **postmarketOS first** (this repository today). It gives a known-good
   kernel, boot image, initramfs and the device quirks, and a working system
   to debug hardware from.
2. **Arch Linux ARM rootfs booted by the postmarketOS boot image**
   (`arch/build-arch-rootfs.sh`). The postmarketOS initramfs only needs a
   filesystem labelled `pmOS_root` with the UUID named in `boot.img`'s
   cmdline, and `/sbin/init` inside it. Arch Linux ARM's generic aarch64
   tarball provides the userspace; the kernel modules, firmware and device
   files are copied out of the apks built here. Same `boot.img`, different
   `userdata`.
3. **Native Arch kernel package** (`arch/PKGBUILD`): the same source,
   config, devicetree and patches as the pmaports package, built with
   `makepkg` on an aarch64 host (the phone itself, once step 2 runs, or a
   cross/qemu build), plus a script that assembles `boot.img` with
   `mkbootimg`. From then on the phone is self-hosting and the postmarketOS
   initramfs can be replaced by mkinitcpio with the same device discovery.

## Step 2 in practice

```sh
scripts/build.sh                      # builds the apks and boot.img first
arch/build-arch-rootfs.sh             # -> arch/out/arch-cupid.img
scripts/flash.sh                      # boot.img + the postmarketOS rootfs, or:
fastboot flash userdata arch/out/arch-cupid.img
```

`build-arch-rootfs.sh` does, without root and without qemu:

- downloads `ArchLinuxARM-aarch64-latest.tar.gz` into `arch/cache/`;
- creates an ext4 image labelled `pmOS_root` with the root UUID from
  `out/boot.img`'s cmdline (so the existing boot image finds it);
- unpacks the tarball with `bsdtar` into the image via `debugfs`-free
  `mkfs.ext4 -d`, which needs no mount and no root;
- copies `/usr/lib/modules/<release>`, `/lib/firmware`, the UCM files, the
  NetworkManager and modules-load drop-ins and `/etc/deviceinfo` from the
  apks in the pmbootstrap work directory;
- configures hostname, a user with the same password as the pmOS image,
  sshd, and systemd-networkd with a DHCP server on `usb0` so
  `ssh user@172.16.42.1` keeps working.

Package installation (phosh, NetworkManager and so on) needs a running
aarch64 userspace. The script leaves a `firstboot.sh` in the image that runs
`pacman -Syu` and installs the packages listed in `arch/packages.txt` on the
first boot over USB networking, because the host cannot run `pacman` for
aarch64 without `qemu-user-static` (if `qemu-aarch64-static` and
`arch-chroot` are present the script does it at build time instead).

## Known gaps for the Arch path

- Untested on hardware so far; the pmOS image is the reference.
- The postmarketOS initramfs expects `/etc/deviceinfo` and runs its own
  resize and udev steps; those are harmless on Arch but the image size is
  fixed at creation (`CUPID_ARCH_SIZE`, default 6G) unless the initramfs
  resize succeeds.
- Audio needs the same UCM files and `alsa-ucm-conf`; the script copies the
  cupid UCM files, the rest comes from the Arch package.
- `qbootctl` is not packaged for Arch: without marking the slot successful,
  ABL falls back to fastboot after about seven boots. The script installs a
  small systemd unit that runs the `qbootctl` binary copied from the pmOS
  apk until an Arch package exists.
