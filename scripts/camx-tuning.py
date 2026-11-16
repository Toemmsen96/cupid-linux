#!/usr/bin/env python3
"""Build libcamera software ISP tuning files (Lsc, Ccm) from the stock CamX
Chromatix tuned bins (vendor/lib64/camera/com.qti.tuned.cupid_*.bin).

  camx-tuning.py <dir with the tuned bins> <output dir>

Parameter Parser V3.4 layout as used by scripts/camx-sensormodule.py. Region
lists are 24-byte entries (start, end, u32, sym, u32, dataSym); the data
symbol gives the payload offset, and payloads are shared between regions,
so they must be resolved through the symbol table, not by position. The
region-list offsets below were found by hand for the cupid bins."""
import importlib.util, os, struct, sys
import numpy as np
_spec = importlib.util.spec_from_file_location(
    'camxmod', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'camx-sensormodule.py'))
camxmod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(camxmod)

def regions(d, base, syms, off, n):
    out = []
    for k in range(n):
        lo, hi, _, _, _, sym = struct.unpack_from('<2f4I', d, off + 24 * k)
        out.append((lo, hi, base + syms[sym][1], sym))
    return out

def ccm_at(d, off):
    m = struct.unpack_from('<9f', d, off)
    for r in range(3):
        assert abs(sum(m[3 * r:3 * r + 3]) - 1) < 0.03, (hex(off), m)
    assert all(1 < m[i] < 3.5 for i in (0, 4, 8)), (hex(off), m)
    return m

def lsc_at(d, off):
    a = np.frombuffer(d[off:off + 884 * 4], dtype='<f4').reshape(4, 13, 17).astype(float)
    assert np.all((a > 0.9) & (a < 8)) and abs(a[0, 6, 8] - 1) < 0.05, hex(off)
    r, gr, gb, b = a
    ys = np.linspace(0, 12, 17)
    res = {}
    for name, t in (('r', r), ('g', (gr + gb) / 2), ('b', b)):
        u = np.empty((17, 17))
        for x in range(17):
            u[:, x] = np.interp(ys, np.arange(13), t[:, x])
        res[name] = np.minimum(u, 255 / 64)
    # The software ISP gathers AWB statistics before lens shading. Scale R
    # and B so the table does not shift the frame-average colour: with grey
    # world, the error per channel is mean(1/lsc_g) / mean(1/lsc_c).
    hm = {k: np.mean(1 / v) for k, v in res.items()}
    res = {k: v * hm[k] / hm['g'] for k, v in res.items()}
    # Where a gain exceeds the 3.98 maximum, scale all three channels of that
    # cell together so the corner stays neutral instead of tinted.
    peak = np.maximum(np.maximum(res['r'], res['g']), res['b'])
    k = np.minimum(1.0, (255 / 64) / peak)
    return {c: np.clip(np.rint(v * k * 64), 32, 255).astype(int) for c, v in res.items()}

def ct_for(lo, hi):
    if lo <= 1: return 2000
    if hi >= 9000 and lo >= 5500: return 6500
    return int(round((lo + hi) / 2 / 50) * 50)

def build(cam):
    d, base, syms, order = camxmod.load(os.path.join(sys.argv[1], 'com.qti.tuned.%s.bin' % cam['bin']))
    ccms = [(ct_for(lo, hi), lo, hi, ccm_at(d, o)) for lo, hi, o, _ in regions(d, base, syms, *cam['ccm'])]
    lscs = [(ct, lo, hi, o, lsc_at(d, o)) for (lo, hi, o, _), ct in zip(regions(d, base, syms, *cam['lsc'][:2]), cam['lsc'][2]) if ct]
    L = ['# SPDX-License-Identifier: CC0-1.0']
    L += ['# ' + x for x in cam['desc']]
    L += ['# Generated from the stock Chromatix tuning (com.qti.tuned.%s):' % cam['bin'],
          '# colour matrices from cc13_ipe_v2 for CCT regions ' + ', '.join('%g-%g' % (lo, hi) for _, lo, hi, _ in ccms) + ' K,',
          '# lens shading from lsc41 (%s K regions, R/Gr/Gb/B 17x13 resampled' % ', '.join('%g-%g' % (lo, hi) for _, lo, hi, _, _ in lscs),
          '# to 17x17, G = (Gr + Gb) / 2, R and B scaled so the table keeps the',
          '# frame-average colour, as AWB statistics are taken before shading',
          '# correction). Tabular Lsc values are stored quantised as UQ<2,6>',
          '# (64 = 1.0, max 255).'] + ['# ' + x for x in cam.get('note', [])] + [
          '%YAML 1.1', '---', 'version: 1', 'algorithms:', '  - BlackLevel:']
    if cam.get('af'): L.append('  - Af:')
    L += ['  - Awb:', '  - Lsc:', '      type: table', '      sets:']
    for ct, lo, hi, o, t in lscs:
        L.append('        - ct: %d' % ct)
        for name in ('r', 'g', 'b'):
            v = t[name].reshape(-1)
            rows = [', '.join('%3d' % x for x in v[i:i + 17]) for i in range(0, 289, 17)]
            L.append('          %s: [ %s ]' % (name, ',\n               '.join(rows)))
    L += ['  - Ccm:', '      ccms:']
    for ct, lo, hi, m in ccms:
        L += ['        - ct: %d' % ct,
              '          ccm: [ %8.5f, %8.5f, %8.5f,' % m[0:3],
              '                 %8.5f, %8.5f, %8.5f,' % m[3:6],
              '                 %8.5f, %8.5f, %8.5f ]' % m[6:9]]
    L += ['  - Adjust:', '  - Agc:', '...', '']
    for ct, lo, hi, o, t in lscs:
        print(cam['name'], 'lsc', ct, hex(o), {k: (int(v.min()), int(v.max())) for k, v in t.items()}, file=sys.stderr)
    for ct, lo, hi, m in ccms:
        print(cam['name'], 'ccm', ct, '%g-%g' % (lo, hi), ' '.join('%.3f' % x for x in m), file=sys.stderr)
    return '\n'.join(L)

CAMS = [
    dict(name='ov32b40', bin='cupid_ofilm_ov32b40_front', desc=['OmniVision OV32B40, Xiaomi 12 front camera (ofilm module).'],
         ccm=(0x3fad36, 5), lsc=(0x3cf332, 3, (2850, 4000, 6500))),
    dict(name='s5k5e9', bin='cupid_sunny_s5k5e9_macro', af=True, desc=['Samsung S5K5E9, Xiaomi 12 macro camera (sunny module).'],
         ccm=(0x195036, 5), lsc=(0x16f3ea, 3, (None, 4000, 6500)),
         note=['The 2600-3100 K shading table is left out: it over-corrects this unit',
               '(corners at ~160 % of the centre), the stock pipeline likely uses the',
               'module OTP shading data instead.']),
    dict(name='imx766', bin='cupid_semco_imx766_wide', af=True, desc=['Sony IMX766, Xiaomi 12 main camera (semco module).'],
         ccm=(0xe952aa, 4), lsc=(0xe62566, 3, (2850, 4000, 5400))),
]
if __name__ == '__main__':
    for cam in CAMS:
        open(os.path.join(sys.argv[2], cam['name'] + '.yaml'), 'w').write(build(cam))
