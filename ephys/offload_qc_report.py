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


def load_pc_marks(path: Path | None) -> dict[str, list[tuple]]:
    """Field-PC Rec Start/Stop marks (field2026-sync from-field *pc-side-session-marks.csv): {animal: [(start_local, elapsed_s)]}."""
    out: dict[str, list[tuple]] = defaultdict(list)
    if path is None or not Path(path).exists():
        return out
    import re
    from datetime import timezone
    ET = timezone(timedelta(hours=-4))
    for r in csv.DictReader(open(path, encoding="cp1252")):
        try:
            st = datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", r["rec_start_utc"]).replace("Z", "+00:00")).astimezone(ET).replace(tzinfo=None)
            out[r["animal"]].append((st, float(r["pc_elapsed_s"])))
        except Exception:
            continue
    return out


def card_vs_pc_span(marks: dict, animal: str, start: datetime, duration_s: float) -> tuple[str, float | None]:
    """Card duration minus the field PC's Rec Start->Stop span for the matching mark (start within 5 s).
    Normal: +0.1 ... +0.9 s (the Stop ack lands after the last block). Below -1.0 s: samples missing on the card."""
    best = None
    for st, el in marks.get(animal, []):
        dt = abs((st - start).total_seconds())
        if dt <= 5 and (best is None or dt < best[0]):
            best = (dt, el)
    if best is None:
        return "", None
    d = duration_s - best[1]
    return f"{d:+.1f}", d


def chain_verdict(c: dict) -> str:
    v = c["verdict"]
    if v.startswith("OK-native"):
        extra = " (field-PC step inside, modelled)" if "step" in v else (" (mid-session outliers)" if "outliers" in v else "")
        return f"OK{extra}: {c['n_kept']} anchors, drift {float(c['drift_native_ppm']):+.1f} ± {float(c['drift_native_sem_ppm']):.1f} ppm, residual {float(c['native_residual_ms']):.0f} ms"
    if v == "OK-chained":
        return f"OK (chained {c['borrowed_from']}): drift {float(c['drift_chained_ppm']):+.1f} ± {float(c['chain_unc_ppm']):.0f} ppm; start offset known to BLE precision"
    if v == "one-end-only":
        return f"start cluster only ({c['n_native_start']} anchors, no chainable neighbour): offset known, drift assumed from the logger's other sessions"
    if v == "corrupt":
        return "CORRUPT SYNC LANES (noise decoded as anchors); no field-PC time"
    if v == "no-anchors":
        return "no anchors (logger never BLE-connected)"
    if v.startswith("DISCONTINUITY"):
        return f"DISCONTINUITY inside (ends OK): {c.get('step_note', '')}"
    return f"{v}: drift {c.get('drift_native_ppm') or c.get('drift_chained_ppm')} ppm"


def build(cohort: str, animals: list[str] | None, pc_time_root: Path, pc_marks_path: Path | None = None) -> tuple[str, list[dict]]:
    cfg = ephys_block(cohort)
    # Sessions the field log marks as not-real recordings (cohorts/<key>.yaml ephys.field_flags): kept in the index, excluded
    # from the firmware verdict and named in the problems list instead of being reported as a firmware failure
    field_flags = {}
    for ff in ((cfg.get("_cohort_yaml") or {}).get("ephys", {}).get("field_flags") or []):
        for s in ff.get("sessions", []):
            field_flags[(_norm_animal(str(ff.get("animal"))), s)] = str(ff.get("flag", "field-flagged"))

    def flagged(r):
        return field_flags.get((_norm_animal(str(r.get("animal"))), r.get("session")))
    rows, detail = load_index(cohort)
    chain = load_chain(cohort)
    marks = load_pc_marks(pc_marks_path)
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
        # removal fraction is only meaningful with a measurable tick count: sessions >= 120 s with >= 1 tick/s
        rem = [min(1.0, max(0.0, float(r["tick_removal_frac"]))) for r in g
               if r.get("tick_removal_frac") not in ("", None) and float(r.get("duration_s") or 0) >= 120 and float(r.get("ticks_per_s") or 0) >= 1.0]
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
        # the defect signature is single-sample ticks at 100-2,500/s that the median rule removes (tick_removal_frac ~1);
        # a few ordinary fast transients per second on a noisy logger are neither. Verdict per logger: FM65 worst-window
        # ticks/s must stay below the 'glitchy' threshold (10/s) AND below 5 % of the same logger's FM64 median.
        per_logger = []
        MIN_S = 120.0   # round-time guard/test records (a few seconds, rats in hand) carry no information about the firmware
        # ticks concentrated on one or two channels are a flaky contact / bad channel, not the firmware defect (which hit
        # many channels with a fixed donor channel); such sessions are excluded from the firmware verdict and named
        local_notes = []
        flag_notes = []
        probe_detail = {(s.get("animal"), s.get("session")): s.get("probe", {}) for s in detail.get("sessions", [])} if isinstance(detail, dict) else {}

        def channel_local(r):
            p = probe_detail.get((r["animal"], r["session"]), {})
            tpc = p.get("ticks_per_channel_per_s") or []
            if not tpc or sum(tpc) <= 0:
                return None
            order = sorted(range(len(tpc)), key=lambda c: -tpc[c])
            share = (tpc[order[0]] + tpc[order[1]]) / sum(tpc) if len(order) > 1 else 1.0
            return order[:2] if share >= 0.7 else None

        for an in sorted({r["animal"] for r in rows}):
            f64 = [float(r["ticks_per_s"]) for r in fw_groups.get("64", []) if r["animal"] == an and r.get("ticks_per_s") not in ("", None) and float(r.get("duration_s") or 0) >= MIN_S]
            f65 = []
            for r in fw_groups.get("65", []):
                if r["animal"] != an or r.get("ticks_per_s") in ("", None) or float(r.get("duration_s") or 0) < MIN_S:
                    continue
                t = float(r["ticks_per_s"])
                fl = flagged(r)
                if fl:
                    flag_notes.append(f"{an} `{r['session']}` {t:.1f}/s ({fl})")
                    continue
                loc = channel_local(r) if t >= 5.0 else None
                if loc:
                    local_notes.append(f"{an} `{r['session']}` {t:.1f}/s concentrated on ch {loc} (channel-local impulses, not the defect)")
                    continue
                f65.append(t)
            if not f65:
                continue
            med64 = sorted(f64)[len(f64) // 2] if f64 else float("nan")
            ok = max(f65) < 10.0 and (not f64 or max(f65) < max(0.05 * med64, 5.0))   # 5/s floor: ordinary transients, not the defect
            per_logger.append((an, max(f65), med64, ok))
        all_ok = all(x[3] for x in per_logger) if per_logger else False
        L.append(f"**FM65 verdict:** {'CLEAN' if all_ok else 'NOT clean'} — per logger, FM65 worst-window ticks/s vs the same logger's FM64 median: "
                 + "; ".join(f"{an} {m65:.1f} vs {m64:.0f}{' ok' if ok else ' FAIL'}" for an, m65, m64, ok in per_logger)
                 + f" (n = {n} FM65 sessions, max {mx:.2f}/s). The residual 1–7/s on the noisier loggers are ordinary fast transients "
                   "(they are not removed by the median rule, unlike the defect), two orders of magnitude below the FM64 defect load."
                 + (" Excluded as channel-local: " + "; ".join(local_notes) + "." if local_notes else "")
                 + (" Excluded as field-flagged: " + "; ".join(flag_notes) + "." if flag_notes else "") + "\n")
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
            span_txt, span_d = card_vs_pc_span(marks, a, start, dur) if (start and marks) else ("", None)
            steps_inside = []
            if start:
                for s_ in (cfg.get("field_pc_clock_steps") or []):
                    ts_ = datetime.strptime(str(s_["time"]), FMT)
                    if start < ts_ < start + timedelta(seconds=dur):
                        steps_inside.append(f"{s_['time']} {float(s_['jump_s']):+.2f} s")
            if span_d is not None and span_d < -1.0 and dur >= 600:
                if steps_inside:
                    pcv += (f" | field-PC clock stepped forward inside the session ({'; '.join(steps_inside)}, LED log): PC span {abs(span_d):.1f} s "
                            f"longer than the card, no samples missing; pc_time.dat models the step")
                else:
                    pcv += f" | CARD {abs(span_d):.1f} s SHORTER than the field-PC span (normal +0.1..+0.9) with no known PC step inside: samples missing on the card?"
            elif span_d is not None and span_d > 3.0 and dur >= 600:
                if c and c["verdict"].startswith("OK-native") and int(c.get("n_native_end") or 0) >= 2:
                    pcv += (f" | card {span_d:.1f} s LONGER than the field-PC Rec Start->Stop span, but BLE anchors run to the card's end: "
                            f"the PC's Stop was not acted on by the logger until {span_d:.0f} s later (no duplicated data)")
                else:
                    pcv += f" | card {span_d:.1f} s LONGER than the field-PC span: check for duplicated blocks (integrity_scan.py --full-hash)"
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
                             "end": end.strftime(FMT) if end else "", "duration_s": dur, "card_minus_pc_span_s": span_txt,
                             "gap_from_previous_min": "" if gap_min is None else round(gap_min, 2),
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
            elif v.startswith("OK (field-PC step"):
                key = "OK (field-PC step inside, modelled)"
            elif v.startswith(("OK", "BAD FIT", "CORRUPT", "FAILED", "DISCONTINUITY")):
                key = v.split(":")[0].split(" (")[0]
            elif v.startswith("not run"):
                key = "not run"
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
        if str(r.get("deglitch_required")) == "False" and str(r.get("measured_verdict", "")).startswith("glitchy") and float(r.get("duration_s") or 0) >= 120:
            loc = channel_local(r)
            fl = flagged(r)
            if fl:
                probs.append(f"field-flagged (excluded from analysis and from the firmware verdict): {a} `{r['session']}` — {fl}")
            elif loc:
                probs.append(f"channel-local impulses: {a} `{r['session']}` FM{r.get('firmware')} {r.get('ticks_per_s')} ticks/s concentrated on ch {loc} (flaky contact / bad channel, not the firmware defect; add to reject_channels)")
            else:
                probs.append(f"FIRMWARE CLAIM VIOLATED: {a} `{r['session']}` FM{r.get('firmware')} measures glitchy ({r.get('ticks_per_s')} ticks/s)")
        if r.get("notes"):
            regime_fragments = ("WIDE", "BROADBAND", "QC before use", "de-glitch will NOT clean this", "hardware/handling regime")
            for n in str(r["notes"]).split("; "):
                if n and "measured clean on the probe window" not in n and not n.startswith(regime_fragments):
                    probs.append(f"index note: {a} `{r['session']}`: {n}")
    for t in timeline:
        if (t["pc_time"].startswith(("FAILED", "no anchors", "BAD FIT", "CORRUPT", "inconsistent", "DISCONTINUITY")) or "SHORTER than" in t["pc_time"]
                or "LONGER than" in t["pc_time"] or "stepped forward inside" in t["pc_time"]) and t["duration_s"] >= 600:
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
    ap.add_argument("--pc-marks", default=None, help="field-PC Rec Start/Stop marks CSV (field2026-sync from-field/*pc-side-session-marks.csv); default: newest one there")
    ap.add_argument("--suffix", default="", help="optional report-name suffix, e.g. _SF07")
    a = ap.parse_args()
    ar = (ephys_block(a.cohort).get("analysis_root"))
    pc_root = Path(a.pc_time_root) if a.pc_time_root else (Path(ar) / "pc_time" if ar else out_root() / resolve_cohort(a.cohort) / "ephys_pc_time")
    marks_path = Path(a.pc_marks) if a.pc_marks else None
    if marks_path is None:
        cands = sorted(Path("C:/Users/Cornell/Documents/GitHub/field2026-sync/from-field").glob("*pc-side-session-marks.csv"))
        marks_path = cands[-1] if cands else None
    md, timeline = build(a.cohort, a.animals, pc_root, marks_path)
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
