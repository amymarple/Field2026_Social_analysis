r"""select_label_round1.py — round-1 labelling package for the cohort-3 CH01/CH02 rat detector (plan B).

Specification: implementation_plan/2026-10-06-wiser-label-loop.md (part B; pre-registered, approved 2026-10-06) + its
dated amendments (amendment 1 fixes the implementation details before any result). Data map:
cv/cv_field/DATA_MAP_c1yolo_wiser.md (section I). The WISER pixel kit comes from build_wiser_pixel_kit.py (part A).

Stages:
  --pool    B1-B2: per camera ~1 500 night times (1 200 stratified by WISER: tagged animals outside the houses 0 / 1-2 / >= 3
            x motion of the most active of them x night x hour, + 300 uniform; >= 10 s apart; nights 08-30 -> 09-10 minus
            the frozen test night 09-05; 21:00 -> 04:20; handling windows +- 5 min out). Frames grabbed once (the
            grab_frames.py command, CPU exact seek, upright, PNG) + YOLO v5 (rat_m_v5, imgsz 1280, conf >= 0.05) + DINOv3
            ViT-B/16 CLS embeddings, all cached in $OUT/2026c/label_round1_pool_<ts>/ (resumable; never re-grabbed).
  --select  B3-B6 (after the kit): per-frame scores, 200 frames per camera by the quotas, the test extension on 09-05
            (+ 30 per camera, select_pano_targets' stratified test rule, >= 5 min apart; the existing 40 copied unchanged),
            the package $OUT/2026c/label_round1_<ts>/ and the report results/2026c/cv_field/reports/
            cv_field_wiser_label_loop_round1_2026c.md (+ pointer run_manifest_wiser_label_loop_round1_2026c.json).
Rules: machine boxes and WISER positions are proposals; every box in the dataset is a human decision. No model ever runs
on a test-night frame; test frames get no prelabel and no WISER sidecar. The agent never looks at images.

Usage (cv env: C:/Users/Cornell/.conda/envs/cv/python.exe, PYTHONIOENCODING=utf-8):
  python cv/cv_field/select_label_round1.py --selftest
  python cv/cv_field/select_label_round1.py --pool [--out <pool dir>] [--workers 4]        # resumable with --out
  python cv/cv_field/build_wiser_pixel_kit.py --build --pool <pool dir>
  python cv/cv_field/select_label_round1.py --select --pool <pool dir> --kit <kit dir> [--out <package dir>]
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(HERE.parent), str(REPO / "wiser" / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import build_wiser_pixel_kit as K  # noqa: E402  (imports frame_correction first)
import grab_frames as gf  # noqa: E402

OUT_ROOT = K.OUT_ROOT
COHORT, DIRECTION = "2026c", "cv_field"
PLAN = K.PLAN
DRIVER = "cv/cv_field/select_label_round1.py"
REPORT_NAME = "cv_field_wiser_label_loop_round1_2026c.md"
POINTER_NAME = "run_manifest_wiser_label_loop_round1_2026c.json"
VIDEO_ROOT = Path("F:/3rd_rat")
WEIGHTS = OUT_ROOT / "2026a" / "social_field_rat_backup_20261005" / "computer_vision" / "outputs" / "runs" / "rat_m_v5" / "weights" / "best.pt"
WEIGHTS_SHA256 = "2d7294f3e29da845c8c6c26a39d427ffbe374274524e2cfd922c0edd51b63360"
IMGSZ, CONF_FLOOR, PRELABEL_CONF = 1280, 0.05, 0.25
CAMS = K.CAMS
NIGHTS = K.NIGHTS
TEST_NIGHT = K.TEST_NIGHT
SEEDS = {"CH01": 0, "CH02": 1}
POOL_N_STRAT, POOL_N_RAND, POOL_SEP_S = 1200, 300, 10.0
STRATA = ("0|none", "1-2|still", "1-2|active", "1-2|locomoting", ">=3|still", ">=3|active", ">=3|locomoting")
PER_CAM, MAX_PER_NIGHT, SEP_S = 200, 25, 10.0
QUOTA_ORDER = ("visible_suspected_miss", "social", "hard_negative", "wiser_strata", "dino_diversity", "uniform_random")
QUOTAS = {"visible_suspected_miss": 60, "wiser_strata": 50, "social": 30, "hard_negative": 20, "dino_diversity": 20,
          "uniform_random": 20}
MISS_R_IN, SOCIAL_R_IN, EVENT_BRIDGE_S = 20.0, 20.0, 5.0
RAIN_MM = 1.0
N_OVERLAP_PER_CAM, OVERLAP_SEED = 10, 0
TEST_PER_CAM, TEST_SEP_S, TEST_MIX = 30, 300.0, {"zero": 0.2, "few": 0.4, "many": 0.4}
TEST_SEED_BASE = 1000
TEST_DIR = REPO / "cv" / "dataset" / "rat_pano_test" / "images"
PRIOR_TEST_TARGETS = OUT_ROOT / "2026c" / "cv_field_pano_select_20260929_1143" / "targets_test.csv"
REVIEW_DIR = REPO / "cv" / "configs" / "c1yolo_review_2026c"
FIXED_SPOTS = OUT_ROOT / "2026c" / "cv_field_c1yolo_video_20261005_1848" / "fixed_spots" / "fixed_spots.csv"
DINO_SIZE = (1024, 288)                                   # aspect-preserving (3.56:1), multiples of 16
K_CLUSTERS = 20
MANIFEST_COLS = ["image", "camera", "video", "frame", "t_pc", "night", "split", "quota", "reason", "n_boxes_v5", "max_conf_v5",
                 "n_wiser_in_view", "n_visible_suspected_miss", "social", "all_tracked", "map_validated", "cluster_id", "overlap"]
SIDECAR_NOTE = ("WISER circles = tag position +/- ~14 in; hints only; untagged or untracked animals are not shown; "
                "hidden = do not box")
SHOWINFO_PTS = re.compile(r"\bpts:\s*(-?\d+)\s+pts_time:")
SHOWINFO_TB = re.compile(r"config in time_base:\s*(\d+)/(\d+)")
FMT = "%Y-%m-%d %H:%M:%S"


def sha256(p: Path) -> str:
    return K.sha256(p)


def parse_t(s: str) -> datetime:
    s = str(s)
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f" if "." in s else FMT)


def epoch_s(x) -> np.ndarray:
    """Datetimes (Series / array / strings) -> float seconds since 1970, independent of the datetime64 unit."""
    return pd.Series(pd.to_datetime(x)).astype("datetime64[ns]").astype("int64").to_numpy() / 1e9


def jsonable(o):
    return K.jsonable(o)


# ----------------------------------------------------------------------------------------------- video index (fMP4)
def _boxes(f, start, end):
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        h = f.read(16)
        sz, typ = struct.unpack(">I4s", h[:8])
        hdr = 8
        if sz == 1:
            sz, hdr = struct.unpack(">Q", h[8:16])[0], 16
        if sz == 0:
            sz = end - pos
        if sz < hdr:
            break
        yield typ.decode("latin1"), pos + hdr, pos + sz
        pos += sz


def video_sample_ticks(path: Path) -> tuple[np.ndarray, int]:
    """Presentation times (integer ticks of the video track's timescale) of every video sample of a fragmented MP4, read
    from the moov / moof boxes only (no payload): trex defaults, tfhd, tfdt, trun (+ composition offsets). Also works
    for an unfragmented file's stts / ctts. -> (ticks sorted in file order, timescale)."""
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        tracks, trex, vid, out = {}, {}, None, []
        stts, ctts = None, None

        def read(a, b):
            f.seek(a)
            return f.read(b - a)
        for typ, c0, p1 in _boxes(f, 0, size):
            if typ == "moov":
                for t2, d0, q1 in _boxes(f, c0, p1):
                    if t2 == "trak":
                        tid = hdl = ts = None
                        st_tt = st_ct = None
                        for t3, e0, r1 in _boxes(f, d0, q1):
                            if t3 == "tkhd":
                                b = read(e0, r1)
                                tid = struct.unpack(">I", b[12:16] if b[0] == 0 else b[20:24])[0]
                            elif t3 == "mdia":
                                for t4, g0, s1 in _boxes(f, e0, r1):
                                    if t4 == "mdhd":
                                        b = read(g0, s1)
                                        ts = struct.unpack(">I", b[12:16] if b[0] == 0 else b[20:24])[0]
                                    elif t4 == "hdlr":
                                        hdl = read(g0, s1)[8:12].decode("latin1")
                                    elif t4 == "minf":
                                        for t5, h0, u1 in _boxes(f, g0, s1):
                                            if t5 == "stbl":
                                                for t6, k0, w1 in _boxes(f, h0, u1):
                                                    if t6 == "stts":
                                                        st_tt = read(k0, w1)
                                                    elif t6 == "ctts":
                                                        st_ct = read(k0, w1)
                        tracks[tid] = (hdl, ts)
                        if hdl == "vide" and vid is None:
                            vid, stts, ctts = tid, st_tt, st_ct
                    elif t2 == "mvex":
                        for t3, e0, r1 in _boxes(f, d0, q1):
                            if t3 == "trex":
                                b = read(e0, r1)
                                trex[struct.unpack(">I", b[4:8])[0]] = struct.unpack(">I", b[12:16])[0]
                if stts is not None:                         # samples listed in the moov (unfragmented part)
                    n = struct.unpack(">I", stts[4:8])[0]
                    durs = []
                    for i in range(n):
                        cnt, dlt = struct.unpack(">II", stts[8 + 8 * i:16 + 8 * i])
                        durs += [dlt] * cnt
                    cts = [0] * len(durs)
                    if ctts is not None:
                        ver = ctts[0]
                        n2 = struct.unpack(">I", ctts[4:8])[0]
                        k = 0
                        for i in range(n2):
                            cnt, off = struct.unpack(">I" + ("i" if ver == 1 else "I"), ctts[8 + 8 * i:16 + 8 * i])
                            for _ in range(cnt):
                                if k < len(cts):
                                    cts[k] = off
                                k += 1
                    t = 0
                    for d, c in zip(durs, cts):
                        out.append(t + c)
                        t += d
            elif typ == "moof":
                for t2, d0, q1 in _boxes(f, c0, p1):
                    if t2 != "traf":
                        continue
                    tid = ddur = base = None
                    samples = []
                    for t3, e0, r1 in _boxes(f, d0, q1):
                        b = read(e0, r1)
                        if t3 == "tfhd":
                            fl = int.from_bytes(b[1:4], "big")
                            tid = struct.unpack(">I", b[4:8])[0]
                            o = 8 + (8 if fl & 0x1 else 0) + (4 if fl & 0x2 else 0)
                            if fl & 0x8:
                                ddur = struct.unpack(">I", b[o:o + 4])[0]
                        elif t3 == "tfdt":
                            base = struct.unpack(">Q", b[4:12])[0] if b[0] == 1 else struct.unpack(">I", b[4:8])[0]
                        elif t3 == "trun":
                            ver, fl = b[0], int.from_bytes(b[1:4], "big")
                            n = struct.unpack(">I", b[4:8])[0]
                            o = 8 + (4 if fl & 0x1 else 0) + (4 if fl & 0x4 else 0)
                            for _ in range(n):
                                dur, cto = None, 0
                                if fl & 0x100:
                                    dur = struct.unpack(">I", b[o:o + 4])[0]
                                    o += 4
                                if fl & 0x200:
                                    o += 4
                                if fl & 0x400:
                                    o += 4
                                if fl & 0x800:
                                    cto = struct.unpack(">i" if ver == 1 else ">I", b[o:o + 4])[0]
                                    o += 4
                                samples.append((dur, cto))
                    if tid != vid or base is None:
                        continue
                    t = base
                    for dur, cto in samples:
                        out.append(t + cto)
                        t += dur if dur is not None else (ddur if ddur is not None else trex.get(tid, 0))
        if vid is None:
            raise RuntimeError(f"{path}: no video track")
        return np.asarray(out, np.int64), int(tracks[vid][1])


class VideoIndex:
    """Sample ticks per video, parsed once and cached (memory + <dir>/<stem>.npz)."""

    def __init__(self, cache_dir: Path | None):
        self.dir = Path(cache_dir) if cache_dir else None
        self.mem: dict[str, tuple[np.ndarray, int]] = {}
        self.lock = threading.Lock()

    def get(self, video: Path) -> tuple[np.ndarray, int]:
        """Thread-safe: the whole lookup runs under the lock (parsing takes ~0.1 s), and the cache file is written to a
        temporary name and renamed, so no reader ever sees a partial file (2026-10-06: two pool workers raced on one)."""
        key = video.stem
        with self.lock:
            if key in self.mem:
                return self.mem[key]
            p = self.dir / f"{key}.npz" if self.dir else None
            val = None
            if p is not None and p.exists():
                try:
                    z = np.load(p)
                    val = (z["ticks"], int(z["timescale"]))
                except (EOFError, OSError, ValueError, KeyError):
                    val = None                                  # a partial file from an interrupted run: rebuild
            if val is None:
                val = video_sample_ticks(video)
                if p is not None:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    tmp = p.with_name(p.stem + ".tmp.npz")
                    np.savez_compressed(tmp, ticks=val[0], timescale=val[1], monotone=bool(np.all(np.diff(val[0]) > 0)))
                    os.replace(tmp, p)
            self.mem[key] = val
            return val


def frame_index(ticks: np.ndarray, pts: int) -> int:
    """0-based sample index whose presentation tick equals pts (the file's samples are in presentation order)."""
    i = int(np.searchsorted(ticks, pts))
    if i < len(ticks) and ticks[i] == pts:
        return i
    raise RuntimeError(f"pts {pts} not a sample of the file (nearest {ticks[min(i, len(ticks) - 1)]})")


# ----------------------------------------------------------------------------------------------- grabbing
def grab_exact(ffmpeg: str, video: Path, offset: float, cam: str) -> tuple[np.ndarray, int, int]:
    """grab_frames.grab's command (CPU decode, exact seek: the first frame with PTS >= offset; CH01/CH02 transposed
    upright) + the frame's integer PTS and time base from showinfo (its pts_time prints only 6 significant digits).
    -> (upright BGR image, pts ticks, time-base denominator)."""
    w, h = gf.STORED[cam]
    vf = ("transpose=2," if cam in gf.PANO else "") + "showinfo"
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-copyts", "-ss", f"{offset:.3f}", "-i", str(video), "-frames:v", "1", "-an",
           "-vf", vf, "-pix_fmt", "bgr24", "-f", "rawvideo", "-"]
    p = subprocess.run(cmd, capture_output=True)
    need = w * h * 3
    err = p.stderr.decode(errors="replace")
    if p.returncode != 0 or len(p.stdout) != need:
        raise RuntimeError(f"{video.name} @ {offset:.3f}s: decode failed ({err[-300:]})")
    m, tb = SHOWINFO_PTS.findall(err), SHOWINFO_TB.findall(err)
    if not m or not tb:
        raise RuntimeError(f"{video.name} @ {offset:.3f}s: no showinfo pts")
    uw, uh = gf.upright_size(cam)
    return np.frombuffer(p.stdout, np.uint8).reshape(uh, uw, 3), int(m[0]), int(tb[0][1])


def video_start(video: Path) -> datetime:
    m = gf.NAME.match(video.name)
    return datetime.strptime(f"{m['d']} {m['s']}", "%Y-%m-%d %H-%M-%S")


def grab_target(cam: str, t: datetime, segs, ffmpeg: str, vindex: VideoIndex) -> dict:
    """One target time -> image, video, frame index, frame time. Raises RuntimeError on failure."""
    hit = gf.locate(t, segs)
    if not hit:
        raise RuntimeError("no video")
    video, off = hit
    ticks, tsc = vindex.get(video)
    img, pts, den = grab_exact(ffmpeg, video, off, cam)
    if den != tsc:
        raise RuntimeError(f"time base 1/{den} != track timescale {tsc}")
    k = frame_index(ticks, pts)
    t_frame = video_start(video) + timedelta(seconds=pts / tsc)
    return {"img": img, "video": video, "frame": k, "pts_ticks": pts, "timescale": tsc, "t_frame": t_frame,
            "snap_s": (t_frame - t).total_seconds(), "image": f"{video.stem}_f{k}.png"}


# ----------------------------------------------------------------------------------------------- models
def load_yolo():
    from ultralytics import YOLO
    if sha256(WEIGHTS) != WEIGHTS_SHA256:
        raise SystemExit(f"{WEIGHTS} sha256 differs from the verified v5 best.pt")
    model = YOLO(str(WEIGHTS))

    def det(img: np.ndarray):
        r = model.predict(img, imgsz=IMGSZ, conf=CONF_FLOOR, verbose=False)[0]
        return r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()
    return det


def load_dino():
    """field_embed's DINO loader (DINOv3 ViT-B/16 when its checkpoint is present); embeddings of the whole upright frame
    resized aspect-preserving to DINO_SIZE (field_embed's square 224 resize would squash a 3.6:1 panorama)."""
    import cv2
    import torch
    import field_embed as fe
    family, repo, variant, patch, weights = fe.resolve_dino_source("dino")
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = fe._load_dino(repo, variant, weights, dev)
    W, H = DINO_SIZE
    if W % patch or H % patch:
        raise SystemExit(f"DINO size {DINO_SIZE} not a multiple of the patch {patch}")

    def emb(img: np.ndarray) -> np.ndarray:
        x = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
        x = cv2.cvtColor(x, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        x = (x - fe._IMAGENET_MEAN) / fe._IMAGENET_STD
        tt = torch.from_numpy(np.transpose(x, (2, 0, 1))[None]).float().to(dev)
        with torch.no_grad():
            f = model(tt)
        return f.detach().cpu().numpy().astype(np.float32).reshape(-1)
    meta = {"family": family, "repo": repo, "variant": variant, "patch": patch, "input_size_wh": list(DINO_SIZE),
            "weights": str(weights) if weights else None, "weights_sha256": sha256(Path(weights)) if weights else None,
            "token": "CLS (field_embed)"}
    return emb, meta


# ----------------------------------------------------------------------------------------------- pool: candidates + draw
def stratum_of(n_out: np.ndarray, motion: np.ndarray) -> np.ndarray:
    nm = np.vectorize(K.MOTION_NAME.get)(motion)
    cnt = np.where(n_out == 0, "0", np.where(n_out <= 2, "1-2", ">=3"))
    return np.where(n_out == 0, "0|none", np.char.add(np.char.add(cnt.astype(str), "|"), nm.astype(str)))


def night_candidates(night: date, m, houses, handling) -> pd.DataFrame:
    """Every whole night second outside the handling windows +- 5 min: tagged animals outside the house zones (n_out), the
    most active state among them, the stratum, the clock hour (camera-independent; WISER frame)."""
    nf = K.load_night_fixes(night, handling=handling)
    secs, tdt = K.kit_seconds(night, handling)
    st = K.wiser_state(nf, secs, m, houses)
    out_ = st["ok"] & ~st["house"]
    n_out = out_.sum(1)
    mot = np.where(out_, st["motion"], 0).max(1)
    t = pd.to_datetime(tdt)
    return pd.DataFrame({"night": str(night), "sec": secs, "t": t, "hour": t.hour, "n_out": n_out, "motion": mot,
                         "stratum": stratum_of(n_out, mot), "all_tracked": st["all_tracked"]})


def video_coverage(cam: str, night: date, t: pd.Series, ffprobe: str, root: Path = VIDEO_ROOT) -> np.ndarray:
    """Second t has video if a segment covers [t, t + 1 s)."""
    segs = gf.segments(root, cam, night + timedelta(days=1), ffprobe)
    tv = t.to_numpy("datetime64[ns]")
    ok = np.zeros(len(tv), bool)
    for s, e, _ in segs:
        ok |= (tv >= np.datetime64(s)) & (tv + np.timedelta64(1, "s") <= np.datetime64(e))
    return ok


class Spacing:
    """Times already taken (epoch s) with a minimum separation check."""

    def __init__(self, sep: float, times=()):
        self.sep = sep
        self.t: list[float] = sorted(float(x) for x in times)

    def free(self, x: float) -> bool:
        i = bisect.bisect_left(self.t, x)
        return not ((i < len(self.t) and self.t[i] - x < self.sep) or (i > 0 and x - self.t[i - 1] < self.sep))

    def add(self, x: float) -> None:
        bisect.insort(self.t, float(x))


def draw_pool(cand: pd.DataFrame, n_strat: int, n_rand: int, sep_s: float, seed: int) -> pd.DataFrame:
    """B2 draw for one camera. cand: eligible seconds (t, night, hour, stratum). Stratified part: an equal share per
    stratum (STRATA order gets the remainder), within a stratum round-robin over its (night, hour) cells in random order,
    a random second of the cell >= sep_s from every pick; strata short of candidates hand their shortfall to the others
    (round-robin). Uniform part: random seconds >= sep_s from every pick. -> picks with kind = strat / random."""
    rng = np.random.default_rng(seed)
    ep = epoch_s(cand["t"])
    sp = Spacing(sep_s)
    picks: list[tuple[int, str]] = []
    cells: dict[str, list[list[int]]] = {}
    for s in STRATA:
        sub = cand.index[cand["stratum"].to_numpy() == s]
        if not len(sub):
            cells[s] = []
            continue
        g = cand.loc[sub].groupby(["night", "hour"]).indices
        lst = [list(cand.loc[sub].index[v]) for v in g.values()]
        for li in lst:
            rng.shuffle(li)
        order = rng.permutation(len(lst))
        cells[s] = [lst[i] for i in order]
    ptr = {s: 0 for s in STRATA}

    def take_one(s: str) -> bool:
        cl = cells[s]
        while cl:
            k = ptr[s] % len(cl)
            pool = cl[k]
            while pool:
                i = pool.pop()
                if sp.free(ep[cand.index.get_loc(i)]):
                    sp.add(ep[cand.index.get_loc(i)])
                    picks.append((i, "strat"))
                    ptr[s] = k + 1
                    return True
            cl.pop(k)                                   # exhausted cell
            if cl:
                ptr[s] = k % len(cl)
        return False

    want = {s: n_strat // len(STRATA) + (1 if i < n_strat % len(STRATA) else 0) for i, s in enumerate(STRATA)}
    got = {s: 0 for s in STRATA}
    for s in STRATA:
        while got[s] < want[s] and take_one(s):
            got[s] += 1
    live = [s for s in STRATA if cells[s]]
    while sum(got.values()) < n_strat and live:
        for s in list(live):
            if sum(got.values()) >= n_strat:
                break
            if take_one(s):
                got[s] += 1
            else:
                live.remove(s)
    allidx = list(cand.index)
    rng.shuffle(allidx)
    nr = 0
    for i in allidx:
        if nr >= n_rand:
            break
        x = ep[cand.index.get_loc(i)]
        if sp.free(x):
            sp.add(x)
            picks.append((i, "random"))
            nr += 1
    out = cand.loc[[i for i, _ in picks]].copy()
    out["kind"] = [k for _, k in picks]
    out["want_strat"] = out["stratum"].map(want)
    return out.sort_values("t").reset_index(drop=True)


def build_pool_targets(log=print) -> tuple[pd.DataFrame, dict]:
    import wiser_assist_p0 as wp
    m, _, _ = K.load_map()
    houses = wp.load_houses()
    handling = K.load_handling()
    _, ffprobe = gf.find_ffmpeg()
    allc = []
    for night in NIGHTS:
        t0 = time.perf_counter()
        c = night_candidates(night, m, houses, handling)
        for cam in CAMS:
            c[f"video_{cam}"] = video_coverage(cam, night, c["t"], ffprobe)
        allc.append(c)
        log(f"candidates {night}: {len(c)} s, strata " + ", ".join(f"{k} {v}" for k, v in c["stratum"].value_counts().items())
            + f", video CH01 {c['video_CH01'].mean():.3f} CH02 {c['video_CH02'].mean():.3f} ({time.perf_counter() - t0:.0f} s)")
    cand = pd.concat(allc, ignore_index=True)
    tg, stats = [], {}
    for cam in CAMS:
        c = cand[cand[f"video_{cam}"]]
        d = draw_pool(c, POOL_N_STRAT, POOL_N_RAND, POOL_SEP_S, SEEDS[cam])
        d.insert(0, "camera", cam)
        tg.append(d)
        stats[cam] = {"eligible_seconds": int(len(c)), "eligible_by_stratum": c["stratum"].value_counts().to_dict(),
                      "drawn_by_stratum": d[d["kind"] == "strat"]["stratum"].value_counts().to_dict(),
                      "drawn_random": int((d["kind"] == "random").sum()), "drawn_by_night": d["night"].value_counts().sort_index().to_dict()}
        log(f"{cam}: {len(d)} targets ({(d['kind'] == 'strat').sum()} stratified, {(d['kind'] == 'random').sum()} uniform)")
    targets = pd.concat(tg, ignore_index=True)
    targets["t_target"] = targets["t"].dt.strftime(FMT)
    return targets[["camera", "night", "t_target", "hour", "kind", "stratum", "n_out", "motion", "all_tracked"]], stats


# ----------------------------------------------------------------------------------------------- pool run
FRAME_FIELDS = ["camera", "night", "t_target", "t_frame", "snap_s", "video", "frame", "pts_ticks", "timescale", "image",
                "png_bytes", "grab_s", "ok", "error", "kind", "stratum", "n_out", "motion"]


def run_pool(out: Path | None, workers: int = 4, limit: int | None = None, log=print) -> Path:
    import cv2
    t_start = time.perf_counter()
    if out is None:
        import output_paths as op
        out = op.run_dir("label_round1_pool", COHORT, make_figures=False)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    logf = open(out / "pool_log.txt", "a", encoding="utf-8")

    def lg(msg):
        log(msg)
        logf.write(f"{datetime.now():%H:%M:%S} {msg}\n")
        logf.flush()

    tpath = out / "pool_targets.csv"
    if tpath.exists():
        targets = pd.read_csv(tpath)
        lg(f"resume: {len(targets)} targets from {tpath.name}")
        stats = json.loads((out / "pool_draw_stats.json").read_text(encoding="utf-8"))
    else:
        targets, stats = build_pool_targets(lg)
        targets.to_csv(tpath, index=False)
        (out / "pool_draw_stats.json").write_text(json.dumps(jsonable(stats), indent=1), encoding="utf-8")
    fpath, dpath = out / "pool_frames.csv", out / "pool_detections.csv"
    done = set()
    if fpath.exists():
        prev = pd.read_csv(fpath)
        done = set(zip(prev.loc[prev["ok"] == 1, "camera"], prev.loc[prev["ok"] == 1, "t_target"]))
    else:
        with open(fpath, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(FRAME_FIELDS)
    if not dpath.exists():
        with open(dpath, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["image", "x1", "y1", "x2", "y2", "conf"])
    todo = targets[[(c, t) not in done for c, t in zip(targets["camera"], targets["t_target"])]]
    if limit:
        todo = todo.head(limit)
    lg(f"{len(done)} frames done, {len(todo)} to grab (workers {workers})")
    ffmpeg, ffprobe = gf.find_ffmpeg()
    vindex = VideoIndex(out / "video_index")
    segs_cache: dict = {}
    seg_lock = threading.Lock()
    for cam in CAMS:
        (out / "pool" / cam).mkdir(parents=True, exist_ok=True)
    (out / "emb").mkdir(exist_ok=True)

    def segs_for(cam, t):
        key = (cam, t.date())
        with seg_lock:
            if key not in segs_cache:
                segs_cache[key] = gf.segments(VIDEO_ROOT, cam, t.date(), ffprobe)
            return segs_cache[key]

    def work(row):
        t = datetime.strptime(row.t_target, FMT)
        t0 = time.perf_counter()
        try:
            g = grab_target(row.camera, t, segs_for(row.camera, t), ffmpeg, vindex)
        except RuntimeError as e:
            return row, None, str(e)[:300], time.perf_counter() - t0
        png = out / "pool" / row.camera / g["image"]
        if not cv2.imwrite(str(png), g["img"]):
            return row, None, "png write failed", time.perf_counter() - t0
        g["png_bytes"] = png.stat().st_size
        return row, g, "", time.perf_counter() - t0

    det = load_yolo()
    emb, dmeta = load_dino()
    lg(f"models: v5 {WEIGHTS} ({WEIGHTS_SHA256[:12]}), DINO {dmeta['variant']} {dmeta['input_size_wh']}")
    meta_path = out / "pool_run.json"
    run_meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    if "identity_check" not in run_meta and len(todo):
        r0 = todo.iloc[0]
        t = datetime.strptime(r0.t_target, FMT)
        g = grab_target(r0.camera, t, segs_for(r0.camera, t), ffmpeg, vindex)
        video, off = gf.locate(t, segs_for(r0.camera, t))
        img2, pts2, _ = gf.grab(ffmpeg, video, off, r0.camera, "exact", "cpu")
        run_meta["identity_check"] = {"camera": r0.camera, "t_target": r0.t_target, "video": video.name, "offset_s": off,
                                      "frame": g["frame"], "pts_ticks": g["pts_ticks"], "grab_frames_pts_time": pts2,
                                      "max_abs_pixel_diff_vs_grab_frames_grab": int(np.abs(g["img"].astype(np.int16) - img2.astype(np.int16)).max())}
        lg(f"identity check vs grab_frames.grab: max pixel diff {run_meta['identity_check']['max_abs_pixel_diff_vs_grab_frames_grab']}")
    n_ok = n_err = 0
    t_gpu = 0.0
    with ThreadPoolExecutor(workers) as ex:
        it = iter(todo.itertuples(index=False))
        pend = set()
        for _ in range(2 * workers):
            r = next(it, None)
            if r is None:
                break
            pend.add(ex.submit(work, r))
        while pend:
            fut = next(as_completed(pend))
            pend.remove(fut)
            r = next(it, None)
            if r is not None:
                pend.add(ex.submit(work, r))
            row, g, err, secs = fut.result()
            if g is None:
                n_err += 1
                with open(fpath, "a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow([row.camera, row.night, row.t_target, "", "", "", "", "", "", "", "", f"{secs:.2f}", 0, err,
                                            row.kind, row.stratum, row.n_out, row.motion])
                lg(f"  {row.camera} {row.t_target}: {err}")
                continue
            tg = time.perf_counter()
            xyxy, conf = det(g["img"])
            e = emb(g["img"])
            t_gpu += time.perf_counter() - tg
            np.save(out / "emb" / f"{Path(g['image']).stem}.npy", e)
            with open(dpath, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                for b, c in zip(xyxy, conf):
                    w.writerow([g["image"], f"{b[0]:.1f}", f"{b[1]:.1f}", f"{b[2]:.1f}", f"{b[3]:.1f}", f"{c:.4f}"])
            with open(fpath, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([row.camera, row.night, row.t_target, g["t_frame"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                                        f"{g['snap_s']:.4f}", g["video"].name, g["frame"], g["pts_ticks"], g["timescale"], g["image"],
                                        g["png_bytes"], f"{secs:.2f}", 1, "", row.kind, row.stratum, row.n_out, row.motion])
            n_ok += 1
            if n_ok % 100 == 0:
                el = time.perf_counter() - t_start
                lg(f"  {n_ok} frames ({n_err} errors), {el / 60:.1f} min, {el / max(n_ok, 1):.2f} s/frame wall, GPU {t_gpu:.0f} s")
    # consolidate
    fr = pd.read_csv(fpath)
    fr = fr.sort_values(["camera", "t_target", "ok"]).drop_duplicates(["camera", "t_target"], keep="last")
    okf = fr[fr["ok"] == 1]
    dd = pd.read_csv(dpath)
    dd = dd[dd["image"].isin(okf["image"])].drop_duplicates()
    dd.to_csv(out / "pool_detections.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    names = okf["image"].tolist()
    feats = np.stack([np.load(out / "emb" / f"{Path(n).stem}.npy") for n in names]) if names else np.zeros((0, 768), np.float32)
    np.savez_compressed(out / "pool_embeddings.npz", images=np.array(names), feats=feats)
    run_meta.update({"plan": PLAN, "driver": DRIVER + " --pool", "git_commit": K.git_commit(REPO),
                     "weights": {"path": WEIGHTS.as_posix(), "sha256": WEIGHTS_SHA256, "imgsz": IMGSZ, "conf_floor": CONF_FLOOR},
                     "dino": dmeta, "video_root": VIDEO_ROOT.as_posix(), "workers": workers,
                     "frames_ok": int(len(okf)), "frames_failed": int((fr["ok"] == 0).sum()),
                     "detections": int(len(dd)), "runtime_last_s": time.perf_counter() - t_start,
                     "versions": versions(), "draw": {"n_strat": POOL_N_STRAT, "n_rand": POOL_N_RAND, "sep_s": POOL_SEP_S,
                                                      "seeds": SEEDS, "strata": STRATA}})
    meta_path.write_text(json.dumps(jsonable(run_meta), indent=1), encoding="utf-8")
    lg(f"pool done: {len(okf)} frames ok, {(fr['ok'] == 0).sum()} failed, {len(dd)} boxes; {time.perf_counter() - t_start:.0f} s")
    logf.close()
    return out


def versions() -> dict:
    v = {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__}
    for mod in ("cv2", "torch", "ultralytics", "scipy", "sklearn"):
        try:
            v[mod] = __import__(mod).__version__
        except Exception:  # noqa: BLE001
            pass
    return v


# ----------------------------------------------------------------------------------------------- selection: inputs
def clip_review_quota() -> dict:
    """Plan B4 rule for the user's clip review: p = share of visible_missed among the reviewed Step-2 episodes (unsure
    excluded): p >= 0.5 -> 60; 0.25 <= p < 0.5 -> 40; p < 0.25 -> 20. No export -> 60. Also the Step-1 fixed-spot
    verdicts."""
    files = sorted(REVIEW_DIR.glob("*.csv"))
    res = {"export": None, "quota": QUOTAS["visible_suspected_miss"], "p_visible_missed": None, "n_reviewed": 0,
           "fixed_spot_objects": [], "rule": "p >= 0.5 -> 60; 0.25 <= p < 0.5 -> 40; p < 0.25 -> 20; no export -> 60"}
    if not files:
        res["note"] = f"no export in {REVIEW_DIR.relative_to(REPO).as_posix()} at selection time -> 60, no fixed-spot negatives"
        return res
    f = max(files, key=lambda p: p.stat().st_mtime)
    d = pd.read_csv(f)
    res["export"] = f.relative_to(REPO).as_posix()
    st2 = d[d["item_id"].astype(str).str.startswith("c") & d["verdict"].notna()]
    if "status" in st2:
        st2 = st2[st2["status"].astype(str) == "saved"]
    rev = st2[st2["verdict"].astype(str) != "unsure"]
    res["n_reviewed"] = int(len(rev))
    if len(rev):
        p = float((rev["verdict"].astype(str) == "visible_missed").mean())
        res["p_visible_missed"] = p
        res["quota"] = 60 if p >= 0.5 else (40 if p >= 0.25 else 20)
    st1 = d[d["item_id"].astype(str).str.startswith("spot_")]
    res["fixed_spot_objects"] = [int(str(i).split("_")[1]) for i, v in zip(st1["item_id"], st1["verdict"]) if str(v) == "object"]
    return res


def kit_table(kit: Path, cam: str, night: str) -> pd.DataFrame | None:
    p = kit / cam / f"{night}.csv.gz"
    return pd.read_csv(p) if p.exists() else None


class Selector:
    """Per-camera selection under the constraints: >= SEP_S apart, <= MAX_PER_NIGHT per night, one frame per event."""

    def __init__(self):
        self.sp = Spacing(SEP_S)
        self.per_night: dict[str, int] = {}
        self.events: set = set()
        self.rows: list[dict] = []
        self.images: set = set()

    def ok(self, r, events=()) -> bool:
        return (r["image"] not in self.images and self.sp.free(r["epoch"]) and self.per_night.get(r["night"], 0) < MAX_PER_NIGHT
                and not (set(events) & self.events))

    def add(self, r, quota: str, reason: str, events=()) -> None:
        self.sp.add(r["epoch"])
        self.per_night[r["night"]] = self.per_night.get(r["night"], 0) + 1
        self.events |= set(events)
        self.images.add(r["image"])
        self.rows.append({**r, "quota": quota, "reason": reason})


def union_find_events(per_frame_nodes: list[list[tuple]]) -> list[set]:
    """Frames' (animal, run) nodes -> per frame the set of merged-event ids (connected components over shared nodes)."""
    parent: dict = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for nodes in per_frame_nodes:
        for a in nodes:
            find(a)
        for a, b in zip(nodes, nodes[1:]):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    return [{find(a) for a in nodes} for nodes in per_frame_nodes]


def visible_runs(vis: np.ndarray, secs: np.ndarray, bridge: float = EVENT_BRIDGE_S) -> np.ndarray:
    """Run id per second of a boolean timeline (seconds secs, sorted) with gaps <= bridge s bridged; -1 where not visible."""
    rid = np.full(len(vis), -1, int)
    k, last = -1, None
    for i in np.flatnonzero(vis):
        if last is None or secs[i] - secs[last] > bridge + 1e-9:
            k += 1
        rid[i] = k
        last = i
    return rid


def frame_scores(pool_fr: pd.DataFrame, dets: pd.DataFrame, kit: Path, rain: dict, validated: dict, log=print) -> pd.DataFrame:
    """Per pool frame (one camera-night at a time): v5 counts, the kit rows at t_pc, WISER paddock positions (same code as
    the kit), robust hidden (mask +- 7 in), suspected misses, social, hard negative, and the merged-event nodes."""
    import wiser_assist_p0 as wp
    m, _, _ = K.load_map()
    houses = wp.load_houses()
    handling = K.load_handling()
    C = K.fc.Corrections(COHORT)
    masks = {c: dict(np.load(kit / c / "visibility_mask.npz")) for c in CAMS}
    d25 = dets[dets["conf"] >= PRELABEL_CONF]
    nb = d25.groupby("image").size()
    mx = dets.groupby("image")["conf"].max()
    out = []
    for night in NIGHTS:
        ns = str(night)
        sub_n = pool_fr[pool_fr["night"] == ns]
        if not len(sub_n):
            continue
        nf = K.load_night_fixes(night, handling=handling)
        ks, _ = K.kit_seconds(night, handling)
        st_all = K.wiser_state(nf, ks, m, houses)
        for cam in CAMS:
            sub = sub_n[sub_n["camera"] == cam].copy()
            if not len(sub):
                continue
            kt = kit_table(kit, cam, ns)
            if kt is None:
                raise SystemExit(f"kit has no table {cam}/{ns}")
            kt = kt.set_index(["t_pc", "animal"])
            val = bool(validated.get((cam, ns), False))
            # per-second visible timeline (tracked, outside the house zones, in support, robustly unhidden) for the events
            t_str = pd.to_datetime(np.datetime64(K.night_start(night)) + (ks * 1e9).astype("timedelta64[ns]")).strftime(FMT)
            ins = kt["in_support"].unstack("animal").reindex(index=t_str, columns=list(K.ANIMALS)).fillna(0).to_numpy(bool)
            rob = K.robust_hidden(masks[cam], st_all["P"])
            vis_t = st_all["ok"] & ~st_all["house"] & ins & (np.nan_to_num(rob, nan=1.0) == 0)
            runs = np.stack([visible_runs(vis_t[:, j], ks) for j in range(len(K.ANIMALS))], 1)
            sec_index = pd.Series(np.arange(len(ks)), index=t_str)
            for r in sub.itertuples():
                tpc = r.t_target
                k = sec_index.get(tpc)
                rows = kt.loc[tpc] if (tpc, "SF07") in kt.index else None
                rec = {"image": r.image, "camera": cam, "video": r.video, "frame": int(r.frame), "t_pc": tpc, "night": ns,
                       "t_frame": r.t_frame, "epoch": float(pd.Timestamp(tpc).value // 10**9), "kind": r.kind,
                       "stratum": r.stratum, "hour": pd.Timestamp(tpc).hour, "n_boxes_v5": int(nb.get(r.image, 0)),
                       "max_conf_v5": float(mx.get(r.image, 0.0)), "map_validated": int(val), "rain": bool(rain.get(ns, 0) >= RAIN_MM)}
                if rows is None or k is None:
                    rec.update({"all_tracked": "", "n_wiser_in_view": "", "n_visible_suspected_miss": "", "social": "",
                                "hard_negative": False, "miss_animals": "", "event_nodes": [], "kit_row": False})
                    out.append(rec)
                    continue
                rows = rows.reindex(list(K.ANIMALS))
                tracked = rows["tracked"].to_numpy(bool)
                inh = rows["in_house"].to_numpy(bool)
                insup = rows["in_support"].to_numpy(bool)
                Pj = st_all["P"][k]
                rec["all_tracked"] = int(rows["all_tracked"].iloc[0])
                rec["hard_negative"] = bool(val and rec["all_tracked"] == 1 and inh.all())
                in_view = tracked & insup & ~inh
                if val:
                    rec["n_wiser_in_view"] = int(in_view.sum())
                    soc = False
                    vj = np.flatnonzero(in_view)
                    for a in range(len(vj)):
                        for b in range(a + 1, len(vj)):
                            if np.hypot(*(Pj[vj[a]] - Pj[vj[b]])) <= SOCIAL_R_IN:
                                soc = True
                    rec["social"] = int(soc)
                else:
                    rec["n_wiser_in_view"] = rec["social"] = ""
                if val and not rec["rain"]:
                    g = d25[d25["image"] == r.image]
                    cen = np.c_[(g["x1"] + g["x2"]) / 2, (g["y1"] + g["y2"]) / 2] if len(g) else np.zeros((0, 2))
                    bp = np.full((len(cen), 2), np.nan)
                    if len(cen):
                        q, _ = C.to_paddock(cam, parse_t(r.t_frame), cen, z_mm=K.Z_MM, units="in")
                        if q is not None:
                            bp = np.asarray(q, float).reshape(-1, 2)
                    uv = rows[["u", "v"]].to_numpy(float)
                    rp = rows["r_px"].to_numpy(float)
                    miss = []
                    for j in np.flatnonzero(vis_t[k]):
                        near = False
                        if len(cen):
                            dpad = np.hypot(bp[:, 0] - Pj[j, 0], bp[:, 1] - Pj[j, 1])
                            dpix = np.hypot(cen[:, 0] - uv[j, 0], cen[:, 1] - uv[j, 1])
                            near = bool(np.any(np.where(np.isfinite(dpad), dpad <= MISS_R_IN, dpix <= MISS_R_IN / K.RING_IN * rp[j])))
                        if not near:
                            miss.append(j)
                    rec["n_visible_suspected_miss"] = len(miss)
                    rec["miss_animals"] = ",".join(K.ANIMALS[j] for j in miss)
                    rec["event_nodes"] = [f"{cam}:{ns}:{K.ANIMALS[j]}:run{int(runs[k, j])}" for j in miss]
                else:
                    rec["n_visible_suspected_miss"] = ""
                    rec["miss_animals"] = ""
                    rec["event_nodes"] = []
                rec["kit_row"] = True
                out.append(rec)
        log(f"scores {ns}: {len(sub_n)} frames")
    sc = pd.DataFrame(out)
    ev = union_find_events(sc["event_nodes"].tolist())
    sc["events"] = [sorted(map(str, e)) for e in ev]
    return sc


def kmeans_clusters(X: np.ndarray, k: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(X)
    return km.labels_, km.cluster_centers_


def select_camera(sc: pd.DataFrame, X: np.ndarray, quotas: dict, seed: int, fixed_neg: set, log=print) -> tuple[list[dict], dict]:
    """Fill the quotas in QUOTA_ORDER for one camera; shortfalls of misses / social / hard negatives go to the strata."""
    rng = random.Random(seed)
    S = Selector()
    recs = sc.to_dict("records")
    fill = {}
    # 1 visible suspected miss
    cand = [r for r in recs if r["n_visible_suspected_miss"] not in ("", None) and int(r["n_visible_suspected_miss"]) > 0]
    rng.shuffle(cand)
    q = quotas["visible_suspected_miss"]
    n = 0
    for r in cand:
        if n >= q:
            break
        if S.ok(r, r["events"]):
            S.add(r, "visible_suspected_miss", f"misses {r['miss_animals']}; events {';'.join(r['events'])}", r["events"])
            n += 1
    fill["visible_suspected_miss"] = (n, q, len(cand))
    # 2 social
    cand = [r for r in recs if r["social"] not in ("", None) and int(r["social"]) == 1]
    rng.shuffle(cand)
    q, n = quotas["social"], 0
    for r in cand:
        if n >= q:
            break
        if S.ok(r):
            S.add(r, "social", f"{r['n_wiser_in_view']} tagged animals in view, >= 2 within {SOCIAL_R_IN:.0f} in", ())
            n += 1
    fill["social"] = (n, q, len(cand))
    # 3 hard negative: v5 fires (highest max conf first) although WISER puts every animal in a house; + fixed spots
    cand = [r for r in recs if r["hard_negative"] or r["image"] in fixed_neg]
    cand.sort(key=lambda r: (-float(r["max_conf_v5"]), rng.random()))
    q, n = quotas["hard_negative"], 0
    for r in cand:
        if n >= q:
            break
        if S.ok(r):
            why = "all six tracked, all in house zones" if r["hard_negative"] else "box at a fixed spot verdicted object"
            S.add(r, "hard_negative", f"{why}; v5 max conf {float(r['max_conf_v5']):.2f}", ())
            n += 1
    fill["hard_negative"] = (n, q, len(cand))
    # 4 WISER strata (+ shortfalls)
    short = sum(max(0, quotas[k] - fill[k][0]) for k in ("visible_suspected_miss", "social", "hard_negative"))
    q = quotas["wiser_strata"] + short
    by_s = {s: [r for r in recs if r["stratum"] == s] for s in STRATA}
    for s in STRATA:
        rng.shuffle(by_s[s])
    cellcount: dict = {}
    for r in S.rows:
        cellcount[(r["night"], r["hour"])] = cellcount.get((r["night"], r["hour"]), 0) + 1
    n = 0
    live = [s for s in STRATA if by_s[s]]
    while n < q and live:
        for s in list(live):
            if n >= q:
                break
            cs = [r for r in by_s[s] if S.ok(r)]
            if not cs:
                live.remove(s)
                continue
            best = min(cs, key=lambda r: cellcount.get((r["night"], r["hour"]), 0))
            S.add(best, "wiser_strata", f"stratum {s} (outside-count | motion), night {best['night']}, hour {best['hour']:02d}", ())
            cellcount[(best["night"], best["hour"])] = cellcount.get((best["night"], best["hour"]), 0) + 1
            by_s[s].remove(best)
            n += 1
    fill["wiser_strata"] = (n, q, sum(len(v) for v in by_s.values()) + n)
    # 5 DINOv3 diversity: k-means on the camera's pool, the nearest eligible unselected frame to each centroid
    lab, cen = kmeans_clusters(X, K_CLUSTERS, seed=0)
    sc_cluster = dict(zip([r["image"] for r in recs], lab))
    q, n = quotas["dino_diversity"], 0
    for ci in range(K_CLUSTERS):
        if n >= q:
            break
        dist = np.linalg.norm(X - cen[ci], axis=1)
        for i in np.argsort(dist):
            r = recs[i]
            if S.ok(r):
                S.add(r, "dino_diversity", f"nearest to k-means centroid {ci} (k = {K_CLUSTERS})", ())
                n += 1
                break
    fill["dino_diversity"] = (n, q, len(recs))
    # 6 uniform random
    cand = list(recs)
    rng.shuffle(cand)
    q, n = quotas["uniform_random"], 0
    for r in cand:
        if n >= q:
            break
        if S.ok(r):
            S.add(r, "uniform_random", "uniform random from the pool", ())
            n += 1
    fill["uniform_random"] = (n, q, len(recs))
    for r in S.rows:
        r["cluster_id"] = int(sc_cluster[r["image"]])
    return S.rows, {"fill": fill, "cluster_of": sc_cluster, "cluster_sizes": np.bincount(lab, minlength=K_CLUSTERS).tolist()}


# ----------------------------------------------------------------------------------------------- test extension
def test_extension(log=print) -> tuple[pd.DataFrame, dict]:
    """select_pano_targets' stratified test rule on night 09-05: +30 per camera (zero / few / many = 0.2 / 0.4 / 0.4,
    nights round-robin = the one night), >= 5 min from each other and from that camera's 20 existing test frames."""
    import select_pano_targets as spt
    bins = pd.read_pickle(spt.DEFAULT_BINS)
    rois = json.loads(Path(K.ROIS).read_text(encoding="utf-8"))
    handling, popchange, _, _ = spt.load_handling(K.HANDLING)
    tab = spt.bin_table(bins, rois)
    cand = spt.candidates(tab, handling, popchange)
    test_c = cand[cand["night"] == TEST_NIGHT]
    prior = pd.read_csv(PRIOR_TEST_TARGETS)
    untracked = spt.make_untracked(popchange)
    rows, meta = [], {"bins_sha256": sha256(Path(spt.DEFAULT_BINS)), "prior_targets": PRIOR_TEST_TARGETS.as_posix()}
    for k, cam in enumerate(CAMS):
        pt = pd.to_datetime(prior.loc[prior["camera"] == cam, "time"]) - pd.Timedelta(seconds=2.5)
        idx = list(test_c.index[test_c["local"].isin(pt)])
        missing = len(pt) - len(idx)
        rng = random.Random(TEST_SEED_BASE + k)
        picks = spt.draw(test_c, TEST_PER_CAM, TEST_MIX, rng, TEST_SEP_S, taken=idx)
        n_first = len(picks)
        short = TEST_PER_CAM - len(picks)
        if short > 0:
            # amendment 4 (after the first package build): draw() does not refill a stratum short of spaced bins (09-05
            # has 27 min of 'zero'); the shortfall is drawn from the strata that still have candidates, mix renormalised,
            # same spacing, same rng stream
            got = test_c.loc[picks, "stratum"].value_counts()
            room = {s: TEST_MIX[s] for s in spt.STRATA if got.get(s, 0) >= round(TEST_PER_CAM * TEST_MIX[s])}
            tot = sum(room.values())
            mix2 = {s: (room.get(s, 0.0) / tot if tot else 0.0) for s in spt.STRATA}
            picks += spt.draw(test_c, short, mix2, rng, TEST_SEP_S, taken=idx + picks)
        rows += spt.to_rows(test_c, picks, cam, "test_ext", untracked)
        meta[cam] = {"prior_matched_bins": len(idx), "prior_missing": int(missing), "drawn": len(picks),
                     "drawn_by_the_rule": n_first, "refilled_amendment_4": len(picks) - n_first,
                     "strata": test_c.loc[picks, "stratum"].value_counts().to_dict(), "seed": TEST_SEED_BASE + k}
        log(f"test extension {cam}: {len(picks)} drawn (prior bins matched {len(idx)} / {len(pt)})")
    return pd.DataFrame(rows), meta


def frame_of_prior(row, vindex: VideoIndex, root: Path = VIDEO_ROOT) -> int | str:
    """The existing test frames' sample index from their grab manifest (exact seek: the first sample >= the offset),
    cross-checked against the 6-significant-digit frame_pts_s; '' if inconsistent."""
    mm = gf.NAME.match(str(row["video"]))
    video = root / mm["d"] / row["camera"] / row["video"] if mm else Path("")
    if not mm or not video.exists():
        return ""
    ticks, tsc = vindex.get(video)
    off = round(float(row["target_offset_s"]), 3)
    i = int(np.searchsorted(ticks, int(np.ceil(off * tsc - 1e-6))))
    if i >= len(ticks) or abs(ticks[i] / tsc - float(row["frame_pts_s"])) > 0.01:
        return ""
    return i


# ----------------------------------------------------------------------------------------------- package
def yolo_txt(boxes: pd.DataFrame, W: int = 7680, H: int = 2160) -> str:
    lines = []
    for b in boxes.itertuples():
        x1, y1 = max(0.0, float(b.x1)), max(0.0, float(b.y1))
        x2, y2 = min(float(W), float(b.x2)), min(float(H), float(b.y2))
        if x2 <= x1 or y2 <= y1:
            continue
        lines.append(f"0 {(x1 + x2) / 2 / W:.6f} {(y1 + y2) / 2 / H:.6f} {(x2 - x1) / W:.6f} {(y2 - y1) / H:.6f}")
    return "\n".join(lines) + ("\n" if lines else "")


def write_prelabels(split_dir: Path, stem: str, txt: str) -> bool:
    """Coordinator's format correction (2026-10-06, plan amendment 2): the editable images/<stem>.txt is written ONLY when
    v5 has >= 1 box at conf >= 0.25 (the undergrad's check_labels.py counts a frame with a txt as reviewed, and
    finalize_negatives.py writes the empties after the human pass); prelabels_v5/<stem>.txt is always written (empty when
    v5 found nothing) as the pristine provenance record. -> whether the editable txt was written."""
    (split_dir / "prelabels_v5" / f"{stem}.txt").write_text(txt, encoding="utf-8")
    if txt.strip():
        (split_dir / "images" / f"{stem}.txt").write_text(txt, encoding="utf-8")
        return True
    return False


def sidecar(r: dict, kt: pd.DataFrame, occ: list[dict]) -> dict:
    animals = []
    if int(r["map_validated"]) == 1:
        rows = kt.loc[r["t_pc"]].reindex(list(K.ANIMALS))
        for a, x in rows.iterrows():
            f = lambda v: None if (v is None or (isinstance(v, float) and not np.isfinite(v))) else round(float(v), 1)  # noqa: E731
            animals.append({"id": a, "u": f(x["u"]), "v": f(x["v"]), "r_px": f(x["r_px"]), "in_house": bool(x["in_house"]),
                            "hidden_share": None if not np.isfinite(x["hidden_share"]) else round(float(x["hidden_share"]), 3),
                            "in_support": bool(x["in_support"]), "tracked": bool(x["tracked"]), "motion": str(x["motion"])})
    return {"schema": "wiser_sidecar/1", "camera": r["camera"], "video": r["video"], "frame": int(r["frame"]), "t_pc": r["t_pc"],
            "night": r["night"], "frame_size": [7680, 2160], "map_validated": bool(int(r["map_validated"])),
            "all_tracked": bool(int(r["all_tracked"])) if r["all_tracked"] not in ("", None) else False,
            "animals": animals, "occluders": [{"name": o["name"], "kind": o["kind"], "polygon": o["polygon"]} for o in occ],
            "note": SIDECAR_NOTE}


VERIFY_PY = r'''"""verify_manifest.py - check a copied label package against MANIFEST_sha256.csv (stdlib only).
Usage: python verify_manifest.py [<package folder>]   (default: the folder this file is in)"""
import csv, hashlib, sys
from pathlib import Path
root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
bad = missing = 0
rows = list(csv.DictReader(open(root / "MANIFEST_sha256.csv", encoding="utf-8")))
for r in rows:
    p = root / r["path"]
    if not p.exists():
        missing += 1; print("MISSING", r["path"]); continue
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    if h.hexdigest() != r["sha256"] or p.stat().st_size != int(r["bytes"]):
        bad += 1; print("MISMATCH", r["path"])
extra = [p for p in root.rglob("*") if p.is_file() and p.name not in ("MANIFEST_sha256.csv",)
         and p.relative_to(root).as_posix() not in {r["path"] for r in rows}]
for p in extra:
    print("EXTRA", p.relative_to(root).as_posix())
print(f"{len(rows)} files listed, {missing} missing, {bad} mismatched, {len(extra)} extra -> {'OK' if not (bad or missing or extra) else 'FAIL'}")
sys.exit(1 if (bad or missing or extra) else 0)
'''


def write_manifest_sha(root: Path) -> int:
    rows = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != "MANIFEST_sha256.csv":
            rows.append({"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p)})
    pd.DataFrame(rows).to_csv(root / "MANIFEST_sha256.csv", index=False)
    return len(rows)


def package_readme(pkg: Path, kit: Path, n_train: int, n_test: int, n_test_new: int, n_overlap: int, quota_note: str) -> str:
    return "\n".join([
        "# Round-1 labelling package — cohort-3 CH01 / CH02 panoramas (rat detector)", "",
        f"Made by `{DRIVER} --select` (analysis repo, plan `{PLAN}`, part B). Frames are upright 7680 × 2160 panorama "
        "frames of field-PC night times (21:00 → 04:20), named `<video stem>_f<frame index>.png` (frame index = 0-based "
        "sample index in the hourly video). The WISER pixel kit used for the hints: "
        f"`{kit.as_posix()}` (copy it next to this package).", "",
        "## Contents", "",
        f"- `train/images/` — {n_train} frames (200 per camera) + an editable `<stem>.txt` (YOLO format, class 0 = rat, "
        "normalised cx cy w h) next to each frame where YOLO v5 (`rat_m_v5`) found ≥ 1 box with conf ≥ 0.25. **Frames with "
        "no `.txt` are the ones the model found nothing in: they must be opened and saved with `s` even if they stay "
        "empty.** A frame is reviewed only when its `<stem>.prov.json` exists, i.e. once you have saved it with "
        "`label_frames.py --wiser` (a frame that arrives with prelabel boxes has a `.txt` before anyone has looked at it). "
        "Run `finalize_negatives` only after `progress.py <package>` reports \"train READY\" (0 never-saved frames). "
        "**The boxes are machine proposals: keep, move, delete or add boxes — every box that stays is your decision.**",
        "- `train/prelabels_v5/` — the pristine v5 prelabel of every frame (an empty file where v5 found nothing; provenance; "
        "never edit).",
        "- `train/wiser/<stem>.json` — the WISER sidecar (schema `wiser_sidecar/1`): the tagged animals' pixel positions with "
        "a 14-in radius, house-zone flag, hidden share, in-support flag, motion, and the occluder outlines (poles, houses). "
        "When `map_validated` is false the animals list is empty (no WISER circles on that camera-night).",
        "- `train/manifest.csv` — one row per frame: camera, video, frame, t_pc, night, split, quota, reason, v5 counts, WISER "
        "counts, cluster, overlap.",
        f"- `test/images/` — {n_test} frames of the frozen test night 09-05 ({n_test - n_test_new} existing `.jpg` copied "
        f"unchanged from the first test set + {n_test_new} new `.png`), **no txt, no sidecar** + `test/manifest.csv`.",
        f"- `overlap/` — {n_overlap} of the training frames (10 per camera, random, seed 0; `overlap = 1` in the train "
        "manifest) copied with their prelabel txt and sidecars, so a second labeller can label them independently "
        "(inter-labeller agreement).",
        "- `MANIFEST_sha256.csv` (path, bytes, sha256 of every file) and `verify_manifest.py`.", "",
        "## Copy to Q: and verify (the user; the agent never writes Q:)", "",
        "1. Copy the whole folder, e.g. with robocopy: `robocopy <this folder> Q:\\hc997\\SocialFieldRat2026\\3rd_rat\\"
        "labelling\\<this folder name> /E /COPY:DAT /R:2 /W:5` (and the kit folder next to it).",
        "2. Verify the copy: `python Q:\\...\\<this folder name>\\verify_manifest.py` → it prints `OK` when every file listed in "
        "`MANIFEST_sha256.csv` is present with the same size and sha256 and nothing extra is there.", "",
        "## Labelling rules", "",
        "1. **Blind first.** Look at the frame and box every rat you can see BEFORE you show the WISER overlay. Only then "
        "turn the overlay on to look for animals you may have missed (in `label_frames.py --wiser`: `d` = scan done, then "
        "`w` toggles the WISER circles and the occluder outlines).",
        "2. **Only visible animals get a box.** An animal hidden behind a pole, a house or grass gets no box, even if WISER "
        "says it is there (\"hidden — do not box\"). Box the visible part of a partly hidden animal if you can tell it is a rat.",
        "3. **An empty frame is your verdict.** WISER never proves a frame is empty (untagged or untracked animals are not "
        "shown; WISER can be several inches off), and neither does the model. Open every frame and save it with `s` (no "
        "box only when you see no rat); a frame counts as reviewed only when its `<stem>.prov.json` exists.",
        "4. The YOLO prelabels and the WISER circles are proposals. Delete wrong boxes, fix loose ones, add missed ones.",
        "5. The **test** frames are labelled blind: no prelabels, no overlay, never used for training or for choosing frames.",
        "6. Night frames are infrared (monochrome): identity is not visible; do not try to name animals unless a tag id is "
        "asked for by the tool.", "",
        "## How the frames were chosen", "",
        "Per camera from a pool of ~1 500 night times (1 200 stratified by WISER — tagged animals outside the houses 0 / 1–2 "
        "/ ≥ 3 × motion × night × hour — + 300 uniform; ≥ 10 s apart): visible suspected misses (a tracked animal in plain "
        "view without a YOLO box within 20 in), WISER strata, social (≥ 2 animals within 20 in), hard negatives (v5 fires "
        "while WISER puts all six animals in the houses), DINOv3 diversity, uniform random. " + quota_note +
        " Details and numbers: `results/2026c/cv_field/reports/" + REPORT_NAME + "` in the analysis repo.", ""])


# ----------------------------------------------------------------------------------------------- select run
def run_select(pool: Path, kit: Path, out: Path | None, log=print) -> Path:
    t_start = time.perf_counter()
    started = datetime.now().isoformat(timespec="seconds")
    if out is None:
        import output_paths as op
        out = op.run_dir("label_round1", COHORT, make_figures=False)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if any(True for _ in out.iterdir()):
        raise SystemExit(f"{out} is not empty - never overwritten")
    aux = out.parent / f"{out.name}_selection"                  # selection records next to (not inside) the package
    aux.mkdir(exist_ok=True)
    logf = open(aux / "select_log.txt", "w", encoding="utf-8")

    def lg(msg):
        log(msg)
        logf.write(f"{datetime.now():%H:%M:%S} {msg}\n")
        logf.flush()

    kitj = json.loads((kit / "kit.json").read_text(encoding="utf-8"))
    val = pd.DataFrame(kitj["validation_table"])
    validated = {(r.camera, r.night): bool(r.map_validated) for r in val.itertuples()}
    rain = {r.night: float(r.rain_mm_night) if r.rain_mm_night is not None and np.isfinite(r.rain_mm_night) else 0.0
            for r in val.itertuples()}
    rule = clip_review_quota()
    quotas = dict(QUOTAS)
    quotas["wiser_strata"] += QUOTAS["visible_suspected_miss"] - rule["quota"]
    quotas["visible_suspected_miss"] = rule["quota"]
    lg(f"clip-review rule: {rule}")
    pool_all = pd.read_csv(pool / "pool_frames.csv")
    pool_fr = K.usable_pool_frames(pool_all)
    lg(f"pool: {int((pool_all['ok'] == 1).sum())} frames grabbed, {len(pool_fr)} usable (frame <= {K.MAX_SNAP_S} s after "
       f"its target second, one row per image; amendment 3)")
    if (pool_fr["night"] == str(TEST_NIGHT)).any():
        raise SystemExit("the pool holds a test-night frame - refusing")
    dets = pd.read_csv(pool / "pool_detections.csv.gz")
    embz = np.load(pool / "pool_embeddings.npz")
    emb_of = dict(zip(embz["images"].tolist(), embz["feats"]))
    sc = frame_scores(pool_fr, dets, kit, rain, validated, lg)
    sc.drop(columns=["event_nodes"]).to_csv(aux / "pool_scores.csv.gz", index=False)
    fixed_neg = set()                                              # fixed spots verdicted "object" (none without an export)
    if rule["fixed_spot_objects"]:
        fixed_neg = fixed_spot_frames(rule["fixed_spot_objects"], sc, dets, lg)
    import field_embed as fe
    sel_rows, sel_meta = [], {}
    for cam in CAMS:
        s = sc[sc["camera"] == cam].reset_index(drop=True)
        Xr = np.stack([emb_of[i] for i in s["image"]])
        X, info = fe.embed_matrix(Xr, pca_dim=50)
        rows, meta = select_camera(s, X, quotas, SEEDS[cam], fixed_neg, lg)
        sel_rows += rows
        sel_meta[cam] = meta
        lg(f"{cam}: selected {len(rows)}; fill " + "; ".join(f"{k} {v[0]}/{v[1]} (cand {v[2]})" for k, v in meta["fill"].items()))
    sel = pd.DataFrame(sel_rows)
    # overlap: 10 per camera at random (seed 0)
    rng = random.Random(OVERLAP_SEED)
    sel["overlap"] = 0
    for cam in CAMS:
        idx = sorted(sel.index[sel["camera"] == cam])
        for i in rng.sample(idx, N_OVERLAP_PER_CAM):
            sel.loc[i, "overlap"] = 1
    sel["split"] = "train"
    sel = sel.sort_values(["camera", "t_pc"]).reset_index(drop=True)
    # ---- package: train
    tr = out / "train"
    for sub in ("images", "prelabels_v5", "wiser"):
        (tr / sub).mkdir(parents=True, exist_ok=True)
    d25 = dets[dets["conf"] >= PRELABEL_CONF]
    occ_cache, kt_cache = {}, {}
    for r in sel.to_dict("records"):
        stem = Path(r["image"]).stem
        shutil.copy2(pool / "pool" / r["camera"] / r["image"], tr / "images" / r["image"])
        txt = yolo_txt(d25[d25["image"] == r["image"]])
        write_prelabels(tr, stem, txt)
        key = (r["camera"], r["night"])
        if key not in kt_cache:
            kt_cache[key] = kit_table(kit, r["camera"], r["night"]).set_index(["t_pc", "animal"])
            occ_cache[key] = json.loads((kit / r["camera"] / "occluders.json").read_text(encoding="utf-8"))["by_night"][r["night"]]["occluders"]
        sc_ = sidecar(r, kt_cache[key], occ_cache[key])
        (tr / "wiser" / f"{stem}.json").write_text(json.dumps(sc_, indent=1), encoding="utf-8")
    man = sel.copy()
    man["max_conf_v5"] = man["max_conf_v5"].astype(float).round(4)
    for c in MANIFEST_COLS:
        if c not in man:
            man[c] = ""
    man[MANIFEST_COLS].to_csv(tr / "manifest.csv", index=False)
    lg(f"train: {len(sel)} frames written")
    # ---- overlap
    ov = out / "overlap"
    for sub in ("images", "prelabels_v5", "wiser"):
        (ov / sub).mkdir(parents=True, exist_ok=True)
    for r in sel[sel["overlap"] == 1].to_dict("records"):
        stem = Path(r["image"]).stem
        shutil.copy2(tr / "images" / r["image"], ov / "images" / r["image"])
        if (tr / "images" / f"{stem}.txt").exists():                 # no editable txt where v5 found nothing
            shutil.copy2(tr / "images" / f"{stem}.txt", ov / "images" / f"{stem}.txt")
        shutil.copy2(tr / "prelabels_v5" / f"{stem}.txt", ov / "prelabels_v5" / f"{stem}.txt")
        shutil.copy2(tr / "wiser" / f"{stem}.json", ov / "wiser" / f"{stem}.json")
    man[man["overlap"] == 1][MANIFEST_COLS].to_csv(ov / "manifest.csv", index=False)
    # ---- test
    te = out / "test" / "images"
    te.mkdir(parents=True, exist_ok=True)
    vindex = VideoIndex(pool / "video_index_test")
    prior_man = pd.read_csv(TEST_DIR / "manifest.csv")
    trows = []
    for r in prior_man.to_dict("records"):
        src = TEST_DIR / r["out"]
        shutil.copy2(src, te / r["out"])
        if sha256(src) != sha256(te / r["out"]):
            raise SystemExit(f"copy of {src} differs")
        ft = pd.Timestamp(r["frame_time"])
        trows.append({"image": r["out"], "camera": r["camera"], "video": str(r["video"]), "frame": frame_of_prior(r, vindex),
                      "t_pc": ft.floor("s").strftime(FMT), "night": str(TEST_NIGHT), "split": "test", "quota": "test_existing",
                      "reason": str(r["tag"]), "overlap": 0})
    ext, ext_meta = test_extension(lg)
    ffmpeg, ffprobe = gf.find_ffmpeg()
    n_new = 0
    for r in ext.to_dict("records"):
        t = datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S.%f")
        segs = gf.segments(VIDEO_ROOT, r["camera"], t.date(), ffprobe)
        try:
            g = grab_target(r["camera"], t, segs, ffmpeg, vindex)
        except RuntimeError as e:
            lg(f"  test {r['camera']} {r['time']}: {e}")
            continue
        import cv2
        cv2.imwrite(str(te / g["image"]), g["img"])                # no model, no WISER: image only
        trows.append({"image": g["image"], "camera": r["camera"], "video": g["video"].name, "frame": g["frame"],
                      "t_pc": g["t_frame"].strftime(FMT), "night": str(TEST_NIGHT), "split": "test", "quota": "test_extension",
                      "reason": r["tag"], "overlap": 0, "target_time": r["time"]})
        n_new += 1
    tm = pd.DataFrame(trows)
    for c in MANIFEST_COLS:
        if c not in tm:
            tm[c] = ""
    (out / "test").mkdir(exist_ok=True)
    tm[MANIFEST_COLS].to_csv(out / "test" / "manifest.csv", index=False)
    lg(f"test: {len(tm)} frames ({len(prior_man)} existing + {n_new} new)")
    # ---- check separation of the extension (>= 5 min from each other and the camera's existing frames)
    sep_chk = {}
    for cam in CAMS:
        tt = np.sort(epoch_s(tm.loc[tm["camera"] == cam, "t_pc"]))
        sep_chk[cam] = float(np.diff(tt).min()) if len(tt) > 1 else float("nan")
    quota_note = (f"Suspected-miss quota {rule['quota']} ({rule.get('note') or 'clip review p = ' + str(rule['p_visible_missed'])}).")
    (out / "verify_manifest.py").write_text(VERIFY_PY, encoding="utf-8")
    (out / "README.md").write_text(package_readme(out, kit, len(sel), len(tm), n_new, int(sel["overlap"].sum()), quota_note),
                                   encoding="utf-8")
    n_files = write_manifest_sha(out)
    lg(f"package: {n_files} files listed in MANIFEST_sha256.csv")
    res = {"started": started, "runtime_s": time.perf_counter() - t_start, "pool": pool.as_posix(), "kit": kit.as_posix(),
           "package": out.as_posix(), "rule": rule, "quotas": quotas, "fill": {c: sel_meta[c]["fill"] for c in CAMS},
           "cluster_sizes": {c: sel_meta[c]["cluster_sizes"] for c in CAMS}, "test_ext": ext_meta, "test_min_sep_s": sep_chk,
           "n_train": int(len(sel)), "n_test": int(len(tm)), "n_test_new": n_new, "n_overlap": int(sel["overlap"].sum()),
           "n_files": n_files, "selection_records": aux.as_posix(),
           "n_editable_txt": int(sum(1 for _ in (tr / "images").glob("*.txt")))}
    sel.drop(columns=["events"], errors="ignore").to_csv(aux / "selected.csv", index=False)
    (aux / "select_run.json").write_text(json.dumps(jsonable(res), indent=1), encoding="utf-8")
    rp = write_report(res, sel, tm, sc, val, pool, kit, out, kitj)
    lg(f"report -> {rp}")
    logf.close()
    return out


def fixed_spot_frames(spots: list[int], sc: pd.DataFrame, dets: pd.DataFrame, log=print) -> set:
    """CH01 pool frames with a v5 box (>= 0.25) within 40 px of a fixed spot the user verdicted 'object' (the spot's 09-06
    pano centre carried to the frame's night through the 09-18 frame)."""
    C = K.fc.Corrections(COHORT)
    fs = pd.read_csv(FIXED_SPOTS)
    t06 = datetime(2026, 9, 6, 21, 30)
    out = set()
    d25 = dets[dets["conf"] >= PRELABEL_CONF]
    for sid in spots:
        r = fs[fs["spot_id"] == sid].iloc[0]
        p18, _ = C.to_09_18("CH01", t06, np.array([[r.cx_median, r.cy_median]], float))
        for f in sc[sc["camera"] == "CH01"].itertuples():
            B, _ = C.correction("CH01", datetime.strptime(f.t_pc, FMT))
            if B is None:
                continue
            uv = K.apply_affine(K.fc.invert(B), p18)[0]
            g = d25[d25["image"] == f.image]
            if len(g) and np.any(np.hypot((g["x1"] + g["x2"]) / 2 - uv[0], (g["y1"] + g["y2"]) / 2 - uv[1]) <= 40):
                out.add(f.image)
    log(f"fixed-spot object frames: {len(out)}")
    return out


# ----------------------------------------------------------------------------------------------- report
def pool_wall_min(pool: Path) -> float:
    """Wall time of the pool (first to last time stamp of pool_log.txt, same evening), minutes."""
    ts = []
    try:
        for line in (pool / "pool_log.txt").read_text(encoding="utf-8").splitlines():
            m = re.match(r"^(\d{2}):(\d{2}):(\d{2}) ", line)
            if m:
                ts.append(int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]))
    except OSError:
        return float("nan")
    return (ts[-1] - ts[0]) / 60 if len(ts) > 1 else float("nan")


def write_report(res: dict, sel: pd.DataFrame, tm: pd.DataFrame, sc: pd.DataFrame, val: pd.DataFrame, pool: Path, kit: Path,
                 pkg: Path, kitj: dict) -> Path:
    import output_paths as op
    rep = op.report_dir(COHORT, DIRECTION)
    prj = json.loads((pool / "pool_run.json").read_text(encoding="utf-8"))
    pst = json.loads((pool / "pool_draw_stats.json").read_text(encoding="utf-8"))
    pf = pd.read_csv(pool / "pool_frames.csv")
    pfo = pf[pf["ok"] == 1]
    dets = pd.read_csv(pool / "pool_detections.csv.gz")
    f2 = lambda v, nd=2: "–" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{nd}f}"  # noqa: E731
    rule = res["rule"]
    L = ["# WISER-guided labelling loop, round 1 — WISER pixel kit + 400-frame package + test set to 100 (2026c, CH01/CH02)", "",
         f"Drivers `cv/cv_field/build_wiser_pixel_kit.py` (part A) and `{DRIVER}` (part B); plan `{PLAN}` (pre-registered, "
         "approved 2026-10-06 \"做吧\"; amendments 1–3 before results: implementation details + the 5-min test spacing, the "
         "coordinator's prelabel-txt rule, pool frames ≤ 0.5 s from their target second; amendment 4 after the first package "
         "build: the test-extension refill). Generated "
         f"{datetime.now():%Y-%m-%d %H:%M}; code `{K.git_commit(REPO)}`. The agent did not look at any frame, video or figure; "
         "YOLO boxes and WISER positions are proposals, never labels. Part C (the loop in the undergrad's repo) is built "
         "separately.", "",
         "## Outputs", "",
         f"- **Label package** `{pkg.as_posix()}`: {res['n_train']} training frames (200 per camera) with editable v5 "
         f"prelabels ({res.get('n_editable_txt', '?')} frames; no `.txt` where v5 found no box ≥ 0.25 — amendment 2: those "
         "frames must be opened and saved with `s` even if they stay empty; a frame is reviewed only when its "
         "`<stem>.prov.json` exists (saved with `label_frames.py --wiser`); `finalize_negatives` only after `progress.py "
         "<pkg>` reports \"train READY\"), pristine "
         f"prelabel copies for all and WISER sidecars; **{res['n_test']} test frames** ({res['n_test'] - res['n_test_new']} "
         f"existing + {res['n_test_new']} new, no txt, no sidecar); {res['n_overlap']} overlap frames; {res['n_files']} files in "
         "`MANIFEST_sha256.csv` (+ `verify_manifest.py`, `README.md` with the copy-to-Q: steps and the labelling rules).",
         f"- **WISER pixel kit** `{kit.as_posix()}` (`kit.json`, `README.md`, per camera `support.json`, `occluders.json`, "
         "11 night tables, `visibility_mask.npz`, `checks.csv`; `validation.csv`).",
         f"- **Pool** `{pool.as_posix()}`: {len(pfo)} frames (PNG), `pool_detections.csv.gz` (v5, conf ≥ 0.05), "
         "`pool_embeddings.npz` (DINOv3), `pool_targets.csv`, `pool_frames.csv`, `video_index/` — never re-grabbed.", "",
         "## Camera-night map validation (plan A2)", "",
         "| camera | night | rain mm | correction | pool frames | v5 boxes ≥ 0.5 mapped | pairs | median (in) | within-14 | control | verdict |",
         "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in val.itertuples():
        L.append(f"| {r.camera} | {r.night} | {f2(r.rain_mm_night, 1)} | {r.correction_flag} | {r.n_frames} | {r.n_det_mapped} | "
                 f"{r.real_n_pairs} | {f2(r.real_median_in)} | {f2(r.real_within14_share, 3)} | {f2(r.control_within14_share, 3)} | "
                 f"**{r.verdict}** |")
    nfail = val[~val["map_validated"]]
    L += ["", f"{int(val['map_validated'].sum())} of {len(val)} camera-nights pass; failing: "
          + (", ".join(f"{r.camera} {r.night} ({r.verdict})" for r in nfail.itertuples()) if len(nfail) else "none")
          + ". A failing camera-night keeps its frames for labelling but gets `map_validated = 0`: no WISER circles, no "
          "suspected-miss / social / hard-negative quota.", "",
          "## Pool (plan B2)", "",
          "| camera | eligible night-seconds | targets | frames ok | failed | usable (≤ 0.5 s, amendment 3) | boxes ≥ 0.05 | "
          "frames with a box ≥ 0.25 | median grab s (per worker) |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    usable = K.usable_pool_frames(pf)
    for cam in CAMS:
        a = pf[pf["camera"] == cam]
        ao = a[a["ok"] == 1]
        dd = dets[dets["image"].isin(ao["image"])]
        L.append(f"| {cam} | {pst[cam]['eligible_seconds']} | {len(a)} | {len(ao)} | {int((a['ok'] == 0).sum())} | "
                 f"{int((usable['camera'] == cam).sum())} | {len(dd)} | {dd[dd['conf'] >= PRELABEL_CONF]['image'].nunique()} | "
                 f"{ao['grab_s'].median():.2f} |")
    L += ["", "Stratified draw by stratum (tagged animals outside the houses / motion of the most active of them):", "",
          "| stratum | " + " | ".join(f"{c} eligible s | {c} drawn" for c in CAMS) + " |", "|---|" + "---:|" * (2 * len(CAMS))]
    for s in STRATA:
        L.append(f"| {s.replace('|', ' / ')} | " + " | ".join(f"{pst[c]['eligible_by_stratum'].get(s, 0)} | "
                                                           f"{pst[c]['drawn_by_stratum'].get(s, 0)}" for c in CAMS) + " |")
    ic = prj.get("identity_check", {})
    snap = pfo["snap_s"].astype(float)
    L += ["", f"Grab: the grab_frames.py command (CPU, exact seek, transpose=2), frame = the first sample with PTS ≥ the target "
          f"second; frame time − target: median {snap.median():.3f} s, max {snap.max():.3f} s. Identity check vs "
          f"`grab_frames.grab` on {ic.get('camera')} {ic.get('t_target')}: max pixel difference "
          f"{ic.get('max_abs_pixel_diff_vs_grab_frames_grab')}. Pool wall time {pool_wall_min(pool):.0f} min over its runs "
          "(a 6-frame check, a run stopped at 1 873 frames by a race on the video-index cache — fixed, resumed — and the "
          f"resume); last run {prj.get('runtime_last_s', 0) / 60:.0f} min; 4 grab workers; kit build "
          f"{kitj.get('runtime_s', 0) / 60:.0f} min; selection + package {res['runtime_s'] / 60:.0f} min.", "",
          "## Selection (plan B3–B4)", "",
          f"Clip-review rule: {rule.get('note') or ('export ' + str(rule['export']) + ', p = ' + str(rule['p_visible_missed']))} → "
          f"suspected-miss quota **{rule['quota']}**. Fixed-spot negatives: "
          f"{'none (no verdict exported)' if not rule['fixed_spot_objects'] else rule['fixed_spot_objects']}.", "",
          "| quota | " + " | ".join(f"{c} filled / quota (candidates)" for c in CAMS) + " |", "|---|" + "---:|" * len(CAMS)]
    for q in QUOTA_ORDER:
        L.append(f"| {q} | " + " | ".join(f"{res['fill'][c][q][0]} / {res['fill'][c][q][1]} ({res['fill'][c][q][2]})" for c in CAMS) + " |")
    L += ["", "Frames per night (selected, train):", "", "| night | " + " | ".join(CAMS) + " | rain mm |", "|---|" + "---:|" * (len(CAMS) + 1)]
    for n in NIGHTS:
        ns = str(n)
        rr = val[val["night"] == ns]["rain_mm_night"]
        L.append(f"| {ns} | " + " | ".join(str(int(((sel['camera'] == c) & (sel['night'] == ns)).sum())) for c in CAMS)
                 + f" | {f2(float(rr.iloc[0]) if len(rr) else float('nan'), 1)} |")
    vm = sel["n_visible_suspected_miss"].replace("", np.nan).astype(float)
    L += ["", f"Selected frames with ≥ 1 v5 box ≥ 0.25: {int((sel['n_boxes_v5'] > 0).sum())} of {len(sel)}; with ≥ 1 suspected "
          f"miss: {int((vm > 0).sum())}; map-validated: {int(sel['map_validated'].sum())}. DINOv3 k-means (k = {K_CLUSTERS}) "
          "cluster sizes: " + "; ".join(f"{c} {res['cluster_sizes'][c]}" for c in CAMS) + ".", "",
          "## Test set to 100 (plan B5, amendment 1)", "",
          f"Existing 40 (`cv/dataset/rat_pano_test/images/`, `.jpg`) copied unchanged (sha256 checked) + {res['n_test_new']} new "
          "(night 09-05, `select_pano_targets` stratified test rule: zero / few / many tagged animals outside = 0.2 / 0.4 / 0.4, "
          "≥ 5 min from each other and from that camera's existing frames; the rule drew "
          + ", ".join(f"{c} {res['test_ext'][c].get('drawn_by_the_rule')}" for c in CAMS)
          + " — 09-05 has only 27 min of 'zero' bins, too few for 6 more spaced frames next to the existing ones — and "
          "amendment 4 drew the shortfall from the other strata). No model ran on any test frame; no prelabel, "
          "no WISER sidecar. Minimum spacing per camera in the final test set (s): "
          + ", ".join(f"{c} {f2(v, 0)}" for c, v in res["test_min_sep_s"].items()) + ". Strata of the new frames: "
          + "; ".join(f"{c} {res['test_ext'][c]['strata']}" for c in CAMS) + ".", "",
          "## Definitions", "",
          "Units: paddock / WISER positions in inches; pixels = upright pano pixels (7680 × 2160); times = field-PC local "
          "seconds. Night D = D 21:00 → D+1 04:20. $j$ = animal (SF07–SF12), $t$ = whole second.", "",
          "### Kit pixel ($\\mathbf u_j(t)$) and radius ($r_j(t)$)",
          "$$ \\mathbf u_j(t)=A_t\\big(F^{-1}(T(\\mathbf w_j(t)),\\,z{=}60\\,\\mathrm{mm})\\big),\\qquad r_j(t)=14\\sqrt{|\\det J|},\\ "
          "J=\\partial\\mathbf u/\\partial\\mathbf p $$ **Text:** WISER position $\\mathbf w_j$ (default track, linear between "
          "clean fixes ≤ 5 s apart) → paddock by the accepted map $T$ → 09-18 calibration pixel by the inverse of the rev g "
          "camera $F$ at 60 mm above the local ground → the night's pixel by the frame-correction affine $A_t$ (interpolated "
          "per second). $r$ = radius (px) of the circle with the area of the 14-in ring's image. Units: px.", "",
          "### Hidden share ($h$) and robust hidden ($h^{rob}$)",
          "$$ h(\\mathbf p)=\\tfrac19\\sum_{k=1}^{9}\\mathbb 1[\\text{segment camera}\\to\\mathbf q_k(\\mathbf p)\\ \\text{meets an occluder}],\\quad "
          "h^{rob}(\\mathbf p)=\\max\\big(h(\\mathbf p),\\max_{a=0..7}h(\\mathbf p+7(\\cos\\tfrac{2\\pi a}{8},\\sin\\tfrac{2\\pi a}{8}))\\big) $$ "
          "**Text:** share of a rat's 9 sample points (30/60/90 mm × −40/0/+40 mm across the line of sight) hidden by a pole "
          "or house from this camera, looked up in the 2-in visibility mask; robust = also at 8 positions 7 in away (clamped "
          "1 in inside the paddock). Range [0, 1].", "",
          "### Map validation per camera-night",
          "$$ \\tilde r=\\operatorname{median}_{matched}\\lVert\\mathbf p_i-T(\\mathbf w_{\\pi(i)})\\rVert,\\quad f_{14}=\\frac1{|I|}"
          "\\sum_i\\mathbb 1[\\min_j\\lVert\\mathbf p_i-T(\\mathbf w_j)\\rVert\\le14],\\quad \\text{pass}\\iff\\tilde r\\le14\\wedge f_{14}\\ge2f^{+1h}_{14} $$ "
          "**Text:** $\\mathbf p_i$ = paddock position of a v5 box centre (conf ≥ 0.5) of a pool frame of that camera-night "
          "(`Corrections.to_paddock`, z = 60 mm); $\\pi$ = per-frame Hungarian assignment to the animals outside the house "
          "zones (gate 30 in); $f^{+1h}_{14}$ = the same share with WISER one hour later. Needs ≥ 20 mapped boxes and ≥ 10 "
          "pairs. Units: in; shares in [0, 1].", "",
          "### Frame scores",
          "$$ \\mathrm{miss}_j=\\mathbb 1[\\mathrm{tr}_j\\wedge\\neg\\mathrm{house}_j\\wedge\\mathrm{sup}_j\\wedge h^{rob}_j=0\\wedge\\min_b"
          "\\lVert\\mathbf p_b-\\mathbf p_j\\rVert>20],\\quad \\mathrm{social}=\\mathbb 1[\\exists j\\ne k\\in V:\\lVert\\mathbf p_j-\\mathbf p_k\\rVert\\le20] $$ "
          "**Text:** a visible suspected miss = a tracked animal outside the house zones, in the camera's support, robustly "
          "unhidden, with no v5 box (conf ≥ 0.25) whose centre maps within 20 in (a box outside the support counts as near when "
          "its pixel is within $20/14\\cdot r_j$). $V$ = animals tracked, in support, outside the house zones. Hard negative = "
          "all six tracked and all in house zones. Only on map-validated camera-nights; misses not on rain nights (≥ 1 mm "
          "21:00–04:20: 08-31, 09-03, 09-09). Merged event = per animal, a run of seconds in which it is tracked, outside, in "
          "support and robustly unhidden (gaps ≤ 5 s bridged); a frame's miss animals join their runs; ≤ 1 frame per event.", "",
          "### Stratum",
          "$$ n_{out}(t)=\\sum_j\\mathbb 1[\\mathrm{tr}_j\\wedge\\neg\\mathrm{house}_j],\\quad \\mathrm{stratum}=(\\{0,1\\text{–}2,\\ge3\\}(n_{out}),"
          "\\max_{j\\,out}\\mathrm{motion}_j) $$ **Text:** tagged animals outside the house zones (paddock-wide, WISER frame) and "
          "the most active state among them (still < active < locomoting; none when $n_{out}=0$): 7 strata.", "",
          "## Caveats", "",
          "- WISER is a lower bound on the animals present when `all_tracked` = 0 (SF12 night 08-30, SF11 09-02 00:03 → 08:20 "
          "and from 09-07 06:10:45). Before the 09-03 13:59 WISER restart the WISER frame was shifted 7–18 in; the validation "
          "decides those nights.",
          "- The suspected-miss score is a proposal for the labeller's eyes, not a measured miss rate: grass occlusion is not "
          "modelled, the box→paddock map assumes z = 60 mm, WISER is ± 3–7 in.",
          "- The +1 h control reads WISER after 04:20 for the last hour; operator rounds there (e.g. 08-31 03:30) remove fixes "
          "and make the control easier to beat on that night.", "",
          "## Rerun", "", "```",
          "C:/Users/Cornell/.conda/envs/cv/python.exe cv/cv_field/select_label_round1.py --pool",
          f"C:/Users/Cornell/.conda/envs/cv/python.exe cv/cv_field/build_wiser_pixel_kit.py --build --pool {pool.as_posix()}",
          f"C:/Users/Cornell/.conda/envs/cv/python.exe cv/cv_field/select_label_round1.py --select --pool {pool.as_posix()} --kit {kit.as_posix()}",
          "```", ""]
    p = rep / REPORT_NAME
    p.write_text("\n".join(L), encoding="utf-8")
    ptr = {"run_dir": pkg.resolve().as_posix(), "cohort": COHORT, "direction": DIRECTION, "analysis": "wiser_label_loop_round1",
           "drivers": ["cv/cv_field/build_wiser_pixel_kit.py", DRIVER], "report": REPORT_NAME, "plan": PLAN,
           "package": pkg.resolve().as_posix(), "kit": kit.resolve().as_posix(), "pool": pool.resolve().as_posix(),
           "git_commit": K.git_commit(REPO), "n_train": res["n_train"], "n_test": res["n_test"],
           "camera_nights_validated": int(val["map_validated"].sum()), "camera_nights": int(len(val))}
    (rep / POINTER_NAME).write_text(json.dumps(ptr, indent=2) + "\n", encoding="utf-8")
    return p


# ----------------------------------------------------------------------------------------------- selftest
def selftest() -> int:
    import tempfile
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}", flush=True)

    ffmpeg, ffprobe = gf.find_ffmpeg()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # 1. fragmented-MP4 sample index = ffprobe packets; grab returns the exact sample
        root = tmp / "v"
        (root / "2026-09-06" / "CH01").mkdir(parents=True)
        vid = root / "2026-09-06" / "CH01" / "CH01_2026-09-06_21-00-00_to_21-00-12.mp4"
        subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=180x320:rate=20:duration=12",
                        "-c:v", "libx265", "-x265-params", "keyint=40:min-keyint=40:scenecut=0:bframes=0:log-level=error",
                        "-pix_fmt", "yuv420p",
                        "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-video_track_timescale", "90000", str(vid)], check=True)
        ticks, tsc = video_sample_ticks(vid)
        pk = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts", "-of", "csv=p=0",
                             str(vid)], capture_output=True, text=True).stdout.split()
        ref = np.array([int(x.strip(",")) for x in pk], np.int64)
        rec("fMP4 index = ffprobe packet PTS (count, values, monotone; IP-only stream like the Reolink files)",
            len(ticks) == len(ref) == 240 and np.array_equal(np.sort(ticks), np.sort(ref)) and np.all(np.diff(ticks) > 0),
            f"{len(ticks)} samples, timescale {tsc}, first {ticks[:3].tolist()} vs ffprobe {ref[:3].tolist()}")
        gf.STORED["CH01"] = (180, 320)
        try:
            segs = gf.segments(root, "CH01", date(2026, 9, 6), ffprobe)
            vi = VideoIndex(tmp / "vi")
            g = grab_target("CH01", datetime(2026, 9, 6, 21, 0, 7), segs, ffmpeg, vi)
            img2, pts2, _ = gf.grab(ffmpeg, vid, 7.0, "CH01", "exact", "cpu")
            rec("grab_exact: frame 140 at 7.000 s, same pixels as grab_frames.grab, upright, name <stem>_f<frame>.png",
                g["frame"] == 140 and abs(g["snap_s"]) < 1e-6 and np.array_equal(g["img"], img2) and g["img"].shape[:2] == (180, 320)
                and g["image"] == "CH01_2026-09-06_21-00-00_to_21-00-12_f140.png" and (tmp / "vi" / f"{vid.stem}.npz").exists(),
                f"frame {g['frame']}, snap {g['snap_s']:.3f}")
            g2 = grab_target("CH01", datetime(2026, 9, 6, 21, 0, 7, 30000), segs, ffmpeg, vi)
            rec("grab_exact: a target between frames lands on the next sample", g2["frame"] == 141 and 0 < g2["snap_s"] <= 0.05)
        finally:
            gf.STORED["CH01"] = (2160, 7680)
    # 2. pool draw: strata shares, spacing, shortfall redistribution, random part
    rng = np.random.default_rng(3)
    n = 20000
    t = pd.Timestamp("2026-09-06 21:00") + pd.to_timedelta(np.arange(n) * 1.0, unit="s")
    strat = np.array(STRATA)[rng.integers(0, len(STRATA), n)]
    strat[strat == ">=3|still"] = "1-2|still"                   # a stratum with no candidates
    cand = pd.DataFrame({"t": t, "night": "2026-09-06", "hour": t.hour, "stratum": strat})
    d = draw_pool(cand, 140, 30, 10.0, 0)
    ts = np.sort(epoch_s(d["t"]))
    vc = d[d["kind"] == "strat"]["stratum"].value_counts()
    rec("pool draw: 140 stratified + 30 uniform, >= 10 s apart, the empty stratum's share redistributed",
        len(d) == 170 and (d["kind"] == "random").sum() == 30 and np.diff(ts).min() >= 10 and ">=3|still" not in vc
        and vc.min() >= 20 and vc.sum() == 140, str(vc.to_dict()))
    d2 = draw_pool(cand, 140, 30, 10.0, 0)
    rec("pool draw is deterministic for a seed", d.equals(d2))
    # 3. merged events: runs bridged over <= 5 s; frames sharing a run (or linked by a two-animal frame) = one event
    secs = np.array([0, 1, 2, 3, 9, 10, 20, 21, 22, 30], float)
    vis = np.array([1, 1, 1, 0, 1, 1, 0, 1, 1, 1], bool)
    rid = visible_runs(vis, secs)
    rec("visible runs: gap 3 -> 9 (6 s) splits, 22 -> 30 (8 s) splits; 0-2 one run", rid.tolist() == [0, 0, 0, -1, 1, 1, -1, 2, 2, 3])
    secs2 = np.array([0, 1, 2, 6, 7], float)
    rec("visible runs: a 4-s gap is bridged", visible_runs(np.ones(5, bool), secs2).tolist() == [0, 0, 0, 0, 0])
    ev = union_find_events([[("A", 0)], [("A", 0)], [("B", 1)], [("B", 1), ("C", 2)], [("C", 2)], [("D", 5)]])
    rec("union-find events: same run -> same event; a two-animal frame links two runs",
        ev[0] == ev[1] and ev[2] == ev[3] == ev[4] and ev[5] != ev[0] and ev[0] != ev[2])
    # 4. selector constraints + quota filling with shortfall to the strata
    recs = []
    base = pd.Timestamp("2026-09-01 21:00").value // 10**9
    for i in range(400):
        night = f"2026-09-{1 + i % 10:02d}"
        recs.append({"image": f"im{i}.png", "night": night, "hour": 21 + (i % 3), "epoch": float(base + 86400 * (i % 10) + 20 * i),
                     "stratum": STRATA[i % len(STRATA)], "n_visible_suspected_miss": 1 if i < 30 else 0,
                     "miss_animals": "SF07", "events": [f"ev{i // 3}"] if i < 30 else [], "social": 1 if 100 <= i < 105 else 0,
                     "n_wiser_in_view": 2, "hard_negative": 200 <= i < 230, "max_conf_v5": (i % 10) / 10.0})
    sc = pd.DataFrame(recs)
    X = np.random.default_rng(0).normal(size=(400, 8)).astype(np.float32)
    rows, meta = select_camera(sc, X, dict(QUOTAS), 0, set(), print)
    fill = meta["fill"]
    seln = pd.DataFrame(rows)
    rec("quotas: misses capped by one frame per event (10 events), social 5 of 30; shortfalls (50 + 25) to the strata; "
        "hard negatives by v5 conf; 200 in total, <= 25 per night, unique",
        fill["visible_suspected_miss"][0] == 10 and fill["social"][0] == 5 and fill["wiser_strata"][1] == 50 + 50 + 25
        and fill["hard_negative"][0] == 20 and len(seln) == 200 and seln["image"].is_unique
        and seln.groupby("night").size().max() <= MAX_PER_NIGHT
        and seln[seln["quota"] == "hard_negative"]["max_conf_v5"].min() >= 0.3,
        f"{ {k: v[0] for k, v in fill.items()} }, per night max {seln.groupby('night').size().max()}")
    # 5. YOLO txt + sidecar shape
    tx = yolo_txt(pd.DataFrame({"x1": [-10.0, 100.0], "y1": [100.0, 5.0], "x2": [90.0, 100.0], "y2": [200.0, 9.0]}))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for sub in ("images", "prelabels_v5"):
            (tmp / sub).mkdir()
        w1 = write_prelabels(tmp, "a_f1", "0 0.5 0.5 0.1 0.1\n")
        w0 = write_prelabels(tmp, "a_f2", "")
        rec("prelabels: editable txt only when v5 has a box; the pristine copy always (empty when none)",
            w1 and not w0 and (tmp / "images" / "a_f1.txt").exists() and not (tmp / "images" / "a_f2.txt").exists()
            and (tmp / "prelabels_v5" / "a_f2.txt").read_text(encoding="utf-8") == "" and (tmp / "prelabels_v5" / "a_f1.txt").exists())
    rec("YOLO txt: clipped to the frame, degenerate box dropped, class 0 normalised",
        tx == f"0 {45 / 7680:.6f} {150 / 2160:.6f} {90 / 7680:.6f} {100 / 2160:.6f}\n" and yolo_txt(pd.DataFrame(columns=["x1", "y1", "x2", "y2"])) == "")
    kt = pd.DataFrame({"t_pc": ["2026-09-06 22:00:00"] * 6, "animal": list(K.ANIMALS), "tracked": [1, 1, 1, 1, 1, 0],
                       "in_house": [0, 0, 1, 0, 0, 0], "u": [1.0, 2, 3, np.nan, 5, np.nan], "v": [1.0, 2, 3, np.nan, 5, np.nan],
                       "r_px": [100.0] * 5 + [np.nan], "hidden_share": [0, 0.5, 1, 0, 0, np.nan], "in_support": [1, 1, 1, 0, 1, 0],
                       "motion": ["still"] * 5 + ["unknown"], "all_tracked": [0] * 6, "map_validated": [1] * 6}).set_index(["t_pc", "animal"])
    r = {"camera": "CH01", "video": "CH01_x", "frame": 5, "t_pc": "2026-09-06 22:00:00", "night": "2026-09-06", "map_validated": 1,
         "all_tracked": 0}
    sd = sidecar(r, kt, [{"name": "pole_B2", "kind": "pole", "polygon": [[0, 0], [1, 0], [1, 1]], "source": "x"}])
    sd0 = sidecar({**r, "map_validated": 0}, kt, [{"name": "pole_B2", "kind": "pole", "polygon": [[0, 0], [1, 0], [1, 1]], "source": "x"}])
    rec("sidecar: schema keys, 6 animals with null pixels where missing; not validated -> animals [] but occluders kept",
        list(sd.keys()) == ["schema", "camera", "video", "frame", "t_pc", "night", "frame_size", "map_validated", "all_tracked",
                            "animals", "occluders", "note"] and len(sd["animals"]) == 6 and sd["animals"][3]["u"] is None
        and sd["animals"][5]["hidden_share"] is None and sd0["animals"] == [] and len(sd0["occluders"]) == 1
        and set(sd["animals"][0]) == {"id", "u", "v", "r_px", "in_house", "hidden_share", "in_support", "tracked", "motion"}
        and set(sd["occluders"][0]) == {"name", "kind", "polygon"})
    rec("manifest columns as shared", MANIFEST_COLS == ["image", "camera", "video", "frame", "t_pc", "night", "split", "quota",
                                                        "reason", "n_boxes_v5", "max_conf_v5", "n_wiser_in_view",
                                                        "n_visible_suspected_miss", "social", "all_tracked", "map_validated",
                                                        "cluster_id", "overlap"])
    # 6. MANIFEST + verify script
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "a").mkdir()
        (tmp / "a" / "x.txt").write_text("hello", encoding="utf-8")
        (tmp / "verify_manifest.py").write_text(VERIFY_PY, encoding="utf-8")
        n_ = write_manifest_sha(tmp)
        r1 = subprocess.run([sys.executable, str(tmp / "verify_manifest.py")], capture_output=True, text=True)
        (tmp / "a" / "x.txt").write_text("hellO", encoding="utf-8")
        r2 = subprocess.run([sys.executable, str(tmp / "verify_manifest.py")], capture_output=True, text=True)
        rec("MANIFEST_sha256 + verify_manifest.py: OK on the copy, FAIL after a change", n_ == 2 and r1.returncode == 0
            and "OK" in r1.stdout and r2.returncode == 1 and "MISMATCH" in r2.stdout)
    # 7. stratum labels
    rec("strata labels", stratum_of(np.array([0, 2, 3, 1]), np.array([0, 3, 1, 2])).tolist() == ["0|none", "1-2|locomoting", ">=3|still", "1-2|active"])
    print(("PASS" if ok else "FAIL") + " — select_label_round1 self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--pool", nargs="?", const="", default=None, help="--pool [dir]: build / resume the pool; with --select the pool dir")
    ap.add_argument("--select", action="store_true")
    ap.add_argument("--kit", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None, help="pool: grab at most this many new frames (testing)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.select:
        if not (a.pool and a.kit):
            ap.error("--select needs --pool <dir> and --kit <dir>")
        run_select(Path(a.pool), Path(a.kit), Path(a.out) if a.out else None)
        return 0
    if a.pool is not None:
        out = Path(a.pool) if a.pool else (Path(a.out) if a.out else None)
        run_pool(out, a.workers, a.limit)
        return 0
    ap.error("nothing to do (--selftest, --pool or --select)")


if __name__ == "__main__":
    raise SystemExit(main())
