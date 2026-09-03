"""Data-side test of the ASSUMED channel -> shank grouping (the mapping in probes_<cohort>.yaml is unverified).

Channels on one shank share LFP (1-300 Hz) far more than channels on different shanks (200 um apart), so the
64x64 inter-channel correlation of a de-glitched window should show block structure aligned with the true
shank membership. This script:

  1. reads a window (default 60 s, middle of the file) of amplifier.dat, de-glitches it (5-pt median rule);
  2. computes LFP-band and spike-band (500-5000 Hz) correlation matrices;
  3. clusters channels (average-linkage on 1 - r_LFP) into k = number of assumed groups;
  4. reports the agreement between assumed and data-driven groups (adjusted Rand index, ARI) and the mean
     within- vs between-group LFP correlation of the assumed grouping;
  5. writes <figure> (both matrices with assumed group boundaries) + <csv> (per channel: assumed group,
     data-driven cluster, LFP/HP noise).

Definitions:  r_ij = Pearson correlation of the band-limited traces;  ARI in [-1, 1], 1 = identical partition,
~0 = chance.  A high ARI (> 0.8) with within >> between supports the mapping; a low ARI means the placeholder
blocks are wrong and the pinout must be obtained before any shank-level claim.

Usage:
  python ephys/probe_group_check.py --cohort 2026c --animal SF8 --session 0_20260831_190133.486 [--staged] [--seconds 60]
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import numpy as np

from _common import PROJECT_ROOT, ephys_block, figure_dir, find_session_dir, raw_ephys_root, report_dir, stage_root
from deglitch_wild import estimate_thresholds, med5
from make_session_xml import load_probe
from wild_ce_params import parse_ce_params


def _norm_animal(animal: str) -> str:
    a = animal.upper()
    return f"SF{int(a[2:]):02d}" if a.startswith("SF") and a[2:].isdigit() else a


def adjusted_rand_index(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a); b = np.asarray(b)
    ua, ia = np.unique(a, return_inverse=True); ub, ib = np.unique(b, return_inverse=True)
    n = np.zeros((ua.size, ub.size), dtype=np.int64)
    np.add.at(n, (ia, ib), 1)
    comb = lambda x: x * (x - 1) / 2.0
    sum_ij = comb(n).sum(); sum_a = comb(n.sum(1)).sum(); sum_b = comb(n.sum(0)).sum(); tot = comb(a.size)
    expected = sum_a * sum_b / tot if tot else 0.0
    max_index = 0.5 * (sum_a + sum_b)
    return float((sum_ij - expected) / (max_index - expected)) if max_index != expected else 1.0


def band(x: np.ndarray, fs: float, lo: float, hi: float, decim: int = 1) -> np.ndarray:
    from scipy import signal
    b, a = signal.butter(2, [lo / (fs / 2), hi / (fs / 2)], "band")
    y = signal.filtfilt(b, a, x, axis=0)
    return y[::decim]


def check(amplifier: Path, *, nch: int, fs: float, groups: list[list[int]], reject: list[int], seconds: float, k: float, floor: float,
          fig_path: Path, csv_path: Path, title: str) -> dict:
    nbytes = os.path.getsize(amplifier); ns = nbytes // (2 * nch)
    win = int(min(ns, round(seconds * fs))); a0 = max(0, (ns - win) // 2)
    x = np.asarray(np.memmap(amplifier, dtype=np.int16, mode="r", shape=(ns, nch))[a0:a0 + win]).astype(np.float32)
    thr = estimate_thresholds(x, k, floor, block=min(100_000, win), nblocks=min(8, max(1, win // 100_000)))
    ref = med5(x); bad = np.abs(x - ref) > thr[None, :]; x[bad] = ref[bad]
    lfp = band(x, fs, 1.0, 300.0, decim=16); hp = band(x, fs, 500.0, 5000.0)
    C = np.corrcoef(lfp.T); H = np.corrcoef(hp.T)
    C = np.nan_to_num(C); H = np.nan_to_num(H)

    assumed = np.full(nch, -1);
    for gi, g in enumerate(groups):
        assumed[g] = gi
    good = np.array([c for c in range(nch) if c not in set(reject) and assumed[c] >= 0])
    kgrp = len(groups)
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    D = 1.0 - C[np.ix_(good, good)]; np.fill_diagonal(D, 0.0); D = np.clip((D + D.T) / 2, 0, 2)
    Z = linkage(squareform(D, checks=False), method="average")
    cl = np.full(nch, -1); cl[good] = fcluster(Z, kgrp, criterion="maxclust") - 1
    ari = adjusted_rand_index(assumed[good], cl[good])
    same = assumed[good][:, None] == assumed[good][None, :]
    off = ~np.eye(good.size, dtype=bool)
    within = float(C[np.ix_(good, good)][same & off].mean()); between = float(C[np.ix_(good, good)][~same].mean()) if (~same).any() else float("nan")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    for ax, M, name in ((axes[0], C, "LFP 1–300 Hz"), (axes[1], H, "spike band 500–5000 Hz")):
        im = ax.imshow(M, vmin=-1, vmax=1, cmap="RdBu_r", interpolation="nearest")
        edges = np.cumsum([len(g) for g in groups])[:-1]
        for e in edges:
            ax.axhline(e - 0.5, color="k", lw=0.8); ax.axvline(e - 0.5, color="k", lw=0.8)
        ax.set_title(f"{name}: inter-channel r (assumed group edges in black)"); ax.set_xlabel("channel"); ax.set_ylabel("channel")
        fig.colorbar(im, ax=ax, fraction=0.046)
    fig.suptitle(f"{title}\nassumed vs data-driven groups: ARI={ari:.2f}; LFP r within={within:.2f} between={between:.2f} "
                 f"({win / fs:.0f} s window, de-glitched)")
    fig.tight_layout(); fig_path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(fig_path, dpi=130); plt.close(fig)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["channel", "assumed_group", "data_cluster", "rejected", "lfp_r_to_own_group", "lfp_r_to_other_groups", "hp_noise_adc_mad"])
        for c in range(nch):
            own = [j for j in good if assumed[j] == assumed[c] and j != c]; oth = [j for j in good if assumed[j] != assumed[c]]
            w.writerow([c, int(assumed[c]), int(cl[c]), c in set(reject), round(float(C[c, own].mean()), 3) if own else "",
                        round(float(C[c, oth].mean()), 3) if oth else "", round(float(1.4826 * np.median(np.abs(hp[:, c]))), 1)])
    return {"ari": ari, "within": within, "between": between, "figure": str(fig_path), "csv": str(csv_path), "window_s": win / fs,
            "verdict": "supported" if (ari > 0.8 and within > between) else ("weak" if ari > 0.5 else "not supported")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True); ap.add_argument("--animal", required=True); ap.add_argument("--session", required=True)
    ap.add_argument("--staged", action="store_true", help="read the staged copy instead of the raw folder")
    ap.add_argument("--raw-root", default=None); ap.add_argument("--seconds", type=float, default=60.0)
    a = ap.parse_args()
    cfg = ephys_block(a.cohort); animal = _norm_animal(a.animal)
    if a.staged:
        sdir = stage_root(a.cohort) / animal / a.session
    else:
        raw = raw_ephys_root(a.cohort, a.raw_root)
        folder = next(c for c in (a.animal, animal, f"SF{int(animal[2:])}") if (raw / c).is_dir())
        sdir = find_session_dir(raw, folder, a.session)
    cp = parse_ce_params(sdir)
    probe = load_probe(PROJECT_ROOT / cfg.get("probe_config", f"ephys/configs/probes_{a.cohort}.yaml"), animal)
    dg = cfg.get("deglitch") or {}
    stem = f"ephys_spikes_probe_group_check_{animal}_{a.session}_{a.cohort}"
    res = check(sdir / "amplifier.dat", nch=cp.n_channels, fs=float(cp.fs), groups=probe["groups"], reject=probe["reject_channels"], seconds=a.seconds,
                k=float(dg.get("k_mad", 10.0)), floor=float(dg.get("floor_adc", 500.0)), fig_path=figure_dir(a.cohort) / f"{stem}.png",
                csv_path=report_dir(a.cohort) / f"{stem}.csv", title=f"{animal} {a.session} FM{cp.firmware_version} layout={probe['layout']} (mapping verified={probe['verified']})")
    print(f"ARI={res['ari']:.3f} within={res['within']:.3f} between={res['between']:.3f} -> assumed grouping {res['verdict']}\n{res['figure']}\n{res['csv']}")


if __name__ == "__main__":
    main()
