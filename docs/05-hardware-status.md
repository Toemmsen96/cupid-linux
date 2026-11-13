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
| Battery | broken | should work | works | capacity, status, voltage. The firmware never answers `model_name`/`time_to_full_avg`; each read blocked 1 s and logged `-110` (~70/min). Patch 0010 stops asking: verified on pkgrel 1, 6 timeouts then silence |
| Charging | broken | USB-PD rates only | the 120 W charge pumps are vendor-specific |
| Screen | broken | should work | works, glitches | panel `l3_42_02_0a` (matches the bootloader's `msm_drm.dsi_display0`). Starts blanked: press power. 60 Hz flickered (OLED PWM): 0014 runs it at 120 Hz like stock, verified. Sporadic corruption on interaction (noise bands, shifted/duplicated content) at 60 and 120 Hz while phosh's own screenshot is clean. Not the DSI clock (0 DCS commands / 0 clock changes while glitching; 0015 is kept as a correct upstream fix). Measured on GPIO 86 via /dev/mem at 1 MHz: TE is a 50 % square wave toggling once per frame (rising edges 29.3 Hz, 34.39 ms; frame 17.2 ms = 58.2 Hz in 60 Hz mode). The DPU syncs on rising edges only, so it sees every other frame and free-runs (and assumes 60.0 Hz) in between; transfers then collide with scan-out of the compressed GRAM. At 120 Hz TE is a clean pulse (116.7 Hz); the 60 Hz square wave came from a missing stock timing-switch tail. Stock analysis: the DPU tear check self-triggers after 2*vtotal lines (only ~41 us margin at 120 Hz, every frame at 60 Hz; stock uses 0xfff0), and stock drives the panel with 10 bpc DSC (we sent an 8 bpc PPS). Tried on pkgrel 6 and reverted: tear check sync_cfg_height = 0xfff0 like stock (mainline then never starts a frame: "ctl start interrupt wait failed", confirmed by writing INTF1 TEAR_SYNC_CONFIG_HEIGHT back at runtime) and 10 bpc DSC like stock (static noise on 6.13's DSI host). 0018 keeps only the stock timing-switch tails (TE 116.7 -> 121.7 Hz at 120 Hz); glitches still open |
| Touchscreen | broken | should work | works | patches 0002/0003; PIN entry on the greeter works |
| 3D acceleration | works | works | works | Adreno 730, `a730_sqe`/`gmu_gen70000` load, phosh renders |
| Audio | broken | partial | card probes | headphone/codec-DMA path and USB-C audio; internal speakers (CS35L41 on tertiary TDM) do not work: the DSP never propagates a media format to the TDM sink, an audioreach gap |
| Camera | broken | no | | no SM8450 CAMSS on mainline |
| Camera flash | works | works | | `pm8350c_flash` |
| IR TX | works | works | | `ir-spi-led` on spi13, `CONFIG_IR_SPI` |
| WiFi | works | works, stabilised | works | patches 0004/0005, PMU supplies, ASPM off, power save off |
| Bluetooth | works | works | controller up | needs an address: `bootmac` |
| GPS | untested | untested | | modem/GNSS over QMI once the modem runs |
| NFC | broken | no | | NXP NCI on i2c9, nodes commented out in the devicetree |
| Modem | broken | untested | data works | Verified on pkgrel 6 (2026-11-13): LTE/5G NR on Sunrise, DNS, HTTP, 5 MB download in 6 s, no drops; IPA runtime suspend/resume works. The cause was 6.13's v5.0 GSI register table (`ERINDEX` vs `CH_ERINDEX`, every channel bound to event ring 0), fixed by upstream 56007972c0b1 in patch 0016 together with four related fixes; IPA v5.1 itself is the pending upstream series (0012/0013). APN must be set by hand (`nmcli connection add type gsm ifname '*' con-name 'Mobile data' apn internet` for Sunrise/yallo). Calls/SMS/VoLTE untested |
| FDE | broken | no | | touch is not in the initramfs (the driver needs its firmware there too), so unl0kr cannot take input |
| USB OTG | broken | untested | | `dr_mode = "otg"`, USB 2.0 only |
| Sensors | broken | no | | need the SLPI and a userspace sensor stack (hexagonrpc/libssc), not set up |
| Haptics | broken | no | | AW8697 on i2c16, no mainline driver |
| Fingerprint | | no | |
| zram swap | | | works | kernel had only the LZO backend, pmOS asks for zstd; zstd/lz4 backends enabled, verified on pkgrel 1 | Goodix, no mainline driver |

## Open issue: sporadic display corruption

Seen since the first boot, 60 and 120 Hz alike: when the picture changes
(tapping, scrolling, page transitions) parts of the screen briefly show
horizontal noise bands, content shifted or duplicated sideways, or doubled
lines. A phosh screenshot taken at the same moment is clean, so the damage
happens between the DPU and the panel (DSC command mode over DSI). Better since
pkgrel 7 (stock timing-switch tails, TE 121.7 Hz at 120 Hz), not gone.

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
