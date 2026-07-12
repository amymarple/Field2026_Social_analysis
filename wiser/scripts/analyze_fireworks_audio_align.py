r"""
analyze_fireworks_audio_align.py — cross-modal test: do the 07-04 FOLLOWING bursts (21:30, 22:20) line
up with the acoustic FIREWORKS volleys? Aligns the extracted CH01 audio level (peak / L10 / low-band
dBFS-relative) against the Phase-B2 following-episode counts on a common 5-min grid over 20:00-24:00 EDT,
and cross-correlates to (a) test coincidence and (b) surface any camera↔WISER clock offset (the best-lag
peak absorbs a constant offset).

HARD caveats: audio timestamp = Reolink camera/NVR filename WALLCLOCK; following t_start_local =
WISER-derived local. Their sync is UNVERIFIED, so the cross-correlation LAG mixes clock offset with any
real response delay — a clear correlation peak at a small lag is coincidence evidence, its exact lag is
not. Level is RELATIVE dBFS (not SPL) and CH01-location-specific. This tests TIMING coincidence, not the
following-vs-startle-co-flight construct (that needs video).

    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\analyze_fireworks_audio_align.py
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
FW_NIGHT = "2026-07-04"
GRID_MIN = 5
WIN = ("2026-07-04 20:00:00", "2026-07-04 23:59:59")


def _grid_index(t0, t1, step_min):
    return pd.date_range(pd.Timestamp(t0).floor(f"{step_min}min"), pd.Timestamp(t1), freq=f"{step_min}min")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-csv", type=Path,
                    default=ROOT.parent / "audio/outputs/audio_features_CH01_2026-07-04.csv")
    ap.add_argument("--episodes", type=Path,
                    default=ROOT / "outputs/following_incidents_2026-06-28_to_2026-07-08/strict_following_episodes.csv")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/following_incidents_2026-06-28_to_2026-07-08")
    ap.add_argument("--level-col", default="peak_dbfs_relative")
    ap.add_argument("--grid-min", type=int, default=GRID_MIN)
    args = ap.parse_args()

    if not args.audio_csv.exists():
        print(f"ERROR: audio CSV not found: {args.audio_csv} (run extract_audio_features for 07-04 CH01)")
        sys.exit(2)
    A = pd.read_csv(args.audio_csv)
    A["_t"] = pd.to_datetime(A["window_start_timestamp"])
    A = A[(A["_t"] >= WIN[0]) & (A["_t"] <= WIN[1])].copy()
    # keep valid audio only for the level series (silent/qc-bad -> NaN)
    if "valid_audio" in A.columns:
        A.loc[~A["valid_audio"].astype(bool), args.level_col] = np.nan

    ep = pd.read_csv(args.episodes)
    ep = ep[ep["night"].astype(str) == FW_NIGHT].copy()
    ep["_t"] = pd.to_datetime(ep["t_start_local"])
    ep = ep[(ep["_t"] >= WIN[0]) & (ep["_t"] <= WIN[1])]

    grid = _grid_index(WIN[0], WIN[1], args.grid_min)
    A["_bin"] = A["_t"].dt.floor(f"{args.grid_min}min")
    ep["_bin"] = ep["_t"].dt.floor(f"{args.grid_min}min")
    # audio per bin: MAX peak (fireworks transients) + mean leq + max low-band; following: count
    audio_peak = A.groupby("_bin")[args.level_col].max().reindex(grid)
    audio_low = A.groupby("_bin")["band_0_1k_db"].max().reindex(grid) if "band_0_1k_db" in A.columns else None
    audio_leq = A.groupby("_bin")["leq_dbfs_relative"].mean().reindex(grid) if "leq_dbfs_relative" in A.columns else None
    fol = ep.groupby("_bin").size().reindex(grid).fillna(0)

    D = pd.DataFrame({"bin": grid, "following_episodes": fol.to_numpy(),
                      "audio_peak_db": audio_peak.to_numpy()})
    if audio_low is not None:
        D["audio_low0_1k_db"] = audio_low.to_numpy()
    if audio_leq is not None:
        D["audio_leq_db"] = audio_leq.to_numpy()
    D.to_csv(args.out / "fireworks_audio_following_5min.csv", index=False)

    # cross-correlation (standardized) at lags +/- 30 min, following vs audio_peak
    def _xcorr(a, b, max_lag):
        a = pd.Series(a).astype(float); b = pd.Series(b).astype(float)
        out = []
        for L in range(-max_lag, max_lag + 1):
            bb = b.shift(L)
            m = a.notna() & bb.notna()
            if m.sum() >= 8 and a[m].std() > 0 and bb[m].std() > 0:
                out.append((L, float(np.corrcoef(a[m], bb[m])[0, 1])))
        return out
    xc = _xcorr(D["following_episodes"], D["audio_peak_db"], max_lag=6)  # +/-30 min
    best = max(xc, key=lambda t: t[1]) if xc else (None, None)
    lag0 = dict(xc).get(0)

    # coincidence at the two following bursts (nearest bin) + audio percentile within window
    valid_audio = D["audio_peak_db"].dropna()
    def _pctile(v):
        return round(float((valid_audio < v).mean()), 2) if v == v and len(valid_audio) else None
    bursts = {}
    for label, clock in [("burst_2130", "2026-07-04 21:30:00"), ("burst_2220", "2026-07-04 22:20:00")]:
        b = pd.Timestamp(clock).floor(f"{args.grid_min}min")
        row = D[D["bin"] == b]
        if not row.empty:
            ap_db = float(row["audio_peak_db"].iloc[0])
            bursts[label] = {"clock": clock, "following_episodes": int(row["following_episodes"].iloc[0]),
                             "audio_peak_db": round(ap_db, 1) if ap_db == ap_db else None,
                             "audio_peak_pctile_in_window": _pctile(ap_db)}

    R = {"generated_utc": datetime.datetime.utcnow().isoformat(), "level_col": args.level_col,
         "grid_min": args.grid_min, "window": WIN,
         "xcorr_following_vs_audiopeak": {"lag0_r": round(lag0, 3) if lag0 is not None else None,
                                          "best_lag_bins": best[0], "best_lag_min": best[0] * args.grid_min if best[0] is not None else None,
                                          "best_r": round(best[1], 3) if best[1] is not None else None,
                                          "all_lags": [(L, round(r, 3)) for L, r in xc]},
         "bursts": bursts,
         "audio_peak_top3_bins": [str(b) for b in D.set_index("bin")["audio_peak_db"].nlargest(3).index],
         "following_top3_bins": [str(b) for b in D.set_index("bin")["following_episodes"].nlargest(3).index]}
    R["verdict"] = _verdict(R, D)
    (args.out / "fireworks_audio_align_results.json").write_text(json.dumps(R, indent=2, default=str), encoding="utf-8")

    print(f"audio level column: {args.level_col} | grid {args.grid_min} min | window {WIN[0][11:]}-24:00")
    print(D.assign(bin=D["bin"].dt.strftime("%H:%M")).to_string(index=False))
    print()
    x = R["xcorr_following_vs_audiopeak"]
    print(f"[xcorr following vs audio-peak] lag0 r={x['lag0_r']} | best r={x['best_r']} at lag {x['best_lag_min']} min")
    for k, v in bursts.items():
        print(f"[{k}] {v['clock']}: {v['following_episodes']} episodes | audio peak {v['audio_peak_db']} dB "
              f"= {v['audio_peak_pctile_in_window']} pctile in window")
    print(f"[audio loudest bins] {R['audio_peak_top3_bins']}")
    print(f"[following top bins]  {R['following_top3_bins']}")
    print(f"\n[verdict] {R['verdict']}")
    _write_report(args.out, R, D)
    print(f"done -> {args.out}")


def _verdict(R, D):
    x = R["xcorr_following_vs_audiopeak"]; b = R["bursts"]
    coincide = sum(1 for v in b.values() if (v.get("audio_peak_pctile_in_window") or 0) >= 0.7)
    r0 = x["lag0_r"] or 0; rb = x["best_r"] or 0
    head = (f"Cross-modal alignment over 20:00-24:00: following-count vs CH01 audio-peak correlate "
            f"r={x['lag0_r']} at lag 0 (best r={x['best_r']} at {x['best_lag_min']} min lag). ")
    if rb >= 0.4 and coincide >= 1:
        body = (f"The following bursts fall on LOUD audio bins ({coincide}/2 bursts in the top-30% loudest "
                f"minutes), so the following bursts DO coincide with acoustic fireworks activity — "
                f"time-locked, cross-modally consistent with a fireworks trigger.")
    elif rb >= 0.3:
        body = ("There is a positive but modest audio↔following correlation; partial coincidence — "
                "suggestive, not decisive.")
    else:
        body = ("No clear audio↔following coincidence at this resolution — the following bursts are NOT "
                "obviously time-locked to the loudest audio minutes (or the clock offset is larger than "
                "the +/-30 min searched).")
    tail = (" CAVEAT: camera↔WISER clock sync is UNVERIFIED, so a nonzero best-lag mixes clock offset with "
            "response delay; level is relative dBFS (CH01 location); and coincidence in TIMING still does "
            "not distinguish social following from startle co-flight (video needed).")
    return head + body + tail


def _write_report(out, R, D):
    x = R["xcorr_following_vs_audiopeak"]
    tbl = D.assign(clock=D["bin"].dt.strftime("%H:%M")).drop(columns=["bin"])
    tbl = tbl[["clock"] + [c for c in tbl.columns if c != "clock"]]
    md = (f"# Fireworks 07-04 — audio ↔ following cross-modal alignment\n\n"
          f"**Status:** ⚠️ candidate. Tests whether the 07-04 following bursts (21:30, 22:20) coincide "
          f"with acoustic fireworks volleys, aligning CH01 audio level ({R['level_col']}) with Phase-B2 "
          f"following-episode counts on a {R['grid_min']}-min grid. Generated {R['generated_utc']}.\n\n"
          f"## Cross-correlation\n\nfollowing-count vs audio-peak: **r={x['lag0_r']} at lag 0**, best "
          f"**r={x['best_r']} at {x['best_lag_min']} min** lag.\n\n"
          f"## Per-5-min overlay (20:00-24:00 EDT)\n\n" + tbl.to_markdown(index=False) + "\n\n"
          f"## Bursts\n\n" + "\n".join(
              f"- **{v['clock']}**: {v['following_episodes']} following episodes; audio peak "
              f"{v['audio_peak_db']} dB = {v['audio_peak_pctile_in_window']} percentile of the window."
              for v in R["bursts"].values()) + "\n\n"
          f"## Verdict\n\n{R['verdict']}\n\n"
          f"## Definitions\n\n"
          f"- **audio_peak_db** — max `{R['level_col']}` (relative dBFS, NOT SPL) over the 1-min audio "
          f"windows in each {R['grid_min']}-min bin; fireworks volleys are loud transients → captured by "
          f"the max. `audio_low0_1k_db` = low-band (0-1 kHz booms).\n"
          f"- **following_episodes** — Phase-B2 strict lagged-following episodes starting in the bin.\n"
          f"- **cross-correlation lag** — Pearson r of following vs audio-peak shifted by ±k bins; the "
          f"best lag absorbs the UNVERIFIED camera↔WISER clock offset + any real response delay.\n\n"
          f"## Scope\n\nCamera↔WISER clock sync UNVERIFIED (best-lag mixes offset + delay); relative "
          f"dBFS (CH01 location, not SPL); TIMING coincidence only — does NOT distinguish social following "
          f"from startle co-flight (video, B2 queue). One fireworks night. 07-04 also a burrow night.\n")
    (out / "fireworks_audio_align_report.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
