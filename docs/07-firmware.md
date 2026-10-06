# 07 Firmware

All of it is proprietary and comes from Xiaomi's ROM. Nothing is committed to
this repository; the package fetches pinned files at build time.

| Files | From | Installed to |
|---|---|---|
| `adsp.mbn`, `cdsp.mbn`, `slpi.mbn`, `modem.mbn` + `modem_pr/`, `ipa_fws.mbn` and the `.jsn` metadata | [sm8450-mainline/firmware-xiaomi-cupid](https://github.com/sm8450-mainline/firmware-xiaomi-cupid) at `5da2787e` | `/lib/firmware/qcom/sm8450/cupid/` |
| `a730_sqe.fw`, `a730_zap.mbn`, `gmu_gen70000.bin` | same | `/lib/firmware/qcom/` and the initramfs |
| `st_fts_l3.ftb`, `st_fts_l3_thp.ftb`, `stm_fts_production_limits.csv` | [TheMuppets/proprietary_vendor_xiaomi_cupid](https://github.com/TheMuppets/proprietary_vendor_xiaomi_cupid) `lineage-22.2` at `ba672d8f` | `/lib/firmware/` (bare names, as the driver requests them) |
| WCN6855 WiFi (`ath11k/WCN6855/hw2.0/`) | `linux-firmware-ath11k` | |
| WCN6855 Bluetooth (`qca/hpbtfw21.tlv`, `qca/hpnv21.bin`) | `linux-firmware-qca` | the sm8450-mainline repository also carries Xiaomi's `bluetooth/` blobs; not used, the generic ones work |
| ADSP audio topology | `linux-firmware-qcom` (`SM8450-HDK-tplg.bin`) | symlinked as `qcom/sm8450/Xiaomi-12-tplg.bin` |

The upstream pmaports package pulls the first group from git.mainlining.org,
which returns 502. GitHub's archive of the same repository was verified to
contain the real `modem.mbn` (108 MB ELF) although the repository stores it in
LFS; the sha512 in the APKBUILD pins it.

## Extracting your own

To get files from your own phone instead (root required) or to verify the
packaged ones: `scripts/dump-stock.sh` pulls the touch and GPU firmware from
`/vendor/firmware/`. The remoteproc firmware lives split in
`/vendor/firmware_mnt/image/<name>.mdt` + `.b00..bNN`; merge with
`pil-squasher` into one `.mbn`. From a fastboot ROM, extract `vendor.img`
(EROFS, `fsck.erofs --extract`) and the `modem` image (vfat).

Keep the repository free of these blobs. If you need a local override, build
a `firmware-xiaomi-cupid` with a local tarball in `source=` and do not commit
it.
