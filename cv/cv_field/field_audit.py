"""field_audit.py — lightweight whole-field (CH01-CH04) milestone audit for cv_field.

Deliberately NOT the shelter cv-measurement-auditor: that agent's engine (glass-treatment timeline,
through-glass view-quality tiers) is shelter-specific and would misapply to the glass-free whole-field
cameras. This is a small, self-contained audit that carries the whole-field regimes instead (night-IR,
weather, wall-edge/huddle occlusion, and — the big one — no cross-camera identity yet).

Two modes (chosen by whether validation metrics are handed in):
  * metadata  — from round_provenance.csv + configs: selection coverage per cluster, round-over-round
                novelty, day/night split, per-camera calibration RMSE. No error metrics invented.
  * validation — additionally records the honest session-split held-out mAP (by day/night) and the
                equal-budget random-selection control delta (the active-learning falsification check).

Persists two files (schema ``cv_field_measurement_audit/1.0``) into
``results/<cohort>/cv_field/reports/``: ``cv_field_audit_<label>.md`` and ``.json``. Reads only; changes no
detector, threshold, or label. Uses only the stdlib so it runs anywhere.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CV_DIR = HERE.parent
for _p in (str(HERE), str(CV_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_NAME_RE = re.compile(r"(CH0\d)_.*?(\d{4}-\d{2}-\d{2})_(\d{2})-\d{2}-\d{2}")


def parse_frame(name: str):
    """(channel, date, hour) from a harvested frame name, or (None, None, None)."""
    m = _NAME_RE.search(name)
    if not m:
        return None, None, None
    return m.group(1), m.group(2), int(m.group(3))


def daynight(hour):
    """Approximate day/night from the recording start hour (documented as approximate, wallclock-based)."""
    if hour is None:
        return "unknown"
    return "day" if 6 <= hour < 20 else "night"


def read_provenance(path):
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"provenance not found: {p}")
    with p.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def calib_rmse(calib_dir, channels):
    out = {}
    for ch in channels:
        f = Path(calib_dir) / f"{ch}_calib.json"
        if not f.exists():
            out[ch] = None
            continue
        try:
            out[ch] = json.loads(f.read_text(encoding="utf-8")).get("reproj_rmse_cm")
        except Exception:  # noqa: BLE001
            out[ch] = None
    return out


def summarize(rows, channels):
    by_round = defaultdict(list)
    for r in rows:
        by_round[str(r.get("round"))].append(r)
    rounds = {}
    for rnd, rws in sorted(by_round.items()):
        clusters = {r.get("cluster_id") for r in rws if r.get("cluster_id") not in (None, "", "None")}
        dn = Counter(daynight(parse_frame(r["frame"])[2]) for r in rws)
        cams = Counter(parse_frame(r["frame"])[0] for r in rws)
        rounds[rnd] = {"n_selected": len(rws), "method_mix": dict(Counter(r["method"] for r in rws)),
                       "distinct_clusters": len(clusters), "day_night": dict(dn), "by_camera": dict(cams)}
    total_dn = Counter(daynight(parse_frame(r["frame"])[2]) for r in rows)
    return {"rounds": rounds, "total_selected": len(rows), "day_night_total": dict(total_dn)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="cv_field whole-field milestone audit (metadata|validation).",
                                 allow_abbrev=False)
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--provenance", required=True, help="dataset/rat_field/round_provenance.csv")
    ap.add_argument("--channels", nargs="+", default=["CH01", "CH02", "CH03", "CH04"])
    ap.add_argument("--calib-dir", default=str(CV_DIR / "configs"))
    ap.add_argument("--val-json", default=None,
                    help="validation mode: JSON with held-out mAP, e.g. {\"map50\":..,\"by\":{\"day\":..,\"night\":..}}")
    ap.add_argument("--random-json", default=None,
                    help="equal-budget random-control metrics, e.g. {\"map50\":..} (falsification delta)")
    ap.add_argument("--label", default="latest", help="report label suffix (e.g. a date)")
    args = ap.parse_args(argv)

    import output_paths as op
    cohort = op.resolve_cohort(args.cohort)
    rows = read_provenance(args.provenance)
    summary = summarize(rows, args.channels)
    rmse = calib_rmse(args.calib_dir, args.channels)

    mode = "validation" if args.val_json else "metadata"
    val = json.loads(Path(args.val_json).read_text()) if args.val_json else None
    rand = json.loads(Path(args.random_json).read_text()) if args.random_json else None
    al_delta = None
    if val and rand and val.get("map50") is not None and rand.get("map50") is not None:
        al_delta = round(val["map50"] - rand["map50"], 4)

    caveats = [
        "scope is night-IR only (21:00–04:20); CH01/CH02 daytime color is corrupt and excluded.",
        "counts are a LOWER BOUND (visible_count): wall-edge blind band + huddle occlude animals.",
        "NO cross-camera identity (animal_id=<camera>:<track_id>) — no whole-field per-animal / "
        "cross-camera-headcount claims.",
        "day/night split is approximate (recording-start wallclock hour); expect ~all night in-scope.",
        "clusters are a labeling heuristic, not evidence of behavioral discreteness.",
    ]
    verdict = ("active-learning selection beats random control by "
               f"{al_delta:+.3f} mAP50" if al_delta is not None
               else "metadata-only: selection coverage + provenance recorded; no error metric invented")

    payload = {
        "schema_version": "cv_field_measurement_audit/1.0",
        "cohort": cohort, "direction": "cv_field", "mode": mode,
        "channels": args.channels, "verdict": verdict,
        "selection": summary, "calibration_rmse_cm": rmse,
        "validation": val, "random_control": rand, "active_learning_delta_map50": al_delta,
        "regime_caveats": caveats,
    }

    rep_dir = op.report_dir(cohort, "cv_field")
    base = rep_dir / f"cv_field_audit_{args.label}"
    base.with_suffix(".json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

    md = [f"# cv_field milestone audit — {cohort} ({mode})", "",
          f"**Verdict:** {verdict}", "",
          f"- channels: {', '.join(args.channels)}  ·  total frames selected: {summary['total_selected']}",
          f"- day/night split (all rounds): {summary['day_night_total']}",
          "", "## Per-round selection", ""]
    for rnd, s in summary["rounds"].items():
        md.append(f"- **round {rnd}** — {s['n_selected']} frames, methods {s['method_mix']}, "
                  f"distinct clusters {s['distinct_clusters']}, day/night {s['day_night']}")
    md += ["", "## Per-camera calibration RMSE (cm)", ""]
    for ch, v in rmse.items():
        md.append(f"- {ch}: {v if v is not None else 'n/a'}")
    if mode == "validation":
        md += ["", "## Validation", "",
               f"- held-out mAP: {val}",
               f"- random control: {rand}",
               f"- **active-learning delta (mAP50):** {al_delta}"]
    md += ["", "## Whole-field regime caveats", ""] + [f"- {c}" for c in caveats]
    base.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"audit ({mode}) -> {base.with_suffix('.md')}")
    print(f"           -> {base.with_suffix('.json')}")
    print(f"verdict: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
