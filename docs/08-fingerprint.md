# 08 Fingerprint

Verdict: **feasible with big effort.** Direct sensor access from Linux stays
impossible (the SPI pins/QUP SEs are TrustZone-owned; capture and matching
are proprietary code in Xiaomi's `gfcupid` trusted app). The route is to load
and drive the stock `gfcupid` TA from Linux through QTEE (upstream
`drivers/tee/qcomtee`) and replace the Android HAL in userspace.

## Evidence

- TZ supports smcinvoke: at boot `qcom_scm` registered the `qcomtee` platform
  device (`/sys/bus/platform/devices/qcomtee` on the phone). Only
  `CONFIG_QCOMTEE` is missing (unset in the mainline config); no DT change.
- `qcom_qseecom` (mainline) is useless here: lookup/send only for firmware-
  preloaded apps, no app loading, no listeners, no buffer patching; dmesg:
  `qseecom: found qseecom with version 0x1402000`, `untested machine, skipping`.
- SHM bridge active (SM8450 not in `qcom_tzmem_blacklist`).
- Open userspace: quic-teec (`libqcomtee`) and Qualcomm minkipc
  (`qtee_supplicant` with FS 0xa, GPFS 0x7000, RPMB 0x2000, time 0xb
  listeners; `smcinvoke_client`: `IClientEnv_open(CAppLoader_UID=3)` ->
  `IAppLoader_loadFromBuffer(elf)` -> `IAppController_getAppObject` ->
  legacy `handleRequest`).

## Hardware (stock DT)

- Node `fingerprint_goodix` (`goodix,fingerprint`, dts line 35085), no SPI
  child on the Linux side. Reset GPIO41, IRQ GPIO40 (Linux-owned, unclaimed).
  Power L11C (pm8350c_l11) 3.2 V always-on (already so in the port).
- TLMM `qcom,gpios-reserved = <28 29 30 31 36 37 38 39>` = QUP SE8/SE10,
  disabled in stock DT; port already reserves them. devcfg has
  `fingerprint_qsee_spidev_id/speed` (one of SE8/SE10; the other is the eSE)
  and the QUP wrapper clocks: TZ drives SPI and its clocks.
- Optical: panel local HBM (`mi,local-hbm-enabled`), DCS sequences in stock
  DT for l3_42_02_0a (`mi,mdss-dsi-local-hbm-normal-white-1000nit-command`,
  `...-off-to-normal-command`, `mi,mdss-dsi-hbm-fod-on/off-command`,
  ~lines 29765-29900). FOD area x=433 y=2056 214x214 (getprop
  `persist.vendor.sys.fp.fod.location.X_Y`, touch `fts,fod-*`).

## Stock software

- `mfp-daemon` -> `fingerprint.goodix_fod.so` -> `libgf_hal.so` ->
  `libQSEEComAPI.so` -> `/dev/qseecom` (legacy QSEECom).
- `goodix_fod.ko`: regulator, reset GPIO, IRQ via netlink only (replaceable
  with libgpiod).
- `CaEntry::startTap` @0x2d060: `QSEECom_start_app(h,
  "/vendor/firmware_mnt/image", "gfcupid", 0x1000)`; then an HMAC key from
  keymaster (cmd {0x205, 2}) sent in a 0x11c-byte command (only signs Android
  auth tokens; a random key works on Linux).
- TA: `non-hlos/image/gfcupid.mdt` + `.b00`-`.b08` (AArch64, needs
  `libcmnlib.so`, which UEFI loads: `qcom,commonlib64-loaded-by-uefi`).
  `smplap64` (sample legacy app) in the same directory = first test.
- Transport `CaEntry::sendCommand` @0x2d50c, `QSEECom_send_modified_cmd`
  (32-bit), 0x40-byte header in the 4 KiB shared buffer: 0x00 32-bit phys
  addr of payload (fd #0, patched by kernel), 0x04 length, 0x08 sequence,
  0x10 ms-of-day timestamp, 0x1c TA result, 0x20 32-bit phys addr of a 4 MiB
  carveout (fd #1), 0x24 carveout size/handle. Buffers from the
  `qcom,qseecom` dma-buf heap (alloc-ranges 0-4 GiB). Payload: 16-byte
  goodix header (reset flag, target, cmd id, result); e.g. wakeup
  {target 0x3ea, cmd 9}, size 0x20 (`Sensor::wakeupSensor` @0x32418).
  ~170 `GF_*CMD_*` names in `libgf_hal.so`.
- TA imports: SFS/FTS via FS listener 0xa (factory calibration in
  `/mnt/vendor/persist/goodix/`: cali_data.so, caliParamsInfo.so,
  BMatrix.so, HLBMatrix.so, chartbase.so, midbase.so, highflesh.so,
  oemInfo.so; present in this phone's persist, sda21 on the port);
  templates `finger_%d_%d.so` (re-enroll needed); RPMB via 0x2000;
  `qsee_register_shared_buffer`/`qsee_prepare_shared_buf_for_*`; SPI/TLMM in TZ.
- Stock `smcinvoke_mod.ko`: callback objects,
  `qseecom_process_listener_from_smcinvoke`, `firmware_request_from_smcinvoke`,
  `CQSEEComCompatAppLoader_UID = 122`.

## Open question: passing the buffers

(a) QTEE QSEECom-compat loader (UID 122, `IQSEEComCompat.sendRequest`, memory
objects + patch offsets; IDL from Qualcomm's GPL securemsm-kernel headers or
RE), or (b) legacy `handleRequest` with userspace-filled 32-bit phys addrs of
`tee_shm` buffers (pagemap as root or a debug ioctl; needs allocations below
4 GiB: qcomtee uses `alloc_pages_exact` without `GFP_DMA32` -> small patch).

## Plan

0. `CONFIG_QCOMTEE=m` (expect `qcomtee: QTEE version ...`, `/dev/tee0`,
   `/dev/teepriv0`).
1. Package quic-teec + minkipc for pmOS/musl; run `qtee_supplicant` with
   persist read-only at `/mnt/vendor/persist` and `/persist`; squash
   `smplap64` and test the legacy app path; then `gfcupid.elf`; probe
   `IClientEnv_open(122)` to pick (a) or (b). (2-5 days)
2. libgpiod reset GPIO41 / IRQ GPIO40; wakeup {0x3ea, 9} and a version/ID
   command to prove SPI in TZ (risk: QUP wrapper-1 clocks; `clk_ignore_unused`).
3. Reverse the minimal command set from the unstripped HAL
   (`FingerprintCore::init` @0x37744, `CustomizedFingerprintCore::init`
   @0x3f320, `Sensor::init` @0x31e84, `SZSensor::init` @0x36d4c,
   `FingerprintCore::authenticate` @0x38d6c): init, enroll, authenticate,
   remove, cancel, wakeup/sleep, IRQ type, exposure/"spot lit" handshake. (weeks)
4. Local-HBM on/off in the panel driver from the stock DCS sequences; finger
   detection in the FOD area from fts touch events. (~1 week)
5. Daemon + libfprint driver modelled on `goodixmoc` (or an fprintd-compatible
   service) for fprintd/pam_fprintd. (1-2 weeks)
   Shortcut option: run `libgf_hal.so` under libhybris with stand-in
   `libQSEEComAPI.so` and `/dev/goodix_fp` (heavy: bionic, binder stubs).

TZ calls can fault and reboot the phone: steps 1+ only when nothing else is
being tested on it.

## Prior art

None published for TZ-backed fingerprint on mainline. eMainline msm8996 FPC
bit-banged SPI (not possible here). QTEE series tested on sm8550/sm8650.

- https://emainline.gitlab.io/2021/12/12/fingerprint_P1.html
- https://wiki.postmarketos.org/wiki/SM7150_Mainlining
- https://patchew.org/linux/20250911-qcom-tee-using-tee-ss-without-mem-obj-v12-0-17f07a942b8d@oss.qualcomm.com
- https://lwn.net/Articles/1036385/
- https://github.com/quic/quic-teec
- https://github.com/qualcomm/minkipc

