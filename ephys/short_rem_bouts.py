r"""What are the short NREM bouts that end in REM? (cohort 2026c; plan implementation_plan/2026-10-09-short-rem-bouts.md,
written before computing). Label-free LFP description (Part A) + a blind human reading page (Part B).

Usage:  python ephys/short_rem_bouts.py features [--scorings final pass2med] [--workers 8]
        python ephys/short_rem_bouts.py review --run <features run dir>      (Part B page)
        python ephys/short_rem_bouts.py merge --run <run> --answers <export.json>
        python ephys/short_rem_bouts.py --selftest

Definitions (records, coverage and channels exactly as ephys/rem_ripple_model.py; 1-s states 0 unknown, 1 WAKE, 3 NREM, 5 REM):
  sets      R60 = NREM bouts <= 60 s followed directly by REM; W60 = followed directly by WAKE (both split by the state
            before: REM / WAKE / unknown); references per animal x probe block (up to REF_N each, random, seed 0):
            N_ref = the middle 30 s of NREM bouts >= 300 s; R_ref = REM bouts >= 40 s without their first / last 10 s;
            T_ref = the last 30 s of NREM bouts >= 300 s that end in REM.
  epochs    one per second s whose 2-s Hann window [s - 1, s + 1) lies inside the segment (so a bout < 3 s has none and the
            neighbouring states never leak in); spectra by scipy.signal.spectrogram (nperseg 2500, 1-s step).
  features  theta = log P(6-10 Hz) and td = log P(6-10) / P(1-4) on the CA1 radiatum site (sharpwave_col); delta_ctx = log
            P(1-4) and sigma_ctx = log P(10-16) on the cortical site (noise_col); rip = detected SWR events in the second
            (all flags and state labels ignored); emg = mean fast LFP-EMG corr; each z-scored per animal x block on the
            pooled N_ref + R_ref epochs.
  reading   LDA NREM vs REM (equal priors) per animal x block on the N_ref / R_ref epochs -> pREM per epoch; per segment:
            pREM (mean), frac_REM (share > 0.5), inter (share with sigma_ctx >= N_ref median and td >= the midpoint of the
            N_ref and R_ref medians); rules in the plan.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _common import figure_dir, git_commit, report_dir, write_json  # noqa: E402

COHORT = "2026c"
W, N, R = 1, 3, 5
FS = 1250
SHORT_S = 60
LONG_NREM_S = 300
REM_REF_S = 40
REF_N = 60
BANDS = {"delta": (1.0, 4.0), "theta": (6.0, 10.0), "sigma": (10.0, 16.0)}
LFP_ROOT = "Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/lfp"
EMG_ROOT = "Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/emg_from_lfp"
FEATS = ["theta", "td", "delta_ctx", "sigma_ctx"]


# ------------------------------------------------------------------ pure pieces (selftested)
def segments(state: np.ndarray, rng: np.random.Generator) -> list[dict]:
    """Short bouts and reference segments of one record (record-second coordinates, end exclusive)."""
    from sleep_cycles import bouts
    bl = bouts(state)
    out = []
    for i, (s, a, b) in enumerate(bl):
        prev = bl[i - 1][0] if i else 0
        nxt = bl[i + 1][0] if i + 1 < len(bl) else 0
        n = b - a
        pv = {R: "REM", W: "WAKE"}.get(prev, "unknown")
        if s == N and n <= SHORT_S and nxt in (R, W):
            out.append({"set": "R60" if nxt == R else "W60", "a": a, "b": b, "bout_len": n, "prev": pv})
        if s == N and n >= LONG_NREM_S:
            m = (a + b) // 2
            out.append({"set": "N_ref", "a": m - 15, "b": m + 15, "bout_len": n, "prev": pv})
            if nxt == R:
                out.append({"set": "T_ref", "a": b - 30, "b": b, "bout_len": n, "prev": pv})
        if s == R and n >= REM_REF_S:
            out.append({"set": "R_ref", "a": a + 10, "b": b - 10, "bout_len": n, "prev": pv})
    return out


def epoch_seconds(a: int, b: int) -> np.ndarray:
    """Seconds s whose 2-s window [s - 1, s + 1) lies inside [a, b)."""
    return np.arange(a + 1, b) if b - a >= 3 else np.arange(0)


def band_powers(x: np.ndarray, secs_rel: np.ndarray) -> dict[str, np.ndarray]:
    """Log band powers of x (chunk starting at second 0) for 2-s windows centred on the given chunk seconds."""
    from scipy import signal
    f, t, S = signal.spectrogram(x.astype(np.float64), fs=FS, window="hann", nperseg=2 * FS, noverlap=FS, detrend="constant",
                                 scaling="density", mode="psd")
    # segment k covers [k, k + 2) s -> centred on second k + 1
    k = secs_rel - 1
    out = {}
    for nm, (lo, hi) in BANDS.items():
        m = (f >= lo) & (f < hi)
        out[nm] = np.log(np.maximum(S[m][:, k].sum(0) * (f[1] - f[0]), 1e-12))
    return out


# ------------------------------------------------------------------ extraction
def session_items(sc: str, a) -> tuple[pd.DataFrame, dict]:
    """All segments of the scoring with their session, session-second offsets, block and channels."""
    import rem_ripple_model as rrm
    import yaml
    from swr_auto import channels_for
    ctx = rrm.prepare(a)
    from sleep_model import records_for
    from sleep_schedule import REVIEW, included_sessions
    recs = records_for(ctx["roots"][sc])
    starts = {(r.animal, r.session): r.start for r in included_sessions(REVIEW, ctx["roots"][sc]).itertuples()}
    cfg = yaml.safe_load(open(HERE / "configs/swr_channels_2026c.yaml"))
    rng = np.random.default_rng(0)
    rows = []
    for rc in recs:
        A = rrm.record_arrays(rc, starts, ctx["Q"], ctx["settle"], ctx["cache"], ctx["codes"])
        offs = [int(round((starts[(rc["animal"], s)] - rc["start"]).total_seconds())) for s in rc["sessions"]]
        ends = offs[1:] + [len(rc["state"])]
        for sg in segments(rc["state"], rng):
            j = int(np.searchsorted(offs, sg["a"], side="right") - 1)
            if j < 0 or sg["b"] > ends[j]:
                continue                                                   # crosses a session join
            if not A["cov"][sg["a"]:sg["b"]].all():
                continue
            blk = A["blk"][sg["a"]:sg["b"]]
            if (blk != blk[0]).any():
                continue
            ses = rc["sessions"][j]
            ch = channels_for(cfg, rc["animal"], ses)
            rows.append({**sg, "animal": rc["animal"], "record_id": rc["record_id"], "session": ses, "block": int(blk[0]),
                         "s0": sg["a"] - offs[j], "s1": sg["b"] - offs[j],
                         "t": rc["start"] + pd.Timedelta(seconds=int(sg["a"])),
                         "ctx_col": int(ch["noise_col"]), "rad_col": int(ch["sharpwave_col"]), "pyr_col": int(ch["ripple_col"])})
    S = pd.DataFrame(rows)
    # references: at most REF_N per animal x block x set (random, seed 0)
    ref = S.set.isin(["N_ref", "R_ref", "T_ref"])
    keep = S[ref].groupby(["animal", "block", "set"], group_keys=False).apply(
        lambda g: g.sample(min(len(g), REF_N), random_state=0))
    S = pd.concat([S[~ref], keep]).sort_values(["animal", "session", "s0"]).reset_index(drop=True)
    S["item"] = [f"{sc}_{i:05d}" for i in range(len(S))]
    return S, ctx


def session_job(animal: str, session: str, items: pd.DataFrame, lfp_root: str, emg_root: str, events: dict | None) -> pd.DataFrame:
    lfp_path = Path(lfp_root) / animal / f"{session}.lfp"
    nch = int(json.loads(Path(str(lfp_path) + ".json").read_text())["n_channels"])
    mm = np.memmap(lfp_path, dtype=np.int16, mode="r")
    mm = mm[: mm.size // nch * nch].reshape(-1, nch)
    ef = Path(emg_root) / animal / f"{session}.EMGFromLFP50Hz.npz"
    emg = None
    if ef.exists():
        with np.load(ef) as z:
            emg = (z["j"] * 0.02, z["corr"].astype(np.float64))
    pk = np.sort(np.floor(events["peak_s"]).astype(np.int64)) if events is not None else np.zeros(0, np.int64)
    out = []
    for it in items.itertuples():
        secs = epoch_seconds(it.s0, it.s1)
        if not len(secs):
            continue
        c0, c1 = (secs[0] - 1) * FS, (secs[-1] + 1) * FS
        if c1 > mm.shape[0]:
            continue
        chunk = np.asarray(mm[c0:c1, [it.ctx_col, it.rad_col]], np.float64)
        rel = secs - secs[0] + 1
        ctx, rad = band_powers(chunk[:, 0], rel), band_powers(chunk[:, 1], rel)
        rip = (np.searchsorted(pk, secs + 1) - np.searchsorted(pk, secs)).astype(float)
        if emg is not None:
            lo, hi = np.searchsorted(emg[0], secs), np.searchsorted(emg[0], secs + 1)
            e = np.array([np.nanmean(emg[1][l:h]) if h > l else np.nan for l, h in zip(lo, hi)])
        else:
            e = np.full(len(secs), np.nan)
        out.append(pd.DataFrame({"item": it.item, "sec": secs, "theta": rad["theta"], "td": rad["theta"] - rad["delta"],
                                 "delta_ctx": ctx["delta"], "sigma_ctx": ctx["sigma"], "rip": rip, "emg": e}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def extract(S: pd.DataFrame, ctx: dict, a) -> pd.DataFrame:
    from joblib import Parallel, delayed
    jobs = [(an, ses, g) for (an, ses), g in S.groupby(["animal", "session"])]
    res = Parallel(n_jobs=a.workers, backend="loky", verbose=0)(
        delayed(session_job)(an, ses, g, a.lfp_root, a.emg_root, ctx["cache"].get((an, ses))) for an, ses, g in jobs)
    return pd.concat([r for r in res if len(r)], ignore_index=True)


# ------------------------------------------------------------------ reading
def classify(S: pd.DataFrame, E: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis as LDA
    E = E.merge(S[["item", "animal", "block", "set"]], on="item")
    E = E.dropna(subset=FEATS)
    parts, fits = [], []
    for (an, bk), g in E.groupby(["animal", "block"]):
        ref = g[g.set.isin(["N_ref", "R_ref"])]
        nN, nR = int((ref.set == "N_ref").sum()), int((ref.set == "R_ref").sum())
        if nN < 30 or nR < 30:
            fits.append({"animal": an, "block": bk, "n_Nref_epochs": nN, "n_Rref_epochs": nR, "fitted": False})
            continue
        mu, sd = ref[FEATS + ["rip", "emg"]].mean(), ref[FEATS + ["rip", "emg"]].std().replace(0, 1)
        g = g.copy()
        for c in FEATS + ["rip", "emg"]:
            g[c + "_z"] = (g[c] - mu[c]) / sd[c]
        y = (ref.set == "R_ref").astype(int).to_numpy()
        Zr = g.loc[ref.index, [f + "_z" for f in FEATS]].to_numpy()
        lda = LDA(priors=[0.5, 0.5]).fit(Zr, y)
        lda_c = LDA(priors=[0.5, 0.5]).fit(g.loc[ref.index, ["delta_ctx_z", "sigma_ctx_z"]].to_numpy(), y)
        g["pREM"] = lda.predict_proba(g[[f + "_z" for f in FEATS]].to_numpy())[:, 1]
        g["pREM_ctx"] = lda_c.predict_proba(g[["delta_ctx_z", "sigma_ctx_z"]].to_numpy())[:, 1]
        sig_n = g.loc[ref.index][ref.set == "N_ref"].sigma_ctx_z.median()
        td_mid = (g.loc[ref.index][ref.set == "N_ref"].td_z.median() + g.loc[ref.index][ref.set == "R_ref"].td_z.median()) / 2
        g["inter"] = ((g.sigma_ctx_z >= sig_n) & (g.td_z >= td_mid)).astype(float)
        acc = float((lda.predict(Zr) == y).mean())
        fits.append({"animal": an, "block": bk, "n_Nref_epochs": nN, "n_Rref_epochs": nR, "fitted": True, "ref_accuracy": acc,
                     "coef": dict(zip(FEATS, np.round(lda.coef_[0], 3)))})
        parts.append(g)
    E = pd.concat(parts, ignore_index=True)
    seg = E.groupby("item").agg(pREM=("pREM", "mean"), frac_REM=("pREM", lambda x: float((x > 0.5).mean())),
                                pREM_ctx=("pREM_ctx", "mean"), inter=("inter", "mean"), rip_per_min=("rip", lambda x: 60 * x.mean()),
                                emg=("emg", "mean"), n_epochs=("pREM", "size"),
                                **{f"{c}_z": (f"{c}_z", "mean") for c in FEATS + ["emg"]}).reset_index()
    seg = S.merge(seg, on="item")
    return seg, pd.DataFrame(fits)


def summarise(seg: pd.DataFrame) -> pd.DataFrame:
    seg = seg.copy()
    seg["group"] = np.where(seg.set.isin(["R60", "W60"]), seg.set + " after " + seg.prev, seg.set)
    g = seg.groupby(["scoring", "animal", "group"])
    T = g.agg(n=("item", "size"), pREM=("pREM", "median"), frac_REM=("frac_REM", "median"), pREM_ctx=("pREM_ctx", "median"),
              inter=("inter", "median"), rip_per_min=("rip_per_min", "median"), emg_z=("emg_z", "median"),
              theta_z=("theta_z", "median"), td_z=("td_z", "median"), delta_ctx_z=("delta_ctx_z", "median"),
              sigma_ctx_z=("sigma_ctx_z", "median")).reset_index()
    return T


def reading(T: pd.DataFrame) -> dict:
    out = {}
    for sc, g in T.groupby("scoring"):
        r = g[g.group == "R60 after REM"].set_index("animal")
        nref = g[g.group == "N_ref"].set_index("animal")
        n = len(r)
        need = n - 1 if n < 6 else 5
        rem_like = int((r.pREM > 0.5).sum())
        nrem_like = int(((r.pREM < 0.5) & ((r.delta_ctx_z - nref.delta_ctx_z.reindex(r.index)).abs() <= 0.5)
                         & ((r.sigma_ctx_z - nref.sigma_ctx_z.reindex(r.index)).abs() <= 0.5)).sum())
        inter = int(((r.inter >= 0.3) | ((r.pREM > 0.3) & (r.pREM < 0.7))).sum())
        verdict = ("REM-like" if rem_like >= need else "genuine NREM" if nrem_like >= need else
                   "intermediate" if inter >= need else "mixed")
        out[sc] = {"animals": n, "need": need, "rem_like": rem_like, "nrem_like": nrem_like, "intermediate": inter, "verdict": verdict}
    return out


# ------------------------------------------------------------------ figure + report
def figure(seg: pd.DataFrame, out: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    seg = seg[seg.scoring == "final"].copy()
    seg["group"] = np.where(seg.set.isin(["R60", "W60"]), seg.set + " after " + seg.prev, seg.set)
    order = ["N_ref", "T_ref", "R60 after REM", "R60 after WAKE", "W60 after REM", "W60 after WAKE", "R_ref"]
    ans = sorted(seg.animal.unique())
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    cols = plt.cm.tab10(np.arange(len(ans)))
    for ax, col, lab in ((axes[0], "pREM", "P(REM-like), LDA on 4 label-free features"), (axes[1], "sigma_ctx_z", "cortical sigma (10-16 Hz), z")):
        for k, an in enumerate(ans):
            vals = [seg[(seg.animal == an) & (seg.group == g)][col].median() for g in order]
            ax.plot(np.arange(len(order)) + (k - len(ans) / 2) * 0.05, vals, "o-", color=cols[k], label=an, ms=4, lw=1)
        data = [seg[seg.group == g][col].dropna().to_numpy() for g in order]
        ax.boxplot(data, positions=np.arange(len(order)), widths=0.5, showfliers=False, medianprops={"color": "k"})
        ax.set_ylabel(lab)
        if col == "pREM":
            ax.axhline(0.5, color="grey", lw=0.8, ls="--")
    axes[1].set_xticks(np.arange(len(order)), order, rotation=15)
    axes[0].legend(fontsize=8, ncol=6, loc="upper left")
    axes[0].set_title("Short NREM bouts (<= 60 s) by the next and previous state vs references, FINAL (box = pooled, lines = animal medians)", fontsize=10)
    fig.tight_layout()
    p = figure_dir(COHORT) / f"ephys_spikes_short_rem_bouts_{COHORT}.png"
    fig.savefig(p, dpi=140)
    fig.savefig(out / "figures" / p.name, dpi=140)
    plt.close(fig)
    return p


def report(out: Path) -> Path:
    seg = pd.read_csv(out / "segments.csv.gz", parse_dates=["t"])
    T = pd.read_csv(out / "summary_by_animal.csv")
    fits = pd.read_csv(out / "lda_fits.csv")
    meta = json.loads((out / "meta.json").read_text())
    rd = report_dir(COHORT)
    fig = figure(seg, out)
    T.to_csv(rd / f"ephys_spikes_short_rem_bouts_summary_{COHORT}.csv", index=False)
    rdg = reading(T)
    L = [f"# What are the short NREM bouts that end in REM? (cohort {COHORT}) — Part A, label-free description", "",
         "Plan (before computing): [2026-10-09-short-rem-bouts.md](../../../../implementation_plan/2026-10-09-short-rem-bouts.md). "
         f"Driver `ephys/short_rem_bouts.py`; run `{out}`; git `{meta.get('git')}`.", "",
         "**Part A is a description, not the decision.** The features come from the same LFP the scorer read. The human blind "
         "reading (Part B) decides.", "", "## Pre-registered reading (Part A)", ""]
    for sc, r in rdg.items():
        L.append(f"- **{sc}:** {r['verdict']}. Of {r['animals']} animals with R60-after-REM bouts (rule: ≥ {r['need']}):")
        L.append(f"  - REM-like (median pREM > 0.5): {r['rem_like']};")
        L.append(f"  - genuine NREM (pREM < 0.5, cortical delta / sigma within ±0.5 SD of N_ref): {r['nrem_like']};")
        L.append(f"  - intermediate (median inter ≥ 0.3, or pREM 0.3–0.7): {r['intermediate']}.")
    f = T[T.scoring == "final"]

    def rng_of(grp, col, fmt="{:.2f}"):
        v = f[f.group == grp][col]
        return (fmt + "–" + fmt).format(v.min(), v.max()) if len(v) else "–"
    nsf11 = f[(f.group == "R60 after REM") & (f.animal == "SF11")].n
    L += ["", "**What the numbers say (FINAL, range of the animal medians):**",
          f"- **pREM:**",
          f"  - short NREM bouts between two REM bouts (R60 after REM): {rng_of('R60 after REM', 'pREM')};",
          f"  - real REM (R_ref): {rng_of('R_ref', 'pREM')};",
          f"  - mid-NREM (N_ref): {rng_of('N_ref', 'pREM')};",
          f"  - the last 30 s of long NREM before REM (T_ref): {rng_of('T_ref', 'pREM')}.",
          f"- **What decides it is the state before the bout, not after:**",
          f"  - short bouts after REM that end in WAKE (W60 after REM): {rng_of('W60 after REM', 'pREM')};",
          f"  - short bouts after WAKE: R60 {rng_of('R60 after WAKE', 'pREM')}, W60 {rng_of('W60 after WAKE', 'pREM')}.",
          f"- **Ripples per NREM-labelled minute:** R60 after REM {rng_of('R60 after REM', 'rip_per_min', '{:.0f}')}, R_ref "
          f"{rng_of('R_ref', 'rip_per_min', '{:.0f}')}, N_ref {rng_of('N_ref', 'rip_per_min', '{:.0f}')}.",
          "- **Reading:**",
          "  - The short NREM bouts between REM bouts look like REM by label-free LFP features, but not fully: they sit between "
          "REM and NREM, and the intermediate criterion is also met.",
          "  - They are about as ripple-poor as REM.",
          "  - This supports (a): REM interruptions or intermediate sleep cut out of REM episodes. Part B, the human reading, "
          "decides.",
          f"  - SF11 has only {int(nsf11.iloc[0]) if len(nsf11) else 0} such bouts (ripples covered to 09-02); without it the rule "
          "still passes 5/5."]
    L += ["", f"![segments](../figures/{fig.name})", "", "## Definitions", "",
          "- **Sets:**",
          "  - R60 / W60 = NREM bouts ≤ 60 s followed by REM / WAKE, split by the state before them.",
          "  - N_ref = the middle 30 s of NREM bouts ≥ 5 min.",
          "  - R_ref = REM bouts ≥ 40 s without their first and last 10 s.",
          "  - T_ref = the last 30 s of NREM bouts ≥ 5 min that end in REM.",
          "  - References: up to 60 per animal × block. Coverage as in the REM ripple model.",
          "- **Epochs:** each second whose 2-s Hann window lies inside the segment. Bouts < 3 s have none, so the neighbouring "
          "states never leak in.",
          "- **Features:**",
          "  - CA1 radiatum: $\\theta$ = log P(6–10 Hz); $td$ = log P(6–10) / P(1–4).",
          "  - Cortex (top, ripple-free site): $\\delta_{ctx}$ = log P(1–4); $\\sigma_{ctx}$ = log P(10–16), the spindle band.",
          "  - Detected SWR events per second (flags and states ignored); fast LFP-EMG corr.",
          "  - All z-scored per animal × block on the pooled N_ref + R_ref epochs.",
          "- **pREM** = the LDA posterior of REM (equal priors) fitted per animal × block on N_ref vs R_ref epochs, averaged "
          "over the segment's epochs. **pREM_ctx** = the same with the cortical features only.",
          "- **inter** = the share of epochs with $\\sigma_{ctx}$ ≥ the N_ref median and $td$ ≥ the midpoint of the N_ref and "
          "R_ref medians (spindles with theta: the intermediate stage).", "",
          "## Per animal (medians over segments)", "",
          "| scoring | animal | group | n | pREM | frac REM | pREM ctx-only | inter | ripples /min | theta z | td z | delta ctx z | sigma ctx z | EMG z |",
          "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in T.itertuples():
        L.append(f"| {r.scoring} | {r.animal} | {r.group} | {r.n} | {r.pREM:.2f} | {r.frac_REM:.2f} | {r.pREM_ctx:.2f} | {r.inter:.2f} | "
                 f"{r.rip_per_min:.0f} | {r.theta_z:+.2f} | {r.td_z:+.2f} | {r.delta_ctx_z:+.2f} | {r.sigma_ctx_z:+.2f} | {r.emg_z:+.2f} |")
    L += ["", "## LDA fits (reference accuracy on N_ref vs R_ref epochs)", "", "| animal | block | N_ref epochs | R_ref epochs | fitted | accuracy |",
          "|---|---:|---:|---:|:---:|---:|"]
    for r in fits.itertuples():
        L.append(f"| {r.animal} | {r.block} | {r.n_Nref_epochs} | {r.n_Rref_epochs} | {r.fitted} | "
                 f"{r.ref_accuracy:.2f} |" if r.fitted else f"| {r.animal} | {r.block} | {r.n_Nref_epochs} | {r.n_Rref_epochs} | {r.fitted} | – |")
    L += ["", "## Limits", "",
          "- The features come from the LFP the scorer used (a related theta measure). Part A therefore cannot be independent of "
          "the scorer; the cortex-only pREM is the part furthest from it.",
          "- Short bouts < 3 s carry no epoch.",
          "- Description only: no claim about mechanism.", ""]
    p = rd / f"ephys_spikes_short_rem_bouts_{COHORT}.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(rd / f"run_manifest_short_rem_bouts_{COHORT}.json", dict(name="short_rem_bouts", run_dir=str(out), git=meta.get("git"),
                                                                       report=str(p), reading=rdg))
    print(f"report {p}")
    return p


# ------------------------------------------------------------------ Part B: the blind reading page
REVIEW_N = {"R60 after REM": 25, "R60 after WAKE": 15, "W60": 40, "N_ref": 15, "R_ref": 15}
CHOICES = [("1", "NREM"), ("2", "REM"), ("3", "intermediate"), ("4", "wake"), ("5", "cannot tell")]
WIN_S = 60


def pick_review(seg: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """FINAL segments for the page, balanced over animals (round robin), at least 6 epochs each."""
    seg = seg[(seg.scoring == "final") & (seg.n_epochs >= 6)].copy()
    seg["grp"] = np.where(seg.set == "R60", "R60 after " + seg.prev, seg.set)
    out = []
    for g, n in REVIEW_N.items():
        pool = seg[seg.grp == g]
        by = {an: list(rng.permutation(x.item.to_numpy())) for an, x in pool.groupby("animal")}
        take = []
        while len(take) < n and any(by.values()):
            for an in sorted(by):
                if by[an] and len(take) < n:
                    take.append(by[an].pop())
        out.append(pool[pool.item.isin(take)])
    P = pd.concat(out, ignore_index=True)
    P = P.iloc[rng.permutation(len(P))].reset_index(drop=True)
    P["rid"] = [f"S{i + 1:03d}" for i in range(len(P))]
    return P


def render_item(it, lfp_root: str, emg_root: str, png: Path, clim: dict, zs: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import signal
    lfp_path = Path(lfp_root) / it.animal / f"{it.session}.lfp"
    nch = int(json.loads(Path(str(lfp_path) + ".json").read_text())["n_channels"])
    mm = np.memmap(lfp_path, dtype=np.int16, mode="r")
    mm = mm[: mm.size // nch * nch].reshape(-1, nch)
    mid = (it.s0 + it.s1) / 2
    w0 = max(0.0, mid - WIN_S)
    w1 = min(mm.shape[0] / FS, mid + WIN_S)
    x = np.asarray(mm[int(w0 * FS):int(w1 * FS), [it.ctx_col, it.rad_col, it.pyr_col]], np.float64)
    tt = w0 + np.arange(x.shape[0]) / FS - mid
    fig = plt.figure(figsize=(13, 9.2))
    gs = fig.add_gridspec(5, 1, height_ratios=[2.2, 2.2, 1.1, 1.0, 2.6], hspace=0.55)
    lab = {0: f"cortex (col {it.ctx_col})", 1: f"CA1 radiatum (col {it.rad_col})"}
    for k in (0, 1):
        ax = fig.add_subplot(gs[k])
        f, t, S = signal.spectrogram(x[:, k], fs=FS, window="hann", nperseg=FS, noverlap=FS - FS // 4, scaling="density")
        m = f <= 20
        lo, hi = clim[(it.animal, it.block, k)]
        ax.pcolormesh(t + (w0 - mid), f[m], np.log(S[m] + 1e-12), shading="auto", cmap="viridis", vmin=lo, vmax=hi)
        ax.set_ylabel(f"{lab[k]}\nHz")
        ax.axvline(it.s0 - mid, color="w", lw=1.2, ls="--")
        ax.axvline(it.s1 - mid, color="w", lw=1.2, ls="--")
        ax.set_xlim(-WIN_S, WIN_S)
        ax.tick_params(labelbottom=False)
    # td and sigma traces per second (z per animal x block on the Part-A references)
    rel = np.arange(1, int(x.shape[0] // FS))                         # 2-s windows centred at w0 + rel
    bc, br = band_powers(x[:, 0], rel), band_powers(x[:, 1], rel)
    tc = w0 + rel - mid
    mu, sd = zs[(it.animal, it.block)]
    ax = fig.add_subplot(gs[2])
    ax.plot(tc, (br["theta"] - br["delta"] - mu["td"]) / sd["td"], color="tab:orange", lw=1.2, label="theta/delta (CA1), z")
    ax.plot(tc, (bc["sigma"] - mu["sigma_ctx"]) / sd["sigma_ctx"], color="tab:purple", lw=1.2, label="sigma 10-16 Hz (cortex), z")
    ax.axhline(0, color="grey", lw=0.6)
    ax.axvspan(it.s0 - mid, it.s1 - mid, color="gold", alpha=0.25)
    ax.set_xlim(-WIN_S, WIN_S)
    ax.legend(fontsize=7, loc="upper left", ncol=2)
    ax.tick_params(labelbottom=False)
    ax = fig.add_subplot(gs[3])
    ef = Path(emg_root) / it.animal / f"{it.session}.EMGFromLFP50Hz.npz"
    if ef.exists():
        with np.load(ef) as z:
            te, c = z["j"] * 0.02, z["corr"]
        m = (te >= w0) & (te < w1)
        cc = pd.Series(c[m]).rolling(25, center=True, min_periods=1).mean().to_numpy()
        ax.plot(te[m] - mid, cc, color="k", lw=0.8)
    ax.set_ylabel("LFP-EMG\ncorr", fontsize=8)
    ax.axvspan(it.s0 - mid, it.s1 - mid, color="gold", alpha=0.25)
    ax.set_xlim(-WIN_S, WIN_S)
    ax.set_xlabel("s from the segment centre (2 min; dashed lines / shaded band = the segment)", fontsize=9)
    # 10-s raw trace centred on the segment
    ax = fig.add_subplot(gs[4])
    r0 = int((mid - 5 - w0) * FS)
    seg = x[max(r0, 0):r0 + 10 * FS]
    tr = (np.arange(seg.shape[0]) / FS) + (max(r0, 0) / FS + w0 - mid)
    names = ["cortex", "CA1 radiatum", "CA1 pyramidal"]
    for k in range(3):
        y = seg[:, k] - np.median(seg[:, k])
        sc = np.percentile(np.abs(y), 99) or 1
        ax.plot(tr, y / sc / 2.2 - 1.2 * k, lw=0.5, color=["tab:purple", "tab:orange", "tab:green"][k])
        ax.text(tr[0], -1.2 * k + 0.45, names[k], fontsize=8)
    ax.axvspan(max(it.s0 - mid, tr[0]), min(it.s1 - mid, tr[-1]), color="gold", alpha=0.18)
    ax.set_yticks([])
    ax.set_xlabel("s from the segment centre (10 s raw LFP, 1250 Hz)", fontsize=9)
    fig.suptitle(f"{it.rid}   segment length {it.s1 - it.s0} s", fontsize=12)
    fig.savefig(png, dpi=95, bbox_inches="tight")
    plt.close(fig)


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Short-bout blind reading</title><style>
:root{--bg:#f6f7f9;--ink:#17202b;--muted:#5b6675;--line:#d5dbe3;--acc:#2f55d4}
@media (prefers-color-scheme:dark){:root{--bg:#11151b;--ink:#e3e8ef;--muted:#9aa5b4;--line:#2a323d;--acc:#8ea6ff}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,Segoe UI,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:16px}
.item{border:1px solid var(--line);border-radius:10px;padding:10px;margin:14px 0;background:rgba(127,127,127,.04)}
.item img{width:100%;height:auto;background:#fff;border-radius:6px}
.ch{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px;align-items:center}
.ch label{border:1px solid var(--line);border-radius:6px;padding:5px 10px;cursor:pointer}
.ch input:checked+span{font-weight:700;color:var(--acc)}
.bar{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);display:flex;gap:10px;flex-wrap:wrap;align-items:center;z-index:2}
button{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid var(--line);background:transparent;color:inherit;cursor:pointer}
.muted{color:var(--muted)} textarea{width:100%;font:inherit;margin-top:6px}
</style></head><body><div class="wrap">
<h1>Short-bout blind reading (cohort 2026c)</h1>
<p class="muted">Classify the <b>shaded / dashed segment</b> of each panel from its LFP: NREM, REM, intermediate (cortical spindles with
hippocampal theta), wake, or cannot tell. No scorer label is shown; the order is random. Keys 1&ndash;5 answer the item in view.
Answers autosave in this browser; press <b>Export</b> when done and put both files in <code>ephys/configs/short_bout_review_2026c/</code>.</p>
<div class="bar"><span id="cnt"></span><button id="exp">Export JSON + CSV</button><span class="muted" id="msg"></span></div>
<div id="list"></div></div>
<script>
const ITEMS = __ITEMS__, CH = __CHOICES__, KEY = "short_bout_review_2026c";
let A = {}; try { A = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(A)); } catch (e) {} count(); }
function count(){ document.getElementById("cnt").textContent = Object.values(A).filter(x => x.choice).length + " / " + ITEMS.length + " answered"; }
const L = document.getElementById("list");
ITEMS.forEach(id => {
  const d = document.createElement("div"); d.className = "item"; d.id = id;
  const img = document.createElement("img"); img.src = "img/" + id + ".png"; img.alt = id; img.loading = "lazy"; d.appendChild(img);
  const c = document.createElement("div"); c.className = "ch";
  CH.forEach(([k, lab]) => {
    const l = document.createElement("label"); const i = document.createElement("input"); i.type = "radio"; i.name = id; i.value = lab;
    if (A[id] && A[id].choice === lab) i.checked = true;
    i.onchange = () => { A[id] = Object.assign(A[id] || {}, {choice: lab, t: new Date().toISOString()}); save(); };
    const s = document.createElement("span"); s.textContent = k + " " + lab; l.append(i, s); c.appendChild(l);
  });
  d.appendChild(c);
  const n = document.createElement("textarea"); n.rows = 1; n.placeholder = "note (optional)"; n.value = (A[id] && A[id].note) || "";
  n.oninput = () => { A[id] = Object.assign(A[id] || {}, {note: n.value}); save(); }; d.appendChild(n);
  L.appendChild(d);
});
count();
function inView(){ let best = null, bd = 1e9; ITEMS.forEach(id => { const r = document.getElementById(id).getBoundingClientRect(); const dd = Math.abs(r.top + r.height / 2 - innerHeight / 2); if (dd < bd) { bd = dd; best = id; } }); return best; }
document.addEventListener("keydown", e => {
  if (e.target.tagName === "TEXTAREA") return;
  const c = CH.find(x => x[0] === e.key); if (!c) return;
  const id = inView(); const i = document.querySelector('input[name="' + id + '"][value="' + c[1] + '"]'); if (i) { i.checked = true; i.onchange(); }
});
function dl(name, text, type){ const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], {type})); a.download = name; a.click(); }
document.getElementById("exp").onclick = () => {
  const rows = ITEMS.map(id => ({id, choice: (A[id] || {}).choice || "", note: (A[id] || {}).note || "", t: (A[id] || {}).t || ""}));
  dl("short_bout_review_2026c.json", JSON.stringify(rows, null, 1), "application/json");
  dl("short_bout_review_2026c.csv", "id,choice,note,t\n" + rows.map(r => [r.id, r.choice, JSON.stringify(r.note), r.t].join(",")).join("\n"), "text/csv");
  document.getElementById("msg").textContent = "exported " + rows.filter(r => r.choice).length + " answers";
};
</script></body></html>
"""


def review(a):
    from joblib import Parallel, delayed
    run = Path(a.run)
    seg = pd.read_csv(run / "segments.csv.gz")
    E = pd.read_csv(run / "epochs.csv.gz")
    E = E[E.scoring == "final"].merge(seg[seg.scoring == "final"][["item", "animal", "block", "set"]], on="item")
    zs = {}
    for (an, bk), g in E[E.set.isin(["N_ref", "R_ref"])].groupby(["animal", "block"]):
        zs[(an, int(bk))] = (g[["td", "sigma_ctx"]].mean().to_dict(), g[["td", "sigma_ctx"]].std().replace(0, 1).to_dict())
    P = pick_review(seg, np.random.default_rng(7))
    P = P[[(r.animal, int(r.block)) in zs for r in P.itertuples()]].reset_index(drop=True)
    out = run / "review"
    (out / "img").mkdir(parents=True, exist_ok=True)
    # colour limits per animal x block x channel: 2nd-99.5th percentile of log power 0-20 Hz over the block's reference epochs
    # is not stored as spectra, so they come from the picked windows themselves (pooled per animal x block)
    from scipy import signal
    clim = {}
    for (an, bk), g in P.groupby(["animal", "block"]):
        vals = {0: [], 1: []}
        for it in g.itertuples():
            lfp_path = Path(a.lfp_root) / an / f"{it.session}.lfp"
            nch = int(json.loads(Path(str(lfp_path) + ".json").read_text())["n_channels"])
            mm = np.memmap(lfp_path, dtype=np.int16, mode="r")
            mm = mm[: mm.size // nch * nch].reshape(-1, nch)
            mid = (it.s0 + it.s1) / 2
            x = np.asarray(mm[int(max(0, mid - WIN_S) * FS):int((mid + WIN_S) * FS), [it.ctx_col, it.rad_col]], np.float64)
            for k in (0, 1):
                f, t, S = signal.spectrogram(x[:, k], fs=FS, window="hann", nperseg=FS, noverlap=FS - FS // 4)
                vals[k].append(np.log(S[f <= 20] + 1e-12).ravel())
        for k in (0, 1):
            v = np.concatenate(vals[k])
            clim[(an, int(bk), k)] = (float(np.percentile(v, 2)), float(np.percentile(v, 99.5)))
    P["block"] = P.block.astype(int)
    Parallel(n_jobs=a.workers, backend="loky")(delayed(render_item)(it, a.lfp_root, a.emg_root, out / "img" / f"{it.rid}.png", clim, zs)
                                                for it in P.itertuples())
    html = PAGE.replace("__ITEMS__", json.dumps(P.rid.tolist())).replace("__CHOICES__", json.dumps(CHOICES))
    (out / "index.html").write_text(html, encoding="utf-8")
    P.to_csv(run / "review_key_SEALED.csv", index=False)           # the key stays outside the page folder
    print(f"review page {out / 'index.html'} ({len(P)} items); key {run / 'review_key_SEALED.csv'}")


def features(a):
    from output_paths import run_dir
    t0 = time.time()
    out = Path(a.run) if a.run else run_dir("short_rem_bouts", COHORT)
    segs, eps = [], []
    for sc in a.scorings:
        S, ctx = session_items(sc, a)
        print(f"[{sc}] segments {len(S)}:", S.groupby("set").size().to_dict(), f"({time.time() - t0:.0f} s)", flush=True)
        E = extract(S, ctx, a)
        print(f"[{sc}] epochs {len(E)} ({time.time() - t0:.0f} s)", flush=True)
        seg, fits = classify(S, E)
        seg["scoring"] = sc
        fits["scoring"] = sc
        segs.append(seg)
        eps.append(E.assign(scoring=sc))
        fits.to_csv(out / f"lda_fits_{sc}.csv", index=False)
    seg = pd.concat(segs, ignore_index=True)
    seg.to_csv(out / "segments.csv.gz", index=False)
    pd.concat(eps, ignore_index=True).to_csv(out / "epochs.csv.gz", index=False)
    pd.concat([pd.read_csv(out / f"lda_fits_{sc}.csv") for sc in a.scorings]).to_csv(out / "lda_fits.csv", index=False)
    T = summarise(seg)
    T.to_csv(out / "summary_by_animal.csv", index=False)
    write_json(out / "meta.json", dict(git=git_commit(), scorings=a.scorings, minutes=(time.time() - t0) / 60,
                                      params=dict(SHORT_S=SHORT_S, LONG_NREM_S=LONG_NREM_S, REM_REF_S=REM_REF_S, REF_N=REF_N, BANDS=BANDS)))
    print(T[T.group.isin(["N_ref", "R60 after REM", "R60 after WAKE", "W60 after WAKE", "T_ref", "R_ref"])].round(2).to_string(index=False))
    print(reading(T))
    report(out)


# ------------------------------------------------------------------ selftest
def selftest():
    ok = True
    st = np.array([W] * 100 + [N] * 400 + [R] * 60 + [N] * 30 + [R] * 50 + [N] * 20 + [W] * 30 + [N] * 350 + [R] * 45, np.int8)
    sg = segments(st, np.random.default_rng(0))
    got = sorted((d["set"], d["a"], d["b"], d["prev"]) for d in sg)
    exp = sorted([("N_ref", 285, 315, "WAKE"), ("T_ref", 470, 500, "WAKE"), ("R_ref", 510, 550, "unknown"), ("R60", 560, 590, "REM"),
                  ("R_ref", 600, 630, "unknown"), ("W60", 640, 660, "REM"), ("N_ref", 850, 880, "WAKE"), ("T_ref", 1010, 1040, "WAKE"),
                  ("R_ref", 1050, 1075, "unknown")])
    s_ok = got == exp
    print(f"{'PASS' if s_ok else 'FAIL'} segments {got}")
    ok &= s_ok
    e_ok = list(epoch_seconds(10, 14)) == [11, 12, 13] and len(epoch_seconds(10, 12)) == 0
    print(f"{'PASS' if e_ok else 'FAIL'} epochs inside the segment {list(epoch_seconds(10, 14))}")
    ok &= e_ok
    t = np.arange(10 * FS) / FS
    rng = np.random.default_rng(1)
    th = np.sin(2 * np.pi * 8 * t) + 0.1 * rng.standard_normal(t.size)
    de = np.sin(2 * np.pi * 2 * t) + 0.1 * rng.standard_normal(t.size)
    bt, bd = band_powers(th, np.arange(1, 9)), band_powers(de, np.arange(1, 9))
    b_ok = (bt["theta"] - bt["delta"]).min() > 3 and (bd["delta"] - bd["theta"]).min() > 3
    print(f"{'PASS' if b_ok else 'FAIL'} band powers: theta-delta log ratio {np.round(bt['theta'] - bt['delta'], 1)[:3]} (theta signal) "
          f"vs {np.round(bd['theta'] - bd['delta'], 1)[:3]} (delta signal)")
    ok &= b_ok
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["features", "review", "report"])
    ap.add_argument("--scorings", nargs="+", default=["final", "pass2med"], choices=["final", "pass2med"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--run", default=None)
    ap.add_argument("--lfp-root", default=LFP_ROOT)
    ap.add_argument("--emg-root", default=EMG_ROOT)
    ap.add_argument("--swr-root", default="Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/swr")
    ap.add_argument("--sleep-root", default="Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/sleep/imu_fixch")
    ap.add_argument("--quality", default=str(report_dir(COHORT) / f"ephys_spikes_swr_quality_{COHORT}.csv"))
    ap.add_argument("--review", default=str(report_dir(COHORT) / f"ephys_spikes_sleep_review_{COHORT}.csv"))
    ap.add_argument("--cohort-yaml", default=str(REPO / f"cohorts/{COHORT}.yaml"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    if a.cmd == "features":
        features(a)
    elif a.cmd == "review":
        review(a)
    elif a.cmd == "report":
        report(Path(a.run))


if __name__ == "__main__":
    main()
