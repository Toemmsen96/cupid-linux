dnl SPDX-License-Identifier: BSD-3-Clause
dnl Device subgraph for a TDM playback backend (from dianqk/nixos-android-
dnl devices pkgs/marble/audio, after the Marble community topology):
dnl the stream mixer feeds an MFC, which converts to the backend
dnl rate, width and channels, and the TDM sink endpoint. A SAL mixer in
dnl front takes further inputs from graphs opened outside the topology (the
dnl voice call RX graph, on ports 0xc/0x10/0x20/0x22 as in stock).
dnl
dnl   Mixer -> [SAL] -> [MFC] -> [TDM SINK]
dnl
dnl The module instance IDs are stock's (Xiaomi ACDB, speaker device
dnl subgraph 0xb0000002), which the stock voice graphs connect to.
dnl
dnl Uses DEVICE_* from DEVICE_SG_ADD and TDM_* defined by the board file.
include(`audioreach/audioreach.m4') dnl
include(`util/pcm.m4') dnl
include(`audioreach/subgraph.m4') dnl
include(`audioreach/container.m4') dnl
include(`audioreach/module_mfc.m4') dnl
include(`module_sal.m4') dnl
include(`module_tdm.m4') dnl
include(`util/mixer.m4') dnl

undefine(`SAL_MODULE_IID') dnl
undefine(`MFC_MODULE_IID') dnl
undefine(`TDM_MODULE_IID') dnl
undefine(`SG_INDEX') dnl
undefine(`CONTAINER_INDEX') dnl
undefine(`MOD_INDEX') dnl

define(`SAL_MODULE_IID', 0x4012) dnl
define(`MFC_MODULE_IID', 0x48ba) dnl
define(`TDM_MODULE_IID', 0x428f) dnl
define(`SG_INDEX', 1) dnl
define(`CONTAINER_INDEX', 1) dnl
define(`MOD_INDEX', 1) dnl

AR_SUBGRAPH(SG_INDEX, DEVICE_DAI_ID, SG_IID_START, APM_SG_PERF_MODE_LOW_LATENCY,
	APM_SUB_GRAPH_DIRECTION_TX, APM_SUB_GRAPH_SID_AUDIO_PLAYBACK)
AR_CONTAINER(CONTAINER_INDEX, CONT_IID_START,
	`ifelse(LPASS_VER_COMPAT, 110000, APM_CONTAINER_TYPE_ID_GC, APM_CONTAINER_CAP_ID_EP)',
	4096, APM_CONT_GRAPH_POS_GLOBAL_DEV, APM_PROC_DOMAIN_ID_ADSP)

AR_MODULE_SAL(MOD_INDEX, SG_INDEX, CONTAINER_INDEX, SAL_MODULE_IID, 23, 1, 1, 2, MFC_MODULE_IID)
AR_MODULE_MFC(MOD_INDEX, SG_INDEX, CONTAINER_INDEX, MFC_MODULE_IID, 1, 1, 1, 2, TDM_MODULE_IID)
AR_MODULE_TDM_RX(MOD_INDEX, SG_INDEX, CONTAINER_INDEX, TDM_MODULE_IID, 1, 0, 1, 0,
	DEVICE_INTF_TYPE, DEVICE_INTF_INDEX, DEVICE_DATA_FORMAT, DEVICE_SD_LINE_IDX,
	TDM_SYNC_SRC, TDM_DATA_OUT_ENABLE, TDM_SLOT_MASK, TDM_NSLOTS, TDM_SLOT_WIDTH,
	TDM_SYNC_MODE, TDM_INVERT_SYNC, TDM_SYNC_DATA_DELAY, TDM_STREAM_NAME, NONE_IID)

dnl TDM_PLAYBACK_ROUTE(stream-index, mixer-prefix, dai-stream-name)
define(`TDM_PLAYBACK_ROUTE',
`'
`SectionGraph."NAME_PREFIX.$1 $2 Graph" {'
`        index STR($1)'
`        lines ['
`                "NAME_PREFIX.sal$1, , $2 Audio Mixer"'
`                "NAME_PREFIX.mfc$1, , NAME_PREFIX.sal$1"'
`                "NAME_PREFIX.tdm_rx$1, , NAME_PREFIX.mfc$1"'
`                "$3, , NAME_PREFIX.tdm_rx$1"'
`        ]'
`}')

TDM_PLAYBACK_ROUTE(MOD_INDEX, `MIXER_PREFIX', `TDM_STREAM_NAME')
