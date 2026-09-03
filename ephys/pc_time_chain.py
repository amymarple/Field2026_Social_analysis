"""Field-PC-time anchor fits per session, day-wrap aware, WITH chaining of adjacent sessions' anchors.

What is on the card (verified by reading it): analogin.dat = 16 lanes at fs/16; lanes 14/15 hold one packed word
[delay_ms:12 | pc_ms mod 2^20 : 20] that CHANGES once per console sync exchange (~5 s while BLE-connected). pc_ms is
the FIELD PC's milliseconds-of-day. Two facts decide how it must be decoded (both measured on this cohort by comparing
the embedded value with the logger's own RTC start, CE_params.bin = folder name, at every anchor):

  1. DAY WRAP. pc_ms wraps at 86,400,000 at local midnight, and 86,400,000 mod 2^20 = 416,768 ms. A session that
     crosses midnight therefore sees its post-midnight anchors 416.77 s "early" relative to a continuous line. Every
     long night session shows exactly this (-413.6 ... -417.5 s at the end cluster, +0.1 ... +0.6 s again at the next
     session's start). A fit that ignores it either discards the post-midnight anchors or, when it cannot, reports a
     spurious drift (-416.77 s / 6.65 h = -17,400 ppm, the SF07 10_20260901_234332.691 case). Model used here:
        embedded(t) = ((base_ms + off_ms + b * t * 1000) mod 86,400,000) mod 2^20
     with base_ms = RTC start ms-of-day from the folder name, off_ms = field-PC minus logger-RTC offset (a few s), and
     b the sample-clock rate ratio. Each anchor is first unwrapped to continuous PC ms (valid while |off + drift| < 8.7 min),
     then a plain robust line is fitted, so no modulo arithmetic is left in the fit.
  2. DELAY WORD. Adding the 12-bit delay to pc_ms (as the reference generator does) makes anchors with a large delay word
     (700-2,600 ms) disagree with delay-0 anchors of the same connection by exactly that amount; the raw pc_ms agrees with
     the logger RTC to +/-0.7 s in every case checked. The delay word is therefore NOT added by default (--add-delay to
     reproduce the reference behaviour); it is still reported as a link-quality indicator.

Chaining (the round protocol): a session's START is always well anchored (Resync -> 30-s guard -> Start -> 30 s), its END
often not. The RTC keeps running across a stop->start, so the NEXT session's start anchors are mapped onto this session's
axis, t_this = (RTC_start_next - RTC_start_this) + t_next, and used as end anchors ("borrowed"). Their cost is the RTC-vs-
ADC discrepancy accumulated over the session (field 'dev' drift, budget CHAIN_UNC_MS = 1500 ms), a systematic offset, so a
chained drift is reported with uncertainty CHAIN_UNC_MS / span. Chains are only made across gaps <= 300 s (a round with a
Resync re-sets the RTC and breaks the chain; such boundaries show up as a jump in start_vs_prev_ms).

Per session:
    n_anchors, n_native_start / n_native_end (within 120 s of start / end), n_borrowed, borrowed_from
    off_start_ms                 field-PC minus logger-RTC at the session start (from the start cluster; ~the field 'dev')
    drift_native_ppm +/- sem     robust line through native anchors (needs anchors at both ends and >= 10 kept)
    native_residual_ms           RMS residual of the native fit (BLE precision, 10-100 ms expected)
    drift_chained_ppm +/- unc    slope from the start cluster to the borrowed cluster; unc = 1500 ms / span
    start_vs_prev_ms / end_vs_next_ms   this session's cluster vs the neighbouring session's cluster, RTC-chained
                                 (|value| <= ~2 s: agree within the RTC budget; larger: an RTC re-set lies between them)
    verdict   OK-native | OK-chained | one-end-only | inconsistent | no-anchors | corrupt

Usage:  python ephys/pc_time_chain.py --cohort 2026c [--animals SF07 ...] [--add-delay]
Writes results/<cohort>/ephys_spikes/reports/ephys_spikes_pc_time_chain_<cohort>.{csv,md}
"""
from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from _common import ephys_block, git_commit, iter_raw_sessions, parse_session_name, raw_ephys_root, report_dir, utc_now_iso
from wild_ce_params import parse_ce_params

M = 1 << 20                 # packed pc_ms modulo (ms) = 17.48 min
DAY_MS = 86_400_000
LANES = 16
END_WINDOW_S = 120.0
BORROW_MAX_GAP_S = 300.0
CHAIN_UNC_MS = 1500.0
NEIGHBOUR_AGREE_MS = 2000.0
MAD_SCALE = 6.0 * 1.4826
RESID_FLOOR_MS = 150.0
CORRUPT_FACTOR = 10.0
CADENCE_S = 5.0
MIN_CLUSTER = 3
MIN_NATIVE_KEPT = 10


def decode_anchors(session_dir: Path, fs: float, add_delay: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    an = np.memmap(session_dir / "analogin.dat", dtype=np.uint16, mode="r")
    n_misc = an.shape[0] // LANES
    m = np.asarray(an[: n_misc * LANES]).reshape(n_misc, LANES)
    word = m[:, 14].astype(np.uint32) | (m[:, 15].astype(np.uint32) << 16)
    chg = np.where(np.diff(word) != 0)[0] + 1
    pc = (word[chg] & (M - 1)).astype(np.float64)
    delay = ((word[chg] >> 20) & 0xFFF).astype(np.float64)
    t = chg.astype(np.float64) * LANES / fs
    keep = (pc > 0) | (delay > 0)
    pc, delay, t = pc[keep], delay[keep], t[keep]
    if add_delay:
        pc = (pc + delay) % M
    return t, pc, delay


def unwrap_to_continuous(t: np.ndarray, pc: np.ndarray, base_ms: float) -> np.ndarray:
    """Continuous field-PC ms (relative to the session-start day) for each anchor, assuming |offset + drift| < 8.7 min."""
    nominal = base_ms + t * 1000.0
    emb = np.mod(np.mod(nominal, DAY_MS), M)
    resid = ((pc - emb + M / 2) % M) - M / 2
    return nominal + resid


def robust_line(t: np.ndarray, y_ms: np.ndarray) -> dict | None:
    """Robust least squares y = a + b*t*1000 with MAD gating (150-ms floor). y is continuous PC ms minus base."""
    n = t.size
    if n < 2:
        return None
    keep = np.ones(n, dtype=bool)
    a = float(np.median(y_ms - t * 1000.0)); b = 1.0
    for _ in range(8):
        resid = y_ms - (a + b * t * 1000.0)
        mad = float(np.median(np.abs(resid[keep] - np.median(resid[keep])))) if keep.sum() > 2 else 0.0
        gate = max(RESID_FLOOR_MS, MAD_SCALE * mad)
        new_keep = np.abs(resid - np.median(resid[keep])) <= gate if keep.sum() > 2 else np.abs(resid) <= gate
        if new_keep.sum() < 2:
            break
        A = np.vstack([np.ones(int(new_keep.sum())), t[new_keep] * 1000.0]).T
        coef, *_ = np.linalg.lstsq(A, y_ms[new_keep], rcond=None)
        a, b = float(coef[0]), float(coef[1])
        if np.array_equal(new_keep, keep):
            keep = new_keep
            break
        keep = new_keep
    resid = y_ms - (a + b * t * 1000.0)
    rms = float(np.sqrt(np.mean(resid[keep] ** 2))) if keep.any() else float("nan")
    tk = t[keep] * 1000.0
    sem = float(np.sqrt(np.sum(resid[keep] ** 2) / max(1, keep.sum() - 2) / max(1e-9, np.sum((tk - tk.mean()) ** 2)))) if keep.sum() > 2 else float("nan")
    return {"a": a, "b": b, "keep": keep, "n_kept": int(keep.sum()), "rms_ms": rms, "drift_ppm": (b - 1.0) * 1e6, "drift_sem_ppm": sem * 1e6}


def folder_ms_of_day(name: str) -> float:
    meta = parse_session_name(name)
    s = meta["start"]
    return ((s.hour * 60 + s.minute) * 60 + s.second) * 1000.0 + s.microsecond / 1000.0


def analyse_animal(animal: str, sessions: list[tuple[Path, dict]], fs: float, add_delay: bool, verbose: bool = True) -> list[dict]:
    sessions = sorted(sessions, key=lambda s: s[1]["start"])
    dec = []
    for sdir, meta in sessions:
        ns = os.path.getsize(sdir / "amplifier.dat") // 128
        dur = ns / fs
        t, pc, delay = decode_anchors(sdir, fs, add_delay) if (sdir / "analogin.dat").exists() else (np.zeros(0),) * 3
        corrupt = t.size > CORRUPT_FACTOR * max(1.0, dur / CADENCE_S)
        base = folder_ms_of_day(sdir.name)
        y = unwrap_to_continuous(t, pc, base) - base if (t.size and not corrupt) else np.zeros(0)   # continuous PC ms minus RTC start
        dec.append({"name": sdir.name, "start": meta["start"], "dur": dur, "t": t, "y": y, "delay": delay, "corrupt": corrupt})
        if verbose:
            print(f"  {animal} {sdir.name}: {t.size} anchors, {dur / 3600:.2f} h{'  CORRUPT' if corrupt else ''}", flush=True)

    rows = []
    for i, s in enumerate(dec):
        t, y, delay, dur = s["t"], s["y"], s["delay"], s["dur"]
        sel_s = t <= END_WINDOW_S
        sel_e = t >= dur - END_WINDOW_S
        n_start, n_end = int(sel_s.sum()), int(sel_e.sum())
        off_start = float(np.median(y[sel_s] - t[sel_s] * 1000.0)) if (n_start and not s["corrupt"]) else float("nan")
        off_end = float(np.median(y[sel_e] - t[sel_e] * 1000.0)) if (n_end and not s["corrupt"]) else float("nan")
        delay_start = float(np.median(delay[sel_s])) if n_start else float("nan")
        nxt = dec[i + 1] if i + 1 < len(dec) else None
        prv = dec[i - 1] if i > 0 else None
        gap_next = ((nxt["start"] - s["start"]).total_seconds() - dur) if nxt else None
        gap_prev = ((s["start"] - prv["start"]).total_seconds() - prv["dur"]) if prv else None

        # neighbour clusters mapped onto this session's axis (continuous ms relative to THIS session's RTC start)
        def mapped_next():
            if nxt is None or nxt["corrupt"] or not nxt["t"].size:
                return None
            off = (nxt["start"] - s["start"]).total_seconds()
            sel = nxt["t"] <= END_WINDOW_S
            if not sel.any():
                return None
            return off + nxt["t"][sel], nxt["y"][sel] + off * 1000.0

        def mapped_prev():
            if prv is None or prv["corrupt"] or not prv["t"].size:
                return None
            off = (s["start"] - prv["start"]).total_seconds()
            sel = prv["t"] >= prv["dur"] - END_WINDOW_S
            if not sel.any():
                return None
            return prv["t"][sel] - off, prv["y"][sel] - off * 1000.0

        end_vs_next = start_vs_prev = ""
        mn, mp = mapped_next(), mapped_prev()
        if mn is not None and n_end >= MIN_CLUSTER and not s["corrupt"]:
            end_vs_next = f"{float(np.median(mn[1] - mn[0] * 1000.0)) - off_end:+.0f}"
        if mp is not None and n_start >= MIN_CLUSTER and not s["corrupt"]:
            start_vs_prev = f"{off_start - float(np.median(mp[1] - mp[0] * 1000.0)):+.0f}"

        # native fit
        fit_native = None
        if not s["corrupt"] and n_start >= MIN_CLUSTER and n_end >= MIN_CLUSTER:
            f = robust_line(t, y)
            if f is not None and f["n_kept"] >= MIN_NATIVE_KEPT and (t[f["keep"]].max() - t[f["keep"]].min()) >= 0.8 * dur:
                fit_native = f

        # chained fit
        borrowed_from, drift_chain, chain_unc, span = "", "", "", 0.0
        if not s["corrupt"] and fit_native is None:
            if n_end < MIN_CLUSTER and n_start >= MIN_CLUSTER and mn is not None and gap_next is not None and 0 <= gap_next <= BORROW_MAX_GAP_S:
                tb, yb = mn
                span = float(np.median(tb))
                b = float(np.median((yb - off_start) / (tb * 1000.0)))
                borrowed_from = f"next:{tb.size}"
            elif n_start < MIN_CLUSTER and n_end >= MIN_CLUSTER and mp is not None and gap_prev is not None and 0 <= gap_prev <= BORROW_MAX_GAP_S:
                tb, yb = mp
                a_b = float(np.median(yb - tb * 1000.0))
                span = float(np.median(t[sel_e]) - np.median(tb))
                b = float(np.median((y[sel_e] - a_b) / (t[sel_e] * 1000.0))) if span > 0 else None
                borrowed_from = f"prev:{tb.size}"
            else:
                b = None
            if b is not None and span > 0:
                drift_chain = round((b - 1.0) * 1e6, 1)
                chain_unc = round(CHAIN_UNC_MS / span * 1e3, 1)

        if s["corrupt"]:
            verdict = "corrupt"
        elif t.size < 2:
            verdict = "no-anchors"
        elif fit_native is not None:
            verdict = "OK-native" if (abs(fit_native["drift_ppm"]) <= 200 and fit_native["rms_ms"] <= 150) else "inconsistent"
        elif drift_chain != "":
            verdict = "OK-chained" if abs(float(drift_chain)) <= 200 + float(chain_unc) else "inconsistent"
        else:
            verdict = "one-end-only"

        rows.append({
            "animal": animal, "session": s["name"], "start": s["start"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3], "duration_s": round(dur, 3),
            "crosses_midnight": bool(folder_ms_of_day(s["name"]) + dur * 1000.0 >= DAY_MS),
            "n_anchors": int(t.size), "n_native_start": n_start, "n_native_end": n_end,
            "start_delay_ms": round(delay_start) if np.isfinite(delay_start) else "",
            "off_start_ms": round(off_start) if np.isfinite(off_start) else "",
            "n_borrowed": int(borrowed_from.split(":")[1]) if borrowed_from else 0, "borrowed_from": borrowed_from,
            "gap_to_next_s": "" if gap_next is None else round(gap_next, 1),
            "n_kept": fit_native["n_kept"] if fit_native else "",
            "drift_native_ppm": "" if fit_native is None else round(fit_native["drift_ppm"], 1),
            "drift_native_sem_ppm": "" if fit_native is None else round(fit_native["drift_sem_ppm"], 1),
            "native_residual_ms": "" if fit_native is None else round(fit_native["rms_ms"], 1),
            "drift_chained_ppm": drift_chain, "chain_unc_ppm": chain_unc, "chain_span_s": round(span, 1),
            "start_vs_prev_ms": start_vs_prev, "end_vs_next_ms": end_vs_next, "verdict": verdict,
        })
    return rows


def render_md(rows: list[dict], cohort: str, add_delay: bool) -> str:
    L = [f"# Field-PC-time fits, day-wrap aware, with chained anchors, cohort `{cohort}`\n",
         f"Generated {utc_now_iso()} by `ephys/pc_time_chain.py` (git {git_commit()}); delay word {'ADDED' if add_delay else 'NOT added'}. "
         "Anchors decoded from `analogin.dat` lanes 14/15 and unwrapped against the logger RTC start (folder name) with the 86,400,000-ms day wrap "
         "and the 2^20-ms packing both modelled. A session without an end cluster borrows the NEXT session's start cluster through the RTC "
         "(round protocol: Resync -> 30-s guard -> Start -> 30 s; mid-span stop->start) and carries the RTC-chain uncertainty (1.5 s / span). "
         "`start_vs_prev` / `end_vs_next` compare a session's own cluster with the neighbouring session's cluster (RTC-chained, ms): within about 2 s = agree; "
         "larger = an RTC re-set (Resync) lies between them. Definitions in the script docstring.\n",
         "| animal | session | dur h | midnight | anchors | start/end | start delay ms | PC−RTC at start ms | kept | drift native ppm ± sem | resid ms | borrowed | gap→next s | drift chained ppm ± unc | start vs prev ms | end vs next ms | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        nat = f"{r['drift_native_ppm']} ± {r['drift_native_sem_ppm']}" if r["drift_native_ppm"] != "" else ""
        ch = f"{r['drift_chained_ppm']} ± {r['chain_unc_ppm']}" if r["drift_chained_ppm"] != "" else ""
        L.append(f"| {r['animal']} | `{r['session']}` | {r['duration_s'] / 3600:.2f} | {'yes' if r['crosses_midnight'] else ''} | {r['n_anchors']} | {r['n_native_start']}/{r['n_native_end']} | "
                 f"{r['start_delay_ms']} | {r['off_start_ms']} | {r['n_kept']} | {nat} | {r['native_residual_ms']} | {r['n_borrowed']} {r['borrowed_from']} | {r['gap_to_next_s']} | {ch} | "
                 f"{r['start_vs_prev_ms']} | {r['end_vs_next_ms']} | {r['verdict']} |")
    long = [r for r in rows if r["duration_s"] >= 3600]
    cnt = defaultdict(lambda: [0, 0.0])
    for r in long:
        cnt[r["verdict"]][0] += 1
        cnt[r["verdict"]][1] += r["duration_s"] / 3600
    L.append("\n## Sessions >= 1 h by verdict\n\n| verdict | sessions | hours |\n|---|---|---|")
    for k, (n, h) in sorted(cnt.items(), key=lambda kv: -kv[1][1]):
        L.append(f"| {k} | {n} | {h:.1f} |")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--raw-root", default=None)
    ap.add_argument("--animals", nargs="*", default=None)
    ap.add_argument("--add-delay", action="store_true", help="add the 12-bit delay word to pc_ms (reference-generator behaviour; NOT recommended, see docstring)")
    ap.add_argument("--suffix", default="")
    ap.add_argument("--write-pc-time", default=None, metavar="OUT_ROOT",
                    help="also write <OUT_ROOT>/<SFxx>/<session>/pc_time.dat (uint32 field-PC ms-of-day per amplifier sample, the console "
                         "format) + pc_time_fit.json for every session with an OK-native / OK-chained / start-only fit")
    ap.add_argument("--default-drift-ppm", type=float, default=None,
                    help="drift used for start-cluster-only sessions when writing pc_time.dat (default: median of the animal's OK fits)")
    a = ap.parse_args()
    cfg = ephys_block(a.cohort)
    raw = raw_ephys_root(a.cohort, a.raw_root)
    fs = float(cfg.get("sampling_rate_hz", 20000))
    per_animal: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for animal, mac, sdir in iter_raw_sessions(raw, cfg.get("session_glob", "*")):
        key = f"SF{int(animal[2:]):02d}" if animal.upper().startswith("SF") and animal[2:].isdigit() else animal
        if a.animals and key not in {x.upper() for x in a.animals}:
            continue
        per_animal[key].append((sdir, parse_session_name(sdir.name)))
    rows: list[dict] = []
    for animal in sorted(per_animal):
        cp = parse_ce_params(per_animal[animal][0][0])
        rows.extend(analyse_animal(animal, per_animal[animal], float(cp.fs or fs), a.add_delay))
    rd = report_dir(a.cohort)
    csv_path = rd / f"ephys_spikes_pc_time_chain_{a.cohort}{a.suffix}.csv"
    md_path = rd / f"ephys_spikes_pc_time_chain_{a.cohort}{a.suffix}.md"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    md_path.write_text(render_md(rows, a.cohort, a.add_delay), encoding="utf-8")
    print(f"csv -> {csv_path}\nmd  -> {md_path}")
    if a.write_pc_time:
        n = write_pc_time_files(rows, per_animal, Path(a.write_pc_time), fs, a.default_drift_ppm)
        print(f"pc_time.dat written for {n} sessions under {a.write_pc_time}")


def write_pc_time_files(rows: list[dict], per_animal: dict, out_root: Path, fs_default: float, default_drift_ppm: float | None) -> int:
    """Write pc_time.dat (uint32 ms-of-day per amplifier sample) + pc_time_fit.json per usable session.

    Model: pc_ms(sample i) = (base_ms + off_ms + (1 + drift) * i / fs * 1000) mod 86,400,000, where base_ms is the RTC
    start ms-of-day (folder name), off_ms the start-cluster field-PC-minus-RTC offset, drift from the native or chained
    fit, or the animal's median OK drift (or --default-drift-ppm) for start-cluster-only sessions."""
    import json
    by = {(r["animal"], r["session"]): r for r in rows}
    ok_drift = defaultdict(list)
    for r in rows:
        if r["verdict"] == "OK-native":
            ok_drift[r["animal"]].append(float(r["drift_native_ppm"]))
        elif r["verdict"] == "OK-chained":
            ok_drift[r["animal"]].append(float(r["drift_chained_ppm"]))
    n = 0
    for animal, sess in per_animal.items():
        for sdir, meta in sess:
            r = by.get((animal, sdir.name))
            if r is None or r["verdict"] not in ("OK-native", "OK-chained", "one-end-only") or r["off_start_ms"] == "":
                continue
            if r["verdict"] == "OK-native":
                drift, src = float(r["drift_native_ppm"]), "native fit"
            elif r["verdict"] == "OK-chained":
                drift, src = float(r["drift_chained_ppm"]), f"chained fit ({r['borrowed_from']})"
            else:
                pool = ok_drift.get(animal) or [x for v in ok_drift.values() for x in v]
                if default_drift_ppm is not None:
                    drift, src = default_drift_ppm, "--default-drift-ppm"
                elif pool:
                    drift, src = float(np.median(pool)), f"median of {len(pool)} OK fits ({'this animal' if ok_drift.get(animal) else 'cohort'})"
                else:
                    continue
            cp = parse_ce_params(sdir)
            fs = float(cp.fs or fs_default)
            ns = os.path.getsize(sdir / "amplifier.dat") // (2 * (cp.n_channels or 64))
            base = folder_ms_of_day(sdir.name)
            off = float(r["off_start_ms"])
            out = out_root / animal / sdir.name
            out.mkdir(parents=True, exist_ok=True)
            with open(out / "pc_time.dat", "wb") as f:
                step = 5_000_000
                for a0 in range(0, ns, step):
                    i = np.arange(a0, min(ns, a0 + step), dtype=np.float64)
                    ms = np.mod(base + off + (1.0 + drift * 1e-6) * i / fs * 1000.0, DAY_MS)
                    np.floor(ms).astype(np.uint32).tofile(f)
            (out / "pc_time_fit.json").write_text(json.dumps({
                "animal": animal, "session": sdir.name, "n_samples": int(ns), "fs": fs, "rtc_start_ms_of_day": base, "offset_ms": off,
                "drift_ppm": drift, "drift_source": src, "verdict": r["verdict"], "n_anchors": r["n_anchors"], "native_residual_ms": r["native_residual_ms"],
                "model": "pc_ms(i) = (rtc_start_ms_of_day + offset_ms + (1 + drift_ppm*1e-6) * i / fs * 1000) mod 86400000",
                "note": "field-PC ms-of-day of the day the session started; a session crossing midnight wraps to 0 at the field-PC midnight",
                "written_utc": utc_now_iso(), "script": "ephys/pc_time_chain.py --write-pc-time", "git": git_commit(),
            }, indent=2), encoding="utf-8")
            n += 1
    return n


if __name__ == "__main__":
    main()
