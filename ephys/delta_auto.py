"""Delta waves (cortical DOWN states), automatic, per session - cohort 2026c (plan
implementation_plan/2026-10-08-delta-wave-detection.md; method accepted by the user 2026-10-09).

Per session:
  1. NREM = the final 1-s states (`states_1s_final/<SFxx>/<session>.states.npz`, state 3; their runs equal
     SleepState.ints.NREMstate exactly, and they carry the final selection incl. SF07 2_20260905_093310 = pass2med).
  2. Detection = the lab's detect_delta_waves.m, exact port (`delta_detect.detect`): FindDeltaWaves on the configured
     column (configs/delta_channels_2026c.yaml), NREM restrict, CleanLFP [6 10], peak - end > 3 z. No EMG gate (the
     scorer's EMG is the head IMU and NREM is already IMU-gated; SF07's LFP-EMG baseline is high).
  3. DOWN-state check instead of verify_firing's sorted units: raw multi-unit crossings over all NREM (`mua_nrem.py`,
     cached next to the events; FM65 only - FM64 sessions get no check) -> `delta_detect.verify_events`: spikes within
     +-50 ms of the peak vs -1..-0.4 s over the live sites with >= 1 Hz whose firing does not rise at the delta peaks;
     verified = ratio <= 0.5.
  4. Session context from the SWR quality table (reports/..._swr_quality_<c>.csv): use_until (valid_until, paddock end,
     SF12 contact), info (FM64, settle windows, females from 09-11 19:40), sleep_verdict / tags.

Outputs <out>/<SFxx>/<session>/:
  <session>.deltaWaves.events.mat   lab struct deltaWaves (timestamps [start stop], peaks, amplitude (z peak - z end),
                                    amplitudeUnits, values [z start peak end], detectorinfo) + verified, testable,
                                    mua_ratio, mua_p, mua_k_peak, mua_k_pre, after_use_until; ALL detected events - filter
                                    with verified == 1 (and after_use_until == 0)
  <session>.delta_events.csv        the same, one row per event
  <session>.DEL.evt                 Neuroscope: "delta start/peak/stop" for verified events, "delta? ..." for the rest
  <session>.mua_nrem.npz            the MUA intermediate (reusable)
  <session>.delta_summary.json      counts, rates per NREM minute (all / verified), verify sites, context

  python ephys/delta_auto.py --animal SF11 (--sessions S ... | --all [--min-minutes 10]) --lfp-root <.../analysis/lfp>
         --raw-root <WILD root: .../SF7/<MAC>/<session>/amplifier.dat> --states-root <.../states_1s_final>
         --out <dir> [--mua-cache <dir with <SFxx>/<session>.mua_nrem.npz>] [--mua-workers 8] [--redo]
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import scipy.io as sio
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delta_detect as dd  # noqa: E402
import mua_nrem  # noqa: E402
from swr_auto import channels_for, session_start  # noqa: E402
from swr_channel_scan import XML  # noqa: E402
from wild_ce_params import parse_ce_params  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
COHORT = "2026c"
FL = 1250.0
QUALITY = REPO / f"results/{COHORT}/ephys_spikes/reports/ephys_spikes_swr_quality_{COHORT}.csv"


def raw_dir(raw_root: Path, animal: str, session: str) -> Path | None:
    hits = list((raw_root / f"SF{int(animal[2:])}").glob(f"*/{session}"))
    return hits[0] if hits else None


def session_context(animal: str, session: str, quality: Path) -> dict:
    if not quality.exists():
        return {}
    for r in csv.DictReader(open(quality, encoding="utf-8")):
        if r["animal"] == animal and r["session"] == session:
            return {k: r.get(k, "") for k in ("use_until", "info", "sleep_verdict", "sleep_tags", "block", "tier")}
    return {}


def run_session(animal: str, session: str, a) -> dict:
    t0 = time.time()
    out = Path(a.out) / animal / session
    out.mkdir(parents=True, exist_ok=True)
    blk = channels_for(yaml.safe_load(open(a.channels, encoding="utf-8")), animal, session)
    col = int(blk["delta_col"])
    lfp_path = Path(a.lfp_root) / animal / f"{session}.lfp"
    meta = json.loads(Path(str(lfp_path) + ".json").read_text())
    nch, fs = int(meta["n_channels"]), float(meta["fs_out"])
    st_path = Path(a.states_root) / animal / f"{session}.states.npz"
    nrem = dd.nrem_from_states(st_path) if st_path.exists() else np.zeros((0, 2))
    ctx = session_context(animal, session, Path(a.quality))
    summary = dict(animal=animal, session=session, delta_col=col, block_valid_from=blk.get("valid_from"),
                   nrem_min=float(np.sum(nrem[:, 1] - nrem[:, 0]) / 60) if nrem.size else 0.0, context=ctx,
                   method="delta_detect.detect = detect_delta_waves.m port (NREM, CleanLFP [6 10], z peak-end > 3, no EMG gate)"
                          " + verify_events (raw MUA, ratio <= 0.5)", git=dd._git())
    if not nrem.size:  # no final sleep states for this session (not scored / refused) or no NREM: skipped, not an error
        summary.update(n_events=0, skipped="no final sleep states" if not st_path.exists() else "no NREM")
        (out / f"{session}.delta_summary.json").write_text(json.dumps(summary, indent=1))
        return summary
    x = dd.sd.load_channels(str(lfp_path), nch, [col + 1])[:, 0]
    D, D0, info = dd.detect(x, fs, nrem=nrem, emg=None, threshold=3.0)
    del x
    # DOWN-state check
    rd = raw_dir(Path(a.raw_root), animal, session)
    fw = parse_ce_params(rd / "CE_params.bin").firmware_version if rd and (rd / "CE_params.bin").exists() else None
    mua_file = out / f"{session}.mua_nrem.npz"
    cached = Path(a.mua_cache) / animal / f"{session}.mua_nrem.npz" if a.mua_cache else None
    vinfo = dict(sites=[], reason=None)
    if fw is None or fw < 65:
        vinfo["reason"] = f"no MUA check: firmware {fw} (FM64 raw needs de-glitching)" if fw else "no raw session"
        r = dict(k_peak=np.zeros(D.shape[0]), k_pre=np.zeros(D.shape[0]), ratio=np.full(D.shape[0], np.nan),
                 p=np.full(D.shape[0], np.nan), testable=np.zeros(D.shape[0], bool), verified=np.zeros(D.shape[0], bool))
    else:
        if not mua_file.exists():
            if cached is not None and cached.exists():
                shutil.copyfile(cached, mua_file)
            else:
                mua_nrem.extract(rd, Path(a.states_root) / animal / f"{session}.states.npz", HERE / "configs/xml" / XML[animal],
                                 mua_file, workers=a.mua_workers, nch=nch, nrem=nrem)
        spikes, m = mua_nrem.load(mua_file)
        r, vinfo = dd.verify_events(D, spikes, m["rate_hz"], [int(c) for c in m["live"]], np.load(mua_file)["bouts_s"])
        vinfo["reason"] = None
    # use_until (logger clock) -> session seconds
    after = np.zeros(D.shape[0], bool)
    if ctx.get("use_until"):
        lim = (datetime.strptime(ctx["use_until"][:19], "%Y-%m-%d %H:%M:%S") - session_start(session)).total_seconds()
        after = D[:, 1] > lim
    ver = r["verified"].astype(bool)
    amp = D[:, 4] - D[:, 5]
    dw = dict(timestamps=D[:, [0, 2]], peaks=D[:, 1], amplitude=amp, amplitudeUnits="zscore", values=D[:, 3:6],
              eventID=np.zeros((0, 1)), eventIDlabels=np.zeros((0, 1)), eventIDbinary=False,
              center=D[:, [0, 2]].mean(axis=1), duration=D[:, 2] - D[:, 0],
              verified=ver.astype(np.uint8), testable=r["testable"].astype(np.uint8), mua_ratio=r["ratio"],
              mua_p=r["p"], mua_k_peak=np.asarray(r["k_peak"], float), mua_k_pre=np.asarray(r["k_pre"], float),
              after_use_until=after.astype(np.uint8),
              detectorinfo=dict(detectorname="delta_detect.py (exact port of detect_delta_waves.m / FindDeltaWaves.m) + "
                                             "delta_auto.py MUA check", detectiondate=datetime.now().strftime("%Y-%m-%d"),
                                detectionintervals=nrem, detectionchannel=col, detectionchannel1=col + 1, threshold=3.0,
                                detectionparms=dict(NREM_restrict=1, EMG_threshold=np.inf, clean_thresholds=[6, 10],
                                                    verify="raw MUA, ratio <= 0.5", verify_sites=np.array(vinfo.get("sites", []), float),
                                                    use_until=ctx.get("use_until", ""), git=summary["git"] or "")))
    sio.savemat(out / f"{session}.deltaWaves.events.mat", {"deltaWaves": dw}, do_compression=True)
    hdr = "t_start,t_peak,t_end,z_start,z_peak,z_end,amp_z,dur_ms,verified,testable,mua_ratio,mua_p,mua_k_peak,mua_k_pre,after_use_until"
    rows = [f"{d[0]:.4f},{d[1]:.4f},{d[2]:.4f},{d[3]:.3f},{d[4]:.3f},{d[5]:.3f},{am:.3f},{(d[2] - d[0]) * 1000:.0f},"
            f"{int(v)},{int(t)},{ra:.4f},{pv:.3g},{int(kp)},{int(kb)},{int(af)}"
            for d, am, v, t, ra, pv, kp, kb, af in zip(D, amp, ver, r["testable"], r["ratio"], r["p"], r["k_peak"], r["k_pre"], after)]
    (out / f"{session}.delta_events.csv").write_text(hdr + "\n" + "\n".join(rows) + ("\n" if rows else ""))
    with open(out / f"{session}.DEL.evt", "w") as fh:
        for d, v in zip(D, ver):
            tag = "delta" if v else "delta?"
            for t, lab in zip(d[:3], ("start", "peak", "stop")):
                fh.write(f"{t * 1000:.1f}\t{tag} {lab}\n")
    nmin = summary["nrem_min"]
    keep = ~after
    summary.update(n_events=int(D.shape[0]), n_candidates=int(D0.shape[0]), n_testable=int(r["testable"].sum()),
                   n_verified=int(ver.sum()), n_after_use_until=int(after.sum()), firmware=fw,
                   rate_per_nrem_min=round(D.shape[0] / max(nmin, 1e-9), 2),
                   verified_rate_per_nrem_min=round(int(np.sum(ver & keep)) / max(nmin, 1e-9), 2),
                   frac_verified_of_testable=round(float(ver.sum() / max(r["testable"].sum(), 1)), 3),
                   median_dur_ms=round(float(np.median(D[:, 2] - D[:, 0]) * 1000), 1) if D.size else None,
                   verify=dict(sites=vinfo.get("sites", []), reason=vinfo.get("reason"),
                               site_ratio=vinfo.get("site_ratio"), site_rate_hz=vinfo.get("site_rate_hz"),
                               frac_verified=vinfo.get("frac_verified")),
                   detect_info=info, seconds=round(time.time() - t0, 1))
    (out / f"{session}.delta_summary.json").write_text(json.dumps(summary, indent=1, default=float))
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--animal", required=True)
    ap.add_argument("--sessions", nargs="*")
    ap.add_argument("--all", action="store_true", help="every session of the animal with an LFP of >= --min-minutes")
    ap.add_argument("--min-minutes", type=float, default=10.0)
    ap.add_argument("--lfp-root", required=True)
    ap.add_argument("--raw-root", required=True)
    ap.add_argument("--states-root", required=True)
    ap.add_argument("--channels", default=str(HERE / f"configs/delta_channels_{COHORT}.yaml"))
    ap.add_argument("--quality", default=str(QUALITY))
    ap.add_argument("--mua-cache", default=None)
    ap.add_argument("--mua-workers", type=int, default=8)
    ap.add_argument("--out", required=True)
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    sessions = list(a.sessions or [])
    if a.all:
        sessions = []
        for f in sorted((Path(a.lfp_root) / a.animal).glob("*.lfp")):
            dur = json.loads(Path(str(f) + ".json").read_text()).get("duration_s", 0)
            (sessions.append(f.name[:-4]) if dur >= 60 * a.min_minutes
             else print(f"skip {f.name[:-4]}: {dur / 60:.1f} min < {a.min_minutes}", flush=True))
    todo = [s for s in sessions if a.redo or not (Path(a.out) / a.animal / s / f"{s}.delta_summary.json").exists()]
    print(f"{a.animal}: {len(todo)} of {len(sessions)} sessions to run", flush=True)
    n_err = 0
    for s in todo:
        try:
            r = run_session(a.animal, s, a)
            print(f"ok   {s}: {r.get('n_events', 0)} events, verified {r.get('n_verified', 0)} "
                  f"({100 * r.get('frac_verified_of_testable', 0):.0f} % of testable), "
                  f"{r.get('verified_rate_per_nrem_min', 0)}/NREM min, {r.get('verify', {}).get('reason') or ''} ({r.get('seconds', 0)} s)",
                  flush=True)
        except Exception:
            n_err += 1
            err = traceback.format_exc()
            ed = Path(a.out) / "_errors"
            ed.mkdir(parents=True, exist_ok=True)
            (ed / f"{a.animal}_{s}.json").write_text(json.dumps(dict(animal=a.animal, session=s, error=err), indent=1))
            print(f"FAIL {s}: {err.splitlines()[-1]}", flush=True)
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
