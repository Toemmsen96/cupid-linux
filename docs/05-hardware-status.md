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
| Screen | broken | should work | works, flickers at 60 Hz | panel `l3_42_02_0a` (matches the bootloader's `msm_drm.dsi_display0`). Starts blanked: press power. Brightness writes while blanked failed and left DSI in HS mode: patch 0011, verified on pkgrel 1. The flicker remained (also on a static screen, with no frames sent, and with UBWC off): the driver ran the panel at 60 Hz, where the OLED's PWM dimming is visible; stock runs 120 Hz. Patch 0014 defaults to 120 Hz (pending) |
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
| Modem | broken | untested | up, no data | remoteproc up, QMI works, SIM selected. No data: SM8450 has IPA v5.1, which mainline lacks, so ModemManager "Failed to find a net port". Patches 0012/0013 backport the pending upstream support; pkgrel 1 failed to probe ("SMEM item 0", 6.13 still needs `smem_id` in the data), fixed in pkgrel 2 (pending). No VoLTE |
| FDE | broken | no | | touch is not in the initramfs (the driver needs its firmware there too), so unl0kr cannot take input |
| USB OTG | broken | untested | | `dr_mode = "otg"`, USB 2.0 only |
| Sensors | broken | no | | need the SLPI and a userspace sensor stack (hexagonrpc/libssc), not set up |
| Haptics | broken | no | | AW8697 on i2c16, no mainline driver |
| Fingerprint | | no | |
| zram swap | | | works | kernel had only the LZO backend, pmOS asks for zstd; zstd/lz4 backends enabled, verified on pkgrel 1 | Goodix, no mainline driver |

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
