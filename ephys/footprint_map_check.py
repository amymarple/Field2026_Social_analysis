"""Which connector mating / bank rotation makes the sorted units' spatial footprints compact? (channel-map test #2)

The co-activation scan (probe_map_check.py) counts pairs of channels that spike together; it needs many strong pairs and
was inconclusive on SF08/SF11/SF12 (19-67 pairs in 10-60 min). This test uses the Kilosort4 units instead: for each unit
the spike-triggered average over ALL 64 exported columns of the preprocessed .dat (500-8000 Hz) gives a 64-channel
amplitude footprint. A real unit is seen on a few neighbouring sites of ONE shank, so under the correct channel map its
footprint is spatially compact; under a wrong map the same energy is scattered over distant sites / other shanks.

Candidates (same family as probe_map_check --rotation-scan --connector-scan): the ProbeMaps 'version1' XML of the probe,
16 connector matings (each 2x16 Omnetics connector rotated 180 deg or not, the two swapped or not, whole probe mirrored or
not) x raw bank-0 / bank-1 slot rotations (-4..+4, conjugated through the WILD export map). Geometry of A4x16-Lin-5mm-50s-300:
16 sites per shank at 50 um pitch, 4 shanks 300 um apart.

Score per candidate = mean over units of  sum_c f_c * dist(c, peak) / sum_c f_c   [um; lower = more compact], where f_c is
the unit's baseline-subtracted peak-to-peak STA amplitude on exported column c and dist is the candidate's site distance
(same shank: |d depth| x 50 um; other shank: 300 um x |d shank| + |d depth| x 50 um). Also reported: the fraction of
footprint energy on the peak site's shank and within +-100 um of the peak. Units are taken from the raw Kilosort4 folders
(any shank partition; the partition only decides which units exist, the footprint is measured on all 64 columns).

Trigger mode (--trigger) -- FAILED VALIDATION on 2026-09-04, do not use for decisions: on SF07 (map verified two ways) the
verified map ranked 781/1296 with raw crossings and 159/1296 after median referencing + artifact rejection; channel-triggered
averages of the raw staged data are not local enough (multi-unit + residual common mode). Kept for reference only. The unit
mode above (sorted units, preprocessed .dat with local CMR and artifact removal) is the validated test.
Trigger mode: footprints are channel-triggered instead of unit-triggered. A window of the
STAGED raw amplifier.dat (default 300 s from the middle; FM65 sessions are clean, older firmware is de-glitched first) is
band-passed 500-5000 Hz; on every column the largest negative threshold crossings (-5 sigma, MAD) trigger a 64-column STA,
so column c's footprint is the average waveform of the multi-unit spikes seen on c, and its strongest neighbours must be
c's physical neighbours under the right map. The band-passed window is median-referenced across columns and samples where
>= 8 columns cross threshold together are rejected (common-mode transients otherwise dominate). Same candidates, same score
(peak = the trigger column).

Usage (base Python, numpy only; unit mode needs a sorted session, trigger mode a staged one):
  python ephys/footprint_map_check.py --cohort 2026c --animal SF08 --session 13_20260902_082748.094
        [--probe A4x16-Lin-5mm-50s-300] [--units-per-shank 40] [--spikes-per-unit 200] [--max-rot 4] [--top 12]
        [--trigger --seconds 300 --events-per-channel 300]
Appends results/<cohort>/ephys_spikes/reports/ephys_spikes_footprint_map_check_<cohort>.csv and prints the ranking.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ephys_block, git_commit, report_dir, sort_root, stage_root, utc_now_iso  # noqa: E402
from probe_map_check import PROBE_XML, PROBEMAPS, band, connector_variants, load_groups, rotation_permutation  # noqa: E402
from deglitch_wild import estimate_thresholds, med5  # noqa: E402
from wild_ce_params import parse_ce_params  # noqa: E402

GEOM = {"A4x16-Lin-5mm-50s-300": {"pitch_um": 50.0, "shank_um": 300.0},
        "A5x12_16-Buz_lin-5mm-100-200-160_177": {"pitch_um": 20.0, "shank_um": 200.0}}   # Buzsaki tip: ~20 um between sites in XML order (approx.), shanks 200 um


def read_tsv(p: Path) -> dict[int, str]:
    out = {}
    if not p.exists():
        return out
    with open(p, encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        for r in rd:
            k = list(r.keys())
            try:
                out[int(r[k[0]])] = str(r[k[1]]).strip()
            except (ValueError, IndexError):
                pass
    return out


def pick_units(sdir: Path, units_per_shank: int, min_spikes: int) -> list[tuple[str, int, np.ndarray]]:
    """(shank folder name, cluster id, spike times) for the largest-amplitude good/mua clusters of every raw KS4 folder."""
    out = []
    for raw in sorted(p for p in sdir.glob("Kilosort4_*_probe*_shank*") if p.is_dir() and not p.name.endswith("_spi") and not p.name.startswith(".")):
        if not (raw / "spike_times.npy").exists():
            continue
        st = np.load(raw / "spike_times.npy").ravel().astype(np.int64)
        sc = np.load(raw / "spike_clusters.npy").ravel().astype(np.int64)
        lab = read_tsv(raw / "cluster_KSLabel.tsv")
        amp = {k: float(v) for k, v in read_tsv(raw / "cluster_Amplitude.tsv").items() if v.replace(".", "", 1).replace("-", "", 1).isdigit()}
        ids, cnt = np.unique(sc, return_counts=True)
        cand = [(amp.get(int(i), 0.0), int(i)) for i, c in zip(ids, cnt) if c >= min_spikes and lab.get(int(i), "good") in ("good", "mua")]
        for _, cid in sorted(cand, reverse=True)[:units_per_shank]:
            out.append((raw.name, cid, st[sc == cid]))
    return out


def footprints(dat: np.memmap, units, spikes_per_unit: int, pre: int, post: int, seed: int = 0) -> np.ndarray:
    """Baseline-subtracted peak-to-peak STA amplitude per exported column, one row per unit (n_units x 64)."""
    rng = np.random.default_rng(seed)
    ns = dat.shape[0]
    F = np.zeros((len(units), dat.shape[1]), dtype=np.float32)
    for u, (_, _, st) in enumerate(units):
        st = st[(st > pre) & (st < ns - post)]
        pick = np.sort(rng.choice(st, size=min(spikes_per_unit, st.size), replace=False))
        acc = np.zeros((pre + post, dat.shape[1]), dtype=np.float64)
        for t in pick:
            acc += dat[t - pre:t + post]
        sta = acc / max(1, pick.size)
        ptp = sta.max(0) - sta.min(0)
        F[u] = np.clip(ptp - np.median(ptp), 0, None)
    return F


def trigger_footprints(staged: Path, cfg: dict, seconds: float, events_per_channel: int, thr_sigma: float = 5.0, max_active: int = 8, seed: int = 0) -> tuple[np.ndarray, float]:
    """Channel-triggered 64-column footprints from a staged raw window: row c = ptp of the STA triggered on column c's own
    largest negative crossings. Returns (F [64 x 64], window seconds)."""
    cp = parse_ce_params(staged)
    nch, fs = cp.n_channels or 64, float(cp.fs or 20000)
    ns = (staged / "amplifier.dat").stat().st_size // (2 * nch)
    win = int(min(ns, round(seconds * fs))); a0 = max(0, (ns - win) // 2)
    x = np.asarray(np.memmap(staged / "amplifier.dat", dtype=np.int16, mode="r", shape=(ns, nch))[a0:a0 + win]).astype(np.float32)
    if int(cp.firmware_version) < int(cfg.get("clean_firmware_min", 65)):
        dg = cfg.get("deglitch") or {}
        thr = estimate_thresholds(x, float(dg.get("k_mad", 10)), float(dg.get("floor_adc", 500)), block=min(100_000, win), nblocks=min(8, max(1, win // 100_000)))
        B = 1_000_000
        for s0 in range(0, win, B):
            lo, hi = max(0, s0 - 2), min(win, s0 + B + 2)
            blk = x[lo:hi]; ref = med5(blk); bad = np.abs(blk - ref) > thr[None, :]
            i0 = s0 - lo; i1 = i0 + min(B, win - s0)
            seg = x[s0:s0 + (i1 - i0)]; seg[bad[i0:i1]] = ref[i0:i1][bad[i0:i1]]
    hp = band(x, fs, 500.0, 5000.0).astype(np.float32); del x
    # v2 (2026-09-04): the first version triggered on the raw band-passed signal and failed validation on SF07 (verified map
    # ranked 781/1296): the largest raw crossings are common-mode transients seen on every column, so every footprint was
    # global. Global median reference + rejection of samples where >= max_active columns cross at once fixes that.
    hp -= np.median(hp, axis=1, keepdims=True)
    sigma = 1.4826 * np.median(np.abs(hp - np.median(hp, 0)), 0)
    pre, post = int(0.001 * fs), int(0.002 * fs)
    n_active = (hp < (-thr_sigma * np.where(sigma > 0, sigma, np.inf))[None, :]).sum(1)
    art = np.convolve((n_active >= max_active).astype(np.float32), np.ones(int(0.001 * fs), dtype=np.float32), mode="same") > 0
    rng = np.random.default_rng(seed)
    F = np.zeros((nch, nch), dtype=np.float32)
    for c in range(nch):
        if not np.isfinite(sigma[c]) or sigma[c] <= 0:
            continue
        v = hp[:, c]
        below = v < -thr_sigma * sigma[c]
        idx = np.where(below[1:-1] & (v[1:-1] <= v[:-2]) & (v[1:-1] < v[2:]))[0] + 1     # local minima under threshold
        idx = idx[(idx > pre) & (idx < win - post)]
        idx = idx[~art[idx]]                                                              # drop common-mode / artifact events
        if idx.size == 0:
            continue
        if idx.size > 2 * events_per_channel:                                             # the largest crossings, then a random subset
            idx = idx[np.argsort(v[idx])[:2 * events_per_channel]]
        if idx.size > events_per_channel:
            idx = rng.choice(idx, size=events_per_channel, replace=False)
        idx = np.sort(idx)
        acc = np.zeros((pre + post, nch), dtype=np.float64)
        for t in idx:
            acc += hp[t - pre:t + post]
        sta = acc / idx.size
        ptp = sta.max(0) - sta.min(0)
        F[c] = np.clip(ptp - np.median(ptp), 0, None)
    return F, win / fs


def candidate_sites(groups: list[list[int]], P: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """exported column -> (shank index, depth index); -1 where the column is not a probe site."""
    shank = -np.ones(64, dtype=int); depth = -np.ones(64, dtype=int)
    for k, g in enumerate(groups):
        for s, intan in enumerate(g):
            col = int(P[intan])
            shank[col] = k; depth[col] = s
    return shank, depth


def distance_matrix(shank: np.ndarray, depth: np.ndarray, pitch: float, shank_um: float) -> np.ndarray:
    D = np.full((64, 64), np.nan)
    ok = shank >= 0
    ds = np.abs(shank[:, None] - shank[None, :]) * shank_um
    dd = np.abs(depth[:, None] - depth[None, :]) * pitch
    D[np.ix_(ok, ok)] = (ds + dd)[np.ix_(ok, ok)]
    return D


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True); ap.add_argument("--animal", required=True); ap.add_argument("--session", required=True)
    ap.add_argument("--probe", default="A4x16-Lin-5mm-50s-300", choices=list(GEOM))
    ap.add_argument("--sort-root", default=None)
    ap.add_argument("--units-per-shank", type=int, default=40); ap.add_argument("--spikes-per-unit", type=int, default=200)
    ap.add_argument("--min-spikes", type=int, default=300)
    ap.add_argument("--max-rot", type=int, default=4); ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--top-k", type=int, default=6, help="rank by the spread of each unit's k strongest columns only (0 = all 64)")
    ap.add_argument("--cache-dir", default=None, help="cache the 64-column footprints as <dir>/<animal>_<session>_u<N>_s<M>.npz (re-scoring is instant)")
    ap.add_argument("--trigger", action="store_true", help="channel-triggered footprints from the STAGED raw session (no sorting needed)")
    ap.add_argument("--seconds", type=float, default=300.0, help="trigger mode: window length from the middle of the session")
    ap.add_argument("--events-per-channel", type=int, default=300)
    ap.add_argument("--staged-dir", default=None)
    ap.add_argument("--peak-cols", default=None,
                    help="keep only units whose peak column is in this list, e.g. 1-17,32-47 (the columns whose site order differs between candidates)")
    ap.add_argument("--min-amp", type=float, default=0.0, help="keep only units whose peak footprint amplitude (ptp, ADC) is >= this")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    animal = a.animal.upper()
    animal = f"SF{int(animal[2:]):02d}" if animal.startswith("SF") and animal[2:].isdigit() else animal
    sdir = sort_root(a.cohort, a.sort_root) / animal / a.session
    mode = "trigger" if a.trigger else "units"
    if a.trigger:
        staged = Path(a.staged_dir) if a.staged_dir else stage_root(a.cohort, None) / animal / a.session
        if not (staged / "amplifier.dat").exists():
            raise SystemExit(f"session is not staged: {staged}")
        excluded = set()
        cache = Path(a.cache_dir) / f"{animal}_{a.session}_trigger{int(a.seconds)}s_e{a.events_per_channel}_v2.npz" if a.cache_dir else None
        if cache is not None and cache.exists():
            z = np.load(cache); F = z["F"]; n_folders = 0
            print(f"== {animal} {a.session}: channel-triggered footprints from cache {cache.name}")
        else:
            F, win_s = trigger_footprints(staged, ephys_block(a.cohort), a.seconds, a.events_per_channel)
            n_folders = 0
            print(f"== {animal} {a.session}: channel-triggered footprints, {win_s:.0f} s window, <= {a.events_per_channel} events per column, "
                  f"{int((F.sum(1) > 0).sum())} columns with events")
            if cache is not None:
                cache.parent.mkdir(parents=True, exist_ok=True)
                np.savez(cache, F=F, n_folders=0, units=np.array([f"col:{c}" for c in range(F.shape[0])]))
    else:
        dat_path = sdir / f"{a.session}.dat"
        if not dat_path.exists():
            raise SystemExit(f"no preprocessed .dat: {dat_path}")
        pm = json.loads((sdir / "preprocessSession_manifest.json").read_text(encoding="utf-8")) if (sdir / "preprocessSession_manifest.json").exists() else {}
        nch = int(pm.get("n_channels") or 64); fs = float(pm.get("sr") or 20000.0)
        ns = dat_path.stat().st_size // (2 * nch)
        dat = np.memmap(dat_path, dtype=np.int16, mode="r", shape=(ns, nch))
        excluded = set(int(c) for c in (pm.get("bad_channels_0based") or []))
        cache = Path(a.cache_dir) / f"{animal}_{a.session}_u{a.units_per_shank}_s{a.spikes_per_unit}.npz" if a.cache_dir else None
    if a.trigger:
        pass
    elif cache is not None and cache.exists():
        z = np.load(cache); F = z["F"]; n_folders = int(z["n_folders"])
        print(f"== {animal} {a.session}: {F.shape[0]} unit footprints from cache {cache.name}")
    else:
        units = pick_units(sdir, a.units_per_shank, a.min_spikes)
        if not units:
            raise SystemExit(f"no Kilosort4 units under {sdir}")
        pre, post = int(0.001 * fs), int(0.002 * fs)
        n_folders = len(set(u[0] for u in units))
        print(f"== {animal} {a.session}: {len(units)} units from {n_folders} shank folders, {a.spikes_per_unit} spikes each, "
              f"excluded columns {sorted(excluded) or '-'}")
        F = footprints(dat, units, a.spikes_per_unit, pre, post)
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.savez(cache, F=F, n_folders=n_folders, units=np.array([f"{u[0]}:{u[1]}" for u in units]))
    F = F.copy(); F[:, sorted(excluded)] = 0.0
    keep = F.sum(1) > 0
    if a.peak_cols:
        cols = set()
        for tok in a.peak_cols.split(","):
            lo, _, hi = tok.partition("-")
            cols.update(range(int(lo), int(hi or lo) + 1))
        keep &= np.isin(F.argmax(1), sorted(cols))
    if a.min_amp > 0:
        keep &= F.max(1) >= a.min_amp
    F = F[keep]
    n_units = int(F.shape[0])
    if n_units == 0:
        raise SystemExit("no units left after the peak-column / amplitude filters")
    print(f"   scoring {n_units} units" + (f" (peak column in {a.peak_cols})" if a.peak_cols else "") + (f" (peak ptp >= {a.min_amp:g})" if a.min_amp > 0 else ""))
    Fn = F / F.sum(1, keepdims=True)
    peak = F.argmax(1)
    if a.top_k and a.top_k < 64:      # keep each unit's k strongest columns only (sharper than the full 64-column spread)
        Fk = np.zeros_like(F); idx = np.argsort(-F, axis=1)[:, :a.top_k]
        np.put_along_axis(Fk, idx, np.take_along_axis(F, idx, 1), 1)
        Fk = Fk / Fk.sum(1, keepdims=True)
    else:
        Fk = Fn

    groups_v1 = load_groups(PROBEMAPS / PROBE_XML[a.probe][0])
    variants = connector_variants(groups_v1)
    g = GEOM[a.probe]
    rows = []
    for vname, groups in variants.items():
        for r0 in range(-a.max_rot, a.max_rot + 1):
            for r1 in range(-a.max_rot, a.max_rot + 1):
                P = rotation_permutation(r0, r1)
                shank, depth = candidate_sites(groups, P)
                D = distance_matrix(shank, depth, g["pitch_um"], g["shank_um"])
                Dp = np.nan_to_num(D[peak], nan=g["shank_um"] * 4)          # unit x column: distance from the unit's peak column
                spread = (Fn * Dp).sum(1)                                     # um per unit, all 64 columns
                spread_k = (Fk * Dp).sum(1)                                   # um per unit, k strongest columns
                same = np.array([Fn[u][shank == shank[peak[u]]].sum() if shank[peak[u]] >= 0 else 0.0 for u in range(n_units)])
                near = (Fn * (Dp <= 100.0)).sum(1)
                rows.append({"variant": vname, "rot_bank0": r0, "rot_bank1": r1, "spread_topk_um": float(spread_k.mean()), "spread_um": float(spread.mean()),
                             "spread_median_um": float(np.median(spread)), "same_shank_frac": float(same.mean()), "within_100um_frac": float(near.mean())})
    rows.sort(key=lambda r: r["spread_topk_um"])
    ref = next((r for r in rows if r["variant"] == "v1_raw" and r["rot_bank0"] == 1 and r["rot_bank1"] == 0), None)
    print(f"   {len(rows)} candidates (16 matings x {(2 * a.max_rot + 1) ** 2} bank rotations); lower spread = more compact footprints")
    for i, r in enumerate(rows[:a.top]):
        tag = "  <== SF07's map" if ref is r else ""
        print(f"   {i + 1:3d}. {r['variant']:12s} rot0 {r['rot_bank0']:+d} rot1 {r['rot_bank1']:+d}  top-{a.top_k} spread {r['spread_topk_um']:6.1f} um  all-64 {r['spread_um']:6.1f}  "
              f"same-shank {r['same_shank_frac']:.2f}  within 100um {r['within_100um_frac']:.2f}{tag}")
    if ref is not None and ref not in rows[:a.top]:
        print(f"   ref. v1_raw rot0 +1 rot1 +0 (SF07's map): rank {rows.index(ref) + 1}, top-{a.top_k} spread {ref['spread_topk_um']:.1f} um, same-shank {ref['same_shank_frac']:.2f}, "
              f"within 100um {ref['within_100um_frac']:.2f}")
    best, second = rows[0], rows[1]
    print(f"   margin: best {best['spread_topk_um']:.1f} vs 2nd {second['spread_topk_um']:.1f} um ({best['variant']} {best['rot_bank0']:+d}/{best['rot_bank1']:+d} vs "
          f"{second['variant']} {second['rot_bank0']:+d}/{second['rot_bank1']:+d})")
    if not a.no_write:
        out = report_dir(a.cohort) / f"ephys_spikes_footprint_map_check_{a.cohort}.csv"
        new = not out.exists()
        with open(out, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["written_utc", "animal", "session", "probe", "mode", "n_units", "spikes_per_unit", "top_k", "rank", "variant", "rot_bank0", "rot_bank1",
                            "spread_topk_um", "spread_um", "spread_median_um", "same_shank_frac", "within_100um_frac", "repo_git"])
            for i, r in enumerate(rows[:a.top]):
                w.writerow([utc_now_iso(), animal, a.session, a.probe, mode, n_units, (a.events_per_channel if a.trigger else a.spikes_per_unit), a.top_k, i + 1, r["variant"], r["rot_bank0"], r["rot_bank1"],
                            round(r["spread_topk_um"], 2), round(r["spread_um"], 2), round(r["spread_median_um"], 2), round(r["same_shank_frac"], 4),
                            round(r["within_100um_frac"], 4), git_commit()])
        print(f"   -> {out}")


if __name__ == "__main__":
    main()
