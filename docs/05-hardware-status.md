# 05 Hardware status

"Wiki" is the postmarketOS wiki page for cupid as of November 2025 (the live
page sits behind a JavaScript challenge; this is from the Internet Archive).
"Expected" is what this repository's packages should give, based on what was
verified on the Xiaomi 12 Pro (zeus, same SoC, same bootloader generation,
port derived from cupid) and on the cupid-specific fixes applied here.
Nothing has been booted on a cupid from this repository yet; update this
table after the first flash.

| Component | Wiki | Expected | Notes |
|---|---|---|---|
| Flashing | works | works | fastboot, see [03-install.md](03-install.md) |
| USB networking | works | works | 172.16.42.1 |
| Internal storage | works | works | UFS |
| Battery | broken | should work | `qcom-battmgr` over pmic-glink, needs the ADSP running |
| Charging | broken | USB-PD rates only | the 120 W charge pumps are vendor-specific |
| Screen | broken | should work | panel driver `panel-l3-42-02-0a-dsc` in the fork; zeus assumed it works on cupid; if `wait_for_idle -110` shows up, drop `MIPI_DSI_MODE_VIDEO_BURST` |
| Touchscreen | broken | should work | patches 0002/0003, irq flags, rails, firmware, module load |
| 3D acceleration | works | works | Adreno 730, zap firmware in the initramfs |
| Audio | broken | partial | headphone/codec-DMA path and USB-C audio; internal speakers (CS35L41 on tertiary TDM) do not work: the DSP never propagates a media format to the TDM sink, an audioreach gap |
| Camera | broken | no | no SM8450 CAMSS on mainline |
| Camera flash | works | works | `pm8350c_flash` |
| IR TX | works | works | `ir-spi-led` on spi13, `CONFIG_IR_SPI` |
| WiFi | works | works, stabilised | patches 0004/0005, PMU supplies, ASPM off, power save off |
| Bluetooth | works | works | needs an address: `bootmac` |
| GPS | untested | untested | modem/GNSS over QMI once the modem runs |
| NFC | broken | no | NXP NCI on i2c9, nodes commented out in the devicetree |
| Modem | broken | untested | firmware, `rmtfs_mem`, `soc-qcom-modem` in place; data only if it works, no VoLTE |
| FDE | broken | no | touch is not in the initramfs (the driver needs its firmware there too), so unl0kr cannot take input |
| USB OTG | broken | untested | `dr_mode = "otg"`, USB 2.0 only |
| Sensors | broken | no | need the SLPI and a userspace sensor stack (hexagonrpc/libssc), not set up |
| Haptics | broken | no | AW8697 on i2c16, no mainline driver |
| Fingerprint | | no | Goodix, no mainline driver |

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

Dropped on purpose: 0001 (PM8008 interrupt, zeus-only), 0009/0010/0011/0012/
0013/0014/0015 (speaker experiments that did not produce sound, and the two
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
