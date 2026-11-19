#!/usr/bin/env python3
"""Build libcamera software ISP tuning files (Awb, Lsc, Ccm) from the stock CamX
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
    # The same factors take a white point measured after the stock shading
    # (stock AWB statistics) to one measured before it (ours): see awb().
    vign = (hm['g'] / hm['r'], hm['g'] / hm['b'])
    # Where a gain exceeds the 3.98 maximum, scale all three channels of that
    # cell together so the corner stays neutral instead of tinted.
    peak = np.maximum(np.maximum(res['r'], res['g']), res['b'])
    k = np.minimum(1.0, (255 / 64) / peak)
    return {c: np.clip(np.rint(v * k * 64), 32, 255).astype(int) for c, v in res.items()}, vign

# AWB reference points (refPtV1): ten (R/G, B/G) white points of the stock
# AWB, measured after black level and lens shading. Their illuminants were
# identified by mapping each point to xy chromaticity through the stock D65
# colour matrix: 0 and 9 are the ends of the search area (~15000+ and
# ~1900 K), 1 D75, 2 D65, 3 D50, 4-6 a fluorescent line (CW, TL84; off the
# Planckian locus, green side), 7 A, 8 horizon. The same order holds in
# every cupid bin. initDataV1 (start gains at 5000 K) equals point 3.
REFPT_CT = ((1, 7500), (2, 6500), (3, 5000), (7, 2850), (8, 2300))
REFPT_FLUO = (4, 5, 6)

def refpts(d, base, syms):
    sid = [s for s, (name, _, _) in syms.items() if name == 'refPtV1']
    assert len(sid) == 1
    _, off, size = syms[sid[0]]
    assert size == 144
    f = struct.unpack_from('<20f', d, base + off + 24)
    pts = [(f[2 * i], f[2 * i + 1]) for i in range(10)]
    # R/G rises and B/G falls from the high- to the low-CT end.
    assert all(0.1 < rg < 2 and 0.1 < bg < 2 for rg, bg in pts)
    assert all(pts[a][0] < pts[b][0] and pts[a][1] > pts[b][1]
               for (a, _), (b, _) in zip(REFPT_CT, REFPT_CT[1:]))
    return pts

def awb(pts, lscs):
    """CT curve for libcamera's Bayesian AWB: (ct, R gain, B gain).

    Our AWB statistics are frame means taken before lens shading, the stock
    reference points are white after the stock shading. A white wall's
    frame mean is darkened per channel by the vignetting, mean(1 / lsc), so
    the gain that makes it grey is the stock gain times mean(1 / lsc_g) /
    mean(1 / lsc_c) of the stock table for that CT (interpolated between the
    tables used, clamped at the ends). With the R/B scaling of the tables
    above, the centre of the frame then comes out neutral."""
    cts = [ct for ct, *_ in lscs]
    def vign(ct):
        return [np.interp(ct, cts, [v[i] for *_, v in lscs]) for i in (0, 1)]
    def gains(rg, bg, ct):
        kr, kb = vign(ct)
        return kr / rg, kb / bg
    curve = [(ct, *gains(*pts[i], ct)) for i, ct in REFPT_CT]
    # Extend the daylight end to 10000 K: log R/G and B/G are close to
    # linear in mired along the daylight locus (fit through D75, D65, D50).
    day = [(ct, pts[i]) for i, ct in REFPT_CT if ct >= 5000]
    mired = [1e6 / ct for ct, _ in day]
    ext = [float(np.exp(np.polyval(np.polyfit(mired, np.log([p[k] for _, p in day]), 1), 100)))
           for k in (0, 1)]
    curve.append((10000, *gains(*ext, 10000)))
    curve.sort()
    # How far the fluorescent points lie off the curve (in libcamera's
    # 1/gain space, green side): sets transverseNeg.
    poly = np.array([(1 / r, 1 / b) for _, r, b in curve])
    def dist(p):
        best = 1e9
        for a, b in zip(poly, poly[1:]):
            t = np.clip(np.dot(p - a, b - a) / np.dot(b - a, b - a), 0, 1)
            best = min(best, np.linalg.norm(p - (a + t * (b - a))))
        return best
    fluo = []
    for i in REFPT_FLUO:
        r, b = gains(*pts[i], 4000)
        fluo.append(dist(np.array((1 / r, 1 / b))))
    return curve, max(fluo)

AWB_MODES = (('Auto', 2300, 8000), ('Incandescent', 2300, 3000), ('Tungsten', 3000, 3500),
             ('Fluorescent', 3800, 4700), ('Indoor', 3000, 5000), ('Daylight', 5000, 6500),
             ('Cloudy', 6500, 8000))

def ct_for(lo, hi):
    if lo <= 1: return 2000
    if hi >= 9000 and lo >= 5500: return 6500
    return int(round((lo + hi) / 2 / 50) * 50)

def build(cam):
    d, base, syms, order = camxmod.load(os.path.join(sys.argv[1], 'com.qti.tuned.%s.bin' % cam['bin']))
    ccms = [(ct_for(lo, hi), lo, hi, ccm_at(d, o)) for lo, hi, o, _ in regions(d, base, syms, *cam['ccm'])]
    lscs = [(ct, lo, hi, o, *lsc_at(d, o)) for (lo, hi, o, _), ct in zip(regions(d, base, syms, *cam['lsc'][:2]), cam['lsc'][2]) if ct]
    curve, fluo = awb(refpts(d, base, syms), lscs)
    neg = np.ceil(fluo * 1.1 * 100) / 100
    L = ['# SPDX-License-Identifier: CC0-1.0']
    L += ['# ' + x for x in cam['desc']]
    L += ['# Generated from the stock Chromatix tuning (com.qti.tuned.%s):' % cam['bin'],
          '# AWB colour temperature curve from the refPtV1 white points,',
          '# colour matrices from cc13_ipe_v2 for CCT regions ' + ', '.join('%g-%g' % (lo, hi) for _, lo, hi, _ in ccms) + ' K,',
          '# lens shading from lsc41 (%s K regions, R/Gr/Gb/B 17x13 resampled' % ', '.join('%g-%g' % (lo, hi) for _, lo, hi, *_ in lscs),
          '# to 17x17, G = (Gr + Gb) / 2, R and B scaled so the table keeps the',
          '# frame-average colour, as AWB statistics are taken before shading',
          '# correction). Tabular Lsc values are stored quantised as UQ<2,6>',
          '# (64 = 1.0, max 255).'] + ['# ' + x for x in cam.get('note', [])] + [
          '%YAML 1.1', '---', 'version: 1', 'algorithms:', '  - BlackLevel:']
    if cam.get('af'): L += ['  - Af:'] + ['      ' + x for x in cam.get('af_tuning', [])]
    L += ['  - Awb:',
          '      # Bayesian AWB along the stock white points (refPtV1: D75, D65,',
          '      # D50, A, horizon; 10000 K extrapolated), converted to gains for',
          '      # statistics taken before lens shading. A single frame mean is',
          '      # measured, so no lux priors; the search may leave the curve towards',
          '      # green as far as the stock fluorescent points (CW, TL84).',
          '      algorithm: bayes',
          '      AwbMode:']
    for mode, lo, hi in AWB_MODES:
        L += ['        %s:' % mode, '          lo: %d' % lo, '          hi: %d' % hi]
    L += [
          '      priors:',
          '        - lux: 0',
          '          ct: [ 2000, 13000 ]',
          '          probability: [ 1.0, 1.0 ]',
          '      colourGains:']
    for ct, r, b in curve:
        L.append('        - ct: %d' % ct)
        L.append('          gains: [ %.4f, %.4f ]' % (r, b))
    L += ['      transversePos: 0.02',
          '      transverseNeg: %.2f' % neg,
          '  - Lsc:', '      type: table', '      sets:']
    for ct, lo, hi, o, t, _ in lscs:
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
    for ct, lo, hi, o, t, v in lscs:
        print(cam['name'], 'lsc', ct, hex(o), {k: (int(x.min()), int(x.max())) for k, x in t.items()}, 'vign %.3f %.3f' % v, file=sys.stderr)
    for ct, r, b in curve:
        print(cam['name'], 'awb', ct, 'R %.3f B %.3f' % (r, b), file=sys.stderr)
    print(cam['name'], 'awb fluorescent offset %.3f' % fluo, file=sys.stderr)
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
         ccm=(0xe952aa, 4), lsc=(0xe62566, 3, (2850, 4000, 5400)),
         af_tuning=['# Lens range from the module EEPROM: infinity and macro (10 cm) DAC',
                    '# 170 and 802 in 10-bit units, about 680 and 3208 in the units of the',
                    '# 12-bit focus control, with a margin on both sides.',
                    'lensMin: 600', 'lensMax: 3300',
                    '# The lens is 10-bit, driven as 12-bit: 8 is 2 real steps.',
                    'fineStep: 8',
                    '# Frames exposed while the lens moves are skipped.',
                    'settleFrames: 2']),
    dict(name='ov13b10', bin='cupid_sunny_ov13b10_ultra', desc=['OmniVision OV13B10, Xiaomi 12 ultra-wide camera (sunny module).'],
         ccm=(0x5d453e, 5), lsc=(0x5abb7a, 3, (2850, 4000, 6500))),
]
# The lists above are the first "trigger" list in each bin with three or more
# CCT regions whose payloads pass ccm_at / lsc_at (later lists repeat them for
# other gain and lux regions).
if __name__ == '__main__':
    for cam in CAMS:
        open(os.path.join(sys.argv[2], cam['name'] + '.yaml'), 'w').write(build(cam))
