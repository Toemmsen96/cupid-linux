#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""VCPM calibration table of a voice subgraph, as the ACDB library builds it.

python3 -I vcpm_cal.py ACDB OUTDIR SG_ID...

For a voice subgraph the ACDB holds the calibration in the VCPM chunks
(VCCD, VCMK, VCKT, VCLU, VCDE) instead of the audio calibration tables. The
AudioReach ACDB library (BuildVcpmBlob in acdb_command.c, from
audioreach-graphservices) turns it into one APM parameter for the VCPM,
VCPM_PARAM_ID_CAL_TABLE, which GSL registers as persistent calibration of
the subgraph. This writes OUTDIR/<sg>.bin: that parameter in APM format
([u32 iid][u32 pid][u32 size][u32 error][payload, padded to 8 bytes]).

Blob payload:
  subgraph info  u32 1, {sg, table size, major, minor, 0, #tables},
                 per table {size, key-ID table offset, cal-object size,
                 #objects}, per object {LUT offset, #params}, per param
                 {data pool offset, persistent}
  master keys    u32 size, u32 n, {key, dynamic}...   keys used by the tables
  key IDs        u32 size, per table u32 n, keys...
  key values     u32 size, per object u32 n, values...
  data pool      u32 size, per param {iid, pid, size, 0, payload, pad}
Offsets are relative to the start of the chunk's data. The default table
(no keys) comes last and leaves out modules that keyed tables calibrate.
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acdb as A


def u32s(*v):
    return struct.pack("<%dI" % len(v), *v)


SAMPLING_RATE, NETWORK, NETWORK_LTE = 0x08001165, 0x080011B5, 0x080011BA


def vcpm_blob(a, sg, drop=(), only=None):
    """Return (miid, pid, payload) or None if sg has no VCPM calibration.
    Parameters of the module instances in drop are left out, and so are
    calibration objects whose key values differ from only ({key: value},
    e.g. {NETWORK: NETWORK_LTE}), to keep the blob small."""
    if "VCCD" not in a.ch:
        return None
    o = a.ch["VCCD"][0]
    miid, pid, nsg = a.u32(o, 3)
    o += 12
    for _ in range(nsg):
        sgid, tsize, major, minor, mkt, ntab = a.u32(o, 6)
        if sgid == sg:
            break
        o += 8 + tsize
    else:
        return None

    # ckv data tables in the file
    tables, t = [], o + 24
    for _ in range(ntab):
        size, keytab, _dot, nobj = a.u32(t, 4)
        objs, q = [], t + 16
        for _ in range(nobj):
            lut, caldef, nd = a.u32(q, 3)
            pools = list(a.u32(q + 12, nd)) if nd > 1 else ([a.u32(q + 12)] if nd else [])
            d = a.ch["VCDE"][0] + caldef
            pairs = [a.u32(d + 4 + 8 * i, 2) for i in range(nd)]
            objs.append((lut, [(iid, p, po) for (iid, p), po in zip(pairs, pools) if iid not in drop]))
            q += 12 + 4 * nd
        kt = a.ch["VCKT"][0] + keytab
        nkeys = a.u32(kt)
        if only and nkeys:
            keys = [a.u32(kt + 4 + 4 * i) for i in range(nkeys)]
            def match(lut):
                lp = a.ch["VCLU"][0] + lut
                vals = [a.u32(lp + 8 + 4 * i) for i in range(nkeys)]
                return all(only.get(k, v) == v for k, v in zip(keys, vals))
            objs = [ob for ob in objs if match(ob[0])]
        tables.append((keytab, nkeys, objs))
        t += 4 + size

    persist = set()
    if "PPTC" in a.ch:
        p = a.ch["PPTC"][0]
        n = a.u32(p)
        persist = set(a.u32(p + 4, n)) if n > 1 else ({a.u32(p + 4)} if n else set())

    # Processing order: keyed tables, then the default table (index 0).
    order = [i for i, tb in enumerate(tables) if tb[1]] + [i for i, tb in enumerate(tables) if not tb[1]]
    referenced = []          # iids of the first object of each keyed table
    out_tables = []          # (keytab, [(lut, [(iid, pid, pool_off)])])
    for i in order:
        keytab, nkeys, objs = tables[i]
        default = nkeys == 0
        out_objs = []
        for k, (lut, params) in enumerate(objs):
            keep = []
            for iid, p, po in params:
                if default:
                    if iid in referenced:
                        continue
                elif k == 0:
                    referenced.append(iid)
                keep.append((iid, p, po))
            if keep:
                out_objs.append((lut, keep))
        if out_objs:
            out_tables.append((keytab, out_objs))

    # chunks
    keyids, luts, pool, info_tables = b"", b"", b"", b""
    pool_base = a.ch["POOL"][0]
    for keytab, objs in out_tables:
        kt = a.ch["VCKT"][0] + keytab
        nk = a.u32(kt)
        keytab_off = len(keyids)
        objs_blob = b""
        for lut, params in objs:
            lp = a.ch["VCLU"][0] + lut
            nv = a.u32(lp)
            lut_off = len(luts)
            luts += u32s(nv) + a.d[lp + 8:lp + 8 + 4 * nv]   # skip #entries (always 1)
            objs_blob += u32s(lut_off, len(params))
            for iid, p, po in params:
                objs_blob += u32s(len(pool), 1 if p in persist else 0)
                sz = a.u32(pool_base + po)
                data = a.d[pool_base + po + 4:pool_base + po + 4 + sz]
                pool += u32s(iid, p, sz, 0) + data + b"\0" * (-sz % 8)
        keyids += u32s(nk) + a.d[kt + 4:kt + 4 + 4 * nk]
        info_tables += u32s(12 + len(objs_blob), keytab_off, len(objs_blob), len(objs)) + objs_blob

    used = set()
    p = 0
    while p < len(keyids):
        n = struct.unpack_from("<I", keyids, p)[0]
        used.update(struct.unpack_from("<%dI" % n, keyids, p + 4))
        p += 4 + 4 * n
    mk = a.ch["VCMK"][0] + mkt
    nm = a.u32(mk)
    masters = [a.u32(mk + 4 + 8 * i, 2) for i in range(nm)]
    found = [m for m in masters if m[0] in used]
    master = u32s(len(found)) + b"".join(u32s(*m) for m in found)

    info = u32s(1, sg, 16 + len(info_tables), major, minor, 0, len(out_tables)) + info_tables
    payload = (info + u32s(len(master)) + master + u32s(len(keyids)) + keyids +
               u32s(len(luts)) + luts + u32s(len(pool)) + pool)
    return miid, pid, payload


def summary(a, sg, payload):
    n_tab = struct.unpack_from("<I", payload, 24)[0]
    return "sg 0x%08x: %d tables, %d bytes" % (sg, n_tab, len(payload))


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    names = os.path.join(os.path.dirname(os.path.abspath(__file__)), "names.json")
    a = A.Acdb(sys.argv[1], names)
    os.makedirs(sys.argv[2], exist_ok=True)
    for s in sys.argv[3:]:
        sg = int(s, 0)
        r = vcpm_blob(a, sg)
        if r is None:
            print("sg 0x%08x: no VCPM calibration" % sg)
            continue
        miid, pid, payload = r
        with open(os.path.join(sys.argv[2], "%08x.bin" % sg), "wb") as f:
            f.write(u32s(miid, pid, len(payload), 0) + payload + b"\0" * (-len(payload) % 8))
        print("%s, iid 0x%x pid 0x%08x" % (summary(a, sg, payload), miid, pid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
