"""Quarantine raw sessions recorded with the WILD ADC ("microphone") lane ON — they carry a 312.5 Hz full-scale pulse train on every
amplifier channel and are unusable (cohorts/<key>.yaml ``ephys.adc_lane``; change_log 2026-09-10).

Three independent signs are checked per session and reported side by side; a session is quarantined when ANY of them says ON:
  1. header:  CE_params.bin byte 28 == 0x08 (the mic-ON config block was active at the Record Start; also sampling_rates[2] == 160000)
  2. window:  the session's [start, end] overlaps a registered ON window (``ephys.adc_lane.on_windows``: mic-ON config write ->
              mic-OFF config write, per logger, from the field's ble_messages) — catches pieces that started with the flag OFF and
              received the ON block while recording (their header still says OFF)
  3. data:    the pulse train itself — in 10-s windows at +60 s, the middle and −60 s: runs of |x| > 5000 ADC on ≥ 32 of 64 channels
              at ≥ 100 pulses/s (a clean session has none)

Usage:
  python ephys/quarantine_adc_sessions.py --cohort 2026c            # report only
  python ephys/quarantine_adc_sessions.py --cohort 2026c --move     # move the flagged sessions to <raw_root>/_quarantine_adc_lane_on/<SFxx>/<MAC>/
Folders whose name starts with "_" are invisible to every ephys tool (``_common.iter_raw_sessions``), so a quarantined session drops out
of the index, chain, coverage and size check (run ``check_offload_sizes.py`` BEFORE moving). Each move is appended to
<raw_root>/_quarantine_adc_lane_on/quarantine_manifest.csv (the record); nothing inside a session folder is ever written.
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from _common import ephys_block, iter_raw_sessions, parse_session_name, raw_ephys_root, utc_now_iso

QUARANTINE_DIR = "_quarantine_adc_lane_on"
PULSE_THR_ADC = 5000.0
MIN_CHANNELS = 32
# Per-channel pulse density varies by logger (2026-09-10 cards: SF09 ~40-100/s, SF10 60-125/s, SF08/SF12 130-180/s) while the
# spike-band noise floor is x7-10 on every lane-ON session (350-570 ADC vs 35-100 clean), so the data test uses either sign.
MIN_PULSES_PER_S = 20.0
MAX_CLEAN_SPIKE_MAD_ADC = 200.0


def _norm_animal(a: str) -> str:
    a = str(a).upper()
    return f"SF{int(a[2:]):02d}" if a.startswith("SF") and a[2:].isdigit() else a


def header_flag(sdir: Path) -> tuple[bool, int, int]:
    """(lane ON per header, byte 28, sampling_rates[2])."""
    p = sdir / "CE_params.bin"
    if not p.exists():
        return False, -1, -1
    b = p.read_bytes()
    b28 = b[28] if len(b) > 28 else -1
    import struct
    sr2 = struct.unpack_from("<I", b, 48)[0] if len(b) >= 52 else -1     # sampling_rates[2] (8 x uint32 from byte 40)
    return (b28 == 0x08) or (sr2 == 160000), b28, sr2


def pulse_metric(sdir: Path, fs: int = 20000, nch: int = 64) -> tuple[float, float, int]:
    """Worst 10-s window of (pulses/s median over channels, fraction of samples in pulses, channels with pulses)."""
    amp = sdir / "amplifier.dat"
    n = os.path.getsize(amp) // (2 * nch)
    if n < fs * 12:
        starts = [0]
    else:
        starts = sorted({fs * 60, max(0, n // 2 - fs * 5), max(0, n - fs * 70)})
    mm = np.memmap(amp, dtype=np.int16, mode="r", shape=(n, nch))
    from scipy import signal as _sig
    sos = _sig.butter(2, [300, 3000], btype="bandpass", fs=fs, output="sos")
    worst = (0.0, 0.0, 0, 0.0)
    for s in starts:
        x = np.asarray(mm[s:min(n, s + fs * 10)], dtype=np.float32)
        if len(x) < fs * 2:
            continue
        x -= np.median(x, axis=0)
        inp = np.abs(x) > PULSE_THR_ADC
        d = np.diff(np.concatenate([np.zeros((1, nch), np.int8), inp.astype(np.int8), np.zeros((1, nch), np.int8)], axis=0), axis=0)
        n_on = (d == 1).sum(axis=0)
        rate = n_on / (len(x) / fs)
        chans = int((rate >= MIN_PULSES_PER_S / 4).sum())
        hp = _sig.sosfilt(sos, x, axis=0)[fs:]
        spk = float(np.median(np.median(np.abs(hp), axis=0) * 1.4826))
        cand = (float(np.median(rate)), float(inp.mean()), chans, spk)
        if cand[0] > worst[0] or cand[3] > worst[3]:
            worst = (max(cand[0], worst[0]), max(cand[1], worst[1]), max(cand[2], worst[2]), max(cand[3], worst[3]))
    return worst


def windows_for(cfg: dict) -> dict[str, list[tuple[datetime, datetime, str]]]:
    out: dict[str, list] = {}
    for w in ((cfg.get("adc_lane") or {}).get("on_windows") or []):
        a = _norm_animal(w["animal"])
        t0 = datetime.strptime(str(w["on_from"])[:19], "%Y-%m-%d %H:%M:%S")
        t1 = datetime.strptime(str(w["off_at"])[:19], "%Y-%m-%d %H:%M:%S") if w.get("off_at") else datetime.max
        out.setdefault(a, []).append((t0, t1, str(w.get("note", ""))))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--raw-root", default=None)
    ap.add_argument("--move", action="store_true", help="actually move the flagged sessions (default: report only)")
    ap.add_argument("--no-data-test", action="store_true", help="skip the pulse-train measurement (header + windows only)")
    a = ap.parse_args()
    cfg = ephys_block(a.cohort)
    root = raw_ephys_root(a.cohort, a.raw_root)
    fs = int(cfg.get("sampling_rate_hz", 20000)); nch = int(cfg.get("n_channels", 64))
    wins = windows_for(cfg)
    qroot = root / QUARANTINE_DIR
    manifest = qroot / "quarantine_manifest.csv"
    flagged = []
    print(f"raw root {root}; ON windows registered for {sorted(wins)}; data test {'off' if a.no_data_test else 'on'}")
    for animal, mac, sdir in iter_raw_sessions(root, cfg.get("session_glob", "*"), cohort=a.cohort):
        meta = parse_session_name(sdir.name)
        if not meta or not (sdir / "amplifier.dat").exists():
            continue
        an = _norm_animal(animal)
        n = os.path.getsize(sdir / "amplifier.dat") // (2 * nch)
        start = meta["start"]; end = start + timedelta(seconds=n / fs)
        hdr, b28, sr2 = header_flag(sdir)
        win_hit = [w for w in wins.get(an, []) if start < w[1] and end > w[0]]
        if not hdr and not win_hit:
            continue                                   # nothing suggests the lane; skip the expensive data test
        rate, frac, chans, spk = (0.0, 0.0, 0, 0.0) if a.no_data_test or n == 0 else pulse_metric(sdir, fs, nch)
        data = (rate >= MIN_PULSES_PER_S and chans >= MIN_CHANNELS) or spk >= MAX_CLEAN_SPIKE_MAD_ADC
        reasons = []
        if hdr: reasons.append(f"header byte28=0x{b28:02x} sr2={sr2}")
        if win_hit: reasons.append("window " + "; ".join(f"{w[0]:%m-%d %H:%M:%S}->{w[1]:%m-%d %H:%M:%S}" for w in win_hit))
        if data: reasons.append(f"data {rate:.0f} pulses/s on {chans} ch, {frac * 100:.0f} % samples, spike-band MAD {spk:.0f} ADC")
        verdict = "ON" if (hdr or data or win_hit) else "off"
        if not data and not a.no_data_test and n > fs * 12:
            reasons.append(f"data test NEGATIVE ({rate:.0f}/s on {chans} ch, spike-band MAD {spk:.0f} ADC) - header/window say ON: check before trusting either")
        flagged.append((animal, mac or "", sdir, start, n / fs / 3600, b28, sr2, rate, frac, chans, verdict, "; ".join(reasons)))
        print(f"  {an} {sdir.name:26} {start:%m-%d %H:%M:%S} {n / fs / 3600:6.2f} h  -> {verdict}: {'; '.join(reasons)}")
    # registered windows with nothing on disk yet
    seen = {(_norm_animal(f[0]), f[3]) for f in flagged}
    for an, ws in wins.items():
        for t0, t1, note in ws:
            if not any(a_ == an and t0 <= s < t1 for a_, s in seen):
                print(f"  {an} window {t0:%m-%d %H:%M:%S}->{t1:%m-%d %H:%M:%S}: no session on disk yet ({note})")
    if not flagged:
        print("nothing to quarantine"); return
    if not a.move:
        print(f"{len(flagged)} session(s) would be moved to {qroot} (re-run with --move)"); return
    qroot.mkdir(parents=True, exist_ok=True)
    new = not manifest.exists()
    with open(manifest, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["moved_utc", "animal", "logger_mac", "session", "start_local", "duration_h", "ce_byte28", "sampling_rate_2", "pulses_per_s", "pulse_sample_frac", "pulse_channels", "verdict", "reasons", "from", "to"])
        for animal, mac, sdir, start, dur, b28, sr2, rate, frac, chans, verdict, reasons in flagged:
            dest_dir = qroot / animal / (mac or "") if mac else qroot / animal
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / sdir.name
            if dest.exists():
                print(f"  SKIP {sdir.name}: already in quarantine"); continue
            shutil.move(str(sdir), str(dest))
            w.writerow([utc_now_iso(), animal, mac, sdir.name, start.strftime("%Y-%m-%d %H:%M:%S"), round(dur, 3), b28, sr2, round(rate, 1), round(frac, 4), chans, verdict, reasons, str(sdir), str(dest)])
            print(f"  moved {sdir.name} -> {dest}")
    print(f"manifest: {manifest}")


if __name__ == "__main__":
    main()
