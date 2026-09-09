"""Channel-map test #4: is a DATA-DERIVED within-shank order a REGULAR routing on the connector pins?

Asked by the user on 2026-09-08 ("SF8 不错，这种有物理接线支持么"). A data-derived order (lfp_profile_check.py --derive-xml) is a depth
order without a pin table. If the probe's real pinout is regular, consecutive sites land on neighbouring pins of the 2 x 8 block that a shank
occupies on the RHD2164 grid, and one of the regular routings reproduces the smooth LFP profiles. Tried per shank: zigzag along pin columns,
serpentine rows, row-major, the ProbeMaps A4x16 centre-outward fan-out, and the four ProbeMaps 'version1' shank routings, each under its 8
symmetries (reverse, row swap, mirror) = 64 routings; scored like test #3 (spw tv + ripple tv + theta tv on the staged 10-min copy, 3.0 =
all monotonic) and compared with the data order; also the fraction of consecutive data-order sites that sit on neighbouring pins (chance
~18 %). A NEGATIVE result does not exclude an irregular vendor pinout; that needs the probe's site-map / package pin table.

Usage: python ephys/wiring_pattern_check.py <staged_raw_dir> <xml> [dead columns ...]
   e.g. python ephys/wiring_pattern_check.py E:/3rd_rat_spikes/analysis/stage/SF08/18_20260903_060030.122__w0s_600s ephys/configs/xml/SF08_A4x16-Lin_dataorder_20260908.xml 32
Result 2026-09-08 (SF08): data order ranks 1 on every shank; best regular routing scores 6.0-9.9 vs 3.8-5.7; neighbouring-pin fraction 1-3 of
15 (chance level) -> no regular routing explains SF08's order.
"""
import sys, itertools; sys.path.insert(0, "ephys")
from pathlib import Path
import numpy as np
import lfp_profile_check as L
from probe_map_check import INTAN64_PINS, PROBEMAPS, PROBE_XML, load_groups, rotation_permutation
from _common import ephys_block
raw = Path(sys.argv[1]); xml_path = sys.argv[2]; dead = set(int(c) for c in sys.argv[3:])
lfp, fs, fw, C = L.load_raw_lfp(raw, 10.0, 0.0, ephys_block("2026c"))
live = np.array([c for c in range(64) if c not in dead])
peaks, env, rip_live = L.detect_ripples(lfp, fs, live); spw, rp, n = L.profiles(lfp, fs, peaks, env, live)
theta, tpow, ref_col, nwin = L.theta_profile(lfp, fs, live)
P = rotation_permutation(1, 0); inv = np.empty(64, int); inv[P] = np.arange(64)
def pin(c):            # column -> (row 0-3, pin col 0-15)
    i = INTAN64_PINS.index(int(inv[c])); return i // 16, i % 16
def local(c):          # -> (block, r in {0,1}, j in 0..7)
    r, k = pin(c); return (r // 2, k // 8), r % 2, k % 8
def tv3(order):
    o = [c for c in order if c not in dead]
    a, fl = L.tv_and_flips(spw[o]); b, _ = L.tv_and_flips(rp[o]); t = L.tv_phase(theta[o])
    return a + b + (t if not np.isnan(t) else 3.0), a, b, t, fl
# regular routing patterns: site k (0..15) -> (r, j) inside a 2x8 block
pat = {}
pat["zigzag_cols"] = [(k % 2, k // 2) for k in range(16)]                       # c0r0 c0r1 c1r0 c1r1 ...
pat["serpentine_rows"] = [(0, j) for j in range(8)] + [(1, j) for j in range(7, -1, -1)]
pat["rowmajor"] = [(0, j) for j in range(8)] + [(1, j) for j in range(8)]
pat["fanout_center"] = [(1,4),(0,3),(0,4),(1,3),(1,5),(0,2),(0,5),(1,2),(1,6),(0,1),(0,6),(1,1),(1,7),(0,0),(0,7),(1,0)]  # ProbeMaps A4x16 connector-B shank
gv1 = load_groups(PROBEMAPS / PROBE_XML["A4x16-Lin-5mm-50s-300"][0])
for si, g in enumerate(gv1, 1):                                                  # the four ProbeMaps v1 shank routings, as patterns
    loc = []
    for ch in g:
        i = INTAN64_PINS.index(ch); r, k = i // 16, i % 16; loc.append((r % 2, k % 8))
    pat[f"probemaps_v1_shank{si}"] = loc
def symmetries(p):
    for rev in (False, True):
        for rsw in (False, True):
            for mir in (False, True):
                q = [((1 - r) if rsw else r, (7 - j) if mir else j) for r, j in p]
                if rev: q = q[::-1]
                yield f"{'rev+' if rev else ''}{'rowswap+' if rsw else ''}{'mirror' if mir else ''}".strip('+') or "as-is", q
groups = load_groups(xml_path)
print(f"{n} ripples; data-derived order vs regular routings (score = spw tv + ripple tv + theta tv; 3.0 = all monotonic)")
for gi, g in enumerate(groups, 1):
    glive = [c for c in g if c not in dead]
    blocks = {local(c)[0] for c in glive}
    assert len(blocks) == 1, blocks
    blk = blocks.pop(); cell = {local(c)[1:]: c for c in glive}
    tot, a, b, t, fl = tv3(glive)
    adj = [abs(local(x)[1] - local(y)[1]) + abs(local(x)[2] - local(y)[2]) == 1 for x, y in zip(glive, glive[1:])]
    deep = glive[-6:]; adj_deep = [abs(local(x)[1] - local(y)[1]) + abs(local(x)[2] - local(y)[2]) == 1 for x, y in zip(deep, deep[1:])]
    print(f"\n== group {gi} (connector {'AB'[blk[0]]}, pin cols {blk[1]*8}-{blk[1]*8+7}): data order score {tot:.2f} (spw {a:.2f} rip {b:.2f} th {t:.2f}, flips {fl})")
    print("   data order in pins (r,j): " + " ".join(f"{c}:({local(c)[1]},{local(c)[2]})" for c in glive))
    print(f"   consecutive sites on NEIGHBOURING pins: {sum(adj)}/{len(adj)} overall, {sum(adj_deep)}/{len(adj_deep)} among the deepest 6 (chance ~ {100*22/120:.0f} %)")
    res = []
    for name, p in pat.items():
        for sym, q in symmetries(p):
            order = [cell[rj] for rj in q if rj in cell]
            if len(order) < len(glive): continue
            sc = tv3(order); res.append((sc[0], name, sym, order, sc))
    res.sort(key=lambda x: x[0])
    for tot2, name, sym, order, sc in res[:3]:
        print(f"   best regular: {name} [{sym}] score {tot2:.2f} (spw {sc[1]:.2f} rip {sc[2]:.2f} th {sc[3]:.2f} flips {sc[4]}): " + " ".join(f"{c}:{spw[c]:+.0f}" for c in order))
    print(f"   ({len(res)} regular routings tried; data order would rank {sum(1 for r in res if r[0] < tot) + 1})")
