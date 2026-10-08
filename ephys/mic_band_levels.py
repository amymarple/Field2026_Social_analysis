r"""Per-second band levels of the in-house UltraMic recordings (MIC01 384 kHz, MIC02 250 kHz), on the field-PC clock.
Plan: implementation_plan/2026-10-07-sleep-internal-schedule.md, section 4 D (environmental disturbance vs animal noise).

Definitions:
  file span     start / end from the file name (<MIC>_<date>_<HH-MM-SS>_to_<HH-MM-SS>.wav, field-PC time); an open file
                (no _to_) spans its sample count at the nominal rate. The samples are spread linearly over the span:
                rate_eff = n_samples / span_s (MIC01 hours hold ~3600.76 s at the nominal 384 kHz, i.e. the mic clock
                runs ~210 ppm fast against the PC clock).
                Exception (timing = "end_anchored"): when rate_eff differs from the nominal rate by > 0.1 % (e.g. the
                first file after a capture start holds ~10 % fewer samples than its name span, because the device
                starts delivering after the file is created), the samples are NOT stretched: they run at the nominal
                rate x the mic's typical clock ratio (CLOCK_RATIO) and END at the file's end time (the rollover /
                rename is the reliable clock point); seconds before the first sample are absent.
  frame         20 ms of samples (Hann window, mean removed); power spectrum P(f) = |rfft|^2 normalised so that a
                full-scale sine reads 0 dB.
  band level    for band b = [lo, hi) Hz: per frame p_b = sum of P(f) over the band; per PC second k (frames whose centre
                falls in [k, k+1)):
                  mean_b(k) = 10 log10(mean over frames of p_b)    (an equivalent level, dB re full scale)
                  max_b(k)  = 10 log10(max over frames of p_b)     (the loudest 20-ms frame: transients, knocks, calls)
  bands         b0 50-500 Hz (machinery, thumps), b1 0.5-4 kHz, b2 4-20 kHz (rustle, scratching), b3 20-40 kHz
                (22-kHz rat calls), b4 40-100 kHz (50-kHz rat calls). The lowest bin is 50 Hz (20-ms frames).
  camera audio  CH01-CH08 MP4s (<CH>_<date>_<HH-MM-SS>_to_<HH-MM-SS>.mp4): the first audio stream (AAC, 16 kHz mono) is
                decoded by ffmpeg ($FFMPEG or `ffmpeg`) ON ITS TIMESTAMPS (aresample async: gaps in the stream are filled
                with zeros at their place; timing = "pts", anchored at the file start, never stretched) and handled the
                same way with bands c0 50-500 Hz, c1 0.5-2 kHz, c2 2-8 kHz (the camera mics stop at 8 kHz); the outdoor
                reference for the in-house mics. (Without the timestamps, 10-min holes in some hours shifted the rest.)
  gaps          all-zero 20-ms frames (filled gaps, dropouts) are left out; a second without any other frame is absent
                from the output (extract_log: missing_s).
  timing_err_s  per file, the bound on the timing error inside it: |n / (rate x CLOCK_RATIO) - span| for stretched WAVs
                (samples missing / extra against the device's typical clock, spread linearly), |n / rate - span| for
                MP4s; WAV files hold no timestamps, so a dropout inside one cannot be placed.
  These are relative levels of one microphone; the devices are not calibrated to each other. Nothing here labels a
  sound as external or animal-made.

Usage:
  python ephys/mic_band_levels.py --files <wav> [<wav> ...] --out <dir>        # one CSV.gz per file
  python ephys/mic_band_levels.py --root <3rd_rat root> --mics MIC01 MIC02 --dates 2026-09-06 [...] --out <dir> --workers N
  python ephys/mic_band_levels.py --selftest
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import wave
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

BANDS = [("b0", 50, 500), ("b1", 500, 4000), ("b2", 4000, 20000), ("b3", 20000, 40000), ("b4", 40000, 100000)]
CAM_BANDS = [("c0", 50, 500), ("c1", 500, 2000), ("c2", 2000, 8000)]     # camera audio: AAC 16 kHz mono (0-8 kHz)
CAM_RATE = 16000
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
CLOCK_RATIO = {"MIC01": 384081.067 / 384000, "MIC02": 250001.389 / 250000}   # measured on full hours, 2026-09-06 10:00
ANOMALY = 1e-3
FRAME_S = 0.02
CHUNK_S = 60
NAME_RE = re.compile(r"((?:MIC|CH)\d\d)_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})(?:_to_(\d{2}-\d{2}-\d{2}))?\.(wav|mp4)$")


def parse_name(p: Path):
    m = NAME_RE.search(p.name)
    if not m:
        raise ValueError(f"unexpected file name {p.name}")
    mic, day, t0, t1, _ = m.groups()
    start = pd.Timestamp(f"{day} {t0.replace('-', ':')}")
    end = None
    if t1:
        end = pd.Timestamp(f"{day} {t1.replace('-', ':')}")
        if end <= start:
            end += pd.Timedelta(days=1)
    return mic, start, end


def wav_info(p: Path):
    with wave.open(str(p), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError(f"{p.name}: expected mono int16")
        rate, n = w.getframerate(), w.getnframes()
    with open(p, "rb") as f:                       # locate the data chunk for np.memmap
        f.seek(12)
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                raise ValueError(f"{p.name}: no data chunk")
            cid, size = hdr[:4], int.from_bytes(hdr[4:], "little")
            if cid == b"data":
                return rate, n, f.tell()
            f.seek(size + (size & 1), 1)


def load_samples(p: Path):
    """int16 samples + their rate: a WAV is memory-mapped; an MP4's first audio stream is decoded by ffmpeg (mono, 16 kHz,
    the cameras' native rate; nothing is resampled for CH01-CH08)."""
    if p.suffix.lower() == ".wav":
        rate, n, off = wav_info(p)
        return np.memmap(p, dtype="<i2", mode="r", offset=off, shape=(n,)), rate
    cmd = [FFMPEG, "-v", "error", "-nostdin", "-i", str(p), "-vn", "-map", "0:a:0", "-af", "aresample=async=1:first_pts=0",
           "-ac", "1", "-ar", str(CAM_RATE), "-f", "s16le", "-"]   # timestamp gaps -> filled with zeros at their place
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<i2"), CAM_RATE


def band_levels(p: Path) -> pd.DataFrame:
    mic, start, end = parse_name(p)
    x, rate = load_samples(p)
    n = len(x)
    bands = CAM_BANDS if mic.startswith("CH") else BANDS
    span = (end - start).total_seconds() if end is not None else n / rate
    rate_eff = n / span
    timing, t_first = "stretched", 0.0               # t_first = PC seconds after `start` of the first sample
    if p.suffix.lower() == ".mp4":                   # samples on the container's timeline (PTS 0 = file start), gaps filled
        timing, rate_eff = "pts", float(rate)
        span = max(span, n / rate)
    elif end is not None and abs(rate_eff / rate - 1) > ANOMALY:
        timing = "end_anchored"
        rate_eff = rate * CLOCK_RATIO.get(mic, 1.0)
        t_first = span - n / rate_eff
    # bound on the timing error inside the file: samples missing / extra against the device's typical clock
    timing_err = abs(n / (rate * CLOCK_RATIO.get(mic, 1.0)) - span) if (end is not None and timing == "stretched") else         (abs(n / rate - (end - start).total_seconds()) if (end is not None and timing == "pts") else np.nan)
    L = int(round(FRAME_S * rate))
    win = np.hanning(L).astype(np.float32)
    freqs = np.fft.rfftfreq(L, 1.0 / rate)
    sel = [(nm, (freqs >= lo) & (freqs < hi)) for nm, lo, hi in bands]
    norm = 32768.0 ** 2 * L * float((win.astype(np.float64) ** 2).sum()) / 4   # band power of a full-scale sine -> 0 dB
    n_sec = int(np.floor(span))
    acc_sum = np.zeros((n_sec, len(bands)))
    acc_max = np.full((n_sec, len(bands)), -np.inf)
    acc_n = np.zeros(n_sec, int)
    n_frames_total = n // L
    step = int(CHUNK_S / FRAME_S)
    for f0 in range(0, n_frames_total, step):
        f1 = min(n_frames_total, f0 + step)
        seg = np.asarray(x[f0 * L:f1 * L], dtype=np.float32).reshape(f1 - f0, L)
        nz = np.any(seg != 0, axis=1)                # all-zero frames = filled gaps / dropouts: left out
        seg -= seg.mean(axis=1, keepdims=True)
        P = np.abs(np.fft.rfft(seg * win, axis=1)) ** 2 / norm
        pb = np.stack([P[:, s].sum(axis=1) for _, s in sel], axis=1)
        centre = t_first + ((np.arange(f0, f1) + 0.5) * L) / rate_eff
        k = np.floor(centre).astype(int)
        ok = (k >= 0) & (k < n_sec) & nz
        np.add.at(acc_sum, k[ok], pb[ok])
        np.maximum.at(acc_max, k[ok], pb[ok])
        np.add.at(acc_n, k[ok], 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_db = 10 * np.log10(acc_sum / acc_n[:, None])
        max_db = 10 * np.log10(acc_max)
    df = pd.DataFrame({"t_pc": start + pd.to_timedelta(np.arange(n_sec), unit="s"), "n_frames": acc_n})
    for j, (nm, _, _) in enumerate(bands):
        df[f"{nm}_mean_db"] = np.round(mean_db[:, j], 2)
        df[f"{nm}_max_db"] = np.round(max_db[:, j], 2)
    df.insert(0, "mic", mic)
    df = df[df.n_frames > 0].reset_index(drop=True)  # end-anchored files: no seconds before the first sample
    df.attrs.update({"file": p.name, "rate": rate, "rate_eff": rate_eff, "n_samples": n, "span_s": span, "timing": timing,
                     "t_first_s": t_first, "timing_err_s": timing_err, "missing_s": int(n_sec - len(df))})
    return df


def one_file(job: tuple) -> dict:
    src, out = Path(job[0]), Path(job[1])
    redo = len(job) > 2 and job[2]
    dst = out / f"{src.stem}.csv.gz"
    if dst.exists() and not redo:
        return {"file": src.name, "status": "exists"}
    t0 = time.time()
    try:
        df = band_levels(src)
    except Exception as e:                           # noqa: BLE001 - record and continue
        return {"file": src.name, "status": f"error: {e}"}
    tmp = dst.with_suffix(".tmp.gz")
    df.to_csv(tmp, index=False, compression="gzip")
    tmp.replace(dst)
    a = df.attrs
    return {"file": src.name, "status": "ok", "rate": a["rate"], "rate_eff": round(a["rate_eff"], 3),
            "span_s": a["span_s"], "timing": a["timing"], "t_first_s": round(a["t_first_s"], 2),
            "timing_err_s": round(a["timing_err_s"], 2) if np.isfinite(a["timing_err_s"]) else None, "missing_s": a["missing_s"],
            "n_sec": len(df),
            "secs": round(time.time() - t0, 1)}


def selftest() -> None:
    import tempfile
    rate = 250000
    t = np.arange(rate * 12) / rate
    sig = np.zeros_like(t)
    sig[(t >= 2) & (t < 3)] = 0.5 * np.sin(2 * np.pi * 200 * t[(t >= 2) & (t < 3)])        # b0, second 2
    sig[(t >= 5) & (t < 6)] = 0.5 * np.sin(2 * np.pi * 30000 * t[(t >= 5) & (t < 6)])      # b3, second 5
    sig[(t >= 8.40) & (t < 8.42)] = 0.9 * np.sin(2 * np.pi * 10000 * t[(t >= 8.40) & (t < 8.42)])  # 20-ms click, b2, s 8
    sig += 1e-4 * np.random.default_rng(0).standard_normal(t.size)
    pcm = np.clip(sig * 32767, -32768, 32767).astype("<i2")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "MIC02_2026-09-06_10-00-00_to_10-00-12.wav"
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
            w.writeframes(pcm.tobytes())
        df = band_levels(p)
        # a short file: 10 s of samples whose name spans 12 s -> end-anchored; the tone in sample-second 9 lands in PC s 11
        tt = np.arange(rate * 10) / rate
        s2 = 1e-4 * np.random.default_rng(1).standard_normal(tt.size)
        s2[tt >= 9] += 0.5 * np.sin(2 * np.pi * 200 * tt[tt >= 9])
        p2 = Path(td) / "MIC02_2026-09-06_10-00-00_to_10-00-12.wav"
        p2.unlink()
        with wave.open(str(p2), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
            w.writeframes(np.clip(s2 * 32767, -32768, 32767).astype("<i2").tobytes())
        d2 = band_levels(p2)
        d3 = None
        if shutil.which(FFMPEG):                     # camera path: AAC 16 kHz in an MP4 container
            t16 = np.arange(CAM_RATE * 12) / CAM_RATE
            s3 = 1e-3 * np.random.default_rng(2).standard_normal(t16.size)
            s3[(t16 >= 4) & (t16 < 5)] += 0.5 * np.sin(2 * np.pi * 1000 * t16[(t16 >= 4) & (t16 < 5)])
            s3[(t16 >= 8) & (t16 < 9)] += 0.5 * np.sin(2 * np.pi * 1000 * t16[(t16 >= 8) & (t16 < 9)])
            pr = Path(td) / "tone.raw"
            pr.write_bytes(np.clip(s3 * 32767, -32768, 32767).astype("<i2").tobytes())
            p3 = Path(td) / "CH01_2026-09-06_10-00-00_to_10-00-15.mp4"     # a 3-s timestamp gap after 6 s
            subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "s16le", "-ar", str(CAM_RATE), "-ac", "1", "-i", str(pr),
                            "-af", "asetpts='if(gte(T,6),PTS+3/TB,PTS)'", "-c:a", "aac", "-b:a", "64k", str(p3)], check=True)
            d3 = band_levels(p3).set_index("t_pc")
    if d3 is not None:
        t0 = pd.Timestamp("2026-09-06 10:00:00")
        hi = d3.c1_mean_db[d3.c1_mean_db > -20].index
        cam = {"camera MP4: tone before the gap at second 4": t0 + pd.Timedelta(seconds=4) in hi,
               "camera MP4: tone after the 3-s gap at second 11 (not 8)": t0 + pd.Timedelta(seconds=11) in hi and len(hi) == 2,
               "camera MP4: gap seconds 7-8 absent": all(t0 + pd.Timedelta(seconds=s) not in d3.index for s in (7, 8))}
        for k, v in cam.items():
            print(("PASS " if v else "FAIL ") + k)
        if not all(cam.values()):
            sys.exit(1)
    else:
        print("SKIP camera MP4 check (no ffmpeg)")
    checks = {
        "short file flagged end_anchored": d2.attrs["timing"] == "end_anchored",
        "short file: first sample ~2 s after the name start": abs(d2.attrs["t_first_s"] - 2.0) < 0.01,
        "short file: last-second tone in PC second 11": d2.set_index("t_pc").b0_mean_db.idxmax() == pd.Timestamp("2026-09-06 10:00:11"),
        "12 seconds": len(df) == 12,
        "PC clock from the name": df.t_pc.iloc[0] == pd.Timestamp("2026-09-06 10:00:00"),
        "200 Hz in b0 at second 2": df.b0_mean_db.idxmax() == 2,
        "30 kHz in b3 at second 5": df.b3_mean_db.idxmax() == 5,
        "click: b2 max at second 8": df.b2_max_db.idxmax() == 8,
        "click: max >> mean (transient)": (df.b2_max_db[8] - df.b2_mean_db[8]) > 10,
        "full-scale-ish sine near -6 dB": abs(df.b0_mean_db[2] - 20 * np.log10(0.5)) < 1.0,
        "no leakage of 30 kHz into b1": df.b1_mean_db[5] < df.b3_mean_db[5] - 40,
    }
    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k)
    if not all(checks.values()):
        sys.exit(1)
    print("selftest PASS")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--root")
    ap.add_argument("--mics", nargs="*", default=["MIC01", "MIC02"])
    ap.add_argument("--dates", nargs="*")
    ap.add_argument("--out")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--redo", action="store_true", help="overwrite existing outputs")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    files = [Path(f) for f in (a.files or [])]
    if a.root:
        for d in a.dates or []:
            for m in a.mics:
                files += sorted((Path(a.root) / d / m).glob(f"{m}_*.wav")) + sorted((Path(a.root) / d / m).glob(f"{m}_*.mp4"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(str(f), str(out / parse_name(f)[0]), a.redo) for f in files]
    for j in jobs:
        Path(j[1]).mkdir(parents=True, exist_ok=True)
    rows = []
    if a.workers > 1:
        with ProcessPoolExecutor(a.workers) as ex:
            for r in ex.map(one_file, jobs):
                print(r, flush=True)
                rows.append(r)
    else:
        for j in jobs:
            r = one_file(j)
            print(r, flush=True)
            rows.append(r)
    log = out / f"extract_log_{time.strftime('%Y%m%d_%H%M%S')}.csv"     # one log per run (newest = current outputs)
    pd.DataFrame(rows).to_csv(log, index=False)
    bad = [r for r in rows if str(r.get("status", "")).startswith("error")]
    if bad:                                          # non-zero exit: run_then_store.sh then does NOT copy to storage
        print(f"{len(bad)} file(s) failed; rerun to retry (finished files are skipped)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
