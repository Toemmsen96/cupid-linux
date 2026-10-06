# Arch Linux on cupid (phase 2)

See [docs/06-arch-linux.md](../docs/06-arch-linux.md) for the plan.

- `build-arch-rootfs.sh`: Arch Linux ARM root filesystem image that boots
  with the postmarketOS `boot.img` from `scripts/build.sh`. Needs no root.
- `packages.txt`: packages installed on the first boot (or at build time with
  `arch-chroot` + `qemu-user-static`).
- `PKGBUILD`: native Arch kernel package from the same sources as the pmaports
  package; `mkbootimg-cupid.sh` turns it into a flashable boot image.

Untested on hardware; the postmarketOS image is the reference until it is.
