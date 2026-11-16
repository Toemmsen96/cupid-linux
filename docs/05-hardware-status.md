# 05 Hardware status

"Wiki" is the postmarketOS wiki page for cupid as of November 2025 (the live
page sits behind a JavaScript challenge; this is from the Internet Archive).
"Expected" is what this repository's packages should give, based on what was
verified on the Xiaomi 12 Pro (zeus, same SoC, same bootloader generation,
port derived from cupid) and on the cupid-specific fixes applied here.
"Tested" is the first boot on a real cupid (2201123G, EEA, HyperOS 3 firmware)
on 2026-11-12 with the 6.13 kernel at pkgrel 0, phosh UI. "pending" marks a
fix that is in this repository but not yet booted.

| Component | Wiki | Expected | Tested | Notes |
|---|---|---|---|---|
| Flashing | works | works | works | fastboot, see [03-install.md](03-install.md); fastboot 37 needs the vbmeta fix in `flash.sh` |
| USB networking | works | works | works | 172.16.42.1, SSH with the pmbootstrap key |
| Internal storage | works | works | works | UFS |
| Battery | broken | should work | works | capacity, status, voltage, current. Xiaomi's firmware inserts BATT_CONSTANT_CURRENT at index 12, shifting temperature and all later battery properties by one: temperature read the 2 A charge current (20000 C), technology 114, and model_name/time_to_full replies had the wrong type and timed out. Patch 0020 translates the ids on xiaomi,cupid (verified on pkgrel 10) and flips the current sign (pkgrel 11); 0010 still caps genuinely unanswered properties |
| Charging | broken | USB-PD rates only | works (PD) | Xiaomi charger: 9 V USB-PD contract, 1.6 A input limit, ~2 A into the battery (~17 W), verified 2026-11-16. phosh showed "not charging" because the firmware reports the battery current negative while charging and upower 1.91 then forces "discharging"; 0020 negates it (verified with the rebuilt module). The 67/120 W modes need Xiaomi's adapter authentication (`verify_process`/`verify_digest` over the vendor `BC_XM_STATUS` 0x50/0x51 opcodes, the ADSP sends 0x50 notifications that mainline logs as unknown) and the vendor charge-pump handling; not done. On a PC the ADSP sees SDP with a 100 mA input limit until the USB gadget is configured |
| Screen | broken | should work | works, glitches | panel `l3_42_02_0a` (matches the bootloader's `msm_drm.dsi_display0`). Black during boot until the first power press (fixed in stable 0021 / next 0011, verified on 6.17 2026-11-16: the bootloader leaves the panel rails on, and after only a reset pulse the panel never leaves sleep, no TE on GPIO 86; one rail power cycle before the first init gives boot text and the greeter). 60 Hz flickered (OLED PWM): 0014 runs it at 120 Hz like stock, verified. Sporadic corruption on interaction (noise bands, shifted/duplicated content) at 60 and 120 Hz while phosh's own screenshot is clean. Not the DSI clock (0 DCS commands / 0 clock changes while glitching; 0015 is kept as a correct upstream fix). Measured on GPIO 86 via /dev/mem at 1 MHz: TE is a 50 % square wave toggling once per frame (rising edges 29.3 Hz, 34.39 ms; frame 17.2 ms = 58.2 Hz in 60 Hz mode). The DPU syncs on rising edges only, so it sees every other frame and free-runs (and assumes 60.0 Hz) in between; transfers then collide with scan-out of the compressed GRAM. At 120 Hz TE is a clean pulse (116.7 Hz); the 60 Hz square wave came from a missing stock timing-switch tail. Stock analysis: the DPU tear check self-triggers after 2*vtotal lines (only ~41 us margin at 120 Hz, every frame at 60 Hz; stock uses 0xfff0), and stock drives the panel with 10 bpc DSC (we sent an 8 bpc PPS). Tried on pkgrel 6 and reverted: tear check sync_cfg_height = 0xfff0 like stock (mainline then never starts a frame: "ctl start interrupt wait failed", confirmed by writing INTF1 TEAR_SYNC_CONFIG_HEIGHT back at runtime) and 10 bpc DSC like stock (static noise on 6.13's DSI host). 0018 keeps only the stock timing-switch tails (TE 116.7 -> 121.7 Hz at 120 Hz); glitches still open |
| Touchscreen | broken | should work | works | patches 0002/0003; PIN entry on the greeter works |
| 3D acceleration | works | works | works | Adreno 730, `a730_sqe`/`gmu_gen70000` load, phosh renders |
| Audio | broken | partial | card probes | headphone/codec-DMA path and USB-C audio; internal speakers (CS35L41 on tertiary TDM) do not work: the DSP never propagates a media format to the TDM sink, an audioreach gap |
| Camera | broken | no (6.13); ultra-wide on 6.17; ultra-wide + front on 7.3 | raw capture works (6.17, 7.3) | the 6.13 tree has no SM8450 CAMSS. On the 6.17 kernel (`next`) the OV13B10 ultra-wide streams 4208x3120 RAW10 through CSIPHY0/CSID0/VFE0 (test pattern and real image verified 2026-11-16). On 7.3 (`mainline`, pkgrel 3) the OV32B40 front camera also streams 3264x2448 RAW10 through CSIPHY3/CSID1/VFE1 (real image verified 2026-11-16), see [Cameras](#cameras). Main and macro sensors have no driver yet |
| Camera flash | works | works | | `pm8350c_flash` |
| IR TX | works | works | | `ir-spi-led` on spi13, `CONFIG_IR_SPI` |
| WiFi | works | works, stabilised | works | patches 0004/0005, PMU supplies, ASPM off, power save off |
| Bluetooth | works | works | controller up | needs an address: `bootmac` |
| GPS | untested | untested | | modem/GNSS over QMI once the modem runs |
| NFC | broken | no | driver loads | NXP SN100T on i2c9 0x28 (stock `qcom,sn-nci`), mainline `nxp-nci-i2c` (NCI 2.0), GPIOs irq 46 / ven 34 / fw 45 / clk-req 35 like the Nothing Phone (2); node enabled at 1 MHz. Userspace: neard (tags); no payments/card emulation |
| Modem | broken | untested | data works | Verified on pkgrel 6 (2026-11-13): LTE/5G NR on <carrier>, DNS, HTTP, 5 MB download in 6 s, no drops; IPA runtime suspend/resume works. The cause was 6.13's v5.0 GSI register table (`ERINDEX` vs `CH_ERINDEX`, every channel bound to event ring 0), fixed by upstream 56007972c0b1 in patch 0016 together with four related fixes; IPA v5.1 itself is the pending upstream series (0012/0013). APN must be set by hand (`nmcli connection add type gsm ifname '*' con-name 'Mobile data' apn internet` for <carrier>/<brand>). Calls/SMS/VoLTE untested |
| FDE | broken | no | | touch is not in the initramfs (the driver needs its firmware there too), so unl0kr cannot take input |
| USB OTG | broken | untested | | `dr_mode = "otg"`, USB 2.0 only |
| Sensors | broken | no | light only | SLPI boots; hexagonrpcd (firmware-xiaomi-cupid-hexagonfs: 61 configs + sns_reg.conf from the LineageOS blobs, byte-identical to stock; socinfo) serves the sensor PD, and cupid-sensor-registry copies this unit's 205-file registry read-only from persist at boot. The light sensor works; accelerometer, gyroscope and magnetometer answered once (after a late hexagonrpcd restart) but not reliably: the SLPI looks for `<registry>/../sns_reg_version`, which hexagonrpcd's virtual tree cannot provide, and keeps trying to write `temp.json` (hexagonrpcd is read-only). Moving the output one level deeper silences the version error but not the writes; the stock dsp/sdsp libraries are never requested. No SSC proximity (ultrasonic, audio DSP). Open |
| Haptics | broken | no | driver broken, node disabled | Awinic AW8697 on i2c16 0x5a (reset gpio89, irq gpio90). The driver in patch 0019 (written from the downstream one, untested before) buzzed once at boot, then its probe ran for ~9 minutes holding the device lock (journald blocked on its uevent, logind could not create sessions, SSH hung) and oopsed in input_ff_create(). The devicetree node is disabled until the driver is reworked; patch, firmware subpackage and feedbackd rule stay |
| Fingerprint | | no | not feasible | Goodix optical under-display sensor; its SPI bus belongs to TrustZone and capture/matching run in the QSEE app `gfcupid`, no Linux path |
| zram swap | | | works | kernel had only the LZO backend, pmOS asks for zstd; zstd/lz4 backends enabled, verified on pkgrel 1 | Goodix, no mainline driver |

## Linux 7.3 (`mainline` kernel package)

First booted 2026-11-16 (kernel 7.3.4), installed over the 6.17 rootfs with
`apk add`:

| Works | Not yet re-checked |
|---|---|
| boot with text, greeter, display at 120 Hz **without the sporadic corruption** (gone on 7.3), touch, battery, WiFi (pkgrel 2), Bluetooth, modem (ModemManager), IPA, sound card, DSPs, camera stack (CAMSS, CCI, PM8008, OV13B10 probe), front camera streaming (OV32B40, pkgrel 3) | mobile data, audio output, sensors, ultra-wide streaming, the battery current sign (reads negative while charging) |

WiFi needed an upstream fix (0027): the qcom PCIe driver read `iommu-map`
as 4-cell entries while sm8450.dtsi uses 5 (`#iommu-cells = <2>`), so the
WCN6855 got no BDF-to-SID entry. Its DMA still worked through the Root
Port's stream, so the firmware download completed on the chip (BHI status
SUCCESS, SBL running), but its MSIs reached the GIC ITS with the Root
Port's device ID and were dropped; ath11k gave up after 20 s ("MHI did not
load image over BHI"). The same parser is in 7.2. The devicetree also got
the WCN6855 details from the HDK: enable pins start low, swctrl and
xo-clk GPIOs, vddaon from pm8350_s11, S11/S12 at the stock minimums.

## Open issue: sporadic display corruption

Seen since the first boot, 60 and 120 Hz alike: when the picture changes
(tapping, scrolling, page transitions) parts of the screen briefly show
horizontal noise bands, content shifted or duplicated sideways, or doubled
lines. A phosh screenshot taken at the same moment is clean, so the damage
happens between the DPU and the panel (DSC command mode over DSI). Better since
pkgrel 7 (stock timing-switch tails, TE 121.7 Hz at 120 Hz), not gone.

Content-dependent (user observation, 2026-11-13): it shows up in Settings and
on buttons in the default GTK apps, never in the terminal. Flat areas,
gradients and rounded widgets glitch, plain text does not. That points at the
DSC data path rather than frame timing.

Measured / ruled out:
- not the DSI PLL: 0 DCS commands and 0 link-clock changes while glitching
  (0015, the upstream byte-clock rounding fix, is kept anyway);
- DSC RC parameters: the panel's own 0x91 values equal the kernel's;
- TE: GPIO 86 / mdp_vsync like stock, clean 1.9 % pulse at 120 Hz;
- the DPU 8.x vsync-source regression, the cmd-mode hdisplay / bits_per_pclk
  and INTF data_width fixes upstream: not applicable to this tree or mode;
- tear check `sync_cfg_height = 0xfff0` like stock: mainline never starts a
  frame ("ctl start interrupt wait failed");
- 10 bpc DSC like stock (`qcom,mdss-dsc-bit-per-component = <10>`, the panel's
  0x91 header 0xab): static noise on 6.13's DSI host.

Left to try:
- first, cheapest: make the panel's own DSC setup agree with our 8 bpc PPS.
  The init sends `0x91 ab 28 00 0c ...`; 0xab is "bpc 10 / line buffer 11" in
  PPS byte-3 encoding, while the kernel encodes 8 bpc (PPS byte 3 = 0x89).
  The RC values in the rest of 0x91 are identical for 8 and 10 bpc at this
  slice size, so changing only the first byte to 0x89 in
  panel-l3-42-02-0a-dsc.c tests whether the panel decodes part of the stream
  with its 10 bpc setting. A content-dependent mismatch would look exactly
  like this;
- whether a glitch disappears by itself after one refresh (frame collides with
  scan-out) or stays until the area is redrawn (bad data in the panel GRAM) —
  film it at 240 fps; this decides between the two directions below;
- 10 bpc again once the 2026 upstream DSI changes are backported (RGB101010
  support cebf747abeeb, bits_per_pclk 2d51cfb77daa, hdisplay ac47870fd795 and
  82159db4371f), keeping stock's 832 MHz link;
- D-PHY margin: mainline T_LPX (hs_rqst) is 4 against stock's 8, stock runs
  832 MHz with spread spectrum (we run ~796 MHz);
- the 0x07 compression-mode packet mainline sends after the PPS, which stock
  never sends;
- runtime experiments on INTF1 tear-check registers (base 0xae36000, only
  with the display on) to test start position / threshold changes without a
  rebuild.

## Cameras

From the stock devicetree (`qcom,cam-sensor0..3`) and the CamX sensor
modules in the vendor partition (`com.qti.sensormodule.cupid_*.bin`):

| Slot | Camera | Sensor | Bus | CSIPHY | MCLK (19.2 MHz) | Reset | Rails |
|---|---|---|---|---|---|---|---|
| sensor0 | rear main, OIS + AF + flash | Sony IMX766 (alt. modules IMX700/IMX707) | CCI0 bus 1 | 2 | MCLK2, gpio102 | gpio126 | DVDD gpio2, AVDD gpio70 (GPIO-switched), PM8008 L6/L7 for OIS/AF |
| sensor1 | front | OmniVision OV32B40 | CCI0 bus 0 | 3 | MCLK5, gpio105 | gpio127 | DVDD gpio93, AVDD gpio68 |
| sensor2 | rear ultra-wide | OmniVision OV13B10 | CCI0 bus 0 | 0 | MCLK1, gpio101 | gpio24 | PM8008 L2 (1.2 V) / L3 (2.8 V) |
| sensor3 | rear telemacro, AF | Samsung S5K5E9 | CCI1 bus 0 | 1 | MCLK3, gpio103 | gpio128 | PM8008 L1, AVDD gpio71 |

All four take I/O from PM8008 L5 (1.8 V). The PM8008 is the "j" instance
at I2C 0x0c on QUP SE5, reset on gpio11, no interrupt line; a second PM8008
("i", 0x08) feeds no camera. CSIPHY rails are pm8350 L5 (0.88 V) and L6
(1.2 V).

Mainline status: CAMSS for SM8450 is not upstream. The Galaxy Tab S8+ port
([aaronsb/sm-x800-linux](https://github.com/aaronsb/sm-x800-linux), same
SoC) streams raw Bayer from three sensors with a small CAMSS patch on top of
the CSID/VFE 680 support that X1E80100 brought (6.17 has it, 6.13 does not)
and a camcc fix without which every session after the first hangs the
TITAN GDSC. Only the OV13B10 has a mainline driver (ACPI-only; patch 0024
adds devicetree support). The OV32B40 has an out-of-tree driver from the
Xiaomi 14 Ultra port
([dianqk/nixos-android-devices](https://github.com/dianqk/nixos-android-devices),
`pkgs/linux-kernel/sm8650/aurora/ov32b40.patch`), carried unchanged as
mainline patch 0028. IMX766 and S5K5E9 have none; their register tables
are in the CamX modules. The IFE/IPE processing pipeline has
no mainline driver either, so the result is raw frames for libcamera's
software ISP.

Stage 1 in `linux-postmarketos-qcom-sm8450-cupid-next`, verified on the
phone 2026-11-16: CAMSS (0021/0022), the PM8008 with optional interrupt (0023),
CCI0 and the ultra-wide on CSIPHY0 at the OV13B10 default address 0x36. The
I2C addresses of the other sensors are still to be found (`i2cdetect` on
the CCI buses).

Needed on the phone beyond the Tab S8 patches: camcc enabled with MXC next
to MMCX (the fork's dtsi has it disabled; MMCX alone leaves TITAN_TOP
stuck off), `.link_entities` in the SM8450 resources (6.17 calls it
unconditionally) and PM8008 L5 always on (it is the CCI pull-up rail; with
it switched off between sessions the first CCI transfer after power-up
timed out and every stream after the first failed).

Capture by hand (v4l-utils):

```sh
M="media-ctl -d /dev/media0"; F="fmt:SGRBG10_1X10/4208x3120"
$M -r
$M -l '"msm_csiphy0":1->"msm_csid0":0[1]'
$M -l '"msm_csid0":1->"msm_vfe0_rdi0":0[1]'
for p in '"ov13b10 4-0036":0' '"msm_csiphy0":0' '"msm_csiphy0":1' \
         '"msm_csid0":0' '"msm_csid0":1' '"msm_vfe0_rdi0":0' '"msm_vfe0_rdi0":1'; do
	$M -V "$p[$F]"
done
v4l2-ctl -d /dev/video0 --set-fmt-video=width=4208,height=3120,pixelformat=pgAA
v4l2-ctl -d /dev/video0 --stream-mmap=4 --stream-count=3 --stream-to=/tmp/uw.raw
```

Frames are packed RAW10 (GRBG), 5264 bytes per line. The sensor is mounted
rotated by 90 degrees.

### Front camera (7.3)

The OV32B40 sits at 0x10 on CCI0 bus 0 (the stock module's slave address
0x20 is the 8-bit form). The devicetree (`mainline` package) adds the two
GPIO-switched rails as fixed regulators (DVDD 1.1 V on gpio93 from
pm8350_s12, AVDD 2.8 V on gpio68 from BOB), MCLK5 on gpio105, reset on
gpio127 and CSIPHY3 with four data lanes at 842.4 MHz, the link frequency
of the driver's 3264x2448 mode. Verified 2026-11-16: chip ID read, frames
of a real scene. WirePlumber/libcamera opens the media device at login;
stop it (`systemctl --user stop wireplumber`) before capturing by hand:

```sh
M="media-ctl -d /dev/media0"; F="fmt:SBGGR10_1X10/3264x2448"
$M -r
$M -l '"msm_csiphy3":1->"msm_csid1":0[1]'
$M -l '"msm_csid1":1->"msm_vfe1_rdi0":0[1]'
for p in '"ov32b40 4-0010":0' '"msm_csiphy3":0' '"msm_csiphy3":1' \
         '"msm_csid1":0' '"msm_csid1":1' '"msm_vfe1_rdi0":0' '"msm_vfe1_rdi0":1'; do
	$M -V "$p[$F]"
done
v4l2-ctl -d /dev/video3 --set-fmt-video=width=3264,height=2448,pixelformat=pBAA
v4l2-ctl -d /dev/video3 --stream-mmap=4 --stream-count=3 --stream-to=/tmp/front.raw
```

Frames are packed RAW10 (BGGR), 4080 bytes per line; the sensor is mounted
rotated by 270 degrees.

## Kernel patches carried

From the zeus port, all SM8450-generic:

| Patch | Purpose |
|---|---|
| 0002 fts single full-duplex transfer | the driver reads as TX-only + RX-only transfers, which GENI does not reproduce; one full-duplex transfer at 12 MHz |
| 0003 fts palm rejection and panel follower | parses `fts,support-super-resolution` (never assigned before, so coordinates were decoded as low-res), drops palm contacts, optional panel follower |
| 0004 pcie-qcom retry link training | PERST and retry when the link is down because the endpoint was unpowered during the first training |
| 0005 ath11k reset on WMI wedge | queue a firmware reset after five WMI timeouts instead of hanging a workqueue |
| 0006 q6apm poll for SPF readiness | like the downstream driver |
| 0007 pdr ack service-up before notifying | avoids the servreg ack deadlock |
| 0008 apr install GPR callback before probe | q6apm's first reply was dropped; `CMD timeout for [1001021]` gone |
| 0009 libbpf const-correct strstr/strchr results (ours) | lets `resolve_btfids` build on hosts whose libc has C23 const string prototypes (glibc 2.40+, gcc 15, clang 23); needed for the BTF the pmOS kconfig check requires |
| 0010 battmgr stop requesting unanswered properties (ours) | after 3 consecutive timeouts a battery property returns `-ENODATA` without asking the ADSP |
| 0011 panel l3-42-02-0a brightness (ours) | keep the level while the panel is off and apply it on enable; always restore `MIPI_DSI_MODE_LPM`; drop the DCS read-back that always failed |
| 0012 IPA v5.1 (backport) | Esteban Urrutia's pending "SM8450 IPA support" v2 2/3 plus its `IPA_MEM_MODEM_STATS_DROP` dependency, rebased onto 6.13 (no IPA v5.2 there) |
| 0014 panel l3-42-02-0a refresh rate (ours) | `refresh_rate` module parameter, 60/90/120 Hz (default 120) with the stock per-rate commands (DCS 0x2f 01/03/02 plus the 90/120 Hz extras); the mode clock follows |
| 0015 msm/dsi byte clock rounding (backport) | upstream 6cd33b6f4155 + 2028280686f4: round the 6G byte clock to the PLL-achievable rate so DCS commands no longer re-lock the PLL (not the cause of the screen glitches, see above) |
| 0018 panel l3-42-02-0a (ours) | stock timing-switch tails for 60/120 Hz (60 Hz ran at ~29 Hz without) |
| 0019 Awinic AW8697 haptics driver (ours) | written from Xiaomi's downstream driver: RAM waveform library, f0 calibration, battery-voltage gain compensation, FF_RUMBLE input device |
| 0020 battmgr Xiaomi property ids (ours) | translate battery property ids >= BATT_TEMP for Xiaomi's extra BATT_CONSTANT_CURRENT; report the battery current positive while charging (the firmware uses Android's sign) |
| 0016 IPA v5.x GSI fixes (backport) | upstream 56007972c0b1 (event ring index never programmed on v5.0+), 9709b56d908a, 1335b903cf2e, de08f9585692, 3cbfd627ee72 |
| 0013 sm8450 IPA node (backport) | v2 3/3: disabled `ipa` node and IMEM `modem-tables`; cupid enables it with `qcom,gsi-loader = "self"` and `ipa_fws.mbn` |

Dropped on purpose (zeus numbering): 0001 (PM8008 interrupt, zeus-only),
0009/0010/0011/0012/0013/0014/0015 (speaker experiments that did not produce sound, and the two
backports that only apply on top of them), 0016/0017 (GPR debug
infrastructure).

## Devicetree changes versus the fork

- `qcom,msm-id`, `qcom,board-id` from the stock cupid devicetree.
- `wcn6855-pmu`: `vddpmumx-supply`, `vddpmucx-supply`.
- `&pcie0`: `max-link-speed = <2>`.
- `regulator-always-on`/`boot-on` on `pm8350_s10/s11/s12`, `pm8350c_s1`,
  `pmr735a_s2` (WCN6855) and `pm8350c_l2`/`l7` (touch).
- touchscreen: `fts,irq-flags = <0x2008>`; the 6.17 variant also gets the
  whole node back (the rebase dropped it).
- `&sound`: `audio-routing` from sm8450-hdk minus the WSA routes.
- CPU thermal zones: 85 C passive trips with cpufreq cooling maps.
- `&ipa`: enabled, `qcom,gsi-loader = "self"`, `memory-region = <&ipa_fw_mem>`,
  `firmware-name = "qcom/sm8450/cupid/ipa_fws.mbn"` (stock: pas-id 15, same
  0x8b900000 region).
