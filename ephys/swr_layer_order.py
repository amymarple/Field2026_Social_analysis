r"""Within-shank site order from the SWR layer profile by SERIATION (user rule 2026-10-05: the ripple gradient where there are
ripples, the sharp-wave gradient where there is a sharp wave; validated blind on the user's correct-order session HYC3 day26).

Physiology this relies on (literature summary in change_log/2026-09-29-sf07-order-from-lfp-reference-windows.md):
  - ripple amplitude peaks in mid stratum pyramidale (site 0 in Mizuseki 2011) and is flat over +-1 site; the ripple keeps its
    phase above and through the layer and REVERSES 150-200 um below it, where its envelope grows again (Csicsvari 1999,
    Schomburg 2012) -> the envelope alone is ambiguous below the layer, the signed ripple is not;
  - the sharp wave is positive in oriens / pyramidale, reverses just below the layer, is most negative ~200 um below the
    reversal (mid-radiatum) and weakens toward lacunosum-moleculare (Buzsaki 1986, Suzuki & Smith 1987, Oliva 2016): it FOLDS
    below the radiatum trough;
  - theta phase is constant above the layer and shifts below it, ~180 deg by SLM where theta power peaks (Csicsvari 1999);
  - a reference that picks up the sharp wave adds the same value to every site: signs move, differences do not (Liu 2022).

Features per site (from `lfp_profile_check.py --save-profile`): S = ripple-triggered sharp wave (uV); Rs = SIGNED ripple =
ripple amplitude x corr(site, the shank's ripple-maximum site) (`ripple_corr`); theta phase; log10 theta power. Each feature is
scaled by its range on the shank (theta: circular range). Order = the SHORTEST OPEN PATH through the sites in that space (exact
Held-Karp, <= 16 live sites): where a feature is flat (ripple far above the layer, sharp wave beyond its peaks) the others carry
the order; only differences enter, never signs. Several profiles of one animal (other days / depths): their distance matrices
are summed - the site order is the wiring and does not change when the probe moves - giving one consensus order; each
profile is weighted by its ripple contrast (`contrast_weight`), so a noise-dominated day cannot pull a clear one.

The path is constrained to keep the (mean) signed ripple UNIMODAL along it (`unimodal_path`): the ripple falls away from the
layer on both sides, so the path cannot jump across the steep layer step and glue the oriens run to the radiatum run
(template WT2 shank 3); `--method plain` = shortest path only.
Orientation (which end is the top), votes summed over the profiles, each relative to the ripple maximum p along the path:
  ripple  the side holding sites with a reversed ripple (corr < -0.1) is the bottom (weight 2);
  theta   the side whose theta phase departs more from p's, compared at equal distances from p, is the bottom;
  spw     the sharp-wave maximum lies at or above p (half weight);
  ratio   |dS|/|dR| (sharp-wave range over ripple range) is large below the layer (19-75 on the templates) and small above
          it (2.5-4.5); with two sides the larger is the bottom, with one side the rest is below p when > 8 (weight 1.5).
  The ripple, theta and ratio votes of a profile are scaled by its ripple contrast w = clip(max/p10 - 1, 0, 2) / 2: a day
  without a ripple gradient (SF11 after its advances) cannot tell which end is the layer.
Limits seen on the template: the fold below the radiatum trough and featureless runs (cortex) are not ordered reliably; isolated
bad sites (no correlation, odd theta) can be misplaced.

Dead / skipped columns and --exclude columns are not ordered: each is re-inserted after the live column that precedes it in the
reference order (the first --orders XML), keeping the user's placement of dead pace makers and bridged duplicates. Excluded
columns stay live in the XML. --dead-at-gaps instead puts each dead column at the largest remaining step of the consensus path
(pace maker, never at an end), for animals whose reference order says nothing about the dead columns (SF09).

Usage: python ephys/swr_layer_order.py --profiles A.npz [B.npz ...] --orders NAME=file.xml [NAME2=...] [--shanks 2 3] [--exclude COL ...]
       [--xml-out OUT.xml] [--csv-out OUT.csv] [--label TEXT]
The first --orders XML gives the shank membership, the group order and the dead/skip flags.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))

NEG_CORR = -0.1
RATIO_BELOW = 8.0


def wrap(d):
    return (np.asarray(d, dtype=float) + 180.0) % 360.0 - 180.0


def circ_range(th: np.ndarray) -> float:
    """Smallest arc (deg) holding all phases = 360 - the largest gap between the sorted phases."""
    t = np.sort(np.mod(th, 360.0)); gaps = np.diff(np.r_[t, t[0] + 360.0])
    return float(360.0 - gaps.max())


def read_groups(xml: Path) -> tuple[list[list[int]], set[int]]:
    raw = Path(xml).read_bytes()
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:                       # Neuroscope re-saves can carry cp1252 bytes under a UTF-8 header
        txt = raw.decode("cp1252")
    r = ET.fromstring(txt.split("?>", 1)[1] if txt.lstrip().startswith("<?xml") else txt)
    gs = r.findall("./anatomicalDescription/channelGroups/group")
    groups = [[int(c.text) for c in g.findall("channel")] for g in gs]
    skip = {int(c.text) for g in gs for c in g.findall("channel") if c.get("skip") == "1"}
    return groups, skip


def features(z, chans: list[int]) -> dict:
    """Per-site features of one profile for the live columns `chans` of one shank."""
    S = z["spw_uV"][chans].astype(float); R = z["ripple_uV"][chans].astype(float)
    TH = z["theta_phase_deg"][chans].astype(float); TP = np.log10(np.maximum(z["theta_power_uV2"][chans].astype(float), 1e-9))
    p = int(np.argmax(R))
    corr = z["ripple_corr"][chans[p], chans].astype(float) if "ripple_corr" in z.files else np.ones(len(chans))
    return {"S": S, "R": R, "Rs": R * corr, "corr": corr, "TH": TH, "TP": TP, "p": p}


def contrast_weight(f: dict) -> float:
    """Consensus weight of one profile on one shank from its ripple contrast (max / 10th percentile): 1 for a clear layer
    profile, small for a day whose ripple is flat noise."""
    return float(np.clip((f["R"].max() / max(np.percentile(f["R"], 10), 1e-9) - 1.0) / 3.0, 0.05, 1.0))


def dist(f: dict) -> np.ndarray:
    D = np.zeros((len(f["S"]),) * 2)
    for key in ("S", "Rs", "TP"):
        v = f[key]; D += ((v[:, None] - v[None, :]) / (np.ptp(v) + 1e-9)) ** 2
    if np.all(np.isfinite(f["TH"])):
        D += (wrap(f["TH"][:, None] - f["TH"][None, :]) / max(circ_range(f["TH"]), 1e-9)) ** 2
    return np.sqrt(D)


def shortest_path(D: np.ndarray) -> list[int]:
    """Exact shortest open Hamiltonian path (Held-Karp DP over subsets)."""
    n = len(D)
    if n <= 2:
        return list(range(n))
    dp = np.full((1 << n, n), np.inf); par = np.full((1 << n, n), -1, dtype=np.int16)
    dp[1 << np.arange(n), np.arange(n)] = 0.0
    for mask in range(1, 1 << n):
        v = dp[mask]
        if not np.isfinite(v).any():
            continue
        cand = v[:, None] + D
        bi = np.argmin(cand, axis=0); best = cand[bi, np.arange(n)]
        for j in range(n):
            if not (mask >> j) & 1:
                m2 = mask | (1 << j)
                if best[j] < dp[m2, j]:
                    dp[m2, j] = best[j]; par[m2, j] = bi[j]
    full = (1 << n) - 1; j = int(np.argmin(dp[full])); path = []; mask = full
    while j >= 0:
        path.append(j); pj = int(par[mask, j]); mask ^= 1 << j; j = pj
    return path[::-1]


def unimodal_path(D: np.ndarray, r: np.ndarray, lam: float = 1.0, tol: float = 0.05) -> list[int]:
    """Exact shortest open path with the ripple constrained to be UNIMODAL along it (it falls away from the pyramidal layer on
    both sides): Held-Karp with a phase bit (rising / falling); after the first drop of r by > tol, every rise of r by > tol
    costs lam x the rise. r = signed ripple scaled to 0-1 (several profiles: their mean). Without this, a path can jump across
    the steep layer step and glue the oriens run to the radiatum run (template WT2 shank 3)."""
    n = len(D)
    if n <= 2:
        return list(range(n))
    rise = r[None, :] - r[:, None]
    T0, NB0 = D, (rise < -tol)
    T1 = D + lam * np.maximum(0.0, rise - tol)
    dp = np.full((1 << n, n, 2), np.inf)
    par = np.full((1 << n, n, 2, 2), -1, dtype=np.int16)          # (previous site, previous phase)
    dp[1 << np.arange(n), np.arange(n), 0] = 0.0
    ar = np.arange(n)
    for mask in range(1, 1 << n):
        v0, v1 = dp[mask, :, 0], dp[mask, :, 1]
        if not (np.isfinite(v0).any() or np.isfinite(v1).any()):
            continue
        C0 = v0[:, None] + T0
        C0_stay = np.where(NB0, np.inf, C0); C0_drop = np.where(NB0, C0, np.inf)
        C1 = v1[:, None] + T1
        i0 = np.argmin(C0_stay, axis=0); b0 = C0_stay[i0, ar]
        id_ = np.argmin(C0_drop, axis=0); bd = C0_drop[id_, ar]
        i1 = np.argmin(C1, axis=0); b1 = C1[i1, ar]
        use1 = b1 < bd; best1 = np.where(use1, b1, bd); src1 = np.where(use1, i1, id_); ph1 = np.where(use1, 1, 0)
        for j in range(n):
            if (mask >> j) & 1:
                continue
            m2 = mask | (1 << j)
            if b0[j] < dp[m2, j, 0]:
                dp[m2, j, 0] = b0[j]; par[m2, j, 0] = (i0[j], 0)
            if best1[j] < dp[m2, j, 1]:
                dp[m2, j, 1] = best1[j]; par[m2, j, 1] = (src1[j], ph1[j])
    full = (1 << n) - 1
    j, ph = np.unravel_index(int(np.argmin(dp[full])), (n, 2)); path = []; mask = full
    while j >= 0:
        path.append(int(j)); pj, pph = par[mask, j, ph]; mask ^= 1 << int(j); j, ph = int(pj), int(pph)
    return path[::-1]


def orientation_votes(path: list[int], f: dict) -> dict:
    """Votes (> 0: `path` already runs top -> bottom) from one profile."""
    pos = {s: i for i, s in enumerate(path)}; n = len(path); ip = pos[f["p"]]
    side = lambda i: np.sign(pos[i] - ip)
    neg = [i for i in range(n) if f["corr"][i] < NEG_CORR]
    v_rip = 2.0 * float(sum(side(i) for i in neg)) / max(len(neg), 1)
    th = f["TH"]; rng = max(circ_range(th), 1e-9) if np.all(np.isfinite(th)) else None
    v_th = 0.0
    k = min(ip, n - 1 - ip, 4)                      # compare theta at EQUAL distances on both sides of p
    if rng and k >= 1:
        dev = np.abs(wrap(th - th[f["p"]])) / rng
        v_th = float(np.mean([dev[path[ip + d]] for d in range(1, k + 1)]) - np.mean([dev[path[ip - d]] for d in range(1, k + 1)]))
    iS = pos[int(np.argmax(f["S"]))]
    v_spw = 0.5 * float(np.sign(ip - iS))
    # sharp wave vs ripple: below the layer the sharp wave keeps changing while the ripple dies (|dS|/|dR| 19-75 on the two
    # templates), above it both grow together toward the layer (2.5-4.5): the side with the larger ratio is the bottom; with
    # one side only (p within 1 site of an end) the rest is below p when its ratio exceeds RATIO_BELOW
    S, R = f["S"][path], f["R"][path]

    def ratio(a, b):
        return float(np.ptp(S[a:b]) / (np.ptp(R[a:b]) + 1e-9)) if b - a >= 2 else float("nan")
    rb, ra = ratio(0, ip + 1), ratio(ip, n)
    if ip >= 2 and n - 1 - ip >= 2:
        v_ratio = 1.5 * float(np.sign(np.log(ra / rb))) if rb > 0 and ra > 0 else 0.0
    else:
        rest = ra if ip < 2 else rb
        below = rest > RATIO_BELOW                  # the rest of the shank is below p (radiatum) -> p is the top
        v_ratio = 1.5 * (1.0 if (ip < 2) == below else -1.0)
    w = float(np.clip(f["R"].max() / max(np.percentile(f["R"], 10), 1e-9) - 1.0, 0.0, 2.0) / 2.0)   # ripple contrast weight 0-1
    return {"ripple": w * v_rip, "theta": w * v_th, "spw": v_spw, "ratio": w * v_ratio}


def compare(order: list[int], ref: list[int]) -> str:
    common = [c for c in ref if c in order]
    if len(common) < 3:
        return f"only {len(common)} common sites"
    pa = {c: i for i, c in enumerate([c for c in ref if c in common])}; pb = {c: i for i, c in enumerate([c for c in order if c in common])}
    rho = spearmanr([pa[c] for c in common], [pb[c] for c in common])[0]
    d = [abs(pa[c] - pb[c]) for c in common]
    return f"rho {rho:+.3f}, {sum(x <= 1 for x in d)}/{len(common)} within +-1, max shift {max(d)}"


def path_len(order: list[int], chans: list[int], D: np.ndarray) -> float:
    idx = {c: i for i, c in enumerate(chans)}; o = [idx[c] for c in order if c in idx]
    return float(sum(D[a, b] for a, b in zip(o[:-1], o[1:])))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profiles", nargs="+", required=True)
    ap.add_argument("--orders", nargs="+", required=True, help="NAME=xml; the first is the reference (membership, group order, dead/skip)")
    ap.add_argument("--shanks", type=int, nargs="*", default=None, help="1-based groups to order (default: all with >= 4 live sites)")
    ap.add_argument("--xml-out", default=None, help="write the consensus order as a Neuroscope XML")
    ap.add_argument("--csv-out", default=None, help="per-site features along the consensus order, per profile")
    ap.add_argument("--exclude", type=int, nargs="*", default=[], help="columns the LFP cannot place (e.g. a site that correlates with "
                    "nothing): left out of the seriation and kept after their predecessor in the reference order, like dead columns")
    ap.add_argument("--dead-at-gaps", action="store_true", help="place dead/skipped columns as pace makers at the largest remaining "
                    "steps of the consensus path (never at an end) instead of after their predecessor in the reference XML")
    ap.add_argument("--method", default="unimodal", choices=["unimodal", "plain"],
                    help="unimodal (default) = shortest path with the signed ripple unimodal along it; plain = shortest path only")
    ap.add_argument("--layout", default="linear", help="layout written into --xml-out (e.g. 'Buzsaki 5x12' for SF09)")
    ap.add_argument("--label", default="")
    a = ap.parse_args()

    orders = {}
    for s in a.orders:
        k, v = s.split("=", 1); orders[k] = read_groups(Path(v))
    ref_name = next(iter(orders)); ref_groups, ref_skip = orders[ref_name]
    Z = [(Path(p).stem, np.load(p)) for p in a.profiles]
    metas = [json.loads(str(z["meta_json"])) for _, z in Z]
    for (name, z), m in zip(Z, metas):
        print(f"profile {name}: {m['animal']} {m['session']} ({m.get('window_desc') or str(m['window_start_min']) + ' min'}), "
              f"{int(z['n_ripples'])} ripples{'' if 'ripple_corr' in z.files else '  [no ripple_corr: unsigned ripple]'}")
    out_groups, rows = [], []
    for k, g in enumerate(ref_groups, 1):
        dead = set(ref_skip) | set(a.exclude)
        for _, z in Z:
            dead |= set(int(c) for c in z["dead"]) | set(int(c) for c in z["skipped"])
        live = [c for c in g if c not in dead]
        if (a.shanks and k not in a.shanks) or len(live) < 4:
            out_groups.append(g); print(f"\nshank {k}: kept as in {ref_name} ({len(live)} live)"); continue
        if len(live) > 16:
            raise SystemExit(f"shank {k}: {len(live)} live sites - exact seriation is limited to 16")
        F = [features(z, live) for _, z in Z]
        Ds = [dist(f) for f in F]
        W = np.array([contrast_weight(f) for f in F]); W = W / W.sum()
        rmean = np.sum([w * (f["Rs"] - f["Rs"].min()) / (np.ptp(f["Rs"]) + 1e-9) for w, f in zip(W, F)], axis=0)
        Dw = np.sum([w * D for w, D in zip(W, Ds)], axis=0)
        cons = unimodal_path(Dw, rmean) if a.method == "unimodal" else shortest_path(Dw)
        votes = [orientation_votes(cons, f) for f in F]
        total = sum(sum(v.values()) for v in votes)
        if total < 0:
            cons = cons[::-1]
        order = [live[i] for i in cons]
        print(f"\nshank {k}: consensus weights " + " ".join(f"{w:.2f}" for w in W) + f"; order over {len(Z)} profile(s) (top -> bottom), orientation votes "
              + "; ".join(f"{Z[i][0]}: " + " ".join(f"{kk} {vv:+.2f}" for kk, vv in v.items()) for i, v in enumerate(votes))
              + f" -> total {total:+.2f}{' (reversed)' if total < 0 else ''}")
        print(f"   order: {order}")
        for name, (gs, _) in orders.items():
            gm = max(gs, key=lambda x: len(set(x) & set(live)))          # the group with the same channel set (numbering may differ)
            ref = [c for c in gm if c in live]
            if len(ref) < 4:
                print(f"   vs {name:12s} no matching group"); continue
            print(f"   vs {name:12s} {compare(order, ref)}; path length per profile "
                  + " ".join(f"{path_len(ref, live, D):.2f}" for D in Ds)
                  + f"  (consensus {' '.join(f'{path_len(order, live, D):.2f}' for D in Ds)})")
        for (name, z), f, D in zip(Z, F, Ds):
            rs1 = (f["Rs"] - f["Rs"].min()) / (np.ptp(f["Rs"]) + 1e-9)
            single = unimodal_path(D, rs1) if a.method == "unimodal" else shortest_path(D)
            v = orientation_votes(single, f)
            if sum(v.values()) < 0:
                single = single[::-1]
            idx = {c: i for i, c in enumerate(live)}
            print(f"   {name}: alone {compare([live[i] for i in single], order)} vs consensus | along consensus "
                  + " ".join(f"{c}:{f['S'][idx[c]]:+.0f}/{f['Rs'][idx[c]]:+.0f}/{f['TH'][idx[c]]:+.0f}" for c in order))
            for i, c in enumerate(order):
                j = idx[c]
                rows.append([a.label, k, i + 1, c, name, round(f["S"][j], 2), round(f["R"][j], 2), round(f["corr"][j], 3), round(f["Rs"][j], 2),
                             round(f["TH"][j], 1), round(float(10 ** f["TP"][j]), 1)])
        seq = list(order)
        if a.dead_at_gaps:
            # dead / skipped columns as pace makers at the largest remaining step of the consensus path (never at an end)
            idx = {c: i for i, c in enumerate(live)}
            steps = [float(Dw[idx[x], idx[y]]) for x, y in zip(order[:-1], order[1:])]
            for c in [c for c in g if c in dead]:
                j = int(np.argmax(steps))
                seq.insert(j + 1, c); half = steps[j] / 2.0
                steps[j:j + 1] = [half, half]
        else:
            # dead / skipped columns back after the live column that precedes them in the reference order
            for c in g:
                if c in dead:
                    prev = [x for x in g[:g.index(c)] if x in seq]
                    seq.insert(seq.index(prev[-1]) + 1 if prev else 0, c)
        out_groups.append(seq)
        if [c for c in seq if c in dead] and seq != order:
            print(f"   with dead/skipped re-inserted: {seq}")
    if a.csv_out:
        Path(a.csv_out).parent.mkdir(parents=True, exist_ok=True)
        with open(a.csv_out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(["label", "shank", "position", "col", "profile", "spw_uV", "ripple_uV", "ripple_corr_to_max", "signed_ripple_uV", "theta_phase_deg", "theta_power_uV2"])
            w.writerows(rows)
        print(f"\nfeatures -> {a.csv_out}")
    if a.xml_out:
        from make_session_xml import build_session_xml, write_xml
        all_dead = sorted((ref_skip | set().union(*[set(int(c) for c in z["dead"]) | set(int(c) for c in z["skipped"]) for _, z in Z])) - set(a.exclude))
        desc = (f"{metas[0]['animal']} within-shank order by SWR layer-profile seriation (ephys/swr_layer_order.py; SPW, signed ripple, "
                f"theta phase, log theta power; shortest path, consensus of {', '.join(n for n, _ in Z)}); top = oriens side; "
                f"dead/skipped{' and excluded ' + str(sorted(a.exclude)) if a.exclude else ''} columns kept after their predecessor in {ref_name}; "
                f"groups {sorted(a.shanks) if a.shanks else 'all'} ordered, others as in {ref_name}; channels = exported columns. {a.label}")
        out = write_xml(build_session_xml(n_channels=64, fs=20000.0, groups=out_groups, reject=all_dead, layout=a.layout, description_extra=desc), Path(a.xml_out))
        print(f"order -> {out}")


if __name__ == "__main__":
    main()
