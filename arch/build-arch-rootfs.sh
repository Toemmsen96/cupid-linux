#!/bin/sh
# Build an Arch Linux ARM root filesystem image for the Xiaomi 12 that boots
# with the postmarketOS boot.img produced by scripts/build.sh.
#
#   arch/build-arch-rootfs.sh            -> arch/out/arch-cupid.img
#
# Environment:
#   CUPID_ARCH_SIZE      image size (default 6G)
#   CUPID_PASSWORD       user password (default 147147)
#   CUPID_ARCH_USER      user name (default: the pmbootstrap user)
#
# Needs: bsdtar (libarchive), mkfs.ext4 with -d (e2fsprogs >= 1.43), tar,
# python3, curl. No root, no loop devices: the filesystem is populated with
# mkfs.ext4 -d from a staging directory. See docs/06-arch-linux.md.
set -e
. "$(dirname "$0")/../scripts/env.sh"

need bsdtar mkfs.ext4 python3 curl tar

AOUT="$REPO/arch/out"
CACHE="$REPO/arch/cache"
SIZE="${CUPID_ARCH_SIZE:-6G}"
TARBALL_URL="http://os.archlinuxarm.org/os/ArchLinuxARM-aarch64-latest.tar.gz"
PKGREPO="$WORK/packages/edge/aarch64"
mkdir -p "$AOUT" "$CACHE"

boot="$OUT/boot.img"
[ -e "$boot" ] || die "$boot missing: run scripts/build.sh first (it builds the kernel and boot image)"
[ -d "$PKGREPO" ] || die "$PKGREPO missing: run scripts/build.sh first"

user="${CUPID_ARCH_USER:-$(pmb config user 2>/dev/null || echo user)}"
password="${CUPID_PASSWORD:-147147}"

# --- root UUID from the boot image cmdline ------------------------------------
# The pmOS initramfs mounts the root by this UUID and will not fall back to
# the label if the UUID is absent.
root_uuid="$(python3 - "$boot" <<'PY'
import re, sys
data = open(sys.argv[1], "rb").read(4096)
cmd = data[64:64+512].split(b"\0", 1)[0].decode()
m = re.search(r"pmos_root_uuid=([0-9a-fA-F-]+)", cmd)
print(m.group(1) if m else "")
PY
)"
[ -n "$root_uuid" ] || die "no pmos_root_uuid in $boot cmdline"
echo "==> root UUID from boot.img: $root_uuid"

# --- Arch Linux ARM tarball -----------------------------------------------------
tarball="$CACHE/ArchLinuxARM-aarch64-latest.tar.gz"
if [ ! -s "$tarball" ]; then
	echo "==> downloading $TARBALL_URL"
	curl -L -o "$tarball" "$TARBALL_URL"
fi

stage="$AOUT/stage"
rm -rf "$stage"
mkdir -p "$stage"
echo "==> unpacking Arch Linux ARM"
bsdtar -xpf "$tarball" -C "$stage" 2>/dev/null || bsdtar -xf "$tarball" -C "$stage"

# --- pieces from the postmarketOS packages ---------------------------------------
# apk files are tar.gz; extract only the paths we need.
extract_apk() { # pkgprefix path...
	pkg="$(ls "$PKGREPO"/"$1"-[0-9]*.apk 2>/dev/null | head -n1)"
	[ -n "$pkg" ] || { echo "warning: no apk for $1 in $PKGREPO"; return 0; }
	shift
	echo "    $(basename "$pkg")"
	tar -xzf "$pkg" -C "$stage" --warning=no-unknown-keyword "$@" 2>/dev/null || true
}
echo "==> copying kernel modules, firmware and device files from the apks"
kernel_pkg="linux-postmarketos-qcom-sm8450-cupid"
[ "$(pmb config kernel 2>/dev/null)" = "next" ] && kernel_pkg="$kernel_pkg-next"
extract_apk "$kernel_pkg" usr/lib/modules
for fw in adsp cdsp gpu ipa modem slpi touchscreen; do
	extract_apk "firmware-xiaomi-cupid-$fw" lib/firmware
done
extract_apk "device-xiaomi-cupid" etc/deviceinfo etc/modules-load.d etc/NetworkManager usr/share/alsa lib/firmware
extract_apk "device-xiaomi-cupid-phosh" etc/phosh usr/share/gmobile etc/environment.d etc/profile.d
# Arch keeps firmware in /usr/lib/firmware; merge what the apks put in /lib.
if [ -d "$stage/lib/firmware" ] && [ ! -L "$stage/lib" ]; then
	mkdir -p "$stage/usr/lib/firmware"
	cp -a "$stage/lib/firmware/." "$stage/usr/lib/firmware/"
	rm -rf "$stage/lib/firmware"
fi

# --- system configuration ---------------------------------------------------------
echo "==> configuring the system"
echo cupid > "$stage/etc/hostname"
mkdir -p "$stage/etc/systemd/network" "$stage/etc/systemd/system/multi-user.target.wants" \
	"$stage/etc/systemd/system/sysinit.target.wants" "$stage/usr/local/bin"

cat > "$stage/etc/systemd/network/10-usb0.network" <<EOF
# USB networking, same addresses as postmarketOS
[Match]
Name=usb0

[Network]
Address=172.16.42.1/24
DHCPServer=yes

[DHCPServer]
PoolOffset=2
PoolSize=10
EmitDNS=no
EOF
ln -sf /usr/lib/systemd/system/systemd-networkd.service "$stage/etc/systemd/system/multi-user.target.wants/"
ln -sf /usr/lib/systemd/system/sshd.service "$stage/etc/systemd/system/multi-user.target.wants/"

# The pmOS initramfs sets up the RNDIS gadget with configfs; nothing in Arch
# tears it down, so usb0 survives switch_root.

# User with the same password as the pmOS image. The Arch tarball ships user
# "alarm"; add ours with a hashed password and wheel for sudo.
hash="$(python3 -c "import crypt,sys; print(crypt.crypt(sys.argv[1], crypt.mksalt(crypt.METHOD_SHA512)))" "$password" 2>/dev/null || openssl passwd -6 "$password")"
uid=1001
grep -q "^$user:" "$stage/etc/passwd" || {
	echo "$user:x:$uid:$uid::/home/$user:/bin/bash" >> "$stage/etc/passwd"
	echo "$user:x:$uid:" >> "$stage/etc/group"
	echo "$user:$hash:19000:0:99999:7:::" >> "$stage/etc/shadow"
	mkdir -p "$stage/home/$user"
	cp -a "$stage/etc/skel/." "$stage/home/$user/" 2>/dev/null || true
	chown -R "$uid:$uid" "$stage/home/$user" 2>/dev/null || true
}
sed -i "s/^wheel:x:10:.*/&,$user/" "$stage/etc/group"
echo "%wheel ALL=(ALL:ALL) ALL" > "$stage/etc/sudoers.d/wheel"
chmod 440 "$stage/etc/sudoers.d/wheel"
# root locked, like pmOS
sed -i 's|^root:[^:]*:|root:!:|' "$stage/etc/shadow"
# SSH keys from the host, like pmbootstrap's ssh_keys=True
mkdir -p "$stage/home/$user/.ssh"
cat "$HOME"/.ssh/*.pub > "$stage/home/$user/.ssh/authorized_keys" 2>/dev/null || true
chmod 700 "$stage/home/$user/.ssh"; chmod 600 "$stage/home/$user/.ssh/authorized_keys" 2>/dev/null || true
chown -R "$uid:$uid" "$stage/home/$user/.ssh" 2>/dev/null || true

# Kernel cmdline, machine id, fstab
: > "$stage/etc/machine-id"
cat > "$stage/etc/fstab" <<EOF
# root is mounted by the postmarketOS initramfs
LABEL=pmOS_root  /  ext4  defaults,noatime  0 1
EOF

# Mark the A/B slot successful. qbootctl is not in the Arch repos; take the
# binary from the pmOS package until it is.
extract_apk "qbootctl" usr/bin/qbootctl
if [ -x "$stage/usr/bin/qbootctl" ]; then
	cat > "$stage/etc/systemd/system/qbootctl.service" <<EOF
[Unit]
Description=Mark the current A/B slot as successfully booted
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/qbootctl -m

[Install]
WantedBy=multi-user.target
EOF
	ln -sf ../qbootctl.service "$stage/etc/systemd/system/multi-user.target.wants/qbootctl.service"
fi

# First boot: package installation over USB networking or WiFi.
pkgs="$(grep -vE '^\s*(#|$)' "$REPO/arch/packages.txt" | tr '\n' ' ')"
cat > "$stage/usr/local/bin/cupid-firstboot.sh" <<EOF
#!/bin/sh
# Runs once: initialise pacman, update, install the desktop packages.
set -e
pacman-key --init
pacman-key --populate archlinuxarm
pacman -Syu --noconfirm
pacman -S --noconfirm --needed $pkgs
systemctl enable NetworkManager bluetooth
systemctl disable cupid-firstboot.service
echo "cupid-firstboot: done" > /var/lib/cupid-firstboot.done
EOF
chmod 755 "$stage/usr/local/bin/cupid-firstboot.sh"
cat > "$stage/etc/systemd/system/cupid-firstboot.service" <<EOF
[Unit]
Description=cupid: first boot package installation
After=network-online.target
Wants=network-online.target
ConditionPathExists=!/var/lib/cupid-firstboot.done

[Service]
Type=oneshot
ExecStart=/usr/local/bin/cupid-firstboot.sh
StandardOutput=journal+console

[Install]
WantedBy=multi-user.target
EOF
ln -sf ../cupid-firstboot.service "$stage/etc/systemd/system/multi-user.target.wants/cupid-firstboot.service"

# If the host can run aarch64 binaries, install the packages now instead.
if command -v arch-chroot >/dev/null 2>&1 && command -v qemu-aarch64-static >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then
	echo "==> arch-chroot: installing packages at build time"
	arch-chroot "$stage" /usr/local/bin/cupid-firstboot.sh || echo "warning: package installation failed, firstboot will retry on the phone"
fi

# --- image ---------------------------------------------------------------------------
img="$AOUT/arch-cupid.img"
echo "==> creating $img ($SIZE, ext4, label pmOS_root, UUID $root_uuid)"
rm -f "$img"
truncate -s "$SIZE" "$img"
mkfs.ext4 -q -F -L pmOS_root -U "$root_uuid" -b 4096 -d "$stage" "$img"
rm -rf "$stage"
ls -l "$img"
cat <<EOF

Flash with the phone in fastboot (keep the postmarketOS boot.img):
  fastboot flash userdata $img
  fastboot reboot
Then: ssh $user@172.16.42.1  (password: the one given to the build)
The first boot installs packages from arch/packages.txt; it needs internet
on the phone (share the host's connection over usb0) and takes a while.
EOF
