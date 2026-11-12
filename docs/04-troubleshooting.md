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
- Internal speakers silent: expected, see
  [05-hardware-status.md](05-hardware-status.md). USB-C audio and the
  headphone path work.

## Remoteprocs, battery, modem

`cat /sys/class/remoteproc/remoteproc*/state` and `/sys/class/remoteproc/*/name`
should show adsp, cdsp, slpi (and mpss) running. Battery readings come from
the ADSP (`qcom-battmgr`), so without adsp there is no battery. The modem
needs `rmtfs` (`soc-qcom-modem`) before `mpss` will stay up; `qmicli` and
ModemManager are then the next steps. None of this has been verified on cupid.
