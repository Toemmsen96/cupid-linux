# 09 Call audio

VoLTE calls connect (the modem runs IMS once `cupid-modem-config` has
activated the carrier configuration), but there is no audio. On SM8450 the
call audio path lives in the ADSP: the modem exchanges voice packets with the
ADSP, and the ADSP's voice call path manager (VCPM, static module instance
4) runs the voice streams. Linux has to open the voice graphs on the ADSP and
configure VCPM; no audio data passes through Linux. Mainline AudioReach has
no voice support (only `VCPM_MODULE_INSTANCE_ID` and the voice-call scenario
ID exist), and the postmarketOS q6voice work covers only the older
APR/q6voice chips, not AudioReach.

## Sources

- Open source, cloned from <https://github.com/AudioReach>:
  - `audioreach-engine/fwk/api/vcpm/vcpm_api.h`: VCPM parameter IDs and
    payloads; `fwk/api/apm/apm_sub_graph_api.h`: the VSID subgraph property.
  - `audioreach-pal/session/SessionAlsaVoice/src/SessionAlsaVoice.cpp`: how
    the HLOS runs a call (hostless RX/TX front ends, VCPM params).
  - `audioreach-conf/qcom/kvh2xml.h`: graph key values.
- Stock: the Forte ACDB (`vendor/etc/acdbdata/Forte/Forte_acdb_cal.acdb`),
  parsed with `scripts/acdb/` (written from the open-source ACDB code; usage:
  `python3 -I scripts/acdb/dump_graph2.py scripts/acdb <acdb> scripts/acdb/names.json KEY=VALUE ...`).
  The dumps of the relevant graphs are in [call-audio/](call-audio/).

## What stock does

- Session: VSID 0x11C05000 (subscription 1), graph key VSID = 0xB3000001.
  The graphs are opened with the VSID property "don't care" (0xFFFFFFFF, as
  in the ACDB); the DSP's VCPM proxy binds them when the VSID param arrives.
- Backends: earpiece and speaker RX on `TDM-LPAIF-RX-TERTIARY-VIRT-0`
  (48 kHz, 24 bit; handset 1 channel), mic on `CODEC_DMA-LPAIF_RXTX-TX-3`
  (48 kHz, 16 bit). The earpiece is the top CS35L41 (stock: T PCM Source
  DSP, AMP PCM Gain 5, T-handset tuning); speaker switch GPIO 52 stays 0.
- At call start the stock voice plugin sends to VCPM (instance 4):
  `VCPM_PARAM_ID_VSID` {vsid} (0x080011BC), `VCPM_PARAM_ID_TX_DEV_PP_CHANNEL_INFO`
  {vsid, channels} (0x08001310), `VCPM_PARAM_ID_CAL_KEYS` {vsid, n,
  (0x08001166 volume step, ...)} (0x0800116B). Linux sends nothing to the
  modem; the modem drives the call.

### RX graph (earpiece/speaker)

Keys `A1000000=A1000010 A2000000=A2000004 AC000000=AC000005 AF000000=AF000001 B3000000=B3000001`.

| Subgraph | Role | Modules (instance) |
|---|---|---|
| 0x40 | stream RX | MAILBOX_RX 0x07001057 (41b1) -> DECODER 0x07001009 (41b3) -> log -> IIR resampler -> 0x07001074 (43fc) -> 0x07001088 (41b5) -> 0x07001096 (41b6) |
| 0x41 | stream RX | splitter -> 0x07001071 -> log |
| 0x44 | stream PP RX | MSIIR -> VOL -> 0x07001052 -> MBDRC -> ... -> 0x1000ff51 -> MFC -> 0x07001035 -> log |
| 0x45 | device PP RX | TRM 0x07001087 -> POP_SUPPRESSOR -> SAL 0x4012 port 0x20; 0x07001046 -> MFC -> log -> SAL port 0x22 |
| 0x02 | device RX | the speaker TDM device graph (SAL 0x4012 -> MFC 0x48ba -> ... -> TDM sink 0x428f, lane 1) |

Scenario 3 (voice call), direction RX. Control links: TDM sink <->
MAILBOX_RX (intent 0x08001089), TDM sink <-> 0x41db and MAILBOX_RX <-> 0x41db
(0x080010C2), 0x465a <-> MAILBOX_RX (0x08001207).

### TX graph (handset mic)

Keys `A3000000=A3000004 AD000000=AD000008 B1000000=B1000007 B3000000=B3000001`.

| Subgraph | Role | Modules |
|---|---|---|
| 0x39 | device TX | CODEC_DMA_SOURCE 0x07001024 (43af, 48 kHz / 16 bit / 1 ch) -> log -> splitter |
| 0x3e | device PP TX | 0x0700105A (mic + echo reference) -> 2x MFC -> SMART_SYNC -> EC_SYNC -> filters -> 0x07001031 (ECNS, loaded at runtime: `smecns_v2_module_fvxi.so.1` from the dsp partition) -> FIR -> MSIIR -> 0x07001068 -> MBDRC -> VOL |
| 0x3f | stream TX | VOL -> EC_SYNC -> SAL -> 0x0700106C -> splitter -> VOL -> 0x07001095 -> 0x07001089 -> ENCODER 0x07001008 (41ae) -> MAILBOX_TX 0x07001056 (41b0) |

Echo reference: RX device splitter 0x418e port 0x29 -> TX 0x4199 port 4, so
RX and TX must be open together. The ECNS module is dynamically loaded by
the ADSP (needs an ADSP hexagonrpcd serving the dsp partition, untested), or
the TX processing subgraph can be replaced by one without 0x07001031.

### VCPM voice config (`VCPM_PARAM_ID_VOICE_CONFIG` 0x08001162 to instance 4, at graph open)

- RX 0xb0000040: `00000001 b0000040 00000001 080011b2 0000002c 00000005 0800117b 000041b3 0800117c 000041b1 0800117e 000041b6 080011e2 000041b5 080011e3 000043fc`
- TX 0xb000003f: `00000001 b000003f 00000001 080011b2 00000024 00000004 08001177 000041ae 08001178 000041b0 0800117a 000041ab 080011e1 000041ac`
- TX PP 0xb000003e: `00000001 b000003e 00000001 080011b2 0000000c 00000001 080011ad 0000419a`

(VCPM_PROPERTY_ID_TAG_INFO 0x080011B2 lists tag -> module instance: decoder,
RX mailbox, encoder, TX mailbox, TTY modules, TX smart sync.)

### VCPM calibration table

The voice subgraphs' calibration is not in the ACDB's audio tables but in
VCPM's own (chunks VCCD/VCMK/VCKT/VCLU/VCDE). The ACDB library
(`BuildVcpmBlob` in audioreach-graphservices) packs it per subgraph into
one parameter, `VCPM_PARAM_ID_CAL_TABLE` 0x08001163 for instance 4, and GSL
registers it as persistent calibration (`APM_CMD_REGISTER_CFG`, from shared
memory) right after the graph open. It holds what VCPM applies when the
modem starts the vocoder, keyed by vocoder class, sample rate, network and
volume step: resampler output rates (0x421f), the TX MFC formats
(0x4197/0x4198), filters, gains, `VCPM_PARAM_ID_CLK_CTRL`, ECNS tuning.
`scripts/acdb/vcpm_cal.py` rebuilds it: 0x40 1.1 KiB, 0x41 0.9 KiB, 0x44
16 KiB (7.5 KiB with only the LTE entries), 0x3f 3 KiB, 0x3e 11 KiB; 0x45,
0x39 and 0x02 have none.

## What Linux needs

1. Graph open for RX subgraphs 0x40/0x41/0x44/0x45/0x02 and TX
   0x39/0x3e/0x3f with scenario 3 and the VSID property 0x080010CC =
   0xFFFFFFFF, all module connections (also across subgraphs, with
   arbitrary port IDs 0x20/0x22/4), control links (0x08001061), and the three
   VCPM voice-config blocks for instance 4.
2. Set-config with the device defaults (TDM sink with lane 0x2, codec DMA
   interface, MFCs).
3. VCPM calibration tables for 0x40/0x41/0x44/0x3f/0x3e
   (`REGISTER_CFG`).
4. To instance 4: VSID 0x11C05000, TX channel info, optionally the volume
   calibration key.
5. Prepare and start all subgraphs.

## Bring-up tooling

- Kernel patch 0040 (r17) adds `/sys/kernel/debug/q6apm_raw`: write
  `[u32 opcode][payload]`, read back `[u32 response opcode][payload]`.
- The topology's speaker and microphone backends use stock's module
  instance IDs, so the stock voice graphs connect to them while Linux
  streams keep them running:
  - speaker TDM: `SAL 0x4012 -> MFC 0x48ba -> TDM sink 0x428f` (voice RX
    enters the SAL on ports 0x20/0x22 handset, 0xc/0x10 speaker);
  - handset microphone, codec DMA TX3: `0x43af -> log 0x4147 -> splitter
    0x4167` (port 1 to the capture stream, port 0xd to the voice TX graph).
- `scripts/voicecall/voicecall.py build <acdb> scripts/acdb/names.json <dir>
  [handset|speaker] [rx-only] [no-ecns] [fit]` turns the ACDB graphs into
  command files (graph open with the stock subgraph data, which already
  carries the VCPM voice configuration; module calibration; VCPM
  calibration tables; VCPM VSID and TX channel info; prepare; start);
  `voicecall.py start|stop <dir>` sends them on the phone. `no-ecns`
  removes the ECNS module from the TX processing subgraph (mic chain
  0x41a1 straight to 0x41a3, AVC sink 0x41a4 dropped). `fit` keeps only the
  LTE entries for one sample rate (`fit=RATE`, default 32000, EVS
  super-wideband as negotiated in tests). Needed before kernel r19: GPR
  sent with `rpmsg_trysend`, so a command larger than the ADSP's 4 KiB
  receive buffers (about 4040 bytes) failed with `EBUSY`. From r19
  (patch 0041) `q6apm_raw` sends with `gpr_send_pkt_sleep()`, which lets
  glink request a large enough buffer, so the full tables (up to 16 KiB)
  go through and `fit` is unnecessary.
- `voicecall.py keys <dir>` (during a call) reads
  `VCPM_PARAM_ID_ACTIVE_CAL_KEYS` per subgraph: vocoder class, sample rate
  and network appear once the modem has started the vocoder.
- Testing without a second person: the mic capture runs through the
  splitter, so a recording of it shows what the speaker plays; beeps
  played through the Linux speaker stream during a call go out through the
  voice TX path. Keep the amplifiers at `Digital PCM Volume` 625.

## State (2026-11-17)

- ECNS: the TX processing subgraph 0x3e fails to open only because of
  the ECNS module 0x07001031, which the ADSP loads as
  `smecns_v2_module_fvxi.so.1` from the DSP partition through its audio PD
  (Android: `audioadsprpcd audiopd`; hexagonrpcd serves only the root and
  sensors PDs). Without it (`no-ecns`) RX and TX open, take their VCPM
  calibration (`fit`), prepare and start with status 0 together with the
  running backends.
- Audio PD (works, 2026-11-17): mainline fastrpc creates it with
  `FASTRPC_IOCTL_INIT_CREATE_STATIC` "audiopd" and hands the ADSP a remote
  heap from the fastrpc node's `memory-region` (8 MiB pool, `qcom,vmids`
  LPASS + ADSP_HEAP, as on kodiak/sm8250); the cupid DTS adds it (kernel
  r18). `pmaports/temp/hexagonrpcd` (0.4.0-r100) adds `hexagonrpcd -a`,
  which creates the PD and serves its file requests, and the unit
  `hexagonrpcd-adsp-audiopd.service` (enabled by the device package's
  preset from r22). With it running, the stock voice graphs including ECNS
  (`build` without `no-ecns`) open, take their calibration and start with
  status 0; the 0x3e table with ECNS is 4020 bytes, just inside the GPR
  limit with `fit`.
- The modem does start the vocoder: during a call (already while it
  rings) `voicecall.py keys` shows vocoder class EVS (0x0800116A) at
  32 kHz on 0x40, 0x3f and 0x3e. Modem and ADSP talk to each other
  directly; a kprobe on `qrtr_endpoint_post` saw no packet routed through
  the application processor, so mainline QRTR is not in the way.
- Four answered test calls carried no audible audio: without calibration
  tables, with tables trimmed to 16 kHz (no entries for the 32 kHz in use),
  and the far end heard at most "something very quiet" of the beeps. The
  VCPM vocoder loopback (`VCPM_PARAM_ID_VOC_PKT_LOOPBACK_DELAY`, loopback
  VSID 0x12006000) produced nothing without a call.
- Next: a call with the stock graphs (ECNS included) and the full
  calibration tables (kernel r19), louder beeps; then the kernel voice
  front end.
- Practical notes: without a login, ModemManager voice calls need root
  (polkit); `mmcli -o` needs the full object path
  (`/org/freedesktop/ModemManager1/Call/N`, the short form crashes mmcli).
  The login screen session runs gnome-calls, callaudiod and pmOS's
  `call_audio_idle_suspend_workaround`, which keeps PulseAudio from
  suspending the sound card during a call, i.e. keeps both backends
  running, which is what the voice graphs need.

Mainline AudioReach is missing: the VSID subgraph property (topology token +
graph setup), module control links, arbitrary port IDs, a way to pass raw
parameters such as the VCPM voice config at graph open, and a data-less
voice front end (control- or DAPM-triggered) that opens and starts both
graphs and then sends the VCPM parameters.
