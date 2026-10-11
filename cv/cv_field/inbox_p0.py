r"""inbox_p0.py — in-box cameras CH07 / CH08, phase 0, parts A and B (cohort 3, 2026c):
A. colour segments found numerically (I-frame chroma scan, edges refined at full frame rate, matched to the colour log);
B. WISER box entry / exit events with the operator's parameters, the 09-05 ground-truth check, per-second house
   occupancy, per-minute in-house positions (house frame, inches) and the camera <-> house check.
Part C (the identity click page) is cv/cv_field/inbox_identity_page.py, which reads this run.

Specification: implementation_plan/2026-10-10-inbox-ch0708-wiser-identity-p0.md (pre-registered) + its dated amendments.

Inputs (read-only): F:/3rd_rat/<YYYY-MM-DD>/CH07|CH08/*.mp4 (2560 x 1920 H.264, 20 fps, GOP 2 s, no B-frames, hourly,
field-PC local names); the default WISER tracks (wiser/src/default_tracks.py, $OUT/2026c/wiser_default_tracks/); the
house rectangles of wiser/configs/wiser_rois.json; the accepted WISER -> paddock map
($OUT/2026c/cv_field_wiser_assist_p0_20261005_2211/mapping.json); the house poses (house_2: calibration centre
(342.4, 117.7) in, ridge 92.0 deg; house_1: cv/configs/house1_cohort_pose_2026c.json); cv/configs/cohort3_lid_events.json.

Definitions (also in the report):
  chroma c = mean over the frame decimated by 4 (nearest pixel, 640 x 480 of 2560 x 1920) of |R-G| + |G-B| (8-bit RGB).
  IR / colour threshold thr = geometric mid-point of the LARGEST gap in log10(max(c, floor)) over all scanned I-frames of
  09-09 -> 09-11 19:40, both cameras pooled (as sam3_vs_yolo_c1.ir_threshold); colour if c >= thr. floor = 1e-2 (plan
  amendment 6, after results: with the pre-registered 1e-4 the largest gap fell between two isolated IR I-frames of
  rounding-level chroma; the pre-registered threshold and its consequences are kept in colour_threshold.json).
  colour run = maximal sequence of consecutive colour I-frames of one camera; its start is refined on every frame of
  [first colour I-frame - 3 s, first colour I-frame] (start = first frame of the colour stretch that reaches the first
  colour I-frame), its end on [last colour I-frame, + 3 s] (end = first IR frame after the colour stretch = OFF instant);
  runs whose refined intervals are < 1 s apart are merged. Frame time = file-name start + PTS (field-PC local, naive).
  frame-difference energy e_k = mean |g_k - g_(k-1)| over the 320 x 240 area-averaged grey image of consecutive I-frames
  of one file (8-bit units; 2 s apart).
  house membership per fix: inside the house_h rectangle of wiser_rois.json grown by 15 in on every side
  (wiser_analysis_utils._rect_membership(..., buffer_in=15)[1]), on the default track position (x, y).
  6-s smoothing: per animal and second s, f_h(s) = (fixes in [s-3, s+3) inside house_h) / (all fixes in [s-3, s+3));
  raw state = house_h if f_h(s) >= 0.5, 'out' if a fix exists and no f_h >= 0.5, 'unknown' if no fix in the window.
  20-s minimum dwell: a change of state is accepted only when the new state lasts >= 20 s; shorter runs keep the
  previous state; unknown stretches < 20 s are bridged with the state held; a longer unknown stretch makes the state
  unknown until a known run >= 20 s, and a change across it is an event flagged with its gap length.
  event = a change of the cleaned state: exit house_h when leaving h, enter house_h when arriving in h (1-s resolution).

Usage (cv env C:/Users/Cornell/.conda/envs/cv/python.exe with PYTHONIOENCODING=utf-8; the WISER phases also run in base):
  python cv/cv_field/inbox_p0.py --selftest
  python cv/cv_field/inbox_p0.py --run <run dir or 'new'> --phases scan segments wiser inhouse camhouse report [--workers 8]
Output: $OUT/2026c/cv_field_inbox_p0_<ts>/ (scan/, scan_keyframes.csv.gz, colour_threshold.json, colour_segments.csv,
        colour_log_rows.csv, control_hours.csv, box_events.csv, box_occupancy_1s.csv.gz, check_0905.csv,
        inhouse_minutes.csv.gz, camera_house_check.csv, run.json) + results/2026c/cv_field/reports/cv_field_inbox_p0_2026c.md,
        pointer run_manifest_inbox_p0_2026c.json. The agent never looks at frames.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time as _time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(REPO / "wiser" / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

COHORT, DIRECTION, NAME = "2026c", "cv_field", "cv_field_inbox_p0"
PLAN = "implementation_plan/2026-10-10-inbox-ch0708-wiser-identity-p0.md"
REPORT_NAME = f"cv_field_inbox_p0_{COHORT}.md"
POINTER_NAME = f"run_manifest_inbox_p0_{COHORT}.json"
OUT_ROOT = Path(os.environ.get("FIELD2026_ANALYSIS_OUT_ROOT", "D:/Field2026_analysis_out"))
VIDEO_ROOT = Path("F:/3rd_rat")
CAMS = ("CH07", "CH08")
CAM_HOUSE = {"CH07": "house_2", "CH08": "house_1"}           # plan facts (09-07 evidence); checked in B4, not decided
SCAN_DAYS = ("2026-09-09", "2026-09-10", "2026-09-11")
SCOPE_END = datetime(2026, 9, 11, 19, 40)                     # population change (5 females released)
TRACK_START = datetime(2026, 8, 30, 19, 0)                    # release
FW, FH = 2560, 1920
CHROMA_STEP = 4
GREY_W, GREY_H = 320, 240
LOG_FLOOR = 1e-4            # pre-registered (as sam3_vs_yolo_c1)
LOG_FLOOR_AMENDED = 1e-2    # amendment 6 (after results): IR GOPs carry rounding-level chroma (<= 0.53), see the report
EDGE_S = 3.0
MERGE_S = 1.0
# control hours (pre-registered with the code, before any scan result): per camera 3 days drawn from 08-31 .. 09-08
# (full video days before the first colour insert of 09-09 19:10), 2 daylight hours 08..18 each (colour needs daylight)
CONTROL_SEED = 20261010
CONTROL_DAYS = tuple(f"2026-{d}" for d in ("08-31", "09-01", "09-02", "09-03", "09-04", "09-05", "09-06", "09-07", "09-08"))
CONTROL_HOURS = tuple(range(8, 19))
FILE_RE = re.compile(r"^(CH0\d)_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})(?:_to_(\d{2})-(\d{2})-(\d{2}))?\.mp4$")
TZ = ZoneInfo("America/New_York")
FMT = "%Y-%m-%d %H" + ":" + "%M" + ":" + "%S"

# B parameters (operator, validated 09-05; plan B1)
DILATE_IN = 15.0
SMOOTH_S = 6
MIN_DWELL_S = 20
HOUSES = ("house_1", "house_2")
LABELS = ("SF07", "SF08", "SF09", "SF10", "SF11", "SF12")
SECOND_TAG = "SF12_tag12376"
# SF11's tag record (plan amendments 12 + 13, confirmed by the user 2026-10-11; COHORT3_DATA_GUIDE section 6): tag 305a died
# 09-02 00:03, 3058 mounted 09-02 08:15 -> tag DROPOUT 1, animal present. Tag 3058 rode on the IMPLANT: at 09-07 06:10:45 the
# implant fell off with the tag on it, so the rat was in the paddock UNTAGGED until it was taken out at the AM round (dropout
# 2; the default tracks' m_off_animal flag on 3058's fixes 06:10:45 -> 08:20 is correct: they are the implant lying in
# house_2, last fix 08:20). From 08:20 to the scope end SF11 is ABSENT; the paddock held five animals, all tagged.
SF11_UNTAGGED = ((datetime(2026, 9, 2, 0, 3), datetime(2026, 9, 2, 8, 15)), (datetime(2026, 9, 7, 6, 10, 45), datetime(2026, 9, 7, 8, 20)))
SF11_ABSENT = ((datetime(2026, 9, 7, 8, 20), SCOPE_END),)
HOUSE_POSE = {"house_2": {"centre": (342.4, 117.7), "ridge_deg": 92.0, "source": "calibration house_check 09-18 (house_2 never moved)"},
              "house_1": None}  # filled from cv/configs/house1_cohort_pose_2026c.json
MAPPING_JSON = OUT_ROOT / "2026c" / "cv_field_wiser_assist_p0_20261005_2211" / "mapping.json"
LID_EVENTS = REPO / "cv" / "configs" / "cohort3_lid_events.json"
INHOUSE_MIN_S = 30          # a minute row needs >= 30 s of the cleaned state in that house
BODY_IN = (62.55 / 2.54, 45.72 / 2.54)   # house body 62.55 x 45.72 cm, long side along the ridge (CAMERA_GEOMETRY_2026c.md 4)
FOOTPRINT_TOL_IN = 3.0      # descriptive column in_body_footprint: minute mean within the body rectangle grown by 3 in

# 09-05 ground truth (operator, field2026-sync from-field/2026-09-10_ir-identity-label-sources.md; plan facts)
GT_0905 = ([("SF07", "house_2", "exit", "08:47:08"), ("SF08", "house_2", "exit", "08:47:08"), ("SF09", "house_2", "exit", "08:47:08"),
            ("SF10", "house_2", "exit", "08:47:08"), ("SF11", "house_2", "exit", "08:47:08"), ("SF12", "house_2", "exit", "08:47:08"),
            ("SF09", "house_2", "enter", "09:49:49"), ("SF07", "house_2", "enter", "09:49:51"), ("SF11", "house_2", "enter", "09:49:58"),
            ("SF10", "house_2", "enter", "09:50:01"), ("SF12", "house_2", "enter", "09:50:15"), ("SF08", "house_1", "enter", "09:50:13")])
GT_ENTRY_ORDER = ("SF09", "SF07", "SF11", "SF10", "SF12")
GT_TOL_S = 30.0

# The colour log (recording repo COLOUR_SAMPLING_LOG_cohort3.md, read 2026-10-10), transcribed. op = operator clock
# (ran ~35 s fast on 09-09); 'slot' = a planned time without an operator note; 'window' = a round with no time.
COLOUR_LOG = [
    {"row": 1, "date": "2026-09-09", "kind": "test flash", "cams": "CH07", "op_on": "19:11", "op_off": "~19:11", "video": "19:10:25.8-19:10:39.3 (13.5 s)"},
    {"row": 2, "date": "2026-09-10", "kind": "AM placement", "cams": "CH07+CH08", "window": ("07:17", "08:40"), "video": ""},
    {"row": 3, "date": "2026-09-10", "kind": "extra colour->IR transition", "cams": "CH07/CH08 (tbc)", "op_off": "09:11", "note": "ON before 09:11", "video": ""},
    {"row": 4, "date": "2026-09-10", "kind": "flash 10:00 (planned, no note)", "cams": "CH07, CH08", "slot": "10:00", "video": ""},
    {"row": 5, "date": "2026-09-10", "kind": "flash 11:30 (planned, no note)", "cams": "CH07, CH08", "slot": "11:30", "video": ""},
    {"row": 6, "date": "2026-09-10", "kind": "flash (midday) pile #1", "cams": "CH07", "op_on": "12:27", "op_off": "~12:27:20", "video": "12:27:03-12:27:25 (22 s)"},
    {"row": 7, "date": "2026-09-10", "kind": "flash (midday) pile #2", "cams": "CH07/CH08 (tbc)", "op_on": "12:52", "op_off": "~12:52:08", "video": ""},
    {"row": 8, "date": "2026-09-10", "kind": "flash (afternoon) pile #3", "cams": "CH07/CH08 (tbc)", "op_on": "13:52", "op_off": "~13:52:08", "video": ""},
    {"row": 9, "date": "2026-09-10", "kind": "flash (afternoon) pile #4", "cams": "CH07/CH08 (tbc)", "op_on": "14:08", "op_off": "~14:08:08", "note": "typed 14:.8", "video": ""},
    {"row": 10, "date": "2026-09-10", "kind": "flash 14:33 pile #5", "cams": "CH07", "op_on": "14:33", "op_off": "~14:33:08", "video": ""},
    {"row": 11, "date": "2026-09-10", "kind": "flash 15:23 pile #6", "cams": "CH07", "op_on": "15:23", "op_off": "~15:23:08", "video": ""},
    {"row": 12, "date": "2026-09-10", "kind": "flash 16:30 pile #7", "cams": "CH07", "op_on": "16:30", "op_off": "~16:30:08", "video": ""},
    {"row": 13, "date": "2026-09-10", "kind": "flash 17:30 not done", "cams": "-", "video": ""},
    {"row": 14, "date": "2026-09-10", "kind": "PM placement tried, too dark (IR only)", "cams": "CH07+CH08", "op_on": "19:50", "note": "~19:50 tried", "video": ""},
    {"row": 15, "date": "2026-09-11", "kind": "colour segment ~09:40", "cams": "CH07/CH08 (tbc)", "op_on": "09:40", "video": ""},
    {"row": 16, "date": "2026-09-11", "kind": "colour segment ~10:00", "cams": "CH07/CH08 (tbc)", "op_on": "10:00", "video": ""},
    {"row": 17, "date": "2026-09-11", "kind": "flash 11:30 (planned, no note)", "cams": "CH07, CH08", "slot": "11:30", "video": ""},
    {"row": 18, "date": "2026-09-11", "kind": "flash 13:00 (planned, no note)", "cams": "CH07, CH08", "slot": "13:00", "video": ""},
    {"row": 19, "date": "2026-09-11", "kind": "flash 14:10", "cams": "CH07", "op_on": "14:10", "op_off": "~14:10:08", "video": ""},
    {"row": 20, "date": "2026-09-11", "kind": "flash 14:44", "cams": "CH07", "op_on": "14:44", "op_off": "~14:44:08", "video": ""},
    {"row": 21, "date": "2026-09-11", "kind": "flash 14:50", "cams": "CH07", "op_on": "14:50", "op_off": "~14:50:08", "video": ""},
    {"row": 22, "date": "2026-09-11", "kind": "flash 16:00 not done", "cams": "-", "video": ""},
    {"row": 23, "date": "2026-09-11", "kind": "colour 18:29 (flash or PM placement, tbc)", "cams": "CH07/CH08 (tbc)", "op_on": "18:29", "video": ""},
]
LOG_TOL_S = 120.0
OP_FAST_S = 35.0
WINDOW_PAD = (timedelta(minutes=5), timedelta(minutes=30))


# ----------------------------------------------------------------------------------------------- utilities
def git_commit(repo: Path) -> str:
    try:
        h = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30).stdout.strip()
        d = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"], capture_output=True,
                           text=True, timeout=30).stdout.strip()
        return h + ("+dirty" if d else "")
    except Exception:  # noqa: BLE001
        return "unknown"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def parse_name(name: str) -> tuple[str, datetime] | None:
    m = FILE_RE.match(name)
    if not m:
        return None
    cam, d, hh, mm, ss = m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5))
    return cam, datetime.fromisoformat(d) + timedelta(hours=hh, minutes=mm, seconds=ss)


def list_files(cam: str, day: str, root: Path = VIDEO_ROOT) -> list[tuple[Path, datetime]]:
    d = root / day / cam
    out = []
    if d.is_dir():
        for p in sorted(d.glob(f"{cam}_*.mp4")):
            r = parse_name(p.name)
            if r:
                out.append((p, r[1]))
    return sorted(out, key=lambda x: x[1])


def utc_ms_to_local(t_ms) -> pd.Series:
    return pd.to_datetime(pd.Series(t_ms), unit="ms", utc=True).dt.tz_convert(TZ).dt.tz_localize(None)


def chroma_rgb(rgb: np.ndarray) -> float:
    s = rgb.astype(np.int16)
    return float(np.mean(np.abs(s[..., 0] - s[..., 1]) + np.abs(s[..., 1] - s[..., 2])))


def frame_measures(frame) -> tuple[float, np.ndarray]:
    """(chroma on the 4x-decimated nearest-pixel RGB, 320 x 240 area-averaged grey float32) of one PyAV frame."""
    rgb = frame.reformat(width=frame.width // CHROMA_STEP, height=frame.height // CHROMA_STEP, format="rgb24",
                         interpolation="POINT").to_ndarray()
    g = frame.reformat(width=GREY_W, height=GREY_H, format="gray", interpolation="AREA").to_ndarray().astype(np.float32)
    return chroma_rgb(rgb), g


def log_gap_threshold(values, floor: float = LOG_FLOOR) -> dict:
    """Geometric mid-point of the largest gap in log10(max(c, floor)) over the pooled values (sam3_vs_yolo_c1 rule)."""
    v = np.sort(np.log10(np.maximum(np.asarray(values, float), floor)))
    u = np.unique(v)
    if u.size < 2:
        return {"thr": float("nan"), "rule": "degenerate (one value)", "n": int(v.size)}
    g = np.diff(u)
    k = int(np.argmax(g))
    thr = float(10 ** ((u[k] + u[k + 1]) / 2))
    return {"thr": thr, "rule": "geometric mid-point of the largest log10-chroma gap (floor 1e-4) of the pooled I-frames",
            "gap_lo": float(10 ** u[k]), "gap_hi": float(10 ** u[k + 1]), "gap_log10": float(g[k]),
            "second_gap_log10": float(np.sort(g)[-2]) if g.size > 1 else float("nan"),
            "n": int(v.size), "n_below": int((np.asarray(values, float) < thr).sum()),
            "n_above": int((np.asarray(values, float) >= thr).sum())}


# ----------------------------------------------------------------------------------------------- A. I-frame scan
def scan_file(path: str, start_iso: str, out_csv: str, stop_iso: str | None = None) -> dict:
    """Decode every key frame (packet-level: only key packets reach the decoder; packet index = frame index, no
    B-frames) -> per key frame chroma, mean grey, difference energy to the previous key frame of the file."""
    import av
    t0 = _time.time()
    start = datetime.fromisoformat(start_iso)
    stop = datetime.fromisoformat(stop_iso) if stop_iso else None
    rows, prev, idx, n_nodec = [], None, -1, 0
    with av.open(path) as c:
        s = c.streams.video[0]
        cc = s.codec_context
        tb = float(s.time_base)
        for pkt in c.demux(s):
            if pkt.size == 0:
                continue
            idx += 1
            if not pkt.is_keyframe:
                continue
            frames = cc.decode(pkt)
            if not frames:
                n_nodec += 1
                continue
            f = frames[-1]
            trel = float(f.pts * tb) if f.pts is not None else float(pkt.pts * tb)
            t = start + timedelta(seconds=trel)
            if stop is not None and t >= stop:
                break
            c_val, g = frame_measures(f)
            e = float(np.mean(np.abs(g - prev))) if prev is not None else float("nan")
            prev = g
            rows.append({"frame_idx": idx, "pts": int(f.pts if f.pts is not None else pkt.pts), "t_rel_s": round(trel, 6),
                         "time": t.strftime(FMT) + f".{t.microsecond // 1000:03d}", "chroma": round(c_val, 5),
                         "grey_mean": round(float(g.mean()), 3), "diff_energy": round(e, 4) if np.isfinite(e) else ""})
    df = pd.DataFrame(rows, columns=["frame_idx", "pts", "t_rel_s", "time", "chroma", "grey_mean", "diff_energy"])
    tmp = out_csv + ".tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, out_csv)
    return {"file": path, "n_key": len(df), "n_packets": idx + 1, "n_undecoded_key": n_nodec, "seconds": round(_time.time() - t0, 1)}


def _scan_job(args):
    try:
        return scan_file(*args)
    except Exception as ex:  # noqa: BLE001
        return {"file": args[0], "error": repr(ex)}


def control_choice() -> list[dict]:
    rng = np.random.default_rng(CONTROL_SEED)
    out = []
    for cam in CAMS:
        days = rng.choice(np.array(CONTROL_DAYS), size=3, replace=False)
        for d in sorted(days):
            for h in sorted(rng.choice(np.array(CONTROL_HOURS), size=2, replace=False)):
                out.append({"camera": cam, "date": str(d), "hour": int(h)})
    return out


def scan_jobs(run: Path, root: Path = VIDEO_ROOT) -> tuple[list[tuple], list[dict]]:
    jobs, inv = [], []
    for cam in CAMS:
        for day in SCAN_DAYS:
            for p, st in list_files(cam, day, root):
                if st >= SCOPE_END:
                    continue
                out = run / "scan" / cam / (p.stem + ".csv")
                inv.append({"set": "scan", "camera": cam, "file": p.as_posix(), "start": st.strftime(FMT), "csv": out.as_posix()})
                jobs.append((p.as_posix(), st.isoformat(), out.as_posix(), SCOPE_END.isoformat()))
    for ch in control_choice():
        for p, st in list_files(ch["camera"], ch["date"], root):
            if st.hour == ch["hour"]:
                out = run / "scan_control" / ch["camera"] / (p.stem + ".csv")
                inv.append({"set": "control", "camera": ch["camera"], "file": p.as_posix(), "start": st.strftime(FMT), "csv": out.as_posix()})
                jobs.append((p.as_posix(), st.isoformat(), out.as_posix(), None))
    return jobs, inv


def prefetch(path: str, chunk: int = 8 << 20) -> float:
    """Read a file once sequentially (into the OS file cache) so the decode workers do not compete for the disk head."""
    t0 = _time.time()
    with open(path, "rb", buffering=0) as f:
        while f.read(chunk):
            pass
    return _time.time() - t0


def phase_scan(run: Path, workers: int, ahead: int | None = None) -> None:
    """Many decode workers + ONE sequential prefetch reader: a job is handed to the pool only after its file was read
    through once (10 concurrent readers on the USB HDD gave 44 MB/s; one sequential reader ~270 MB/s), at most
    workers + ahead jobs outstanding so the cached files are not evicted."""
    from multiprocessing import Pool
    jobs, inv = scan_jobs(run)
    pd.DataFrame(inv).to_csv(run / "scan_inventory.csv", index=False)
    todo = [j for j in jobs if not Path(j[2]).exists()]
    for j in todo:
        Path(j[2]).parent.mkdir(parents=True, exist_ok=True)
    ahead = 2 if ahead is None else ahead
    print(f"[scan] {len(jobs)} files, {len(todo)} to do, {workers} workers, prefetch", flush=True)
    log = run / "scan_log.jsonl"
    done = 0
    with Pool(workers) as pool, open(log, "a", encoding="utf-8") as lf:
        pending = []
        for j in todo:
            while len(pending) >= workers + ahead:
                for a in [a for a in pending if a.ready()]:
                    pending.remove(a)
                    r = a.get()
                    done += 1
                    lf.write(json.dumps(r) + "\n")
                    lf.flush()
                    print(f"[scan] {done}/{len(todo)} {Path(r['file']).name} {r.get('n_key', r.get('error'))} {r.get('seconds', '')} s", flush=True)
                if len(pending) >= workers + ahead:
                    _time.sleep(0.5)
            pf = prefetch(j[0])
            print(f"[scan] prefetched {Path(j[0]).name} in {pf:.1f} s", flush=True)
            pending.append(pool.apply_async(_scan_job, (j,)))
        for a in pending:
            r = a.get()
            done += 1
            lf.write(json.dumps(r) + "\n")
            lf.flush()
            print(f"[scan] {done}/{len(todo)} {Path(r['file']).name} {r.get('n_key', r.get('error'))} {r.get('seconds', '')} s", flush=True)


# ----------------------------------------------------------------------------------------------- A. segments
def load_scan(run: Path, which: str = "scan") -> pd.DataFrame:
    inv = pd.read_csv(run / "scan_inventory.csv")
    inv = inv[inv["set"] == which]
    parts = []
    for r in inv.itertuples():
        p = Path(r.csv)
        if not p.exists():
            continue
        d = pd.read_csv(p)
        d["camera"], d["file"], d["file_start"] = r.camera, r.file, r.start
        parts.append(d)
    if not parts:
        return pd.DataFrame()
    kf = pd.concat(parts, ignore_index=True)
    kf["t"] = pd.to_datetime(kf["time"])
    kf["diff_energy"] = pd.to_numeric(kf["diff_energy"], errors="coerce")
    return kf.sort_values(["camera", "t", "frame_idx"]).reset_index(drop=True)


def colour_runs(is_colour: np.ndarray) -> list[tuple[int, int]]:
    """(first, last) positions of maximal runs of True in a time-ordered boolean array."""
    b = np.asarray(is_colour, bool)
    if not b.any():
        return []
    d = np.diff(np.concatenate([[0], b.astype(int), [0]]))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1))


def refine_start(frames: list[dict], thr: float, t_key: datetime) -> tuple[dict | None, str]:
    """frames: dicts (t, chroma, file, frame_idx) of every frame in [t_key - 3 s, t_key], time-ordered. Start = the first
    frame of the colour stretch that reaches the first colour key frame (walk back from t_key to the last IR frame)."""
    fr = [f for f in frames if f["t"] <= t_key + timedelta(milliseconds=1)]
    if not fr:
        return None, "no frames"
    k = len(fr) - 1
    while k >= 0 and fr[k]["chroma"] >= thr:
        k -= 1
    if k == len(fr) - 1:
        return None, "key frame not colour at full rate"
    if k < 0:
        return fr[0], "start not bracketed (colour through the whole -3 s window)"
    return fr[k + 1], "ok"


def refine_end(frames: list[dict], thr: float, t_key: datetime) -> tuple[dict | None, dict | None, str]:
    """frames in [t_key, t_key + 3 s]. End = the first IR frame after the colour stretch that starts at the last colour key
    frame (the OFF instant at frame resolution); also returns the last colour frame."""
    fr = [f for f in frames if f["t"] >= t_key - timedelta(milliseconds=1)]
    if not fr:
        return None, None, "no frames"
    if fr[0]["chroma"] < thr:
        return None, None, "key frame not colour at full rate"
    k = 0
    while k < len(fr) and fr[k]["chroma"] >= thr:
        k += 1
    if k == len(fr):
        return None, fr[-1], "end not bracketed (colour through the whole +3 s window)"
    return fr[k], fr[k - 1], "ok"


def merge_intervals(segs: list[dict], gap_s: float = MERGE_S) -> list[dict]:
    """Merge refined segments of one camera whose intervals are < gap_s apart (sorted by start)."""
    out = []
    for s in sorted(segs, key=lambda s: s["start"]):
        if out and (s["start"] - out[-1]["end"]).total_seconds() < gap_s:
            o = out[-1]
            o["end"], o["end_file"], o["end_frame_idx"] = s["end"], s["end_file"], s["end_frame_idx"]
            o["last_colour"] = s["last_colour"]
            o["n_colour_keyframes"] += s["n_colour_keyframes"]
            o["key_chroma"] = o["key_chroma"] + s["key_chroma"]
            o["flags"] = "; ".join(x for x in (o["flags"], s["flags"], "merged") if x)
            o["n_merged"] = o.get("n_merged", 1) + 1
        else:
            out.append(dict(s))
    return out


def _hm(day: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{day} {hhmm.strip('~?')}" + (":00" if len(hhmm.strip("~?")) == 5 else ""))


def log_ref_time(row: dict) -> tuple[str, datetime | tuple[datetime, datetime] | None]:
    if row.get("op_on"):
        return "op_on", _hm(row["date"], row["op_on"])
    if row.get("op_off"):
        return "op_off", _hm(row["date"], row["op_off"])
    if row.get("slot"):
        return "slot", _hm(row["date"], row["slot"])
    if row.get("window"):
        a, b = row["window"]
        return "window", (_hm(row["date"], a) - WINDOW_PAD[0], _hm(row["date"], b) + WINDOW_PAD[1])
    return "none", None


def cam_ok(spec: str, cam: str) -> bool:
    spec = spec or ""
    return cam in spec


def match_log(seg: dict, log: list[dict] = COLOUR_LOG) -> dict:
    """The colour-log row a segment matches: same date, camera named in the row, and the segment interval within
    LOG_TOL_S of the operator time (op_on, else op_off, else the planned slot) or inside a round window. Several
    candidates -> the nearest. Returns the match fields (row None if unmatched)."""
    best = None
    for r in log:
        if r["date"] != seg["start"].strftime("%Y-%m-%d") or not cam_ok(r.get("cams", ""), seg["camera"]):
            continue
        kind, ref = log_ref_time(r)
        if kind == "none":
            continue
        if kind == "window":
            if ref[0] <= seg["start"] <= ref[1]:
                d = 0.0
            else:
                continue
        else:
            if seg["start"] <= ref <= seg["end"]:
                d = 0.0
            else:
                d = min(abs((seg["start"] - ref).total_seconds()), abs((seg["end"] - ref).total_seconds()))
            if d > LOG_TOL_S:
                continue
        cand = (d, r["row"], r, kind, ref)
        if best is None or cand[:2] < best[:2]:
            best = cand
    if best is None:
        return {"log_row": None, "log_kind": "", "log_cams": "", "match_type": "none", "log_time": "", "delta_start_vs_op_s": None,
                "delta_start_vs_op_corr_s": None, "unmatched": True}
    d, _, r, kind, ref = best
    if kind == "window":
        return {"log_row": r["row"], "log_kind": r["kind"], "log_cams": r["cams"], "match_type": "window",
                "log_time": f"{ref[0]:%H:%M}-{ref[1]:%H:%M}", "delta_start_vs_op_s": None, "delta_start_vs_op_corr_s": None,
                "unmatched": False}
    anchor = seg["start"] if kind in ("op_on", "slot") else seg["end"]
    delta = (anchor - ref).total_seconds()
    return {"log_row": r["row"], "log_kind": r["kind"], "log_cams": r["cams"], "match_type": kind, "log_time": f"{ref:%H:%M:%S}",
            "delta_start_vs_op_s": round(delta, 2), "delta_start_vs_op_corr_s": round(delta + OP_FAST_S, 2), "unmatched": False}


def file_table(kf_all: pd.DataFrame, run: Path) -> pd.DataFrame:
    """Per camera: every scanned file with start and nominal end (= next file's start, else last key frame + 2 s)."""
    inv = pd.read_csv(run / "scan_inventory.csv")
    inv = inv[inv["set"] == "scan"].copy()
    inv["start_t"] = pd.to_datetime(inv["start"])
    last = kf_all.groupby("file")["t"].max()
    rows = []
    for cam, g in inv.sort_values("start_t").groupby("camera"):
        g = g.reset_index(drop=True)
        for i, r in g.iterrows():
            nxt = g.loc[i + 1, "start_t"] if i + 1 < len(g) else None
            end = nxt if nxt is not None else (last.get(r.file, r.start_t) + pd.Timedelta(seconds=2))
            rows.append({"camera": cam, "file": r.file, "start_t": r.start_t, "end_t": end})
    return pd.DataFrame(rows)


def decode_window(path: str, start: datetime, t0: datetime, t1: datetime, key_idx: dict | None = None,
                  want_image: datetime | None = None) -> list[dict]:
    """Decode every frame of one file whose time (file start + PTS) lies in [t0, t1]: seek to the key frame at or before t0,
    decode forward. frame_idx counted from the key frame landed on (key_idx: pts -> frame index from the scan)."""
    import av
    out = []
    rel0, rel1 = (t0 - start).total_seconds(), (t1 - start).total_seconds()
    with av.open(path) as c:
        s = c.streams.video[0]
        tb = float(s.time_base)
        c.seek(max(0, int((rel0 - 0.001) / tb)), stream=s, backward=True, any_frame=False)
        cur = None
        for f in c.decode(s):
            if f.pts is None:
                continue
            if cur is None:
                cur = key_idx.get(int(f.pts)) if key_idx else None
                cur = -10**9 if cur is None else cur
            else:
                cur += 1
            trel = f.pts * tb
            if trel > rel1 + 1e-6:
                break
            if trel >= rel0 - 1e-6:
                rgb = f.reformat(width=f.width // CHROMA_STEP, height=f.height // CHROMA_STEP, format="rgb24",
                                 interpolation="POINT").to_ndarray()
                out.append({"t": start + timedelta(seconds=trel), "t_rel_s": trel, "pts": int(f.pts), "chroma": chroma_rgb(rgb),
                            "file": path, "frame_idx": cur if cur >= 0 else None})
    return out


def frames_between(files: pd.DataFrame, kf_all: pd.DataFrame, cam: str, t0: datetime, t1: datetime) -> list[dict]:
    out = []
    for r in files[(files.camera == cam) & (files.start_t <= t1) & (files.end_t >= t0)].itertuples():
        kidx = dict(zip(kf_all.loc[kf_all.file == r.file, "pts"].astype(int), kf_all.loc[kf_all.file == r.file, "frame_idx"].astype(int)))
        out += decode_window(r.file, r.start_t.to_pydatetime(), max(t0, r.start_t.to_pydatetime()), t1, kidx)
    return sorted(out, key=lambda f: f["t"])


def lid_windows(path: Path = LID_EVENTS) -> list[dict]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    m = timedelta(minutes=d.get("margin_min", 5))
    return [{"start": datetime.fromisoformat(e["start"]) - m, "end": datetime.fromisoformat(e["end"]) + m, "what": e["what"],
             "raw_start": e["start"], "raw_end": e["end"]} for e in d["events"]]


def lid_event_at(t: datetime, wins: list[dict]) -> str:
    for w in wins:
        if w["start"] <= t < w["end"]:
            return f"{w['raw_start']}-{w['raw_end'][11:]} {w['what']}"
    return ""


def phase_segments(run: Path) -> None:
    kf = load_scan(run, "scan")
    kc0 = load_scan(run, "control")
    # pre-registered rule (floor 1e-4) and its consequence, kept for the record (amendment 6)
    pre = log_gap_threshold(kf["chroma"].to_numpy(), floor=LOG_FLOOR)
    pre["n_colour_iframes"] = int((kf.chroma >= pre["thr"]).sum())
    pre["n_runs"] = int(sum(len(colour_runs(g.chroma.to_numpy() >= pre["thr"])) for _, g in kf.groupby("camera")))
    pre["n_control_colour_iframes"] = int((kc0.chroma >= pre["thr"]).sum()) if len(kc0) else 0
    thr = log_gap_threshold(kf["chroma"].to_numpy(), floor=LOG_FLOOR_AMENDED)
    thr["rule"] = ("amendment 6: geometric mid-point of the largest log10-chroma gap of the pooled I-frames, floor 0.01 "
                   "(the pre-registered floor 1e-4 put the largest gap inside the IR cluster)")
    thr["prereg_floor_1e-4"] = pre
    thr["isolated_low_chroma_iframes"] = kf.loc[(kf.chroma >= 1e-4) & (kf.chroma < thr["thr"]), ["camera", "time", "chroma", "grey_mean"]].to_dict("records")
    thr["scope"] = f"{len(kf)} I-frames, CH07 + CH08, {SCAN_DAYS[0]} -> {SCOPE_END:%Y-%m-%d %H:%M}"
    thr["per_camera"] = {cam: {"n": int((kf.camera == cam).sum()), "n_colour": int(((kf.camera == cam) & (kf.chroma >= thr["thr"])).sum()),
                               "max_ir_chroma": float(kf.loc[(kf.camera == cam) & (kf.chroma < thr["thr"]), "chroma"].max()),
                               "min_colour_chroma": float(kf.loc[(kf.camera == cam) & (kf.chroma >= thr["thr"]), "chroma"].min())
                               if ((kf.camera == cam) & (kf.chroma >= thr["thr"])).any() else None} for cam in CAMS}
    thr["n_exact_zero"] = int((kf.chroma == 0).sum())
    hist_edges = [0, 1e-4, 1e-3, 1e-2, 1e-1, 1, 3, 10, 30, 100, 1000]
    thr["histogram"] = {f"[{a:g},{b:g})": int(((kf.chroma >= a) & (kf.chroma < b)).sum()) for a, b in zip(hist_edges[:-1], hist_edges[1:])}
    (run / "colour_threshold.json").write_text(json.dumps(thr, indent=2), encoding="utf-8")
    T = thr["thr"]
    print(f"[segments] thr {T:.4g} (gap {thr['gap_lo']:.4g} -> {thr['gap_hi']:.4g}, {thr['gap_log10']:.2f} decades)", flush=True)
    files = file_table(kf, run)
    wins = lid_windows()
    segs = []
    for cam, g in kf.groupby("camera"):
        g = g.reset_index(drop=True)
        for a, b in colour_runs(g.chroma.to_numpy() >= T):
            ka, kb = g.loc[a], g.loc[b]
            ta, tb_ = ka.t.to_pydatetime(), kb.t.to_pydatetime()
            fs = frames_between(files, kf, cam, ta - timedelta(seconds=EDGE_S), ta)
            st, fl_s = refine_start(fs, T, ta)
            fe = frames_between(files, kf, cam, tb_, tb_ + timedelta(seconds=EDGE_S))
            en, lastc, fl_e = refine_end(fe, T, tb_)
            flags = "; ".join(x for x in (("start: " + fl_s) if fl_s != "ok" else "", ("end: " + fl_e) if fl_e != "ok" else "") if x)
            st = st or {"t": ta, "file": ka.file, "frame_idx": int(ka.frame_idx)}
            if en is None:
                base = lastc or {"t": tb_, "file": kb.file, "frame_idx": int(kb.frame_idx)}
                en = {"t": base["t"] + timedelta(seconds=0.05), "file": base["file"], "frame_idx": None}
            segs.append({"camera": cam, "start": st["t"], "end": en["t"], "start_file": st["file"], "start_frame_idx": st["frame_idx"],
                         "end_file": en["file"], "end_frame_idx": en["frame_idx"], "last_colour": (lastc or {}).get("t"),
                         "n_colour_keyframes": int(b - a + 1), "key_chroma": g.loc[a:b, "chroma"].tolist(), "flags": flags,
                         "first_colour_key": ta, "last_colour_key": tb_})
            print(f"[segments] {cam} {st['t']} -> {en['t']} ({(en['t'] - st['t']).total_seconds():.1f} s) {flags}", flush=True)
    rows = []
    for cam in CAMS:
        for s in merge_intervals([s for s in segs if s["camera"] == cam]):
            m = match_log(s)
            mid = s["start"] + (s["end"] - s["start"]) / 2
            rows.append({"segment_id": f"{cam}_{s['start']:%Y%m%d_%H%M%S}", "camera": cam, "house": CAM_HOUSE[cam],
                         "start": f"{s['start']:%Y-%m-%d %H:%M:%S.%f}"[:-3], "end": f"{s['end']:%Y-%m-%d %H:%M:%S.%f}"[:-3],
                         "duration_s": round((s["end"] - s["start"]).total_seconds(), 3),
                         "mid": f"{mid:%Y-%m-%d %H:%M:%S.%f}"[:-3],
                         "last_colour_frame": f"{s['last_colour']:%Y-%m-%d %H:%M:%S.%f}"[:-3] if s["last_colour"] else "",
                         "n_colour_keyframes": s["n_colour_keyframes"], "median_chroma": round(float(np.median(s["key_chroma"])), 3),
                         "min_key_chroma": round(float(np.min(s["key_chroma"])), 3),
                         "start_file": Path(s["start_file"]).name, "start_frame_idx": s["start_frame_idx"],
                         "end_file": Path(s["end_file"]).name, "end_frame_idx": s["end_frame_idx"], "flags": s["flags"],
                         "lid_event": lid_event_at(s["start"], wins), **m})
    seg = pd.DataFrame(rows)
    seg.to_csv(run / "colour_segments.csv", index=False)
    # the log's rows with the segments they match (the empty 'video' column, as a table here)
    lr = []
    for r in COLOUR_LOG:
        mm = seg[seg.log_row == r["row"]] if len(seg) else seg
        kind, ref = log_ref_time(r)
        lr.append({"row": r["row"], "date": r["date"], "kind": r["kind"], "cams": r.get("cams", ""), "op_on": r.get("op_on", ""),
                   "op_off": r.get("op_off", ""), "slot_or_window": r.get("slot", "") or ("-".join(r["window"]) if r.get("window") else ""),
                   "log_video_column": r.get("video", ""), "n_segments": len(mm),
                   "segments": "; ".join(mm.segment_id) if len(mm) else "",
                   "video_on_off": "; ".join(f"{a[11:]}-{b[11:]} ({d:.1f} s)" for a, b, d in zip(mm.start, mm.end, mm.duration_s)) if len(mm) else "",
                   "row_without_segment": bool(len(mm) == 0 and kind in ("op_on", "op_off"))})
    pd.DataFrame(lr).to_csv(run / "colour_log_rows.csv", index=False)
    # controls: the threshold applied to the control hours
    kc = load_scan(run, "control")
    ctl = []
    if len(kc):
        for (cam, f), g in kc.groupby(["camera", "file"]):
            ctl.append({"camera": cam, "file": Path(f).name, "n_keyframes": len(g), "n_colour": int((g.chroma >= T).sum()),
                        "max_chroma": float(g.chroma.max()), "first": g.t.min().strftime(FMT), "last": g.t.max().strftime(FMT)})
    pd.DataFrame(ctl).to_csv(run / "control_hours.csv", index=False)
    print(f"[segments] {len(seg)} segments ({seg.camera.value_counts().to_dict() if len(seg) else {}}); "
          f"controls: {sum(c['n_colour'] for c in ctl)} colour I-frames in {len(ctl)} files", flush=True)


# ----------------------------------------------------------------------------------------------- B. WISER box events
TRACK_COLS = ["t_ms", "t_al_ms", "x_raw", "y_raw", "valid", "m_handling", "m_silence", "m_tag_validity", "m_adc_lane", "m_off_animal",
              "x", "y", "method", "imu_ok", "imu_state"]
RULES = {"primary": "valid & ~m_off_animal & ~m_tag_validity (m_handling, m_silence, m_adc_lane kept, carried as flags; amendment 1)",
         "literal": "valid & no m_* flag (the plan's wording)"}
S_UNK, S_OUT, S_H1, S_H2 = 0, 1, 2, 3
STATE_NAME = {S_UNK: "unknown", S_OUT: "out", S_H1: "house_1", S_H2: "house_2"}
HOUSE_CODE = {"house_1": S_H1, "house_2": S_H2}


def load_rois() -> dict:
    d = json.loads((REPO / "wiser" / "configs" / "wiser_rois.json").read_text(encoding="utf-8"))
    return {r["name"]: r for r in d["rois"] if r["name"] in HOUSES}


def load_label(label: str, days: list[str], track_root: Path | None = None) -> pd.DataFrame:
    from default_tracks import load_default_track
    parts = []
    for d in days:
        try:
            parts.append(load_default_track(label, d, root=track_root, columns=TRACK_COLS))
        except FileNotFoundError:
            continue
    if not parts:
        return pd.DataFrame(columns=TRACK_COLS + ["t"])
    df = pd.concat(parts, ignore_index=True).sort_values("t_ms").reset_index(drop=True)
    for c in ("valid", "m_handling", "m_silence", "m_tag_validity", "m_adc_lane", "m_off_animal", "imu_ok"):
        df[c] = df[c].astype(bool)
    df["t"] = utc_ms_to_local(df["t_ms"]).to_numpy()
    return df[(df.t >= TRACK_START) & (df.t < SCOPE_END)].reset_index(drop=True)


def fix_mask(df: pd.DataFrame, rule: str) -> np.ndarray:
    m = df["valid"].to_numpy() & ~df["m_off_animal"].to_numpy() & ~df["m_tag_validity"].to_numpy()
    if rule == "literal":
        m &= ~df["m_handling"].to_numpy() & ~df["m_silence"].to_numpy() & ~df["m_adc_lane"].to_numpy()
    return m


def house_membership(x, y, rois: dict, dilate: float = DILATE_IN) -> dict:
    from wiser_analysis_utils import _rect_membership
    return {h: _rect_membership(np.asarray(x, float), np.asarray(y, float), rois[h], dilate)[1] for h in HOUSES}


def raw_states(n_fix: np.ndarray, n_in: dict, smooth_s: int = SMOOTH_S) -> np.ndarray:
    """Per second s: f_h = in-house fixes / all fixes over [s - smooth_s/2, s + smooth_s/2); house_h if f_h >= 0.5,
    'out' if any fix and no f_h >= 0.5, unknown without fixes."""
    n = len(n_fix)
    half = smooth_s // 2

    def wsum(a):
        c = np.concatenate([[0], np.cumsum(a, dtype=np.int64)])
        lo = np.clip(np.arange(n) - half, 0, n)
        hi = np.clip(np.arange(n) - half + smooth_s, 0, n)
        return c[hi] - c[lo]
    nf = wsum(n_fix)
    st = np.full(n, S_OUT, np.int8)
    st[nf == 0] = S_UNK
    best = np.zeros(n)
    for h in HOUSES:
        f = np.where(nf > 0, wsum(n_in[h]) / np.maximum(nf, 1), 0.0)
        take = (f >= 0.5) & (f > best)
        st[take] = HOUSE_CODE[h]
        best = np.maximum(best, f)
    return st


def rle(a: np.ndarray) -> list[tuple[int, int, int]]:
    a = np.asarray(a)
    if a.size == 0:
        return []
    b = np.flatnonzero(np.diff(a)) + 1
    starts = np.concatenate([[0], b])
    ends = np.concatenate([b, [a.size]])
    return [(int(a[s]), int(s), int(e - s)) for s, e in zip(starts, ends)]


def dwell_clean(raw: np.ndarray, min_dwell: int = MIN_DWELL_S) -> tuple[np.ndarray, list[dict]]:
    """Minimum-dwell cleaning (see the module docstring). Returns the cleaned state per second and the transitions:
    dicts (i = first second of the new state, frm, to, gap_s = length of the unknown stretch crossed, 0 if none)."""
    out = np.full(len(raw), S_UNK, np.int8)
    trans = []
    cur, last_known, gap = None, None, 0
    for v, a, L in rle(raw):
        if v == S_UNK:
            if cur is not None and L < min_dwell:
                out[a:a + L] = cur
            else:
                if cur is not None:
                    last_known = cur
                    gap = 0
                cur = None
                gap += L
            continue
        if cur is None:
            if L >= min_dwell:
                cur = v
                out[a:a + L] = v
                if last_known is not None and last_known != v:
                    trans.append({"i": a, "frm": last_known, "to": v, "gap_s": gap})
                last_known, gap = None, 0
            else:
                gap += L
            continue
        if v == cur:
            out[a:a + L] = cur
        elif L >= min_dwell:
            trans.append({"i": a, "frm": cur, "to": v, "gap_s": 0})
            cur = v
            out[a:a + L] = v
        else:
            out[a:a + L] = cur
    return out, trans


def transitions_to_events(trans: list[dict], label: str, t0: datetime) -> list[dict]:
    ev = []
    for tr in trans:
        t = t0 + timedelta(seconds=tr["i"])
        common = {"animal": label, "time": t.strftime(FMT), "from_state": STATE_NAME[tr["frm"]], "to_state": STATE_NAME[tr["to"]],
                  "across_unknown_s": tr["gap_s"]}
        if tr["frm"] in (S_H1, S_H2):
            ev.append({**common, "house": STATE_NAME[tr["frm"]], "kind": "exit"})
        if tr["to"] in (S_H1, S_H2):
            ev.append({**common, "house": STATE_NAME[tr["to"]], "kind": "enter"})
    return ev


def label_states(df: pd.DataFrame, rule: str, rois: dict, coords=("x", "y"), t0: datetime = TRACK_START,
                 t1: datetime = SCOPE_END) -> dict:
    """Per-second counts, raw and cleaned states, events of one label under one fix rule."""
    n = int((t1 - t0).total_seconds())
    m = fix_mask(df, rule)
    d = df.loc[m]
    sec = ((d["t"] - pd.Timestamp(t0)).dt.total_seconds().to_numpy() // 1).astype(np.int64)
    ok = (sec >= 0) & (sec < n)
    sec = sec[ok]
    mem = house_membership(d[coords[0]].to_numpy()[ok], d[coords[1]].to_numpy()[ok], rois)
    n_fix = np.bincount(sec, minlength=n)
    n_in = {h: np.bincount(sec[mem[h]], minlength=n) for h in HOUSES}
    raw = raw_states(n_fix, n_in)
    clean, trans = dwell_clean(raw)
    return {"n_fix": n_fix, "n_in": n_in, "raw": raw, "clean": clean, "trans": trans, "t0": t0}


def handling_seconds(df: pd.DataFrame, t0: datetime, n: int) -> np.ndarray:
    d = df.loc[df["m_handling"].to_numpy()]
    sec = ((d["t"] - pd.Timestamp(t0)).dt.total_seconds().to_numpy() // 1).astype(np.int64)
    sec = sec[(sec >= 0) & (sec < n)]
    return np.bincount(sec, minlength=n) > 0


def untagged(label: str, t: datetime) -> bool:
    """In the paddock without a tag on the animal (a tag dropout): SF11 09-02 00:03 -> 08:15 and 09-07 06:10:45 -> 08:20."""
    return label == "SF11" and any(a <= t < b for a, b in SF11_UNTAGGED)


def absent(label: str, t: datetime) -> bool:
    """Not in the paddock: SF11 after it left at the 09-07 AM round (last fix 08:20)."""
    return label == "SF11" and any(a <= t < b for a, b in SF11_ABSENT)


def window_mask(wins, t0: datetime, n: int) -> np.ndarray:
    tsec = np.arange(n)
    m = np.zeros(n, bool)
    for a, b in wins:
        m |= (tsec >= (a - t0).total_seconds()) & (tsec < (b - t0).total_seconds())
    return m


def occupancy_table(st: np.ndarray, labs: list[str], t0: datetime) -> pd.DataFrame:
    """Per second: roster per house, n out, untracked (present tagged animals with an unknown state), sf11_untagged (tag
    dropout, animal present), sf11_absent (left the paddock), all_tracked (every present animal tagged and located)."""
    n = st.shape[1]
    occ = {"time": pd.date_range(t0, periods=n, freq="s").strftime(FMT)}
    sf11_untag = window_mask(SF11_UNTAGGED, t0, n) if "SF11" in labs else np.zeros(n, bool)
    sf11_abs = window_mask(SF11_ABSENT, t0, n) if "SF11" in labs else np.zeros(n, bool)

    def roster_strings(mem: np.ndarray) -> np.ndarray:
        code = (mem.astype(np.int64) * (1 << np.arange(len(labs)))[:, None]).sum(0)
        lut = np.array([";".join(l for j, l in enumerate(labs) if c >> j & 1) for c in range(1 << len(labs))], dtype=object)
        return lut[code]
    for h in HOUSES:
        mem = st == HOUSE_CODE[h]
        occ[f"n_{h}"] = mem.sum(0)
        occ[h] = roster_strings(mem)
    occ["n_out"] = (st == S_OUT).sum(0)
    unknown = st == S_UNK
    if "SF11" in labs:
        unknown[labs.index("SF11")] &= ~sf11_untag & ~sf11_abs
    occ["untracked"] = roster_strings(unknown)
    occ["sf11_untagged"] = sf11_untag
    occ["sf11_absent"] = sf11_abs
    occ["all_tracked"] = (~unknown.any(0)) & ~sf11_untag
    return pd.DataFrame(occ)


def phase_occupancy(run: Path) -> pd.DataFrame:
    """Rebuild box_occupancy_1s.csv.gz from the saved cleaned states (states_1s.npz) - no WISER reload, events unchanged."""
    z = np.load(run / "states_1s.npz", allow_pickle=False)
    labs = [str(x) for x in z["labels"]]
    keep = [i for i, l in enumerate(labs) if l in LABELS]
    occ = occupancy_table(z["states"][keep], [labs[i] for i in keep], datetime.fromisoformat(str(z["t0"])))
    occ.to_csv(run / "box_occupancy_1s.csv.gz", index=False)
    print(f"[occupancy] rebuilt from states_1s.npz: all_tracked {occ.all_tracked.mean():.4f}", flush=True)
    return occ


def phase_wiser(run: Path, track_root: Path | None = None, t0: datetime = TRACK_START, t1: datetime = SCOPE_END,
                labels=LABELS, days: list[str] | None = None) -> dict:
    rois = load_rois()
    days = days or [str(date(2026, 8, 30) + timedelta(days=k)) for k in range(13)]
    n = int((t1 - t0).total_seconds())
    wins = lid_windows()
    states, events, ev_lit, ev_raw, info = {}, [], [], [], {}
    for lab in list(labels) + [SECOND_TAG]:
        df = load_label(lab, days, track_root)
        if df.empty:
            info[lab] = {"n_fix": 0}
            continue
        p = label_states(df, "primary", rois, t0=t0, t1=t1)
        hand = handling_seconds(df, t0, n)
        info[lab] = {"n_fix": int(len(df)), "n_fix_primary": int(fix_mask(df, "primary").sum()),
                     "n_fix_literal": int(fix_mask(df, "literal").sum()), "known_s": int((p["clean"] != S_UNK).sum())}
        if lab == SECOND_TAG:
            states[lab] = p["clean"]
            continue
        states[lab] = p["clean"]
        chg = np.flatnonzero(np.diff(p["clean"])) + 1
        for e in transitions_to_events(p["trans"], lab, t0):
            i = int((datetime.strptime(e["time"], FMT) - t0).total_seconds())
            k = np.searchsorted(chg, i, side="right")
            run_end = int(chg[k]) if k < len(chg) else n
            e.update({"rule": "primary", "new_state_run_s": run_end - i,
                      "in_handling": bool(hand[max(0, i - 30):i + 31].any()),
                      "fixes_pm10s": int(p["n_fix"][max(0, i - 10):i + 11].sum()),
                      "lid_event": lid_event_at(datetime.strptime(e["time"], FMT), wins)})
            events.append(e)
        lit = label_states(df, "literal", rois, t0=t0, t1=t1)
        ev_lit += [{**e, "rule": "literal"} for e in transitions_to_events(lit["trans"], lab, t0)]
        rw = label_states(df, "primary", rois, coords=("x_raw", "y_raw"), t0=t0, t1=t1)
        ev_raw += [{**e, "rule": "primary_rawfix"} for e in transitions_to_events(rw["trans"], lab, t0)]
        print(f"[wiser] {lab}: {len(df)} fixes, {sum(1 for e in events if e['animal'] == lab)} events (literal {sum(1 for e in ev_lit if e['animal'] == lab)}, "
              f"raw fixes {sum(1 for e in ev_raw if e['animal'] == lab)})", flush=True)
    cols = ["animal", "house", "kind", "time", "from_state", "to_state", "across_unknown_s", "new_state_run_s", "in_handling",
            "fixes_pm10s", "lid_event", "rule"]
    ev = pd.DataFrame(events, columns=cols).sort_values(["time", "animal", "kind"]).reset_index(drop=True)
    ev.to_csv(run / "box_events.csv", index=False)
    pd.DataFrame(ev_lit + ev_raw).to_csv(run / "box_events_sensitivity.csv.gz", index=False)
    # per-second occupancy
    labs = [l for l in labels if l in states]
    occupancy_table(np.vstack([states[l] for l in labs]), labs, t0).to_csv(run / "box_occupancy_1s.csv.gz", index=False)
    np.savez_compressed(run / "states_1s.npz", t0=str(t0), labels=np.array(labs + ([SECOND_TAG] if SECOND_TAG in states else [])),
                        states=np.vstack([states[l] for l in labs] + ([states[SECOND_TAG]] if SECOND_TAG in states else [])))
    # SF12's second tag vs its primary tag
    agree = None
    if SECOND_TAG in states and "SF12" in states:
        a, b = states["SF12"], states[SECOND_TAG]
        both = (a != S_UNK) & (b != S_UNK)
        agree = {"n_both_known_s": int(both.sum()), "agree_share": float((a[both] == b[both]).mean()) if both.any() else None}
    chk = check_0905(ev)
    chk_lit = check_0905(pd.DataFrame(ev_lit))
    chk_raw = check_0905(pd.DataFrame(ev_raw))
    chk.to_csv(run / "check_0905.csv", index=False)
    pd.concat([chk_lit.assign(rule="literal"), chk_raw.assign(rule="primary_rawfix")]).to_csv(run / "check_0905_sensitivity.csv", index=False)
    res = {"labels": info, "sf12_second_tag_agreement": agree, "rules": RULES,
           "check_0905": verdict_0905(chk), "check_0905_literal": verdict_0905(chk_lit), "check_0905_rawfix": verdict_0905(chk_raw),
           "n_events": int(len(ev)), "n_events_literal": len(ev_lit), "n_events_rawfix": len(ev_raw)}
    (run / "wiser_summary.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(f"[wiser] {len(ev)} events; 09-05 check: {res['check_0905']['verdict']} (literal {res['check_0905_literal']['verdict']}, "
          f"raw fixes {res['check_0905_rawfix']['verdict']})", flush=True)
    return res


def check_0905(ev: pd.DataFrame, gt=GT_0905, day: str = "2026-09-05", search_min: float = 30.0) -> pd.DataFrame:
    rows = []
    for animal, house, kind, hms in gt:
        tg = datetime.fromisoformat(f"{day} {hms}")
        cand = pd.DataFrame()
        if len(ev):
            cand = ev[(ev.animal == animal) & (ev.house == house) & (ev.kind == kind)].copy()
        if len(cand):
            cand["dt"] = (pd.to_datetime(cand["time"]) - pd.Timestamp(tg)).dt.total_seconds()
            cand = cand[cand.dt.abs() <= search_min * 60]
        if len(cand):
            best = cand.loc[cand.dt.abs().idxmin()]
            rows.append({"animal": animal, "house": house, "kind": kind, "gt_time": f"{day} {hms}", "wiser_time": best["time"],
                         "delta_s": float(best["dt"]), "within_30s": bool(abs(best["dt"]) <= GT_TOL_S)})
        else:
            rows.append({"animal": animal, "house": house, "kind": kind, "gt_time": f"{day} {hms}", "wiser_time": "",
                         "delta_s": None, "within_30s": False})
    return pd.DataFrame(rows)


def verdict_0905(chk: pd.DataFrame) -> dict:
    ent = chk[(chk.kind == "enter") & (chk.house == "house_2") & chk.wiser_time.astype(bool)]
    order = list(ent.sort_values(["wiser_time", "delta_s"]).animal) if len(ent) else []
    order_ok = tuple(order) == GT_ENTRY_ORDER
    all_ok = bool(chk.within_30s.all())
    d = pd.to_numeric(chk.delta_s, errors="coerce")
    return {"verdict": "PASS" if (order_ok and all_ok) else "FAIL", "entry_order_wiser": order, "entry_order_gt": list(GT_ENTRY_ORDER),
            "order_matches": order_ok, "all_within_30s": all_ok, "n_matched": int(d.notna().sum()), "n_gt": len(chk),
            "max_abs_delta_s": float(d.abs().max()) if d.notna().any() else None,
            "median_abs_delta_s": float(d.abs().median()) if d.notna().any() else None,
            "rule": "pass if the five house_2 entries come in the operator's order and every one of the 12 events is within 30 s"}


# ----------------------------------------------------------------------------------------------- B3. in-house positions
def load_map(path: Path = MAPPING_JSON) -> dict:
    am = json.loads(Path(path).read_text(encoding="utf-8"))["accepted_map"]
    return {"s": float(am["scale"]), "theta": float(np.radians(am["theta_deg"])), "c": np.array(am["centre_wiser_in"], float),
            "d": np.array([am["dx_in"], am["dy_in"]], float), "source": str(path)}


def wiser_to_paddock(xy, mp: dict) -> np.ndarray:
    W = np.asarray(xy, float).reshape(-1, 2)
    c, s_ = np.cos(mp["theta"]), np.sin(mp["theta"])
    M = mp["s"] * np.array([[c, -s_], [s_, c]])
    return (W - mp["c"]) @ M.T + mp["c"] + mp["d"]


def house_poses() -> dict:
    h1 = json.loads((REPO / "cv" / "configs" / "house1_cohort_pose_2026c.json").read_text(encoding="utf-8"))
    return {"house_1": {"centre": tuple(h1["centre_in"]), "ridge_deg": float(h1["ridge_deg"]),
                        "source": "cv/configs/house1_cohort_pose_2026c.json (09-04 12:00 CH01 + CH02 labels)"},
            "house_2": dict(HOUSE_POSE["house_2"])}


def to_house_frame(p, pose: dict) -> np.ndarray:
    """paddock (x, y) in -> (along, across) in: along = (p - c) . (cos phi, sin phi), across = (p - c) . (-sin phi, cos phi)."""
    P = np.asarray(p, float).reshape(-1, 2) - np.asarray(pose["centre"], float)
    ph = np.radians(pose["ridge_deg"])
    u, v = np.array([np.cos(ph), np.sin(ph)]), np.array([-np.sin(ph), np.cos(ph)])
    return np.column_stack([P @ u, P @ v])


def window_stats(d: pd.DataFrame, mp: dict, pose: dict) -> dict:
    """Mean house-frame position of a set of fixes: track mean (x, y), raw-fix mean, SE = sd(raw) / sqrt(n), IMU shares
    over the distinct aligned seconds."""
    if d.empty:
        return {"n_fix": 0}
    tr = to_house_frame(wiser_to_paddock(d[["x", "y"]].to_numpy(), mp), pose)
    rw = to_house_frame(wiser_to_paddock(d[["x_raw", "y_raw"]].to_numpy(), mp), pose)
    n = len(d)
    sec = (pd.to_numeric(d["t_al_ms"], errors="coerce").fillna(d["t_ms"]).to_numpy() // 1000).astype(np.int64)
    imu = pd.DataFrame({"s": sec, "ok": d["imu_ok"].to_numpy(), "st": d["imu_state"].to_numpy()}).drop_duplicates("s")
    ok = imu[imu.ok]
    return {"n_fix": n, "along_in": float(tr[:, 0].mean()), "across_in": float(tr[:, 1].mean()),
            "along_raw_in": float(rw[:, 0].mean()), "across_raw_in": float(rw[:, 1].mean()),
            "along_se_in": float(rw[:, 0].std(ddof=1) / np.sqrt(n)) if n > 1 else None,
            "across_se_in": float(rw[:, 1].std(ddof=1) / np.sqrt(n)) if n > 1 else None,
            "sd_along_raw_in": float(rw[:, 0].std(ddof=1)) if n > 1 else None, "sd_across_raw_in": float(rw[:, 1].std(ddof=1)) if n > 1 else None,
            "imu_ok_s": int(len(ok)), "still_share": float((ok.st == 1).mean()) if len(ok) else None,
            "active_share": float((ok.st == 2).mean()) if len(ok) else None, "loco_share": float((ok.st == 3).mean()) if len(ok) else None,
            "share_V3": float((d["method"] == "V3").mean())}


def phase_inhouse(run: Path, track_root: Path | None = None, labels=LABELS, days: list[str] | None = None) -> None:
    mp, poses = load_map(), house_poses()
    z = np.load(run / "states_1s.npz", allow_pickle=False)
    t0 = datetime.fromisoformat(str(z["t0"]))
    labs = list(z["labels"])
    days = days or [str(date(2026, 8, 30) + timedelta(days=k)) for k in range(13)]
    rows = []
    for lab in labels:
        if lab not in labs:
            continue
        stt = z["states"][labs.index(lab)]
        df = load_label(lab, days, track_root)
        df = df.loc[fix_mask(df, "primary")].reset_index(drop=True)
        sec = ((df["t"] - pd.Timestamp(t0)).dt.total_seconds().to_numpy() // 1).astype(np.int64)
        okk = (sec >= 0) & (sec < len(stt))
        df, sec = df.loc[okk].reset_index(drop=True), sec[okk]
        df["state"] = stt[sec]
        # an in-house fix: the cleaned state is that house AND the fix itself lies in the house's dilated rectangle
        # (excursions shorter than the 20-s dwell keep the state but not their fixes)
        memb = house_membership(df["x"].to_numpy(), df["y"].to_numpy(), load_rois())
        df.loc[(df.state == S_H1) & ~memb["house_1"], "state"] = -1
        df.loc[(df.state == S_H2) & ~memb["house_2"], "state"] = -1
        df["minute"] = df["t"].dt.floor("min")
        # seconds in each house per minute, from the cleaned state
        mins = (pd.Timestamp(t0) + pd.to_timedelta(np.arange(len(stt)), unit="s")).floor("min")
        for h in HOUSES:
            code = HOUSE_CODE[h]
            s_in = pd.Series(stt == code).groupby(mins).sum()
            keep = s_in[s_in >= INHOUSE_MIN_S]
            dh = df[df.state == code]
            g = dict(tuple(dh.groupby("minute")))
            for mnt, k in keep.items():
                d = g.get(mnt)
                if d is None:
                    continue
                st = window_stats(d, mp, poses[h])
                st["in_body_footprint"] = bool(abs(st["along_in"]) <= BODY_IN[0] / 2 + FOOTPRINT_TOL_IN
                                               and abs(st["across_in"]) <= BODY_IN[1] / 2 + FOOTPRINT_TOL_IN)
                rows.append({"animal": lab, "house": h, "minute": mnt.strftime("%Y-%m-%d %H:%M"), "n_s_in": int(k), **st})
        print(f"[inhouse] {lab}: {sum(1 for r in rows if r['animal'] == lab)} minute rows", flush=True)
    out = pd.DataFrame(rows)
    out.to_csv(run / "inhouse_minutes.csv.gz", index=False, float_format="%.4f")
    (run / "inhouse_frames.json").write_text(json.dumps({"map": {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in mp.items()},
                                                          "poses": poses}, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------------------------------- B4. camera <-> house
def pearson(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 3 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
        return float("nan")
    return float(np.corrcoef(a[m], b[m])[0, 1])


def spearman(a, b) -> float:
    a, b = pd.Series(a, dtype=float), pd.Series(b, dtype=float)
    m = a.notna() & b.notna()
    return pearson(a[m].rank(), b[m].rank())


def shift_null(e: np.ndarray, n: np.ndarray, r_obs: float, n_draw: int = 1000, min_shift: int = 60, seed: int = 1) -> float:
    """Share of circular shifts (>= min_shift minutes) of the event series with r >= the observed r (context only)."""
    rng = np.random.default_rng(seed)
    L = len(n)
    if not np.isfinite(r_obs) or L < 3 * min_shift:
        return float("nan")
    ks = rng.integers(min_shift, L - min_shift, size=n_draw)
    return float(np.mean([pearson(e, np.roll(n, k)) >= r_obs for k in ks]))


def phase_camhouse(run: Path) -> None:
    kf = load_scan(run, "scan")
    seg = pd.read_csv(run / "colour_segments.csv") if (run / "colour_segments.csv").exists() else pd.DataFrame()
    ev = pd.read_csv(run / "box_events.csv")
    wins = lid_windows()
    kf = kf[kf.diff_energy.notna()].copy()
    kf["t_prev"] = kf["t"] - pd.Timedelta(seconds=2.5)
    excl = np.zeros(len(kf), bool)
    for s in seg.itertuples():
        a, b = pd.Timestamp(s.start) - pd.Timedelta(seconds=10), pd.Timestamp(s.end) + pd.Timedelta(seconds=10)
        excl |= ((kf.camera == s.camera) & (((kf.t >= a) & (kf.t <= b)) | ((kf.t_prev >= a) & (kf.t_prev <= b)))).to_numpy()
    kf = kf[~excl]
    kf["minute"] = kf.t.dt.floor("min")
    t_lo, t_hi = pd.Timestamp(SCAN_DAYS[0]), pd.Timestamp(SCOPE_END)
    grid = pd.date_range(t_lo, t_hi - pd.Timedelta(minutes=1), freq="min")
    E = {cam: kf[kf.camera == cam].groupby("minute").diff_energy.mean().reindex(grid) for cam in CAMS}
    ev["minute"] = pd.to_datetime(ev["time"]).dt.floor("min")
    N = {h: ev[ev.house == h].groupby("minute").size().reindex(grid, fill_value=0).astype(float) for h in HOUSES}
    lid = np.zeros(len(grid), bool)
    for w in wins:
        lid |= (grid >= w["start"]) & (grid < w["end"])
    rows = []
    for subset, keep in (("all minutes", np.ones(len(grid), bool)), ("outside lid events (+-5 min)", ~lid)):
        for cam in CAMS:
            for h in HOUSES:
                e, n = E[cam].to_numpy()[keep], N[h].to_numpy()[keep]
                m = np.isfinite(e)
                r = pearson(e[m], n[m])
                rows.append({"subset": subset, "camera": cam, "house": h, "expected_pair": CAM_HOUSE[cam] == h,
                             "n_minutes": int(m.sum()), "n_event_minutes": int((n[m] > 0).sum()), "n_events": int(n[m].sum()),
                             "pearson_r": round(r, 4), "spearman_rho": round(spearman(e[m], n[m]), 4),
                             "p_circular_shift": round(shift_null(e[m], n[m], r), 4),
                             "mean_energy_event_min": round(float(np.nanmean(e[m][n[m] > 0])), 4) if (n[m] > 0).any() else None,
                             "mean_energy_other_min": round(float(np.nanmean(e[m][n[m] == 0])), 4)})
    out = pd.DataFrame(rows)
    out.to_csv(run / "camera_house_check.csv", index=False)
    pd.DataFrame({"minute": grid.strftime("%Y-%m-%d %H:%M"), **{f"energy_{c}": E[c].to_numpy() for c in CAMS},
                  **{f"events_{h}": N[h].to_numpy() for h in HOUSES}, "lid_event": lid}).to_csv(run / "camera_house_minutes.csv.gz", index=False)
    print(out.to_string(), flush=True)


# ----------------------------------------------------------------------------------------------- report
def _md_table(df: pd.DataFrame, cols: list[str] | None = None, fmt: dict | None = None) -> str:
    if df is None or len(df) == 0:
        return "_(none)_\n"
    cols = cols or list(df.columns)
    fmt = fmt or {}

    def cell(c, v):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "-"
        if c in fmt:
            try:
                return fmt[c].format(v)
            except (ValueError, TypeError):
                return str(v)
        return str(v).replace("|", "/")
    L = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df[cols].itertuples(index=False):
        L.append("| " + " | ".join(cell(c, v) for c, v in zip(cols, r)) + " |")
    return "\n".join(L) + "\n"


DEFINITIONS = r"""
## Definitions (formula and words)

Times are field-PC local (America/New_York, naive). Video frame time t = file-name start + PTS. WISER fix time =
`t_ms` (Unix ms UTC, the field-PC clock) converted to local time. Positions are inches.

**A. Colour segments**
- **Chroma** c = (1/N) Σ_p (|R_p − G_p| + |G_p − B_p|) over the N = 640 × 480 pixels of the frame decimated by 4
  (nearest pixel), 8-bit RGB. A monochrome (IR) frame has R = G = B, so c = 0; a colour frame has c ≫ 0.
- **Threshold** thr = 10^((v_k + v_(k+1)) / 2), where v = the sorted distinct values of log10(max(c, f)) over all
  scanned I-frames of 09-09 00:00 → 09-11 19:40 (both cameras pooled) and k = argmax_j (v_(j+1) − v_j): the geometric
  mid-point of the largest gap in log chroma. A frame is colour if c ≥ thr. Floor f = 0.01 (plan amendment 6, after
  results; the pre-registered f = 10⁻⁴ put the largest gap between two isolated IR I-frames, see section A).
- **Colour run**: a maximal sequence of consecutive colour I-frames of one camera (I-frames are 2 s apart, GOP 2 s).
- **Segment start** = the time of the first frame (every frame decoded in [t_a − 3 s, t_a], t_a = first colour I-frame
  of the run) of the uninterrupted colour stretch that reaches t_a. **Segment end** = the time of the first IR frame
  after the uninterrupted colour stretch that starts at the last colour I-frame t_b (frames in [t_b, t_b + 3 s]); this is
  the OFF instant at frame resolution (0.05 s). Runs whose refined intervals are < 1 s apart are merged.
  **Duration** = end − start (s). **Median chroma** = median of c over the run's colour I-frames.
- **Log match**: a segment matches the colour-log row of the same date whose camera field names the segment's camera
  and whose operator time T (ON, else OFF, else the planned slot) lies within 120 s of the segment interval
  (distance = 0 if T ∈ [start, end], else min(|start − T|, |end − T|)); a round row without a time matches a segment
  inside the round window (−5 / +30 min). Nearest row wins. **Δ** = start − T (ON / slot rows) or end − T (OFF-only rows);
  **Δ_corr** = Δ + 35 s (the operator clock ran ≈ 35 s fast on 09-09). A segment with no row is *unmatched*; a row with an
  operator time and no segment is a *row without segment*.
- **Control count** = number of I-frames with c ≥ thr in each control hour (expected 0).

**B. WISER box events and positions**
- **Fix rule (primary)**: `valid` ∧ ¬`m_off_animal` ∧ ¬`m_tag_validity` (amendment 1; `m_handling`, `m_silence`,
  `m_adc_lane` fixes are kept and the events carry `in_handling`). **Literal rule**: `valid` and no `m_*` flag.
- **Membership** of a fix: (x, y) of the default track inside the house_h rectangle of `wiser_rois.json` grown by 15 in on
  every side (`_rect_membership(..., 15)[1]`).
- **6-s smoothing**: for animal i and second s, f_h(s) = Σ_{u ∈ [s−3, s+3)} n_in,h(u) / Σ_{u ∈ [s−3, s+3)} n_fix(u), where
  n_fix(u) = number of fixes in second u and n_in,h(u) = those inside house_h. Raw state = house_h if f_h(s) ≥ 0.5;
  'out' if the window holds a fix and no f_h ≥ 0.5; 'unknown' if it holds no fix.
- **20-s minimum dwell** (cleaned state): walking through the runs of the raw state, a change is accepted only if the new
  state's run lasts ≥ 20 s; shorter runs keep the current state; unknown runs < 20 s are bridged (state held); a longer
  unknown run makes the state unknown until a known run ≥ 20 s.
- **Event** = a change of the cleaned state at second s: *exit house_h* when leaving h, *enter house_h* when arriving in h
  (1-s resolution). `across_unknown_s` = length of the unknown stretch the change crossed (0 = observed directly);
  `new_state_run_s` = how long the new cleaned state lasts; `in_handling` = any `m_handling` fix of that animal within
  ± 30 s; `fixes_pm10s` = fixes of that animal within ± 10 s; `lid_event` = the house-lid event window (± 5 min) containing it.
- **09-05 check**: for each of the operator's 12 events (six exits from house_2 at 08:47:08; entries into house_2 SF09
  09:49:49, SF07 09:49:51, SF11 09:49:58, SF10 09:50:01, SF12 09:50:15; SF08 into house_1 09:50:13) the nearest WISER
  event of the same animal, house and kind within ± 30 min; Δt = t_WISER − t_operator. **Pass** iff every |Δt| ≤ 30 s and
  the five house_2 entries, sorted by t_WISER, come in the operator's order SF09, SF07, SF11, SF10, SF12.
- **Occupancy (per second)**: roster of house_h = animals whose cleaned state is h; `untracked` = animals present in the
  paddock and tagged whose state is unknown; `sf11_untagged` = SF11 present without a tag on the animal (dropouts 09-02
  00:03 → 08:15, and 09-07 06:10:45 → 08:20 after the implant carrying tag 3058 fell off); `sf11_absent` = SF11 out of the
  paddock (taken out at the 09-07 AM round; the last 3058 fix at 08:20 is the implant in house_2); `all_tracked` = no
  untracked animal and no untagged animal present. Rosters are complete except in tag dropouts (SF11's two; SF12 before its
  tag's first fix 08-31 06:36) and while a tagged animal is untracked (plan amendments 12-13, 2026-10-11).
- **Paddock position** p = s R(θ) (w − c) + c + d (the accepted WISER → paddock similarity: s 0.96340, θ 0.1143°,
  c (501.68, 761.10) in, d (−272.85, −605.80) in). **House frame**: along = (p − C) · (cos φ, sin φ),
  across = (p − C) · (−sin φ, cos φ), with C, φ the house centre and ridge angle (house_2 (342.4, 117.7) in, 92.0°;
  house_1 (142.23, 123.46) in, 88.51°). +along ≈ paddock +y (toward the y = 240 wall), +across ≈ paddock −x.
- **In-house minute** (animal i, house h, minute m): kept if the cleaned state is h for n_s_in ≥ 30 s of the minute; the
  in-house fixes are those whose second has state h AND that lie in h's dilated rectangle. `along_in` / `across_in` =
  mean of the default-track (x, y) of those fixes in the house frame; `along_raw_in` / `across_raw_in` = mean of the raw
  fixes; `sd_*_raw_in` = their standard deviation; **SE** = sd / √n (n = `n_fix`; ignores autocorrelation, so it is a
  lower bound of the true uncertainty); IMU shares = fraction of the minute's distinct IMU-QC-ok aligned seconds in each
  `imu_state` (1 still, 2 active, 3 locomoting); `in_body_footprint` = |along| ≤ 24.63/2 + 3 in and |across| ≤ 18.0/2 + 3 in
  (descriptive only; the dilated rectangle reaches far beyond the body).
- **Frame-difference energy** e_k = (1/M) Σ_q |g_k(q) − g_(k−1)(q)| over the M = 320 × 240 pixels of the area-averaged
  grey image of consecutive I-frames k − 1, k (2 s apart) of one file. **Per-minute energy** E_cam(m) = mean e_k over the
  minute's I-frames, excluding I-frames within ± 10 s of a colour segment of that camera (or whose predecessor is).
  **Per-minute events** N_h(m) = number of enter + exit events (all animals) of house h in minute m.
- **Camera ↔ house correlation**: Pearson r and Spearman ρ between E_cam(m) and N_h(m) over the minutes of 09-09 00:00 →
  09-11 19:40 (all, and outside the lid-event windows ± 5 min). `p_circular_shift` = share of 1 000 circular shifts of
  N_h by ≥ 60 min with r ≥ the observed r (context only; no decision is taken from this check).

**C. Click page**
- **Frames**: colour_mid = the first frame with t ≥ (start + end) / 2; ir_p06 / ir_p15 = the first frames with
  t ≥ end + 6 s / end + 15 s. Each frame's chroma is recomputed; `mode_check` flags a colour frame with c < thr or an IR
  frame with c ≥ thr. Frame index = position in the file counted from the key frame the decoder seeks to.
- **Lid correction** B (2 × 3) = `frame_correction.Corrections("2026c").correction(cam, t)`: maps frame pixels to the
  09-04 12:00 reference pixels of the frame's lid-closed segment (median of that segment's tracked samples); stored per
  frame with the segment index and flag, not applied.
- **Roster at the flash** = the occupancy roster of the camera's house at the segment middle. **Pre-flash position** =
  the in-house minute statistics above over [start − 60 s, start).
"""


def write_report(run: Path) -> Path:
    import output_paths as op
    rep = op.report_dir(COHORT, DIRECTION)
    meta = json.loads((run / "run.json").read_text(encoding="utf-8")) if (run / "run.json").exists() else {}
    thr = json.loads((run / "colour_threshold.json").read_text(encoding="utf-8"))
    seg = pd.read_csv(run / "colour_segments.csv")
    lr = pd.read_csv(run / "colour_log_rows.csv")
    ctl = pd.read_csv(run / "control_hours.csv")
    ws = json.loads((run / "wiser_summary.json").read_text(encoding="utf-8"))
    ev = pd.read_csv(run / "box_events.csv")
    chk = pd.read_csv(run / "check_0905.csv")
    chs = pd.read_csv(run / "check_0905_sensitivity.csv")
    ih = pd.read_csv(run / "inhouse_minutes.csv.gz")
    ch = pd.read_csv(run / "camera_house_check.csv") if (run / "camera_house_check.csv").exists() else pd.DataFrame()
    pg = run / "identity_page" / "page_check.json"
    pgc = json.loads(pg.read_text(encoding="utf-8")) if pg.exists() else {}
    pdata = json.loads((run / "identity_page" / "page_data.json").read_text(encoding="utf-8")) if (run / "identity_page" / "page_data.json").exists() else {}
    occ = pd.read_csv(run / "box_occupancy_1s.csv.gz", usecols=["time", "all_tracked", "sf11_untagged"])
    old_occ = run / "superseded_20261011" / "box_occupancy_1s.csv.gz"            # the 10-10 version (first superseded)
    old_share = float(pd.read_csv(old_occ, usecols=["all_tracked"]).all_tracked.mean()) if old_occ.exists() else float("nan")
    seg["day"] = seg.start.str[:10]
    n_by = seg.groupby(["camera", "day"]).size().unstack(fill_value=0) if len(seg) else pd.DataFrame()
    v = ws["check_0905"]
    L = [f"# In-box cameras CH07 / CH08, phase 0: colour segments, WISER box events, in-house positions, identity click page (cohort `{COHORT}`)\n",
         f"Plan `{PLAN}` (pre-registered 2026-10-10, approved by the user; amendments dated there). Run `{run.as_posix()}`; "
         f"generated {datetime.now():%Y-%m-%d %H:%M}; code `{(meta.get('phases_run') or [{}])[-1].get('git_commit', '?')}`. Drivers "
         "`cv/cv_field/inbox_p0.py` (A, B) and `cv/cv_field/inbox_identity_page.py` (C). The agent never looked at a frame; every "
         "number below is computed. Scope 2026-08-30 19:00 → 2026-09-11 19:40 (before the five females).\n",
         "## Summary\n",
         f"- **A. Colour segments**: threshold thr = **{thr['thr']:.4g}** (largest log-chroma gap {thr['gap_lo']:.4g} → "
         f"{thr['gap_hi']:.4g}, {thr['gap_log10']:.2f} decades; next largest gap {thr.get('second_gap_log10', float('nan')):.2f} decades) over "
         f"{thr['n']} I-frames; **{len(seg)} colour segments** "
         + (", ".join(f"{c} {d}: {int(n_by.loc[c, d])}" for c in n_by.index for d in n_by.columns if n_by.loc[c, d]) if len(seg) else "")
         + f"; {int((~seg.unmatched.astype(bool)).sum()) if len(seg) else 0} match a colour-log row, "
         f"{int(seg.unmatched.astype(bool).sum()) if len(seg) else 0} unmatched; {int(lr.row_without_segment.sum())} log rows with an operator time have "
         f"no segment. Controls: {int(ctl.n_colour.sum()) if len(ctl) else 0} colour I-frames in {len(ctl)} control hours.",
         f"- **B. 09-05 ground truth: {v['verdict']}** — WISER entry order {', '.join(v['entry_order_wiser'])} (operator "
         f"{', '.join(v['entry_order_gt'])}); {v['n_matched']} of {v['n_gt']} events matched, |Δt| median {v['median_abs_delta_s']:.0f} s, max "
         f"{v['max_abs_delta_s']:.0f} s (Δt = WISER − operator from {pd.to_numeric(chk.delta_s, errors='coerce').min():+.0f} to "
         f"{pd.to_numeric(chk.delta_s, errors='coerce').max():+.0f} s). Literal mask rule: "
         f"{ws['check_0905_literal']['verdict']}; raw fixes instead of the track: {ws['check_0905_rawfix']['verdict']}.",
         f"- **B. Box events**: {len(ev)} events (primary rule) for SF07–SF12, {int(ev.in_handling.sum())} near a handling mask; "
         f"{len(ih)} in-house animal-minutes; per second every animal in the paddock was tagged and located {100 * occ.all_tracked.mean():.1f} % "
         f"of the scope ({100 * occ.loc[occ.time < '2026-09-07 06:10:45', 'all_tracked'].mean():.1f} % before 09-07 06:10:45, "
         f"{100 * occ.loc[occ.time >= '2026-09-07 08:20:00', 'all_tracked'].mean():.1f} % after SF11 was taken out at 08:20; corrected "
         f"2026-10-11 — the 10-10 version gave {100 * old_share:.1f} % by counting SF11 as present but untagged to the scope end).",
         ]
    if len(ch):
        a = ch[ch.subset == "all minutes"]
        L.append("- **B. Camera ↔ house** (per-minute frame-difference energy vs per-minute WISER events, 09-09 → 09-11): "
                 + "; ".join(f"{r.camera}–{r.house} r {r.pearson_r:.2f}" for r in a.itertuples())
                 + " (expected pairing CH07–house_2, CH08–house_1; no decision taken from it).")
    if pgc:
        L.append(f"- **C. Click page**: `{(run / 'identity_page' / 'index.html').as_posix()}` — {pgc.get('n_segments')} segments, "
                 f"{pgc.get('n_frames')} frames, page check {pgc.get('verdict')} (missing paths {len(pgc.get('missing', []))}, "
                 f"network URLs {len(pgc.get('network_urls', []))}, pre-filled identities {pgc.get('prefilled_identities')}). "
                 "Exports go to `cv/configs/inbox_identity_2026c/`.")
    L.append("")
    # A
    L += ["## A. Colour segments (CH07 / CH08, 09-09 → 09-11 19:40)\n",
          f"I-frame chroma histogram: " + ", ".join(f"{k}: {v_}" for k, v_ in thr.get("histogram", {}).items()) + ". "
          + "; ".join(f"{c}: {d['n']} I-frames, {d['n_colour']} colour, max IR chroma {d['max_ir_chroma']:.4g}, min colour chroma "
                      f"{d['min_colour_chroma'] if d['min_colour_chroma'] is None else round(d['min_colour_chroma'], 3)}"
                      for c, d in thr.get("per_camera", {}).items()) + ".\n"]
    pre = thr.get("prereg_floor_1e-4", {})
    iso = pd.DataFrame(thr.get("isolated_low_chroma_iframes", []))
    if pre:
        L += [f"**Threshold (plan amendment 6, after results).** The pre-registered rule (floor 10⁻⁴) gave thr = {pre['thr']:.4g} "
              f"(largest gap {pre['gap_lo']:.4g} → {pre['gap_hi']:.4g}, {pre['gap_log10']:.2f} decades — inside the IR cluster): "
              f"{pre['n_colour_iframes']} colour I-frames, {pre['n_runs']} colour runs, {pre['n_control_colour_iframes']} colour I-frames in "
              "the control hours. The isolated I-frames with 10⁻⁴ ≤ c < thr (IR by the amended rule; rounding-level chroma, two of them "
              "on CH08 at 23:00 / 23:39, when colour is impossible):\n",
              _md_table(iso, None, {"chroma": "{:.4g}", "grey_mean": "{:.1f}"}) if len(iso) else "_(none)_\n",
              f"\nWith the floor at 0.01 the same rule gives thr = {thr['thr']:.4g}; no I-frame lies in ({thr['gap_lo']:.4g}, "
              f"{thr['gap_hi']:.4g}), so every threshold in that interval gives the identical classification. The pre-registered "
              "outputs are kept in the run as `colour_segments_prereg_thr.csv`, `colour_log_rows_prereg_thr.csv`, "
              "`control_hours_prereg_thr.csv`, `colour_threshold_prereg.json`.\n"]
    s2 = seg.copy()
    if len(s2):
        s2["ON–OFF"] = s2.start.str[5:23] + " – " + s2.end.str[11:23]
        s2["log"] = s2.apply(lambda r: f"{int(r.log_row)}: {r.log_kind} ({r.match_type})" if not bool(r.unmatched) else "**unmatched**", axis=1)
        s2["Δ / Δ_corr (s)"] = s2.apply(lambda r: "-" if pd.isna(r.delta_start_vs_op_s) else f"{r.delta_start_vs_op_s:+.0f} / {r.delta_start_vs_op_corr_s:+.0f}", axis=1)
        s2["lid"] = s2.lid_event.fillna("").map(lambda x: "yes" if x else "")
    L.append(_md_table(s2, ["segment_id", "ON–OFF", "duration_s", "n_colour_keyframes", "median_chroma", "log", "Δ / Δ_corr (s)", "lid", "flags"],
                       {"duration_s": "{:.2f}", "median_chroma": "{:.2f}"}) if len(s2) else "_(no segment)_\n")
    um = seg[seg.unmatched.astype(bool)] if len(seg) else seg
    if len(um):
        notes = []
        for r in um.itertuples():
            st_, en_ = datetime.fromisoformat(r.start), datetime.fromisoformat(r.end)
            best = None
            for row in COLOUR_LOG:
                kind, ref = log_ref_time(row)
                if row["date"] != r.start[:10] or kind in ("none", "window"):
                    continue
                d = 0.0 if st_ <= ref <= en_ else min(abs((st_ - ref).total_seconds()), abs((en_ - ref).total_seconds()))
                if best is None or d < best[0]:
                    best = (d, row, ref)
            notes.append(f"{r.segment_id} ({r.duration_s:.1f} s{', in a lid event' if isinstance(r.lid_event, str) and r.lid_event else ''}): "
                         + (f"nearest row {best[1]['row']} ({best[1]['kind']}, {best[1].get('cams')}, {best[2]:%H:%M}) "
                            f"{best[0] / 60:.1f} min away" if best else "no timed row that day"))
        L.append("Unmatched segments and the nearest timed log row of the same date (any camera): " + "; ".join(notes) + ".\n")
    if len(iso):
        near = []
        for r in iso.itertuples():
            t_ = datetime.fromisoformat(r.time)
            for row in COLOUR_LOG:
                kind, ref = log_ref_time(row)
                if row["date"] == r.time[:10] and kind in ("op_on", "op_off", "slot") and abs((t_ - ref).total_seconds()) <= LOG_TOL_S:
                    near.append(f"{r.camera} {r.time} (c = {r.chroma:.3g}) lies {(t_ - ref).total_seconds() / 60:+.1f} min from row "
                                f"{row['row']} ({row['kind']})")
        if near:
            L.append("Isolated low-chroma I-frames within ± 2 min of a log row (IR by the amended rule; listed for the user): "
                     + "; ".join(near) + ".\n")
    L += ["\nThe colour log's rows with the segments they match (this fills the log's empty \"video\" column here; the recording "
          "repo is not edited):\n",
          _md_table(lr.assign(op=lr.op_on.fillna("").astype(str) + " / " + lr.op_off.fillna("").astype(str) + " " + lr.slot_or_window.fillna("").astype(str)),
                    ["row", "date", "kind", "cams", "op", "n_segments", "video_on_off", "row_without_segment"]),
          "\nControl hours (the threshold applied to hours before any colour insert existed):\n",
          _md_table(ctl, ["camera", "file", "n_keyframes", "n_colour", "max_chroma"], {"max_chroma": "{:.4g}"})]
    # B
    cnt = ev.groupby(["animal", "house", "kind"]).size().unstack(fill_value=0).reset_index() if len(ev) else pd.DataFrame()
    hours = ev.time.str[11:13].astype(int) if len(ev) else pd.Series(dtype=int)
    L += ["\n## B. WISER box events (operator parameters: house rectangle + 15 in, 6-s smoothing, 20-s minimum dwell)\n",
          f"Default tracks (`wiser/src/default_tracks.py`, V3 / B2) of SF07–SF12, 08-30 19:00 → 09-11 19:40. Fix rule: {RULES['primary']}. "
          f"Events per animal × house × kind:\n", _md_table(cnt),
          f"\n{int(((hours >= 19) | (hours < 6)).sum())} of {len(ev)} events fall between 19:00 and 06:00. "
          f"{int((ev.across_unknown_s > 0).sum())} events cross an unknown stretch (time precision = that stretch). "
          f"`new_state_run_s` median {ev.new_state_run_s.median():.0f} s (p05 {ev.new_state_run_s.quantile(.05):.0f} s). "
          f"Sensitivities in `box_events_sensitivity.csv.gz`: literal mask rule {ws['n_events_literal']} events, raw fixes instead "
          f"of the track {ws['n_events_rawfix']}. SF12's second tag (08-31) agrees with SF12's primary tag on "
          f"{100 * (ws.get('sf12_second_tag_agreement') or {}).get('agree_share', float('nan')):.0f} % of "
          f"{(ws.get('sf12_second_tag_agreement') or {}).get('n_both_known_s', 0)} jointly known seconds (the second tag was sporadic).\n",
          "### 09-05 ground-truth check (plan B2 / B5)\n",
          _md_table(chk, ["animal", "house", "kind", "gt_time", "wiser_time", "delta_s", "within_30s"], {"delta_s": "{:+.0f}"}),
          f"\n**Verdict: {v['verdict']}** ({v['rule']}). Sensitivities: literal rule {ws['check_0905_literal']['verdict']} "
          f"({ws['check_0905_literal']['n_matched']} of 12 matched within ± 30 min — `m_handling` covers the round 08:40:00–09:49:59, "
          "so the literal rule drops every fix of that window and the exits and most entries vanish; that is why amendment 1 keeps "
          f"them), raw fixes {ws['check_0905_rawfix']['verdict']} "
          f"(max |Δt| {ws['check_0905_rawfix']['max_abs_delta_s']:.0f} s).\n",
          "### In-house positions (house frame, inches)\n",
          f"{len(ih)} animal-minutes; per house the median minute position (along, across) and the share of minutes whose mean lies in "
          "the body footprint:\n",
          _md_table(ih.groupby(["animal", "house"]).agg(minutes=("minute", "size"), along_median=("along_in", "median"),
                                                         across_median=("across_in", "median"), se_median=("along_se_in", "median"),
                                                         still_share_median=("still_share", "median"),
                                                         in_footprint=("in_body_footprint", "mean")).reset_index(),
                    None, {"along_median": "{:+.1f}", "across_median": "{:+.1f}", "se_median": "{:.2f}", "still_share_median": "{:.2f}",
                           "in_footprint": "{:.2f}"})]
    if len(ch):
        L += ["\n### Camera ↔ house check (plan B4; reported, not decided)\n",
              _md_table(ch, ["subset", "camera", "house", "expected_pair", "n_minutes", "n_events", "pearson_r", "spearman_rho",
                             "p_circular_shift", "mean_energy_event_min", "mean_energy_other_min"],
                        {"pearson_r": "{:+.3f}", "spearman_rho": "{:+.3f}", "p_circular_shift": "{:.3f}", "mean_energy_event_min": "{:.2f}",
                         "mean_energy_other_min": "{:.2f}"})]
    # C
    if pdata:
        segs = pdata.get("segments", [])
        rost = pd.DataFrame([{"segment_id": s["segment_id"], "house": s["house"], "roster at the flash": ", ".join(s["wiser"]["roster"]) or "none",
                              "untracked": ", ".join(s["wiser"]["untracked"]), "SF11": s["wiser"]["sf11_note"],
                              "lid segment (colour frame)": next((f.get("lid", {}).get("lid_segment") for f in s["frames"] if f["kind"] == "colour_mid"), None),
                              "lid flag": next((f.get("lid", {}).get("flag") for f in s["frames"] if f["kind"] == "colour_mid"), None),
                              "frame checks": " ".join(str(f.get("mode_check", f.get("error", "?")))[:12] for f in s["frames"])} for s in segs])
        L += ["\n## C. Identity click page\n",
              f"`{(run / 'identity_page' / 'index.html').as_posix()}` (open from disk; self-contained, no network). One entry per colour "
              f"segment ({len(segs)}): the colour frame at the segment middle and IR frames at +6 s / +15 s after OFF (full resolution, "
              "JPEG quality 95, upright as recorded), the WISER roster of the camera's house with the pre-flash minute positions drawn as a "
              "top view (SE and SD bars, IMU shares), the identity legend (built from `wiser/configs/rat_identities_2026c.csv`: the user's "
              "identifying colour per animal, 2026-10-10, SF09 / SF10 corrected the same day — SF07 green, SF08 red, SF09 black, SF10 blue, SF11 white (looks grey), SF12 yellow; "
              "the Notion coban / sticker shown for reference; the first days about 08-30 / 08-31 are uncertain; click markers take the "
              "identifying colour) and the six in-hand close-up clips. The user clicks heads, picks "
              "SF07–SF12 / unknown and sure / likely, and answers \"pile composition complete?\"; localStorage autosave; Export CSV / JSON "
              "→ `cv/configs/inbox_identity_2026c/`; Import JSON. No identity is pre-filled. Each frame carries its lid segment and "
              "correction B (recorded, not applied). **Blind first** (plan amendment 8): per segment the WISER roster and arrangement "
              "stay hidden until \"Save clicks & reveal WISER\"; the clicks saved then are the blind record (`before_reveal`, "
              "`verdict_first`) the order test uses, later edits are recorded separately; clicks stored by the first page version "
              "are flagged `legacy` (that version showed WISER, so they are not blind). Markers can be selected (within 12 screen px), "
              "dragged, nudged, relabelled and deleted (Delete, right-click, × in the per-frame list) with undo / redo; all of it "
              "checked in headless Chrome (`inbox_identity_page.py --ui-check`). **Top-view orientation** (plan amendment 9): after "
              "the reveal the WISER top view is drawn in paddock directions (default = WISER / paddock orientation, +x right, +y up; "
              "edges labelled with the paddock walls, the nearest pole B1 / B3 drawn) and can be rotated (0 / 90 / 180 / 270°) and "
              "mirrored per house; the choice is stored with a timestamp and exported as `orientation_by_house`. It is a display "
              "setting only — not a fit and not the pre-registered camera ↔ WISER mapping (fitted later from the blind clicks); "
              "the user's chosen orientation may serve as an independent prior / check for that fit.\n",
              _md_table(rost),
              "\nClose-up clips: source `D:/Field2026_analysis_out/2026c/inhand_closeups/SF07.MOV … SF12.MOV` (read-only; every sha256 "
              "checked against that folder's `MANIFEST_sha256.csv` before transcoding; sources unchanged afterwards), transcoded once to "
              "H.264 MP4 (`identity_page/closeups/`). Per the folder README: SF07, SF08, SF09, SF10, SF12 were filmed 2026-09-10 "
              "07:54–08:19 (AM round); SF11 on 2026-08-30 (the user, 2026-10-10: its implant came off early, so an earlier clip is used); the "
              "files' `creation_time` tag (2026-10-10 20:3x UTC) is the transfer time, not the filming time. The clips are H.264 720 × 1280 "
              "portrait (SF11 1280 × 720), 30 fps.\n",
              _md_table(pd.DataFrame(pdata.get("closeups", [])), None)]
    L += [DEFINITIONS,
          "## What is not verified\n",
          "- CH07 = house_2 / CH08 = house_1 rests on the 09-07 evidence (plan facts); the B4 correlation is reported, not used to decide.",
          "- The 09-05 check validates the box events at one round (handled placements); natural night crossings are not validated, and "
          "the dilated rectangle (± 28–33 in around the ROI centre) also counts an animal just outside the house as 'in'.",
          "- In-house positions use the accepted P0 WISER → paddock map (one CH01 hour, test median 4.4 in) and the house poses; the "
          "WISER tag sits on the head; WISER is a 2-D solve (no z). The arrangement layer is not accepted until the user's clicks pass "
          "the operator's rule (≥ 4 of the first 5 flashes with ≥ 3 identified animals; the later, pre-registered step).",
          "- SE = sd / √n ignores autocorrelation of consecutive fixes (a lower bound).",
          "- A colour insert shorter than the 2-s I-frame spacing can fall between I-frames and be missed by the scan.",
          "- Correction 2026-10-11 (plan amendments 12-13, confirmed by the user): tag 3058 rode on SF11's implant; at 09-07 06:10:45 "
          "the implant fell off with the tag, the rat stayed in the paddock untagged until it was taken out at the AM round, and the "
          "last 3058 fix (08:20) is the implant in house_2 (the default tracks' `m_off_animal` flag on those fixes is correct). From "
          "08:20 to 09-11 19:40 SF11 is absent and the paddock held five animals, all tagged: rosters are complete except in tag "
          "dropouts (SF11 09-02 00:03 → 08:15 and 09-07 06:10:45 → 08:20; SF12 night 08-30 / 31). The 10-10 version called every "
          "roster after 09-07 06:10 a lower bound; no event, position, segment, roster or check result depended on that; only the "
          "`all_tracked` share changed (box_occupancy_1s.csv.gz rebuilt from the unchanged states_1s.npz; earlier versions in "
          "`superseded_20261011/` and `superseded_20261011b/`).",
          "\n## Files\n",
          f"Run `{run.as_posix()}`: `scan/`, `scan_control/` (per-file I-frame tables), `scan_inventory.csv`, `scan_log.jsonl`, "
          "`colour_threshold.json`, `colour_segments.csv`, `colour_log_rows.csv`, `control_hours.csv`, `box_events.csv`, "
          "`box_events_sensitivity.csv.gz`, `box_occupancy_1s.csv.gz`, `states_1s.npz`, `check_0905.csv`, `check_0905_sensitivity.csv`, "
          "`wiser_summary.json`, `inhouse_minutes.csv.gz`, `inhouse_frames.json`, `camera_house_check.csv`, `camera_house_minutes.csv.gz`, "
          "`identity_page/` (`index.html`, `frames/`, `closeups/`, `page_data.json`, `page_check.json`), `run.json`. "
          "Data map: `cv/cv_field/DATA_MAP_c1yolo_wiser.md` section K."]
    out = rep / REPORT_NAME
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    ptr = {"run_dir": run.as_posix(), "cohort": COHORT, "direction": DIRECTION, "analysis": "inbox_p0",
           "drivers": ["cv/cv_field/inbox_p0.py", "cv/cv_field/inbox_identity_page.py"], "report": REPORT_NAME, "plan": PLAN,
           "git_commit": git_commit(REPO), "identity_page": (run / "identity_page" / "index.html").as_posix(),
           "clicks_export_dir": "cv/configs/inbox_identity_2026c/", "closeups_source": "D:/Field2026_analysis_out/2026c/inhand_closeups",
           "threshold": thr["thr"], "n_segments": int(len(seg)), "check_0905": v["verdict"], "n_events": int(len(ev)),
           "n_inhouse_minutes": int(len(ih))}
    (rep / POINTER_NAME).write_text(json.dumps(ptr, indent=2) + "\n", encoding="utf-8")
    print(f"[report] {out.as_posix()} + {POINTER_NAME}", flush=True)
    return out


# ----------------------------------------------------------------------------------------------- self-test
def _synthetic_video(path: Path, colour_from: float, colour_to: float, dur: float = 24.0, fps: int = 20, gop: int = 40) -> bool:
    """A small H.264 file: grey (IR-like, R = G = B) frames with a coloured stretch [colour_from, colour_to) s."""
    try:
        import av
    except ImportError:
        return False
    with av.open(str(path), mode="w") as c:
        s = c.add_stream("libx264", rate=fps)
        s.width, s.height, s.pix_fmt = 320, 240, "yuv420p"
        s.codec_context.gop_size = gop
        s.codec_context.options = {"bf": "0", "g": str(gop), "keyint_min": str(gop), "sc_threshold": "0", "crf": "18"}
        rng = np.random.default_rng(0)
        for k in range(int(dur * fps)):
            t = k / fps
            base = np.full((240, 320), 100 + (k % 7), np.uint8)
            img = np.dstack([base, base, base])
            if colour_from <= t < colour_to:
                img = img.copy()
                img[..., 0] = 160
                img[..., 2] = 60
            img[rng.integers(0, 240), rng.integers(0, 320)] = 255
            fr = av.VideoFrame.from_ndarray(img, format="rgb24")
            fr.pts = k
            for p in s.encode(fr):
                c.mux(p)
        for p in s.encode():
            c.mux(p)
    return True


def _synthetic_tracks(root: Path, gt=GT_0905, day: str = "2026-09-05") -> None:
    """Default-track files for 09-05 08:30-10:00: each animal in its house until its exit time, away, back at its entry."""
    rois = load_rois()
    rng = np.random.default_rng(5)
    ex = {a: t for a, h, k, t in gt if k == "exit"}
    en = {a: (h, t) for a, h, k, t in gt if k == "enter"}
    for a in LABELS:
        t_local = pd.date_range(f"{day} 08:30:00", f"{day} 10:00:00", freq="250ms")
        t_ex, (h_en, t_en) = pd.Timestamp(f"{day} {ex[a]}"), en[a]
        t_en = pd.Timestamp(f"{day} {t_en}")
        cx = np.where(t_local < t_ex, rois["house_2"]["x"], np.where(t_local >= t_en, rois[h_en]["x"], 300.0))
        cy = np.where(t_local < t_ex, rois["house_2"]["y"], np.where(t_local >= t_en, rois[h_en]["y"], 630.0))
        x, y = cx + rng.normal(0, 2, len(cx)), cy + rng.normal(0, 2, len(cy))
        t_ms = ((t_local.tz_localize(TZ).tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(milliseconds=1)).to_numpy(np.int64)
        df = pd.DataFrame({"t_ms": t_ms, "t_al_ms": t_ms - 150, "shortid": 1, "x_raw": x, "y_raw": y, "anchors_used": 8, "valid": 1,
                           "m_handling": 0, "m_silence": 0, "m_tag_validity": 0, "m_adc_lane": 0, "m_off_animal": 0, "x": x, "y": y,
                           "vx": 0.0, "vy": 0.0, "method": "V3", "imu_ok": 1, "imu_state": 1, "zupt": 0, "loco_boost": 0})
        (root / a).mkdir(parents=True, exist_ok=True)
        df.to_csv(root / a / f"{day.replace('-', '')}.csv.gz", index=False)


def selftest() -> int:
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    # A. threshold, runs, edges, merge, log matching
    th = log_gap_threshold(np.r_[np.zeros(500), [0.004, 0.01], [12.0, 15.0, 33.0]])
    rec("threshold: largest log10 gap (0.01 -> 12) mid-point", abs(th["thr"] - np.sqrt(0.01 * 12.0)) < 1e-9, f"{th['thr']:.4g}")
    vals = np.r_[np.zeros(1000), [0.00081, 0.01137, 0.012, 0.04563, 0.1412, 0.35639, 0.53238],     # the observed isolated IR values
                 [2.6096, 3.03, 3.19, 3.23, 14.56, 20.0, 30.0]]
    rec("amendment 6: floor 1e-4 splits the IR cluster, floor 0.01 separates IR (<= 0.53) from colour (>= 2.61)",
        log_gap_threshold(vals, LOG_FLOOR)["thr"] < 0.01137
        and abs(log_gap_threshold(vals, LOG_FLOOR_AMENDED)["thr"] - np.sqrt(0.53238 * 2.6096)) < 1e-9,
        f"{log_gap_threshold(vals, LOG_FLOOR)['thr']:.4g} / {log_gap_threshold(vals, LOG_FLOOR_AMENDED)['thr']:.4g}")
    rec("colour runs", colour_runs(np.array([0, 1, 1, 0, 0, 1, 0, 1, 1, 1], bool)) == [(1, 2), (5, 5), (7, 9)])
    t0 = datetime(2026, 9, 10, 12, 27, 0)
    fr = [{"t": t0 + timedelta(seconds=k * 0.05), "chroma": 0.0 if k < 31 else 15.0, "file": "f", "frame_idx": 100 + k} for k in range(61)]
    st, fl = refine_start(fr, 1.0, t0 + timedelta(seconds=3))
    rec("refine start = first colour frame of the stretch", st["frame_idx"] == 131 and fl == "ok", f"{st['frame_idx']} {fl}")
    fr2 = [{"t": t0 + timedelta(seconds=k * 0.05), "chroma": 15.0 if k < 23 else 0.0, "file": "f", "frame_idx": k} for k in range(61)]
    en, lc, fl2 = refine_end(fr2, 1.0, t0)
    rec("refine end = first IR frame after the stretch", en["frame_idx"] == 23 and lc["frame_idx"] == 22 and fl2 == "ok")
    s1 = {"start": t0, "end": t0 + timedelta(seconds=5), "end_file": "a", "end_frame_idx": 1, "last_colour": None, "n_colour_keyframes": 2,
          "key_chroma": [10.0], "flags": ""}
    s2 = {**s1, "start": t0 + timedelta(seconds=5.5), "end": t0 + timedelta(seconds=9)}
    s3 = {**s1, "start": t0 + timedelta(seconds=30), "end": t0 + timedelta(seconds=33)}
    mg = merge_intervals([s1, s2, s3])
    rec("merge segments < 1 s apart", len(mg) == 2 and mg[0]["end"] == s2["end"])
    seg = {"camera": "CH07", "start": datetime(2026, 9, 10, 12, 27, 3), "end": datetime(2026, 9, 10, 12, 27, 25)}
    m = match_log(seg)
    rec("log match: 09-10 12:27 CH07 -> row 6", m["log_row"] == 6 and m["match_type"] == "op_on", str(m))
    m2 = match_log({**seg, "camera": "CH08"})
    rec("log match: the same time on CH08 (row says CH07) -> unmatched", m2["unmatched"])
    m3 = match_log({"camera": "CH08", "start": datetime(2026, 9, 10, 7, 50), "end": datetime(2026, 9, 10, 7, 52)})
    rec("log match: inside the 09-10 AM round -> placement row (window)", m3["log_row"] == 2 and m3["match_type"] == "window")
    m4 = match_log({"camera": "CH07", "start": datetime(2026, 9, 10, 9, 10, 20), "end": datetime(2026, 9, 10, 9, 10, 35)})
    rec("log match: OFF-only row matched on the segment end", m4["log_row"] == 3 and m4["match_type"] == "op_off")
    m5 = match_log({"camera": "CH07", "start": datetime(2026, 9, 10, 12, 31), "end": datetime(2026, 9, 10, 12, 31, 8)})
    rec("log match: > 2 min from any row -> unmatched", m5["unmatched"])
    # B. states, dwell, events
    n = 400
    n_fix = np.full(n, 4)
    n_fix[250:300] = 0
    in2 = np.where(np.arange(n) < 200, 4, 0)
    in2[100:105] = 0                                       # 5-s flicker out: absorbed
    in1 = np.where(np.arange(n) >= 300, 4, 0)
    in1[320:330] = 0                                       # 10-s flicker inside house_1: absorbed
    raw = raw_states(n_fix, {"house_1": in1, "house_2": in2})
    rec("6-s smoothing: a 5-s flicker is already majority-in on its edges", raw[100] == S_H2 and raw[103] == S_OUT)
    clean, trans = dwell_clean(raw)
    ev = transitions_to_events(trans, "SFxx", datetime(2026, 9, 5, 8, 0))
    kinds = [(e["kind"], e["house"]) for e in ev]
    rec("dwell: flickers absorbed; exit house_2, enter house_1 across a 50-s unknown gap", kinds == [("exit", "house_2"), ("enter", "house_1")]
        and ev[0]["time"].endswith("08:03:21") and ev[1]["across_unknown_s"] > 0, f"{kinds} {[e['time'] for e in ev]} {[e['across_unknown_s'] for e in ev]}")
    rec("dwell: short unknown gap bridged", dwell_clean(np.r_[np.full(30, S_H2), np.full(10, S_UNK), np.full(30, S_H2)])[0][35] == S_H2)
    rec("dwell: a < 20-s first run does not set the state", dwell_clean(np.r_[np.full(10, S_OUT), np.full(30, S_H1)])[1] == [])
    # house frame + map
    pose = {"centre": (100.0, 50.0), "ridge_deg": 90.0}
    hf = to_house_frame([[100.0, 60.0], [90.0, 50.0]], pose)
    rec("house frame: +y along a 90-deg ridge; -x is +across", np.allclose(hf, [[10, 0], [0, 10]]), str(hf.round(6).tolist()))
    mp = {"s": 1.0, "theta": 0.0, "c": np.array([0.0, 0.0]), "d": np.array([-5.0, 2.0])}
    rec("WISER -> paddock: translation", np.allclose(wiser_to_paddock([[10, 10]], mp), [[5, 12]]))
    rec("pearson / spearman", abs(pearson([1, 2, 3, 4], [2, 4, 6, 8.5]) - 1) < 0.01 and abs(spearman([1, 2, 3, 4], [1, 5, 9, 20]) - 1) < 1e-9)
    # end to end on synthetic tracks: the 09-05 check passes, a swapped order fails
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _synthetic_tracks(tmp / "tracks")
        res = phase_wiser(tmp, track_root=tmp / "tracks", t0=datetime(2026, 9, 5, 8, 30), t1=datetime(2026, 9, 5, 10, 0), days=["2026-09-05"])
        chk = pd.read_csv(tmp / "check_0905.csv")
        rec("synthetic 09-05: PASS, every |dt| <= 1 s", res["check_0905"]["verdict"] == "PASS" and chk.delta_s.abs().max() <= 1.0,
            f"{res['check_0905']['verdict']} max |dt| {chk.delta_s.abs().max()}")
        ev = pd.read_csv(tmp / "box_events.csv")
        sw = ev.copy()
        i9, i7 = sw.index[(sw.animal == "SF09") & (sw.kind == "enter")][0], sw.index[(sw.animal == "SF07") & (sw.kind == "enter")][0]
        sw.loc[i9, "time"], sw.loc[i7, "time"] = ev.loc[i7, "time"], ev.loc[i9, "time"]
        sw.loc[i9, "time"] = "2026-09-05 09:49:53"
        rec("synthetic 09-05: SF09 entering after SF07 -> FAIL (order)", verdict_0905(check_0905(sw))["verdict"] == "FAIL")
        occ = pd.read_csv(tmp / "box_occupancy_1s.csv.gz")
        r0 = occ[occ.time == "2026-09-05 08:40:00"].iloc[0]
        rec("occupancy: six in house_2 before the removal", r0.n_house_2 == 6 and r0.all_tracked, f"{r0.house_2}")
        # SF11 (corrected 2026-10-11): unknown while present (06:10:45-08:20) -> untracked; after 08:20 absent, not a gap
        t_a = datetime(2026, 9, 7, 8, 0)
        stt = np.full((6, 2400), S_H2, np.int8)
        stt[4, :] = S_UNK
        oc = occupancy_table(stt, list(LABELS), t_a)
        b4, af = oc.iloc[600], oc.iloc[1800]                     # 08:10 and 08:30
        rec("occupancy: SF11 untagged-present 06:10:45-08:20 (implant + tag off), absent after 08:20 (all_tracked True)",
            b4.untracked == "" and bool(b4.sf11_untagged) and not b4.all_tracked and not b4.sf11_absent and af.untracked == ""
            and bool(af.all_tracked) and bool(af.sf11_absent) and not af.sf11_untagged and af.n_house_2 == 5,
            f"{b4.untracked!r} {b4.sf11_untagged} {b4.all_tracked} / {af.untracked!r} {af.all_tracked} {af.sf11_absent}")
        oc2 = occupancy_table(stt, list(LABELS), datetime(2026, 9, 2, 0, 0))
        rec("occupancy: SF11's tag dropout 09-02 00:03-08:15 = untagged, present (all_tracked False)",
            bool(oc2.iloc[600].sf11_untagged) and not oc2.iloc[600].all_tracked and oc2.iloc[600].untracked == "")
        r1 = occ[occ.time == "2026-09-05 09:55:00"].iloc[0]
        rec("occupancy: five in house_2, SF08 in house_1 after the release", r1.n_house_2 == 5 and r1.house_1 == "SF08")
        phase_inhouse(tmp, track_root=tmp / "tracks", days=["2026-09-05"])
        ih = pd.read_csv(tmp / "inhouse_minutes.csv.gz")
        rec("in-house minutes: rows only for minutes inside a house, SE small", len(ih) > 0 and set(ih.house) <= set(HOUSES)
            and ih.along_se_in.max() < 1.0 and (ih.n_s_in >= INHOUSE_MIN_S).all(), f"{len(ih)} rows")
        # synthetic video: scan + full-rate edges
        vp = tmp / "CH07_2026-09-10_12-00-00_to_12-00-24.mp4"
        if _synthetic_video(vp, 10.3, 18.75):
            r = scan_file(vp.as_posix(), "2026-09-10T12:00:00", (tmp / "scan.csv").as_posix())
            sc = pd.read_csv(tmp / "scan.csv")
            colour_keys = sc[sc.chroma >= 1.0]
            rec("video scan: I-frames every 2 s, colour I-frames at 12, 14, 16, 18 s", r["n_key"] == 12 and
                colour_keys.t_rel_s.round(1).tolist() == [12.0, 14.0, 16.0, 18.0], f"{sc.t_rel_s.round(2).tolist()} {colour_keys.t_rel_s.tolist()}")
            kidx = dict(zip(sc.pts.astype(int), sc.frame_idx.astype(int)))
            st0 = datetime(2026, 9, 10, 12, 0, 0)
            fs = decode_window(vp.as_posix(), st0, st0 + timedelta(seconds=9), st0 + timedelta(seconds=12), kidx)
            a, _ = refine_start(fs, 1.0, st0 + timedelta(seconds=12))
            fe = decode_window(vp.as_posix(), st0, st0 + timedelta(seconds=18), st0 + timedelta(seconds=21), kidx)
            b, lc, _ = refine_end(fe, 1.0, st0 + timedelta(seconds=18))
            rec("video edges at full rate: ON frame 206 (10.30 s), OFF frame 375 (18.75 s), frame index counted from the key frame",
                a["frame_idx"] == 206 and b["frame_idx"] == 375 and abs((a["t"] - st0).total_seconds() - 10.3) < 1e-6,
                f"{a['frame_idx']} {b['frame_idx']} {(a['t'] - st0).total_seconds()}")
        else:
            print("[SKIP] synthetic video (PyAV not available in this interpreter)")
    print(("PASS" if ok else "FAIL") + " - inbox_p0 self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run", default=None, help="run folder, or 'new'")
    ap.add_argument("--phases", nargs="+", default=["scan", "segments", "wiser", "inhouse", "camhouse", "report"])
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.run in (None, "new"):
        import output_paths as op
        run = op.run_dir(NAME, COHORT, make_figures=True)
    else:
        run = Path(args.run)
    print(f"[run] {run.as_posix()}", flush=True)
    t_start = datetime.now()
    if "scan" in args.phases:
        phase_scan(run, args.workers)
    if "segments" in args.phases:
        phase_segments(run)
    if "wiser" in args.phases:
        phase_wiser(run)
    if "inhouse" in args.phases:
        phase_inhouse(run)
    if "camhouse" in args.phases:
        phase_camhouse(run)
    if "occupancy" in args.phases:
        phase_occupancy(run)
    meta_path = run / "run.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta.setdefault("phases_run", []).append({"phases": args.phases, "started": t_start.isoformat(timespec="seconds"),
                                             "finished": datetime.now().isoformat(timespec="seconds"), "git_commit": git_commit(REPO)})
    meta.update({"plan": PLAN, "driver": "cv/cv_field/inbox_p0.py", "cohort": COHORT, "run_dir": run.as_posix(),
                 "params": {"dilate_in": DILATE_IN, "smooth_s": SMOOTH_S, "min_dwell_s": MIN_DWELL_S, "edge_s": EDGE_S,
                            "merge_s": MERGE_S, "log_tol_s": LOG_TOL_S, "op_fast_s": OP_FAST_S, "control_seed": CONTROL_SEED,
                            "inhouse_min_s": INHOUSE_MIN_S, "chroma_step": CHROMA_STEP, "grey": [GREY_W, GREY_H]},
                 "recording_repo_commit": git_commit(REPO.parent / "Field_2026_Social_Recording")})
    meta_path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    if "report" in args.phases:
        write_report(run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
