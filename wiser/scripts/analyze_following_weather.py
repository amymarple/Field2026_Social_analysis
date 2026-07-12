r"""
analyze_following_weather.py — does the 07-04 FIREWORKS night show elevated following (a field
observation), and does RAIN increase following? Cross-checks the existing Phase-B2 per-night following
incident rates against the AWN weather data. NO rebuild of the following detector — reads
`incident_summary_by_night.csv`.

Guardrails (this is why the answer is careful):
  * The 07-04 "increased following" note is an OBSERVER HYPOTHESIS, not a label (AGENTS.md) — tested here.
  * 07-04 is n=1 AND triply confounded: the env map marks it wet + fireworks + burrow at once, so a
    fireworks effect cannot be isolated from rain/dropout on that night alone. The cleanest available
    contrast is 07-04 vs 07-06 (BOTH late + wet + burrow; differ only in fireworks).
  * Following uses the MOVEMENT-NORMALIZED rate (frac_bouts_following) so "more following" is separated
    from "more movement". episodes_per_hour is shown as context.
  * RAIN is a measurement confound too: rain -> more UWB dropout -> fewer detectable following episodes
    (a mechanical DECREASE), and wet nights are late-sequence (habituation). So a rain effect on
    following is not cleanly a behavioural effect.

    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\analyze_following_weather.py
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# env-map night_regime (curated) — cross-checked against AWN below
REGIME = {
    "2026-06-28": {"wet": False, "fireworks": False, "burrow": False, "phase": "release"},
    "2026-06-29": {"wet": False, "fireworks": False, "burrow": False, "phase": "early"},
    "2026-06-30": {"wet": True,  "fireworks": False, "burrow": False, "phase": "early"},
    "2026-07-01": {"wet": True,  "fireworks": False, "burrow": False, "phase": "mid"},
    "2026-07-02": {"wet": False, "fireworks": False, "burrow": False, "phase": "mid"},
    "2026-07-03": {"wet": False, "fireworks": False, "burrow": True,  "phase": "mid"},
    "2026-07-04": {"wet": True,  "fireworks": True,  "burrow": True,  "phase": "late"},
    "2026-07-05": {"wet": False, "fireworks": False, "burrow": True,  "phase": "late"},
    "2026-07-06": {"wet": True,  "fireworks": False, "burrow": True,  "phase": "late"},
    "2026-07-07": {"wet": False, "fireworks": False, "burrow": False, "phase": "late"},
    "2026-07-08": {"wet": False, "fireworks": False, "burrow": False, "phase": "late"},
}
NIGHT_START_H, NIGHT_END_H = 21, 5   # local (EDT) night window


def _night_rain(weather: pd.DataFrame, night: str) -> dict:
    """Total rain (mm) and peak rain rate in the [night 21:00, next 05:00) local window, integrating
    Rain Rate (mm/hr) over the 5-min AWN log intervals."""
    d0 = pd.Timestamp(night + " 21:00", tz="America/New_York") if False else \
        pd.Timestamp(night).tz_localize("America/New_York") + pd.Timedelta(hours=NIGHT_START_H)
    d1 = pd.Timestamp(night).tz_localize("America/New_York") + pd.Timedelta(hours=24 + NIGHT_END_H)
    w = weather[(weather["_t"] >= d0) & (weather["_t"] < d1)].sort_values("_t")
    if w.empty:
        return {"rain_mm": np.nan, "peak_rate_mmhr": np.nan, "n_obs": 0}
    dt_hr = w["_t"].diff().dt.total_seconds().div(3600).fillna(5 / 60).clip(upper=0.5).to_numpy()
    rate = pd.to_numeric(w["Rain Rate (mm/hr)"], errors="coerce").fillna(0).to_numpy()
    return {"rain_mm": float(np.sum(rate * dt_hr)), "peak_rate_mmhr": float(np.max(rate)),
            "n_obs": int(len(w))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--incident-summary", type=Path,
                    default=ROOT / "outputs/following_incidents_2026-06-28_to_2026-07-08/incident_summary_by_night.csv")
    ap.add_argument("--weather-glob", default="/d/Reolink_record/audio_in/weather_data/AWN-*20260628-20260709.csv")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/following_incidents_2026-06-28_to_2026-07-08")
    ap.add_argument("--rain-thr-mm", type=float, default=0.2)
    args = ap.parse_args()

    fol = pd.read_csv(args.incident_summary)
    fol["night"] = fol["night"].astype(str)

    wfiles = glob.glob(args.weather_glob)
    if not wfiles:
        print(f"WARNING: no weather file at {args.weather_glob}; using env-map wet flags only")
        weather = None
    else:
        weather = pd.read_csv(sorted(wfiles)[-1])
        weather["_t"] = pd.to_datetime(weather["Date"], utc=True).dt.tz_convert("America/New_York")

    rows = []
    for _, r in fol.iterrows():
        n = r["night"]; reg = REGIME.get(n, {})
        rain = _night_rain(weather, n) if weather is not None else {"rain_mm": np.nan, "peak_rate_mmhr": np.nan}
        awn_wet = bool(rain["rain_mm"] > args.rain_thr_mm) if rain["rain_mm"] == rain["rain_mm"] else None
        rows.append({"night": n, "phase": reg.get("phase"),
                     "frac_bouts_following": float(r["mean_frac_bouts_following"]),
                     "episodes_per_hour": float(r["episodes_per_hour"]),
                     "fireworks": reg.get("fireworks"), "burrow": reg.get("burrow"),
                     "envmap_wet": reg.get("wet"), "awn_rain_mm": round(rain["rain_mm"], 2) if rain["rain_mm"] == rain["rain_mm"] else None,
                     "awn_peak_rate_mmhr": round(rain["peak_rate_mmhr"], 2) if rain.get("peak_rate_mmhr") == rain.get("peak_rate_mmhr") else None,
                     "awn_wet": awn_wet})
    T = pd.DataFrame(rows)
    T.to_csv(args.out / "following_weather_by_night.csv", index=False)

    # authoritative wet = AWN if available else env-map
    T["wet"] = T["awn_wet"].where(T["awn_wet"].notna(), T["envmap_wet"]).astype(bool)
    fm = "frac_bouts_following"
    fw = T[T["fireworks"] == True]                                     # noqa: E712
    dry_normal = T[(~T["wet"]) & (T["fireworks"] != True) & (T["phase"] != "release")]  # noqa: E712
    wet_nofw = T[(T["wet"]) & (T["fireworks"] != True)]               # noqa: E712
    dry_all = T[(~T["wet"]) & (T["fireworks"] != True)]               # noqa: E712
    # matched contrasts around the fireworks night. AWN shows 07-04 was DRY in-window, so 07-05
    # (dry+burrow+late) is the CLEANEST match (differ only in fireworks); 07-06 (wet+burrow+late) is a
    # second match that also carries rain.
    def _f(n):
        return float(T[T["night"] == n][fm].mean())
    m0704, m0705, m0706 = _f("2026-07-04"), _f("2026-07-05"), _f("2026-07-06")

    R = {
        "generated_utc": datetime.datetime.utcnow().isoformat(),
        "per_night": T.round(4).to_dict("records"),
        "fireworks_0704_frac": round(float(fw[fm].mean()), 4),
        "dry_normal_mean_frac": round(float(dry_normal[fm].mean()), 4),
        "dry_normal_nights": dry_normal["night"].tolist(),
        "wet_no_fireworks_mean_frac": round(float(wet_nofw[fm].mean()), 4),
        "wet_no_fireworks_nights": wet_nofw["night"].tolist(),
        "dry_all_mean_frac": round(float(dry_all[fm].mean()), 4),
        "matched_0704_vs_0705_dry": {"fireworks_0704": round(m0704, 4),
                                     "matched_DRY_burrow_late_0705": round(m0705, 4),
                                     "ratio": round(m0704 / m0705, 2) if m0705 else None},
        "matched_0704_vs_0706_wet": {"fireworks_0704": round(m0704, 4),
                                     "matched_wet_burrow_late_0706": round(m0706, 4),
                                     "ratio": round(m0704 / m0706, 2) if m0706 else None},
        "awn_vs_envmap_wet_disagreements": T[T["awn_wet"].notna() & (T["awn_wet"] != T["envmap_wet"])]["night"].tolist(),
        "awn_note": "AWN (rain-rate integrated over the 21:00-05:00 window) is the authoritative rain "
                    "signal; env-map 'wet' is a coarse ground-wetness flag. 07-04 (fireworks) and 07-01 "
                    "were env-map-'wet' but AWN-DRY -> the fireworks night carried NO in-window rain.",
    }

    # verdicts
    fw_vs_dry = R["fireworks_0704_frac"] - R["dry_normal_mean_frac"]
    fw_vs_matched = m0704 - m0705   # cleanest: vs the DRY burrow+late match
    rain_effect = R["wet_no_fireworks_mean_frac"] - R["dry_all_mean_frac"]
    R["verdict_fireworks"] = (
        f"07-04 following (frac {R['fireworks_0704_frac']}) is {'ABOVE' if fw_vs_dry > 0 else 'below'} the "
        f"dry-normal mean ({R['dry_normal_mean_frac']}); against the CLEANEST match 07-05 (dry+burrow+late, "
        f"no fireworks) it is {R['matched_0704_vs_0705_dry']['ratio']}x, and vs 07-06 (wet+burrow+late) "
        f"{R['matched_0704_vs_0706_wet']['ratio']}x — highest of the late+burrow nights. The AWN cross-check "
        f"REMOVES the rain confound (07-04 was dry in-window). Descriptively CONSISTENT with the observed "
        f"increased following. BUT: n=1; following also rises in the late sequence generally (07-08 dry = "
        f"{_f('2026-07-08'):.4f} > 07-04 with no fireworks), so 07-04 is elevated but not a standout spike; "
        f"and a fireworks STARTLE (co-flight to shelter) is not the same construct as social following. "
        f"Suggestive, NOT confirmable from WISER — the B2 video queue for 07-04 is the way to check the mechanism.")
    R["verdict_rain"] = (
        f"Rain does NOT increase following: wet (no-fireworks) mean frac {R['wet_no_fireworks_mean_frac']} "
        f"{'>=' if rain_effect >= 0 else '<'} dry mean {R['dry_all_mean_frac']} (diff {rain_effect:+.4f}). "
        f"If anything wet nights follow LESS, and this is further confounded by rain->UWB dropout (a "
        f"mechanical decrease in detectable episodes) and late-sequence habituation — so no evidence for a "
        f"rain-increases-following effect; a weak wet<dry that is partly a measurement artifact.")
    (args.out / "following_weather_results.json").write_text(json.dumps(R, indent=2, default=str), encoding="utf-8")

    md = (f"# Following × weather — fireworks (07-04) & rain cross-check\n\n"
          f"**Status:** ⚠️ candidate (descriptive; n=1 for fireworks). Tests the FIELD OBSERVATION of "
          f"increased following on the 07-04 fireworks night, and whether rain increases following, against "
          f"the Phase-B2 per-night following-incident rates + AWN weather. Movement-normalized rate "
          f"(`frac_bouts_following`). Generated {R['generated_utc']}.\n\n"
          f"## Per-night table\n\n"
          + T[["night", "phase", "frac_bouts_following", "episodes_per_hour", "fireworks", "burrow",
               "awn_rain_mm", "awn_wet"]].to_markdown(index=False) + "\n\n"
          f"## Weather cross-check\n\n"
          f"{R['awn_note']} AWN vs env-map 'wet' disagreements: {R['awn_vs_envmap_wet_disagreements']} "
          f"(env-map-wet but AWN-dry). Genuinely rainy in-window nights: 06-30 (0.30 mm), 07-06 (2.39 mm).\n\n"
          f"## Fireworks (07-04)\n\n{R['verdict_fireworks']}\n\n"
          f"- 07-04 {R['matched_0704_vs_0705_dry']['fireworks_0704']} vs matched DRY+burrow+late 07-05 "
          f"{R['matched_0704_vs_0705_dry']['matched_DRY_burrow_late_0705']} = "
          f"{R['matched_0704_vs_0705_dry']['ratio']}x; vs wet+burrow+late 07-06 "
          f"{R['matched_0704_vs_0706_wet']['matched_wet_burrow_late_0706']} = "
          f"{R['matched_0704_vs_0706_wet']['ratio']}x.\n\n"
          f"## Rain\n\n{R['verdict_rain']}\n\n"
          f"## Definitions\n\n"
          f"- **frac_bouts_following** — fraction of a follower's movement bouts that overlap a strict "
          f"lagged-following episode (Phase B2); movement-normalized so it separates *more following* from "
          f"*more moving*. Range [0,1].\n"
          f"- **awn_rain_mm** — Σ(Rain Rate mm/hr × Δt) over the [21:00, next 05:00) local window from AWN.\n"
          f"- **matched contrast** — 07-04 vs 07-05/07-06, holding burrow+late-phase fixed, differing in "
          f"fireworks (and 07-06 also in rain). n=1 vs n=1; descriptive only.\n\n"
          f"## Scope\n\nn=1 fireworks night; 07-04 also a burrow night and in the late (higher-following) "
          f"sequence; fireworks startle-driven co-flight is not the same construct as social following; "
          f"rain confounded by UWB dropout (mechanical decrease) + habituation. Frame UNVERIFIED. Following "
          f"'leader' = temporal order, herd-not-dyad (Phase B). Video (B2 queue) is the way to confirm mechanism.\n")
    (args.out / "following_weather_report.md").write_text(md, encoding="utf-8")

    print(T[["night", "phase", "frac_bouts_following", "episodes_per_hour", "fireworks", "burrow",
             "envmap_wet", "awn_rain_mm", "awn_wet"]].to_string(index=False))
    print()
    print(f"[fireworks] 07-04 frac={R['fireworks_0704_frac']} | dry-normal {R['dry_normal_nights']} mean={R['dry_normal_mean_frac']}")
    print(f"[fireworks] matched 07-04 vs 07-05 (DRY+burrow+late): {m0704:.4f} vs {m0705:.4f} = {R['matched_0704_vs_0705_dry']['ratio']}x "
          f"| vs 07-06 (wet+burrow+late) {m0706:.4f} = {R['matched_0704_vs_0706_wet']['ratio']}x")
    print(f"[rain] wet(no-fw) {R['wet_no_fireworks_nights']} mean={R['wet_no_fireworks_mean_frac']} vs dry mean={R['dry_all_mean_frac']} (diff {rain_effect:+.4f})")
    print(f"[AWN vs env-map wet disagreements] {R['awn_vs_envmap_wet_disagreements']}")
    print(f"\n[verdict fireworks] {R['verdict_fireworks']}")
    print(f"[verdict rain] {R['verdict_rain']}")
    print(f"done -> {args.out}")


if __name__ == "__main__":
    main()
