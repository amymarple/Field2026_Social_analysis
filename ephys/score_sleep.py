r"""Sleep-state scoring (WAKE / NREM / REM) of cohort-3 LFP with the IMU as the EMG (plan: 2026-09-28-sleep-scoring-imu.md).

Scorer: PreprocessPipeline `src/preprocess/state_scoring.py` (the MATLAB-parity SleepScoreMaster port; chosen over the
Sleep_dynamics copy, see the plan), imported unmodified from --pipeline-root. Nothing is patched: the IMU enters by writing
`<basename>.EMGFromLFP.LFP.mat` BEFORE the call - the scorer reuses an existing EMG file - so its EMG slot carries
    EMG(t) = log10( mean VeDBA over [t - 1 s, t + 1 s] + 0.01 )      t = 0.5, 1.0, ... s (2 Hz, as getEMGFromLFP)
(VeDBA from ephys/make_imu.py, m/s^2). The scorer smooths it (15 s), min-max normalises it and puts its threshold at the
histogram dip, which for the IMU is the still / active valley (per-animal 0.31-0.39 m/s^2 on the raw per-second VeDBA).

Variants (one folder each; the user reviews and picks):
  imu           IMU in the EMG slot, useEMG_NREM=False  -> MATLAB rule: movement gates REM only; NREM = slow wave
  imu_nremgate  IMU in the EMG slot, useEMG_NREM=True   -> NREM also requires low movement (moving + slow wave = WAKE)
  lfpemg        the scorer's own LFP-EMG (300-600 Hz correlation of a 450-Hz-low-passed .lfp)  -> the standard baseline
Per session and variant: <out>/<variant>/<SFxx>/<session>/ holds the .lfp as a HARD LINK to <analysis_root>/lfp (no copy),
a session.mat built from the animal's XML (ephys/configs/probes_<c>.yaml), the scorer outputs, and complex_system/ with a
COPY of the automatic SleepState for manual review - state_editor.py loads and saves complex_system/ first, so manual
edits never touch (and are never overwritten by) the automatic result. The channel-selection result (SleepScoreLFP) is
computed once and copied into the other variants.

No excluded time is passed in this version: the scorer fills excluded (ignoretime) bins from their neighbours (see the
plan), so a session whose IMU has frozen / invalid / NaN seconds is refused until the gap-aware shim is validated.

Reports (rebuilt from every <out>/*/*/*/score_sleep.json on each run, so a partial rerun never drops rows):
  results/<c>/ephys_spikes/reports/ephys_spikes_sleep_pilot_<c>.csv            one row per session x variant
  results/<c>/ephys_spikes/reports/ephys_spikes_sleep_pilot_agreement_<c>.csv  epoch agreement + kappa per variant pair

Usage (local first):
  python ephys/score_sleep.py --cohort 2026c --sessions SF08:6_20260910_082629.685 SF07:15_20260902_082418.755 \
      [--variants imu imu_nremgate lfpemg] [--pipeline-root D:/Documents/ayalab/PreprocessPipeline]
  python ephys/score_sleep.py --cohort 2026c          # no sessions: only rebuild the two CSVs
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import yaml
from scipy.io import loadmat, savemat

from _common import PROJECT_ROOT, analysis_root, ephys_block, git_commit, report_dir, resolve_cohort, utc_now_iso

VARIANTS = {"imu": ("imu", False), "imu_nremgate": ("imu", True), "lfpemg": ("lfp", False)}
EMG_FS = 2.0
EMG_WIN_S = 2.0
EMG_EPS = 0.01


def pipeline_module(root: str | None):
    root = Path(root or os.environ.get("PREPROCESS_PIPELINE_ROOT") or "D:/Documents/ayalab/PreprocessPipeline")
    sys.path.insert(0, str(root))
    import src.preprocess.state_scoring as ss          # noqa: E402
    from src.preprocess.metafile import PreprocessConfig  # noqa: E402
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.call(["git", "-C", str(root), "diff", "--quiet", "--", "src/preprocess/state_scoring.py"]) != 0
    return ss, PreprocessConfig, f"{commit}{'+dirty' if dirty else ''}", root


def session_struct(cohort: str, animal: str) -> dict:
    """Minimal buzcode session struct from the animal's XML: 64 exported columns, spike groups (1-based) = shanks,
    Bad = XML skip='1' channels (1-based)."""
    probes = yaml.safe_load(open(PROJECT_ROOT / ephys_block(cohort)["probe_config"], encoding="utf-8"))
    entry = (probes.get("animals") or probes).get(animal) or {}
    xml_path = PROJECT_ROOT / entry["xml"]
    root = ET.parse(xml_path).getroot()
    groups = []
    for grp in root.iter("group"):
        chs = [int(c.text) for c in grp.iter("channel")]
        if chs and grp.find("../..") is not None:
            groups.append(chs)
    sd = root.find("spikeDetection")
    spike_groups = [[int(c.text) for c in g.iter("channel")] for g in sd.iter("group")] if sd is not None else groups
    ad = root.find("anatomicalDescription")
    bad = sorted({int(c.text) for c in ad.iter("channel") if c.get("skip") == "1"}) if ad is not None else []
    return {
        "general": {"name": animal},
        "extracellular": {"nChannels": 64, "sr": 20000.0, "srLfp": 1250.0,
                          "spikeGroups": {"channels": [np.asarray(g, dtype=np.float64) + 1 for g in spike_groups if g]}},
        "channelTags": {"Bad": {"channels": np.asarray(bad, dtype=np.float64) + 1}},
        "_xml": str(xml_path.relative_to(PROJECT_ROOT)),
    }


def imu_emg(npz_path: Path, duration_s: float) -> dict:
    with np.load(npz_path) as z:
        v, t, fs = z["vedba_ms2"].astype(np.float64), z["t_logger_s"], float(z["fs"])
        bad = np.zeros(len(v), bool)
        for key in ("frozen", "invalid"):
            if key in z.files:
                bad |= z[key]
    if bad.any() or np.isnan(v).any():
        raise SystemExit(f"{npz_path.name}: IMU has frozen / invalid / NaN samples - excluded time is not supported yet (see docstring)")
    tt = np.arange(1, int(duration_s * EMG_FS)) / EMG_FS
    half = int(EMG_WIN_S / 2 * fs)
    c = np.cumsum(np.r_[0.0, v])
    idx = np.clip(np.rint(tt * fs).astype(int), 0, len(v))
    lo, hi = np.clip(idx - half, 0, len(v)), np.clip(idx + half, 0, len(v))
    mean = (c[hi] - c[lo]) / np.maximum(hi - lo, 1)
    return {"timestamps": tt.reshape(-1, 1), "data": np.log10(mean + EMG_EPS).reshape(-1, 1),
            "channels": np.zeros((1, 1)), "detectorName": "IMU_VeDBA_log10 (ephys/score_sleep.py)",
            "samplingFrequency": np.asarray([[int(EMG_FS)]], dtype=np.uint8)}


def link_or_fail(src: Path, dst: Path) -> None:
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError as e:
        raise SystemExit(f"cannot hard-link {src} -> {dst} ({e}); refusing to copy a {src.stat().st_size / 1e9:.1f} GB file")


def score_one(ss, Cfg, pp_commit, cohort: str, animal: str, session: str, variant: str, out_root: Path, lfp_root: Path,
              imu_root: Path, sslfp_cache: dict) -> dict:
    emg_kind, nrem_gate = VARIANTS[variant]
    bp = out_root / variant / animal / session
    bp.mkdir(parents=True, exist_ok=True)
    lfp = lfp_root / animal / f"{session}.lfp"
    link_or_fail(lfp, bp / f"{session}.lfp")
    sess = session_struct(cohort, animal)
    savemat(bp / f"{session}.session.mat", {"session": {k: v for k, v in sess.items() if not k.startswith("_")}})
    duration = os.path.getsize(lfp) / (64 * 2) / 1250.0
    if emg_kind == "imu":
        emg = imu_emg(imu_root / animal / f"{session}.imu.npz", duration)
        savemat(bp / f"{session}.EMGFromLFP.LFP.mat", {"EMGFromLFP": emg})
    key = (animal, session)
    if key in sslfp_cache and not (bp / f"{session}.SleepScoreLFP.LFP.mat").exists():
        shutil.copy2(sslfp_cache[key], bp / f"{session}.SleepScoreLFP.LFP.mat")
    cfg = Cfg(basepath=bp)
    cfg.state_score = True
    cfg.useEMG_NREM = bool(nrem_gate)
    cfg.state_save_lfp_mat = True
    t0 = time.time()
    res = ss.run_state_scoring(basepath=bp, basename=session, session_struct=sess, pulses=None, config=cfg)
    sslfp = bp / f"{session}.SleepScoreLFP.LFP.mat"
    if sslfp.exists():
        sslfp_cache.setdefault(key, sslfp)
    auto = bp / f"{session}.SleepState.states.mat"
    review = bp / "complex_system" / f"{session}.SleepState.states.mat"
    if auto.exists() and not review.exists():             # seed the manual-review copy once; never overwrite it
        review.parent.mkdir(exist_ok=True)
        shutil.copy2(auto, review)
    st = loadmat(auto, simplify_cells=True)["SleepState"]
    idx = st["idx"]
    states = np.asarray(idx["states"]).reshape(-1)
    ts = np.asarray(idx["timestamps"]).reshape(-1)
    ssm = (st.get("detectorinfo") or {}).get("detectionparms", {}).get("SleepScoreMetrics", {}) or {}
    metrics = {**(ssm.get("histsandthreshs") or {}), "SWchanID": ssm.get("SWchanID"), "THchanID": ssm.get("THchanID")}
    frac = {name: float(np.mean(states == code)) for name, code in (("wake", 1), ("nrem", 3), ("rem", 5), ("unscored", 0))}
    info = {"animal": animal, "session": session, "variant": variant, "basepath": str(bp), "elapsed_s": round(time.time() - t0, 1),
            **{f"frac_{k}": round(v, 4) for k, v in frac.items()},
            "rem_share_of_sleep": round(frac["rem"] / max(1e-9, frac["rem"] + frac["nrem"]), 4),
            "swthresh": metrics.get("swthresh"), "EMGthresh": metrics.get("EMGthresh"), "THthresh": metrics.get("THthresh"),
            "SWchan": metrics.get("SWchanID"), "THchan": metrics.get("THchanID"),
            "scorer": f"PreprocessPipeline {pp_commit}", "xml": sess["_xml"], "git_commit": git_commit(), "written_utc": utc_now_iso()}
    info.update(imu_consistency(imu_root / animal / f"{session}.imu_1s.csv", animal, ts, states))
    (bp / "score_sleep.json").write_text(json.dumps(info, indent=2, default=str), encoding="utf-8")
    return info


IMU_STILL_THR = {"SF07": 0.387, "SF08": 0.307, "SF09": 0.325, "SF10": 0.325, "SF11": 0.387, "SF12": 0.365}  # m/s^2, 2026-09-28


def imu_consistency(imu1: Path, animal: str, ts: np.ndarray, states: np.ndarray) -> dict:
    """Score vs IMU movement, per second s (independent of the variant; theta_a = IMU_STILL_THR[animal]):
      moving(s) = VeDBA_1s(s) >= theta_a;   run(s) = length (s) of the unbroken moving run containing s
      moving_scored_wake         = mean_{moving} [state(s) = WAKE]
      sustained_moving_scored_wake = mean_{moving, run >= 30 s} [state(s) = WAKE]   (acceptance: >= 0.95)
      brief_moving_scored_sleep  = mean_{moving, run < 5 s} [state(s) in {NREM, REM}]  (twitches / shifts inside sleep)
      still_scored_sleep         = mean_{not moving} [state(s) in {NREM, REM}]
    """
    if not imu1.exists():
        return {}
    import pandas as pd
    d = pd.read_csv(imu1, usecols=["sec", "vedba_mean"])
    v = d["vedba_mean"].to_numpy()
    s_at = np.interp(d["sec"].to_numpy() + 0.5, ts, states, left=0, right=0).round()
    moving = v >= IMU_STILL_THR[animal]
    still = v < IMU_STILL_THR[animal]                      # NaN (frozen / invalid) is neither
    edges = np.flatnonzero(np.diff(np.r_[0, moving.astype(np.int8), 0]))
    run = np.zeros(len(v), int)
    for a, b in zip(edges[::2], edges[1::2]):
        run[a:b] = b - a
    sleep = np.isin(s_at, (3, 5))

    def frac(x, m):
        return round(float(np.mean(x[m])), 4) if m.any() else None
    return {"moving_scored_wake": frac(s_at == 1, moving), "sustained_moving_scored_wake": frac(s_at == 1, moving & (run >= 30)),
            "brief_moving_scored_sleep": frac(sleep, moving & (run < 5)), "still_scored_sleep": frac(sleep, still)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--sessions", nargs="*", default=[], help="ANIMAL:SESSION, animal as SF07 (none: only rebuild the CSVs)")
    ap.add_argument("--variants", nargs="+", default=["imu", "imu_nremgate", "lfpemg"], choices=list(VARIANTS))
    ap.add_argument("--pipeline-root", default=None)
    ap.add_argument("--anchor", nargs="*", default=[], help="ANIMAL:SESSION:REC_S:EXPECTED (WAKE|NREM|REM) - report state +-60 s")
    a = ap.parse_args()
    c = resolve_cohort(a.cohort)
    ss, Cfg, pp_commit, pp_root = pipeline_module(a.pipeline_root)
    ar = analysis_root(c)
    out_root, lfp_root, imu_root = ar / "sleep", ar / "lfp", ar / "imu"
    print(f"scorer: PreprocessPipeline {pp_commit} ({pp_root}); output -> {out_root}")
    cache = {}
    for spec in a.sessions:
        animal, session = spec.split(":")
        for v in a.variants:
            info = score_one(ss, Cfg, pp_commit, c, animal, session, v, out_root, lfp_root, imu_root, cache)
            for anc in a.anchor:
                aan, ases, arec, aexp = anc.split(":")
                if (aan, ases) == (animal, session):
                    st = loadmat(Path(info["basepath"]) / f"{session}.SleepState.states.mat", simplify_cells=True)["SleepState"]["idx"]
                    ts, s = np.asarray(st["timestamps"]).reshape(-1), np.asarray(st["states"]).reshape(-1)
                    w = (ts >= float(arec) - 60) & (ts <= float(arec) + 60)
                    counts = {n: int(np.sum(s[w] == code)) for n, code in (("WAKE", 1), ("NREM", 3), ("REM", 5), ("0", 0))}
                    info[f"anchor_{arec}_{aexp}"] = counts
                    (Path(info["basepath"]) / "score_sleep.json").write_text(json.dumps(info, indent=2, default=str), encoding="utf-8")
            print(f"{animal} {session} {v:13s}: wake {info['frac_wake']:.2f} nrem {info['frac_nrem']:.2f} rem {info['frac_rem']:.2f} "
                  f"(REM {info['rem_share_of_sleep']:.0%} of sleep); moving->WAKE {info.get('moving_scored_wake')}, "
                  f"still->sleep {info.get('still_scored_sleep')}; {info['elapsed_s']} s"
                  + "".join(f"; {k}: {vv}" for k, vv in info.items() if k.startswith("anchor_")), flush=True)
    write_summary(c, out_root)


def load_states(bp: Path, session: str) -> tuple[np.ndarray, np.ndarray]:
    st = loadmat(bp / f"{session}.SleepState.states.mat", simplify_cells=True)["SleepState"]["idx"]
    return np.asarray(st["timestamps"]).reshape(-1), np.asarray(st["states"]).reshape(-1)


def write_summary(c: str, out_root: Path) -> None:
    """Rebuild both pilot CSVs from every score_sleep.json under out_root (so a partial rerun never drops rows).

    Agreement between two variants a, b of one session, over the 1-s epochs t both score (state != 0):
      agree = mean_t [s_a(t) == s_b(t)];  kappa = (agree - p_e) / (1 - p_e),  p_e = sum_k p_a(k) p_b(k)
    """
    import pandas as pd
    rows = []
    for p in sorted(out_root.glob("*/*/*/score_sleep.json")):
        info = json.loads(p.read_text(encoding="utf-8"))
        if "sustained_moving_scored_wake" not in info:     # rows written before the run-length split: add it
            ts, s = load_states(p.parent, info["session"])
            info.update(imu_consistency(out_root.parent / "imu" / info["animal"] / f"{info['session']}.imu_1s.csv", info["animal"], ts, s))
            p.write_text(json.dumps(info, indent=2, default=str), encoding="utf-8")
        rows.append(info)
    if not rows:
        return
    df = pd.DataFrame(rows).sort_values(["animal", "session", "variant"])
    df.to_csv(report_dir(c) / f"ephys_spikes_sleep_pilot_{c}.csv", index=False)
    pairs = []
    for (animal, session), g in df.groupby(["animal", "session"]):
        st = {r.variant: load_states(Path(r.basepath), session) for r in g.itertuples()}
        vs = sorted(st)
        for i, va in enumerate(vs):
            for vb in vs[i + 1:]:
                n = min(len(st[va][1]), len(st[vb][1]))
                sa, sb = st[va][1][:n], st[vb][1][:n]
                m = (sa != 0) & (sb != 0)
                agree = float(np.mean(sa[m] == sb[m]))
                pe = sum(np.mean(sa[m] == k) * np.mean(sb[m] == k) for k in (1, 3, 5))
                row = {"animal": animal, "session": session, "variant_a": va, "variant_b": vb, "epochs": int(m.sum()),
                       "agree": round(agree, 4), "kappa": round((agree - pe) / max(1e-9, 1 - pe), 4)}
                for name, code in (("wake", 1), ("nrem", 3), ("rem", 5)):   # where a says X, share b also says X
                    ka = sa[m] == code
                    row[f"{name}_a_also_b"] = round(float(np.mean(sb[m][ka] == code)), 4) if ka.any() else None
                pairs.append(row)
    pd.DataFrame(pairs).to_csv(report_dir(c) / f"ephys_spikes_sleep_pilot_agreement_{c}.csv", index=False)
    print(f"-> {report_dir(c) / f'ephys_spikes_sleep_pilot_{c}.csv'} (+ _agreement)")


if __name__ == "__main__":
    main()
