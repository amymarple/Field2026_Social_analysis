"""Index every offloaded WILD session of a cohort with its firmware version and glitch evidence.

For each ``<raw_root>/<animal>/<logger MAC>/<slot>_<YYYYMMDD>_<HHMMSS>.<ms>/`` it records the header
(``CE_params.bin``: firmware, hardware, RTC start, MAC, fs, Nch), sizes/duration, sidecar consistency, the
firmware-derived provenance verdict (``deglitch_required = firmware_version < clean_firmware_min``), and a
MEASURED 30-s glitch probe (ticks/s, glitch samples/s, bad-channel candidates; see ephys/signal_probe.py) so the
firmware rule is checked against the data itself (this is how FM65 gets evaluated once it is offloaded).

Outputs (cohort-keyed, canonical):
    results/<cohort>/ephys_spikes/reports/ephys_spikes_session_index_<cohort>.csv   one row per session
    results/<cohort>/ephys_spikes/reports/ephys_spikes_session_index_<cohort>.md    human table + definitions
    results/<cohort>/ephys_spikes/reports/ephys_spikes_session_index_<cohort>.json  per-channel probe detail
and, unless --no-mirror, the same CSV/MD as SESSION_INDEX.{csv,md} under the cohort's analysis folder
(<ephys.analysis_root>/index/, e.g. E:/3rd_rat_spikes/analysis/index/) for other agents; never inside a raw session folder.

Usage:
  python ephys/build_session_index.py --cohort 2026c [--raw-root E:/3rd_rat_spikes] [--probe-seconds 30] [--no-mirror]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from _common import (PROJECT_ROOT, ephys_block, git_commit, iter_raw_sessions, parse_session_name, raw_ephys_root,
                     report_dir, utc_now_iso, write_json)
from signal_probe import probe_window_stats
from wild_ce_params import parse_ce_params

CSV_COLUMNS = [
    "animal", "logger_mac", "session", "slot", "start_local", "end_local", "duration_s", "duration_hms",
    "firmware", "hw", "provenance", "deglitch_required", "commit_risk", "measured_verdict", "regime", "regime_by_window", "ticks_per_s",
    "tick_removal_frac", "raw_std_median_adc", "glitch_samples_per_s", "glitch_pct_samples", "probe_seconds", "probe_windows", "noise_uV_median",
    "bad_channel_candidates",
    "fs", "n_channels", "n_samples", "amplifier_gb", "rtc_start", "rtc_agrees_with_folder", "has_info_rhd",
    "time_dat_ok", "analogin_ok", "sd_capacity_kb", "error_code", "valid_until", "adc_lane", "field_flag", "notes", "path",
]


def _hms(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 3600:d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"


def provenance_for(fw: int, cfg: dict) -> tuple[str, bool, str]:
    clean_min = int(cfg.get("clean_firmware_min", 65))
    hist = cfg.get("firmware_history") or {}
    label = hist.get(fw) or hist.get(str(fw)) or "(no field note for this firmware)"
    if fw < clean_min:
        return f"FM{fw}: {label}", True, "stop-only commit (session exists only after a clean Record Stop)"
    return f"FM{fw}: {label}", False, "power-cut-safe commit (maker, FM65+)"


def index_session(animal: str, mac: str | None, sdir: Path, cfg: dict, *, probe_seconds: float, probe_windows: int = 5,
                  valid_until: str = "") -> tuple[dict, dict]:
    nch = int(cfg.get("n_channels", 64))
    fs = float(cfg.get("sampling_rate_hz", 20000))
    gain = float(cfg.get("gain_to_uV", 0.195))
    dg = cfg.get("deglitch") or {}
    meta = parse_session_name(sdir.name) or {}
    notes = []
    row = {c: "" for c in CSV_COLUMNS}
    row.update({"animal": animal, "logger_mac": mac or "", "session": sdir.name, "slot": meta.get("slot", ""), "path": str(sdir)})
    detail: dict = {"animal": animal, "session": sdir.name}

    amp = sdir / "amplifier.dat"
    ce = sdir / "CE_params.bin"
    if ce.exists():
        cp = parse_ce_params(ce)
        nch = cp.n_channels or nch
        fs = float(cp.fs or fs)
        row.update({"firmware": cp.firmware_version, "hw": cp.hw_version, "fs": int(fs), "n_channels": nch,
                    "rtc_start": cp.rtc_start or "", "sd_capacity_kb": cp.sd_capacity, "error_code": cp.error_code})
        if mac and cp.mac != mac.upper():
            notes.append(f"header MAC {cp.mac} != folder MAC {mac}")
        # ADC ("microphone") lane: byte 28 == 0x08 or sampling_rates[2] == 160000 -> the amplifier stream carries a 312.5 Hz full-scale
        # pulse train and adc.dat holds no usable signal (measured 2026-09-10; cohorts/<key>.yaml ephys.adc_lane). Such sessions belong
        # in <raw_root>/_quarantine_adc_lane_on (ephys/quarantine_adc_sessions.py); if one is still in the tree, say so loudly.
        raw_ce = ce.read_bytes()
        sr2 = cp.sampling_rates[2] if len(cp.sampling_rates) > 2 else 0
        if (len(raw_ce) > 28 and raw_ce[28] == 0x08) or sr2 == 160000 or (sdir / "adc.dat").exists() and os.path.getsize(sdir / "adc.dat") > 0:
            row["adc_lane"] = "ON"
            notes.append("ADC LANE ON (byte 28 = 0x08 / 160 kHz adc.dat): amplifier carries the 312.5 Hz pulse train - UNUSABLE; quarantine it (ephys/quarantine_adc_sessions.py --move)")
        prov, need, risk = provenance_for(cp.firmware_version, cfg)
        row.update({"provenance": prov, "deglitch_required": need, "commit_risk": risk})
        if meta and cp.rtc_start:
            rtc = datetime.strptime(cp.rtc_start, "%Y-%m-%d %H:%M:%S")
            row["rtc_agrees_with_folder"] = abs((rtc - meta["start"].replace(microsecond=0)).total_seconds()) <= 1
        # cross-check with the field boundary (every session started before 2026-09-01 19:00 ET is affected)
        if meta and meta["start"] < datetime(2026, 9, 1, 19, 0) and not need:
            notes.append("firmware says clean but session predates the 2026-09-01 19:00 FM65 upgrade")
    else:
        notes.append("CE_params.bin missing")

    if meta:
        row["start_local"] = meta["start"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    if amp.exists():
        nbytes = os.path.getsize(amp)
        ns = nbytes // (2 * nch)
        if nbytes % (2 * nch):
            notes.append(f"amplifier.dat size {nbytes} not a multiple of 2*{nch}")
        dur = ns / fs
        row.update({"n_samples": ns, "amplifier_gb": round(nbytes / 1e9, 3), "duration_s": round(dur, 3), "duration_hms": _hms(dur)})
        if meta:
            row["end_local"] = (meta["start"] + timedelta(seconds=dur)).strftime("%Y-%m-%d %H:%M:%S")
        t = sdir / "time.dat"
        row["time_dat_ok"] = (t.exists() and os.path.getsize(t) == 4 * ns)
        an = sdir / "analogin.dat"
        misc_ratio = cp.misc_ratio if ce.exists() and cp.misc_ratio else 16
        row["analogin_ok"] = (an.exists() and os.path.getsize(an) == 2 * ns)  # misc_ratio lanes at fs/misc_ratio == 2*ns bytes
        if an.exists() and not row["analogin_ok"]:
            notes.append(f"analogin.dat {os.path.getsize(an)} B, expected {2 * ns} (misc_ratio {misc_ratio})")
        max_samples = None
        if valid_until and meta:
            vu = datetime.strptime(valid_until[:19], "%Y-%m-%d %H:%M:%S")
            n_valid = int((vu - meta["start"]).total_seconds() * fs)
            if 0 < n_valid < ns:
                max_samples = n_valid
                row["valid_until"] = vu.strftime("%Y-%m-%d %H:%M:%S")
                notes.append(f"recording continues {(ns - n_valid) / fs / 3600:.2f} h past valid_until {row['valid_until']} "
                             "(cohorts/<key>.yaml ephys.valid_until): probe windows and coverage limited to the valid part")
            else:
                notes.append(f"valid_until {valid_until} is outside the session; ignored")
        if probe_seconds > 0 and ns >= 16:
            st = probe_window_stats(amp, nch=nch, fs=fs, seconds=probe_seconds, k=float(dg.get("k_mad", 10.0)),
                                    floor=float(dg.get("floor_adc", 500.0)), gain_uV=gain, n_windows=probe_windows, max_samples=max_samples)
            detail["probe"] = st
            row.update({"measured_verdict": st["verdict"], "regime": st.get("regime", ""), "regime_by_window": st.get("regime_by_window", st.get("regime", "")),
                        "probe_windows": st.get("n_windows", 1), "ticks_per_s": round(st.get("ticks_per_s", float("nan")), 2),
                        "tick_removal_frac": round(st.get("tick_removal_frac", float("nan")), 3), "raw_std_median_adc": round(st.get("raw_std_median_adc", float("nan")), 0),
                        "glitch_samples_per_s": round(st.get("glitch_samples_per_s", float("nan")), 2),
                        "glitch_pct_samples": round(st.get("glitch_pct_samples", float("nan")), 4),
                        "probe_seconds": round(st["probe_seconds"], 2), "noise_uV_median": round(st.get("noise_uV_median", float("nan")), 2),
                        "bad_channel_candidates": " ".join(str(c) for c in st.get("bad_channel_candidates", []))})
            if row.get("deglitch_required") is False and st["verdict"].startswith("glitchy"):
                notes.append("MEASURED GLITCHY although firmware >= clean_firmware_min")
            if row.get("deglitch_required") is True and st["verdict"].startswith("clean"):
                notes.append("measured clean on the probe window despite pre-FM65 firmware (de-glitch anyway)")
            if st.get("regime") == "wide-impulse":
                notes.append("WIDE (>=3-sample) impulses dominate: not the FM62/64 single-sample defect; de-glitch will NOT clean this; QC before use")
            if st.get("regime") == "broadband":
                notes.append("BROADBAND noise blow-up (raw std > 2500 ADC): hardware/handling regime; QC before use")
    else:
        notes.append("amplifier.dat missing")
    row["has_info_rhd"] = (sdir / "info.rhd").exists()
    row["notes"] = "; ".join(notes)
    return row, detail


def _norm_animal(a: str) -> str:
    a = str(a).upper()
    return f"SF{int(a[2:]):02d}" if a.startswith("SF") and a[2:].isdigit() else a


def field_flag_map(cfg: dict) -> dict[tuple[str, str], str]:
    """(animal, session) -> flag text from cohorts/<key>.yaml ephys.field_flags: sessions the field record marks as not-real
    recordings or as test recordings (kept in the index; excluded from coverage, the firmware verdict and any analysis until
    decided). An entry with `pc_time: false` was recorded from another PC's console: its BLE anchors are not field-PC time."""
    out = {}
    for ff in ((cfg.get("_cohort_yaml") or {}).get("ephys", {}).get("field_flags") or []):
        for s in ff.get("sessions") or []:
            out[(_norm_animal(ff.get("animal")), str(s))] = str(ff.get("flag", "field-flagged")) + ("" if ff.get("pc_time", True) else " [no field-PC time]")
    return out


def valid_until_map(cfg: dict) -> dict[tuple[str, str], str]:
    """(animal, session) -> 'YYYY-MM-DD HH:MM:SS' from cohorts/<key>.yaml ephys.valid_until: sessions whose recording continues
    after the neural signal ended (an implant that detached mid-session). The session stays a normal session up to that time
    (fitted, counted, sortable); the probe windows and the coverage tables stop there. Logger wallclock, like start_local."""
    out = {}
    for vu in ((cfg.get("_cohort_yaml") or {}).get("ephys", {}).get("valid_until") or []):
        out[(_norm_animal(vu.get("animal")), str(vu.get("session")))] = str(vu.get("valid_until", ""))
    return out


def _index_one(args):
    animal, mac, sdir, cfg, probe_seconds, probe_windows, valid_until = args
    return index_session(animal, mac, sdir, cfg, probe_seconds=probe_seconds, probe_windows=probe_windows, valid_until=valid_until)


def build_index(raw_root: Path, cfg: dict, *, probe_seconds: float = 30.0, probe_windows: int = 5, verbose: bool = True,
                workers: int = 1) -> tuple[list[dict], list[dict], dict]:
    rows, details = [], []
    animals: dict[str, dict] = {}
    flags = field_flag_map(cfg)
    valid_until = valid_until_map(cfg)
    sessions = list(iter_raw_sessions(raw_root, cfg.get("session_glob", "*"), cohort=(cfg.get("_cohort_yaml") or {}).get("cohort")))
    cfg_plain = {k: v for k, v in cfg.items() if k != "_cohort_yaml"}   # picklable subset for worker processes
    if workers > 1 and len(sessions) > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_index_one, [(a, m, s, cfg_plain, probe_seconds, probe_windows, valid_until.get((_norm_animal(a), s.name), ""))
                                               for a, m, s in sessions]))
    else:
        results = []
        for animal, mac, sdir in sessions:
            if verbose:
                print(f"  {animal} {mac or '-'} {sdir.name} ...", flush=True)
            results.append(index_session(animal, mac, sdir, cfg, probe_seconds=probe_seconds, probe_windows=probe_windows,
                                         valid_until=valid_until.get((_norm_animal(animal), sdir.name), "")))
    for (animal, mac, sdir), (row, det) in zip(sessions, results):
        row["field_flag"] = flags.get((_norm_animal(animal), sdir.name), "")
        rows.append(row)
        details.append(det)
        a = animals.setdefault(animal, {"animal": animal, "logger_mac": mac or "", "n_sessions": 0, "hours": 0.0, "firmware": set(), "recovery_bin_gb": ""})
        a["n_sessions"] += 1
        a["hours"] += float(row.get("duration_s") or 0) / 3600.0
        if row.get("firmware") != "":
            a["firmware"].add(int(row["firmware"]))
    for animal_dir in sorted(p for p in Path(raw_root).iterdir() if p.is_dir() and not p.name.startswith(("$", ".", "_", "analysis"))):
        rb = animal_dir / "recovery.bin"
        a = animals.setdefault(animal_dir.name, {"animal": animal_dir.name, "logger_mac": "", "n_sessions": 0, "hours": 0.0, "firmware": set(), "recovery_bin_gb": ""})
        a["recovery_bin_gb"] = round(os.path.getsize(rb) / 1e9, 1) if rb.exists() else ""
    rows.sort(key=lambda r: (r["animal"], r.get("start_local", "")))
    return rows, details, animals


def write_outputs(rows: list[dict], details: list[dict], animals: dict, *, cohort: str, cfg: dict, raw_root: Path,
                  out_dir: Path, mirror_dir: Path | None, probe_seconds: float) -> dict:
    stem = f"ephys_spikes_session_index_{cohort}"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{stem}.csv"
    md_path = out_dir / f"{stem}.md"
    json_path = out_dir / f"{stem}.json"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    write_json(json_path, {"cohort": cohort, "raw_root": str(raw_root), "written_utc": utc_now_iso(), "git_commit": git_commit(),
                           "probe_seconds": probe_seconds, "clean_firmware_min": cfg.get("clean_firmware_min"),
                           "deglitch": cfg.get("deglitch"), "sessions": details})
    md = render_markdown(rows, animals, cohort=cohort, cfg=cfg, raw_root=raw_root, probe_seconds=probe_seconds, csv_name=csv_path.name)
    md_path.write_text(md, encoding="utf-8")
    out = {"csv": csv_path, "md": md_path, "json": json_path}
    if mirror_dir is not None:
        mirror_dir.mkdir(parents=True, exist_ok=True)
        (mirror_dir / "SESSION_INDEX.csv").write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
        (mirror_dir / "SESSION_INDEX.md").write_text(md, encoding="utf-8")
        out["mirror"] = mirror_dir
    return out


def render_markdown(rows: list[dict], animals: dict, *, cohort: str, cfg: dict, raw_root: Path, probe_seconds: float, csv_name: str) -> str:
    clean_min = cfg.get("clean_firmware_min", 65)
    dg = cfg.get("deglitch") or {}
    L = []
    L.append(f"# WILD neurologger session index — cohort `{cohort}`\n")
    L.append(f"Generated {utc_now_iso()} by `ephys/build_session_index.py` (git {git_commit()}) from `{raw_root}`. "
             f"Machine-readable twin: `{csv_name}`. Regenerate; do not hand-edit.\n")
    L.append("## Firmware provenance (the rule that decides what may be analysed)\n")
    L.append(f"- `firmware` is read from each session's `CE_params.bin` (uint16 at byte 328). "
             f"`deglitch_required = firmware < {clean_min}` (`clean_firmware_min` in `cohorts/{cohort}.yaml`).")
    for k, v in (cfg.get("firmware_history") or {}).items():
        L.append(f"- **FM{k}** — {v}")
    L.append("- `recovery.bin` (per animal) = raw card image kept for a FUTURE recovery of the FM59–62 uncommitted (stop-only-commit) sessions; never parsed here.\n")
    L.append("## Definitions\n")
    L.append("| quantity | formula | plain text |\n|---|---|---|")
    L.append("| `duration_s` | `n_samples / fs`, `n_samples = bytes(amplifier.dat) / (2·n_channels)` | recorded length from the int16 file size; `end_local = start_local + duration_s` (logger wallclock, EDT) |")
    L.append(f"| glitch sample | `\\|x_c(t) − med5_c(t)\\| > max({dg.get('k_mad', 10)}·1.4826·MAD_c, {dg.get('floor_adc', 500)} ADC)` | sample deviating from its 5-point running median beyond a per-channel robust threshold; this is exactly what de-glitching replaces |")
    L.append("| `ticks_per_s` | `#{ \\|x(t) − (x(t−1)+x(t+1))/2\\| > 1200 ADC } / probe_seconds`, summed over channels | the defects-note impulse metric; ~100–1400/s on FM62/64 sessions, ~0 expected on clean data |")
    L.append(f"| `measured_verdict` | glitchy if `ticks_per_s > 10`, clean if `< 1`, else ambiguous; suffixed `+wide-impulse` / `+broadband` when the regime is not normal | data-side evidence from `probe_windows` windows of {probe_seconds:g} s spread over the file (session values = WORST window: max ticks/s, min removal, max std; `regime_by_window` lists each window); checks the firmware rule rather than assuming it |")
    L.append("| `regime` | `broadband` if `raw_std_median_adc > 2500`; `wide-impulse` if `ticks_per_s > 100` and `tick_removal_frac < 0.9`; else `normal` | whether the impulses are the 1–2-sample FM62/64 defect (removable by the 5-point median) or something wider / a noise blow-up that de-glitching cannot fix |")
    L.append("| `tick_removal_frac` | `1 − ticks(after de-glitch of the window) / ticks(before)` | fraction of impulses the median rule actually removes; the FM64 defect gives ≈ 0.997 |")
    L.append("| `raw_std_median_adc` | median over channels of `std(x)` on the probe window | broadband level; clean night sessions ≈ 550–1000 ADC |")
    L.append("| `noise_uV_median` | median over channels of `1.4826·median\\|hp\\|·0.195 µV/ADC`, hp = 500–5000 Hz of the de-glitched window | robust spike-band noise floor (µV, RELATIVE: the 0.195 µV/ADC Intan default is unverified for WILD) |")
    L.append("| `bad_channel_candidates` | `noise_uV < 3` or `noise_uV > 4·median` or `raw_std < 0.25·median` | advisory dead/broken channels for `probes_<cohort>.yaml` `reject_channels` |")
    L.append("| `time_dat_ok` / `analogin_ok` | `bytes(time.dat) = 4·n_samples`; `bytes(analogin.dat) = 2·n_samples` (16 lanes @ fs/16) | sidecar sizes consistent with the amplifier stream |")
    L.append("| `field_flag` | text from `cohorts/<key>.yaml` `ephys.field_flags` (empty = none) | the field record marks the session as not a real recording (zombie restart of a dying cell) or as a TEST recording; kept in this inventory, excluded from coverage, the firmware verdict and any analysis until decided. `[no field-PC time]` = recorded from another PC's console: its BLE anchors are not field-PC time and `pc_time_chain` does not fit it |")
    L.append("| `valid_until` | 'YYYY-MM-DD HH:MM:SS' from `cohorts/<key>.yaml` `ephys.valid_until` (empty = whole session valid), logger wallclock | the neural signal ended before the Stop (implant detached mid-session): the session is a normal session up to this time (fitted, counted, sortable) and open-circuit noise after it; the probe windows and the coverage tables stop here |")
    L.append("| `adc_lane` | `ON` when `CE_params.bin` byte 28 == 0x08 or `sampling_rates[2]` == 160000 or a non-empty `adc.dat` exists (empty = lane off) | the WILD ADC/microphone lane was on: the amplifier stream carries a 312.5 Hz full-scale pulse train and `adc.dat` no usable signal (measured 2026-09-10) - unusable; such sessions are moved to `<raw_root>/_quarantine_adc_lane_on` and should not appear here |\n")
    from _common import FOREIGN
    if FOREIGN:
        L.append("## Foreign logger folders (ignored)\n")
        L.append("Session folders under a MAC folder that is NOT the animal's registered logger (a spare logger's card downloaded into the wrong animal folder). "
                 "They are excluded from every table until moved out of the raw tree (e.g. to `<root>/_other_loggers/<MAC>/`).\n")
        for a, mac, s in FOREIGN:
            L.append(f"- `{a}/{mac}/{s.name}`")
        L.append("")
    flagged = [r for r in rows if r.get("field_flag")]
    if flagged:
        L.append("## Field-flagged sessions (indexed, excluded from coverage and analysis)\n")
        for r in flagged:
            L.append(f"- {r['animal']} `{r['session']}` ({r.get('duration_hms', '')}): {r['field_flag']}")
        L.append("")
    adc = [r for r in rows if r.get("adc_lane") == "ON"]
    if adc:
        L.append("## ADC-lane-ON sessions still in the raw tree (UNUSABLE - quarantine them)\n")
        for r in adc:
            L.append(f"- {r['animal']} `{r['session']}` ({r.get('duration_hms', '')}): run `python ephys/quarantine_adc_sessions.py --cohort <key> --move`")
        L.append("")
    bounded = [r for r in rows if r.get("valid_until")]
    if bounded:
        L.append("## Sessions with a validity boundary (neural signal ended before the Stop)\n")
        for r in bounded:
            L.append(f"- {r['animal']} `{r['session']}` ({r.get('duration_hms', '')}): valid until {r['valid_until']}; {r.get('notes', '')}")
        L.append("")
    L.append("## Per-animal summary\n")
    L.append("| animal | logger MAC | sessions | hours offloaded | firmware seen | recovery.bin (GB) |\n|---|---|---|---|---|---|")
    for a in sorted(animals):
        d = animals[a]
        fw = ", ".join(f"FM{f}" for f in sorted(d["firmware"])) or "—"
        L.append(f"| {a} | {d['logger_mac'] or '—'} | {d['n_sessions']} | {d['hours']:.2f} | {fw} | {d['recovery_bin_gb'] or '—'} |")
    L.append("")
    n_need = sum(1 for r in rows if r.get("deglitch_required") is True)
    n_clean = sum(1 for r in rows if r.get("deglitch_required") is False)
    L.append(f"**{len(rows)} sessions indexed: {n_need} require de-glitching (firmware < FM{clean_min}), {n_clean} flagged clean by firmware.**\n")
    L.append("## Sessions\n")
    L.append("| animal | session | start (local) | end (local) | dur | GB | FW | deglitch? | measured (worst window) | regime by window | ticks/s | removable | raw std | noise µV | bad ch cand. | notes |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        L.append(f"| {r['animal']} | `{r['session']}` | {r.get('start_local','')} | {r.get('end_local','')} | {r.get('duration_hms','')} | {r.get('amplifier_gb','')} | "
                 f"FM{r.get('firmware','?')} | {'YES' if r.get('deglitch_required') is True else ('no' if r.get('deglitch_required') is False else '?')} | "
                 f"{r.get('measured_verdict','')} | {r.get('regime_by_window','')} | {r.get('ticks_per_s','')} | {r.get('tick_removal_frac','')} | {r.get('raw_std_median_adc','')} | {r.get('noise_uV_median','')} | "
                 f"{r.get('bad_channel_candidates','')} | {r.get('notes','')} |")
    L.append("")
    L.append("## How to use\n")
    L.append("1. Never analyse a `deglitch? = YES` session from its raw `amplifier.dat`; stage it first: "
             f"`python ephys/stage_session.py --cohort {cohort} --animal <SFxx> --session <folder>` (de-glitches by the firmware gate, writes a clean working copy off-repo).")
    L.append("2. Sort from the staged copy: `python ephys/run_sort_session.py --cohort " + cohort + " --animal <SFxx> --session <folder>`.")
    L.append("3. When FM65 sessions arrive, re-run this index; their `measured_verdict` is the evidence that they are clean.")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--raw-root", default=None, help="override raw_data_roots.analysis_pc.ephys")
    ap.add_argument("--probe-seconds", type=float, default=30.0, help="length of each measured glitch probe window (0 = skip)")
    ap.add_argument("--probe-windows", type=int, default=5, help="number of probe windows spread over each file (worst case is reported)")
    ap.add_argument("--no-mirror", action="store_true", help="do not write SESSION_INDEX.{csv,md} next to the data")
    ap.add_argument("--out-dir", default=None, help="override results/<cohort>/ephys_spikes/reports")
    ap.add_argument("--workers", type=int, default=1, help="parallel session probes (CPU-bound filtering; 8 is a good value on this PC)")
    a = ap.parse_args()
    cfg = ephys_block(a.cohort)
    raw = raw_ephys_root(a.cohort, a.raw_root)
    if not raw.is_dir():
        raise SystemExit(f"raw root not found: {raw}")
    print(f"indexing {raw} (probe {a.probe_windows} x {a.probe_seconds:g} s per session)")
    rows, details, animals = build_index(raw, cfg, probe_seconds=a.probe_seconds, probe_windows=a.probe_windows, workers=a.workers)
    out_dir = Path(a.out_dir) if a.out_dir else report_dir(a.cohort, cfg.get("direction", "ephys_spikes"))
    mirror = None
    if not a.no_mirror:
        ar = cfg.get("analysis_root")
        mirror = (Path(ar) / "index") if ar else raw   # never inside a raw session folder; the cohort's analysis folder when declared
    out = write_outputs(rows, details, animals, cohort=a.cohort, cfg=cfg, raw_root=raw, out_dir=out_dir,
                        mirror_dir=mirror, probe_seconds=a.probe_seconds)
    for k, v in out.items():
        print(f"{k:7s} {v}")
    print(f"{len(rows)} sessions; deglitch required: {sum(1 for r in rows if r.get('deglitch_required') is True)}")


if __name__ == "__main__":
    main()
