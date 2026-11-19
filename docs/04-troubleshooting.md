# 04 Troubleshooting

Work through these in order. The phone is silent while ABL rejects an image,
so the first question is always whether the kernel ran at all.

## It comes back to fastboot, or reboots in a loop

1. In fastboot, immediately: `fastboot getvar slot-retry-count:a` (use the
   slot you flashed).
   - Still at its maximum (6 or 7): ABL rejected the image. Check that vbmeta
     is flashed to both slots, that `dtbo` and `vendor_boot` are erased, and
     that the devicetree has `qcom,msm-id` and `qcom,board-id` (`fdtget
     out/*.dtb / qcom,board-id`).
   - Decremented once per attempt: the kernel started and died. Several
     decrements within seconds mean it dies early.
2. Back in fastboot "by itself" after a number of successful boots: the slot is
   never marked successful. `rc-status`/`systemctl status qbootctl` on the
   phone; `soc-qcom-qbootctl` must be installed and enabled.
3. Back in fastboot right after a `scripts/flash.sh kernel`: the new
   `boot.img` names a different root UUID than the installed rootfs. Flash
   both (`scripts/flash.sh`).

Serial console is the only early-boot channel: UART pads are on the board
(1.8 V, see the wiki page), `console=ttyMSM0,115200n8 earlycon` in
`deviceinfo_kernel_cmdline`. ramoops does not survive a reset on this platform
(XBL scrubs DRAM).

## Console instead of the login screen

`systemctl status greetd` shows `start-limit-hit`, and
`journalctl -b _UID=110 | grep phrog` shows `Settings schema 'sm.puri.phosh'
is not installed` before an abort. The phrog greeter links `libphosh`; phosh
0.59 renamed its schemas to `mobi.phosh`, so upgrading only `phosh` (and
`phosh-schemas`) leaves phrog on the old `libphosh`. Upgrade them together
(`apk upgrade`, or `apk add -u libphosh`), then
`systemctl reset-failed greetd && systemctl restart greetd`.

## Crashes under memory load

The phone reboots while something uses a lot of memory or writes large
files (unpacking archives, downloads, running an LLM), and
`journalctl -b -1 -k | grep -A3 "external abort"` shows
`Internal error: synchronous external abort` in `clear_page`, `copy_page`
or `__arch_copy_from_user`. Linux handed out a page that the secure world
no longer lets it touch. Up to kernel r22 this was the ADSP remote heap
(0xff800000, 8 MiB): it was a reusable CMA pool, and fastrpc assigns it to
the DSP; r23 declares it `no-map`. To place a new fault, translate the
faulting linear-map address (`x0` in `clear_page`) to a physical one:
physical = address - 0xffff000000000000 + 0x80000000 (no linear-map
randomisation on this phone), then compare with
`dmesg | grep "reserved mem"`. Any region that firmware or a driver hands
to a remote processor (`qcom,vmids`, `qcom_scm_assign_mem`) must be
`no-map`, never `reusable`.

## Black screen

Not necessarily a failure. Wait a minute, then `ssh <user>@172.16.42.1`.

- First check the obvious: the greeter starts with the panel blanked. Press
  the power button once (seen on the first cupid boot). The first login after
  that can scroll console text for up to a minute before phosh appears.
- SSH refuses with "REMOTE HOST IDENTIFICATION HAS CHANGED": another pmOS
  device used 172.16.42.1 before. `ssh-keygen -R 172.16.42.1`.
- SSH works: check `dmesg | grep -iE 'panel|dsi|msm'`. The panel driver is
  the module `panel-l3-42-02-0a-dsc`; `/sys/class/drm/card*-DSI-1/status`
  should read `connected`. A dark panel with the system up is usually a rail
  (wrong regulator looks like a broken driver), then the DSI mode flags: if
  `failed wait_for_idle -110` or frame-done timeouts appear, the driver's
  `MIPI_DSI_MODE_VIDEO_BURST` is wrong for this command-mode panel (the
  Xiaomi 12 Pro had to drop it).
- No SSH, but the USB network interface appears on the host: the initramfs is
  waiting or stuck. `telnet 172.16.42.1 23` gives the initramfs debug shell
  when it failed to find the root partition ("failed to mount subpartitions").
  Check `blkid` there: `userdata` must show `LABEL="pmOS_root"`.
- Nothing on USB: the kernel did not get as far as the initramfs. See above.

## Screen flickers, or a different refresh rate

The panel runs at 120 Hz by default (patch 0014). 60 Hz flickers visibly
(OLED PWM dimming); 90 Hz is in between. To change it, add
`panel_l3_42_02_0a_dsc.refresh_rate=60` (or `90`) to
`deviceinfo_kernel_cmdline` and rebuild, or for a quick test boot with it via
`fastboot boot`. `cat /sys/module/panel_l3_42_02_0a_dsc/parameters/refresh_rate`
shows the active value; `vrefresh` in
`/sys/kernel/debug/dri/0/state` (root) must match it.

## Touch does not work

`dmesg | grep -i fts`:

- `Failed to init pinctrl`: the `mi_ts_active`/`mi_ts_suspend` states are
  missing (devicetree).
- `Threaded irq requested with handler=NULL and !ONESHOT`: `fts,irq-flags`
  must be `0x2008`.
- `chip_id0:0x0,chip_id1:0x0` / `read chip error`: SPI reads return zeros.
  Patch 0002 (single full-duplex transfer) is missing from the kernel, or the
  rails are off: `cat /sys/kernel/debug/regulator/regulator_summary | grep -E
  'pm8350c_l2|pm8350c_l7'`.
- `Cannot execute fw upgrade`: `/lib/firmware/st_fts_l3.ftb` missing
  (`firmware-xiaomi-cupid-touchscreen`).
- No messages at all: the module is not loaded. `modprobe fts_touch_spi`;
  `/etc/modules-load.d/cupid.conf` should contain it.
- Touches land in the wrong place: patch 0003 missing or
  `fts,support-super-resolution = <1>` missing. The driver logs `super
  resolution: 1` when it is on.
- Touch stops after the screen blanks: known. The driver gates reports on a
  resume bit nothing on mainline sets; the panel-follower hook in patch 0003
  exists but is not wired in the devicetree because it broke touch entirely
  on zeus.

## WiFi

- No `wlan0`: `dmesg | grep -E 'qcom-pcie|ath11k'`. Expect `PCIe Gen.2 x1
  link up` within a second. Without it the WCN6855 did not get PERST while
  powered: patch 0004 missing, or the WCN rails are not always-on.
- Link drops under load, scans time out (-110), `MHI BHI offset 0xffffffff`:
  ASPM L1 is on. `cat /sys/module/pcie_aspm/parameters/policy` must be
  `performance` (kernel cmdline), and NetworkManager's `wifi.powersave = 2`.
- MAC is an Atheros default (`00:03:7f:...`): expected; the vendor
  calibration and MAC are not used. NetworkManager randomises it anyway.
- Slow WiFi, 5 GHz networks 40-60 dB weaker than 2.4 GHz from the same
  router: the generic linux-firmware board file is in use. Use the stock
  firmware and board file from `modem_b`, see "WiFi speed" in
  [05-hardware-status](05-hardware-status.md#wifi-speed-73).
- With the stock firmware a 5 GHz network associates but gets no DHCP
  lease, `iw dev wlan0 station dump` shows most `tx failed`: the firmware
  runs with its default country (US) on a DFS channel. Set the real one
  with `iw reg set XX` (kernel r22 or later) and check that `iw reg get`
  shows it under `phy#0 (self-managed)`.
- A different IP address on the 5 GHz network than on 2.4 GHz is normal:
  NetworkManager uses a different random MAC per network.

## Bluetooth

`bluetoothctl show` says "No default controller": the controller is
unconfigured because the devicetree carries no `local-bd-address`. `bootmac`
(pulled in by `soc-qcom`) sets one at boot; check its service. As a fallback,
add `local-bd-address = [ xx xx xx xx xx xx ];` (little-endian) to the
`bluetooth` node under `&uart20` and rebuild the kernel.

## Audio

- No card: `dmesg | grep -E 'sndcard|q6apm|gpr'`. `CMD timeout for
  [1001021]` means the ADSP patches (0006-0008) are missing. `-2` while
  loading `qcom/sm8450/Xiaomi-12-tplg.bin` means the topology symlink is
  missing.
- Card exists, only "Dummy Output": the UCM profile is not found. It must be
  at `/usr/share/alsa/ucm2/conf.d/sm8450/Xiaomi-12.conf`.
- Internal speakers silent: they need the 7.3 kernel (`mainline`, pkgrel
  7+) and device pkgrel 8+ (topology and UCM), see
  [05-hardware-status.md](05-hardware-status.md#speakers-73). Without a user
  logged in on the screen PipeWire has no access to the card. USB-C audio and the
  headphone path work.
- Speakers loud, harsh and deaf to the volume (a square wave of the
  signal): kernel older than r16 or device package older than r18 (wrong
  TDM lane / frame-sync polarity), see
  [05-hardware-status.md](05-hardware-status.md#speakers-73).
- No sound in calls: call audio (modem voice through the DSP) is still
  being brought up, see [09-call-audio.md](09-call-audio.md). Check that
  `/lib/firmware/updates/qcom/sm8450/Xiaomi-12-voice.bin` exists
  (`journalctl -u cupid-voice-firmware`: it needs the stock `vendor`
  partition, i.e. a phone whose super partition was not wiped), that the
  card switches to the "Voice Call" profile during the call
  (`pactl list cards | grep 'Active Profile'`) and that the kernel logs
  "voice call graphs started". Speakerphone is not supported yet.

## Remoteprocs, battery, modem

`cat /sys/class/remoteproc/remoteproc*/state` and `/sys/class/remoteproc/*/name`
should show adsp, cdsp, slpi (and mpss) running. Battery readings come from
the ADSP (`qcom-battmgr`), so without adsp there is no battery. The modem
needs `rmtfs` (`soc-qcom-modem`) before `mpss` will stay up; `qmicli` and
ModemManager are then the next steps.

Do not stop the ADSP (`echo stop > /sys/class/remoteproc/remoteproc1/state`)
on 7.3: the phone hangs hard and resets a few seconds later, with nothing in
the log.

- Calls stay in "dialing" or incoming calls go to voicemail: no carrier
  configuration is active, so the modem has no VoLTE.
  `journalctl -u cupid-modem-config` shows what the service did; it needs
  the SIM to be known to ModemManager, and picks the configuration whose
  trailer lists the SIM's network code (and card number prefix). To force
  one, or when none matches: put the MBN path below `modem_pr/mcfg/configs/mcfg_sw/generic` (e.g.
  `EU/Vodafone/...`) into `/etc/cupid-modem-config`, then
  `systemctl restart cupid-modem-config`.
- Modem keeps crashing at boot (`DOG detects stalled initialization` in
  `dmesg`) and ModemManager then reports the SIM missing: a carrier
  configuration was still active at power-on (unclean shutdown). The modem
  recovers after three resets; `systemctl restart ModemManager` brings the
  SIM back, `cupid-modem-config` then activates the configuration again.
- GPS does not start (`Couldn't start GPS engine ... GeneralError`): the
  ModemManager overlay from `pmaports/temp/modemmanager` is not installed
  (`apk info -v modemmanager` should show `-r100`).
- SMS that arrived while the phone was at the login screen are missing in
  Chatty: before device r17 the greeter session's Chatty took them; they
  are in `/var/lib/greetd/.purple/chatty/db/chatty-history.db`. r17 keeps
  Chatty out of the greeter (`ConditionUser=!greetd` drop-in), so SMS wait
  on the modem until the user's Chatty starts after login.

## Shows "not charging" on a charger

Fixed in kernel pkgrel 11 (patch 0020). Older kernels report the battery
current with the firmware's sign, negative while charging, and upower then
shows "discharging" although the battery charges (check
`/sys/class/power_supply/qcom-battmgr-bat/status` and `capacity`). On a PC
port the ADSP sees a plain USB port and limits the input to 100 mA until the
USB gadget is configured, which is barely more than the phone uses.

## Phone runs warm

Measure first: `/proc/interrupts` twice, 10 s apart. Measured on 2026-11-16
(screen off, on a charger): ~1500 wakeups/s, about 1000 of them from audio.
Phosh Mobile Settings keeps two 25 Hz level meters open while it runs (even
in the background), so the microphone records continuously and the ADSP runs
an AudioReach graph (~120 GPR messages/s). Close the app; `pactl list short
sources` should then show the sources SUSPENDED. Other known costs: WiFi
power save is off on purpose (see WiFi above), and charging at ~2 A heats
the battery to ~38 C. Suspend on idle only happens on battery after 15
minutes (GNOME default) and has not been verified on this kernel yet; an
open SSH session blocks it.
