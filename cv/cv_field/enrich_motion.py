"""enrich_motion.py — compute a MOTION sidecar (+ editable label proposals) for an existing frame pool.

For each pool frame it derives the source recording + offset from the filename, pulls a short burst, and runs
field_motion.motion_from_burst. Writes:

  <pool>/motion.json          {frame: {score, boxes(px), W, H}}  — read by `select_frames --use-motion`
  <proposals_dir>/<stem>.txt  YOLO boxes (class 0) — editable label pre-fill for `label_frames --proposals`

Motion boxes are high-recall PROPOSALS, never training labels (see field_motion). Bursts touch source video,
so point ``--rec-root`` at a LOCAL copy of the night when possible (BioHPC golden rule: don't compute against
Q:). For a NEW night, prefer a motion-aware harvest that does this in one streaming pass; this tool retrofits
motion onto a pool that was already harvested as single stills.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import field_motion as fm  # noqa: E402

FRAME_RE = re.compile(r"(CH0\d)_(CH0\d_(\d{4}-\d{2}-\d{2})_\d{2}-\d{2}-\d{2}_to_\d{2}-\d{2}-\d{2})_(\d+)s$")


def source_of(stem: str, rec_root: Path):
    """(source .mp4 path, offset_s) from a pool-frame stem, or None if it doesn't parse."""
    m = FRAME_RE.match(stem)
    if not m:
        return None
    ch, vstem, date, off = m.group(1), m.group(2), m.group(3), int(m.group(4))
    return rec_root / date / ch / f"{vstem}.mp4", off


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compute a motion sidecar + label proposals for a frame pool.")
    ap.add_argument("--pool", required=True, help="directory of harvested frames")
    ap.add_argument("--rec-root", default=r"Q:\hc997\SocialFieldRat2026",
                    help="root holding <date>/<CH>/*.mp4 (prefer a LOCAL copy over Q:)")
    ap.add_argument("--proposals-dir", default=None, help="default: <pool>/../proposals")
    ap.add_argument("--ffmpeg", default=r"C:\ffmpeg\bin\ffmpeg.exe")
    ap.add_argument("--burst-dur", type=float, default=fm.BURST_DUR_S)
    ap.add_argument("--limit", type=int, default=None, help="cap frames (debug)")
    args = ap.parse_args(argv)

    pool = Path(args.pool)
    frames = sorted(p for p in pool.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    if args.limit:
        frames = frames[:args.limit]
    prop_dir = Path(args.proposals_dir) if args.proposals_dir else pool.parent / "proposals"
    prop_dir.mkdir(parents=True, exist_ok=True)
    rec_root = Path(args.rec_root)

    sidecar, n_motion, n_missing = {}, 0, 0
    for fp in frames:
        so = source_of(fp.stem, rec_root)
        if not so or not so[0].exists():
            n_missing += 1
            continue
        r = fm.frame_motion(so[0], so[1], ffmpeg=args.ffmpeg, dur=args.burst_dur)
        if r is None:
            n_missing += 1
            continue
        sidecar[fp.name] = {"score": r["score"], "boxes": r["boxes"], "W": r["W"], "H": r["H"]}
        if r["boxes"]:
            n_motion += 1
            rows = fm.boxes_to_yolo(r["boxes"], r["W"], r["H"])
            (prop_dir / f"{fp.stem}.txt").write_text(
                "\n".join(f"{c} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for c, cx, cy, w, h in rows) + "\n")
    out = pool / "motion.json"
    out.write_text(json.dumps(sidecar, indent=0))
    print(f"enriched {len(sidecar)}/{len(frames)} frames ({n_motion} with motion, {n_missing} unreadable) "
          f"-> {out}\nproposals -> {prop_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
