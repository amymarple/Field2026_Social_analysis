r"""Within-shank site order from the SWR gradient (user rule, 2026-09-29): no polarity reversal is needed - along a shank
approaching the CA1 pyramidal layer the sharp-wave ripple gets progressively LARGER and LONGER. Reads the profiles saved by
`lfp_profile_check.py --save-profile` (no raw data), so any window of any animal can be re-scored instantly.

Per site c (from the ripple-triggered averages over the window's N ripples, +-100 ms):
  SPW amplitude   A_spw(c)  = max_t |spw_wave_c(t)| - baseline      (1-50 Hz LFP, baseline = median of |t| >= 80 ms)
  SPW duration    D_spw(c)  = full width at half maximum of |spw_wave_c - baseline| around t = 0 (ms)
  ripple amp.     A_rip(c)  = max_t env_wave_c(t) - baseline         (|Hilbert| of 130-200 Hz)
  ripple duration D_rip(c)  = FWHM of env_wave_c - baseline around t = 0 (ms)
  SWR score       S(c)      = mean over the four features of rank(feature)/n  (rank within the shank, 1 = smallest)
Order of a shank = sites by S ascending (top = smallest / shortest SWR).
VALID ONLY FOR SHANKS WITHOUT A POLARITY REVERSAL (e.g. SF07, all-positive SPW). Where the SPW reverses (SF08/SF10/SF12:
positive above, negative in radiatum) the absolute amplitude rises toward BOTH ends of the shank, so these scores are
meaningless there; check the signed SPW profile instead (monotone along the order, ripple maximum at the pyramidale end).
Also note (SF08, 2026-10-05): when the probe sits at a different depth the whole profile shifts (top sites can turn
negative), so the SIGN of a site is not a depth label - the direction of the gradient and the ripple maximum are. Monotonicity of an order for feature f =
Spearman rho(position, f) (1 = f rises steadily along the order) and total variation tv = sum|diff f| / range (1 = monotonic).

Usage: python ephys/swr_gradient_order.py --profiles A.npz [B.npz ...] --orders NAME=file.xml ... [--derive-xml-dir DIR]
       [--features-csv-dir DIR]
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

FEATURES = ("spw_amp_uV", "spw_fwhm_ms", "rip_amp_uV", "rip_fwhm_ms")


def fwhm(t_ms: np.ndarray, y: np.ndarray) -> float:
    """Width (ms) of the contiguous region around the peak nearest t=0 where y >= half its peak value."""
    i0 = int(np.argmin(np.abs(t_ms)))
    lo_win = int(np.searchsorted(t_ms, -30.0)); hi_win = int(np.searchsorted(t_ms, 30.0))
    ip = lo_win + int(np.argmax(y[lo_win:hi_win])) if hi_win > lo_win else i0
    half = y[ip] / 2.0
    if half <= 0:
        return float("nan")
    a = ip
    while a > 0 and y[a - 1] >= half:
        a -= 1
    b = ip
    while b < len(y) - 1 and y[b + 1] >= half:
        b += 1
    dt = float(np.median(np.diff(t_ms)))
    return (b - a + 1) * dt


def site_features(npz: dict) -> dict[int, dict]:
    t = npz["wave_t_ms"]
    edge = np.abs(t) >= 80.0
    out = {}
    for c in [int(x) for x in npz["live"]]:
        sw = npz["spw_wave_uV"][:, c]
        sw = sw - np.median(sw[edge])
        sgn = 1.0 if abs(sw.max()) >= abs(sw.min()) else -1.0          # use the dominant polarity of the sharp wave
        env = npz["ripple_env_wave_uV"][:, c]
        env = env - np.median(env[edge])
        out[c] = {"spw_amp_uV": float((sgn * sw).max()), "spw_fwhm_ms": fwhm(t, sgn * sw),
                  "rip_amp_uV": float(env.max()), "rip_fwhm_ms": fwhm(t, env), "spw_sign": sgn}
    return out


def swr_score(chans: list[int], feat: dict[int, dict]) -> dict[int, float]:
    n = len(chans)
    ranks = {f: {c: r for r, c in enumerate(sorted(chans, key=lambda c: feat[c][f]), 1)} for f in FEATURES}
    return {c: float(np.mean([ranks[f][c] / n for f in FEATURES])) for c in chans}


def groups(xml: Path) -> list[list[int]]:
    r = ET.parse(xml).getroot()
    return [[int(c.text) for c in g.findall("channel")] for g in r.findall("./anatomicalDescription/channelGroups/group")]


def tv(v: np.ndarray) -> float:
    rng = v.max() - v.min()
    return float(np.abs(np.diff(v)).sum() / rng) if rng > 0 else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profiles", nargs="+", required=True, help="profile .npz files (lfp_profile_check --save-profile)")
    ap.add_argument("--orders", nargs="+", default=[], help="NAME=path.xml candidate orders to score")
    ap.add_argument("--derive-xml-dir", default=None, help="write the SWR-score order of each window as an XML here")
    ap.add_argument("--features-csv-dir", default=None, help="write per-site features per window as CSV here")
    a = ap.parse_args()
    orders = {k: groups(Path(v)) for k, v in (s.split("=", 1) for s in a.orders)}
    derived = {}
    for p in a.profiles:
        z = dict(np.load(p))
        meta = json.loads(str(z["meta_json"]))
        wname = Path(p).stem
        feat = site_features(z)
        base_groups = orders[next(iter(orders))] if orders else []
        print(f"\n=== {wname}: {meta['animal']} {meta['session']} {meta['window_start_min']:.0f}-"
              f"{meta['window_start_min'] + meta['window_min']:.0f} min, {int(z['n_ripples'])} ripples")
        # SWR-score order per shank (shank membership from the first candidate order; membership is not in question)
        dgs = []
        for g in base_groups:
            live = [c for c in g if c in feat]
            s = swr_score(live, feat)
            dgs.append(sorted(live, key=lambda c: s[c]) + [c for c in g if c not in feat])
        derived[wname] = dgs
        cand = dict(orders); cand[f"D_swr_{wname}"] = dgs
        for k, gs in enumerate(base_groups, 1):
            print(f"  shank {k}:")
            for name, og in cand.items():
                o = [c for c in og[k - 1] if c in feat]
                pos = np.arange(len(o))
                cells = []
                for f in FEATURES:
                    v = np.array([feat[c][f] for c in o])
                    cells.append(f"{f.split('_')[0]}-{f.split('_')[1][:3]} rho {spearmanr(pos, v)[0]:+.2f} tv {tv(v):.2f}")
                print(f"    {name:34s} " + " | ".join(cells))
        if a.features_csv_dir:
            out = Path(a.features_csv_dir) / f"swr_features_{wname}.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["col", "shank", *FEATURES, "spw_sign", "swr_score", "position_in_swr_order"])
                for k, dg in enumerate(dgs, 1):
                    s = swr_score([c for c in dg if c in feat], feat)
                    for i, c in enumerate(dg):
                        if c in feat:
                            w.writerow([c, k, *[round(feat[c][f], 3) for f in FEATURES], feat[c]["spw_sign"], round(s[c], 4), i + 1])
            print(f"  features -> {out}")
        if a.derive_xml_dir and base_groups:
            from make_session_xml import build_session_xml, write_xml
            desc = (f"{meta['animal']} within-shank order by the SWR gradient (SPW amplitude, SPW FWHM, ripple amplitude, ripple FWHM; "
                    f"mean rank) on {meta['session']} {meta['window_start_min']:.0f}-{meta['window_start_min'] + meta['window_min']:.0f} min "
                    f"({int(z['n_ripples'])} ripples); top = smallest/shortest SWR; channels = exported columns")
            skip = sorted(int(x) for x in z["skipped"])
            out = Path(a.derive_xml_dir) / f"{meta['animal']}_swr_order_{wname}.xml"
            write_xml(build_session_xml(n_channels=64, fs=20000.0, groups=dgs, reject=skip, layout="linear", description_extra=desc), out)
            print(f"  order -> {out}")
    if len(derived) >= 2:
        names = list(derived)
        a0, b0 = derived[names[0]], derived[names[1]]
        print(f"\n=== SWR-score order agreement {names[0]} vs {names[1]}:")
        for k, (x, y) in enumerate(zip(a0, b0), 1):
            px = {c: i for i, c in enumerate(x)}; py = {c: i for i, c in enumerate(y)}
            ch = sorted(set(x) & set(y))
            moved = [(c, px[c] + 1, py[c] + 1) for c in ch if abs(px[c] - py[c]) > 1]
            print(f"  shank {k}: rho {spearmanr([px[c] for c in ch], [py[c] for c in ch])[0]:.3f}; {len(ch) - len(moved)}/{len(ch)} within +-1; "
                  f"off by >1: {moved}")
            print(f"     {names[0]}: {x}\n     {names[1]}: {y}")


if __name__ == "__main__":
    main()
