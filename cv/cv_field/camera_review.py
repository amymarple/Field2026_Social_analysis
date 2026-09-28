"""camera_review.py — daily frames per camera for HUMAN review of camera stability (did a camera move / get bumped?).

Plan: implementation_plan/2026-09-28-cohort3-camera-stability.md. An automatic check (ECC on a band around the
labelled wall-foot lines) was tried first and was unreliable across days — grass, rain and IR/colour changes dominate
the band (change_log/2026-09-28-cohort3-camera-stability.md). So this tool only extracts frames and lays them out for a
person to judge; it makes no judgement itself.

For each camera and each day it grabs frames at fixed clock times (default 03:01 night IR, 12:00 midday, 21:30
evening IR) from the local raw copy, draws the wall-foot lines labelled on the 2026-09-18 calibration frame
(recording repo calibration_qc/session_2026-09-18_line_labels_CH0x.json, upright pixels) on every frame — if a wall
no longer sits on its line, the camera has moved relative to the calibration — and writes one HTML page per camera:
the 09-18 reference on top, then one row per day. Clicking a thumbnail toggles it with the reference (blink
comparison); the full-resolution image is linked.

It also writes <CH>_flipbook.mp4: every frame in time order at 2 fps, reference first, lines kept, timestamp burnt in —
the quickest way to spot a move (the walls jump off the fixed lines).

Usage:  python cv/cv_field/camera_review.py --cohort 2026c [--cameras CH01 CH02 CH03 CH04] [--times 03:01 12:00 21:30]
        python cv/cv_field/camera_review.py --flipbook <run_dir> [--cameras ...] [--fps 2]   # rebuild videos only
        python cv/cv_field/camera_review.py --selftest
Output: $FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/cv_field_camera_review_<ts>/index.html + <CH>_flipbook.mp4 (off-repo).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PANO = {"CH01", "CH02"}                      # stored 2160x7680 rotated; upright = ffmpeg transpose=2
NAME = re.compile(r"^(?P<ch>\w+?)_(?P<d>\d{4}-\d{2}-\d{2})_(?P<s>\d{2}-\d{2}-\d{2})(?:_to_(?P<e>\d{2}-\d{2}-\d{2}))?\.mp4$")
GAP_TRY_S = (0, 2, 5, 10, 30)                # segments start a second after the previous one ends: step past the gap
THUMB_W = 1600
LINE_BGR = (255, 0, 255)


def find_ffmpeg() -> str:
    for c in (os.environ.get("REOLINK_FFMPEG"), shutil.which("ffmpeg"), r"C:\ffmpeg\bin\ffmpeg.exe"):
        if c and Path(c).exists():
            return str(Path(c) / "ffmpeg.exe") if Path(c).is_dir() else str(c)
    raise SystemExit("ffmpeg not found (set REOLINK_FFMPEG)")


def probe_seconds(video: Path) -> float | None:
    ffprobe = str(Path(find_ffmpeg()).with_name("ffprobe.exe"))
    try:
        out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                             capture_output=True, text=True, check=True).stdout.strip()
        return float(out)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return None


def segments(folder: Path, cam: str, probe=probe_seconds) -> list[tuple[datetime, datetime, Path]]:
    """Segments of one camera in one folder, with ends. A file without `_to_` (never renamed: crash, kill, last file
    of a run) ends at its probed duration, else at the next start, else +1 h."""
    out = []
    for f in sorted(folder.glob(f"{cam}_*.mp4")) if folder.is_dir() else []:
        m = NAME.match(f.name)
        if not m or m["ch"] != cam:
            continue
        s = datetime.strptime(f"{m['d']} {m['s']}", "%Y-%m-%d %H-%M-%S")
        e = None
        if m["e"]:
            e = datetime.strptime(f"{m['d']} {m['e']}", "%Y-%m-%d %H-%M-%S")
            if e <= s:
                e += timedelta(days=1)
        out.append([s, e, f])
    out.sort()
    for i, seg in enumerate(out):
        if seg[1] is None:
            dur = probe(seg[2])
            seg[1] = (seg[0] + timedelta(seconds=dur)) if dur else (out[i + 1][0] if i + 1 < len(out) else seg[0] + timedelta(hours=1))
    return [tuple(x) for x in out]


def locate(t: datetime, segs: list) -> tuple[Path, float, datetime] | None:
    for k in GAP_TRY_S:
        tk = t + timedelta(seconds=k)
        for s, e, f in segs:
            if s <= tk < e - timedelta(seconds=2):
                return f, (tk - s).total_seconds(), tk
    return None


def grab(ffmpeg: str, video: Path, offset_s: float, cam: str, size: tuple[int, int]) -> np.ndarray:
    vf = ["-vf", "transpose=2"] if cam in PANO else []
    cmd = [ffmpeg, "-v", "error", "-ss", f"{offset_s:.3f}", "-i", str(video), "-frames:v", "1", *vf,
           "-pix_fmt", "bgr24", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    w, h = size
    if len(raw) != w * h * 3:
        raise RuntimeError(f"{video.name} @ {offset_s:.1f}s: got {len(raw)} bytes, expected {w}x{h}x3")
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3).copy()


def draw_lines(img: np.ndarray, lines: dict) -> np.ndarray:
    out = img.copy()
    th = max(2, img.shape[1] // 1500)
    for name, pts in lines.items():
        if name.startswith("WALL"):
            p = np.round(np.asarray(pts, float)).astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(out, [p], False, LINE_BGR, th, cv2.LINE_AA)
    return out


def save_pair(img: np.ndarray, lines: dict, stem: str, d: Path) -> tuple[str, str]:
    """Full-res (with lines) + thumbnail (with lines); returns relative paths."""
    lined = draw_lines(img, lines)
    full = d / "full" / f"{stem}.jpg"
    thumb = d / "thumb" / f"{stem}.jpg"
    full.parent.mkdir(parents=True, exist_ok=True)
    thumb.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(full), lined, [cv2.IMWRITE_JPEG_QUALITY, 90])
    s = THUMB_W / lined.shape[1]
    cv2.imwrite(str(thumb), cv2.resize(lined, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return full.relative_to(d.parent).as_posix(), thumb.relative_to(d.parent).as_posix()


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:system-ui,sans-serif;margin:16px;background:#111;color:#ddd}}
table{{border-collapse:collapse}}td,th{{padding:4px;vertical-align:top;text-align:left}}
img{{width:{tw}px;max-width:100%;cursor:pointer;border:2px solid #333}}img.ref{{border-color:#f0f}}
.cap{{font-size:12px;color:#aaa}}a{{color:#8cf}}.na{{color:#666;font-size:12px}}</style></head><body>
<h2>{title}</h2><p>{legend}</p><div>{ref}</div><table><tr><th>date</th>{heads}</tr>{rows}</table>
<script>document.querySelectorAll('img[data-ref]').forEach(function(im){{im.addEventListener('click',function(){{
var r=im.dataset.ref,s=im.dataset.src;if(im.classList.toggle('ref')){{im.src=r}}else{{im.src=s}}}})}});</script>
</body></html>"""


def review_camera(cam: str, args, ffmpeg: str, run: Path) -> dict:
    lab_path = Path(args.labels_dir) / f"session_2026-09-18_line_labels_{cam}.json"
    lab = json.loads(lab_path.read_text(encoding="utf-8")) if lab_path.exists() else {"lines": {}, "clock": "15:47:30"}
    lines = lab.get("lines", {})
    d = run / cam
    size = tuple(lab["frame_size_upright"]) if "frame_size_upright" in lab else None
    if size is None:
        raise SystemExit(f"{cam}: no label file with frame_size_upright at {lab_path}")
    ref_t = datetime.combine(date(2026, 9, 18), datetime.strptime(lab["clock"], "%H:%M:%S").time())
    hit = locate(ref_t, segments(Path(args.ref_session), cam))
    ref_html, ref_thumb = "<p class=na>no 09-18 reference frame</p>", ""
    if hit:
        f, off, tk = hit
        full, ref_thumb = save_pair(grab(ffmpeg, f, off, cam, size), lines, f"{cam}_REF_{tk:%Y%m%d_%H%M%S}", d)
        ref_html = (f"<p><b>Reference</b> — calibration 2026-09-18 {tk:%H:%M:%S} ({html.escape(f.name)}) "
                    f"<a href='{full}'>full</a></p><img class=ref src='{ref_thumb}'>")
    heads = "".join(f"<th>{t:%H:%M}</th>" for t in args.times)
    rows, n = [], 0
    day = args.start
    while day <= args.end:
        segs = segments(Path(args.cohort_root) / f"{day:%Y-%m-%d}" / cam, cam) + \
            segments(Path(args.cohort_root) / f"{day - timedelta(days=1):%Y-%m-%d}" / cam, cam)
        cells = []
        for t0 in args.times:
            hit = locate(datetime.combine(day, t0), segs)
            if not hit:
                cells.append("<td class=na>no video</td>")
                continue
            f, off, tk = hit
            try:
                img = grab(ffmpeg, f, off, cam, size)
            except (RuntimeError, subprocess.CalledProcessError) as e:
                cells.append(f"<td class=na>grab failed: {html.escape(str(e)[:60])}</td>")
                continue
            full, thumb = save_pair(img, lines, f"{cam}_{tk:%Y%m%d_%H%M%S}", d)
            n += 1
            cells.append(f"<td><img src='{thumb}' data-src='{thumb}' data-ref='{ref_thumb}'><div class=cap>"
                         f"{tk:%m-%d %H:%M:%S} · <a href='{full}'>full</a> · {html.escape(f.name)}</div></td>")
        rows.append(f"<tr><td>{day:%m-%d}</td>{''.join(cells)}</tr>")
        day += timedelta(days=1)
    legend = ("Magenta = wall-foot lines labelled on the 2026-09-18 calibration frame. If a wall does not sit on its line, "
              "the camera moved relative to the calibration. <b>Click a thumbnail to blink it against the reference.</b> "
              "Times are field-PC time (file names), not the burnt-in OSD." + ("" if lines else " (No wall labels for this camera.)"))
    page = run / f"{cam}.html"
    page.write_text(PAGE.format(title=f"{cam} daily frames — cohort {args.cohort}", legend=legend, ref=ref_html,
                                heads=heads, rows="".join(rows), tw=min(THUMB_W, 520)), encoding="utf-8")
    print(f"{cam}: {n} frames -> {page}")
    return {"camera": cam, "frames": n, "page": page.name}


def flipbook(run: Path, cam: str, fps: float = 2.0, width: int = 1920) -> Path | None:
    """Time-lapse MP4 of a camera's review frames (09-18 reference first, then chronological), wall lines kept,
    field-PC timestamp burnt in top-left. A camera move shows as the walls jumping off the fixed magenta lines."""
    frames = sorted((run / cam / "full").glob(f"{cam}_*.jpg"), key=lambda p: (0 if "_REF_" in p.name else 1, p.stem[-15:]))
    if not frames:
        return None
    tmp = Path(tempfile.mkdtemp(prefix=f"flip_{cam}_"))
    try:
        for i, p in enumerate(frames):
            img = cv2.imread(str(p))
            s = width / img.shape[1]
            img = cv2.resize(img, (width, int(round(img.shape[0] * s / 2)) * 2), interpolation=cv2.INTER_AREA)
            ts = datetime.strptime(p.stem[-15:], "%Y%m%d_%H%M%S")
            text = f"{cam}  " + ("REFERENCE calibration " if "_REF_" in p.name else "") + f"{ts:%Y-%m-%d %H:%M:%S}"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
            cv2.rectangle(img, (0, 0), (tw + 20, th + 20), (0, 0, 0), -1)
            cv2.putText(img, text, (10, th + 10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imwrite(str(tmp / f"{i:04d}.png"), img)
        out = run / f"{cam}_flipbook.mp4"
        subprocess.run([find_ffmpeg(), "-v", "error", "-y", "-framerate", str(fps), "-i", str(tmp / "%04d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(out)], check=True)
        print(f"{cam}: flipbook ({len(frames)} frames @ {fps:g} fps) -> {out}")
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for name in ("CH03_2026-09-04_02-00-01_to_03-00-00.mp4", "CH03_2026-09-04_03-00-01_to_04-00-00.mp4",
                     "CH03_2026-09-04_13-00-00.mp4", "CH03_2026-09-04_19-01-26_to_20-00-00.mp4", "CH04_2026-09-04_03-00-00_to_04-00-00.mp4"):
            (folder / name).write_bytes(b"")
        segs = segments(folder, "CH03", probe=lambda p: 360.0)          # unrenamed 13:00 file really lasts 6 min
        cases = [(datetime(2026, 9, 4, 3, 0, 0), "03-00-01", 1.0),         # lands in the 1-s gap -> next segment
                 (datetime(2026, 9, 4, 2, 30, 0), "02-00-01", 1799.0),
                 (datetime(2026, 9, 4, 13, 3, 0), "13-00-00", 180.0),       # inside the probed 6 min
                 (datetime(2026, 9, 4, 15, 47, 30), None, None)]           # after the killed file: no video
        for t, want, off in cases:
            hit = locate(t, segs)
            got = (NAME.match(hit[0].name)["s"], round(hit[1], 1)) if hit else (None, None)
            passed = (got[0] == want) and (off is None or abs(got[1] - off) < 0.01)
            ok &= passed
            print(f"[{'PASS' if passed else 'FAIL'}] {t:%H:%M:%S} -> {got}")
        img = np.zeros((100, 200, 3), np.uint8)
        passed = int(draw_lines(img, {"WALL_A": [[10, 50], [190, 50]], "X24": [[0, 0], [99, 99]]})[50, 100, 2]) == 255 \
            and int(draw_lines(img, {"X24": [[0, 0], [99, 99]]}).sum()) == 0
        ok &= passed
        print(f"[{'PASS' if passed else 'FAIL'}] only WALL_* lines are drawn")
    print(("PASS" if ok else "FAIL") + " — camera_review self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--cameras", nargs="+", default=["CH01", "CH02", "CH03", "CH04"])
    ap.add_argument("--start", type=date.fromisoformat, default=date(2026, 8, 30))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2026, 9, 17))
    ap.add_argument("--times", nargs="+", type=lambda s: datetime.strptime(s, "%H:%M").time(),
                    default=[time(3, 1), time(12, 0), time(21, 30)])
    ap.add_argument("--cohort-root", default=r"F:\3rd_rat")
    ap.add_argument("--ref-session", default=r"F:\calibration\session_2026-09-18_13-54-34")
    ap.add_argument("--labels-dir", default=str(HERE.parents[2] / "Field_2026_Social_Recording" / "calibration_qc"))
    ap.add_argument("--flipbook", metavar="RUN_DIR", default=None,
                    help="only (re)build <CH>_flipbook.mp4 from the frames already in RUN_DIR (no video decoding)")
    ap.add_argument("--fps", type=float, default=2.0, help="flipbook frame rate")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.flipbook:
        for cam in args.cameras:
            flipbook(Path(args.flipbook), cam, args.fps)
        return 0
    import output_paths as op
    args.cohort = op.resolve_cohort(args.cohort)
    ffmpeg = find_ffmpeg()
    run = op.run_dir("cv_field_camera_review", args.cohort, make_figures=False)
    pages = [review_camera(cam, args, ffmpeg, run) for cam in args.cameras]
    for p in pages:
        p["video"] = flipbook(run, p["camera"], args.fps)
    links = "".join(f"<li><a href='{p['page']}'>{p['camera']}</a> — {p['frames']} frames"
                    + (f" · <a href='{p['video'].name}'>flipbook mp4</a>" if p.get("video") else "") + "</li>" for p in pages)
    (run / "index.html").write_text(f"<!doctype html><meta charset=utf-8><title>Camera review {args.cohort}</title>"
                                    f"<body style='font-family:system-ui;background:#111;color:#ddd'><h2>Camera review — "
                                    f"cohort {args.cohort}</h2><ul>{links}</ul></body>", encoding="utf-8")
    print(f"open -> {run / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
