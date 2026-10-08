"""Choose SWR detection channels for one cohort-3 session (one per animal x probe block) from the LFP itself
(plan: implementation_plan/2026-10-07-swr-detection-automation.md).

Within the --hours (default 2) window of the session with the most NREM (final 1-s sleep states), during NREM, for every live column (final channel map; skip = dead/bridged):
  burst        99th / 50th percentile of its 80-250 Hz DetectSWR envelope (ripple-band burstiness; pass 1)
  ratio        median envelope at NREM ripple peaks / median at random times (pass 2; peaks = z > 4 local maxima of
               the ripple column, >= 50 ms apart; the same metric used to vet the reference sessions' noise channels)
  corr         correlation of its log envelope with the ripple column's at those peaks
  spw_uV       mean 2-50 Hz LFP at the peaks (sharp wave; positive above the pyramidal layer, negative in radiatum)
Proposal:
  ripple_col     the largest pass-2 ratio
  sharpwave_col  the most negative sharp wave on the ripple column's shank, below it
  noise_col      among each shank's top 3 live sites, the smallest ratio (user rule: cortical, top, no ripple)
  shank_ripple   each shank's largest ratio
Writes <out>/<SFxx>_<session>_scan.csv (per column), _proposal.yaml (paste into configs/swr_channels_<c>.yaml after the
user's check), and _profile.png (ratio and SPW by depth per shank).

  python ephys/swr_channel_scan.py --animal SF07 --session 15_20260902_082418.755 --out DIR [--lfp-root ...] [--xml ...]
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swr_detect as sd  # noqa: E402

SR = 1250.0
UV = 0.195
HERE = Path(__file__).resolve().parent
XML = {"SF07": "SF07_A4x16-Lin_lfporder_20261006.xml", "SF08": "SF08_A4x16-Lin_lfporder_20261006.xml",
       "SF09": "SF09_A5x12-16_lfporder_20261007.xml", "SF10": "SF10_A4x16-Lin_lfporder_20261006.xml",
       "SF11": "SF11_A4x16-Lin_lfporder_20261006.xml", "SF12": "SF12_A4x16-Lin_lfporder_20261006.xml"}


def shanks_from_xml(path: Path):
    """[(shank number, [(col, skip), ...] top -> bottom)] from the anatomical groups of a Neuroscope XML."""
    out = []
    for gi, g in enumerate(ET.parse(path).getroot().findall("anatomicalDescription/channelGroups/group"), 1):
        out.append((gi, [(int(c.text), c.get("skip", "0") == "1") for c in g.findall("channel")]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--animal", required=True)
    ap.add_argument("--session", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lfp-root", default="Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/lfp")
    ap.add_argument("--states-root", default="D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final")
    ap.add_argument("--xml", default=None)
    ap.add_argument("--redo", action="store_true", help="recompute the per-column scan")
    ap.add_argument("--hours", type=float, default=2.0, help="scan the window of this length with the most NREM")
    ap.add_argument("--extra-bad", type=int, nargs="*", default=[], help="0-based columns to exclude (e.g. per-session failures)")
    a = ap.parse_args()
    xml = Path(a.xml) if a.xml else HERE / "configs/xml" / XML[a.animal]
    shanks = shanks_from_xml(xml)
    skip = {c for _, g in shanks for c, s in g if s} | set(a.extra_bad)
    live = [c for _, g in shanks for c, s in g if c not in skip]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"{a.animal}_{a.session}"
    import pandas as pd
    if Path(f"{stem}_scan.csv").exists() and not a.redo:  # the per-column scan is the slow part (~12 min); reuse it
        df = pd.read_csv(f"{stem}_scan.csv")
        meta = json.loads(Path(f"{stem}_scan.json").read_text()) if Path(f"{stem}_scan.json").exists() else {}
        n_pk = meta.get("n_nrem_ripple_peaks", "?")
    else:
        df, n_pk = scan(a, shanks, skip, live)
        df.to_csv(f"{stem}_scan.csv", index=False)
        Path(f"{stem}_scan.json").write_text(json.dumps(dict(n_nrem_ripple_peaks=n_pk, xml=str(xml), skip=sorted(skip))))
    propose(a, df, shanks, stem, n_pk)


def scan(a, shanks, skip, live):
    lfp_path = Path(a.lfp_root) / a.animal / f"{a.session}.lfp"
    nchan = int(json.loads(Path(str(lfp_path) + ".json").read_text())["n_channels"])
    mm = np.memmap(lfp_path, dtype=np.int16, mode="r")
    n_all = mm.size // nchan
    st = np.load(Path(a.states_root) / a.animal / f"{a.session}.states.npz")
    # the --hours window with the most NREM (contiguous rows: a fraction of the file is read)
    nrem_flag = np.zeros(int(n_all / SR) + 2, int)
    nrem_flag[np.clip(st["ts"][st["state"] == 3].astype(int), 0, nrem_flag.size - 1)] = 1
    w = int(a.hours * 3600)
    if w < nrem_flag.size:
        cs = np.concatenate([[0], np.cumsum(nrem_flag)])
        w0 = int(np.argmax(cs[w:] - cs[:-w]))
    else:
        w0, w = 0, nrem_flag.size
    r0, r1 = int(w0 * SR), min(int((w0 + w) * SR), n_all)
    X = np.asarray(mm[r0 * nchan: r1 * nchan]).reshape(-1, nchan)
    n = X.shape[0]
    in_nrem = np.zeros(n, bool)
    for s0 in st["ts"][st["state"] == 3]:
        i0 = int(s0 * SR) - r0
        if 0 <= i0 < n:
            in_nrem[i0: i0 + int(SR)] = True
    print(f"window {w0 / 3600:.2f}-{(w0 + w) / 3600:.2f} h of {n_all / SR / 3600:.2f} h, NREM {in_nrem.mean() * 100:.0f} %", flush=True)
    p = sd.Params()
    h1, h2 = sd.makegausslpfir(80, SR, 6), sd.makegausslpfir(250, SR, 6)
    pw = sd.makegausslpfir(165 / np.pi, SR, 6)
    hs1, hs2 = sd.makegausslpfir(2, SR, 6), sd.makegausslpfir(50, SR, 6)

    def env(x):
        r = sd.firfilt(x.astype(float), h2)
        return sd.firfilt(np.abs(r - sd.firfilt(r, h1)), pw).astype(np.float32)

    E = {c: env(X[:, c]) for c in live}
    burst = {c: float(np.percentile(E[c][in_nrem], 99) / np.median(E[c][in_nrem])) for c in live}
    rcol = max(live, key=lambda c: burst[c])
    er = E[rcol].astype(float)
    z = (er - np.median(er)) / (1.4826 * np.median(np.abs(er - np.median(er))))
    pk, _ = find_peaks(z, height=4, distance=int(0.05 * SR))
    pk = pk[in_nrem[pk]]
    pk = pk[(pk > 200) & (pk < n - 200)]
    rnd = np.random.default_rng(0).integers(0, n, 20000)
    rows = []
    for sh, g in shanks:
        for depth, (c, s) in enumerate(g):
            r = dict(shank=sh, depth_index=depth, col=c, skip=bool(c in skip))
            if c in E:
                e = E[c].astype(float)
                low = sd.firfilt(X[:, c].astype(float), hs2)
                low = low - sd.firfilt(low, hs1)
                r.update(burst=round(burst[c], 3), ratio=round(float(np.median(e[pk]) / np.median(e[rnd])), 3),
                         corr=round(float(np.corrcoef(np.log(er[pk] + 1e-9), np.log(e[pk] + 1e-9))[0, 1]), 3),
                         spw_uV=round(float(np.mean(low[pk]) * UV), 1))
            rows.append(r)
    import pandas as pd
    return pd.DataFrame(rows), int(pk.size)


def propose(a, df, shanks, stem, n_pk):
    import pandas as pd
    L = df[~df.skip & df.ratio.notna()]
    ripple = int(L.loc[L.ratio.idxmax(), "col"])
    rsh = int(L.loc[L.col == ripple, "shank"].iloc[0])
    rdep = int(L.loc[L.col == ripple, "depth_index"].iloc[0])
    # sharp wave: the most negative SPW below the ripple site on its shank; else the most negative anywhere (cross-shank,
    # as in the lab's PPP4 run); else (no reversal on the probe = above the pyramidal layer) the least positive SPW on the
    # ripple shank, which still contrasts depth - flagged
    below = L[(L.shank == rsh) & (L.depth_index > rdep) & (L.spw_uV < 0)]
    neg = L[(L.spw_uV < 0) & (L.col != ripple)]
    flags = []
    if len(below):
        sw = int(below.loc[below.spw_uV.idxmin(), "col"])
    elif len(neg):
        sw = int(neg.loc[neg.spw_uV.idxmin(), "col"])
        flags.append("sharp wave on another shank")
    else:
        same = L[(L.shank == rsh) & (L.col != ripple)]
        sw = int(same.loc[same.spw_uV.idxmin(), "col"])
        flags.append("no sharp-wave reversal on the probe (above the pyramidal layer): SW = least positive site")
    tops = pd.concat([g.sort_values("depth_index").head(3) for _, g in L.groupby("shank")])
    tops = tops[~tops.col.isin([ripple, sw])]
    nz = tops.loc[tops.ratio.idxmin()]
    noise = int(nz["col"])
    if nz["ratio"] > 1.5 or nz["corr"] > 0.3:
        flags.append(f"noise site not ripple-free (ratio {nz['ratio']:.2f}, corr {nz['corr']:.2f})")
    shank_ripple = {int(sh): int(g.loc[g.ratio.idxmax(), "col"]) for sh, g in L.groupby("shank")}
    swv = float(L.loc[L.col == sw, "spw_uV"].iloc[0])
    prop = dict(ripple_col=ripple, sharpwave_col=sw, noise_col=noise, shank_ripple=shank_ripple, flags=flags,
                source=(f"swr_channel_scan on {a.session}: {n_pk} NREM ripple peaks; ripple col {ripple} (shank {rsh}) ratio "
                        f"{L.ratio.max():.2f}; SW col {sw} ({swv:.0f} uV); noise col {noise} ratio {nz['ratio']:.2f} "
                        f"corr {nz['corr']:.2f}"),
                confirmed=False)
    Path(f"{stem}_proposal.yaml").write_text(json.dumps(prop, indent=1))
    print(json.dumps(prop, indent=1))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, len(shanks), figsize=(3 * len(shanks), 7), sharey="row", squeeze=False)
    for j, (sh, g) in enumerate(shanks):
        d = df[df.shank == sh].sort_values("depth_index")
        for i, (col, lab) in enumerate((("ratio", "ripple ratio at NREM ripples"), ("spw_uV", "sharp wave (uV)"))):
            ax = axes[i, j]
            ok = d[col].notna()
            ax.plot(d.loc[ok, col], -d.loc[ok, "depth_index"], "o-", ms=3)
            for _, r in d.iterrows():
                if r.notna()[col]:
                    mark = "R" if r.col == ripple else "S" if r.col == sw else "N" if r.col == noise else ""
                    ax.annotate(f"{int(r.col)}{(' ' + mark) if mark else ''}", (r[col], -r.depth_index), fontsize=6)
            if i == 0:
                ax.axvline(1, color="0.6", lw=0.5)
            ax.set_title(f"shank {sh}" if i == 0 else "", fontsize=9)
            ax.set_xlabel(lab, fontsize=8)
    axes[0, 0].set_ylabel("depth index (top = 0)")
    fig.suptitle(f"{a.animal} {a.session}: R ripple, S sharp wave, N noise (proposal)", fontsize=10)
    fig.tight_layout()
    fig.savefig(f"{stem}_profile.png", dpi=110)


if __name__ == "__main__":
    main()
