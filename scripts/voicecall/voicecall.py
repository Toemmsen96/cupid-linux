#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Voice call graphs on the ADSP, sent as raw APM commands (bring-up tool).

build ACDB NAMES OUTDIR [handset|speaker] [rx-only]
    (host, needs scripts/acdb) Build the command files for a call from the
    stock Forte ACDB: graph open for the voice RX and TX subgraphs (their
    ACDB data includes the VCPM voice configuration), their calibration,
    the VCPM session parameters, and prepare/start. Stock's speaker device subgraph is left out: the Linux
    topology's TDM speaker backend carries the same module instance IDs
    (SAL 0x4012, MFC 0x48ba, TDM sink 0x428f), so the voice graph connects
    to it while a Linux playback stream keeps it running.

start DIR / stop DIR
    (phone, root) Send DIR/start/* or DIR/stop/* in order through
    /sys/kernel/debug/q6apm_raw (kernel patch 0040) and print each result.

Command file: [u32 opcode][payload]. For APM commands with an in-band
payload the payload starts with the 16-byte apm_cmd_header.
"""
import os, struct, sys

GRAPH_OPEN, PREPARE, START, STOP, CLOSE, SET_CFG = (0x01001000, 0x01001001, 0x01001002,
                                                   0x01001003, 0x01001004, 0x01001006)
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
# Owned by the Linux topology (speaker TDM backend).
LINUX_SGS = {0xB0000002}

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


def cmd(opcode, params):
    return struct.pack("<IIIII", opcode, 0, 0, 0, len(params)) + params


def sg_list_cmd(opcode, sgs):
    return cmd(opcode, param(APM_IID, SUB_GRAPH_LIST, struct.pack("<I", len(sgs)) +
                             b"".join(struct.pack("<I", s) for s in sgs)))


def build(acdb_path, names, outdir, rx="rx-handset", tx=True):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "acdb"))
    import acdb as A
    a = A.Acdb(acdb_path, names)
    graphs = {}
    for gkv, sl, sp in a.gkvs():
        for name, want in GKV.items():
            if dict(gkv) == want:
                graphs[name] = (a.sg_list(sl), a.sg_props(sp))
    files = {"start": [], "stop": []}
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
        files["start"].append(("open-" + name, cmd(GRAPH_OPEN, params)))
        cal = b""
        for sg in sgs:
            for ckv, res, _ in A.sg_cal(a, sg):
                if ckv:
                    continue
                cal += b"".join(param(iid, pid, pl) for iid, pid, pl in res if pl is not None)
        if cal:
            files["start"].append(("cal-" + name, cmd(SET_CFG, cal)))
    files["start"].append(("vsid", cmd(SET_CFG, param(VCPM_IID, VCPM_VSID, struct.pack("<I", VSID)) +
                                       param(VCPM_IID, VCPM_TX_DEV_PP_CHANNEL_INFO,
                                             struct.pack("<II", VSID, 1)))))
    files["start"].append(("prepare", sg_list_cmd(PREPARE, sgs_all)))
    files["start"].append(("start", sg_list_cmd(START, sgs_all)))
    files["stop"].append(("stop", sg_list_cmd(STOP, sgs_all)))
    files["stop"].append(("close", sg_list_cmd(CLOSE, sgs_all)))
    for kind, lst in files.items():
        d = os.path.join(outdir, kind)
        os.makedirs(d, exist_ok=True)
        for i, (n, data) in enumerate(lst):
            with open(os.path.join(d, "%02d-%s.cmd" % (i, n)), "wb") as f:
                f.write(data)
            print("%s/%02d-%s.cmd %d bytes" % (kind, i, n, len(data)))


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
        build(sys.argv[2], sys.argv[3], sys.argv[4], rx, sys.argv[6:] != ["rx-only"])
        return 0
    if len(sys.argv) == 3 and sys.argv[1] in ("start", "stop"):
        return run(sys.argv[2], sys.argv[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
