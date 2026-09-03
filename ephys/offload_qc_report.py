"""Offload QC report for a cohort's WILD sessions: timeline continuity, timestamps, firmware, signal quality.

Combines three sources into one human-readable report (cohort-keyed, regenerable):

  1. the session index (results/<cohort>/ephys_spikes/reports/ephys_spikes_session_index_<cohort>.{csv,json},
     from ephys/build_session_index.py): firmware, RTC-vs-folder agreement, sidecar sizes, the measured
     multi-window glitch probe (ticks/s, tick_removal_frac, regime), spike-band noise, bad-channel candidates;
  2. per-animal timeline continuity computed here from start/end times:
         gap_min = (start of next session − end of this session) / 60
     negative gap (< −1 s) = OVERLAP (a real clock/commit problem); 0–10 min = normal stop→restart;
     larger = battery rounds / handling / lost intervals (listed);
  3. the BLE field-PC-time anchor fits (Neurologger `WILD_generate_pc_time.py`, run per session by
     ephys/README.md instructions into <OUT_ROOT>/<cohort>/ephys_pc_time/<SFxx>/<session>/pc_time_summary.txt).
     "PC time" here is the FIELD RECORDING PC's clock (the BLE master, wild_console host): while a logger is
     connected, the console embeds field-PC ms-of-day words into the logger's own analogin.dat (raw-misc lanes
     14/15), so the anchors travel on the SD card and the fit is computable on the analysis PC without any
     clock from this machine. The field PC's own clock QC (free-running, NTP disabled, +2.1 s/day) lives in
     field2026-sync from-field/2026-08-30_cohort3-pc-drift-log.csv and the field PC's E:\recording_qc\pc_drift.png.
         updates_kept   anchors used / found (need >= 10 and anchors near BOTH ends for a publishable fit)
         drift_ppm      fitted logger-vs-field-PC clock rate difference (1 ppm = 86.4 ms/day); |drift| > 200 ppm
                        on a short record means the fit is unconstrained; on a multi-hour record it means the
                        anchors are inconsistent (a field-PC clock step, or a Resync during the recording)
         residual_rms_ms  scatter of anchors around the line; ~10–100 ms class is the expected BLE precision
     A missing fit (no anchors) means the logger was never BLE-connected during the session.

FM64 vs FM65 evaluation: sessions are grouped by firmware and the measured probe statistics are compared
(ticks/s summed over 64 ch, tick_removal_frac, noise); the firmware claim "FM65 has no artificial spikes" is
supported only if every FM65 session's worst-window ticks/s is < 1 (the index's 'clean' threshold).

Usage:
  python ephys/offload_qc_report.py --cohort 2026c [--animals SF07 ...] [--pc-time-root <dir>]
Writes results/<cohort>/ephys_spikes/reports/ephys_spikes_offload_qc_<cohort>.md (+ .csv of the timeline).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from _common import PROJECT_ROOT, ephys_block, git_commit, out_root, report_dir, resolve_cohort, utc_now_iso

FMT = "%Y-%m-%d %H:%M:%S"


def _norm_animal(animal: str) -> str:
    a = animal.upper()
    return f"SF{int(a[2:]):02d}" if a.startswith("SF") and a[2:].isdigit() else a


def load_index(cohort: str) -> tuple[list[dict], dict]:
    rd = report_dir(cohort)
    stem = rd / f"ephys_spikes_session_index_{cohort}"
    rows = list(csv.DictReader(open(f"{stem}.csv", encoding="utf-8")))
    detail = json.loads(Path(f"{stem}.json").read_text(encoding="utf-8")) if Path(f"{stem}.json").exists() else {}
    return rows, detail


def parse_pc_time_summary(path: Path) -> dict:
    d: dict = {"present": path.exists()}
    if not path.exists():
        return d
    txt = path.read_text(encoding="utf-8", errors="replace")
    for line in txt.splitlines():
        m = re.match(r"^([a-z_]+)=(.*)$", line.strip())
        if m:
            d[m.group(1)] = m.group(2)
        elif line.lower().startswith(("error", "warning")):
            d.setdefault("messages", []).append(line.strip())
    if "updates_kept" in d:
        mk = re.match(r"(\d+)/(\d+)", d["updates_kept"])
        if mk:
            d["anchors_kept"], d["anchors_found"] = int(mk.group(1)), int(mk.group(2))
    for k in ("drift_ppm", "drift_sem_ppm", "residual_rms_ms", "offset_ms", "offset_sem_ms"):
        try:
            d[k] = float(d[k])
        except (KeyError, ValueError):
            pass
    d["ok"] = "generated" in txt and "error" not in txt.lower()
    d["incomplete"] = (not d["ok"]) and not d.get("messages")
    return d


ANCHOR_CADENCE_S = 5.0          # live anchors arrive ~every 5 s while BLE-connected (field notes)
CORRUPT_ANCHOR_FACTOR = 10.0    # more 'anchors' than 10x what the cadence allows => the misc lanes carry noise


def pc_time_verdict(p: dict, duration_s: float) -> str:
    if not p.get("present"):
        return "not run"
    if p.get("incomplete"):
        return "incomplete (fit not finished or crashed silently)"
    if not p.get("ok"):
        return "FAILED: " + "; ".join(p.get("messages", [])[:1])
    kept = p.get("anchors_kept", 0)
    found = p.get("anchors_found", kept)
    rms = p.get("residual_rms_ms", float("nan"))
    if duration_s > 0 and found > CORRUPT_ANCHOR_FACTOR * max(1.0, duration_s / ANCHOR_CADENCE_S):
        return (f"CORRUPT SYNC LANES: {found} 'anchors' decoded where <= {int(duration_s / ANCHOR_CADENCE_S)} are possible at the 5-s cadence, "
                f"residual {rms / 1000:.0f} s: analogin lanes 14/15 carry noise, no field-PC time for this session")
    if kept == 0:
        return "no anchors (logger never BLE-connected)"
    if duration_s < 120:
        return f"{kept} anchors (record too short to judge drift)"
    drift = abs(p.get("drift_ppm", float("nan")))
    sem = p.get("drift_sem_ppm", float("nan"))
    if kept < 10:
        return f"{kept} anchors < 10 (fit not publishable)"
    if duration_s >= 3600 and (drift > 200 or rms > 150):
        return (f"BAD FIT: {kept} anchors, drift {p['drift_ppm']:+.0f} ppm, residual {rms:.0f} ms, anchors inconsistent "
                f"(field-PC clock step or a Resync during the recording?); inspect pc_time_fit_summary.jpg and the field-PC drift log")
    if drift > 200 or (sem == sem and sem > max(50.0, drift)):
        return f"{kept} anchors, drift {drift:.0f}+/-{sem:.0f} ppm (unconstrained, short record)"
    return f"OK: {kept} anchors, drift {p['drift_ppm']:+.1f} ppm, residual {rms:.0f} ms"


def load_chain(cohort: str) -> dict[tuple[str, str], dict]:
    """Per-session rows of ephys/pc_time_chain.py (day-wrap-aware fits); {} when not generated yet."""
    p = report_dir(cohort) / f"ephys_spikes_pc_time_chain_{cohort}.csv"
    if not p.exists():
        return {}
    return {(r["animal"], r["session"]): r for r in csv.DictReader(open(p, encoding="utf-8"))}


def chain_verdict(c: dict) -> str:
    v = c["verdict"]
    if v == "OK-native":
        return f"OK: {c['n_kept']} anchors, drift {float(c['drift_native_ppm']):+.1f} ± {float(c['drift_native_sem_ppm']):.1f} ppm, residual {float(c['native_residual_ms']):.0f} ms"
    if v == "OK-chained":
        return f"OK (chained {c['borrowed_from']}): drift {float(c['drift_chained_ppm']):+.1f} ± {float(c['chain_unc_ppm']):.0f} ppm; start offset known to BLE precision"
    if v == "one-end-only":
        return f"start cluster only ({c['n_native_start']} anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions"
    if v == "corrupt":
        return "CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time"
    if v == "no-anchors":
        return "no anchors (logger never BLE-connected)"
    return f"{v}: drift {c.get('drift_native_ppm') or c.get('drift_chained_ppm')} ppm"


def build(cohort: str, animals: list[str] | None, pc_time_root: Path) -> tuple[str, list[dict]]:
    cfg = ephys_block(cohort)
    rows, detail = load_index(cohort)
    chain = load_chain(cohort)
    if animals:
        want = {_norm_animal(a) for a in animals}
        rows = [r for r in rows if _norm_animal(r["animal"]) in want]
    by_animal: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_animal[_norm_animal(r["animal"])].append(r)
    for a in by_animal:
        by_animal[a].sort(key=lambda r: r.get("start_local", ""))

    timeline: list[dict] = []
    L: list[str] = []
    L.append(f"# WILD offload QC — cohort `{cohort}`\n")
    L.append(f"Generated {utc_now_iso()} by `ephys/offload_qc_report.py` (git {git_commit()}) from the session index "
             f"(`ephys_spikes_session_index_{cohort}.csv`) and the PC-time fits under `{pc_time_root}`. Regenerate; do not hand-edit.\n")
    L.append("Definitions: see the docstring of `ephys/offload_qc_report.py` and the index's Definitions section "
             "(`ticks_per_s`, `tick_removal_frac`, `regime`, `noise_uV`, bad-channel rule). Times are the logger wallclock "
             "(field-PC local time at Resync, EDT).\n")

    # ---- firmware summary ----
    L.append("## Firmware summary (measured, worst of 5 × 30-s windows per session)\n")
    L.append("| firmware | sessions | hours | ticks/s (median / max over sessions) | tick removal (min) | noise µV (median) | regimes |\n|---|---|---|---|---|---|---|")
    fw_groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        fw_groups[r.get("firmware", "?")].append(r)
    fw_verdicts = {}
    for fw in sorted(fw_groups, key=lambda x: int(x) if str(x).isdigit() else 0):
        g = fw_groups[fw]
        ticks = sorted(float(r["ticks_per_s"]) for r in g if r.get("ticks_per_s") not in ("", None))
        rem = [float(r["tick_removal_frac"]) for r in g if r.get("tick_removal_frac") not in ("", None)]
        noise = sorted(float(r["noise_uV_median"]) for r in g if r.get("noise_uV_median") not in ("", None))
        regimes = defaultdict(int)
        for r in g:
            regimes[r.get("regime", "?")] += 1
        hours = sum(float(r.get("duration_s") or 0) for r in g) / 3600
        med_t = ticks[len(ticks) // 2] if ticks else float("nan")
        max_t = ticks[-1] if ticks else float("nan")
        fw_verdicts[fw] = (max_t, len(g))
        L.append(f"| FM{fw} | {len(g)} | {hours:.1f} | {med_t:.1f} / {max_t:.1f} | {min(rem) if rem else float('nan'):.3f} | "
                 f"{noise[len(noise) // 2] if noise else float('nan'):.1f} | {', '.join(f'{k}:{v}' for k, v in sorted(regimes.items()))} |")
    L.append("")
    if "65" in fw_verdicts:
        mx, n = fw_verdicts["65"]
        L.append(f"**FM65 verdict:** {'CLEAN — every FM65 session measures < 1 tick/s in its worst window' if mx < 1 else 'NOT clean — at least one FM65 session measures ≥ 1 tick/s (see table)'} "
                 f"(n = {n} sessions, max worst-window ticks/s = {mx:.2f}). FM64 sessions of the same loggers are the control.\n")
    else:
        L.append("**FM65 verdict:** no FM65 session indexed yet.\n")

    # ---- per-animal timeline ----
    L.append("## Per-animal timeline and continuity\n")
    for a in sorted(by_animal):
        g = by_animal[a]
        L.append(f"### {a} (logger {g[0].get('logger_mac', '')}) — {len(g)} sessions, {sum(float(r.get('duration_s') or 0) for r in g) / 3600:.1f} h\n")
        L.append("| session | FW | start | end | dur | GB | rtc=folder | sidecars | measured (worst window) | ticks/s | removable | noise µV | bad ch | PC-time fit | notes |\n"
                 "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        prev_end = None
        prev_name = None
        for r in g:
            start = datetime.strptime(r["start_local"][:19], FMT) if r.get("start_local") else None
            dur = float(r.get("duration_s") or 0)
            end = start + timedelta(seconds=dur) if start else None
            gap_min = (start - prev_end).total_seconds() / 60 if (start and prev_end) else None
            gap_flag = ""
            if gap_min is not None:
                if gap_min < -1 / 60:
                    gap_flag = f"OVERLAP {gap_min:.1f} min with previous"
                elif gap_min > 10:
                    gap_flag = f"gap {gap_min:.0f} min after previous"
            pc = parse_pc_time_summary(pc_time_root / a / r["session"] / "pc_time_summary.txt")
            c = chain.get((a, r["session"]))
            pcv = chain_verdict(c) if c else pc_time_verdict(pc, dur)
            if c:
                pc = {"anchors_kept": c.get("n_kept") or c.get("n_anchors"), "drift_ppm": c.get("drift_native_ppm") or c.get("drift_chained_ppm"),
                      "residual_rms_ms": c.get("native_residual_ms")}
            side = "ok" if (str(r.get("time_dat_ok")) == "True" and str(r.get("analogin_ok")) == "True" and str(r.get("has_info_rhd")) == "True") else \
                f"time.dat {r.get('time_dat_ok')} analogin {r.get('analogin_ok')} rhd {r.get('has_info_rhd')}"
            notes = "; ".join(x for x in (gap_flag, r.get("notes", "")) if x)
            L.append(f"| `{r['session']}` | FM{r.get('firmware', '?')} | {r.get('start_local', '')[:19]} | {end.strftime(FMT) if end else ''} | {r.get('duration_hms', '')} | "
                     f"{r.get('amplifier_gb', '')} | {r.get('rtc_agrees_with_folder', '')} | {side} | {r.get('measured_verdict', '')} | {r.get('ticks_per_s', '')} | "
                     f"{r.get('tick_removal_frac', '')} | {r.get('noise_uV_median', '')} | {r.get('bad_channel_candidates', '')} | {pcv} | {notes} |")
            timeline.append({"animal": a, "session": r["session"], "firmware": r.get("firmware", ""), "start": r.get("start_local", ""),
                             "end": end.strftime(FMT) if end else "", "duration_s": dur, "gap_from_previous_min": "" if gap_min is None else round(gap_min, 2),
                             "previous_session": prev_name or "", "measured_verdict": r.get("measured_verdict", ""), "ticks_per_s": r.get("ticks_per_s", ""),
                             "tick_removal_frac": r.get("tick_removal_frac", ""), "regime_by_window": r.get("regime_by_window", ""),
                             "pc_time": pcv, "anchors_kept": pc.get("anchors_kept", ""), "drift_ppm": pc.get("drift_ppm", ""),
                             "residual_rms_ms": pc.get("residual_rms_ms", ""), "notes": notes})
            prev_end, prev_name = end, r["session"]
        L.append("")

    # ---- problems list ----
    # ---- PC-time overview ----
    L.append("## Field-PC-time fit overview (sessions >= 1 h)\n")
    if chain:
        L.append("Source: `ephys/pc_time_chain.py` (day-wrap-aware, delay word not added, adjacent-session anchors chained through the RTC). "
                 "The reference generator's per-session fits are superseded: it mis-handles the 86,400,000-ms day wrap (post-midnight anchors "
                 "land 416.77 s early after the 2^20 packing) and adds a delay word that shifts anchors by 0.7–2.6 s.\n")
    L.append("| verdict | sessions | hours |\n|---|---|---|")
    agg: dict[str, list[float]] = defaultdict(list)
    for t in timeline:
        if t["duration_s"] >= 3600:
            v = t["pc_time"]
            if v.startswith("OK (chained"):
                key = "OK (chained through the next session's start)"
            elif v.startswith(("OK", "BAD FIT", "CORRUPT", "FAILED")):
                key = v.split(":")[0].split(" (")[0]
            elif "< 10" in v:
                key = "< 10 anchors"
            elif v.startswith("start cluster only"):
                key = "start cluster only (offset known, drift assumed)"
            else:
                key = v
            agg[key].append(t["duration_s"])
    for k in sorted(agg, key=lambda x: -sum(agg[x])):
        L.append(f"| {k} | {len(agg[k])} | {sum(agg[k]) / 3600:.1f} |")
    L.append("")
    L.append("## Problems and flags\n")
    probs = []
    for t in timeline:
        if isinstance(t["gap_from_previous_min"], (int, float)) and t["gap_from_previous_min"] < -1 / 60:
            probs.append(f"OVERLAP: {t['animal']} `{t['session']}` starts {abs(t['gap_from_previous_min']):.1f} min before `{t['previous_session']}` ends")
    for r in rows:
        a = _norm_animal(r["animal"])
        if str(r.get("rtc_agrees_with_folder")) == "False":
            probs.append(f"RTC/folder mismatch: {a} `{r['session']}` (rtc_start {r.get('rtc_start')})")
        if str(r.get("time_dat_ok")) != "True" or str(r.get("analogin_ok")) != "True" or str(r.get("has_info_rhd")) != "True":
            probs.append(f"sidecar inconsistency: {a} `{r['session']}` time.dat {r.get('time_dat_ok')} analogin {r.get('analogin_ok')} info.rhd {r.get('has_info_rhd')}")
        if r.get("regime") not in ("normal", "", None):
            probs.append(f"noise regime {r.get('regime')}: {a} `{r['session']}` (FM{r.get('firmware')}, windows {r.get('regime_by_window')}, removal {r.get('tick_removal_frac')})")
        if str(r.get("deglitch_required")) == "False" and str(r.get("measured_verdict", "")).startswith("glitchy"):
            probs.append(f"FIRMWARE CLAIM VIOLATED: {a} `{r['session']}` FM{r.get('firmware')} measures glitchy ({r.get('ticks_per_s')} ticks/s)")
        if r.get("notes"):
            regime_fragments = ("WIDE", "BROADBAND", "QC before use", "de-glitch will NOT clean this", "hardware/handling regime")
            for n in str(r["notes"]).split("; "):
                if n and "measured clean on the probe window" not in n and not n.startswith(regime_fragments):
                    probs.append(f"index note: {a} `{r['session']}`: {n}")
    for t in timeline:
        if t["pc_time"].startswith(("FAILED", "no anchors", "BAD FIT", "CORRUPT", "inconsistent")) and t["duration_s"] >= 600:
            probs.append(f"PC-time: {t['animal']} `{t['session']}` ({t['duration_s'] / 3600:.1f} h): {t['pc_time']}")
    L.extend([f"- {p}" for p in probs] or ["- none"])
    L.append("")
    L.append("## How to read\n")
    L.append("- `deglitch?`/firmware < 65 sessions must be staged (`ephys/stage_session.py`) before analysis; FM65 sessions are copied verbatim.")
    L.append("- A `wide-impulse` / `broadband` regime is not fixed by de-glitching: exclude or QC by hand.")
    L.append("- 'PC time' = the FIELD recording PC's clock (BLE master), embedded in each logger's analogin.dat; nothing from the analysis PC enters the fit. "
             "A fit marked OK gives a session-level field-PC-time coordinate (BLE precision, ~10–100 ms); sub-ms alignment needs the LED edges. Gaps between sessions are battery rounds unless noted.")
    return "\n".join(L) + "\n", timeline


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--animals", nargs="*", default=None)
    ap.add_argument("--pc-time-root", default=None, help="default <OUT_ROOT>/<cohort>/ephys_pc_time")
    ap.add_argument("--suffix", default="", help="optional report-name suffix, e.g. _SF07")
    a = ap.parse_args()
    ar = (ephys_block(a.cohort).get("analysis_root"))
    pc_root = Path(a.pc_time_root) if a.pc_time_root else (Path(ar) / "pc_time" if ar else out_root() / resolve_cohort(a.cohort) / "ephys_pc_time")
    md, timeline = build(a.cohort, a.animals, pc_root)
    rd = report_dir(a.cohort)
    md_path = rd / f"ephys_spikes_offload_qc_{a.cohort}{a.suffix}.md"
    csv_path = rd / f"ephys_spikes_offload_qc_{a.cohort}{a.suffix}.csv"
    md_path.write_text(md, encoding="utf-8")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(timeline[0].keys()) if timeline else ["animal"])
        w.writeheader()
        for t in timeline:
            w.writerow(t)
    print(f"report -> {md_path}\ntimeline -> {csv_path}")


if __name__ == "__main__":
    main()
