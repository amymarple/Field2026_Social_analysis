"""Convert raw WILD sessions to Neuroscope LFP (1250 Hz, int16, 64 ch) without staging a 20 kHz copy.

Every session of a cohort gets one ``<session>.lfp`` so that the probe position can be tracked from the LFP over the whole
recording *before* anything is spike-sorted (implementation_plan/2026-09-28-ephys-block-sorting-strategy.md, phase L).
The filter is the lab pipeline's (PreprocessPipeline ``write_lfp``, MATLAB neurocode parity): 5th-order Butterworth low-pass
at 450 Hz, zero-phase (forward-backward), on the RAW signal. Decimation 20 kHz -> 1250 Hz here is ``scipy.signal.resample_poly``
(polyphase FIR, down=16); the pipeline uses spikeinterface's FFT ``resample``. Both remove the band above the 625 Hz output
Nyquist after the 450 Hz pre-filter, so the two differ only in the 450-625 Hz transition band and near file edges; not
bit-identical. Output sample k = input sample 16*k (zero-phase FIR); frames = ceil(n_samples / 16).

Firmware < ephys.clean_firmware_min (FM64) is de-glitched in the stream with the same rule and thresholds as
``stage_session.py`` / ``deglitch_wild.py`` (5-point median, |x - ref| > max(K*1.4826*MAD, FLOOR)), so no single-sample
impulse leaks into the LFP. FM62 (08-31 day, unfixable regimes) is skipped unless --include-fm62.

Selection (from the session index CSV): not field-flagged unless --include-flagged, duration >= --min-seconds (60), firmware
FM64/FM65. Raw folders are read-only; outputs go to ``<ephys.analysis_root>/lfp/<SFxx>/<session>.lfp`` (+ ``.lfp.json``
sidecar with provenance) or --out-root. Existing complete outputs are skipped (resumable) unless --overwrite.

Usage:
  python ephys/make_lfp.py --cohort 2026c --animal SF7 --session 9_20260901_192912.215      # one session
  python ephys/make_lfp.py --cohort 2026c [--animal SF7 SF8 ...] [--workers 8]             # everything selected
  python ephys/make_lfp.py --selftest                                                        # synthetic, no data needed
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# One BLAS/OpenMP thread per worker process: parallelism comes from the process pool. Without this, each worker starts a
# thread pool the size of the machine (512 on BioHPC cbsuruiz01) and the run is ~10x slower (measured 2026-09-28).
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np  # noqa: E402
from scipy import signal

from _common import (analysis_root, ephys_block, find_session_dir, git_commit, out_root, raw_ephys_root, report_dir,
                     resolve_cohort, utc_now_iso)
from deglitch_wild import DEFAULT_FLOOR, DEFAULT_K, estimate_thresholds, med5

FS_IN = 20000.0
DOWN = 16
FS_OUT = FS_IN / DOWN            # 1250 Hz
LOWPASS_HZ = 450.0               # pipeline write_lfp
FILT_ORDER = 5
CHUNK = 600_000                  # 30 s per chunk (multiple of DOWN)
MARGIN = 4_000                   # 200 ms each side (multiple of DOWN) >> filter settling and FIR half-length
SOS = signal.iirfilter(FILT_ORDER, LOWPASS_HZ, btype="lowpass", ftype="butter", fs=FS_IN, output="sos")


def _norm_animal(a: str) -> str:
    a = a.upper()
    return f"SF{int(a[2:]):02d}" if a.startswith("SF") and a[2:].isdigit() else a


def lfp_root(cohort: str, override: str | None = None) -> Path:
    """Off-repo LFP root: <analysis_root>/lfp/ when the cohort declares one, else <OUT_ROOT>/<cohort>/ephys_lfp/."""
    if override:
        return Path(override)
    ar = analysis_root(cohort)
    return ar / "lfp" if ar else out_root() / resolve_cohort(cohort) / "ephys_lfp"


def _lfp_chunk(x: np.ndarray, thr: np.ndarray | None) -> tuple[np.ndarray, np.ndarray | None]:
    """(de-glitch) -> 450 Hz zero-phase low-pass -> decimate by 16. x: (n, nch) int16/float; returns float32 (ceil(n/16), nch)."""
    x = x.astype(np.float32)
    counts = None
    if thr is not None:
        ref = med5(x)
        bad = np.abs(x - ref) > thr[None, :]
        x[bad] = ref[bad]
        counts = bad
    y = signal.sosfiltfilt(SOS, x, axis=0)
    return signal.resample_poly(y, 1, DOWN, axis=0).astype(np.float32), counts


def _read(f, nch: int, s0: int, s1: int) -> np.ndarray:
    """Samples [s0, s1) of an open raw file as (n, nch) int16, one large read (sequential access keeps NFS/HDD read-ahead)."""
    x = np.empty((s1 - s0) * nch, dtype=np.int16)
    f.seek(s0 * nch * 2)
    got = f.readinto(memoryview(x).cast("B"))
    if got != x.nbytes:
        raise IOError(f"short read at sample {s0}: {got} of {x.nbytes} bytes")
    return x.reshape(-1, nch)


def _work(args: tuple) -> tuple[int, np.ndarray | None]:
    """Worker: a CONTIGUOUS segment [s_lo, s_hi) of input samples, read front to back chunk by chunk (one sequential
    stream per worker) and written straight into its place in the preallocated output (frame a/16 for chunk start a)."""
    path, out_path, nch, ns, s_lo, s_hi, thr = args
    counts = np.zeros(nch, dtype=np.int64) if thr is not None else None
    with open(path, "rb", buffering=0) as f, open(out_path, "r+b") as fo:
        for a in range(s_lo, s_hi, CHUNK):
            b = min(a + CHUNK, s_hi)
            pa, pb = max(a - MARGIN, 0), min(b + MARGIN, ns)
            z, bad = _lfp_chunk(_read(f, nch, pa, pb), thr)
            k0 = (a - pa) // DOWN
            n_out = math.ceil((b - a) / DOWN)
            if bad is not None:
                counts += bad[a - pa:b - pa].sum(axis=0)
            fo.seek((a // DOWN) * nch * 2)
            fo.write(np.clip(np.rint(z[k0:k0 + n_out]), -32768, 32767).astype(np.int16).tobytes())
    return s_hi - s_lo, counts


def convert_session(src: Path, out: Path, *, nch: int = 64, deglitch: bool = False, workers: int = 8,
                    max_seconds: float | None = None, meta: dict | None = None, progress: bool = True) -> dict:
    """Stream ``src`` (amplifier.dat) into ``out`` (.lfp); writes ``out`` atomically and a ``.json`` sidecar."""
    src = Path(src)
    if src.is_dir():
        src = src / "amplifier.dat"
    nbytes = os.path.getsize(src)
    if nbytes % (2 * nch):
        raise ValueError(f"{src}: size {nbytes} not divisible by 2*{nch}")
    ns_file = nbytes // (2 * nch)
    ns = ns_file if max_seconds is None else min(ns_file, int(max_seconds * FS_IN))
    t0 = time.time()
    thr = None
    if deglitch:
        d = np.memmap(src, dtype=np.int16, mode="r").reshape(ns_file, nch)[:ns]
        thr = estimate_thresholds(d, DEFAULT_K, DEFAULT_FLOOR)
        del d
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".partial")
    expected = math.ceil(ns / DOWN)
    with open(tmp, "wb") as fo:                       # preallocate; every worker writes its own region
        fo.truncate(expected * nch * 2)
    # One contiguous segment per worker (boundaries on CHUNK multiples, so frames stay aligned to 16*k).
    n_chunks = math.ceil(ns / CHUNK)
    nseg = max(1, min(workers, n_chunks))
    bounds = [min(ns, (n_chunks * i // nseg) * CHUNK) for i in range(nseg + 1)]
    jobs = [(str(src), str(tmp), nch, ns_file, bounds[i], bounds[i + 1], thr) for i in range(nseg) if bounds[i] < bounds[i + 1]]
    replaced = np.zeros(nch, dtype=np.int64)
    done_samples = 0
    with ProcessPoolExecutor(max_workers=len(jobs)) as ex:
        for n_done, counts in ex.map(_work, jobs):
            done_samples += n_done
            if counts is not None:
                replaced += counts
            if progress:
                print(f"\r  {100.0 * done_samples / ns:5.1f}%  {time.time() - t0:6.0f} s", end="", flush=True)
    if progress:
        print()
    n_frames = expected
    if done_samples != ns or os.path.getsize(tmp) != expected * nch * 2:
        raise RuntimeError(f"{out}: processed {done_samples} of {ns} samples")
    os.replace(tmp, out)
    elapsed = time.time() - t0
    side = {
        "source": str(src), "output": str(out), "n_channels": nch, "dtype": "int16",
        "fs_in": FS_IN, "fs_out": FS_OUT, "n_samples_in": int(ns), "n_frames_out": int(n_frames),
        "truncated_to_s": max_seconds, "duration_s": ns / FS_IN,
        "filter": f"butter order {FILT_ORDER} low-pass {LOWPASS_HZ:g} Hz, sosfiltfilt (zero-phase), on raw; then resample_poly down={DOWN}",
        "sample_alignment": "lfp[k] <-> amplifier sample 16*k",
        "deglitch": bool(deglitch), "deglitch_k_mad": DEFAULT_K if deglitch else None, "deglitch_floor_adc": DEFAULT_FLOOR if deglitch else None,
        "deglitch_replaced_total": int(replaced.sum()) if deglitch else None,
        "chunk_samples": CHUNK, "margin_samples": MARGIN, "workers": workers,
        "elapsed_s": round(elapsed, 1), "throughput_MB_s": round(ns * nch * 2 / 1e6 / elapsed, 1),
        "realtime_factor": round((ns / FS_IN) / elapsed, 1),
        "git_commit": git_commit(), "written_utc": utc_now_iso(),
    }
    if meta:
        side.update(meta)
    out.with_name(out.name + ".json").write_text(json.dumps(side, indent=2), encoding="utf-8")
    return side


def select_sessions(cohort: str, animals: list[str] | None, sessions: list[str] | None, *, include_flagged: bool,
                    include_fm62: bool, min_seconds: float) -> list[dict]:
    idx = report_dir(cohort) / f"ephys_spikes_session_index_{resolve_cohort(cohort)}.csv"
    rows = list(csv.DictReader(open(idx, encoding="utf-8")))
    want_a = {_norm_animal(a) for a in animals} if animals else None
    out = []
    for r in rows:
        if want_a and _norm_animal(r["animal"]) not in want_a:
            continue
        if sessions and r["session"] not in sessions:
            continue
        if not sessions:   # explicit --session bypasses the filters
            if (r.get("field_flag") or "").strip() and not include_flagged:
                continue
            if float(r.get("duration_s") or 0) < min_seconds:
                continue
            fw = int(r.get("firmware") or 0)
            if fw < 64 and not include_fm62:
                continue
        out.append(r)
    return out


def _selftest() -> int:
    """Chunked output must equal the one-shot computation (interior), keep < 400 Hz, remove > 625 Hz, and de-glitch spikes."""
    import tempfile
    rng = np.random.default_rng(0)
    nch, dur = 4, 70.0
    n = int(dur * FS_IN)
    t = np.arange(n) / FS_IN
    x = (300 * np.sin(2 * np.pi * 8 * t)[:, None] + 200 * np.sin(2 * np.pi * 180 * t)[:, None]
         + 400 * np.sin(2 * np.pi * 2000 * t)[:, None] + 30 * rng.standard_normal((n, nch)))
    glitch = rng.choice(n, 500, replace=False)
    x_g = x.copy()
    x_g[glitch, 1] += 15000
    ok = True
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "amplifier.dat"
        np.clip(np.rint(x_g), -32768, 32767).astype(np.int16).tofile(src)
        side = convert_session(src, Path(td) / "t.lfp", nch=nch, deglitch=True, workers=2, progress=False)
        lfp = np.fromfile(Path(td) / "t.lfp", dtype=np.int16).reshape(-1, nch).astype(np.float32)
        ref, _ = _lfp_chunk(np.clip(np.rint(x_g), -32768, 32767).astype(np.int16), estimate_thresholds(
            np.clip(np.rint(x_g), -32768, 32767).astype(np.int16), DEFAULT_K, DEFAULT_FLOOR))
        inner = slice(1000, lfp.shape[0] - 1000)
        diff = float(np.max(np.abs(lfp[inner] - np.rint(ref[inner]))))
        c1 = side["n_frames_out"] == math.ceil(n / DOWN) and lfp.shape[0] == math.ceil(n / DOWN)
        c2 = diff <= 1.0
        sig0 = lfp[inner, 0] - lfp[inner, 0].mean()
        tt = np.arange(sig0.shape[0]) / FS_OUT
        amp = lambda hz: 2 * abs(np.mean(sig0 * np.exp(-2j * np.pi * hz * tt)))   # exact-frequency projection
        c3 = abs(amp(8) - 300) < 15 and abs(amp(180) - 200) < 15      # passband kept (8 Hz theta, 180 Hz ripple band)
        aliased = abs(2000 - 2 * FS_OUT)                                # 2 kHz would alias to 500 Hz without the pre-filter
        c4 = amp(aliased) < 2.0
        c5 = side["deglitch_replaced_total"] >= 490 and float(np.max(np.abs(lfp[inner, 1] - lfp[inner, 0]))) < 200
    for name, c in [("frame count = ceil(n/16)", c1), (f"chunked == one-shot (max diff {diff:.2f} LSB)", c2),
                    ("8 Hz / 180 Hz amplitude kept", c3), ("2 kHz removed (no alias at 500 Hz)", c4),
                    ("15k-ADC single-sample glitches removed", c5)]:
        print(f"[{'PASS' if c else 'FAIL'}] {name}")
        ok &= bool(c)
    print("PASS - make_lfp self-test" if ok else "FAIL - make_lfp self-test")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--animal", nargs="*", default=None)
    ap.add_argument("--session", nargs="*", default=None, help="explicit session folder name(s); bypasses the selection filters")
    ap.add_argument("--raw-root", default=None)
    ap.add_argument("--out-root", default=None, help="default <ephys.analysis_root>/lfp")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--min-seconds", type=float, default=60.0)
    ap.add_argument("--max-seconds", type=float, default=None, help="convert only the first N s of each session (tests)")
    ap.add_argument("--include-flagged", action="store_true")
    ap.add_argument("--include-fm62", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    cfg = ephys_block(a.cohort)
    raw = raw_ephys_root(a.cohort, a.raw_root)
    root = lfp_root(a.cohort, a.out_root)
    sel = select_sessions(a.cohort, a.animal, a.session, include_flagged=a.include_flagged, include_fm62=a.include_fm62,
                          min_seconds=a.min_seconds)
    hours = sum(float(r.get("duration_s") or 0) for r in sel) / 3600
    print(f"{len(sel)} sessions, {hours:.1f} h -> {root}")
    if a.dry_run:
        for r in sel:
            print(f"  {r['animal']:5s} {r['session']:28s} FM{r['firmware']} {float(r['duration_s']) / 3600:6.2f} h")
        return
    clean_min = int(cfg.get("clean_firmware_min", 65))
    done = 0
    for r in sel:
        animal = _norm_animal(r["animal"])
        out = root / animal / f"{r['session']}.lfp"
        if out.exists() and out.with_name(out.name + ".json").exists() and not a.overwrite:
            continue
        src = find_session_dir(raw, r["animal"], r["session"])
        fw = int(r.get("firmware") or 0)
        print(f"{animal} {r['session']} FM{fw} {float(r['duration_s']) / 3600:.2f} h{' (de-glitch)' if fw < clean_min else ''}")
        convert_session(src, out, deglitch=fw < clean_min, workers=a.workers, max_seconds=a.max_seconds,
                        meta={"cohort": resolve_cohort(a.cohort), "animal": animal, "session": r["session"], "firmware": fw,
                              "start_local": r.get("start_local"), "logger_mac": r.get("logger_mac")})
        done += 1
    print(f"done: {done} converted")


if __name__ == "__main__":
    main()
