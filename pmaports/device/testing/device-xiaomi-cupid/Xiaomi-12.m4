dnl SPDX-License-Identifier: BSD-3-Clause
dnl AudioReach topology for the Xiaomi 12 (cupid), built with the
dnl linux-msm/audioreach-topology macros. Card "Xiaomi-12" with the sm8450
dnl driver name, so q6apm requests qcom/sm8450/Xiaomi-12-tplg.bin.
dnl
dnl The SM8450-HDK topology (Linaro, 2023) with the WSA speaker backend
dnl replaced by the tertiary TDM interface of the two CS35L41 amplifiers and
dnl without the HDK's primary MI2S (HDMI) backend:
dnl
dnl   MultiMedia1/2 (48 kHz S16 stereo) -> RX_CODEC_DMA_RX_0 (WCD938x jack)
dnl                                     -> TERTIARY_TDM_RX_0 (speakers)
dnl   VA_CODEC_DMA_TX_0 / TX_CODEC_DMA_TX_3 -> MultiMedia3/4
dnl
dnl Speaker TDM like stock ("TDM-LPAIF-RX-TERTIARY", Android backend_conf):
dnl 96 kHz, 32-bit samples in four 32-bit slots, short frame sync with a one
dnl bit data delay, internal sync (SoC clock provider), data output on. The
dnl slot mask in use (slots 0/1: top/bottom amplifier) comes from the card's
dnl dai-link; the device MFC converts the 48 kHz stereo stream.
include(`audioreach/audioreach.m4')
include(`audioreach/stream-subgraph.m4')
include(`audioreach/device-subgraph.m4')
include(`util/route.m4')
include(`util/mixer.m4')
include(`audioreach/tokens.m4')

dnl Playback MultiMedia1
STREAM_SG_PCM_ADD(audioreach/subgraph-stream-vol-playback.m4, FRONTEND_DAI_MULTIMEDIA1,
	`S16_LE', 48000, 48000, 2, 2,
	0x00004001, 0x00004001, 0x00006001)
dnl Playback MultiMedia2
STREAM_SG_PCM_ADD(audioreach/subgraph-stream-vol-playback.m4, FRONTEND_DAI_MULTIMEDIA2,
	`S16_LE', 48000, 48000, 2, 2,
	0x00004002, 0x00004002, 0x00006010)
dnl Capture MultiMedia3
STREAM_SG_PCM_ADD(audioreach/subgraph-stream-capture.m4, FRONTEND_DAI_MULTIMEDIA3,
	`S16_LE', 48000, 48000, 1, 2,
	0x00004003, 0x00004003, 0x00006020)
dnl Capture MultiMedia4
STREAM_SG_PCM_ADD(audioreach/subgraph-stream-capture.m4, FRONTEND_DAI_MULTIMEDIA4,
	`S16_LE', 48000, 48000, 1, 2,
	0x00004004, 0x00004004, 0x00006030)

dnl Tertiary TDM speaker interface (PARAM_ID_TDM_INTF_CFG values)
define(`TDM_SYNC_SRC', 1) dnl internal
define(`TDM_DATA_OUT_ENABLE', 1)
define(`TDM_SLOT_MASK', 0x3)
define(`TDM_NSLOTS', 4)
define(`TDM_SLOT_WIDTH', 32)
define(`TDM_SYNC_MODE', 0) dnl short sync, bit mode
define(`TDM_INVERT_SYNC', 0)
define(`TDM_SYNC_DATA_DELAY', 1) dnl one bit clock
define(`TDM_STREAM_NAME', `Tertiary TDM0 Playback')
DEVICE_SG_ADD(subgraph-device-tdm-playback.m4, `TERTIARY_TDM_RX_0', TERTIARY_TDM_RX_0,
	`S32_LE', 96000, 96000, 2, 2,
	LPAIF_INTF_TYPE_LPAIF, I2S_INTF_TYPE_TERTIARY, 0, DATA_FORMAT_FIXED_POINT,
	0x00004005, 0x00004005, 0x00006050, `TERTIARY_TDM_RX_0')
dnl
dnl WCDRX Playback
DEVICE_SG_ADD(audioreach/subgraph-device-codec-dma-playback.m4, `RX_CODEC_DMA_RX_0', RX_CODEC_DMA_RX_0,
	`S16_LE', 48000, 48000, 2, 2,
	LPAIF_INTF_TYPE_RXTX, CODEC_INTF_IDX_RX0, 0, DATA_FORMAT_FIXED_POINT,
	0x00004007, 0x00004007, 0x00006070)
dnl
dnl VA Capture
DEVICE_SG_ADD(audioreach/subgraph-device-codec-dma-capture.m4, `VA_CODEC_DMA_TX_0', VA_CODEC_DMA_TX_0,
	`S16_LE', 48000, 48000, 1, 2,
	LPAIF_INTF_TYPE_VA, CODEC_INTF_IDX_TX0, 0, DATA_FORMAT_FIXED_POINT,
	0x00004008, 0x00004008, 0x00006080)
dnl
dnl WCDTX Capture
DEVICE_SG_ADD(audioreach/subgraph-device-codec-dma-capture.m4, `TX_CODEC_DMA_TX_3', TX_CODEC_DMA_TX_3,
	`S16_LE', 48000, 48000, 1, 2,
	LPAIF_INTF_TYPE_RXTX, CODEC_INTF_IDX_TX3, 0, DATA_FORMAT_FIXED_POINT,
	0x00004009, 0x00004009, 0x00006090)

STREAM_DEVICE_PLAYBACK_MIXER(TERTIARY_TDM_RX_0, ``TERTIARY_TDM_RX_0'', ``MultiMedia1'', ``MultiMedia2'')
STREAM_DEVICE_PLAYBACK_MIXER(RX_CODEC_DMA_RX_0, ``RX_CODEC_DMA_RX_0'', ``MultiMedia1'', ``MultiMedia2'')

STREAM_DEVICE_PLAYBACK_ROUTE(TERTIARY_TDM_RX_0, ``TERTIARY_TDM_RX_0 Audio Mixer'', ``MultiMedia1, stream0.logger1'', ``MultiMedia2, stream1.logger1'')
STREAM_DEVICE_PLAYBACK_ROUTE(RX_CODEC_DMA_RX_0, ``RX_CODEC_DMA_RX_0 Audio Mixer'', ``MultiMedia1, stream0.logger1'', ``MultiMedia2, stream1.logger1'')

STREAM_DEVICE_CAPTURE_MIXER(FRONTEND_DAI_MULTIMEDIA3, ``VA_CODEC_DMA_TX_0'',``TX_CODEC_DMA_TX_3'' )
STREAM_DEVICE_CAPTURE_MIXER(FRONTEND_DAI_MULTIMEDIA4, ``VA_CODEC_DMA_TX_0'',``TX_CODEC_DMA_TX_3'' )
STREAM_DEVICE_CAPTURE_ROUTE(FRONTEND_DAI_MULTIMEDIA3, ``MultiMedia3 Mixer'', ``VA_CODEC_DMA_TX_0, device110.logger1'', ``TX_CODEC_DMA_TX_3, device120.logger1'')
STREAM_DEVICE_CAPTURE_ROUTE(FRONTEND_DAI_MULTIMEDIA4, ``MultiMedia4 Mixer'', ``VA_CODEC_DMA_TX_0, device110.logger1'', ``TX_CODEC_DMA_TX_3, device120.logger1'')
