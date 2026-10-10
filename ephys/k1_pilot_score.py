"""Score the K1 pilot (plan implementation_plan/2026-10-09-k1-block-sorting.md, section "Pilot").

Question: is one K1 run per whole block (up to ~12 h) as good as sorting shorter pieces? K1 on GPU is not run-to-run
deterministic (atomicAdd), so every comparison is judged against the agreement between two runs of the SAME whole
block (r1 vs r2), the baseline.

Comparison of sort A against sort B on a common time window. Reference units of A are clusters with:
- >= MIN_SPIKES spikes in the window;
- ISI violations (< 1.5 ms) <= 1 %.

For each reference unit:
- Matching: each of its spikes is matched to the nearest spike of B within +-TOL samples (any B cluster).
- Union of B clusters: every B cluster with >= 50 % of its window spikes matched to the unit, plus the B cluster that
  received the most matches. This absorbs K1's oversplitting.
- recovery = matched spikes that fall in the union / the unit's spikes.
- purity = matched spikes in the union / all window spikes of the union.
- agree = recovery >= 0.9 and purity >= 0.9.

Pairs per block:
- baseline: whole_r1 vs whole_r2 (whole span);
- whole vs part: whole_r1 vs first2of3 (its span) and whole_r1 vs last2of3 (its span), both directions;
- overlap: first2of3 vs last2of3 on the middle third.
For SF10, whole_r1 is also compared with whole_wr32 and whole_shank (settings), but those are reported only.

Decision (fixed before the scores): a whole-block sort is kept if, on every block, its median recovery and purity
against the parts are within 0.05 of the r1-vs-r2 baseline, and its agree fraction is >= the baseline's minus 0.10.

Usage (server, PreprocessPipeline venv; reads <pilot>/<block>/<variant>/kilosort1 and <blocks>/<block>/*.segments.json):
  python ephys/k1_pilot_score.py --pilot /workdir/hc997/ephys_2026c/k1_pilot --blocks-dir /workdir/hc997/ephys_2026c/k1_blocks
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

TOL = 10            # samples (0.5 ms at 20 kHz)
MIN_SPIKES = 300
ISI_S = 0.0015
ISI_MAX = 0.01


def load(phy: Path, offset: int):
    t = np.load(phy / "spike_times.npy").ravel().astype(np.int64) + offset
    c = np.load(phy / "spike_clusters.npy").ravel().astype(np.int64)
    o = np.argsort(t, kind="stable")
    return t[o], c[o]


def window(t, c, lo, hi):
    m = (t >= lo) & (t < hi)
    return t[m], c[m]


def reference_units(t, c, fs=20000.0):
    out = []
    for cid in np.unique(c):
        tt = t[c == cid]
        if tt.size < MIN_SPIKES:
            continue
        if np.mean(np.diff(tt) < ISI_S * fs) <= ISI_MAX:
            out.append(cid)
    return out


def compare(ta, ca, tb, cb):
    """Per reference unit of A: recovery and purity in B (union of B clusters)."""
    rows = []
    if tb.size == 0:
        return rows
    b_counts = pd.Series(cb).value_counts()
    for cid in reference_units(ta, ca):
        tt = ta[ca == cid]
        k = np.searchsorted(tb, tt)
        k0 = np.clip(k - 1, 0, tb.size - 1); k1 = np.clip(k, 0, tb.size - 1)
        d0 = np.abs(tb[k0] - tt); d1 = np.abs(tb[k1] - tt)
        nn = np.where(d0 <= d1, k0, k1); dist = np.minimum(d0, d1)
        hit = dist <= TOL
        if not hit.any():
            rows.append(dict(unit=int(cid), n=int(tt.size), recovery=0.0, purity=0.0, n_union=0)); continue
        hit_b = pd.Series(cb[nn[hit]]).value_counts()
        union = [b for b, n in hit_b.items() if n >= 0.5 * b_counts[b]]
        best = hit_b.index[0]
        if best not in union:
            union.append(best)
        in_union = int(hit_b[hit_b.index.isin(union)].sum())
        rows.append(dict(unit=int(cid), n=int(tt.size), recovery=in_union / tt.size,
                         purity=in_union / int(b_counts[union].sum()), n_union=len(union)))
    return rows


def summarize(rows, label, block):
    df = pd.DataFrame(rows)
    if df.empty:
        return dict(block=block, pair=label, n_units=0)
    agree = (df.recovery >= 0.9) & (df.purity >= 0.9)
    return dict(block=block, pair=label, n_units=len(df), recovery_med=df.recovery.median(),
                purity_med=df.purity.median(), agree_frac=agree.mean(), union_med=df.n_union.median())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pilot", required=True)
    ap.add_argument("--blocks-dir", required=True)
    ap.add_argument("--out", default=None, help="default <pilot>/k1_pilot_scores.{csv,md}")
    a = ap.parse_args()
    pilot, bdir = Path(a.pilot), Path(a.blocks_dir)
    summ, per_unit = [], []
    for bpath in sorted(p for p in pilot.iterdir() if p.is_dir() and not p.name.startswith("_")):
        block = bpath.name
        whole = json.loads((bdir / block / f"{block}.segments.json").read_text())
        N = whole["n_samples"]
        spans = {"whole_r1": (0, N), "whole_r2": (0, N), "whole_wr32": (0, N), "whole_shank": (0, N),
                 "first2of3": (0, int(0.6667 * N)), "last2of3": (int(0.3333 * N), N)}
        sorts = {}
        for v, (lo, hi) in spans.items():
            phy = bpath / v / "kilosort1"
            if v == "whole_shank":
                parts = sorted(p for p in bpath.glob(f"{v}/kilosort1_*") if (p / "spike_times.npy").exists())
                if parts:   # per-shank folders: concatenate with cluster ids made unique
                    ts, cs = [], []
                    for i, p in enumerate(parts):
                        t, c = load(p, 0); ts.append(t); cs.append(c + 100000 * i)
                    t = np.concatenate(ts); c = np.concatenate(cs); o = np.argsort(t, kind="stable")
                    sorts[v] = (t[o], c[o], lo, hi)
                continue
            if (phy / "spike_times.npy").exists():
                t, c = load(phy, lo)
                sorts[v] = (t, c, lo, hi)
        pairs = [("whole_r1", "whole_r2", None, "baseline r1 vs r2"),
                 ("whole_r2", "whole_r1", None, "baseline r2 vs r1"),
                 ("first2of3", "whole_r1", "first2of3", "part first -> whole"),
                 ("whole_r1", "first2of3", "first2of3", "whole -> part first"),
                 ("last2of3", "whole_r1", "last2of3", "part last -> whole"),
                 ("whole_r1", "last2of3", "last2of3", "whole -> part last"),
                 ("first2of3", "last2of3", "overlap", "overlap first -> last"),
                 ("last2of3", "first2of3", "overlap", "overlap last -> first"),
                 ("whole_r1", "whole_wr32", None, "settings: lab -> whitening 32"),
                 ("whole_r1", "whole_shank", None, "settings: lab -> per shank")]
        for A, B, win, label in pairs:
            if A not in sorts or B not in sorts:
                continue
            if win is None:
                lo, hi = 0, N
            elif win == "overlap":
                lo, hi = int(0.3333 * N), int(0.6667 * N)
            else:
                lo, hi = sorts[win][2], sorts[win][3]
            ta, ca = window(sorts[A][0], sorts[A][1], lo, hi)
            tb, cb = window(sorts[B][0], sorts[B][1], lo, hi)
            rows = compare(ta, ca, tb, cb)
            for r in rows:
                r.update(block=block, pair=label)
            per_unit += rows
            summ.append(summarize(rows, label, block))
        for v, (t, c, lo, hi) in sorts.items():
            summ.append(dict(block=block, pair=f"sort {v}", n_units=len(reference_units(t, c)),
                             spikes=int(t.size), clusters=int(np.unique(c).size)))
    out = Path(a.out) if a.out else pilot / "k1_pilot_scores"
    pd.DataFrame(per_unit).to_csv(str(out) + "_units.csv", index=False)
    s = pd.DataFrame(summ)
    s.to_csv(str(out) + ".csv", index=False)
    pd.set_option("display.width", 220)
    print(s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
