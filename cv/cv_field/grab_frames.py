"""grab_frames.py — fast single-frame extraction from the hourly Reolink recordings (keyframe snap + GPU decode).

Why: labelling pools need single frames at chosen times from the cohort-3 HEVC recordings (keyframe every ~2 s).
Benchmark on the local HDD copy (2026-09-28, CH01/CH02 night 09-04, 20 times each, bulk
`$FIELD2026_ANALYSIS_OUT_ROOT/2026c/cv_field_grab_benchmark_20260928_2139/`): every method costs ~0.8-1.1 s/frame
(median) — the floor is ffmpeg start-up, container open, the pano transpose and piping a 50 MB raw frame, not the
decode: an EXACT seek (decode from the previous keyframe) is only ~0.1 s slower than a keyframe snap and lands within
0.03-0.11 s of the target. GPU (NVDEC) decode gives the same frames (mean |diff| 0.7 grey levels, colour-conversion
rounding) but no speed-up for single frames and a slower tail (p90 3-6 s). Default is therefore CPU + exact; `--mode key`
and `--decode gpu` stay available (GPU decode is for continuous decoding, e.g. whole-night inference).

Layout: `<root>/<YYYY-MM-DD>/<CH>/<CH>_<date>_<HH-MM-SS>[_to_<HH-MM-SS>].mp4` (the local cohort copy `F:\\3rd_rat`).
Times are field-PC local time (file names), never the burnt-in OSD. A night spans two date folders; the date folder
before the target is searched too. Never-renamed segments (no `_to_`) get their span from ffprobe. CH01/CH02 are stored
rotated and are returned UPRIGHT (90 deg counter-clockwise), the frame the calibration and labels use.

Usage (cv env or base Python with OpenCV):
  python cv/cv_field/grab_frames.py --targets targets.csv --out cv/dataset/rat_pano/pool/r0 [--mode exact|key] [--decode cpu|gpu] [--workers 3]
      targets.csv: camera,time[,tag]   time = "YYYY-MM-DD HH:MM:SS[.fff]"   -> <CH>_<video stem>_<pts>s.jpg + manifest.csv
  python cv/cv_field/grab_frames.py --benchmark --cameras CH01 CH02 --night 2026-09-04 --n 20 --cohort 2026c
  python cv/cv_field/grab_frames.py --selftest        # offline: synthetic HEVC clip, no field data needed
Output names follow the cv_field convention `<CH>_<video stem>_<seconds>s` so train_detector.session_key() groups
frames by camera+date+hour.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time as _time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PANO = {"CH01", "CH02"}
STORED = {"CH01": (2160, 7680), "CH02": (2160, 7680), "CH03": (4512, 2512), "CH04": (4512, 2512),
          "CH05": (2560, 1920), "CH06": (2560, 1920), "CH07": (2560, 1920), "CH08": (2560, 1920)}   # (w, h) as stored
NAME = re.compile(r"^(?P<cam>CH0\d)_(?P<d>\d{4}-\d{2}-\d{2})_(?P<s>\d{2}-\d{2}-\d{2})(?:_to_(?P<e>\d{2}-\d{2}-\d{2}))?\.mp4$")
PTS = re.compile(r"pts_time:\s*([0-9.]+)")
NIGHT = ((21, 0), (4, 20))                       # cv_field night window, field-PC time


def find_ffmpeg() -> tuple[str, str]:
    cands = [os.environ.get("REOLINK_FFMPEG"), shutil.which("ffmpeg"), r"C:\ffmpeg\bin\ffmpeg.exe"]
    ff = next((c for c in cands if c and Path(c).exists()), None)
    if ff is None:
        raise SystemExit("ffmpeg not found (set REOLINK_FFMPEG)")
    probe = str(Path(ff).with_name("ffprobe" + Path(ff).suffix))
    return ff, probe


def upright_size(cam: str) -> tuple[int, int]:
    w, h = STORED[cam]
    return (h, w) if cam in PANO else (w, h)


_DUR: dict[str, float] = {}


def probe_duration(video: Path, ffprobe: str) -> float:
    key = str(video)
    if key not in _DUR:
        out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                             capture_output=True, text=True).stdout.strip()
        _DUR[key] = float(out) if out not in ("", "N/A") else 0.0
    return _DUR[key]


def segments(root: Path, cam: str, day: date, ffprobe: str) -> list[tuple[datetime, datetime, Path]]:
    """(start, end, path) of the camera's segments in the date folders `day` and the day before, sorted."""
    out = []
    for d in (day - timedelta(days=1), day):
        folder = Path(root) / f"{d:%Y-%m-%d}" / cam
        if not folder.is_dir():
            continue
        for f in folder.glob(f"{cam}_*.mp4"):
            m = NAME.match(f.name)
            if not m:
                continue
            s = datetime.strptime(f"{m['d']} {m['s']}", "%Y-%m-%d %H-%M-%S")
            if m["e"]:
                e = datetime.strptime(f"{m['d']} {m['e']}", "%Y-%m-%d %H-%M-%S")
                if e <= s:
                    e += timedelta(days=1)
            else:
                dur = probe_duration(f, ffprobe)
                if dur <= 0:
                    continue
                e = s + timedelta(seconds=dur)
            out.append((s, e, f))
    return sorted(out)


def locate(t: datetime, segs) -> tuple[Path, float] | None:
    for s, e, f in segs:
        if s <= t < e:
            return f, (t - s).total_seconds()
    return None


def grab(ffmpeg: str, video: Path, offset: float, cam: str, mode: str = "exact", decode: str = "cpu"):
    """Decode one frame -> (upright BGR image, frame pts in s, decoder used). mode 'key' = keyframe at/before offset
    (one frame decoded), 'exact' = the frame at offset. decode 'gpu' tries NVDEC first and falls back to the CPU."""
    w, h = STORED[cam]
    vf = ("transpose=2," if cam in PANO else "") + "showinfo"
    for dec in (["gpu", "cpu"] if decode == "gpu" else ["cpu"]):
        cmd = [ffmpeg, "-hide_banner", "-nostdin"]
        if dec == "gpu":
            cmd += ["-hwaccel", "cuda"]
        cmd += ["-copyts", "-ss", f"{offset:.3f}"]
        if mode == "key":
            cmd += ["-noaccurate_seek"]
        cmd += ["-i", str(video), "-frames:v", "1", "-an", "-vf", vf, "-pix_fmt", "bgr24", "-f", "rawvideo", "-"]
        p = subprocess.run(cmd, capture_output=True)
        need = w * h * 3
        if p.returncode == 0 and len(p.stdout) == need:
            m = PTS.findall(p.stderr.decode(errors="replace"))
            pts = float(m[0]) if m else float("nan")
            uw, uh = upright_size(cam)
            return np.frombuffer(p.stdout, np.uint8).reshape(uh, uw, 3), pts, dec
    raise RuntimeError(f"{video.name} @ {offset:.1f}s: decode failed ({p.stderr.decode(errors='replace')[-300:]})")


def grab_one(target: dict, root: Path, ffmpeg: str, ffprobe: str, mode: str, decode: str, out: Path | None) -> dict:
    cam, t = target["camera"], target["time"]
    row = {"camera": cam, "target_time": f"{t:%Y-%m-%d %H:%M:%S.%f}"[:-3], "tag": target.get("tag", ""),
           "video": "", "target_offset_s": "", "frame_pts_s": "", "frame_time": "", "snap_s": "", "decoder": "",
           "mode": mode, "seconds": "", "out": "", "error": ""}
    hit = locate(t, segments(root, cam, t.date(), ffprobe))
    if not hit:
        row["error"] = "no video"
        return row
    video, off = hit
    t0 = _time.perf_counter()
    try:
        img, pts, dec = grab(ffmpeg, video, off, cam, mode, decode)
    except RuntimeError as e:
        row.update(video=video.name, target_offset_s=f"{off:.3f}", error=str(e)[:200])
        return row
    secs = _time.perf_counter() - t0
    m = NAME.match(video.name)
    start = datetime.strptime(f"{m['d']} {m['s']}", "%Y-%m-%d %H-%M-%S")
    ft = start + timedelta(seconds=pts) if np.isfinite(pts) else None
    row.update(video=video.name, target_offset_s=f"{off:.3f}", frame_pts_s=f"{pts:.3f}", decoder=dec,
               frame_time=f"{ft:%Y-%m-%d %H:%M:%S.%f}"[:-3] if ft else "",
               snap_s=f"{(ft - t).total_seconds():.3f}" if ft else "", seconds=f"{secs:.2f}")
    if out is not None:
        name = f"{cam}_{video.stem}_{pts:.2f}s.jpg"
        cv2.imwrite(str(out / name), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        row["out"] = name
    row["_img"] = img
    return row


def read_targets(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = r["time"].strip()
            fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in t else "%Y-%m-%d %H:%M:%S"
            rows.append({"camera": r["camera"].strip().upper(), "time": datetime.strptime(t, fmt), "tag": r.get("tag", "")})
    return rows


FIELDS = ["camera", "target_time", "frame_time", "snap_s", "video", "target_offset_s", "frame_pts_s", "decoder", "mode",
          "seconds", "out", "tag", "error"]


def run_targets(args) -> int:
    ffmpeg, ffprobe = find_ffmpeg()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    targets = read_targets(Path(args.targets))
    t0 = _time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(lambda tg: grab_one(tg, Path(args.root), ffmpeg, ffprobe, args.mode, args.decode, out), targets))
    man = out / "manifest.csv"
    new = not man.exists()
    with open(man, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)
    ok = [r for r in rows if not r["error"]]
    wall = _time.perf_counter() - t0
    print(f"{len(ok)}/{len(rows)} frames -> {out} in {wall:.0f} s ({wall / max(1, len(ok)):.2f} s/frame wall, "
          f"{args.workers} workers); decoders: {sorted({r['decoder'] for r in ok})}; manifest -> {man}")
    for r in rows:
        if r["error"]:
            print(f"  {r['camera']} {r['target_time']}: {r['error']}")
    return 0 if ok else 1


def night_times(night: date, n: int, seed: int) -> list[datetime]:
    a = datetime.combine(night, datetime.min.time()).replace(hour=NIGHT[0][0], minute=NIGHT[0][1])
    b = datetime.combine(night + timedelta(days=1), datetime.min.time()).replace(hour=NIGHT[1][0], minute=NIGHT[1][1])
    rng = random.Random(seed)
    span = (b - a).total_seconds()
    return sorted(a + timedelta(seconds=rng.uniform(0, span)) for _ in range(n))


def benchmark(args) -> int:
    """Per camera: n random night times; each decoded 4 ways (CPU exact, CPU key, GPU key, GPU exact) in a rotating
    order (spreads the OS file-cache advantage). Reports s/frame per method, how far the keyframe snap moves the time,
    and GPU-vs-CPU pixel agreement on the same keyframe."""
    ffmpeg, ffprobe = find_ffmpeg()
    import output_paths as op
    cohort = op.resolve_cohort(args.cohort)
    run = op.run_dir("cv_field_grab_benchmark", cohort, make_figures=False)
    methods = [("cpu", "exact"), ("cpu", "key"), ("gpu", "key"), ("gpu", "exact")]
    rows, summary = [], {}
    for cam in args.cameras:
        times = night_times(date.fromisoformat(args.night), args.n, args.seed)
        for i, t in enumerate(times):
            order = methods[i % 4:] + methods[:i % 4]
            got = {}
            for dec, mode in order:
                r = grab_one({"camera": cam, "time": t}, Path(args.root), ffmpeg, ffprobe, mode, dec, None)
                got[(dec, mode)] = r
                rows.append({k: v for k, v in r.items() if k != "_img"} | {"requested_decoder": dec})
            ck, gk = got[("cpu", "key")], got[("gpu", "key")]
            if "_img" in ck and "_img" in gk:
                d = np.abs(ck["_img"].astype(np.int16) - gk["_img"].astype(np.int16))
                rows[-1]["gpu_vs_cpu_key_mad"] = f"{d.mean():.3f}"
                rows[-1]["gpu_vs_cpu_key_max"] = str(int(d.max()))
                rows[-1]["gpu_vs_cpu_same_pts"] = str(ck["frame_pts_s"] == gk["frame_pts_s"])
        cam_rows = [r for r in rows if r["camera"] == cam]
        s = {}
        for dec, mode in methods:
            sec = [float(r["seconds"]) for r in cam_rows if r["requested_decoder"] == dec and r["mode"] == mode and r["seconds"]]
            used = sorted({r["decoder"] for r in cam_rows if r["requested_decoder"] == dec and r["mode"] == mode and r["decoder"]})
            s[f"{dec}_{mode}"] = {"n": len(sec), "median_s": round(float(np.median(sec)), 2) if sec else None,
                                  "p90_s": round(float(np.percentile(sec, 90)), 2) if sec else None, "decoder_used": used}
        snaps = [abs(float(r["snap_s"])) for r in cam_rows if r["mode"] == "key" and r["snap_s"]]
        mads = [float(r["gpu_vs_cpu_key_mad"]) for r in cam_rows if r.get("gpu_vs_cpu_key_mad")]
        same = [r["gpu_vs_cpu_same_pts"] == "True" for r in cam_rows if r.get("gpu_vs_cpu_same_pts")]
        s["key_snap_abs_s"] = {"median": round(float(np.median(snaps)), 2) if snaps else None,
                               "max": round(float(max(snaps)), 2) if snaps else None}
        s["gpu_vs_cpu_key"] = {"mean_abs_diff_grey": round(float(np.mean(mads)), 3) if mads else None,
                               "same_pts_frac": round(float(np.mean(same)), 2) if same else None}
        summary[cam] = s
        print(f"{cam}: " + "  ".join(f"{k} {v['median_s']} s" for k, v in s.items() if "median_s" in v)
              + f" | snap |dt| med {s['key_snap_abs_s']['median']} s max {s['key_snap_abs_s']['max']} s"
              + f" | GPU vs CPU key: MAD {s['gpu_vs_cpu_key']['mean_abs_diff_grey']}, same frame {s['gpu_vs_cpu_key']['same_pts_frac']}")
    keys = sorted({k for r in rows for k in r})
    with open(run / "benchmark_rows.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    meta = {"night": args.night, "n": args.n, "seed": args.seed, "root": args.root, "summary": summary,
            "note": "seconds = wall time of one ffmpeg process per frame, sequential; methods rotated per target"}
    (run / "benchmark_summary.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"bulk -> {run}")
    return 0


def selftest() -> int:
    ffmpeg, ffprobe = find_ffmpeg()
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "2026-09-04" / "CH01").mkdir(parents=True)
        (root / "2026-09-05" / "CH01").mkdir(parents=True)
        # stored-rotated synthetic "pano": 180 wide x 320 high, keyframe every 2 s at 20 fps, 10 s
        def make(path: Path, secs: int):
            subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=180x320:rate=20:duration={secs}",
                            "-c:v", "libx265", "-x265-params", "keyint=40:min-keyint=40:scenecut=0:log-level=error",
                            "-pix_fmt", "yuv420p", str(path)], check=True)
        make(root / "2026-09-04" / "CH01" / "CH01_2026-09-04_23-59-55_to_00-00-05.mp4", 10)   # crosses midnight
        make(root / "2026-09-05" / "CH01" / "CH01_2026-09-05_00-00-05.mp4", 10)               # never renamed
        STORED["CH01"] = (180, 320)
        try:
            segs = segments(root, "CH01", date(2026, 9, 5), ffprobe)
            rec("segments: closed + open (probed) found across the date folders", len(segs) == 2,
                f"{[(f'{s:%H:%M:%S}', f'{e:%H:%M:%S}') for s, e, _ in segs]}")
            hit = locate(datetime(2026, 9, 5, 0, 0, 2), segs)
            rec("locate across midnight", hit and hit[0].name.startswith("CH01_2026-09-04") and abs(hit[1] - 7.0) < 1e-6,
                f"{hit[0].name if hit else None} @ {hit[1] if hit else None}")
            hit2 = locate(datetime(2026, 9, 5, 0, 0, 9), segs)
            rec("locate in the never-renamed segment", hit2 and "_to_" not in hit2[0].name and abs(hit2[1] - 4.0) < 1e-6)
            for dec in ("cpu", "gpu"):
                try:
                    img, pts, used = grab(ffmpeg, hit[0], 7.3, "CH01", "key", dec)
                    rec(f"{dec}: key mode snaps to the keyframe at/before 7.3 s", abs(pts - 6.0) < 0.06,
                        f"pts {pts:.3f} decoder {used}")
                    rec(f"{dec}: pano returned upright (w > h)", img.shape[:2] == (180, 320), f"{img.shape}")
                    img2, pts2, used2 = grab(ffmpeg, hit[0], 7.3, "CH01", "exact", dec)
                    rec(f"{dec}: exact mode lands on the target frame", abs(pts2 - 7.3) <= 0.051, f"pts {pts2:.3f}")
                except RuntimeError as e:
                    rec(f"{dec}: decode", dec == "gpu", f"(GPU unavailable is tolerated) {str(e)[:120]}")
            t = root / "targets.csv"
            t.write_text("camera,time,tag\nCH01,2026-09-05 00:00:02,a\nCH01,2026-09-05 00:00:09.5,b\nCH01,2026-09-05 03:00:00,c\n")
            ns = argparse.Namespace(targets=str(t), out=str(root / "pool"), root=str(root), mode="key", decode="gpu", workers=2)
            run_targets(ns)
            man = list(csv.DictReader(open(root / "pool" / "manifest.csv", encoding="utf-8")))
            rec("targets -> 2 frames + 1 'no video' row in the manifest",
                sum(1 for r in man if r["out"]) == 2 and sum(1 for r in man if r["error"] == "no video") == 1)
            rec("output names follow <CH>_<video stem>_<pts>s.jpg",
                all(re.match(r"CH01_CH01_2026-09-0[45]_\d{2}-\d{2}-\d{2}.*_\d+\.\d{2}s\.jpg$", r["out"]) for r in man if r["out"]))
        finally:
            STORED["CH01"] = (2160, 7680)
    print(("PASS" if ok else "FAIL") + " — grab_frames self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--benchmark", action="store_true")
    ap.add_argument("--targets", help="CSV camera,time[,tag]")
    ap.add_argument("--out", help="output folder for frames + manifest.csv")
    ap.add_argument("--root", default=r"F:\3rd_rat", help="cohort video root (<root>/<date>/<CH>/)")
    ap.add_argument("--mode", choices=["key", "exact"], default="exact")
    ap.add_argument("--decode", choices=["gpu", "cpu"], default="cpu")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--cameras", nargs="+", default=["CH01", "CH02"])
    ap.add_argument("--night", default="2026-09-04", help="benchmark night (21:00 -> 04:20 next day)")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cohort", default=None)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.benchmark:
        return benchmark(args)
    if not (args.targets and args.out):
        ap.error("--targets and --out are required (or --benchmark / --selftest)")
    return run_targets(args)


if __name__ == "__main__":
    raise SystemExit(main())
