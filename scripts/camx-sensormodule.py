#!/usr/bin/env python3
"""Decode register settings from a CamX com.qti.sensormodule.*.bin
(vendor/lib64/camera/ of the stock ROM).

  scripts/camx-sensormodule.py MODULE.bin [-v]

Prints every regSetting array with the name of the symbol before it (the
resolution tables show up after "integrationInfo", one per mode).

Format
(Parameter Parser V3.4, reverse engineered):
  header @0xa4: n sections, then (flag, offset, size) per section;
  section 1 = symbol table, 56-byte entries: id, name[32], 3 ints, offset, size
  section 2 = data; regSetting arrays are 40-byte entries:
    hasSlave, slaveSym, regAddr, nData, dataSym, addrType, dataType, op, nDelay, delaySym
  dataSym/delaySym are symbol ids whose (offset,size) point at u32 values."""
import struct, sys
def load(path):
    d = open(path, 'rb').read()
    n = struct.unpack_from('<I', d, 0xa4)[0]
    secs = [struct.unpack_from('<3I', d, 0xa8 + 12 * i) for i in range(n)]
    # entries are (?, offset, size)
    symoff, symsize = secs[0][1], secs[0][2]
    base = secs[1][1]
    syms = {}
    order = []
    for k in range(symsize // 56):
        a = symoff + k * 56
        sid = struct.unpack_from('<I', d, a)[0]
        name = d[a + 4:a + 36].split(b'\0')[0].decode(errors='replace')
        _, _, _, off, size = struct.unpack_from('<5i', d, a + 36)
        syms[sid] = (name, off, size)
        order.append(sid)
    return d, base, syms, order
def vals(d, base, syms, sid):
    name, off, size = syms[sid]
    return list(struct.unpack_from('<%dI' % (size // 4), d, base + off)) if size >= 4 else []
OPS = {0: 'W', 1: 'DELAY', 2: 'POLL'}
def regsettings(path):
    d, base, syms, order = load(path)
    ctx = None
    out = []
    for sid in order:
        name, off, size = syms[sid]
        if name in ('slaveAddr', 'registerData', 'delayUs'):
            continue
        if name != 'regSetting':
            ctx = name
            continue
        regs = []
        for e in range(size // 40):
            w = struct.unpack_from('<10I', d, base + off + 40 * e)
            hs, sl, addr, nd, dsym, at, dt, op, ndl, dlsym = w
            data = vals(d, base, syms, dsym)
            delay = vals(d, base, syms, dlsym) if ndl else []
            slave = vals(d, base, syms, sl) if hs else []
            regs.append((addr, data, at, dt, op, delay[0] if delay else 0, slave))
        out.append((ctx, sid, regs))
    return out
if __name__ == '__main__':
    for ctx, sid, regs in regsettings(sys.argv[1]):
        print('== %s (sym %d), %d regs' % (ctx, sid, len(regs)))
        if len(sys.argv) > 2 and len(regs) > 3:
            for r in regs:
                print('  0x%04x %s a%d d%d %s%s%s' % (r[0], ' '.join('0x%02x' % v for v in r[1]), r[2], r[3], OPS.get(r[4], r[4]), ' delay=%d' % r[5] if r[5] else '', ' slave=%s' % r[6] if r[6] else ''))
        else:
            for r in regs:
                print('  0x%04x %s %s%s' % (r[0], ' '.join('0x%02x' % v for v in r[1]), OPS.get(r[4], r[4]), ' delay=%d' % r[5] if r[5] else ''))
