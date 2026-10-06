"""c1_yolo_video_test.py — the cohort-1 YOLO v5 panorama rat detector on one whole cohort-3 CH01 night hour + review media.

Plan: implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md, steps 2 and 3 (pre-registered; amendments dated there).
No ground truth exists here: the per-5-s comparison with WISER is a PLAUSIBILITY check for the user, not accuracy.

Step 2.
  Hour (rule fixed in the plan): complete hourly files `CH01_2026-09-06_2[1-3]-*_to_*.mp4` and
  `CH01_2026-09-07_0[0-3]-*_to_*.mp4` under F:/3rd_rat (night 09-06; the frozen test night 09-05 is never touched),
  no overlap with cv/configs/cohort3_handling_windows.json; pick the highest mean number of WISER-tagged animals outside
  the houses per 5-s bin (`select_pano_targets.bin_table` on c3_bins5.pkl: house rectangle + 14 in); ties -> earlier;
  a missing / truncated F: file (ffprobe duration < 98 % of the name span) -> the next one. A bin without any located
  tag has no WISER count (missing, not 0).
  Run: every frame decoded sequentially in-process with PyAV (libavcodec, CPU frame threads; swscale bgr24 + 90 deg ccw
  rotation in 8 threads, order kept) -> the upright 7680 x 2160 pano; one frame compared numerically with
  grab_frames.grab (ffmpeg CLI transpose=2 -> bgr24). Plan amendment: the plan's ffmpeg -> pipe path (NVDEC if it works)
  is pipe-bound at ~8 fps for 50-MB frames and NVDEC does not lift that; PyAV was pixel-identical on a test frame. YOLO v5
  `rat_m_v5/best.pt` (from the verified step-0 backup) at imgsz 1280, conf >= 0.05, fp32, all boxes cached.
  Frame time = file-name start + PTS (field-PC time; stream starts may be offset <= ~1 min, as for every stream).
  Outputs: detections.csv.gz (frame, pts_s, t_pc, x1, y1, x2, y2, conf; upright pano px), frames.csv.gz (frame,
  pts_s, t_pc, decoded_ok), per_second.csv (median count at conf 0.25 / 0.5 over the second's frames, max conf),
  per_5s.csv (YOLO = median per-frame count at 0.25 vs WISER outside-count), run.json, hour_selection.csv,
  identity_check.json, review_10min.mp4 (the 10-min window with the highest mean WISER outside-count).
Step 3 (user request 2026-10-05): 6 labelled 60-s review clips chosen by rule on the 5-s bins only
  (2 agree-many, 1 wiser-zero, 1 yolo-miss, 1 yolo-excess, 1 random seed 0; no overlap with each other or the 10-min
  window) -> review_clips/<k>_<category>_<HH-MM-SS>.mp4 + clips.csv + index.html + review_template.csv.
Rendering (10-min video and clips): every frame of the window, boxes with conf >= 0.25 and their confidence, burned-in
  field-PC frame time, WISER outside-count and YOLO count (boxes >= 0.25 in that frame), scaled to 3840 x 1080, H.264
  (libx264), 20 fps. The agent never looks at any frame or video: the user reviews them.

Usage (cv env, PYTHONIOENCODING=utf-8):
  python cv/cv_field/c1_yolo_video_test.py                      # hour choice -> detection pass -> tables -> media -> report
  python cv/cv_field/c1_yolo_video_test.py --hour-only           # print the hour-selection table, write nothing
  python cv/cv_field/c1_yolo_video_test.py --run <dir> --steps tables media report   # resume from the caches
  python cv/cv_field/c1_yolo_video_test.py --selftest            # synthetic clip + stub detector (ffmpeg, no GPU, no field data)
"""
from __future__ import annotations

import argparse
import csv
import glob
import gzip
import hashlib
import html
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import grab_frames as gf  # noqa: E402

OUT_ROOT = Path(os.environ.get("FIELD2026_ANALYSIS_OUT_ROOT", "D:/Field2026_analysis_out"))
BACKUP = OUT_ROOT / "2026a" / "social_field_rat_backup_20261005"
WEIGHTS = BACKUP / "computer_vision" / "outputs" / "runs" / "rat_m_v5" / "weights" / "best.pt"
VIDEO_ROOT = Path("F:/3rd_rat")
BINS = OUT_ROOT / "2026c" / "wiser_working" / "c3_bins5.pkl"
HANDLING = REPO / "cv" / "configs" / "cohort3_handling_windows.json"
ROIS = REPO / "wiser" / "configs" / "wiser_rois.json"
CANDIDATE_GLOBS = ["2026-09-06/CH01/CH01_2026-09-06_2[1-3]-*_to_*.mp4", "2026-09-07/CH01/CH01_2026-09-07_0[0-3]-*_to_*.mp4"]
FROZEN_NIGHT = (datetime(2026, 9, 5, 21, 0), datetime(2026, 9, 6, 4, 20))
EDT_H = 4                      # field-PC local (EDT) = UTC - 4 h; WISER b5 = floor(UTC epoch s / 5)
CONF_FLOOR = 0.05
CUTS = (0.25, 0.5)
DRAW_CUT = 0.25
IMGSZ = 1280
OUT_W, OUT_H = 3840, 1080
FPS_OUT = 20
REVIEW_BINS = 120              # 10 min of 5-s bins
CLIP_BINS = 12                 # 60 s
MIN_WISER_COVER = 0.9          # 10-min window: >= 90 % of its bins must have a WISER count
COHORT, DIRECTION, NAME = "2026c", "cv_field", "cv_field_c1yolo_video"
REPORT_NAME = "cv_field_c1yolo_video_2026c.md"
POINTER_NAME = "run_manifest_c1yolo_video_2026c.json"
SHOWINFO = re.compile(r"n:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:\s*(-?[0-9.]+)")
NAME_RE = re.compile(r"^(CH0\d)_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})_to_(\d{2}-\d{2}-\d{2})\.mp4$")


# ----------------------------------------------------------------------------------------------- time / WISER
def pts_key(p: float) -> float:
    """Join key for PTS (s). The Reolink streams carry arrival-time PTS with bursts: 1 825 of 72 000 frame pairs of the
    step-2 hour are < 1 ms apart (min 0.022 ms), so a 1-ms rounding merged 804 frames; 6 decimals (1 us) keep them apart
    and both passes compute the PTS identically (PyAV frame.pts x time_base)."""
    return round(float(p), 6)


def b5_of(t: datetime | pd.Timestamp) -> int:
    """5-s WISER bin of a field-PC local time (EDT)."""
    return int((pd.Timestamp(t) + pd.Timedelta(hours=EDT_H)).value // 10**9 // 5)


def bin_start_local(b5: int) -> pd.Timestamp:
    return pd.Timestamp(b5 * 5, unit="s") - pd.Timedelta(hours=EDT_H)


def file_span(path: Path) -> tuple[datetime, datetime]:
    m = NAME_RE.match(path.name)
    if not m:
        raise ValueError(f"not a complete hourly file name: {path.name}")
    s = datetime.strptime(f"{m.group(2)} {m.group(3)}", "%Y-%m-%d %H-%M-%S")
    e = datetime.strptime(f"{m.group(2)} {m.group(4)}", "%Y-%m-%d %H-%M-%S")
    if e <= s:
        e += timedelta(days=1)
    return s, e


def wiser_bins(bins_path: Path = BINS, rois_path: Path = ROIS) -> pd.DataFrame:
    """b5, n_tagged, n_outside, tags_outside, local (bin start) — the select_pano_targets zone rule."""
    import select_pano_targets as spt
    bins = pd.read_pickle(bins_path)
    rois = json.loads(Path(rois_path).read_text(encoding="utf-8"))
    return spt.bin_table(bins, rois)


def load_handling(path: Path = HANDLING) -> list[tuple[datetime, datetime, str]]:
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    return [(datetime.fromisoformat(a), datetime.fromisoformat(b), why) for a, b, why in cfg["windows"]]


def probe_duration(ffprobe: str, path: Path) -> float:
    out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def hour_table(files: list[Path], wb: pd.DataFrame, handling, ffprobe: str | None) -> pd.DataFrame:
    rows = []
    wtab = wb.set_index("b5")
    for f in sorted(files):
        s, e = file_span(f)
        if s < FROZEN_NIGHT[1] and e > FROZEN_NIGHT[0]:
            raise SystemExit(f"{f.name} overlaps the frozen test night — refusing")
        b0, b1 = b5_of(s), b5_of(e)
        sel = wtab.loc[(wtab.index >= b0) & (wtab.index < b1)]
        ov = [why for a, b, why in handling if a < e and b > s]
        span = (e - s).total_seconds()
        dur = probe_duration(ffprobe, f) if ffprobe and f.is_file() else 0.0
        rows.append({"file": f.name, "path": f.as_posix(), "start": s, "end": e, "n_bins": int(len(sel)),
                     "bins_expected": int(b1 - b0), "coverage": len(sel) / max(1, b1 - b0),
                     "mean_wiser_outside": float(sel["n_outside"].mean()) if len(sel) else np.nan,
                     "mean_wiser_tagged": float(sel["n_tagged"].mean()) if len(sel) else np.nan,
                     "handling_overlap": "; ".join(ov), "exists": f.is_file(),
                     "bytes": f.stat().st_size if f.is_file() else 0, "probe_duration_s": dur,
                     "complete": bool(f.is_file() and dur >= 0.98 * span)})
    t = pd.DataFrame(rows)
    t["eligible"] = (t["handling_overlap"] == "") & t["mean_wiser_outside"].notna()
    t = t.sort_values(["mean_wiser_outside", "start"], ascending=[False, True], kind="stable").reset_index(drop=True)
    t["rank"] = np.arange(1, len(t) + 1)
    chosen = None
    for i, r in t.iterrows():
        if r["eligible"] and r["complete"]:
            chosen = i
            break
    t["chosen"] = False
    if chosen is not None:
        t.loc[chosen, "chosen"] = True
    return t


def best_window(per5: pd.DataFrame, nbins: int, value: str, t_lo: pd.Timestamp, t_hi: pd.Timestamp,
                min_cover: float = MIN_WISER_COVER) -> dict | None:
    """Window of nbins consecutive bins inside [t_lo, t_hi) maximising mean(value) over bins present (>= min_cover);
    ties -> earlier."""
    b_lo = b5_of(t_lo) + (0 if bin_start_local(b5_of(t_lo)) >= t_lo else 1)
    b_hi = b5_of(t_hi)                             # bins [b, b+nbins) must end by t_hi
    v = per5.set_index("b5")[value]
    best = None
    for b in range(b_lo, b_hi - nbins + 1):
        w = v.reindex(range(b, b + nbins))
        cov = w.notna().mean()
        if cov < min_cover:
            continue
        m = float(w.mean())
        if best is None or m > best["mean"] + 1e-12:
            best = {"b0": b, "b1": b + nbins, "mean": m, "coverage": float(cov)}
    return best


# ----------------------------------------------------------------------------------------------- decode + detect
def ffmpeg_cmd(ff: str, video: Path, decode: str, vf_tail: str = "", ss: float | None = None) -> list[str]:
    cmd = [ff, "-hide_banner", "-nostdin", "-loglevel", "info"]
    if decode == "gpu":
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-copyts"]
    if ss is not None:
        cmd += ["-ss", f"{ss:.3f}"]
    vf = "transpose=2" + (("," + vf_tail) if vf_tail else "") + ",showinfo"
    cmd += ["-i", str(video), "-an", "-vf", vf, "-pix_fmt", "bgr24", "-vsync", "passthrough", "-f", "rawvideo", "-"]
    return cmd


class FrameStream:
    """Sequential raw-frame reader of one ffmpeg process with showinfo PTS parsing on a side thread."""

    def __init__(self, cmd: list[str], w: int, h: int, qsize: int = 12):
        self.w, self.h = w, h
        self.nbytes = w * h * 3
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self.pts: list[float] = []
        self.errors: list[str] = []
        self.pts_lock = threading.Condition()
        self.q: queue.Queue = queue.Queue(maxsize=qsize)
        self.partial = 0
        self.t_err = threading.Thread(target=self._stderr, daemon=True)
        self.t_out = threading.Thread(target=self._stdout, daemon=True)
        self.t_err.start()
        self.t_out.start()

    def _stderr(self):
        for raw in iter(self.p.stderr.readline, b""):
            line = raw.decode(errors="replace")
            m = SHOWINFO.search(line)
            if m and "Parsed_showinfo" in line:
                with self.pts_lock:
                    self.pts.append(float(m.group(3)))
                    self.pts_lock.notify_all()
            elif "error" in line.lower() or "corrupt" in line.lower() or "missing" in line.lower():
                if len(self.errors) < 2000:
                    self.errors.append(line.strip()[:300])
        with self.pts_lock:
            self.pts_lock.notify_all()

    def _stdout(self):
        while True:
            buf = np.empty(self.nbytes, np.uint8)
            mv = memoryview(buf)
            got = 0
            while got < self.nbytes:
                r = self.p.stdout.readinto(mv[got:])
                if not r:
                    break
                got += r
            if got < self.nbytes:
                self.partial = got
                self.q.put(None)
                return
            self.q.put(buf.reshape(self.h, self.w, 3))

    def frames(self):
        while True:
            f = self.q.get()
            if f is None:
                return
            yield f

    def pts_of(self, k: int, timeout: float = 30.0) -> float:
        end = time.time() + timeout
        with self.pts_lock:
            while len(self.pts) <= k:
                rem = end - time.time()
                if rem <= 0 or (self.p.poll() is not None and not self.t_err.is_alive()):
                    return float("nan") if len(self.pts) <= k else self.pts[k]
                self.pts_lock.wait(min(rem, 1.0))
            return self.pts[k]

    def close(self):
        try:
            self.p.kill()
        except Exception:  # noqa: BLE001
            pass
        self.p.wait()
        self.t_err.join(timeout=10)


def bench_decode(ff: str, video: Path, decode: str, w: int, h: int, n: int = 200) -> dict:
    """ffmpeg CLI -> transpose=2 -> bgr24 -> pipe (the grab_frames path, sequential), n frames."""
    t0 = time.perf_counter()
    fs = FrameStream(ffmpeg_cmd(ff, video, decode), w, h)
    k = 0
    for _ in fs.frames():
        k += 1
        if k >= n:
            break
    dt = time.perf_counter() - t0
    fs.close()
    return {"path": f"ffmpeg-cli {decode} pipe", "frames": k, "seconds": round(dt, 2), "fps": round(k / dt, 2) if dt else 0.0,
            "ok": k >= n, "stderr_errors": fs.errors[:5]}


class AvFrames:
    """In-process sequential decode with PyAV (libavcodec, frame-threaded) + a thread pool doing the swscale bgr24
    conversion and the 90 deg ccw rotation (= ffmpeg transpose=2), order preserved. Yields (pts_s, upright BGR).
    PTS = frame.pts x stream time_base (exact). Corrupt packets are counted and skipped, never invented."""

    def __init__(self, video: Path, start_pts: float | None = None, end_pts: float | None = None, workers: int = 8,
                 scale_to: tuple[int, int] | None = None):
        self.video, self.start, self.end = Path(video), start_pts, end_pts
        self.workers, self.scale_to = workers, scale_to
        self.n_packets = 0
        self.packet_errors: list[str] = []
        self.n_frames = 0
        self.nb_frames_container = None

    def _conv(self, fr):
        import cv2
        a = fr.to_ndarray(format="bgr24")
        a = cv2.rotate(a, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if self.scale_to is not None:
            a = cv2.resize(a, self.scale_to, interpolation=cv2.INTER_AREA)
        return a

    def __iter__(self):
        import av
        from collections import deque
        from concurrent.futures import ThreadPoolExecutor
        c = av.open(str(self.video))
        st = c.streams.video[0]
        st.thread_type = "AUTO"
        self.nb_frames_container = int(st.frames or 0)
        tb = st.time_base
        if self.start is not None and self.start > 3:
            c.seek(int((self.start - 3) / tb), stream=st, backward=True, any_frame=False)
        try:
            pend = deque()
            stop = False
            with ThreadPoolExecutor(self.workers) as ex:
                for pkt in c.demux(st):
                    if stop:
                        break
                    self.n_packets += 1
                    try:
                        frs = pkt.decode()
                    except Exception as e:  # noqa: BLE001 - corrupt packet: skip, count
                        if len(self.packet_errors) < 1000:
                            self.packet_errors.append(f"packet {self.n_packets}: {type(e).__name__}: {str(e)[:150]}")
                        continue
                    for fr in frs:
                        p = float(fr.pts * tb) if fr.pts is not None else float("nan")
                        if self.start is not None and np.isfinite(p) and p < self.start - 1e-6:
                            continue
                        if self.end is not None and np.isfinite(p) and p >= self.end - 1e-6:
                            stop = True
                            break
                        pend.append((p, ex.submit(self._conv, fr)))
                        self.n_frames += 1
                        while len(pend) > 2 * self.workers:
                            q, f = pend.popleft()
                            yield q, f.result()
                while pend:
                    q, f = pend.popleft()
                    yield q, f.result()
        finally:
            c.close()


def bench_av(video: Path, n: int = 300, workers: int = 8) -> dict:
    t0 = time.perf_counter()
    k = 0
    for _ in AvFrames(video, workers=workers):
        k += 1
        if k >= n:
            break
    dt = time.perf_counter() - t0
    return {"path": f"pyav in-process, {workers} conversion threads", "frames": k, "seconds": round(dt, 2),
            "fps": round(k / dt, 2) if dt else 0.0, "ok": k >= n}


def yolo_detector(weights: Path, imgsz: int = IMGSZ, conf: float = CONF_FLOOR):
    from ultralytics import YOLO
    model = YOLO(str(weights))

    def det(imgs: list[np.ndarray]):
        rs = model.predict(imgs, imgsz=imgsz, conf=conf, verbose=False)
        return [(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()) for r in rs]
    return det


def detect_pass(video: Path, det, run: Path, batch: int = 8, keep_frame: int | None = None, log_every: int = 3000,
                workers: int = 8) -> dict:
    """Decode every frame (AvFrames), run det on batches, write detections.csv (chunked). Returns frames + stats."""
    src = AvFrames(video, workers=workers)
    dpath = run / "detections.csv"
    with open(dpath, "w", newline="", encoding="utf-8") as f:
        f.write("frame,x1,y1,x2,y2,conf\n")
    n, t0, t_inf = 0, time.perf_counter(), 0.0
    kept = None
    pts: list[float] = []
    pend: list[np.ndarray] = []
    pend_idx: list[int] = []

    def flush():
        nonlocal t_inf
        if not pend:
            return
        ti = time.perf_counter()
        out = det(pend)
        t_inf += time.perf_counter() - ti
        with open(dpath, "a", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            for k, (b, c) in zip(pend_idx, out):
                for bb, cc in zip(b, c):
                    wr.writerow([k, f"{bb[0]:.1f}", f"{bb[1]:.1f}", f"{bb[2]:.1f}", f"{bb[3]:.1f}", f"{cc:.4f}"])
        pend.clear()
        pend_idx.clear()

    for p, img in src:
        if keep_frame is not None and n == keep_frame:
            kept = img.copy()
        pts.append(p)
        pend.append(img)
        pend_idx.append(n)
        n += 1
        if len(pend) >= batch:
            flush()
        if log_every and n % log_every == 0:
            el = time.perf_counter() - t0
            print(f"  {n} frames, {n / el:.1f} fps overall, inference {t_inf / el * 100:.0f} % of wall", flush=True)
    flush()
    wall = time.perf_counter() - t0
    fr = pd.DataFrame({"frame": np.arange(n), "pts_s": pts, "decoded_ok": True})
    stats = {"frames_decoded": n, "packets": src.n_packets, "container_nb_frames": src.nb_frames_container,
             "packet_errors_n": len(src.packet_errors), "packet_errors_head": src.packet_errors[:10],
             "pts_monotone": bool(pd.Series(pts).is_monotonic_increasing),
             "pts_nan": int(np.isnan(np.asarray(pts, float)).sum()) if pts else 0,
             "wall_s": round(wall, 1), "fps": round(n / wall, 2) if wall else 0, "inference_s": round(t_inf, 1),
             "decode": "pyav (libavcodec in-process, CPU, frame threads) + 8 swscale/rotate threads"}
    return {"frames": fr, "stats": stats, "kept": kept}


def finalize_tables(run: Path, start: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
    fr = pd.read_csv(run / "frames.csv.gz")
    det = pd.read_csv(run / "detections.csv.gz")
    return fr, det


def per_frame_counts(fr: pd.DataFrame, det: pd.DataFrame) -> pd.DataFrame:
    out = fr[["frame", "pts_s", "t_pc"]].copy()
    for c in CUTS:
        cnt = det[det["conf"] >= c].groupby("frame").size()
        out[f"n_{int(c * 100):03d}"] = out["frame"].map(cnt).fillna(0).astype(int)
    out["max_conf"] = out["frame"].map(det.groupby("frame")["conf"].max()).fillna(0.0)
    return out


def per_second(pf: pd.DataFrame) -> pd.DataFrame:
    t = pd.to_datetime(pf["t_pc"])
    g = pf.assign(second=t.dt.floor("s")).groupby("second")
    return pd.DataFrame({"n_frames": g.size(), "count_025_median": g["n_025"].median(), "count_050_median": g["n_050"].median(),
                         "max_conf": g["max_conf"].max()}).reset_index()


def per_5s(pf: pd.DataFrame, wb: pd.DataFrame) -> pd.DataFrame:
    t = pd.to_datetime(pf["t_pc"])
    secs = ((t + pd.Timedelta(hours=EDT_H)) - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)   # unit-agnostic
    b = (secs // 5).to_numpy().astype(np.int64)
    g = pf.assign(b5=b).groupby("b5")
    p = pd.DataFrame({"n_frames": g.size(), "yolo_count": g["n_025"].median(), "yolo_count_050": g["n_050"].median(),
                      "yolo_max_conf": g["max_conf"].max()}).reset_index()
    p["bin_start"] = [bin_start_local(int(x)) for x in p["b5"]]
    w = wb.set_index("b5")
    p["wiser_outside"] = p["b5"].map(w["n_outside"])
    p["wiser_tagged"] = p["b5"].map(w["n_tagged"])
    p["wiser_tags_outside"] = p["b5"].map(w["tags_outside"])
    p["diff"] = p["yolo_count"] - p["wiser_outside"]
    return p


def plausibility(p5: pd.DataFrame) -> dict:
    d = p5.dropna(subset=["yolo_count", "wiser_outside"])
    if d.empty:
        return {"n_bins": 0}
    diff = d["yolo_count"] - d["wiser_outside"]
    rho = d[["yolo_count", "wiser_outside"]].corr(method="spearman").iloc[0, 1]
    vc = diff.round(1).value_counts().sort_index()
    return {"n_bins": int(len(d)), "n_bins_no_wiser": int(p5["wiser_outside"].isna().sum()),
            "diff_mean": float(diff.mean()), "diff_median": float(diff.median()),
            "diff_abs_mean": float(diff.abs().mean()), "spearman_rho": float(rho) if np.isfinite(rho) else None,
            "frac_yolo0_wiser_ge1": float(((d["yolo_count"] == 0) & (d["wiser_outside"] >= 1)).mean()),
            "frac_yolo_gt_wiser": float((d["yolo_count"] > d["wiser_outside"]).mean()),
            "frac_yolo_eq_wiser": float((d["yolo_count"] == d["wiser_outside"]).mean()),
            "frac_yolo_lt_wiser": float((d["yolo_count"] < d["wiser_outside"]).mean()),
            "wiser_outside_mean": float(d["wiser_outside"].mean()), "yolo_count_mean": float(d["yolo_count"].mean()),
            "diff_distribution": {str(k): int(v) for k, v in vc.items()},
            "by_wiser_outside": {str(int(k)): {"bins": int(len(g)), "yolo_mean": float(g["yolo_count"].mean()),
                                               "yolo_zero_frac": float((g["yolo_count"] == 0).mean())}
                                 for k, g in d.groupby("wiser_outside")}}


# ----------------------------------------------------------------------------------------------- clip selection
def eligible_windows(p5: pd.DataFrame, nbins: int) -> pd.DataFrame:
    """All windows of nbins consecutive bins where every bin has >= 1 frame and a WISER count."""
    s = p5.set_index("b5")
    rows = []
    for b in range(int(s.index.min()), int(s.index.max()) - nbins + 2):
        w = s.reindex(range(b, b + nbins))
        if w["n_frames"].isna().any() or (w["n_frames"] < 1).any() or w["wiser_outside"].isna().any():
            continue
        y, x = w["yolo_count"].to_numpy(float), w["wiser_outside"].to_numpy(float)
        rows.append({"b0": b, "b1": b + nbins, "mean_wiser": x.mean(), "mean_yolo": y.mean(),
                     "mean_absdiff": np.abs(y - x).mean(), "all_wiser_zero": bool((x == 0).all()),
                     "n_miss": int(((y == 0) & (x >= 2)).sum()), "n_excess": int((y > x + 1).sum())})
    return pd.DataFrame(rows)


def overlaps(b0: int, b1: int, taken: list[tuple[int, int]]) -> bool:
    return any(b0 < t1 and t0 < b1 for t0, t1 in taken)


def select_clips(win: pd.DataFrame, taken: list[tuple[int, int]], seed: int = 0) -> list[dict]:
    """Rule of the plan's step-3 amendment. Returns one dict per requested clip (category, b0, b1, rule value) or a
    'none' entry when a category has no qualifying window."""
    taken = list(taken)
    out = []

    def pick(cat, cand, rule, value_col, ascending=False):
        c = cand[[not overlaps(int(r.b0), int(r.b1), taken) for r in cand.itertuples()]] if len(cand) else cand
        if len(c) == 0:
            out.append({"category": cat, "b0": None, "b1": None, "rule": rule, "rule_value": None})
            return
        c = c.sort_values([value_col, "b0"], ascending=[ascending, True], kind="stable")
        r = c.iloc[0]
        taken.append((int(r.b0), int(r.b1)))
        out.append({"category": cat, "b0": int(r.b0), "b1": int(r.b1), "rule": rule, "rule_value": float(r[value_col]),
                    "mean_wiser": float(r.mean_wiser), "mean_yolo": float(r.mean_yolo)})

    if len(win) == 0:
        win = pd.DataFrame(columns=["b0", "b1", "mean_wiser", "mean_yolo", "mean_absdiff", "all_wiser_zero", "n_miss",
                                    "n_excess"])
    agree = win[win["mean_absdiff"] <= 1]
    pick("agree-many", agree, "max mean WISER, given mean abs(YOLO - WISER) <= 1", "mean_wiser")
    pick("agree-many", agree, "max mean WISER, given mean abs(YOLO - WISER) <= 1", "mean_wiser")
    pick("wiser-zero", win[win["all_wiser_zero"].astype(bool)], "max mean YOLO, given WISER = 0 in all 12 bins", "mean_yolo")
    pick("yolo-miss", win[win["n_miss"] >= 1], "max number of bins with YOLO = 0 and WISER >= 2", "n_miss")
    pick("yolo-excess", win[win["n_excess"] >= 1], "max number of bins with YOLO > WISER + 1", "n_excess")
    free = win[[not overlaps(int(r.b0), int(r.b1), taken) for r in win.itertuples()]] if len(win) else win
    if len(free) == 0:
        out.append({"category": "random", "b0": None, "b1": None, "rule": "uniform, default_rng(0)", "rule_value": None})
    else:
        free = free.sort_values("b0").reset_index(drop=True)
        i = int(np.random.default_rng(seed).integers(len(free)))
        r = free.iloc[i]
        taken.append((int(r.b0), int(r.b1)))
        out.append({"category": "random", "b0": int(r.b0), "b1": int(r.b1), "rule": "uniform, default_rng(0)",
                    "rule_value": float(i), "mean_wiser": float(r.mean_wiser), "mean_yolo": float(r.mean_yolo)})
    return out


# ----------------------------------------------------------------------------------------------- rendering
def render_window(ff: str, video: Path, file_start: datetime, t0: pd.Timestamp, t1: pd.Timestamp, frames: pd.DataFrame,
                  det: pd.DataFrame, wiser: dict, out_path: Path, out_w: int = OUT_W, out_h: int = OUT_H,
                  src_w: int = 7680, cam: str = "CH01", encoder: str = "libx264") -> dict:
    """Decode [t0, t1) (field-PC time) from the video, draw cached boxes >= DRAW_CUT (joined by PTS), burn in time /
    WISER / YOLO count, encode H.264 at FPS_OUT. Returns render stats."""
    import cv2
    p0 = (t0 - pd.Timestamp(file_start)).total_seconds()
    p1 = (t1 - pd.Timestamp(file_start)).total_seconds()
    fsel = frames[(frames["pts_s"] >= p0 - 1e-6) & (frames["pts_s"] < p1 - 1e-6)]
    want = {pts_key(v): int(k) for k, v in zip(fsel["frame"], fsel["pts_s"])}
    dsel = det[(det["conf"] >= DRAW_CUT) & det["frame"].isin(fsel["frame"])]
    boxes = {k: g[["x1", "y1", "x2", "y2", "conf"]].to_numpy() for k, g in dsel.groupby("frame")}
    scale = out_w / src_w
    src = AvFrames(video, start_pts=p0, end_pts=p1, scale_to=(out_w, out_h))
    enc = subprocess.Popen([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
                            "-s", f"{out_w}x{out_h}", "-r", str(FPS_OUT), "-i", "-", "-c:v", encoder,
                            "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                            str(out_path)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    n_written, n_unmatched = 0, 0
    fsz = max(0.6, out_h / 1080 * 1.1)
    for pts, img in src:
        if not np.isfinite(pts) or pts < p0 - 1e-6:
            continue
        if pts >= p1 - 1e-6:
            break
        fidx = want.get(pts_key(pts))
        if fidx is None:
            n_unmatched += 1
        img = np.ascontiguousarray(img)
        bx = boxes.get(fidx, np.zeros((0, 5)))
        for x1, y1, x2, y2, c in bx:
            a, b, cc, d = (int(round(v * scale)) for v in (x1, y1, x2, y2))
            cv2.rectangle(img, (a, b), (cc, d), (0, 255, 0), 2)
            cv2.putText(img, f"{c:.2f}", (a, max(14, b - 5)), cv2.FONT_HERSHEY_SIMPLEX, fsz * 0.55, (0, 255, 0), 2,
                        cv2.LINE_AA)
        t = pd.Timestamp(file_start) + pd.Timedelta(seconds=pts)
        wv = wiser.get(b5_of(t))
        wtxt = "n/a" if wv is None or (isinstance(wv, float) and not np.isfinite(wv)) else f"{int(wv)}"
        txt = (f"{cam} {t:%Y-%m-%d %H:%M:%S}.{t.microsecond // 1000:03d} field-PC | WISER outside: {wtxt} | "
               f"YOLO >= {DRAW_CUT:.2f}: {len(bx)} | frame {fidx if fidx is not None else '?'}")
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, fsz, 2)
        cv2.rectangle(img, (0, 0), (tw + 20, th + 20), (0, 0, 0), -1)
        cv2.putText(img, txt, (10, th + 10), cv2.FONT_HERSHEY_SIMPLEX, fsz, (255, 255, 255), 2, cv2.LINE_AA)
        enc.stdin.write(img.tobytes())
        n_written += 1
    enc.stdin.close()
    enc.wait()
    err = enc.stderr.read().decode(errors="replace")[-300:]
    return {"file": out_path.name, "frames_expected": int(len(fsel)), "frames_written": n_written,
            "frames_unmatched_pts": n_unmatched, "bytes": out_path.stat().st_size if out_path.is_file() else 0,
            "encoder_rc": enc.returncode, "encoder_err": err, "pts_range": [p0, p1]}


def write_index(clip_dir: Path, rows: list[dict], review: dict | None) -> None:
    cols = ["file", "category", "start", "end", "frames", "mean_wiser", "mean_yolo", "rule", "rule_value"]
    h = ["<!doctype html><html><head><meta charset='utf-8'><title>CH01 YOLO v5 review clips</title>",
         "<style>body{font-family:sans-serif;margin:16px;max-width:1900px}table{border-collapse:collapse;font-size:13px}"
         "td,th{border:1px solid #999;padding:3px 6px}video{width:100%;max-width:1900px}h2{margin-top:28px}</style>"
         "</head><body>",
         "<h1>Cohort-3 CH01: cohort-1 YOLO v5 boxes (conf &ge; 0.25) — clips for manual review</h1>",
         "<p>Chosen by rule on the 5-s bins only (plan implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md, "
         "step 3). Field-PC time. WISER = tagged animals outside the houses (lower bound for what CH01 can see). "
         "Machine boxes are proposals, not labels. Record verdicts in review_template.csv.</p><table><tr>"]
    h += [f"<th>{c}</th>" for c in cols] + ["</tr>"]
    allrows = ([review] if review else []) + rows
    for r in allrows:
        h.append("<tr>" + "".join(f"<td>{html.escape(str(r.get(c, '')))}</td>" for c in cols) + "</tr>")
    h.append("</table>")
    for r in allrows:
        if not r.get("src"):
            continue
        h.append(f"<h2>{html.escape(r['file'])} — {html.escape(r['category'])}, {html.escape(str(r['start']))} → "
                 f"{html.escape(str(r['end']))}</h2><video controls preload='metadata' src='{html.escape(r['src'])}'></video>")
    h.append("</body></html>")
    (clip_dir / "index.html").write_text("\n".join(h), encoding="utf-8")


# ----------------------------------------------------------------------------------------------- driver
def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def candidate_files(root: Path = VIDEO_ROOT) -> list[Path]:
    out = []
    for g in CANDIDATE_GLOBS:
        out += [Path(p) for p in glob.glob(str(root / g))]
    return sorted(out)


def step_hour(run: Path | None, ffprobe: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    wb = wiser_bins()
    tab = hour_table(candidate_files(), wb, load_handling(), ffprobe)
    if run is not None:
        tab.to_csv(run / "hour_selection.csv", index=False)
    return tab, wb


def step_detect(run: Path, meta: dict, ff: str) -> None:
    video = Path(meta["video"])
    w, h = gf.upright_size("CH01")
    bench = {d: bench_decode(ff, video, d, w, h, n=150) for d in ("gpu", "cpu")}
    bench["pyav"] = bench_av(video, n=300)
    meta["decode_bench"] = bench
    meta["decode"] = "pyav"
    print("decode bench: " + "; ".join(f"{v['path']} {v['fps']} fps ok={v['ok']}" for v in bench.values()))
    s, _ = file_span(video)
    keep = int(max(0, (pd.Timestamp(meta["review_window"]["start"]) - pd.Timestamp(s)).total_seconds() * 20))
    det = yolo_detector(Path(meta["weights"]))
    res = detect_pass(video, det, run, keep_frame=keep)
    fr = res["frames"]
    fr["t_pc"] = [(pd.Timestamp(s) + pd.Timedelta(seconds=float(p))).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                  if np.isfinite(p) else "" for p in fr["pts_s"]]
    fr.to_csv(run / "frames.csv.gz", index=False)
    d = pd.read_csv(run / "detections.csv")
    d = d.merge(fr[["frame", "pts_s", "t_pc"]], on="frame", how="left")[["frame", "pts_s", "t_pc", "x1", "y1", "x2", "y2", "conf"]]
    d.to_csv(run / "detections.csv.gz", index=False)
    (run / "detections.csv").unlink()
    meta["detect_stats"] = res["stats"]
    identity_check(run, meta, ff, keep, res["kept"])


def identity_check(run: Path, meta: dict, ff: str, keep: int, kept: np.ndarray | None = None) -> dict:
    """Pixel identity of frame `keep` of the sequential PyAV pass vs grab_frames.grab (ffmpeg CLI, CPU, exact seek,
    transpose=2). grab returns the first frame with PTS >= offset, so offset = the midpoint between the previous frame's
    PTS and this one's (frames can be < 1 ms apart). The pass frame is read back from its lossless PNG if not given."""
    import cv2
    video = Path(meta["video"])
    fr = pd.read_csv(run / "frames.csv.gz")
    png = run / f"identity_frame_{keep}.png"
    if kept is not None:
        cv2.imwrite(str(png), kept)
    else:
        kept = cv2.imread(str(png), cv2.IMREAD_COLOR)
    pts = float(fr.loc[keep, "pts_s"])
    prev = float(fr.loc[keep - 1, "pts_s"]) if keep > 0 else pts - 0.05
    off = (prev + pts) / 2
    idc = {"frame": keep, "pts_s": pts, "prev_pts_s": prev, "grab_offset_s": off, "png": png.name}
    img, p2, used = gf.grab(ff, video, off, "CH01", "exact", "cpu")
    dd = np.abs(img.astype(np.int16) - kept.astype(np.int16))
    idc["vs_grab_cpu"] = {"grab_pts_s": p2, "same_frame_pts": bool(abs(p2 - pts) < 1e-4), "decoder_used": used,
                          "identical": bool(dd.max() == 0), "max_abs_diff": int(dd.max()), "mean_abs_diff": float(dd.mean()),
                          "frac_pixels_differ": float((dd.max(2) > 0).mean())}
    old = run / "identity_check.json"
    if old.is_file():
        prior = json.loads(old.read_text(encoding="utf-8"))
        if prior.get("grab_offset_s") is None and "vs_grab_cpu" in prior:
            idc["first_attempt_offset_pts_minus_1ms"] = prior["vs_grab_cpu"]
    old.write_text(json.dumps(idc, indent=2), encoding="utf-8")
    meta["identity_check"] = idc
    print(f"identity check: {json.dumps(idc)}")
    return idc


def step_tables(run: Path, meta: dict, wb: pd.DataFrame) -> dict:
    fr = pd.read_csv(run / "frames.csv.gz")
    det = pd.read_csv(run / "detections.csv.gz")
    dpt = np.diff(fr["pts_s"].to_numpy(float))
    meta["pts_spacing"] = {"n_lt_1ms": int((dpt < 0.001).sum()), "min_ms": float(dpt.min() * 1000),
                           "median_ms": float(np.median(dpt) * 1000), "max_ms": float(dpt.max() * 1000),
                           "duplicates": int((dpt == 0).sum()),
                           "round_1ms_collisions": int(len(dpt) + 1 - len(np.unique(np.round(fr["pts_s"].to_numpy(float), 3))))}
    pf = per_frame_counts(fr, det)
    pf.to_csv(run / "per_frame_counts.csv.gz", index=False)
    ps = per_second(pf)
    ps.to_csv(run / "per_second.csv", index=False)
    p5 = per_5s(pf, wb)
    p5.to_csv(run / "per_5s.csv", index=False)
    pl = plausibility(p5)
    pl["frames"] = int(len(fr))
    pl["frames_with_det_025"] = int((pf["n_025"] > 0).sum())
    pl["frac_frames_no_det_025"] = float((pf["n_025"] == 0).mean())
    pl["detections_total_floor"] = int(len(det))
    pl["detections_025"] = int((det["conf"] >= 0.25).sum())
    pl["count_025_frame_distribution"] = {str(k): int(v) for k, v in pf["n_025"].value_counts().sort_index().items()}
    meta["plausibility"] = pl
    (run / "plausibility.json").write_text(json.dumps(pl, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in pl.items() if not isinstance(v, dict)}, indent=1))
    return pl


def step_media(run: Path, meta: dict, ff: str, wb: pd.DataFrame) -> None:
    video = Path(meta["video"])
    s, _ = file_span(video)
    fr = pd.read_csv(run / "frames.csv.gz")
    det = pd.read_csv(run / "detections.csv.gz")
    p5 = pd.read_csv(run / "per_5s.csv")
    wiser = dict(zip(p5["b5"].astype(int), p5["wiser_outside"]))
    for b, v in zip(wb["b5"], wb["n_outside"]):
        wiser.setdefault(int(b), v)
    rw = meta["review_window"]
    t0, t1 = pd.Timestamp(rw["start"]), pd.Timestamp(rw["end"])
    tt = time.perf_counter()
    st = render_window(ff, video, s, t0, t1, fr, det, wiser, run / "review_10min.mp4")
    st["seconds"] = round(time.perf_counter() - tt, 1)
    meta["review_render"] = st
    print(f"review_10min.mp4: {st}")
    # step 3 clips
    cd = run / "review_clips"
    cd.mkdir(exist_ok=True)
    win = eligible_windows(p5, CLIP_BINS)
    win.to_csv(cd / "eligible_windows.csv", index=False)
    sel = select_clips(win, [(int(rw["b0"]), int(rw["b1"]))], seed=0)
    rows = []
    for k, c in enumerate(sel, start=1):
        if c["b0"] is None:
            rows.append({"file": "", "category": c["category"], "start": "", "end": "", "frames": "", "mean_wiser": "",
                         "mean_yolo": "", "rule": c["rule"], "rule_value": "no qualifying window", "src": ""})
            continue
        a, b = bin_start_local(c["b0"]), bin_start_local(c["b1"])
        name = f"{k}_{c['category']}_{a:%H-%M-%S}.mp4"
        tt = time.perf_counter()
        r = render_window(ff, video, s, a, b, fr, det, wiser, cd / name)
        fsel = fr[(fr["pts_s"] >= (a - pd.Timestamp(s)).total_seconds() - 1e-6) & (fr["pts_s"] < (b - pd.Timestamp(s)).total_seconds() - 1e-6)]
        rows.append({"file": name, "category": c["category"], "start": f"{a:%Y-%m-%d %H:%M:%S}", "end": f"{b:%Y-%m-%d %H:%M:%S}",
                     "frames": f"{int(fsel['frame'].min())}-{int(fsel['frame'].max())}" if len(fsel) else "",
                     "mean_wiser": round(c["mean_wiser"], 3), "mean_yolo": round(c["mean_yolo"], 3), "rule": c["rule"],
                     "rule_value": round(c["rule_value"], 3), "src": name, "frames_written": r["frames_written"],
                     "frames_expected": r["frames_expected"], "frames_unmatched_pts": r["frames_unmatched_pts"],
                     "bytes": r["bytes"], "render_s": round(time.perf_counter() - tt, 1)})
        print(f"clip {name}: {r['frames_written']}/{r['frames_expected']} frames, {r['bytes'] / 1e6:.0f} MB")
    cols = ["file", "category", "start", "end", "frames", "mean_wiser", "mean_yolo", "rule", "rule_value",
            "frames_written", "frames_expected", "frames_unmatched_pts", "bytes"]
    with open(cd / "clips.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    rev_sel = fr[(fr["pts_s"] >= (t0 - pd.Timestamp(s)).total_seconds() - 1e-6) & (fr["pts_s"] < (t1 - pd.Timestamp(s)).total_seconds() - 1e-6)]
    review = {"file": "review_10min.mp4", "category": "10-min (max mean WISER)", "start": f"{t0:%Y-%m-%d %H:%M:%S}",
              "end": f"{t1:%Y-%m-%d %H:%M:%S}", "frames": f"{int(rev_sel['frame'].min())}-{int(rev_sel['frame'].max())}",
              "mean_wiser": round(rw["mean"], 3),
              "mean_yolo": round(float(p5[(p5["b5"] >= rw["b0"]) & (p5["b5"] < rw["b1"])]["yolo_count"].mean()), 3),
              "rule": "max mean WISER over 120 bins (at least 90 % with a WISER count)", "rule_value": round(rw["mean"], 3),
              "src": "../review_10min.mp4"}
    write_index(cd, rows, review)
    with open(cd / "review_template.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clip", "user_verdict", "notes"])
        w.writerow(["review_10min.mp4", "", ""])
        for r in rows:
            if r["file"]:
                w.writerow([r["file"], "", ""])
    meta["clips"] = rows
    meta["review_row"] = review


def write_report(run: Path, meta: dict, tab: pd.DataFrame) -> Path:
    pl = meta.get("plausibility", {})
    ds = meta.get("detect_stats", {})
    rr = meta.get("review_render", {})
    idc = meta.get("identity_check", {})
    L = ["# Cohort-1 YOLO v5 panorama detector on one cohort-3 CH01 night hour (2026c)", "",
         f"Driver `cv/cv_field/c1_yolo_video_test.py` (plan `implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md`, "
         f"steps 2-3); run `{run.as_posix()}`; generated {datetime.now():%Y-%m-%d %H:%M}. **No ground truth here**: the "
         "YOLO-vs-WISER numbers are a plausibility check for the user, not an accuracy number. Machine boxes are "
         "proposals, never labels. The agent did not look at any frame or video.", "",
         "## Hour", "",
         f"Rule (plan): complete CH01 files of night 09-06 (21:00-04:00 starts), no handling overlap, highest mean "
         f"number of WISER-tagged animals outside the houses per 5-s bin; ties → earlier. Chosen: **{meta['video_name']}** "
         f"({Path(meta['video']).stat().st_size / 1e9:.2f} GB, ffprobe {meta.get('probe_duration_s', float('nan')):.1f} s).", "",
         "| rank | file | mean WISER outside | mean tagged | bins (coverage) | handling overlap | complete | chosen |",
         "|---:|---|---:|---:|---|---|---|---|"]
    for r in tab.itertuples():
        L.append(f"| {r.rank} | {r.file} | {r.mean_wiser_outside:.3f} | {r.mean_wiser_tagged:.2f} | {r.n_bins} / "
                 f"{r.bins_expected} ({r.coverage:.1%}) | {r.handling_overlap or '–'} | {r.complete} | "
                 f"{'**yes**' if r.chosen else ''} |")
    b = meta.get("decode_bench", {})
    L += ["", "## Decode, detection, runtime", "",
          "- Decode benchmark (no inference): " + "; ".join(f"{v.get('path')} {v.get('fps')} fps over {v.get('frames')} frames"
                                                           for v in b.values()) + ". Path used: **in-process PyAV** "
          "(libavcodec frame threads, swscale bgr24 + 90° ccw rotation in 8 threads; plan amendment — the ffmpeg CLI → pipe "
          "path of grab_frames is pipe-bound for 50-MB frames, NVDEC does not help it, and PyAV is pixel-identical to it).",
          f"- Pass: {ds.get('frames_decoded')} frames decoded from {ds.get('packets')} demuxed packets (incl. PyAV's final "
          f"empty flush packet; the fragmented MP4 stores no frame count); {ds.get('packet_errors_n')} packets failed to decode; PTS monotone "
          f"{ds.get('pts_monotone')}, {ds.get('pts_nan')} without PTS), wall {ds.get('wall_s')} s = {ds.get('fps')} fps, of which YOLO "
          "inference "
          f"{ds.get('inference_s')} s. YOLO v5 `rat_m_v5/best.pt` (backup copy, sha256 `{meta.get('weights_sha256')}`), "
          f"imgsz {IMGSZ}, conf ≥ {CONF_FLOOR}, fp32, batch 8; ultralytics {meta.get('versions', {}).get('ultralytics')}.",
          "- Pixel identity (frame {f}, PTS {p}): ".format(f=idc.get("frame"), p=idc.get("pts_s"))
          + "; ".join(f"vs `grab_frames.grab` {k[8:]} exact (offset {idc.get('grab_offset_s', float('nan')):.6f} s = midpoint to the "
                      f"previous frame): grab PTS {v['grab_pts_s']}, same frame {v.get('same_frame_pts')}, identical {v['identical']}, "
                      f"max |diff| {v['max_abs_diff']}, mean |diff| {v['mean_abs_diff']:.4f}, pixels differing {v['frac_pixels_differ']:.2%}"
                      for k, v in idc.items() if k == "vs_grab_cpu") + "."
          + (f" A first attempt with offset PTS − 1 ms landed on the previous frame (PTS {idc['first_attempt_offset_pts_minus_1ms']['grab_pts_s']}, "
             f"0.37 ms earlier; mean |diff| {idc['first_attempt_offset_pts_minus_1ms']['mean_abs_diff']:.2f}) — the stream has frames < 1 ms "
             "apart, see below." if idc.get("first_attempt_offset_pts_minus_1ms") else ""),
          f"- PTS spacing: {meta.get('pts_spacing', {}).get('n_lt_1ms', '?')} of {ds.get('frames_decoded')} consecutive frame "
          f"pairs are < 1 ms apart (median {meta.get('pts_spacing', {}).get('median_ms', float('nan')):.1f} ms, max "
          f"{meta.get('pts_spacing', {}).get('max_ms', float('nan')):.1f} ms): Reolink PTS are arrival times in bursts, so the "
          "renderer joins detections to frames by PTS at 1 µs.", ""]
    L += ["## Detections", "",
          f"- {pl.get('detections_total_floor')} boxes at conf ≥ {CONF_FLOOR}, {pl.get('detections_025')} at ≥ 0.25; frames "
          f"with ≥ 1 box at 0.25: {pl.get('frames_with_det_025')} / {pl.get('frames')} "
          f"({1 - pl.get('frac_frames_no_det_025', float('nan')):.1%}).",
          "- Per-frame count at 0.25: " + ", ".join(f"{k}: {v}" for k, v in pl.get("count_025_frame_distribution", {}).items()) + ".",
          "- Tables: `per_second.csv` (median count at 0.25 / 0.5 over the second's frames, max conf), `per_5s.csv`.", "",
          "## YOLO count vs WISER outside-count per 5-s bin (plausibility, not accuracy)", "",
          f"Bins with both: {pl.get('n_bins')} ({pl.get('n_bins_no_wiser')} bins without any located tag excluded). "
          f"Mean WISER outside {pl.get('wiser_outside_mean', float('nan')):.2f}, mean YOLO count "
          f"{pl.get('yolo_count_mean', float('nan')):.2f}; YOLO − WISER mean {pl.get('diff_mean', float('nan')):.2f}, median "
          f"{pl.get('diff_median', float('nan')):.2f}, mean |·| {pl.get('diff_abs_mean', float('nan')):.2f}; Spearman ρ "
          f"{pl.get('spearman_rho') if pl.get('spearman_rho') is None else round(pl['spearman_rho'], 3)}; bins with YOLO = 0 while "
          f"WISER ≥ 1: {pl.get('frac_yolo0_wiser_ge1', float('nan')):.1%}; YOLO > WISER: {pl.get('frac_yolo_gt_wiser', float('nan')):.1%}; "
          f"YOLO = WISER: {pl.get('frac_yolo_eq_wiser', float('nan')):.1%}; YOLO < WISER: {pl.get('frac_yolo_lt_wiser', float('nan')):.1%}.", "",
          "| YOLO − WISER | bins |", "|---:|---:|"]
    L += [f"| {k} | {v} |" for k, v in pl.get("diff_distribution", {}).items()]
    L += ["", "| WISER outside | bins | mean YOLO count | share of bins with YOLO = 0 |", "|---:|---:|---:|---:|"]
    L += [f"| {k} | {v['bins']} | {v['yolo_mean']:.2f} | {v['yolo_zero_frac']:.1%} |" for k, v in pl.get("by_wiser_outside", {}).items()]
    L += ["", "Reading guide: WISER counts tagged animals outside the two houses anywhere in the paddock (all six animals "
          "were tagged on night 09-06; the untagged females arrived 09-11). CH01 covers ≈ 68 % of the paddock and an "
          "animal in view can be hidden by grass, so WISER is not ground truth for CH01: YOLO below WISER can be correct "
          "(animal out of view or occluded) or a miss; YOLO above WISER can only be false or duplicate boxes, or an animal "
          "WISER places inside the 14-in house buffer. WISER positions carry ~4–7 in jitter. The 5-s median smooths "
          "single-frame flicker.", "",
          "## Review video and clips (for the user; the agent did not look at them)", "",
          f"- `review_10min.mp4`: {meta['review_window']['start']} → {meta['review_window']['end']} (field-PC), the 10-min "
          f"window of the hour with the highest mean WISER outside-count ({meta['review_window']['mean']:.2f}); "
          f"{rr.get('frames_written')} / {rr.get('frames_expected')} frames written ({rr.get('frames_unmatched_pts')} without a "
          f"PTS match), {rr.get('bytes', 0) / 1e6:.0f} MB, 3840 × 1080 H.264 20 fps, render {rr.get('seconds')} s.",
          f"- Step-3 clips (`review_clips/`, index `review_clips/index.html`, verdict sheet `review_clips/review_template.csv`), "
          "chosen by rule on the 5-s bins (plan amendment); a category without a qualifying window is listed as such:", "",
          "| file | category | start → end (field-PC) | frames | mean WISER | mean YOLO | rule | rule value |",
          "|---|---|---|---|---:|---:|---|---|"]
    for r in meta.get("clips", []):
        L.append(f"| {r['file'] or '–'} | {r['category']} | {r['start']} → {r['end']} | {r['frames']} | {r['mean_wiser']} | "
                 f"{r['mean_yolo']} | {r['rule']} | {r['rule_value']} |")
    fsp = run / "fixed_spots" / "fixed_spots.csv"
    if fsp.is_file():
        sp = pd.read_csv(fsp)
        info = json.loads((run / "fixed_spots" / "fixed_spots.json").read_text(encoding="utf-8"))
        L += ["", "## Fixed spots (diagnostic added after results at the user's request; plan amendment B)", "",
              "From the cached detections only (YOLO not rerun), driver `cv/cv_field/c1_yolo_fixed_spots.py`. Occupancy = "
              f"share of the {info['n_frames']} frames with a box centre (conf ≥ {info['conf']}) in a {info['cell_px']}-px cell; "
              f"cells ≥ {info['occ_min']:.0%} ({info['n_cells_ge_min']} cells) joined 8-connected into {info['n_components']} "
              f"spots, ranked, at most {info['max_spots']} kept. Cells named in the user's review: "
              + "; ".join(f"x {c['x0']}–{c['x0'] + info['cell_px']} / y {c['y0']}–{c['y0'] + info['cell_px']} {c['occupancy']:.1%}"
                          for c in info["user_cells"]) + ". **No conclusion here about what the spots are** — locator, "
              "heatmap, crops and the verdict sheet are in `fixed_spots/` (`index.html`, `fixed_spots_review.csv`, "
              "`fn_notes.txt` for the misses).", "",
              "| spot | pano centre (x, y) | occupancy | median conf | median box w × h | centre SD x / y (px) | cells |",
              "|---:|---|---:|---:|---|---|---:|"]
        L += [f"| {r.spot_id} | {r.cx_median:.0f}, {r.cy_median:.0f} | {r.occupancy:.1%} | {r.conf_median:.2f} | "
              f"{r.w_median:.0f} × {r.h_median:.0f} | {r.cx_sd:.1f} / {r.cy_sd:.1f} | {r.n_cells} |" for r in sp.itertuples()]
    L += ["", "## Definitions", "",
          "Units: upright pano pixels (7680 × 2160); times field-PC local (EDT). $k$ = frame, $b$ = 5-s WISER bin.", "",
          "### Frame time",
          "$$ t_k = t_{file\\,start} + PTS_k $$ **Text:** file-name start plus the frame's presentation time (ffmpeg "
          "`-copyts`, showinfo); the stream's own start may be offset ≤ ~1 min from the name, as for every stream.", "",
          "### Per-frame count at cut $c$",
          "$$ n_k(c)=\\#\\{\\text{boxes in frame }k:\\ conf\\ge c\\} $$ **Text:** YOLO boxes kept at $c$ (0.25 or 0.5).", "",
          "### YOLO count per 5-s bin",
          "$$ Y_b=\\operatorname{median}_{k\\in b} n_k(0.25) $$ **Text:** typical number of boxes over the ~100 frames of "
          "the bin; robust to single-frame flicker. $b=\\lfloor (t_k + 4\\,h)_{UTC\\ epoch}/5\\rfloor$.", "",
          "### WISER outside-count",
          "$$ W_b=\\#\\{\\text{tags located in }b\\text{ with median position outside both house rectangles grown by 14 in}\\} $$ "
          "**Text:** tagged animals outside the houses (`select_pano_targets.bin_table` on `c3_bins5.pkl`); missing when no "
          "tag is located in $b$.", "",
          "### Plausibility summaries",
          "$$ D_b = Y_b - W_b,\\quad \\rho = \\mathrm{Spearman}(Y_b, W_b),\\quad f_{miss}=\\frac{\\#\\{b: Y_b=0,\\,W_b\\ge1\\}}{\\#b},"
          "\\quad f_{over}=\\frac{\\#\\{b: Y_b>W_b\\}}{\\#b} $$ over the bins with both values. **Text:** agreement of the "
          "two counts; not accuracy (no ground truth).", "",
          "### Clip rules", "Window = 12 consecutive bins (60 s), all with ≥ 1 frame and a WISER count; mean over its bins. "
          "agree-many: max $\\bar W$ s.t. $\\overline{|D|}\\le1$; wiser-zero: $W_b=0\\ \\forall b$, max $\\bar Y$; yolo-miss: "
          "max $\\#\\{b: Y_b=0, W_b\\ge2\\}$; yolo-excess: max $\\#\\{b: Y_b>W_b+1\\}$; random: uniform, seed 0. No overlap; "
          "ties → earlier.", "",
          "### Cell and spot occupancy (fixed-spot diagnostic)",
          "$$ O_c=\\frac{\\#\\{k:\\ \\exists\\ \\text{box with } conf\\ge0.25,\\ \\text{centre}\\in c\\}}{N_{frames}},\\quad "
          "O_S=\\frac{\\#\\{k:\\ \\exists\\ \\text{box centre}\\in \\bigcup_{c\\in S} c\\}}{N_{frames}} $$ "
          "**Text:** share of the hour's frames with a box centre in a 40-px cell $c$ / in spot $S$ (8-connected cells "
          "with $O_c\\ge0.05$). Range [0, 1]; the number alone does not tell a resting animal from a fixed "
          "object. Centre SD = population SD of the box "
          "centres in the spot (px).", "",
          "## Rerun", "", "```", f"C:/Users/Cornell/.conda/envs/cv/python.exe cv/cv_field/c1_yolo_video_test.py --run "
          f"{run.as_posix()} --steps tables media report", "```", ""]
    rdir = REPO / "results" / COHORT / DIRECTION / "reports"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / REPORT_NAME).write_text("\n".join(L), encoding="utf-8")
    ptr = {"run_dir": str(run.resolve()), "cohort": COHORT, "direction": DIRECTION, "analysis": "c1yolo_video",
           "driver": "cv/cv_field/c1_yolo_video_test.py", "report": REPORT_NAME,
           "plan": "implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md", "video": meta["video"],
           "weights": meta["weights"], "weights_sha256": meta.get("weights_sha256"), "git_commit": meta.get("git_commit"),
           "review_video": "review_10min.mp4", "review_clips_index": "review_clips/index.html"}
    (rdir / POINTER_NAME).write_text(json.dumps(ptr, indent=2) + "\n", encoding="utf-8")
    return rdir / REPORT_NAME


def run_all(args) -> int:
    ff, ffprobe = gf.find_ffmpeg()
    if args.hour_only:
        tab, _ = step_hour(None, ffprobe)
        print(tab.drop(columns=["path"]).to_string())
        return 0
    ver = json.loads((BACKUP / "VERIFY.json").read_text(encoding="utf-8"))
    if not ver.get("pass"):
        raise SystemExit("step-0 backup not verified — refusing")
    if args.run:
        run = Path(args.run)
    else:
        sys.path.insert(0, str(REPO / "common"))
        import output_paths as op
        run = op.run_dir(NAME, COHORT, make_figures=False)
    mp = run / "run.json"
    meta = json.loads(mp.read_text(encoding="utf-8")) if mp.is_file() else {}
    tab, wb = step_hour(run, ffprobe)
    if "video" not in meta:
        ch = tab[tab["chosen"]]
        if ch.empty:
            raise SystemExit("no eligible complete candidate hour")
        r = ch.iloc[0]
        import torch
        import ultralytics
        meta.update({"plan": "implementation_plan/2026-10-05-c1-yolo-transfer-sam3.md", "video": r["path"],
                     "video_name": r["file"], "video_bytes": int(r["bytes"]), "probe_duration_s": float(r["probe_duration_s"]),
                     "mean_wiser_outside": float(r["mean_wiser_outside"]), "weights": WEIGHTS.as_posix(),
                     "weights_sha256": sha256(WEIGHTS), "backup_verified_at": ver.get("verified_at"),
                     "versions": {"ultralytics": ultralytics.__version__, "torch": torch.__version__,
                                  "ffmpeg": subprocess.run([ff, "-version"], capture_output=True, text=True).stdout.splitlines()[0]},
                     "git_commit": git_commit(), "started": datetime.now().isoformat(timespec="seconds"),
                     "params": {"imgsz": IMGSZ, "conf_floor": CONF_FLOOR, "cuts": CUTS, "draw_cut": DRAW_CUT,
                                "out": [OUT_W, OUT_H], "fps_out": FPS_OUT}})
        s, e = file_span(Path(r["path"]))
        p5w = wb[["b5", "n_outside"]].rename(columns={"n_outside": "wiser_outside"})
        bw = best_window(p5w, REVIEW_BINS, "wiser_outside", pd.Timestamp(s), pd.Timestamp(e))
        meta["review_window"] = {"b0": bw["b0"], "b1": bw["b1"], "mean": bw["mean"], "coverage": bw["coverage"],
                                 "start": f"{bin_start_local(bw['b0']):%Y-%m-%d %H:%M:%S}",
                                 "end": f"{bin_start_local(bw['b1']):%Y-%m-%d %H:%M:%S}"}
        mp.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    print(f"run -> {run}\nvideo {meta['video_name']}; review window {meta['review_window']}")
    steps = args.steps
    t0 = time.perf_counter()
    if "detect" in steps:
        step_detect(run, meta, ff)
        mp.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    if "identity" in steps:
        identity_check(run, meta, ff, int(meta["identity_check"]["frame"]))
        mp.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    if "tables" in steps:
        step_tables(run, meta, wb)
        mp.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    if "media" in steps:
        step_media(run, meta, ff, wb)
        mp.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    meta.setdefault("runtime_s", {})[",".join(steps)] = round(time.perf_counter() - t0, 1)
    mp.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    if "report" in steps:
        p = write_report(run, meta, tab)
        print(f"report -> {p}")
    return 0


# ----------------------------------------------------------------------------------------------- selftest
def selftest() -> int:
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    ff, ffprobe = gf.find_ffmpeg()
    # time / bins
    t = pd.Timestamp("2026-09-06 22:00:02.5")
    rec("b5: local EDT -> UTC/5 and back", bin_start_local(b5_of(t)) == pd.Timestamp("2026-09-06 22:00:00"))
    rec("PTS key keeps frames 0.37 ms apart distinct", pts_key(1310.176811) != pts_key(1310.1771778))
    # hour table: tie -> earlier; truncated -> next; handling overlap excluded
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "2026-09-06" / "CH01").mkdir(parents=True)
        names = ["CH01_2026-09-06_21-00-00_to_22-00-00.mp4", "CH01_2026-09-06_22-00-00_to_23-00-01.mp4",
                 "CH01_2026-09-06_23-00-01_to_00-00-01.mp4"]
        for n in names:
            (root / "2026-09-06" / "CH01" / n).write_bytes(b"x")
        rows = []
        for h0, val in ((21, 2), (22, 2), (23, 3)):
            s = pd.Timestamp(f"2026-09-06 {h0}:00:05")
            for i in range(700):
                rows.append({"b5": b5_of(s) + i, "n_tagged": 5, "n_outside": val, "tags_outside": ""})
        wb = pd.DataFrame(rows)
        files = [root / "2026-09-06" / "CH01" / n for n in names]
        tab = hour_table(files, wb, [(datetime(2026, 9, 6, 23, 30), datetime(2026, 9, 6, 23, 40), "round")], None)
        tab["complete"] = True
        tab["chosen"] = False
        first = tab[tab["eligible"] & tab["complete"]].iloc[0]
        rec("hour: handling overlap excluded, tie -> earlier hour", first["file"] == names[0]
            and not tab.set_index("file").loc[names[2], "eligible"], f"{first['file']}")
        try:
            hour_table([root / "2026-09-05" / "CH01" / "CH01_2026-09-05_22-00-00_to_23-00-00.mp4"], wb, [], None)
            rec("refuses a frozen-test-night file", False)
        except SystemExit:
            rec("refuses a frozen-test-night file", True)
    # best window
    p5 = pd.DataFrame({"b5": np.arange(1000, 1100), "v": np.r_[np.zeros(40), np.ones(20) * 3, np.zeros(40)]})
    bw = best_window(p5, 12, "v", bin_start_local(1000), bin_start_local(1100))
    rec("best window: first all-3 window, ties -> earlier", bw["b0"] == 1040 and bw["mean"] == 3.0, str(bw))
    # clip selection
    n = 400
    y = np.zeros(n); x = np.zeros(n)
    x[0:60] = 4; y[0:60] = 4                                 # agree-many candidates
    x[100:112] = 0; y[100:112] = 2                           # wiser-zero with YOLO 2
    x[150:162] = 3; y[150:162] = 0                           # yolo-miss
    x[200:212] = 0; y[200:212] = 3                           # yolo-excess (and also wiser-zero, but lower priority)
    x[200:212] = 1
    p5c = pd.DataFrame({"b5": np.arange(n), "n_frames": 100, "yolo_count": y, "wiser_outside": x})
    win = eligible_windows(p5c, 12)
    sel = select_clips(win, [(20, 40)], seed=0)
    cats = [c["category"] for c in sel]
    spans = [(c["b0"], c["b1"]) for c in sel if c["b0"] is not None]
    rec("clips: 6 entries in the fixed order", cats == ["agree-many", "agree-many", "wiser-zero", "yolo-miss", "yolo-excess",
                                                         "random"], str(cats))
    rec("clips: agree-many avoid the 10-min window and each other",
        sel[0]["b0"] == 0 and sel[1]["b0"] == 40 and sel[0]["rule_value"] == 4.0, str(spans[:2]))
    rec("clips: wiser-zero = highest mean YOLO with WISER 0", sel[2]["b0"] == 100, str(sel[2]))
    rec("clips: yolo-miss / yolo-excess windows", sel[3]["b0"] == 150 and sel[3]["rule_value"] == 12
        and sel[4]["b0"] == 200 and sel[4]["rule_value"] == 12, f"{sel[3]['b0']} {sel[4]['b0']}")
    allspans = spans + [(20, 40)]
    rec("clips: no overlaps", all(not overlaps(a, b, [s for s in allspans if s != (a, b)]) for a, b in allspans))
    sel2 = select_clips(eligible_windows(p5c.assign(wiser_outside=1.0, yolo_count=1.0), 12), [], seed=0)
    rec("clips: missing categories reported as none, not substituted",
        [c["category"] for c in sel2 if c["b0"] is None] == ["wiser-zero", "yolo-miss", "yolo-excess"], str(sel2))
    # plausibility
    pl = plausibility(pd.DataFrame({"yolo_count": [0, 1, 2, 3, np.nan], "wiser_outside": [1, 1, 2, 2, 1]}))
    rec("plausibility: fractions + spearman", pl["n_bins"] == 4 and pl["frac_yolo0_wiser_ge1"] == 0.25
        and pl["frac_yolo_gt_wiser"] == 0.25 and pl["spearman_rho"] > 0.8, str(pl))
    # end to end on a synthetic stored-rotated clip with a stub detector
    W0, H0 = gf.STORED["CH01"]
    gf.STORED["CH01"] = (90, 320)                            # stored portrait 90 x 320 -> upright 320 x 90
    try:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            vid = run / "CH01_2026-09-06_22-00-00_to_22-00-12.mp4"
            subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=90x320:rate=20:duration=12",
                            "-c:v", "libx265", "-x265-params", "keyint=40:min-keyint=40:scenecut=0:log-level=error",
                            "-pix_fmt", "yuv420p", str(vid)], check=True)
            w, h = gf.upright_size("CH01")

            def stub(imgs):
                return [(np.array([[10.0, 10, 40, 40], [100, 20, 130, 50]]), np.array([0.9, 0.3])) for _ in imgs]
            res = detect_pass(vid, stub, run, batch=4, keep_frame=50, log_every=0)
            fr = res["frames"]
            rec("detect pass: 240 frames, PTS for each, monotone", len(fr) == 240 and fr["pts_s"].notna().all()
                and fr["pts_s"].is_monotonic_increasing, f"{len(fr)} frames")
            d = pd.read_csv(run / "detections.csv")
            rec("detect pass: boxes cached per frame", len(d) == 480 and d["frame"].nunique() == 240)
            img, p2, _ = gf.grab(ff, vid, float(fr.loc[50, "pts_s"]) - 0.001, "CH01", "exact", "cpu")
            dd = np.abs(img.astype(int) - res["kept"].astype(int))
            rec("pixel identity with grab_frames.grab (cpu, same frame)", abs(p2 - fr.loc[50, "pts_s"]) < 1e-3 and dd.max() == 0,
                f"max diff {dd.max()}")
            s, _ = file_span(vid)
            fr["t_pc"] = [(pd.Timestamp(s) + pd.Timedelta(seconds=float(p))).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] for p in fr["pts_s"]]
            d = d.merge(fr[["frame", "pts_s", "t_pc"]], on="frame")
            pf = per_frame_counts(fr, d)
            rec("per-frame counts at 0.25 / 0.5", (pf["n_025"] == 2).all() and (pf["n_050"] == 1).all())
            ps = per_second(pf)
            rec("per-second table: 12 seconds of 20 frames", len(ps) == 12 and (ps["n_frames"] == 20).all(), str(len(ps)))
            wbs = pd.DataFrame({"b5": [b5_of(pd.Timestamp(s)) + i for i in range(3)], "n_tagged": 5, "n_outside": [2, 1, 0],
                                "tags_outside": ""})
            p5s = per_5s(pf, wbs)
            rec("per-5-s: 3 bins, YOLO median 2 vs WISER 2/1/0", len(p5s) == 3 and (p5s["yolo_count"] == 2).all()
                and p5s["diff"].tolist() == [0, 1, 2], str(p5s[["yolo_count", "wiser_outside"]].values.tolist()))
            wiser = dict(zip(p5s["b5"], p5s["wiser_outside"]))
            st = render_window(ff, vid, s, pd.Timestamp(s) + pd.Timedelta(seconds=5), pd.Timestamp(s) + pd.Timedelta(seconds=10),
                               fr, d, wiser, run / "clip.mp4", out_w=320, out_h=90, src_w=320)
            n_out = int(subprocess.run([ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                                        "stream=nb_read_frames", "-of", "csv=p=0", str(run / "clip.mp4")],
                                       capture_output=True, text=True).stdout.strip() or 0)
            rec("render: every frame of the window, PTS-joined, H.264 written", st["frames_written"] == 100
                and st["frames_unmatched_pts"] == 0 and n_out == 100, f"{st} read {n_out}")
            cd = run / "rc"
            cd.mkdir()
            write_index(cd, [{"file": "1_random_22-00-05.mp4", "category": "random", "start": "a", "end": "b", "frames": "1-2",
                              "mean_wiser": 1, "mean_yolo": 1, "rule": "r", "rule_value": 0, "src": "1_random_22-00-05.mp4"}],
                        {"file": "review_10min.mp4", "category": "10-min", "start": "a", "end": "b", "frames": "", "mean_wiser": 1,
                         "mean_yolo": 1, "rule": "r", "rule_value": 1, "src": "../review_10min.mp4"})
            h_ = (cd / "index.html").read_text(encoding="utf-8")
            rec("index.html embeds both videos", h_.count("<video") == 2 and "../review_10min.mp4" in h_)
    finally:
        gf.STORED["CH01"] = (W0, H0)
    print(("PASS" if ok else "FAIL") + " — c1_yolo_video_test self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--hour-only", action="store_true")
    ap.add_argument("--run", default=None)
    ap.add_argument("--steps", nargs="+", default=["detect", "tables", "media", "report"],
                    choices=["detect", "identity", "tables", "media", "report"])
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    return run_all(a)


if __name__ == "__main__":
    sys.exit(main())
