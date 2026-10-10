"""Build one K1 block .dat (and optional fractional sub-blocks) from its member sessions. Server or local; stdlib + numpy.

Reads the block row from the block table (`ephys/plan_blocks.py` -> results/<c>/ephys_spikes/reports/
ephys_spikes_k1_blocks_<c>.csv).
- Each segment is [session, raw animal folder, start_sample, end_sample].
- The source is the staged copy `<stage-root>/<SFxx>/<session>/amplifier.dat` if it exists with the raw size,
  otherwise the raw file under `<raw-root>/<raw animal>/<MAC>/<session>/amplifier.dat`, which is read only.
- The segments are concatenated sequentially into `<out-root>/<block>/<block><suffix>.dat` (64 ch int16), written to
  `.part` first and then renamed.
- Boundaries: `<block><suffix>.segments.json` holds every segment's [start, end) in block samples (MergePoints-like),
  plus sizes and timings.

Sub-blocks for the pilot (`--fraction A B`) take samples [A*N, B*N) of the whole block, e.g. 0 0.6667 or 0.3333 1.

Usage:
  python ephys/server/build_block_dat.py --blocks <csv> --block SF10_20260902_083247 --out-root /workdir/.../k1_blocks \
         --stage-root /workdir/.../k1_stage --raw-root /fs/.../3rd_rat/WILD [--fraction 0 0.6667 --suffix _first2of3]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

NCH, BYTES = 64, 2
CHUNK = 20000 * 60   # samples per copy step (1 min, 154 MB)
MACS = {"SF7": "D0DBEFEF3111", "SF8": "128C2F27E131", "SF9": "68BDFFFF62DB", "SF10": "CACB6D600151",
        "SF11": "1DFE7F77721C", "SF12": "FBED2F2321B1"}


def source(seg_session: str, raw_animal: str, stage_root: Path, raw_root: Path) -> Path:
    raw = raw_root / raw_animal / MACS[raw_animal] / seg_session / "amplifier.dat"
    padded = f"SF{int(raw_animal[2:]):02d}"
    staged = stage_root / padded / seg_session / "amplifier.dat"
    if staged.exists() and raw.exists() and staged.stat().st_size == raw.stat().st_size:
        return staged
    if staged.exists() and not raw.exists():
        return staged
    if not raw.exists():
        raise FileNotFoundError(f"neither staged nor raw: {staged} / {raw}")
    return raw


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--blocks", required=True)
    ap.add_argument("--block", required=True)
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--stage-root", required=True)
    ap.add_argument("--raw-root", required=True)
    ap.add_argument("--fraction", type=float, nargs=2, default=None, metavar=("A", "B"))
    ap.add_argument("--suffix", default="")
    a = ap.parse_args()
    row = next((r for r in csv.DictReader(open(a.blocks, newline="", encoding="utf-8")) if r["block"] == a.block), None)
    if row is None:
        sys.exit(f"block {a.block} not in {a.blocks}")
    segs = json.loads(row["segments"])
    total = sum(e - s for _, _, s, e in segs)
    lo, hi = (0, total) if a.fraction is None else (int(a.fraction[0] * total), int(a.fraction[1] * total))
    out_dir = Path(a.out_root) / a.block
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{a.block}{a.suffix}.dat"
    meta = out_dir / f"{a.block}{a.suffix}.segments.json"
    if dst.exists() and meta.exists() and dst.stat().st_size == (hi - lo) * NCH * BYTES:
        print(f"[block] exists: {dst}"); return
    t0 = time.time()
    written, pos, out_segs = 0, 0, []
    with open(str(dst) + ".part", "wb") as fo:
        for session, raw_animal, s0, s1 in segs:
            n = s1 - s0
            a0, a1 = max(lo, pos), min(hi, pos + n)        # overlap of this segment with [lo, hi) in block samples
            if a1 > a0:
                src = source(session, raw_animal, Path(a.stage_root), Path(a.raw_root))
                first = s0 + (a0 - pos)
                with open(src, "rb") as fi:
                    fi.seek(first * NCH * BYTES)
                    left = a1 - a0
                    while left > 0:
                        k = min(CHUNK, left)
                        buf = fi.read(k * NCH * BYTES)
                        if len(buf) != k * NCH * BYTES:
                            raise IOError(f"short read from {src}")
                        fo.write(buf); left -= k
                out_segs.append({"session": session, "source": str(src), "session_start_sample": first,
                                 "session_end_sample": first + (a1 - a0), "block_start_sample": written,
                                 "block_end_sample": written + (a1 - a0)})
                written += a1 - a0
            pos += n
    os.replace(str(dst) + ".part", dst)
    info = {"block": a.block, "suffix": a.suffix, "fraction": a.fraction, "n_samples": written,
            "hours": written / 20000 / 3600, "bytes": dst.stat().st_size, "segments": out_segs,
            "block_row": {k: row[k] for k in ("animal", "start", "end", "hours", "chain", "tier", "disconnect",
                                               "settle_window_h", "fm64", "deeper_profile")},
            "elapsed_s": round(time.time() - t0, 1)}
    meta.write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"[block] {dst} {written / 20000 / 3600:.2f} h, {dst.stat().st_size / 1e9:.1f} GB, {len(out_segs)} segment(s), "
          f"{time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
