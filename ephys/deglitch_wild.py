"""Remove single-sample acquisition glitches ("artificial spikes") from a WILD CE64 ``amplifier.dat``.

Vendored port of field2026-sync ``from-field/2026-09-01_deglitch_wild.py`` (field-validated 2026-09-01 on
SF10 ``5_20260901_054403.494``: 99.7 % tick removal, 0.17 % samples replaced, spike-safe). The numerics are
IDENTICAL to the field script (float32, 5-point running median, per-channel MAD threshold sampled from 8
blocks spread over the file); this port only adds a free output path, a JSON manifest, and a verification
metric. Targets the two FM59-64 defects (from-field ``2026-09-01_fm59-62-signal-defects.md``):

  A) per-sample channel substitution — a sample carries another (fixed) channel's simultaneous value;
  B) 15-s housekeeping injection — one-sample deflections to about -21,650 ADC synchronised across channels.

Both are 1-2 samples wide with immediate return to trend, so a 5-point median comparison separates them from
real spikes (~1 ms = 20 samples at 20 kHz; a spike's peak stays close to its 5-point median because its
neighbours are also deep in the waveform).

Definitions (per channel c, sample t; x in ADC units, int16):
    ref_c(t)  = median( x_c[t-2], x_c[t-1], x_c[t], x_c[t+1], x_c[t+2] )      (edge-replicated)
    dev_c(t)  = x_c(t) - ref_c(t)
    MAD_c     = median_t | dev_c(t) - median_t dev_c(t) |                     (8 x 100k-sample blocks)
    thr_c     = max( K * 1.4826 * MAD_c , FLOOR )        K = 10, FLOOR = 500 ADC   (field defaults)
    glitch    = | dev_c(t) | > thr_c   ->   x_c(t) := ref_c(t)
    glitch_rate_per_s = (number of replaced samples, summed over channels) / duration_s
    tick (verification metric only) = | x_c(t) - 0.5*(x_c(t-1)+x_c(t+1)) | > 1200 ADC  (the defects-note metric)

The original file is NEVER modified. Run on RAW 20 kHz data BEFORE any filtering / LFP downsampling / sorting.

Usage:
  python ephys/deglitch_wild.py <session_folder_or_amplifier.dat> --out <path/to/amplifier.dat>
        [--nch 64] [--k 10] [--floor 500] [--report <csv>] [--manifest <json>] [--verify] [--chunk 500000]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

DEFAULT_K = 10.0
DEFAULT_FLOOR = 500.0
DEFAULT_CHUNK = 500_000   # samples per chunk
PAD = 4                   # overlap so the median window never sees a chunk edge
TICK_ADC = 1200.0         # verification-only metric from the defects note
EST_BLOCK = 100_000
EST_NBLOCKS = 8


def med5(x: np.ndarray) -> np.ndarray:
    """5-point running median along axis 0, edge-replicated (numpy only). Exact: median of 5 = 3rd order statistic."""
    n = x.shape[0]
    idx = np.arange(n)
    stack = np.empty((5,) + x.shape, dtype=x.dtype)
    for k, off in enumerate((-2, -1, 0, 1, 2)):
        stack[k] = x[np.clip(idx + off, 0, n - 1)]
    return np.partition(stack, 2, axis=0)[2]


def estimate_thresholds(d: np.ndarray, k: float, floor: float, *, block: int = EST_BLOCK, nblocks: int = EST_NBLOCKS) -> np.ndarray:
    """Per-channel thresholds from ``nblocks`` contiguous blocks spread across the file (identical to the field script)."""
    ns = d.shape[0]
    blk = min(block, ns)
    nblk = min(nblocks, max(1, ns // blk))
    devs = []
    for i in range(nblk):
        a = (ns - blk) * i // max(1, nblk - 1) if nblk > 1 else 0
        sub = d[a:a + blk].astype(np.float32)
        devs.append(sub - med5(sub))
    dev = np.concatenate(devs)
    mad = np.median(np.abs(dev - np.median(dev, axis=0)), axis=0)
    return np.maximum(k * 1.4826 * mad, floor).astype(np.float32)


def tick_count(x: np.ndarray, thr: float = TICK_ADC) -> int:
    """Verification metric: samples deviating > thr ADC from the mean of their two neighbours (interior samples)."""
    if x.shape[0] < 3:
        return 0
    x = x.astype(np.float32)
    dev = np.abs(x[1:-1] - 0.5 * (x[:-2] + x[2:]))
    return int((dev > thr).sum())


def deglitch_file(src: Path, out: Path, *, nch: int = 64, k: float = DEFAULT_K, floor: float = DEFAULT_FLOOR,
                  chunk: int = DEFAULT_CHUNK, report: Path | None = None, manifest: Path | None = None,
                  verify: bool = False, fs: float = 20000.0, progress: bool = True, extra_meta: dict | None = None,
                  sample_range: tuple[int, int] | None = None) -> dict:
    """De-glitch ``src`` into ``out``. ``sample_range=(start, stop)`` restricts the OUTPUT to that sample window
    (thresholds are still estimated on the window itself), used for quick test slices of long sessions."""
    src = Path(src)
    out = Path(out)
    if src.is_dir():
        src = src / "amplifier.dat"
    if out.resolve() == src.resolve():
        raise ValueError("refusing to overwrite the source file (raw data is never modified in place)")
    nbytes = os.path.getsize(src)
    if nbytes % (2 * nch):
        raise ValueError(f"size {nbytes} not divisible by 2*{nch} — wrong --nch?")
    ns_file = nbytes // (2 * nch)
    d = np.memmap(src, dtype=np.int16, mode="r").reshape(ns_file, nch)
    if sample_range is not None:
        s0, s1 = int(max(0, sample_range[0])), int(min(ns_file, sample_range[1]))
        if s1 <= s0:
            raise ValueError(f"empty sample_range {sample_range} for a file of {ns_file} samples")
        d = d[s0:s1]
        nbytes = (s1 - s0) * 2 * nch
    ns = d.shape[0]

    t0 = time.time()
    thr = estimate_thresholds(d, k, floor)

    counts = np.zeros(nch, dtype=np.int64)
    ticks_before = ticks_after = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".partial")
    with open(tmp, "wb") as fo:
        for a in range(0, ns, chunk):
            b = min(a + chunk, ns)
            pa, pb = max(a - PAD, 0), min(b + PAD, ns)
            x = d[pa:pb].astype(np.float32)
            if verify:
                ticks_before += tick_count(x[a - pa:b - pa + 0])
            ref = med5(x)
            bad = np.abs(x - ref) > thr[None, :]
            x[bad] = ref[bad]
            counts += bad[a - pa:b - pa].sum(axis=0)
            y = np.clip(x[a - pa:b - pa], -32768, 32767).astype(np.int16)
            if verify:
                ticks_after += tick_count(y)
            y.tofile(fo)
            if progress:
                print(f"\r{100.0 * b / ns:5.1f}%  glitches so far: {int(counts.sum())}", end="", flush=True)
    if progress:
        print()
    os.replace(tmp, out)
    if os.path.getsize(out) != nbytes:
        raise RuntimeError(f"output size mismatch: {os.path.getsize(out)} != {nbytes}")

    dur_s = ns / fs
    tot = int(counts.sum())
    summary = {
        "source": str(src), "output": str(out), "n_channels": nch, "n_samples": int(ns), "duration_s": dur_s,
        "source_n_samples": int(ns_file), "sample_range": list(sample_range) if sample_range is not None else None,
        "k_mad": k, "floor_adc": floor, "window": 5, "chunk": chunk,
        "threshold_adc_per_channel": [float(t) for t in thr],
        "n_replaced_per_channel": [int(c) for c in counts],
        "n_replaced_total": tot,
        "pct_samples_replaced": 100.0 * tot / (ns * nch),
        "glitch_rate_per_s": tot / dur_s if dur_s else None,
        "ticks_before": int(ticks_before) if verify else None,
        "ticks_after": int(ticks_after) if verify else None,
        "tick_removal_pct": (100.0 * (1 - ticks_after / ticks_before) if verify and ticks_before else None),
        "elapsed_s": time.time() - t0,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algorithm": "5-point running median; replace |x-ref| > max(K*1.4826*MAD, FLOOR); port of from-field/2026-09-01_deglitch_wild.py",
    }
    if extra_meta:
        summary.update(extra_meta)

    if report is not None:
        report = Path(report)
        report.parent.mkdir(parents=True, exist_ok=True)
        with open(report, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["channel", "threshold_adc", "n_replaced", "pct_of_samples"])
            for c in range(nch):
                w.writerow([c, f"{thr[c]:.0f}", int(counts[c]), f"{100.0 * counts[c] / ns:.4f}"])
        summary["report"] = str(report)
    if manifest is not None:
        manifest = Path(manifest)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        summary["manifest"] = str(manifest)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", help="session folder containing amplifier.dat, or the .dat file itself")
    ap.add_argument("--out", required=True, help="output amplifier.dat path (anywhere; never the source)")
    ap.add_argument("--nch", type=int, default=64)
    ap.add_argument("--k", type=float, default=DEFAULT_K, help="MAD multiplier (field default 10)")
    ap.add_argument("--floor", type=float, default=DEFAULT_FLOOR, help="minimum threshold in ADC units (field default 500)")
    ap.add_argument("--fs", type=float, default=20000.0)
    ap.add_argument("--chunk", type=int, default=DEFAULT_CHUNK)
    ap.add_argument("--report", default=None, help="per-channel CSV (default: <out dir>/deglitch_report.csv)")
    ap.add_argument("--manifest", default=None, help="JSON summary (default: <out dir>/deglitch_manifest.json)")
    ap.add_argument("--verify", action="store_true", help="also count >1200-ADC ticks before/after (slower)")
    a = ap.parse_args()
    out = Path(a.out)
    report = Path(a.report) if a.report else out.parent / "deglitch_report.csv"
    manifest = Path(a.manifest) if a.manifest else out.parent / "deglitch_manifest.json"
    s = deglitch_file(Path(a.session), out, nch=a.nch, k=a.k, floor=a.floor, chunk=a.chunk, report=report,
                      manifest=manifest, verify=a.verify, fs=a.fs)
    print(f"done: {s['n_replaced_total']} samples replaced ({s['pct_samples_replaced']:.4f}% of all samples; "
          f"{s['glitch_rate_per_s']:.1f}/s summed over {a.nch} ch) -> {out}")
    if a.verify:
        print(f"ticks >1200 ADC: {s['ticks_before']} -> {s['ticks_after']} ({s['tick_removal_pct']:.2f}% removed)")
    print(f"report -> {report}\nmanifest -> {manifest}")


if __name__ == "__main__":
    sys.exit(main())
