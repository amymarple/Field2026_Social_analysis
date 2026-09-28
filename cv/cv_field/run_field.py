"""run_field.py — cohort-appendable whole-field (CH01-CH04) inference for cv_field.

Orchestrates the existing, unchanged cv/ tools: per channel it runs ``animal_tracking.py`` (YOLO + ByteTrack
-> per-camera field-cm tracks) then ``merge_cameras.py`` (one common-frame table). Outputs land in the
cohort-appendable layout via common/output_paths.py; a run_manifest + measurement_context sidecar make each
run auditable.

Large-batch / long-video inference is the heavy step that routes to BioHPC (see REMOTE_COMPUTE.md); this
driver only shells out to the CLIs and reads env-driven paths, so it runs identically local or on the server.

IMPORTANT (carried into the report, enforced by field_audit.py): there is NO cross-camera identity yet —
merge_cameras sets animal_id = <camera>:<track_id>, so a rat in a CH01/CH02 overlap is double-counted. Do
NOT make whole-field per-animal-trajectory or cross-camera-headcount claims from this output.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CV_DIR = HERE.parent
for _p in (str(HERE), str(CV_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _run(cmd) -> None:
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True)


def main(argv=None) -> int:
    import cohorts as co
    ap = argparse.ArgumentParser(description="cv_field whole-field inference (CH01-CH04) -> merged field-cm.",
                                 allow_abbrev=False)
    co.add_cohort_arg(ap)
    ap.add_argument("--channels", nargs="+", default=["CH01", "CH02", "CH03", "CH04"])
    ap.add_argument("--clips", nargs="+", required=True,
                    help="one clip per channel, in --channels order")
    ap.add_argument("--weights", required=True, help="cv_field detector weights (runs/detect/rat_field/.../best.pt)")
    ap.add_argument("--device", default="0")
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--out-name", default="cv_field_tracks")
    args = ap.parse_args(argv)

    import output_paths as op
    cohort = op.resolve_cohort(args.cohort)
    if len(args.clips) != len(args.channels):
        raise SystemExit(f"need one clip per channel: {len(args.clips)} clips vs {len(args.channels)} channels")

    run = op.run_dir(args.out_name, cohort)
    tracks_dir = run / "tracks"; tracks_dir.mkdir(parents=True, exist_ok=True)
    per_cam = []
    for ch, clip in zip(args.channels, args.clips):
        out = tracks_dir / f"{ch}.csv"
        _run([sys.executable, str(CV_DIR / "animal_tracking.py"), "--channel", ch, "--clip", clip,
              "--weights", args.weights, "--classes", "0", "--fps", args.fps,
              "--ground-point", "auto", "--out", out])
        per_cam.append(out)

    merged = run / "merged.csv"
    _run([sys.executable, str(CV_DIR / "merge_cameras.py"), "--inputs", *per_cam,
          "--out", merged, "--absolute-time"])

    import measurement_context as mc
    ctx = mc.build_context("cv_field/run_field.py", args, args.channels,
                           active_learning={"stage": "inference", "cross_camera_identity": False})
    mc.write_manifest(run / f"{args.out_name}.measurement_context.json", ctx)

    rep_dir = op.report_dir(cohort, "cv_field")
    op.write_run_manifest(rep_dir, run, cohort=cohort, direction="cv_field",
                          analysis="whole_field_inference", mc_run_id=ctx["mc_run_id"],
                          merged=str(merged))
    print(f"merged whole-field tracks -> {merged}")
    print("NOTE: animal_id = <camera>:<track_id> — no cross-camera identity; counts are a lower bound.")
    print(f"bulk -> {run}   manifest -> {rep_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
