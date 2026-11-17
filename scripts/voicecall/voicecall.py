#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Voice call graphs on the ADSP, sent as raw APM commands (bring-up tool).

build ACDB NAMES OUTDIR [handset|speaker] [rx-only] [no-ecns] [fit[=RATE]]
    (host, needs scripts/acdb) Build the command files for a call from the
    stock Forte ACDB: graph open for the voice RX and TX subgraphs (their
    ACDB data includes the VCPM voice configuration), their calibration,
    the VCPM's calibration tables (scripts/acdb/vcpm_cal.py), the VCPM
    session parameters, and prepare/start. Stock's speaker and
    microphone device subgraphs are left out (LINUX_SGS): the Linux
    topology's backends carry the same module instance IDs, so the voice
    graphs connect to them while a Linux playback and capture stream keep
    them running. no-ecns leaves the ECNS module out of the TX processing
    subgraph (NO_ECNS). fit keeps only the LTE entries for one vocoder
    sample rate (default 32000: EVS super-wideband, what VoLTE negotiated
    in tests) of the VCPM calibration tables, so that each command fits the
    ADSP's 4 KiB receive buffers (GPR sends without waiting for a bigger
    one). VCPM reports the rate in use: see keys.

start DIR / stop DIR
    (phone, root) Send DIR/start/* or DIR/stop/* in order through
    /sys/kernel/debug/q6apm_raw (kernel patch 0040) and print each result.

keys DIR
    (phone, root) Print the calibration keys VCPM has active for each voice
    subgraph of DIR (VCPM_PARAM_ID_ACTIVE_CAL_KEYS). Vocoder class, sample
    rate and network come from the modem once it starts the vocoder, so
    during a working call they are set; empty means the modem never did.

Command file: [u32 opcode][payload]. For APM commands with an in-band
payload the payload starts with the 16-byte apm_cmd_header.
"""
import os, struct, sys

GRAPH_OPEN, PREPARE, START, STOP, CLOSE, SET_CFG = (0x01001000, 0x01001001, 0x01001002,
                                                   0x01001003, 0x01001004, 0x01001006)
REGISTER_CFG, DEREGISTER_CFG = 0x01001008, 0x01001009
APM_IID = 1
VCPM_IID = 4
SUB_GRAPH_LIST = 0x08001005
VCPM_VSID = 0x080011BC
VCPM_TX_DEV_PP_CHANNEL_INFO = 0x08001310
VSID = 0x11C05000  # subscription 1
GPR_BASIC_RSP_RESULT = 0x02001005

# Stock graph key vectors (ACDB), see docs/09-call-audio.md.
GKV = {
    "rx-handset": {0xA1000000: 0xA1000010, 0xA2000000: 0xA2000004, 0xAC000000: 0xAC000005,
                   0xAF000000: 0xAF000001, 0xB3000000: 0xB3000001},
    "rx-speaker": {0xA1000000: 0xA1000010, 0xA2000000: 0xA2000001, 0xAC000000: 0xAC000005,
                   0xAF000000: 0xAF000001, 0xB3000000: 0xB3000001},
    "tx-handset": {0xA3000000: 0xA3000004, 0xAD000000: 0xAD000008, 0xB1000000: 0xB1000007,
                   0xB3000000: 0xB3000001},
}
# Owned by the Linux topology, with stock's module instance IDs: the
# speaker TDM backend (SAL 0x4012 -> MFC 0x48ba -> TDM 0x428f) and the
# handset microphone backend (codec DMA TX3 0x43af -> log 0x4147 ->
# splitter 0x4167). Linux streams keep them running.
LINUX_SGS = {0xB0000002, 0xB0000039}

def pad8(b):
    return b + b"\0" * (-len(b) % 8)


def param(miid, pid, payload):
    return pad8(struct.pack("<IIII", miid, pid, len(payload), 0) + payload)


def acdb_params(blob):
    """ACDB parameter list (12-byte headers) -> APM format (16-byte)."""
    out, p = b"", 0
    while p + 12 <= len(blob):
        miid, pid, sz = struct.unpack_from("<III", blob, p)
        out += param(miid, pid, blob[p + 12:p + 12 + sz])
        p += 12 + sz + (-sz % 8)
    return out


APM_MODULES_LIST, APM_MODULE_PROP, APM_MODULE_CONN, APM_MODULE_CTRL_LINK = (
    0x08001002, 0x08001003, 0x08001004, 0x08001061)

# The TX processing subgraph without the ECNS module 0x07001031 (iid 0x41a0),
# which the ADSP loads from its audio PD, and without the AVC sink 0x41a4 fed
# only by ECNS: the microphone chain goes straight from log 0x41a1 to FIR
# 0x41a3, the echo reference ends at log 0x419c.
NO_ECNS = ({0x41a0, 0x41a4}, [(0x41a1, 1, 0x41a3, 2)])


def split_params(params):
    """APM parameter list -> [(miid, pid, payload)]."""
    out, p = [], 0
    while p + 16 <= len(params):
        miid, pid, sz, _ = struct.unpack_from("<IIII", params, p)
        out.append((miid, pid, params[p + 16:p + 16 + sz]))
        p += 16 + sz + (-sz % 8)
    return out


def drop_modules(params, drop, add_conns=()):
    """Remove module instances `drop` from an APM parameter list: module
    lists, properties, data connections, control links and their
    calibration; then add the data connections `add_conns`."""
    out, add_conns = b"", list(add_conns)
    for miid, pid, pl in split_params(params):
        if miid in drop:
            continue
        if miid != APM_IID:
            out += param(miid, pid, pl)
            continue
        w = lambda q: struct.unpack_from("<I", pl, q)[0]
        n, q, items = w(0), 4, []
        for _ in range(n):
            if pid == APM_MODULES_LIST:
                sg, cont, nm = struct.unpack_from("<III", pl, q)
                mods = [struct.unpack_from("<II", pl, q + 12 + 8 * j) for j in range(nm)]
                q += 12 + 8 * nm
                mods = [m for m in mods if m[1] not in drop]
                items.append(struct.pack("<III", sg, cont, len(mods)) +
                             b"".join(struct.pack("<II", *m) for m in mods))
                continue
            if pid == APM_MODULE_PROP:
                start, iids = q, (w(q),)
                q += 4
            elif pid in (APM_MODULE_CONN, APM_MODULE_CTRL_LINK):
                start, iids = q, (w(q), w(q + 8))
                q += 16
            else:
                break
            if pid != APM_MODULE_CONN:  # property list
                nprops = w(q)
                q += 4
                for _ in range(nprops):
                    q += 8 + w(q + 4)
            if not drop.intersection(iids):
                items.append(pl[start:q])
        else:
            if pid == APM_MODULE_CONN and len(items) < n and add_conns:
                items += [struct.pack("<IIII", *c) for c in add_conns]
                add_conns = []
            if not items:
                continue
            pl = struct.pack("<I", len(items)) + b"".join(items)
        out += param(miid, pid, pl)
    return out


def cmd(opcode, params):
    return struct.pack("<IIIII", opcode, 0, 0, 0, len(params)) + params


def sg_list_cmd(opcode, sgs):
    return cmd(opcode, param(APM_IID, SUB_GRAPH_LIST, struct.pack("<I", len(sgs)) +
                             b"".join(struct.pack("<I", s) for s in sgs)))


def build(acdb_path, names, outdir, rx="rx-handset", tx=True, ecns=True, fit=None):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "acdb"))
    import acdb as A
    import vcpm_cal
    a = A.Acdb(acdb_path, names)
    graphs = {}
    for gkv, sl, sp in a.gkvs():
        for name, want in GKV.items():
            if dict(gkv) == want:
                graphs[name] = (a.sg_list(sl), a.sg_props(sp))
    files = {"start": [], "stop": []}
    dereg = []
    sgs_all = []
    for name in (rx, "tx-handset") if tx else (rx,):
        sgl, props = graphs[name]
        sgs = [sg for sg, _ in sgl if sg not in LINUX_SGS]
        sgs_all += sgs
        params = b"".join(acdb_params(props[sg][1]) for sg in sgs)
        for src, dsts in sgl:
            for dst in dsts:
                if src in LINUX_SGS and dst in LINUX_SGS:
                    continue
                blob = A.sg_conn(a, src, dst)
                if blob:
                    params += acdb_params(blob)
        if not ecns:
            params = drop_modules(params, NO_ECNS[0],
                                  NO_ECNS[1] if name.startswith("tx") else ())
        files["start"].append(("open-" + name, cmd(GRAPH_OPEN, params)))
        cal = b""
        for sg in sgs:
            for ckv, res, _ in A.sg_cal(a, sg):
                if ckv:
                    continue
                cal += b"".join(param(iid, pid, pl) for iid, pid, pl in res
                                if pl is not None and (ecns or iid not in NO_ECNS[0]))
        if cal:
            files["start"].append(("cal-" + name, cmd(SET_CFG, cal)))
        # VCPM's own calibration table per voice subgraph, registered as
        # persistent calibration like GSL does (in-band here).
        for sg in sgs:
            r = vcpm_cal.vcpm_blob(a, sg, () if ecns else NO_ECNS[0],
                                   {vcpm_cal.NETWORK: vcpm_cal.NETWORK_LTE,
                                    vcpm_cal.SAMPLING_RATE: fit} if fit else None)
            if r:
                vc = param(*r)
                files["start"].append(("vcpm-cal-%x" % (sg & 0xff), cmd(REGISTER_CFG, vc)))
                dereg.append(("vcpm-uncal-%x" % (sg & 0xff), cmd(DEREGISTER_CFG, vc)))
    files["start"].append(("vsid", cmd(SET_CFG, param(VCPM_IID, VCPM_VSID, struct.pack("<I", VSID)) +
                                       param(VCPM_IID, VCPM_TX_DEV_PP_CHANNEL_INFO,
                                             struct.pack("<II", VSID, 1)))))
    files["start"].append(("prepare", sg_list_cmd(PREPARE, sgs_all)))
    files["start"].append(("start", sg_list_cmd(START, sgs_all)))
    files["stop"].append(("stop", sg_list_cmd(STOP, sgs_all)))
    files["stop"] += dereg
    files["stop"].append(("close", sg_list_cmd(CLOSE, sgs_all)))
    for kind, lst in files.items():
        d = os.path.join(outdir, kind)
        os.makedirs(d, exist_ok=True)
        for i, (n, data) in enumerate(lst):
            with open(os.path.join(d, "%02d-%s.cmd" % (i, n)), "wb") as f:
                f.write(data)
            print("%s/%02d-%s.cmd %d bytes" % (kind, i, n, len(data)))


VCPM_ACTIVE_CAL_KEYS = 0x080011C1
GET_CFG, RSP_GET_CFG = 0x01001007, 0x02001000


def raw(data):
    fd = os.open("/sys/kernel/debug/q6apm_raw", os.O_RDWR)
    try:
        os.write(fd, data)
        return os.read(fd, 8192)
    finally:
        os.close(fd)


def keys(d):
    start = os.path.join(d, "start")
    name = [n for n in sorted(os.listdir(start)) if n.endswith("-start.cmd")][0]
    data = open(os.path.join(start, name), "rb").read()
    sgs = struct.unpack_from("<I", data, 36)[0]   # after cmd and param headers
    for sg in struct.unpack_from("<%dI" % sgs, data, 40):
        rsp = raw(cmd(GET_CFG, param(VCPM_IID, VCPM_ACTIVE_CAL_KEYS,
                                     struct.pack("<III", sg, 8, 0) + bytes(64))))
        if struct.unpack_from("<I", rsp)[0] != RSP_GET_CFG:
            print("0x%08x: response 0x%08x" % (sg, struct.unpack_from("<I", rsp)[0]))
            continue
        status, _, _, _, err, _, _, n = struct.unpack_from("<8I", rsp, 4)
        pairs = [struct.unpack_from("<II", rsp, 36 + 8 * i) for i in range(min(n, 8))]
        print("0x%08x: status %d error %d keys %s" % (sg, status, err,
              " ".join("%08x=%08x" % kv for kv in pairs) or "none"))
    return 0


def run(d, kind):
    path = os.path.join(d, kind)
    rc = 0
    for n in sorted(os.listdir(path)):
        data = open(os.path.join(path, n), "rb").read()
        fd = os.open("/sys/kernel/debug/q6apm_raw", os.O_RDWR)
        try:
            os.write(fd, data)
            rsp = os.read(fd, 8192)
        except OSError as e:
            print("%s: %s" % (n, e))
            return 1
        finally:
            os.close(fd)
        op = struct.unpack_from("<I", rsp)[0]
        if op == GPR_BASIC_RSP_RESULT and len(rsp) >= 12:
            req, status = struct.unpack_from("<II", rsp, 4)
            print("%s: opcode 0x%08x status 0x%x" % (n, req, status))
            if status:
                rc = 1
                if kind == "start":
                    return rc
        else:
            print("%s: response 0x%08x %s" % (n, op, rsp[4:68].hex()))
    return rc


def main():
    if len(sys.argv) >= 5 and sys.argv[1] == "build":
        rx = "rx-" + (sys.argv[5] if len(sys.argv) > 5 else "handset")
        build(sys.argv[2], sys.argv[3], sys.argv[4], rx, "rx-only" not in sys.argv[6:],
              "no-ecns" not in sys.argv[6:],
              next((int(a[4:]) if a[4:] else 32000 for a in sys.argv[6:]
                    if a == "fit" or a.startswith("fit=")), None))
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "keys":
        return keys(sys.argv[2])
    if len(sys.argv) == 3 and sys.argv[1] in ("start", "stop"):
        return run(sys.argv[2], sys.argv[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
