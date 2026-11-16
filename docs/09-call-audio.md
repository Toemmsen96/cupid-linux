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
RX mailbox, encoder, TX mailbox, TTY modules, TX smart sync.) The voice
stream calibration is VCPM's own table (`VCPM_PARAM_ID_CAL_TABLE`, ACDB
chunks VCCD/VCMK/VCKT/VCLU/VCDE), not extracted yet; probably optional for
first audio.

## What Linux needs

1. Graph open for RX subgraphs 0x40/0x41/0x44/0x45/0x02 and TX
   0x39/0x3e/0x3f with scenario 3 and the VSID property 0x080010CC =
   0xFFFFFFFF, all module connections (also across subgraphs, with
   arbitrary port IDs 0x20/0x22/4), control links (0x08001061), and the three
   VCPM voice-config blocks for instance 4.
2. Set-config with the device defaults (TDM sink with lane 0x2, codec DMA
   interface, MFCs).
3. To instance 4: VSID 0x11C05000, TX channel info, optionally the volume
   calibration key.
4. Prepare and start all subgraphs.

Mainline AudioReach is missing: the VSID subgraph property (topology token +
graph setup), module control links, arbitrary port IDs, a way to pass raw
parameters such as the VCPM voice config at graph open, and a data-less
voice front end (control- or DAPM-triggered) that opens and starts both
graphs and then sends the VCPM parameters.
