r"""inbox_sam3_dino_test.py — in-box CH07 (house_2, cohort 3): SAM 3 text-prompt detection (T1), SAM 3 point-prompt masks
(T2) and a frozen DINOv3 head-crop identity probe (T3), all scored on the user's blind head clicks; plus the blind mask
review page for the user (amendment 1 item 1).

Specification: implementation_plan/2026-10-11-inbox-sam3-dinov3-test.md (approved by the user 2026-10-11), amendment 1
(Codex review "Yolo_identity", before results) and amendment 2 (implementation details fixed in this driver, before
results). Truth = the user's blind clicks (before_reveal, verdict_first / first_*) in the formal export
cv/configs/inbox_identity_2026c/inbox_identity_2026c_20261010_220725.csv; frames = the identity page's full-resolution
frames (2560 x 1920) of the phase-0 run. The agent never judges images: every image-based verdict is the user's.

Units and groups (amendment 1 item 2): consecutive usable segments are one still-episode group when the WISER house_2
roster (box_occupancy_1s.csv.gz) is unchanged over the interval [last frame of segment i, colour frame of segment i+1] and
every roster animal's head IMU (imu_seconds_cache) is ok and still in >= 90 % of its seconds. dev = the groups holding the
5 earliest usable segments (T1 / T2 choices only); test = the other groups. T3 is leave-one-group-out over all groups
(+ leave-one-day-out, 09-11 held out).

T1  SAM3SemanticPredictor (imgsz 1008, score floor 0.01), prompts P1 "rat", P2 "Long Evans rat", P3 "rat with a colorful
    rectangular implant on its head", P4 "hooded rat"; image features once per frame / tile, the four prompts on them;
    whole frame (primary) and 2 x 2 tiles 1344 x 1008 (sensitivity; cross-tile duplicates merged at mask IoU >= 0.5).
    A head is covered by a mask if the click lies inside it or within 15 px. Head -> the covering mask with the highest
    score (then smaller area); a mask chosen by several heads keeps the nearest one. Metrics vs tau; prompt and tau chosen
    by F1 on dev IR frames; head-point exclusivity on test IR frames with grouped-bootstrap CIs.
T2  SAM3Predictor (interactive, from sam3.pt; ultralytics 8.4.93 exposes points / labels for it, so the SAM 2.1 fallback is
    not used): per blind IR head a positive point; variant = + negative points at the frame's other blind heads.
    Exclusivity (mask covers its own head and no other), merge, own-head miss, areas (px), boxes (px), pairwise IoU.
T3  head-centred square crops (4 in = 299 px primary; 16 in = 1197 px sensitivity) -> 224 -> DINOv3 ViT-B/16, CLS and
    mean-patch; logistic regression (C by inner grouped CV) and nearest centroid; controls: position only (u, v; house
    frame), head-masked (disc 1.5 in filled with the crop median), position-matched (same position, another group's
    frame), shuffled labels. Decision rule of amendment 1 item 3.
Review  40 masks (14 T1 chosen prompt + tau, 13 T2 positive, 13 T2 negative) from test IR frames, stratified by pile size,
    method and score hidden; mask_key.csv kept in the run folder (not linked from the page).

Usage. GPU phases (data t1gpu t2gpu dino) in the cv env (C:/Users/Cornell/.conda/envs/cv/python.exe, PYTHONIOENCODING=utf-8);
the CPU phases (score review report) and the selftest in base Python (numpy pandas scipy scikit-learn opencv websocket-client),
because scipy's L-BFGS-B (sklearn's lbfgs) crashes natively in the cv env:
  python cv/cv_field/inbox_sam3_dino_test.py --selftest                 # synthetic, no GPU, no field data
  <cv env python> cv/cv_field/inbox_sam3_dino_test.py --phases data t1gpu t2gpu dino          # new run folder
  python cv/cv_field/inbox_sam3_dino_test.py --run <dir> --phases score review report        # scores from the caches
  <cv env python> ... --run <dir> --phases sweep_gpu ; python ... --run <dir> --phases sweep report   # amendment 4 (exploratory)
  python ... --run <dir> --phases gui        # interactive prompt explorer from the sweep caches (<run>/prompt_gui/index.html)
Output: $FIELD2026_ANALYSIS_OUT_ROOT/2026c/cv_field_inbox_sam3_dino_<ts>/ + results/2026c/cv_field/reports/
        cv_field_inbox_sam3_dino_2026c.md + pointer run_manifest_inbox_sam3_dino_2026c.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

OUT_ROOT = Path(os.environ.get("FIELD2026_ANALYSIS_OUT_ROOT", "D:/Field2026_analysis_out"))
COHORT, DIRECTION, NAME = "2026c", "cv_field", "cv_field_inbox_sam3_dino"
PLAN = "implementation_plan/2026-10-11-inbox-sam3-dinov3-test.md"
REPORT_NAME = f"cv_field_inbox_sam3_dino_{COHORT}.md"
POINTER_NAME = f"run_manifest_inbox_sam3_dino_{COHORT}.json"
CLICKS_CSV = REPO / "cv" / "configs" / "inbox_identity_2026c" / "inbox_identity_2026c_20261010_220725.csv"
STATEMENT_JSON = REPO / "cv" / "configs" / "inbox_identity_2026c" / "composition_statement_user_2026-10-11.json"
REVIEW_EXPORT_DIR = REPO / "cv" / "configs" / "inbox_sam3_mask_review_2026c"
P0_RUN = OUT_ROOT / "2026c" / "cv_field_inbox_p0_20261010_1702"
CLICKS_RUN = OUT_ROOT / "2026c" / "cv_field_inbox_clicks_20261010_2227"
IMU_ROOT = OUT_ROOT / "2026c" / "imu_seconds_cache"
SAM3_WEIGHTS = Path("C:/Users/Cornell/.cache/huggingface/hub/models--facebook--sam3/snapshots/"
                    "3c879f39826c281e95690f02c7821c4de09afae7/sam3.pt")
DINO_REPO = Path.home() / ".cache" / "torch" / "hub" / "facebookresearch_dinov3_main"
DINO_CKPT = Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / "dinov3_vitb16_pretrain_lvd1689m-73cec8be.pth"
TZ = ZoneInfo("America/New_York")
IMG_W, IMG_H = 2560, 1920

CLASSES = ("SF07", "SF08", "SF09", "SF10", "SF12")          # SF11 absent on every click day (left 09-07)
PROMPTS = {"P1": "rat", "P2": "Long Evans rat", "P3": "rat with a colorful rectangular implant on its head",
           "P4": "hooded rat"}
PKEYS = list(PROMPTS)
TAUS = [0.01, 0.02, 0.03, 0.05, 0.075] + [round(0.10 + 0.05 * k, 3) for k in range(18)]   # 0.10 ... 0.95
SCORE_FLOOR = 0.01
COVER_PX = 15.0
TILE_W, TILE_H, TILE_X, TILE_Y = 1344, 1008, (0, 1216), (0, 912)
MERGE_IOU = 0.5
N_DEV_SEG = 5
STILL_SHARE = 0.90
N_BOOT, SEED = 2000, 20261011
PX_PER_IN_DEFAULT = 74.79724152080254                       # the clicks run's proper fit (fit_summary.csv)
CROP_IN, BODY_CROP_IN, DISC_IN, PILE_LINK_IN = 4.0, 16.0, 1.5, 6.0
C_GRID = (1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0)
N_SHUFFLE = 20
MARGIN = 0.15
REVIEW_N = {"T1": 14, "T2pos": 13, "T2neg": 13}
STRATA = ("1", "2-3", "4+", "none")
CHOICES = [("one_whole_rat", "one whole rat"), ("part_of_a_rat", "part of a rat"),
           ("two_or_more_rats", "two or more rats"), ("not_a_rat", "not a rat")]
REVIEW_PAGE_VERSION = "inbox_sam3_mask_review_2026c_v1"


# ============================================================================================ small helpers
def git_commit() -> str:
    try:
        h = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", "cv/cv_field/inbox_sam3_dino_test.py"],
                               capture_output=True, text=True).stdout.strip()
        return h + ("+dirty" if dirty else "")
    except Exception:  # noqa: BLE001
        return "unknown"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (Path,)):
        return o.as_posix()
    if isinstance(o, (datetime, pd.Timestamp)):
        return str(o)
    if isinstance(o, float) and not np.isfinite(o):
        return None
    raise TypeError(type(o))


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, default=_jsonable, ensure_ascii=False), encoding="utf-8")


def unix_s(t: datetime) -> float:
    return t.replace(tzinfo=TZ).timestamp()


# ============================================================================================ masks (RLE cache)
def rle_encode(m: np.ndarray) -> np.ndarray:
    """Row-major run lengths of a boolean array, starting with a (possibly empty) run of False."""
    f = np.asarray(m, bool).ravel()
    if f.size == 0:
        return np.zeros(1, np.int32)
    d = np.flatnonzero(f[1:] != f[:-1]) + 1
    runs = np.diff(np.concatenate([[0], d, [f.size]]))
    if f[0]:
        runs = np.concatenate([[0], runs])
    return runs.astype(np.int32)


def rle_decode(counts, shape) -> np.ndarray:
    counts = np.asarray(counts, np.int64)
    vals = np.zeros(len(counts), bool)
    vals[1::2] = True
    return np.repeat(vals, counts).reshape(shape)


def crop_record(full: np.ndarray) -> dict:
    """A full-frame boolean mask -> {bbox (x0, y0, x1, y1) end-exclusive, crop, area}."""
    rows, cols = np.flatnonzero(full.any(1)), np.flatnonzero(full.any(0))
    if not len(rows):
        return {"bbox": (0, 0, 0, 0), "crop": np.zeros((0, 0), bool), "area": 0}
    y0, y1, x0, x1 = int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1
    c = full[y0:y1, x0:x1]
    return {"bbox": (x0, y0, x1, y1), "crop": c.copy(), "area": int(c.sum())}


def torch_records(masks) -> list[dict]:
    """(K, H, W) torch bool masks (GPU) -> bbox-cropped numpy records."""
    rows, cols = masks.any(2), masks.any(1)
    area = masks.flatten(1).sum(1).cpu().numpy()
    out = []
    for k in range(masks.shape[0]):
        r, c = rows[k].nonzero(), cols[k].nonzero()
        if r.numel() == 0:
            out.append({"bbox": (0, 0, 0, 0), "crop": np.zeros((0, 0), bool), "area": 0})
            continue
        y0, y1, x0, x1 = int(r[0]), int(r[-1]) + 1, int(c[0]), int(c[-1]) + 1
        out.append({"bbox": (x0, y0, x1, y1), "crop": masks[k, y0:y1, x0:x1].cpu().numpy().copy(), "area": int(area[k])})
    return out


def save_masks(path: Path, recs: list[dict], fields: dict) -> None:
    """recs: bbox-cropped masks; fields: name -> per-mask array (score, prompt, tile, ...)."""
    counts = [rle_encode(r["crop"]) for r in recs]
    offs = np.cumsum([0] + [len(c) for c in counts]).astype(np.int64)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, counts=np.concatenate(counts).astype(np.int32) if counts else np.zeros(0, np.int32), offsets=offs,
                        bbox=np.array([r["bbox"] for r in recs], np.int32).reshape(-1, 4),
                        area=np.array([r["area"] for r in recs], np.int64), **{k: np.asarray(v) for k, v in fields.items()})
    os.replace(tmp, path)


def load_masks(path: Path) -> dict:
    z = np.load(path, allow_pickle=False)
    d = {k: z[k] for k in z.files}
    bb, cnt, off = d["bbox"], d["counts"], d["offsets"]
    d["crops"] = [rle_decode(cnt[off[k]:off[k + 1]], (int(bb[k, 3] - bb[k, 1]), int(bb[k, 2] - bb[k, 0]))) for k in range(len(bb))]
    return d


def head_dist(crop: np.ndarray, bbox, u: float, v: float, r: float = COVER_PX) -> float:
    """Distance (px) from the click (u, v) to the mask: 0 if the pixel holding the click is in the mask, else the distance to
    the nearest mask-pixel centre if <= r + 1, else inf."""
    x0, y0, x1, y1 = (int(b) for b in bbox)
    if crop.size == 0:
        return np.inf
    iu, iv = int(np.floor(u)), int(np.floor(v))
    if x0 <= iu < x1 and y0 <= iv < y1 and crop[iv - y0, iu - x0]:
        return 0.0
    R = int(np.ceil(r)) + 1
    xa, xb, ya, yb = max(iu - R, x0), min(iu + R + 1, x1), max(iv - R, y0), min(iv + R + 1, y1)
    if xa >= xb or ya >= yb:
        return np.inf
    w = crop[ya - y0:yb - y0, xa - x0:xb - x0]
    if not w.any():
        return np.inf
    yy, xx = np.nonzero(w)
    return float(np.hypot(xx + xa + 0.5 - u, yy + ya + 0.5 - v).min())


def dist_matrix(heads_uv: np.ndarray, crops: list, bboxes) -> np.ndarray:
    D = np.full((len(heads_uv), len(crops)), np.inf)
    for j, (c, b) in enumerate(zip(crops, bboxes)):
        for i, (u, v) in enumerate(heads_uv):
            if b[0] - COVER_PX - 1 <= u <= b[2] + COVER_PX + 1 and b[1] - COVER_PX - 1 <= v <= b[3] + COVER_PX + 1:
                D[i, j] = head_dist(c, b, u, v)
    return D


def centroid(crop: np.ndarray, bbox) -> tuple[float, float]:
    a = crop.sum()
    if a == 0:
        return (np.nan, np.nan)
    ys = crop.sum(1) @ (np.arange(crop.shape[0]) + 0.5) / a
    xs = crop.sum(0) @ (np.arange(crop.shape[1]) + 0.5) / a
    return (float(xs + bbox[0]), float(ys + bbox[1]))


def mask_iou(ca: np.ndarray, ba, cb: np.ndarray, bb) -> float:
    aa, ab = int(ca.sum()), int(cb.sum())
    if aa == 0 or ab == 0:
        return 0.0
    x0, y0, x1, y1 = max(ba[0], bb[0]), max(ba[1], bb[1]), min(ba[2], bb[2]), min(ba[3], bb[3])
    inter = 0
    if x0 < x1 and y0 < y1:
        inter = int((ca[y0 - ba[1]:y1 - ba[1], x0 - ba[0]:x1 - ba[0]] & cb[y0 - bb[1]:y1 - bb[1], x0 - bb[0]:x1 - bb[0]]).sum())
    return inter / float(aa + ab - inter)


def union_area(crops: list, bboxes: list) -> int:
    x0, y0 = min(b[0] for b in bboxes), min(b[1] for b in bboxes)
    x1, y1 = max(b[2] for b in bboxes), max(b[3] for b in bboxes)
    canvas = np.zeros((y1 - y0, x1 - x0), bool)
    for c, b in zip(crops, bboxes):
        canvas[b[1] - y0:b[3] - y0, b[0] - x0:b[2] - x0] |= c
    return int(canvas.sum())


def full_mask(crop: np.ndarray, bbox, shape=(IMG_H, IMG_W)) -> np.ndarray:
    m = np.zeros(shape, bool)
    x0, y0, x1, y1 = bbox
    if crop.size:
        m[y0:y1, x0:x1] = crop
    return m


# ============================================================================================ truth, frames, piles
def load_truth(clicks_csv: Path, p0_run: Path, statement: Path | None = STATEMENT_JSON) -> dict:
    """Blind record + frame table + segment table. Blind = before_reveal, not legacy, with verdict_first (first_*)."""
    import inbox_click_analysis as ica
    snap = ica.load_clicks(clicks_csv)
    ct = ica.click_table(snap)
    rb = ica.record(ct, "blind")
    page = json.loads((p0_run / "identity_page" / "page_data.json").read_text(encoding="utf-8"))
    segs = ica.page_segments(page)
    paths = {(s["segment_id"], f["kind"]): (p0_run / "identity_page" / f["path"]).as_posix()
             for s in page["segments"] for f in s["frames"] if "path" in f}
    st = ica.load_statement(statement, segs) if statement else {"unusable": {}}
    heads = rb.rename(columns={"kind": "frame_kind"}).copy()
    heads["frame_id"] = heads.segment_id + "__" + heads.frame_kind
    heads["domain"] = np.where(heads.frame_kind == "colour_mid", "colour", "ir")
    heads = heads.sort_values(["frame_id", "click_id"]).reset_index(drop=True)
    fr = []
    for fid, g in heads.groupby("frame_id", sort=True):
        sid, kind = g.segment_id.iloc[0], g.frame_kind.iloc[0]
        S = segs[sid]
        fr.append({"frame_id": fid, "segment_id": sid, "frame_kind": kind, "domain": g.domain.iloc[0], "camera": S["camera"],
                   "house": S["house"], "path": paths[(sid, kind)], "frame_time": S["frames"][kind]["time"],
                   "seg_start": S["start"], "n_heads": len(g), "n_named": int(g.animal.isin(CLASSES).sum())})
    frames = pd.DataFrame(fr).sort_values(["seg_start", "frame_kind"]).reset_index(drop=True)
    after = ct[ct.status == "after_reveal"]
    dropped = sorted(set(after.segment_id + "__" + after.frame_kind) - set(frames.frame_id))
    dup = heads[heads.animal.isin(CLASSES)].groupby(["frame_id", "animal"]).click_id.transform("size") > 1
    heads["dup_label"] = False
    heads.loc[dup[dup].index, "dup_label"] = True
    return {"heads": heads, "frames": frames, "segs": segs, "click_table": ct, "dropped_frames": dropped,
            "unusable": st.get("unusable", {}), "n_blind": len(rb), "n_after": int((ct.status == "after_reveal").sum())}


def pile_sizes(uv: np.ndarray, link_px: float) -> np.ndarray:
    """Single-linkage clusters of the head points at link_px; per head the size of its cluster."""
    n = len(uv)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for i in range(n):
        for j in range(i + 1, n):
            if np.hypot(*(uv[i] - uv[j])) <= link_px:
                parent[find(i)] = find(j)
    roots = [find(i) for i in range(n)]
    return np.array([roots.count(r) for r in roots], int)


def stratum(p) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "none"
    p = int(p)
    return "1" if p == 1 else "2-3" if p <= 3 else "4+"


# ============================================================================================ still-episode groups
def load_occupancy(p0_run: Path, t0: datetime, t1: datetime) -> pd.DataFrame:
    occ = pd.read_csv(p0_run / "box_occupancy_1s.csv.gz", usecols=["time", "house_2"])
    occ = occ[(occ.time >= f"{t0:%Y-%m-%d %H:%M:%S}") & (occ.time <= f"{t1:%Y-%m-%d %H:%M:%S}")].copy()
    occ["sec"] = pd.to_datetime(occ.time).dt.tz_localize(TZ).map(lambda x: int(x.timestamp()))
    occ["house_2"] = occ.house_2.fillna("").astype(str)
    return occ.set_index("sec")


def load_imu(root: Path, animals, days) -> dict:
    out = {}
    for a in animals:
        parts = [pd.read_csv(root / a / f"{d:%Y%m%d}.csv.gz", usecols=["sec", "ok", "still"]) for d in sorted(set(days))
                 if (root / a / f"{d:%Y%m%d}.csv.gz").exists()]
        out[a] = (pd.concat(parts, ignore_index=True).drop_duplicates("sec").set_index("sec") if parts else pd.DataFrame(columns=["ok", "still"]))
    return out


def pair_link(t_a: datetime, t_b: datetime, occ: pd.DataFrame, imu: dict, share: float = STILL_SHARE) -> dict:
    """Join rule for two consecutive segments over [t_a, t_b] (field-PC local): roster unchanged + every roster animal still
    (ok and still) in >= share of the seconds; a missing or failed IMU second counts as not still."""
    s0, s1 = int(np.floor(unix_s(t_a))), int(np.floor(unix_s(t_b)))
    secs = np.arange(s0, s1 + 1)
    ro = occ.reindex(secs)
    n_missing_occ = int(ro.house_2.isna().sum())
    sets = sorted(set(ro.house_2.dropna()))
    unchanged = n_missing_occ == 0 and len(sets) == 1
    roster = [a for a in (sets[0].split(";") if sets and sets[0] else []) if a]
    shares, shares_ok = {}, {}
    for a in roster:
        d = imu.get(a)
        if d is None or d.empty:
            shares[a], shares_ok[a] = 0.0, np.nan
            continue
        g = d.reindex(secs)
        ok = g.ok.eq(True).to_numpy()
        st = g.still.eq(True).to_numpy() & ok
        shares[a] = float(st.sum() / len(secs))
        shares_ok[a] = float(st.sum() / ok.sum()) if ok.sum() else np.nan
    still_all = bool(roster) and all(v >= share for v in shares.values())
    still_all_okden = bool(roster) and all((v >= share) if np.isfinite(v) else False for v in shares_ok.values())
    with_imu = [a for a in roster if np.isfinite(shares_ok.get(a, np.nan))]          # >= 1 ok second in the interval
    still_alt = bool(with_imu) and all(shares[a] >= share for a in with_imu)
    return {"t_a": t_a, "t_b": t_b, "gap_s": float(s1 - s0 + 1), "n_missing_occ": n_missing_occ, "rosters_seen": " | ".join(sets),
            "roster_unchanged": unchanged, "roster": ";".join(roster),
            "still_share": ";".join(f"{a}:{v:.3f}" for a, v in shares.items()),
            "still_share_okden": ";".join(f"{a}:{v:.3f}" for a, v in shares_ok.items()),
            "min_still_share": min(shares.values()) if shares else np.nan,
            "joined": bool(unchanged and still_all), "joined_okden": bool(unchanged and still_all_okden),
            "joined_alt": bool(unchanged and still_alt), "animals_without_imu": ";".join(a for a in roster if a not in with_imu)}


def build_groups(seg_ids: list[str], segs: dict, occ: pd.DataFrame | None, imu: dict | None, joiner=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Chain consecutive segments by the join rule -> per-segment group table and per-pair table."""
    order = sorted(seg_ids, key=lambda s: segs[s]["start"])
    pairs, gid, gid_alt, gmap, gmap_alt = [], 1, 1, {}, {}
    gmap[order[0]] = gmap_alt[order[0]] = 1
    for a, b in zip(order[:-1], order[1:]):
        t_a = max(f["time"] for f in segs[a]["frames"].values())
        t_b = segs[b]["frames"]["colour_mid"]["time"]
        r = joiner(a, b) if joiner else pair_link(t_a, t_b, occ, imu)
        r.update({"seg_a": a, "seg_b": b})
        pairs.append(r)
        if not r["joined"]:
            gid += 1
        if not r.get("joined_alt", r["joined"]):
            gid_alt += 1
        gmap[b], gmap_alt[b] = gid, gid_alt
    rows = []
    for k, s in enumerate(order):
        rows.append({"segment_id": s, "order": k + 1, "start": segs[s]["start"], "group": f"G{gmap[s]:02d}",
                     "group_alt": f"A{gmap_alt[s]:02d}", "day": f"{segs[s]['start']:%Y-%m-%d}"})
    g = pd.DataFrame(rows)
    dev_groups = set(g.head(N_DEV_SEG).group)
    g["split"] = np.where(g.group.isin(dev_groups), "dev", "test")
    gd = g.groupby("group").day.agg(lambda x: ";".join(sorted(set(x))))
    g["group_day"] = g.group.map(gd)
    return g, pd.DataFrame(pairs)


# ============================================================================================ grouped bootstrap
def boot_weights(n_groups: int, n_boot: int = N_BOOT, seed: int = SEED) -> np.ndarray:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n_groups, size=(n_boot, n_groups))
    W = np.zeros((n_boot, n_groups))
    for b in range(n_boot):
        W[b] = np.bincount(idx[b], minlength=n_groups)
    return W


def ci(vals) -> tuple[float, float]:
    v = np.asarray(vals, float)
    v = v[np.isfinite(v)]
    return (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))) if len(v) else (np.nan, np.nan)


def flat(d: dict) -> dict:
    """(lo, hi) tuples -> <key>_lo / <key>_hi columns (for CSV tables)."""
    o = {}
    for k, v in d.items():
        if isinstance(v, (tuple, list)) and len(v) == 2 and all(isinstance(x, (int, float, np.floating)) for x in v):
            o[f"{k}_lo"], o[f"{k}_hi"] = float(v[0]), float(v[1])
        else:
            o[k] = v
    return o


def ratio_ci(num_g: np.ndarray, den_g: np.ndarray, W: np.ndarray) -> tuple[float, float]:
    with np.errstate(invalid="ignore", divide="ignore"):
        return ci((W @ num_g) / (W @ den_g))


# ============================================================================================ T1 scoring
def match_units(D: np.ndarray, score, area, cent, heads_uv, r: float = COVER_PX) -> dict:
    """One frame: D (n_heads, n_units) head->unit distance (units = kept masks / merged clusters). Head -> the covering unit with
    the highest score, then the smaller area; a unit chosen by several heads keeps the nearest (distance to the unit, then to
    its centroid). TP = units keeping a head; merged = units covering >= 2 heads; empty = units covering none; exclusive head =
    kept by a unit that covers no other head."""
    n, m = D.shape
    C = D <= r
    choice = np.full(n, -1)
    for i in range(n):
        js = np.flatnonzero(C[i])
        if len(js):
            choice[i] = min(js, key=lambda j: (-score[j], area[j], j))
    keeper = np.full(m, -1)
    for j in range(m):
        hs = np.flatnonzero(choice == j)
        if len(hs):
            keeper[j] = min(hs, key=lambda i: (D[i, j], float(np.hypot(heads_uv[i][0] - cent[j][0], heads_uv[i][1] - cent[j][1]))
                                               if np.isfinite(cent[j][0]) else 0.0, i))
    ncov = C.sum(0) if m else np.zeros(0, int)
    matched = np.zeros(n, bool)
    matched[keeper[keeper >= 0]] = True
    excl = np.array([bool(matched[i] and choice[i] >= 0 and ncov[choice[i]] == 1) for i in range(n)], bool)
    return {"n_heads": n, "n_masks": m, "tp": int((keeper >= 0).sum()), "merged": int((ncov >= 2).sum()), "empty": int((ncov == 0).sum()),
            "excl": int(excl.sum()), "choice": choice, "keeper": keeper, "ncov": ncov, "matched": matched, "exclusive": excl}


def tile_clusters(order: list[int], tile: np.ndarray, neighbours: dict) -> list[list[int]]:
    """order = mask indices (score descending, all >= tau). A mask joins the first-created cluster whose representative is a
    cross-tile neighbour (mask IoU >= MERGE_IOU); else it starts a cluster."""
    rep_of, clusters = {}, []
    for k in order:
        cands = [rep_of[r] for r in neighbours.get(k, ()) if r in rep_of and tile[r] != tile[k]]
        if cands:
            clusters[min(cands)].append(k)
        else:
            rep_of[k] = len(clusters)
            clusters.append([k])
    return clusters


def cross_tile_neighbours(M: dict, idx: np.ndarray) -> dict:
    """Pairs of masks (within idx) from different tiles with mask IoU >= MERGE_IOU."""
    bb, area, tile = M["bbox"], M["area"], M["tile"]
    nb: dict = {}
    idx = np.asarray(list(idx), int)
    if len(idx) < 2:
        return nb
    B, A, T = bb[idx].astype(np.int64), area[idx].astype(np.int64), tile[idx]
    iw = np.minimum(B[:, None, 2], B[None, :, 2]) - np.maximum(B[:, None, 0], B[None, :, 0])
    ih = np.minimum(B[:, None, 3], B[None, :, 3]) - np.maximum(B[:, None, 1], B[None, :, 1])
    ib = np.clip(iw, 0, None) * np.clip(ih, 0, None)             # bbox intersection >= mask intersection
    amax, amin = np.maximum(A[:, None], A[None, :]), np.minimum(A[:, None], A[None, :])
    # necessary for IoU >= MERGE_IOU: |Ma n Mb| / |Ma u Mb| <= min(ib, amin) / amax
    cand = (T[:, None] != T[None, :]) & (amin > 0) & (np.minimum(ib, amin) >= MERGE_IOU * amax)
    for i, j in np.argwhere(np.triu(cand, 1)):
        a, b = int(idx[i]), int(idx[j])
        if mask_iou(M["crops"][a], bb[a], M["crops"][b], bb[b]) >= MERGE_IOU:
            nb.setdefault(a, []).append(b)
            nb.setdefault(b, []).append(a)
    return nb


def t1_frame_sweep(M: dict, heads_uv: np.ndarray, tiled: bool, taus=TAUS, pkeys=None) -> list[dict]:
    """All prompts x taus for one frame's cached masks -> count rows (+ per-head detail at every tau). pkeys: prompt names in
    the order of M['prompt'] indices (default the T1 prompts P1..P4)."""
    rows = []
    bb, sc, ar, pr = M["bbox"], M["score"], M["area"], M["prompt"]
    for pi, pk in enumerate(pkeys or PKEYS):
        idx = np.flatnonzero(pr == pi)
        D = dist_matrix(heads_uv, [M["crops"][k] for k in idx], bb[idx]) if len(idx) else np.zeros((len(heads_uv), 0))
        Dfull = {k: D[:, n] for n, k in enumerate(idx)}
        cents = {k: centroid(M["crops"][k], bb[k]) for k in idx}
        nb = cross_tile_neighbours(M, idx) if tiled else {}
        ua_cache: dict = {}
        for tau in taus:
            keep = [k for k in idx[np.argsort(-sc[idx], kind="stable")] if sc[k] >= tau]
            if tiled:
                cl = tile_clusters(keep, M["tile"], nb)
                Du = np.column_stack([np.min(np.column_stack([Dfull[k] for k in c]), 1) for c in cl]) if cl else np.zeros((len(heads_uv), 0))
                s_u = np.array([sc[c[0]] for c in cl])
                a_u = []
                for c in cl:
                    key = tuple(sorted(c))
                    if key not in ua_cache:
                        ua_cache[key] = int(ar[c[0]]) if len(c) == 1 else union_area([M["crops"][k] for k in c], [tuple(bb[k]) for k in c])
                    a_u.append(ua_cache[key])
                c_u = [cents[c[0]] for c in cl]
                units = [c[0] for c in cl]
                n_members = [len(c) for c in cl]
            else:
                Du = np.column_stack([Dfull[k] for k in keep]) if keep else np.zeros((len(heads_uv), 0))
                s_u, a_u, c_u, units, n_members = sc[keep], ar[keep], [cents[k] for k in keep], keep, [1] * len(keep)
            r = match_units(Du, np.asarray(s_u, float), np.asarray(a_u, float), c_u, heads_uv)
            rows.append({"prompt": pk, "tau": tau, "n_heads": r["n_heads"], "n_masks": r["n_masks"], "tp": r["tp"], "merged": r["merged"],
                         "empty": r["empty"], "excl": r["excl"], "missed": int((r["choice"] < 0).sum()),
                         "n_cross_tile_merges": int(sum(n_members) - len(n_members)),
                         "_match": r, "_units": units, "_ncov": r["ncov"], "_clusters": cl if tiled else [[k] for k in keep]})
    return rows


def pooled(df: pd.DataFrame) -> dict:
    nh, nm, tp = df.n_heads.sum(), df.n_masks.sum(), df.tp.sum()
    ce = df.n_masks - df.n_heads
    return {"n_frames": len(df), "n_heads": int(nh), "n_masks": int(nm), "tp": int(tp), "merged": int(df.merged.sum()),
            "empty": int(df["empty"].sum()), "excl": int(df.excl.sum()),
            "P": tp / nm if nm else np.nan, "R": tp / nh if nh else np.nan, "F1": 2 * tp / (nm + nh) if (nm + nh) else np.nan,
            "X": df.excl.sum() / nh if nh else np.nan, "merged_rate": df.merged.sum() / nm if nm else np.nan,
            "empty_rate": df["empty"].sum() / nm if nm else np.nan, "count_err_mean": float(ce.mean()) if len(df) else np.nan,
            "count_err_mae": float(ce.abs().mean()) if len(df) else np.nan}


def t1_choose(sweep: pd.DataFrame) -> dict:
    """Prompt and tau maximising pooled F1 on dev IR frames (whole frame); ties -> higher tau, then lower prompt number."""
    d = sweep[(sweep.split == "dev") & (sweep.domain == "ir")]
    best = None
    for (pk, tau), g in d.groupby(["prompt", "tau"]):
        f1 = pooled(g)["F1"]
        key = (np.nan_to_num(f1, nan=-1.0), tau, -PKEYS.index(pk))
        if best is None or key > best[0]:
            best = (key, pk, tau, f1)
    return {"prompt": best[1], "tau": float(best[2]), "dev_F1": float(best[3]), "text": PROMPTS[best[1]]}


def t1_boot(df: pd.DataFrame, groups: list[str], W: np.ndarray) -> dict:
    """Grouped-bootstrap CIs of the pooled T1 metrics on a frame set (groups resampled with replacement)."""
    G = df.groupby("group")[["n_heads", "n_masks", "tp", "merged", "empty", "excl"]].sum().reindex(groups).fillna(0)
    ce = (df.n_masks - df.n_heads)
    df2 = df.assign(ce=ce, ace=ce.abs(), one=1)
    G2 = df2.groupby("group")[["ce", "ace", "one"]].sum().reindex(groups).fillna(0)
    out = {"P": ratio_ci(G.tp.values, G.n_masks.values, W), "R": ratio_ci(G.tp.values, G.n_heads.values, W),
           "F1": ratio_ci(2 * G.tp.values, (G.n_masks + G.n_heads).values, W), "X": ratio_ci(G.excl.values, G.n_heads.values, W),
           "merged_rate": ratio_ci(G.merged.values, G.n_masks.values, W), "empty_rate": ratio_ci(G["empty"].values, G.n_masks.values, W),
           "count_err_mean": ratio_ci(G2.ce.values, G2.one.values, W), "count_err_mae": ratio_ci(G2.ace.values, G2.one.values, W)}
    return out


# ============================================================================================ T2 scoring
def t2_frame(M: dict, heads: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """One IR frame's point-prompt masks (pos / neg variants, one mask per head) -> per-head rows and pairwise IoU rows."""
    uv = heads[["u", "v"]].to_numpy(float)
    cids = list(heads.click_id)
    rows, pairs = [], []
    for vi, var in enumerate(("pos", "neg")):
        sel = np.flatnonzero(M["variant"] == vi)
        order = [int(M["head"][k]) for k in sel]
        for k, hi in zip(sel, order):
            assert str(M["click_id"][k]) == cids[hi], "head order mismatch"
            d = np.array([head_dist(M["crops"][k], M["bbox"][k], u, v) for u, v in uv])
            cov = d <= COVER_PX
            own = bool(cov[hi])
            n = int(cov.sum())
            x0, y0, x1, y1 = (int(b) for b in M["bbox"][k])
            w, h = x1 - x0, y1 - y0
            rows.append({"click_id": cids[hi], "variant": var, "own_covered": own, "n_heads_covered": n,
                         "exclusive": own and n == 1, "merge": n >= 2, "miss_own": not own, "wrong_only": (not own) and n >= 1,
                         "area_px": int(M["area"][k]), "box_w_px": w, "box_h_px": h,
                         "box_aspect": (max(w, h) / min(w, h)) if min(w, h) > 0 else np.nan, "box_long_px": max(w, h),
                         "pred_score": float(M["score"][k])})
        for a_i, a in enumerate(sel):
            for b in sel[a_i + 1:]:
                pairs.append({"variant": var, "click_a": str(M["click_id"][a]), "click_b": str(M["click_id"][b]),
                              "iou": mask_iou(M["crops"][a], M["bbox"][a], M["crops"][b], M["bbox"][b])})
    return rows, pairs


# ============================================================================================ T3 crops + classifiers
def frame_fill(img: np.ndarray) -> np.ndarray:
    return np.median(img[::4, ::4].reshape(-1, img.shape[2]), axis=0).astype(img.dtype)


def square_crop(img: np.ndarray, u: float, v: float, side: int, fill) -> tuple[np.ndarray, tuple[int, int]]:
    """side x side crop centred on (u, v), clipped to the frame and padded with fill."""
    H, W = img.shape[:2]
    x0, y0 = int(np.floor(u)) - side // 2, int(np.floor(v)) - side // 2
    out = np.empty((side, side, img.shape[2]), img.dtype)
    out[:] = fill
    xa, xb, ya, yb = max(x0, 0), min(x0 + side, W), max(y0, 0), min(y0 + side, H)
    if xa < xb and ya < yb:
        out[ya - y0:yb - y0, xa - x0:xb - x0] = img[ya:yb, xa:xb]
    return out, (x0, y0)


def disc_masked(crop: np.ndarray, cx: float, cy: float, r: float) -> np.ndarray:
    """The crop with a disc of radius r (px) at (cx, cy) filled with the crop's per-channel median."""
    med = np.median(crop.reshape(-1, crop.shape[2]), axis=0).astype(crop.dtype)
    yy, xx = np.ogrid[:crop.shape[0], :crop.shape[1]]
    m = (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2 <= r * r
    out = crop.copy()
    out[m] = med
    return out


def lbfgs_ok() -> bool:
    """scipy's L-BFGS-B (sklearn's lbfgs solver) crashes natively in the cv env (Windows 0xc06d007f, a delay-load DLL failure,
    found 2026-10-11); probed in a child process so a crash cannot take this one down."""
    code = "from scipy.optimize import minimize; import numpy as np; minimize(lambda x: (x**2).sum(), np.ones(2), method='L-BFGS-B')"
    return subprocess.run([sys.executable, "-c", code], capture_output=True).returncode == 0


def _lr(C: float):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=5000))


def lr_fit(X, y, g, c_grid=C_GRID):
    """Logistic regression with C chosen by inner GroupKFold (min(5, n groups) folds, pooled accuracy; ties -> smaller C)."""
    import warnings
    from sklearn.model_selection import GroupKFold
    ug = np.unique(g)
    C_best = 1.0
    if len(ug) >= 2 and len(c_grid) > 1:
        gkf = GroupKFold(n_splits=min(5, len(ug)))
        splits = list(gkf.split(X, y, g))
        best = None
        for C in sorted(c_grid):
            corr = tot = 0
            for tr, va in splits:
                if len(np.unique(y[tr])) < 2:
                    continue
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    m = _lr(C).fit(X[tr], y[tr])
                corr += int((m.predict(X[va]) == y[va]).sum())
                tot += len(va)
            acc = corr / tot if tot else -1
            if best is None or acc > best[0] + 1e-12:
                best = (acc, C)
        C_best = best[1]
    with __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        m = _lr(C_best).fit(X, y)
    return m, C_best


class NearestCentroid:
    """cosine=True: L2-normalised embeddings, centroid = normalised class mean, predict max cosine; cosine=False: standardised
    coordinates, Euclidean nearest class mean."""

    def __init__(self, cosine: bool):
        self.cosine = cosine

    def _t(self, X):
        X = np.asarray(X, float)
        if self.cosine:
            return X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)
        return (X - self.mu) / self.sd

    def fit(self, X, y):
        X = np.asarray(X, float)
        if not self.cosine:
            self.mu, self.sd = X.mean(0), np.where(X.std(0) > 0, X.std(0), 1.0)
        Z = self._t(X)
        self.classes_ = np.unique(y)
        self.cent = np.array([Z[y == c].mean(0) for c in self.classes_])
        if self.cosine:
            self.cent /= np.maximum(np.linalg.norm(self.cent, axis=1, keepdims=True), 1e-12)
        return self

    def predict(self, X):
        Z = self._t(X)
        if self.cosine:
            return self.classes_[np.argmax(Z @ self.cent.T, 1)]
        d = ((Z[:, None, :] - self.cent[None]) ** 2).sum(-1)
        return self.classes_[np.argmin(d, 1)]


def fit_predict(clf: str, Xtr, ytr, gtr, Xte, cosine: bool):
    if clf == "lr":
        m, C = lr_fit(Xtr, ytr, gtr)
        return m.predict(Xte), C
    return NearestCentroid(cosine).fit(Xtr, ytr).predict(Xte), np.nan


def run_logo(X, y, g, clf: str, cosine: bool, n_jobs: int = 8) -> tuple[np.ndarray, dict]:
    from joblib import Parallel, delayed
    ug = list(np.unique(g))

    def one(gk):
        tr, te = g != gk, g == gk
        if len(np.unique(y[tr])) < 2:
            return gk, np.flatnonzero(te), np.array([None] * te.sum()), np.nan
        p, C = fit_predict(clf, X[tr], y[tr], g[tr], X[te], cosine)
        return gk, np.flatnonzero(te), p, C
    res = Parallel(n_jobs=n_jobs if clf == "lr" else 1)(delayed(one)(gk) for gk in ug)
    pred = np.empty(len(y), object)
    Cs = {}
    for gk, idx, p, C in res:
        pred[idx] = p
        Cs[gk] = C
    return pred, Cs


def run_split(X, y, g, train, test, clf: str, cosine: bool) -> tuple[np.ndarray, float]:
    pred = np.empty(len(y), object)
    p, C = fit_predict(clf, X[train], y[train], g[train], X[test], cosine)
    pred[test] = p
    return pred, C


def acc_stats(y, pred, mask=None) -> dict:
    from sklearn.metrics import balanced_accuracy_score
    m = np.ones(len(y), bool) if mask is None else mask
    yy, pp = y[m], pred[m].astype(str)
    vc = pd.Series(yy).value_counts()
    return {"n": int(m.sum()), "acc": float((yy == pp).mean()) if m.sum() else np.nan,
            "bal_acc": float(balanced_accuracy_score(yy, pp)) if m.sum() else np.nan,
            "majority_rate": float(vc.max() / vc.sum()) if len(vc) else np.nan, "chance": 1.0 / len(CLASSES)}


def decide(acc_m: float, acc_best: float, boot_m: np.ndarray, boot_best: np.ndarray, chance: float = 0.2, margin: float = MARGIN) -> dict:
    """Amendment 1 item 3. carries = point >= margin above chance AND above the best control, AND both grouped-bootstrap CIs
    of the differences exclude 0; established = additionally both CI lower bounds >= margin."""
    d_ch, d_ct = acc_m - chance, acc_m - acc_best
    ci_ch, ci_ct = ci(boot_m - chance), ci(boot_m - boot_best)
    carries = bool(d_ch >= margin and d_ct >= margin and ci_ch[0] > 0 and ci_ct[0] > 0)
    est = bool(carries and ci_ch[0] >= margin and ci_ct[0] >= margin)
    return {"d_chance": d_ch, "d_chance_ci": ci_ch, "d_ctrl": d_ct, "d_ctrl_ci": ci_ct, "carries_identity": carries,
            "gain_15pp_established": est}


# ============================================================================================ GPU phases
def build_semantic():
    from ultralytics.models.sam import SAM3SemanticPredictor
    return SAM3SemanticPredictor(overrides=dict(model=str(SAM3_WEIGHTS), conf=SCORE_FLOOR, imgsz=1008, save=False, verbose=False))


def build_interactive():
    """SAM 3 interactive (point) predictor. ultralytics 8.4.93 builds it with compile=self.args.compile (False) and the ViT
    trunk compiles whenever compile_mode is not None -> the model is built here with compile=None."""
    from ultralytics.models.sam import SAM3Predictor
    from ultralytics.models.sam.build_sam3 import build_interactive_sam3
    p = SAM3Predictor(overrides=dict(model=str(SAM3_WEIGHTS), imgsz=1008, conf=0.0, save=False, verbose=False))
    p.setup_model(model=build_interactive_sam3(str(SAM3_WEIGHTS), compile=None), verbose=False)
    return p


def semantic_image(pred, img: np.ndarray, prompts: list | None = None) -> list[dict]:
    """One image (frame or tile): features once, the prompts on them -> mask records with prompt index and score.
    prompts: [(index, text)], default the T1 prompts P1..P4."""
    pred.set_image(img)
    assert list(pred.imgsz) == [1008, 1008], pred.imgsz
    out = []
    for pi, text in (prompts or [(i, PROMPTS[k]) for i, k in enumerate(PKEYS)]):
        masks, boxes = pred.inference_features(pred.features, src_shape=img.shape[:2], text=[text])
        if masks is None or boxes.shape[0] == 0:
            continue
        sc = boxes[:, 4].float().cpu().numpy()
        for k, r in enumerate(torch_records(masks)):
            r.update({"prompt": pi, "score": float(sc[k])})
            out.append(r)
        del masks, boxes
    pred.reset_image()
    return out


def phase_t1gpu(run: Path, frames: pd.DataFrame) -> dict:
    import cv2
    import torch
    pred = build_semantic()
    tiles = [(x, y) for y in TILE_Y for x in TILE_X]
    tim = []
    for n, fr in enumerate(frames.itertuples()):
        pw, pt = run / "sam3_t1" / "whole" / f"{fr.frame_id}.npz", run / "sam3_t1" / "tiled" / f"{fr.frame_id}.npz"
        if pw.exists() and pt.exists():
            continue
        img = cv2.imread(fr.path, cv2.IMREAD_COLOR)
        assert img is not None and img.shape[:2] == (IMG_H, IMG_W), (fr.path, None if img is None else img.shape)
        t0 = time.perf_counter()
        if not pw.exists():
            recs = semantic_image(pred, img)
            save_masks(pw, recs, {"prompt": np.array([r["prompt"] for r in recs], np.int8),
                                  "score": np.array([r["score"] for r in recs], np.float32), "tile": np.full(len(recs), -1, np.int8)})
        t1 = time.perf_counter()
        if not pt.exists():
            recs = []
            for ti, (ox, oy) in enumerate(tiles):
                for r in semantic_image(pred, np.ascontiguousarray(img[oy:oy + TILE_H, ox:ox + TILE_W])):
                    x0, y0, x1, y1 = r["bbox"]
                    r["bbox"] = (x0 + ox, y0 + oy, x1 + ox, y1 + oy) if r["area"] else (0, 0, 0, 0)
                    r["tile"] = ti
                    recs.append(r)
            save_masks(pt, recs, {"prompt": np.array([r["prompt"] for r in recs], np.int8),
                                  "score": np.array([r["score"] for r in recs], np.float32),
                                  "tile": np.array([r["tile"] for r in recs], np.int8)})
        torch.cuda.synchronize() if torch.cuda.is_available() else None
        tim.append({"frame_id": fr.frame_id, "whole_s": t1 - t0, "tiled_s": time.perf_counter() - t1})
        print(f"  T1 {n + 1}/{len(frames)} {fr.frame_id}: whole {t1 - t0:.1f} s, tiled {time.perf_counter() - t1:.1f} s", flush=True)
    if tim:
        tp = run / "timing_t1.csv"
        pd.DataFrame(tim).to_csv(tp, mode="a", header=not tp.exists(), index=False)
    info = {"device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu", "precision": "fp32",
            "imgsz": [1008, 1008], "score_floor": SCORE_FLOOR, "nms_iou": float(pred.args.iou)}
    del pred
    torch.cuda.empty_cache()
    return info


def phase_t2gpu(run: Path, frames: pd.DataFrame, heads: pd.DataFrame) -> dict:
    import cv2
    import torch
    pred = build_interactive()
    tim = []
    irf = frames[frames.domain == "ir"]
    for n, fr in enumerate(irf.itertuples()):
        p = run / "sam3_t2" / f"{fr.frame_id}.npz"
        if p.exists():
            continue
        H = heads[heads.frame_id == fr.frame_id].sort_values("click_id")
        img = cv2.imread(fr.path, cv2.IMREAD_COLOR)
        assert img is not None and img.shape[:2] == (IMG_H, IMG_W)
        t0 = time.perf_counter()
        pred.set_image(img)
        assert list(pred.imgsz) == [1008, 1008], pred.imgsz
        pts = H[["u", "v"]].to_numpy(float)
        k = len(pts)
        recs, var, hidx, cid, sc = [], [], [], [], []
        m_pos, b_pos = pred.inference_features(pred.features, src_shape=img.shape[:2], points=pts[:, None, :],
                                               labels=np.ones((k, 1), int), multimask_output=False)
        if k > 1:
            neg_pts = np.stack([np.vstack([pts[i], np.delete(pts, i, 0)]) for i in range(k)])
            neg_lab = np.tile(np.array([1] + [0] * (k - 1)), (k, 1))
            m_neg, b_neg = pred.inference_features(pred.features, src_shape=img.shape[:2], points=neg_pts, labels=neg_lab,
                                                   multimask_output=False)
        else:
            m_neg, b_neg = m_pos, b_pos
        for vi, (m, b) in enumerate(((m_pos, b_pos), (m_neg, b_neg))):
            rr = torch_records(m)
            s = b[:, 4].float().cpu().numpy()
            for i, r in enumerate(rr):
                recs.append(r)
                var.append(vi)
                hidx.append(i)
                cid.append(H.click_id.iloc[i])
                sc.append(float(s[i]))
        pred.reset_image()
        save_masks(p, recs, {"variant": np.array(var, np.int8), "head": np.array(hidx, np.int16), "click_id": np.array(cid, dtype="U32"),
                             "score": np.array(sc, np.float32), "neg_same_as_pos": np.array([k == 1])})
        tim.append({"frame_id": fr.frame_id, "seconds": time.perf_counter() - t0, "n_heads": k})
        print(f"  T2 {n + 1}/{len(irf)} {fr.frame_id}: {k} heads, {time.perf_counter() - t0:.1f} s", flush=True)
        del m_pos, m_neg
    if tim:
        tp = run / "timing_t2.csv"
        pd.DataFrame(tim).to_csv(tp, mode="a", header=not tp.exists(), index=False)
    info = {"predictor": "SAM3Predictor (interactive), build_interactive_sam3(compile=None)", "imgsz": [1008, 1008],
            "multimask_output": False, "mask_threshold": float(getattr(pred.model, "mask_threshold", 0.0))}
    del pred
    torch.cuda.empty_cache()
    return info


def load_dino(dev: str):
    import torch
    m = torch.hub.load(str(DINO_REPO), "dinov3_vitb16", source="local", weights=str(DINO_CKPT))
    return m.eval().to(dev)


def dino_embed(model, crops_rgb: list[np.ndarray], dev: str, batch: int = 32) -> tuple[np.ndarray, np.ndarray]:
    import torch
    mean, std = np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32)
    cls, mp = [], []
    for i in range(0, len(crops_rgb), batch):
        x = np.stack([((c.astype(np.float32) / 255.0) - mean) / std for c in crops_rgb[i:i + batch]]).transpose(0, 3, 1, 2)
        with torch.no_grad():
            o = model.forward_features(torch.from_numpy(np.ascontiguousarray(x)).to(dev))
        cls.append(o["x_norm_clstoken"].float().cpu().numpy())
        mp.append(o["x_norm_patchtokens"].float().mean(1).cpu().numpy())
    return np.concatenate(cls), np.concatenate(mp)


def t3_units(heads: pd.DataFrame, frames: pd.DataFrame, groups: pd.DataFrame, fit: dict | None, seed: int = SEED) -> pd.DataFrame:
    """Named blind clicks (IR and colour) with group, day, house-frame position and the position-matched partner frame."""
    import inbox_click_analysis as ica
    u = heads[heads.animal.isin(CLASSES)].copy()
    gm = groups.set_index("segment_id")
    u["group"] = u.segment_id.map(gm.group)
    u["day"] = u.segment_id.map(gm.day)
    if fit is not None:
        hf = ica.sim_apply(fit, np.column_stack([u.u_ref, -u.v_ref]))
        u["along_in"], u["across_in"] = hf[:, 0], hf[:, 1]
    else:
        u["along_in"], u["across_in"] = u.u_ref, -u.v_ref
    rng = np.random.default_rng(seed)
    fg = frames.assign(group=frames.segment_id.map(gm.group))
    partner = []
    for r in u.itertuples():
        cand = fg[(fg.domain == r.domain) & (fg.group != r.group)].frame_id.tolist()
        partner.append(cand[int(rng.integers(len(cand)))] if cand else None)
    u["posmatch_frame"] = partner
    return u.reset_index(drop=True)


def phase_dino(run: Path, units: pd.DataFrame, frames: pd.DataFrame, px_per_in: float) -> dict:
    import cv2
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_dino(dev)
    sides = {"s4in": int(round(CROP_IN * px_per_in)), "s16in": int(round(BODY_CROP_IN * px_per_in))}
    disc_r = DISC_IN * px_per_in
    fpath = frames.set_index("frame_id").path
    jobs: dict = {}                     # frame -> list of (unit idx, content)
    for i, r in units.iterrows():
        jobs.setdefault(r.frame_id, []).append((i, "head"))
        jobs.setdefault(r.frame_id, []).append((i, "masked"))
        if r.posmatch_frame:
            jobs.setdefault(r.posmatch_frame, []).append((i, "posmatch"))
    feats = {f"{c}_{s}_{e}": np.full((len(units), 768), np.nan, np.float32)
             for c in ("head", "masked", "posmatch") for s in sides for e in ("cls", "mean")}
    for fid, js in jobs.items():
        img = cv2.imread(fpath[fid], cv2.IMREAD_COLOR)
        fill = frame_fill(img)
        for sk, side in sides.items():
            crops, keys = [], []
            for i, content in js:
                u, v = units.at[i, "u"], units.at[i, "v"]
                c, (x0, y0) = square_crop(img, u, v, side, fill)
                if content == "masked":
                    c = disc_masked(c, u - x0, v - y0, disc_r)
                c = cv2.resize(c, (224, 224), interpolation=cv2.INTER_AREA)
                crops.append(cv2.cvtColor(c, cv2.COLOR_BGR2RGB))
                keys.append((i, content))
            cl, mp = dino_embed(model, crops, dev)
            for (i, content), a, b in zip(keys, cl, mp):
                feats[f"{content}_{sk}_cls"][i] = a
                feats[f"{content}_{sk}_mean"][i] = b
    np.savez_compressed(run / "t3_embeddings.npz", click_id=units.click_id.to_numpy(dtype="U32"), **feats)
    info = {"model": "dinov3_vitb16", "checkpoint": DINO_CKPT.name, "hub_repo": DINO_REPO.as_posix(), "sides_px": sides,
            "disc_radius_px": disc_r, "device": dev}
    del model
    torch.cuda.empty_cache()
    return info


# ============================================================================================ T3 evaluation
def t3_eval(units: pd.DataFrame, E: dict, n_jobs: int = 8) -> dict:
    """All T3 configurations: LOGO (all groups) and LODO (train 09-09 + 09-10, test 09-11), per domain."""
    out_rows, preds, dec_rows, conf_rows, shuf_rows = [], [], [], [], []
    for dom in ("ir", "colour"):
        U = units[units.domain == dom].reset_index(drop=True)
        if U.empty:
            continue
        sel = units.index[units.domain == dom].to_numpy()
        y = U.animal.to_numpy()
        g = U.group.to_numpy()
        feats = {k: v[sel] for k, v in E.items()}
        feats["pos_uv"] = U[["u", "v"]].to_numpy(float)
        feats["pos_house"] = U[["along_in", "across_in"]].to_numpy(float)
        sides = ("s4in", "s16in") if dom == "ir" else ("s4in",)
        configs = []
        for s in sides:
            for e in ("cls", "mean"):
                for c in ("head", "masked", "posmatch"):
                    for clf in ("lr", "nc"):
                        configs.append((f"{c}_{s}_{e}", clf))
        for f in ("pos_uv", "pos_house"):
            for clf in ("lr", "nc"):
                configs.append((f, clf))
        days = sorted(set(U.day))
        lodo_test = U.day.to_numpy() == "2026-09-11"
        schemes = {"LOGO": None}
        if lodo_test.any() and (~lodo_test).any():
            schemes["LODO"] = lodo_test
        P = {}
        for sch, te in schemes.items():
            for fk, clf in configs:
                X = feats[fk]
                cosine = not fk.startswith("pos_")
                t0 = time.perf_counter()
                if sch == "LOGO":
                    pred, Cs = run_logo(X, y, g, clf, cosine, n_jobs)
                    m = np.ones(len(y), bool)
                else:
                    pred, C = run_split(X, y, g, ~te, te, clf, cosine)
                    Cs = {"train": C}
                    m = te
                P[(sch, fk, clf)] = pred
                st = acc_stats(y, pred, m)
                out_rows.append({"domain": dom, "scheme": sch, "feature": fk, "classifier": clf, **st,
                                 "C_chosen": ";".join(f"{k}:{v:g}" for k, v in Cs.items() if np.isfinite(v)) if clf == "lr" else "",
                                 "seconds": round(time.perf_counter() - t0, 2)})
                for i in np.flatnonzero(m):
                    preds.append({"domain": dom, "scheme": sch, "feature": fk, "classifier": clf, "click_id": U.click_id[i],
                                  "group": g[i], "day": U.day[i], "animal": y[i], "pred": pred[i]})
                print(f"  T3 {dom} {sch} {fk} {clf}: acc {st['acc']:.3f} ({time.perf_counter() - t0:.1f} s)", flush=True)
            # decisions (paired grouped bootstrap)
            mask = np.ones(len(y), bool) if sch == "LOGO" else te
            ug = sorted(set(g[mask]))
            W = boot_weights(len(ug))
            gi = {k: n for n, k in enumerate(ug)}

            def gsum(pred):
                corr = np.zeros(len(ug))
                tot = np.zeros(len(ug))
                for i in np.flatnonzero(mask):
                    corr[gi[g[i]]] += float(pred[i] == y[i])
                    tot[gi[g[i]]] += 1
                return corr, tot
            for s in sides:
                for e in ("cls", "mean"):
                    for clf in ("lr", "nc"):
                        mk = (sch, f"head_{s}_{e}", clf)
                        ctrl = {"position u,v": (sch, "pos_uv", clf), "position house frame": (sch, "pos_house", clf),
                                "head-masked": (sch, f"masked_{s}_{e}", clf), "position-matched": (sch, f"posmatch_{s}_{e}", clf)}
                        cm, tot = gsum(P[mk])
                        acc_m = cm.sum() / tot.sum()
                        bm = (W @ cm) / (W @ tot)
                        cacc = {}
                        cb = {}
                        for name, ck in ctrl.items():
                            cc, _ = gsum(P[ck])
                            cacc[name] = cc.sum() / tot.sum()
                            cb[name] = (W @ cc) / (W @ tot)
                        best = max(cacc, key=lambda k: (cacc[k], k))
                        d = decide(acc_m, cacc[best], bm, cb[best])
                        role = ("primary" if (s, e, clf) == ("s4in", "cls", "lr") else
                                "sensitivity (16-in crop)" if s == "s16in" else "secondary")
                        dec_rows.append(flat({"domain": dom, "scheme": sch, "role": role, "crop": s, "embedding": e, "classifier": clf,
                                              "n": int(tot.sum()), "n_groups": len(ug), "acc": acc_m, "acc_ci": ci(bm),
                                              **{f"acc_{k}": v for k, v in cacc.items()}, "best_control": best, "best_control_acc": cacc[best],
                                              **d}))
                        if role == "primary":
                            yy = y[mask]
                            pp = P[mk][mask].astype(str)
                            ct = pd.crosstab(pd.Series(yy, name="true"), pd.Series(pp, name="pred")).reindex(index=CLASSES, columns=CLASSES, fill_value=0)
                            for t_ in CLASSES:
                                for p_ in CLASSES:
                                    conf_rows.append({"domain": dom, "scheme": sch, "true": t_, "pred": p_, "n": int(ct.at[t_, p_])})
        # shuffled labels (IR, primary features, LOGO) and the duplicate-label sensitivity
        if dom == "ir":
            rng = np.random.default_rng(SEED)
            Xp = feats["head_s4in_cls"]
            for k in range(N_SHUFFLE):
                ys = rng.permutation(y)
                pred, _ = run_logo(Xp, ys, g, "lr", True, n_jobs)
                shuf_rows.append({"perm": k, "acc": float((pred.astype(str) == ys).mean())})
                print(f"  T3 shuffled {k + 1}/{N_SHUFFLE}: acc {shuf_rows[-1]['acc']:.3f}", flush=True)
            keep = ~U.dup_label.to_numpy(bool)
            if (~keep).any():
                Ud = U[keep]
                yd, gd = y[keep], g[keep]
                sub = {}
                for fk in ("head_s4in_cls", "pos_uv", "pos_house", "masked_s4in_cls", "posmatch_s4in_cls"):
                    pred, _ = run_logo(feats[fk][keep], yd, gd, "lr", not fk.startswith("pos_"), n_jobs)
                    sub[fk] = float((pred.astype(str) == yd).mean())
                out_rows.append({"domain": dom, "scheme": "LOGO (no duplicate-label clicks)", "feature": "summary",
                                 "classifier": "lr", "n": int(keep.sum()), "acc": sub["head_s4in_cls"],
                                 "C_chosen": json.dumps(sub), "bal_acc": np.nan, "majority_rate": np.nan, "chance": 0.2, "seconds": 0})
    return {"results": pd.DataFrame(out_rows), "preds": pd.DataFrame(preds), "decisions": pd.DataFrame(dec_rows),
            "confusion": pd.DataFrame(conf_rows), "shuffled": pd.DataFrame(shuf_rows)}


def t3_alt(units: pd.DataFrame, E: dict, n_jobs: int = 8) -> dict:
    """Amendment 3 sensitivity: the T3 primary (CLS + logistic, 4-in crop) and its controls, leave-one-group_alt-out, with the
    decision rule (paired bootstrap over group_alt)."""
    sel = units.index[units.domain == "ir"].to_numpy()
    U = units.loc[sel].reset_index(drop=True)
    y, g = U.animal.to_numpy(), U.group_alt.to_numpy()
    feats = {"primary": E["head_s4in_cls"][sel], "position u,v": U[["u", "v"]].to_numpy(float),
             "position house frame": U[["along_in", "across_in"]].to_numpy(float), "head-masked": E["masked_s4in_cls"][sel],
             "position-matched": E["posmatch_s4in_cls"][sel]}
    ug = sorted(set(g))
    W = boot_weights(len(ug))
    gi = np.array([ug.index(x) for x in g])
    tot = np.bincount(gi, minlength=len(ug)).astype(float)
    acc, boot = {}, {}
    for k, X in feats.items():
        pred, _ = run_logo(X, y, g, "lr", not k.startswith("position "), n_jobs)
        corr = np.bincount(gi, weights=(pred.astype(str) == y).astype(float), minlength=len(ug))
        acc[k], boot[k] = corr.sum() / tot.sum(), (W @ corr) / (W @ tot)
    ctrls = [k for k in feats if k != "primary"]
    best = max(ctrls, key=lambda k: (acc[k], k))
    return flat({"n": len(y), "n_groups": len(ug), "acc": acc["primary"], "acc_ci": ci(boot["primary"]),
                 **{f"acc_{k}": acc[k] for k in ctrls}, "best_control": best, "best_control_acc": acc[best],
                 **decide(acc["primary"], acc[best], boot["primary"], boot[best])})


# ============================================================================================ review page
def review_sample(t1_masks: pd.DataFrame, t2_heads: pd.DataFrame, seed: int = SEED, quota: dict = REVIEW_N) -> pd.DataFrame:
    """t1_masks: candidate T1 masks (columns key, stratum, ...); t2_heads: candidate heads (click_id, stratum, ...). Round-robin
    over strata (STRATA order), random within a stratum; T2 negative heads disjoint from the positive heads; items shuffled."""
    rng = np.random.default_rng(seed)

    def draw(cands: pd.DataFrame, q: int) -> pd.DataFrame:
        pools = {s: list(rng.permutation(cands.index[cands.stratum == s].to_numpy())) for s in STRATA}
        picked = []
        while len(picked) < q and any(pools.values()):
            for s in STRATA:
                if pools[s] and len(picked) < q:
                    picked.append(pools[s].pop(0))
        return cands.loc[picked]
    a = draw(t1_masks, quota["T1"]).assign(method="T1")
    b = draw(t2_heads, quota["T2pos"]).assign(method="T2pos")
    c = draw(t2_heads[~t2_heads.click_id.isin(b.click_id)], quota["T2neg"]).assign(method="T2neg")
    items = pd.concat([a, b, c], ignore_index=True)
    items = items.iloc[rng.permutation(len(items))].reset_index(drop=True)
    items["item_id"] = [f"M{k + 1:02d}" for k in range(len(items))]
    return items


def render_item(img: np.ndarray, crop: np.ndarray, bbox, out_dir: Path, item_id: str) -> dict:
    import cv2
    H, W = img.shape[:2]
    m = full_mask(crop, bbox, (H, W))
    tint = img.copy()
    col = np.array([255, 0, 255], np.float32)                       # magenta (BGR) fill + outline
    tint[m] = (0.62 * tint[m].astype(np.float32) + 0.38 * col).astype(np.uint8)
    cs, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(tint, cs, -1, (255, 0, 255), 4)
    x0, y0, x1, y1 = bbox
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    sx, sy = max((x1 - x0) * 1.6, 520), max((y1 - y0) * 1.6, 520)
    zx0, zx1 = int(max(cx - sx / 2, 0)), int(min(cx + sx / 2, W))
    zy0, zy1 = int(max(cy - sy / 2, 0)), int(min(cy + sy / 2, H))
    ctx = tint.copy()
    cv2.rectangle(ctx, (zx0, zy0), (zx1 - 1, zy1 - 1), (255, 255, 0), 8)
    ctx = cv2.resize(ctx, (960, 720), interpolation=cv2.INTER_AREA)
    z, zp = tint[zy0:zy1, zx0:zx1], img[zy0:zy1, zx0:zx1]
    sc = min(1.0, 1000 / max(z.shape[:2]))
    if sc < 1.0:
        z = cv2.resize(z, (int(z.shape[1] * sc), int(z.shape[0] * sc)), interpolation=cv2.INTER_AREA)
        zp = cv2.resize(zp, (int(zp.shape[1] * sc), int(zp.shape[0] * sc)), interpolation=cv2.INTER_AREA)
    out_dir.mkdir(parents=True, exist_ok=True)
    names = {"ctx": f"{item_id}_ctx.jpg", "zoom": f"{item_id}_zoom.jpg", "plain": f"{item_id}_plain.jpg"}
    for k, im in (("ctx", ctx), ("zoom", z), ("plain", zp)):
        cv2.imwrite(str(out_dir / names[k]), im, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return {k: f"items/{v}" for k, v in names.items()} | {"zoom_box": [zx0, zy0, zx1, zy1]}


PAGE_CSS = """
:root{--bg:#f7f7f5;--fg:#1c1c1a;--muted:#62625c;--card:#ffffff;--line:#d6d6d0;--acc:#2456c7;--done:#e6f1e6;--warn:#8a5a00}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#151514;--fg:#ececE8;--muted:#a5a59e;--card:#1f1f1d;--line:#3a3a36;--acc:#8fb0ff;--done:#1d2b1d;--warn:#e0b050}}
:root[data-theme="dark"]{--bg:#151514;--fg:#ececE8;--muted:#a5a59e;--card:#1f1f1d;--line:#3a3a36;--acc:#8fb0ff;--done:#1d2b1d;--warn:#e0b050}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px}
header h1{font-size:18px;margin:0 0 4px}header p{margin:2px 0;color:var(--muted);max-width:1100px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:6px}
button,label.btn{font:inherit;padding:5px 10px;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:6px;cursor:pointer}
button:hover,label.btn:hover{border-color:var(--acc)}#prog{font-weight:600}
main{padding:12px 16px;display:grid;gap:14px;max-width:1700px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.card.done{background:var(--done)}.card h2{font-size:16px;margin:0 0 6px;display:flex;gap:10px;align-items:baseline}
.card h2 .st{font-size:13px;color:var(--muted);font-weight:400}
.imgs{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:10px}
@media (max-width:900px){.imgs{grid-template-columns:minmax(0,1fr)}}
figure{margin:0}figure img{width:100%;height:auto;display:block;border:1px solid var(--line);border-radius:4px;background:#000}
figcaption{font-size:12.5px;color:var(--muted);margin-top:3px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
fieldset{border:0;padding:0;margin:8px 0 4px;display:flex;flex-wrap:wrap;gap:6px 16px}
fieldset label{display:flex;gap:5px;align-items:center;cursor:pointer}
textarea{width:100%;min-height:38px;font:inherit;padding:5px;border:1px solid var(--line);border-radius:5px;background:var(--bg);color:var(--fg)}
.hidden{display:none}
"""

PAGE_JS = r"""
(function(){
const D = JSON.parse(document.getElementById('data').textContent);
const KEY = D.page_version + '::' + D.run;
let S = {version: 1, items: {}};
function load(){ try { const t = localStorage.getItem(KEY); if (t) { const o = JSON.parse(t); if (o && o.items) S = o; } } catch(e) {} }
function save(){ try { localStorage.setItem(KEY, JSON.stringify(S)); } catch(e) {} }
function esc(s){ return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function stamp(){ const d = new Date(), p = n => String(n).padStart(2,'0');
  return d.getFullYear()+p(d.getMonth()+1)+p(d.getDate())+'_'+p(d.getHours())+p(d.getMinutes())+p(d.getSeconds()); }
function progress(){ const n = D.items.filter(it => S.items[it.id] && S.items[it.id].choice).length;
  document.getElementById('prog').textContent = n + ' / ' + D.items.length + ' judged'; }
function setState(id){ const c = document.getElementById('card-'+id), r = S.items[id] || {};
  c.classList.toggle('done', !!r.choice);
  c.querySelector('.st').textContent = r.choice ? ('judged: ' + D.choices.find(x => x[0] === r.choice)[1]) : 'not judged';
  applyFilter(); }
function applyFilter(){ const only = document.getElementById('onlyopen').checked;
  D.items.forEach(it => { const r = S.items[it.id] || {}, c = document.getElementById('card-'+it.id);
    if (c) c.classList.toggle('hidden', only && !!r.choice); }); }
function render(){
  const main = document.getElementById('list'); main.innerHTML = '';
  D.items.forEach((it, k) => {
    const r = S.items[it.id] || {};
    const sec = document.createElement('section'); sec.className = 'card'; sec.id = 'card-' + it.id;
    const radios = D.choices.map(c => '<label><input type="radio" name="c-'+it.id+'" value="'+c[0]+'"'+(r.choice===c[0]?' checked':'')+'> '+esc(c[1])+'</label>').join('');
    sec.innerHTML = '<h2>'+esc(it.id)+' <span class="st"></span><span class="st">('+(k+1)+' of '+D.items.length+')</span></h2>'
      + '<div class="imgs"><figure><img class="ctx" alt="whole frame" loading="lazy" src="'+esc(it.ctx)+'"><figcaption>whole frame: tinted = the region to judge, yellow box = the zoomed area</figcaption></figure>'
      + '<figure><img class="zoom" alt="zoomed region" loading="lazy" src="'+esc(it.zoom)+'" data-tint="'+esc(it.zoom)+'" data-plain="'+esc(it.plain)+'"><figcaption>zoom <button type="button" class="tog">hide tint</button></figcaption></figure></div>'
      + '<fieldset>'+radios+'</fieldset><textarea placeholder="notes (optional)">'+esc(r.note||'')+'</textarea>';
    main.appendChild(sec);
    sec.querySelectorAll('input[type=radio]').forEach(inp => inp.addEventListener('change', () => {
      S.items[it.id] = Object.assign(S.items[it.id] || {}, {choice: inp.value, judged_at: new Date().toISOString()}); save(); setState(it.id); progress(); }));
    sec.querySelector('textarea').addEventListener('input', e => {
      S.items[it.id] = Object.assign(S.items[it.id] || {}, {note: e.target.value, noted_at: new Date().toISOString()}); save(); });
    sec.querySelector('.tog').addEventListener('click', e => { const im = sec.querySelector('img.zoom');
      const plain = im.getAttribute('src') === im.dataset.tint; im.setAttribute('src', plain ? im.dataset.plain : im.dataset.tint);
      e.target.textContent = plain ? 'show tint' : 'hide tint'; });
    setState(it.id);
  });
  progress();
}
function rows(){ return D.items.map(it => { const r = S.items[it.id] || {};
  return {item_id: it.id, choice: r.choice || '', choice_label: r.choice ? D.choices.find(x => x[0] === r.choice)[1] : '', note: r.note || '', judged_at: r.judged_at || ''}; }); }
function exportJSON(){ return {page_version: D.page_version, run: D.run, exported_at: new Date().toISOString(), n_items: D.items.length,
  choices: D.choices, judgments: rows()}; }
function csvCell(v){ v = String(v == null ? '' : v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
function exportCSV(){ const cols = ['item_id','choice','choice_label','note','judged_at'];
  return [cols.join(',')].concat(rows().map(r => cols.map(c => csvCell(r[c])).join(','))).join('\n') + '\n'; }
function download(name, text, type){ const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {type: type}));
  a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
document.getElementById('ej').addEventListener('click', () => download(D.export_prefix + stamp() + '.json', JSON.stringify(exportJSON(), null, 2), 'application/json'));
document.getElementById('ec').addEventListener('click', () => download(D.export_prefix + stamp() + '.csv', exportCSV(), 'text/csv'));
document.getElementById('ij').addEventListener('change', e => { const f = e.target.files[0]; if (!f) return;
  f.text().then(t => { const o = JSON.parse(t); (o.judgments || []).forEach(j => { if (j.choice || j.note) S.items[j.item_id] = {choice: j.choice || '', note: j.note || '', judged_at: j.judged_at || ''}; });
  save(); render(); }); });
document.getElementById('onlyopen').addEventListener('change', applyFilter);
load(); render();
window.__review = {S: () => S, exportCSV, exportJSON, key: KEY, n: D.items.length};
})();
"""


def page_html(items: list[dict], run_name: str) -> str:
    import html as _html
    data = {"page_version": REVIEW_PAGE_VERSION, "run": run_name, "choices": CHOICES,
            "export_prefix": "inbox_sam3_mask_review_2026c_",
            "items": [{"id": it["item_id"], "ctx": it["ctx"], "zoom": it["zoom"], "plain": it["plain"]} for it in items]}
    js_data = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>In-box mask review</title><style>{PAGE_CSS}</style></head><body>
<header><h1>In-box CH07 mask review (cohort 3) — {len(items)} masks</h1>
<p>Each card shows one machine mask, tinted magenta, on a house frame. How it was made is hidden on purpose. For each one, pick what the
tinted region is: <b>one whole rat</b>, <b>part of a rat</b> (e.g. only the head or half the body), <b>two or more rats</b>, or <b>not a rat</b>.
Notes are optional. Answers are kept in this browser; press <b>Export JSON</b> and <b>Export CSV</b> when done and move both files,
unchanged, into <code>cv/configs/inbox_sam3_mask_review_2026c/</code>.</p>
<div class="bar"><span id="prog"></span><button id="ej" type="button">Export JSON</button><button id="ec" type="button">Export CSV</button>
<label class="btn">Import JSON<input id="ij" type="file" accept=".json,application/json" class="hidden"></label>
<label><input id="onlyopen" type="checkbox"> show only cards not yet judged</label><span style="color:var(--muted)">run {_html.escape(run_name)}</span></div></header>
<main id="list"></main>
<script id="data" type="application/json">{js_data}</script>
<script>{PAGE_JS}</script></body></html>
"""


FORBIDDEN = [r"\bprompt", r"\bscore", r"\bpositive\b", r"\bnegative\b", r"\bT1\b", r"\bT2\b", r"\btau\b", "\u03c4", r"\bpos\b",
             r"\bneg\b", r"text-prompt", r"point-prompt", r"Long Evans", r"hooded", r"implant", r"\bT2pos\b", r"\bT2neg\b"]


def blind_check_html(text: str) -> list[str]:
    body = re.sub(r"<style>.*?</style>", "", text, flags=re.S)
    return [p for p in FORBIDDEN if re.search(p, body, flags=re.I)]


def page_check(page_dir: Path, n_expected: int) -> dict:
    """Load the review page in headless Chrome (throwaway profile): every card and image renders, a judgment persists
    across a reload, the export functions return every item, no forbidden (method / score) words, no network URLs."""
    import inbox_identity_page as ipage
    html_text = (page_dir / "index.html").read_text(encoding="utf-8")
    res = {"forbidden_words": blind_check_html(html_text),
           "network_urls": re.findall(r"https?://[^\s\"'<>]+", html_text)}
    files = sorted(p.name for p in (page_dir / "items").glob("*.jpg"))
    res["n_item_files"] = len(files)
    prof = Path(tempfile.mkdtemp(prefix="maskrev_"))
    port = ipage._free_port()
    p, wsu, bws = ipage._chrome((page_dir / "index.html").resolve().as_uri(), prof, port)
    c = None
    try:
        c = ipage._CDP(wsu)
        c.call("Runtime.enable")

        def wait_loaded():
            for _ in range(240):
                try:
                    ok = c.ev("!!(window.__review) && Array.from(document.images).every(i => i.complete)")
                    if ok:
                        return True
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.25)
            return False
        c.ev("document.querySelectorAll('img').forEach(i => i.loading = 'eager')")
        res["loaded"] = wait_loaded()
        c.ev("document.querySelectorAll('img').forEach(i => { i.loading = 'eager'; const s = i.src; i.src = ''; i.src = s; })")
        time.sleep(1.0)
        res["loaded"] = res["loaded"] and wait_loaded()
        res["n_cards"] = c.ev("document.querySelectorAll('section.card').length")
        res["n_images"] = c.ev("document.images.length")
        res["n_images_ok"] = c.ev("Array.from(document.images).filter(i => i.complete && i.naturalWidth > 0).length")
        first = c.ev("window.__review ? JSON.parse(document.getElementById('data').textContent).items[0].id : null")
        c.ev(f"(() => {{ const r = document.querySelector('#card-{first} input[value=\"part_of_a_rat\"]'); r.click(); "
             f"const t = document.querySelector('#card-{first} textarea'); t.value = 'check'; t.dispatchEvent(new Event('input')); }})()")
        res["stored_before_reload"] = c.ev(f"JSON.parse(localStorage.getItem(window.__review.key)).items['{first}'].choice")
        c.call("Page.reload")
        time.sleep(1.5)
        wait_loaded()
        res["stored_after_reload"] = c.ev(f"window.__review.S().items['{first}'] ? window.__review.S().items['{first}'].choice : null")
        res["radio_checked_after_reload"] = c.ev(f"document.querySelector('#card-{first} input[value=\"part_of_a_rat\"]').checked")
        res["csv_lines"] = c.ev("window.__review.exportCSV().trim().split('\\n').length")
        res["json_items"] = c.ev("window.__review.exportJSON().judgments.length")
        res["toggle_ok"] = c.ev(f"(() => {{ const b = document.querySelector('#card-{first} .tog'); const im = document.querySelector('#card-{first} img.zoom'); "
                                "const a = im.getAttribute('src'); b.click(); const bb = im.getAttribute('src'); b.click(); "
                                "return a !== bb && im.getAttribute('src') === a; })()")
        c.ev("localStorage.clear()")
    finally:
        if c:
            c.close()
        ipage._close_chrome(p, bws)
        shutil.rmtree(prof, ignore_errors=True)
    res["verdict"] = "PASS" if (res.get("loaded") and res.get("n_cards") == n_expected and res.get("n_images") == 2 * n_expected
                                and res.get("n_images_ok") == 2 * n_expected and res.get("stored_before_reload") == "part_of_a_rat"
                                and res.get("stored_after_reload") == "part_of_a_rat" and res.get("radio_checked_after_reload")
                                and res.get("csv_lines") == n_expected + 1 and res.get("json_items") == n_expected
                                and res.get("toggle_ok") and not res["forbidden_words"] and not res["network_urls"]
                                and res["n_item_files"] == 3 * n_expected) else "FAIL"
    return res


# ============================================================================================ phases on the run
def phase_data(run: Path) -> dict:
    T = load_truth(CLICKS_CSV, P0_RUN)
    heads, frames, segs = T["heads"], T["frames"], T["segs"]
    seg_ids = sorted(frames.segment_id.unique(), key=lambda s: segs[s]["start"])
    assert not (set(seg_ids) & set(T["unusable"])), "an unusable segment has blind clicks"
    t_lo = min(segs[s]["start"] for s in seg_ids) - timedelta(minutes=5)
    t_hi = max(max(f["time"] for f in segs[s]["frames"].values()) for s in seg_ids) + timedelta(minutes=5)
    occ = load_occupancy(P0_RUN, t_lo, t_hi)
    days = [d.date() for d in pd.date_range(t_lo.date(), t_hi.date())]
    imu = load_imu(IMU_ROOT, CLASSES, days)
    groups, pairs = build_groups(seg_ids, segs, occ, imu)
    fit_pts = pd.read_csv(CLICKS_RUN / "fit_points_primary.csv")
    fsum = pd.read_csv(CLICKS_RUN / "fit_summary.csv")
    px_per_in = float(fsum.loc[fsum.fit == "proper", "px_per_in"].iloc[0]) if (fsum.fit == "proper").any() else PX_PER_IN_DEFAULT
    link = PILE_LINK_IN * px_per_in
    heads["pile_size"] = 0
    for fid, g in heads.groupby("frame_id"):
        heads.loc[g.index, "pile_size"] = pile_sizes(g[["u", "v"]].to_numpy(float), link)
    gm = groups.set_index("segment_id")
    for df in (heads, frames):
        df["group"] = df.segment_id.map(gm.group)
        df["group_alt"] = df.segment_id.map(gm.group_alt)
        df["split"] = df.segment_id.map(gm.split)
        df["day"] = df.segment_id.map(gm.day)
    frames.to_csv(run / "frames.csv", index=False)
    heads.to_csv(run / "heads.csv", index=False)
    groups.to_csv(run / "groups.csv", index=False)
    pairs.to_csv(run / "group_pairs.csv", index=False)
    meta = {"n_blind": T["n_blind"], "n_after_reveal_unused": T["n_after"], "dropped_frames": T["dropped_frames"],
            "unusable_segments": T["unusable"], "n_frames": len(frames), "n_ir_frames": int((frames.domain == "ir").sum()),
            "n_colour_frames": int((frames.domain == "colour").sum()), "n_heads": len(heads),
            "n_groups": int(groups.group.nunique()), "px_per_in": px_per_in, "pile_link_px": link,
            "clicks_sha256": sha256(CLICKS_CSV), "page_data_sha256": sha256(P0_RUN / "identity_page" / "page_data.json"),
            "occupancy_sha256": sha256(P0_RUN / "box_occupancy_1s.csv.gz"), "fit_points_n": len(fit_pts)}
    write_json(run / "data.json", meta)
    print(f"data: {len(heads)} blind heads on {len(frames)} frames, {meta['n_groups']} groups "
          f"({groups[groups.split == 'dev'].group.nunique()} dev)", flush=True)
    return meta


def read_tables(run: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frames = pd.read_csv(run / "frames.csv")
    heads = pd.read_csv(run / "heads.csv")
    groups = pd.read_csv(run / "groups.csv")
    return frames, heads, groups


def phase_score_t1(run: Path, frames: pd.DataFrame, heads: pd.DataFrame) -> dict:
    rows, detail = [], []
    for fr in frames.itertuples():
        H = heads[heads.frame_id == fr.frame_id].sort_values("click_id")
        uv = H[["u", "v"]].to_numpy(float)
        for var in ("whole", "tiled"):
            p = run / "sam3_t1" / var / f"{fr.frame_id}.npz"
            if not p.exists():
                continue
            M = load_masks(p)
            for r in t1_frame_sweep(M, uv, tiled=(var == "tiled")):
                mt = r.pop("_match")
                units = r.pop("_units")
                ncov = r.pop("_ncov")
                rows.append({"variant": var, "frame_id": fr.frame_id, "segment_id": fr.segment_id, "group": fr.group,
                             "group_alt": fr.group_alt, "split": fr.split, "domain": fr.domain, **r})
                if var == "whole":
                    for i, cid in enumerate(H.click_id):
                        j = mt["choice"][i]
                        detail.append({"prompt": r["prompt"], "tau": r["tau"], "frame_id": fr.frame_id, "click_id": cid,
                                       "matched": bool(mt["matched"][i]), "exclusive": bool(mt["exclusive"][i]),
                                       "covered": j >= 0, "mask_index": int(units[j]) if j >= 0 else -1,
                                       "mask_n_heads": int(ncov[j]) if j >= 0 else 0})
    sw = pd.DataFrame(rows)
    sw.to_csv(run / "t1_frame_metrics.csv.gz", index=False)
    det = pd.DataFrame(detail)
    det.to_csv(run / "t1_head_detail.csv.gz", index=False)
    agg = []
    for (var, pk, tau, dom, spl), g in sw.groupby(["variant", "prompt", "tau", "domain", "split"]):
        agg.append({"variant": var, "prompt": pk, "prompt_text": PROMPTS[pk], "tau": tau, "domain": dom, "split": spl, **pooled(g)})
    agg = pd.DataFrame(agg)
    agg.to_csv(run / "t1_sweep.csv", index=False)
    choice = t1_choose(sw[sw.variant == "whole"])
    choice_t = t1_choose(sw[sw.variant == "tiled"]) if (sw.variant == "tiled").any() else None
    test_groups = sorted(sw[(sw.split == "test")].group.unique())
    W = boot_weights(len(test_groups))
    res = {"choice": choice, "choice_tiled": choice_t, "test_groups": test_groups}

    def setting(var, pk, tau, dom, spl):
        g = sw[(sw.variant == var) & (sw.prompt == pk) & (sw.tau == tau) & (sw.domain == dom) & (sw.split == spl)]
        return pooled(g), (t1_boot(g, test_groups, W) if spl == "test" and len(g) else {})
    res["test_ir"] = setting("whole", choice["prompt"], choice["tau"], "ir", "test")
    ga = sw[(sw.variant == "whole") & (sw.prompt == choice["prompt"]) & (sw.tau == choice["tau"]) & (sw.domain == "ir") & (sw.split == "test")]
    alt_groups = sorted(ga.group_alt.unique())
    res["test_ir_group_alt_ci"] = t1_boot(ga.assign(group=ga.group_alt), alt_groups, boot_weights(len(alt_groups)))
    res["n_test_groups_alt"] = len(alt_groups)
    res["dev_ir"] = setting("whole", choice["prompt"], choice["tau"], "ir", "dev")
    res["test_colour"] = setting("whole", choice["prompt"], choice["tau"], "colour", "test")
    res["per_prompt"] = {}
    for pk in PKEYS:
        cp = t1_choose(sw[(sw.variant == "whole") & (sw.prompt == pk)])
        res["per_prompt"][pk] = {"tau": cp["tau"], "dev_F1": cp["dev_F1"], "test": setting("whole", pk, cp["tau"], "ir", "test")}
    if choice_t:
        res["tiled_test_ir"] = setting("tiled", choice_t["prompt"], choice_t["tau"], "ir", "test")
        res["tiled_at_primary_choice"] = setting("tiled", choice["prompt"], choice["tau"], "ir", "test")
    # by pile size (descriptive), chosen setting, test IR
    d = det[(det.prompt == choice["prompt"]) & (det.tau == choice["tau"])].merge(
        heads[["click_id", "pile_size", "domain", "split"]], on="click_id")
    d = d[(d.domain == "ir") & (d.split == "test")]
    bp = d.assign(stratum=d.pile_size.map(stratum)).groupby("stratum").agg(n_heads=("click_id", "size"), X=("exclusive", "mean"),
                                                                           R=("matched", "mean"), covered=("covered", "mean")).reset_index()
    bp.to_csv(run / "t1_by_pile_test_ir.csv", index=False)
    res["by_pile"] = bp.to_dict("records")
    write_json(run / "t1_result.json", res)
    return res


def phase_score_t2(run: Path, frames: pd.DataFrame, heads: pd.DataFrame) -> dict:
    rows, pairs = [], []
    for fr in frames[frames.domain == "ir"].itertuples():
        p = run / "sam3_t2" / f"{fr.frame_id}.npz"
        if not p.exists():
            continue
        H = heads[heads.frame_id == fr.frame_id].sort_values("click_id").reset_index(drop=True)
        r, pp = t2_frame(load_masks(p), H)
        for x in r:
            x.update({"frame_id": fr.frame_id, "group": fr.group, "split": fr.split})
        for x in pp:
            x.update({"frame_id": fr.frame_id, "group": fr.group, "split": fr.split})
        rows += r
        pairs += pp
    t2 = pd.DataFrame(rows).merge(heads[["click_id", "pile_size", "animal", "group_alt"]], on="click_id")
    t2.to_csv(run / "t2_heads.csv", index=False)
    pr = pd.DataFrame(pairs)
    pr.to_csv(run / "t2_pair_iou.csv", index=False)
    test_groups = sorted(t2[t2.split == "test"].group.unique())
    W = boot_weights(len(test_groups))
    summ = []
    gsum = {}
    for (var, spl), g in t2.groupby(["variant", "split"]):
        q = g.area_px.quantile([0.05, 0.25, 0.5, 0.75, 0.95]).to_numpy()
        pq = pr[(pr.variant == var) & (pr.split == spl)].iou
        row = {"variant": var, "split": spl, "n_heads": len(g), "X": g.exclusive.mean(), "merge": g["merge"].mean(),
               "miss_own": g.miss_own.mean(), "wrong_only": g.wrong_only.mean(),
               "area_p05": q[0], "area_p25": q[1], "area_median": q[2], "area_p75": q[3], "area_p95": q[4],
               "box_long_median": g.box_long_px.median(), "box_long_p95": g.box_long_px.quantile(0.95),
               "box_aspect_median": g.box_aspect.median(), "pred_score_median": g.pred_score.median(),
               "n_pairs": len(pq), "pair_iou_median": pq.median() if len(pq) else np.nan,
               "pair_iou_gt_0_1": (pq > 0.1).mean() if len(pq) else np.nan, "pair_iou_gt_0_5": (pq > 0.5).mean() if len(pq) else np.nan}
        if spl == "test":
            G = g.groupby("group").agg(n=("click_id", "size"), x=("exclusive", "sum"), m=("merge", "sum"), mo=("miss_own", "sum")).reindex(test_groups).fillna(0)
            row.update({"X_ci": ratio_ci(G.x.values, G.n.values, W), "merge_ci": ratio_ci(G.m.values, G.n.values, W),
                        "miss_own_ci": ratio_ci(G.mo.values, G.n.values, W)})
            gsum[var] = G
        summ.append(row)
    res = {"summary": summ}
    summ = [flat(r) for r in summ]
    if {"pos", "neg"} <= set(gsum):
        a, b = gsum["pos"], gsum["neg"]
        with np.errstate(invalid="ignore", divide="ignore"):
            dif = (W @ b.x.values) / (W @ b.n.values) - (W @ a.x.values) / (W @ a.n.values)
        res["neg_minus_pos_X"] = {"point": float(b.x.sum() / b.n.sum() - a.x.sum() / a.n.sum()), "ci": ci(dif)}
    alt = {}
    ta = t2[t2.split == "test"]
    ag = sorted(ta.group_alt.unique())
    Wa = boot_weights(len(ag))
    for var, g in ta.groupby("variant"):
        G = g.groupby("group_alt").agg(n=("click_id", "size"), x=("exclusive", "sum")).reindex(ag).fillna(0)
        alt[var] = {"X": float(G.x.sum() / G.n.sum()), "X_ci": ratio_ci(G.x.values, G.n.values, Wa), "n_groups": len(ag)}
    res["test_group_alt"] = alt
    bp = t2[t2.split == "test"].assign(stratum=t2.pile_size.map(stratum)).groupby(["variant", "stratum"]).agg(
        n=("click_id", "size"), X=("exclusive", "mean"), merge=("merge", "mean"), miss_own=("miss_own", "mean")).reset_index()
    bp.to_csv(run / "t2_by_pile_test.csv", index=False)
    res["by_pile"] = bp.to_dict("records")
    pd.DataFrame(summ).to_csv(run / "t2_summary.csv", index=False)
    write_json(run / "t2_result.json", res)
    return res


def phase_score_t3(run: Path, frames: pd.DataFrame, heads: pd.DataFrame, groups: pd.DataFrame, n_jobs: int = 8) -> dict:
    if not lbfgs_ok():
        raise SystemExit("scipy L-BFGS-B crashes in this interpreter (cv env): run '--phases score review report' with base Python")
    units = pd.read_csv(run / "t3_units.csv")
    z = np.load(run / "t3_embeddings.npz", allow_pickle=False)
    assert list(z["click_id"]) == list(units.click_id), "embedding order mismatch"
    E = {k: z[k] for k in z.files if k != "click_id"}
    R = t3_eval(units, E, n_jobs)
    R["results"].to_csv(run / "t3_results.csv", index=False)
    R["preds"].to_csv(run / "t3_predictions.csv.gz", index=False)
    dec = R["decisions"]
    dec.to_csv(run / "t3_decisions.csv", index=False)
    R["confusion"].to_csv(run / "t3_confusion.csv", index=False)
    R["shuffled"].to_csv(run / "t3_shuffled.csv", index=False)
    units["group_alt"] = units.segment_id.map(groups.set_index("segment_id").group_alt)
    alt = t3_alt(units, E, n_jobs)
    write_json(run / "t3_group_alt.json", alt)
    prim = dec[(dec.domain == "ir") & (dec.role == "primary")]
    out = {"primary": prim.to_dict("records"), "group_alt": alt, "shuffled_mean": float(R["shuffled"].acc.mean()) if len(R["shuffled"]) else np.nan,
           "shuffled_range": [float(R["shuffled"].acc.min()), float(R["shuffled"].acc.max())] if len(R["shuffled"]) else None}
    write_json(run / "t3_result.json", out)
    return out


def phase_review(run: Path, frames: pd.DataFrame, heads: pd.DataFrame, check: bool = True) -> dict:
    import cv2
    t1 = json.loads((run / "t1_result.json").read_text(encoding="utf-8"))
    pk, tau = t1["choice"]["prompt"], t1["choice"]["tau"]
    pi = PKEYS.index(pk)
    det = pd.read_csv(run / "t1_head_detail.csv.gz")
    det = det[(det.prompt == pk) & (det.tau == tau)]
    test_ir = frames[(frames.domain == "ir") & (frames.split == "test")]
    hpile = heads.set_index("click_id").pile_size
    cand1 = []
    for fr in test_ir.itertuples():
        M = load_masks(run / "sam3_t1" / "whole" / f"{fr.frame_id}.npz")
        H = heads[heads.frame_id == fr.frame_id].sort_values("click_id")
        uv = H[["u", "v"]].to_numpy(float)
        for k in np.flatnonzero((M["prompt"] == pi) & (M["score"] >= tau)):
            d = np.array([head_dist(M["crops"][k], M["bbox"][k], u, v) for u, v in uv])
            cov = np.flatnonzero(d <= COVER_PX)
            dd = det[(det.frame_id == fr.frame_id) & (det.mask_index == k) & det.matched]
            if len(dd):
                cid = dd.click_id.iloc[0]
            elif len(cov):
                cid = H.click_id.iloc[int(cov[np.argmin(d[cov])])]
            else:
                cid = None
            cand1.append({"frame_id": fr.frame_id, "mask_index": int(k), "click_id": cid, "n_heads_covered": int(len(cov)),
                          "pile_size": int(hpile[cid]) if cid else np.nan, "stratum": stratum(hpile[cid]) if cid else "none",
                          "score": float(M["score"][k]), "area_px": int(M["area"][k])})
    cand1 = pd.DataFrame(cand1)
    t2h = pd.read_csv(run / "t2_heads.csv")
    cand2 = heads[(heads.domain == "ir") & (heads.split == "test") & heads.click_id.isin(t2h.click_id)][["click_id", "frame_id", "pile_size"]].copy()
    cand2["stratum"] = cand2.pile_size.map(stratum)
    items = review_sample(cand1, cand2.reset_index(drop=True))
    page = run / "mask_review"
    if page.exists():
        shutil.rmtree(page)
    (page / "items").mkdir(parents=True)
    key_rows, page_items = [], []
    t2cache: dict = {}
    for it in items.itertuples():
        fr = frames.set_index("frame_id").loc[it.frame_id]
        img = cv2.imread(fr.path, cv2.IMREAD_COLOR)
        if it.method == "T1":
            M = load_masks(run / "sam3_t1" / "whole" / f"{it.frame_id}.npz")
            k = int(it.mask_index)
            meta = {"prompt": pk, "prompt_text": PROMPTS[pk], "tau": tau, "score": float(M["score"][k])}
        else:
            if it.frame_id not in t2cache:
                t2cache[it.frame_id] = load_masks(run / "sam3_t2" / f"{it.frame_id}.npz")
            M = t2cache[it.frame_id]
            vi = 0 if it.method == "T2pos" else 1
            k = int(np.flatnonzero((M["variant"] == vi) & (M["click_id"] == it.click_id))[0])
            meta = {"prompt": "", "prompt_text": "", "tau": np.nan, "score": float(M["score"][k])}
        r = render_item(img, M["crops"][k], tuple(int(b) for b in M["bbox"][k]), page / "items", it.item_id)
        page_items.append({"item_id": it.item_id, **r})
        key_rows.append({"item_id": it.item_id, "method": it.method, **meta, "frame_id": it.frame_id,
                         "click_id": it.click_id if isinstance(it.click_id, str) else "", "stratum": it.stratum,
                         "pile_size": it.pile_size, "mask_index": k, "area_px": int(M["area"][k]),
                         "bbox": ";".join(str(int(b)) for b in M["bbox"][k]), "zoom_box": ";".join(map(str, r["zoom_box"]))})
    key = pd.DataFrame(key_rows).sort_values("item_id")
    key.to_csv(run / "mask_key.csv", index=False)
    (page / "index.html").write_text(page_html(sorted(page_items, key=lambda x: x["item_id"]), run.name), encoding="utf-8")
    res = {"n_items": len(key), "by_method": key.method.value_counts().to_dict(),
           "by_method_stratum": key.groupby(["method", "stratum"]).size().rename("n").reset_index().to_dict("records"),
           "n_t1_candidates": len(cand1), "n_t2_candidates": len(cand2),
           "t1_candidates_by_stratum": cand1.stratum.value_counts().to_dict() if len(cand1) else {},
           "t2_candidates_by_stratum": cand2.stratum.value_counts().to_dict()}
    if check:
        res["page_check"] = page_check(page, len(key))
        write_json(run / "mask_review_page_check.json", res["page_check"])
        print(f"review page check: {res['page_check']['verdict']}", flush=True)
    write_json(run / "mask_review_meta.json", res)
    return res


# ============================================================================================ exploratory prompt sweep (amendment 4)
SWEEP_PROMPTS = ["rat", "Long Evans rat", "hooded rat", "black striped rat", "rat with a black stripe on its back",
                 "black and white rat", "rat with a black head and a white body", "rat with an implant on its head",
                 "sleeping rats", "pile of rats"]
SWEEP_FROM_T1 = {0: 0, 1: 1, 2: 3}        # sweep prompt index -> T1 cache prompt index (P1 rat, P2 Long Evans rat, P4 hooded rat)
SWEEP_TAUS = (0.01, 0.25)                 # the T1 dev-chosen tau, and a fixed 0.25
SWEEP_DAYS = ("2026-09-10", "2026-09-11")
SWEEP_PER_DAY = 5
SWEEP_COLOURS = [(255, 70, 70), (40, 200, 255), (60, 220, 60), (255, 80, 255), (0, 150, 255), (255, 255, 0), (40, 40, 255),
                 (190, 130, 255), (130, 255, 190), (255, 190, 60), (210, 210, 210), (0, 110, 210)]     # BGR, cycled per mask
SWEEP_PANEL_W, SWEEP_PANEL_H = 512, 384


def select_sweep_frames(frames: pd.DataFrame, groups: pd.DataFrame) -> pd.DataFrame:
    """Amendment 4: eligible = a usable segment with an IR frame at 07:00-19:00 holding >= 3 blind heads; per day one segment
    per group_alt (the middle one in time), then SWEEP_PER_DAY at round(linspace(0, n - 1, k)); IR frame = ir_p06 if eligible
    else ir_p15; the colour mid-frame of the same segment is the separate colour block."""
    gm = groups.set_index("segment_id")
    f = frames.copy()
    f["t"] = pd.to_datetime(f.frame_time)
    ir = f[(f.domain == "ir") & (f.n_heads >= 3) & (f.t.dt.hour >= 7) & (f.t.dt.hour < 19)]
    rows = []
    for day in SWEEP_DAYS:
        segs = sorted(set(ir[ir.t.dt.strftime("%Y-%m-%d") == day].segment_id), key=lambda x: str(gm.at[x, "start"]))
        by: dict = {}
        for sid in segs:
            by.setdefault(gm.at[sid, "group_alt"], []).append(sid)
        reps = sorted((v[(len(v) - 1) // 2] for v in by.values()), key=lambda x: str(gm.at[x, "start"]))
        idx = (np.round(np.linspace(0, len(reps) - 1, SWEEP_PER_DAY)).astype(int) if len(reps) > SWEEP_PER_DAY
               else np.arange(len(reps)))
        for i in idx:
            sid = reps[int(i)]
            irf = ir[ir.segment_id == sid].sort_values("frame_kind").iloc[0]
            col = f[(f.segment_id == sid) & (f.domain == "colour")]
            rows.append({"day": day, "segment_id": sid, "group": gm.at[sid, "group"], "group_alt": gm.at[sid, "group_alt"],
                         "split": gm.at[sid, "split"], "ir_frame": irf.frame_id, "ir_time": str(irf.frame_time), "ir_heads": int(irf.n_heads),
                         "colour_frame": col.frame_id.iloc[0] if len(col) else None,
                         "colour_heads": int(col.n_heads.iloc[0]) if len(col) else 0})
    return pd.DataFrame(rows)


def sweep_masks(run: Path, fid: str, variant: str) -> dict:
    """The T1 cache (reused prompts, remapped to sweep indices) + the sweep cache (new prompts) of one frame and variant."""
    A = load_masks(run / "sam3_t1" / variant / f"{fid}.npz")
    B = load_masks(run / "prompt_sweep" / "sam3" / variant / f"{fid}.npz")
    inv = {t1: sw for sw, t1 in SWEEP_FROM_T1.items()}
    ka = np.flatnonzero(np.isin(A["prompt"], list(inv)))
    return {"bbox": np.concatenate([A["bbox"][ka], B["bbox"]]).astype(np.int64), "area": np.concatenate([A["area"][ka], B["area"]]),
            "score": np.concatenate([A["score"][ka], B["score"]]).astype(np.float32),
            "tile": np.concatenate([A["tile"][ka], B["tile"]]).astype(int),
            "prompt": np.concatenate([np.array([inv[int(x)] for x in A["prompt"][ka]], int), B["prompt"].astype(int)]),
            "crops": [A["crops"][k] for k in ka] + list(B["crops"])}


def phase_sweep_gpu(run: Path, frames: pd.DataFrame, groups: pd.DataFrame) -> dict:
    import cv2
    import torch
    sd = run / "prompt_sweep"
    sd.mkdir(parents=True, exist_ok=True)
    sel = select_sweep_frames(frames, groups)
    sel.to_csv(sd / "sweep_frames.csv", index=False)
    pred = build_semantic()
    new = [(i, t) for i, t in enumerate(SWEEP_PROMPTS) if i not in SWEEP_FROM_T1]
    tiles = [(x, y) for y in TILE_Y for x in TILE_X]
    fpath = frames.set_index("frame_id").path
    fids = list(sel.ir_frame) + [x for x in sel.colour_frame if isinstance(x, str)]
    for n, fid in enumerate(fids):
        pw, pt = sd / "sam3" / "whole" / f"{fid}.npz", sd / "sam3" / "tiled" / f"{fid}.npz"
        if pw.exists() and pt.exists():
            continue
        img = cv2.imread(fpath[fid], cv2.IMREAD_COLOR)
        t0 = time.perf_counter()
        if not pw.exists():
            recs = semantic_image(pred, img, new)
            save_masks(pw, recs, {"prompt": np.array([r["prompt"] for r in recs], np.int8),
                                  "score": np.array([r["score"] for r in recs], np.float32), "tile": np.full(len(recs), -1, np.int8)})
        if not pt.exists():
            recs = []
            for ti, (ox, oy) in enumerate(tiles):
                for r in semantic_image(pred, np.ascontiguousarray(img[oy:oy + TILE_H, ox:ox + TILE_W]), new):
                    x0, y0, x1, y1 = r["bbox"]
                    r["bbox"] = (x0 + ox, y0 + oy, x1 + ox, y1 + oy) if r["area"] else (0, 0, 0, 0)
                    r["tile"] = ti
                    recs.append(r)
            save_masks(pt, recs, {"prompt": np.array([r["prompt"] for r in recs], np.int8),
                                  "score": np.array([r["score"] for r in recs], np.float32),
                                  "tile": np.array([r["tile"] for r in recs], np.int8)})
        print(f"  sweep {n + 1}/{len(fids)} {fid}: {time.perf_counter() - t0:.1f} s", flush=True)
    # determinism check: "rat" re-run on the first IR frame (whole) vs the T1 cache
    fid = fids[0]
    img = cv2.imread(fpath[fid], cv2.IMREAD_COLOR)
    recs = sorted(semantic_image(pred, img, [(0, "rat")]), key=lambda r: -r["score"])
    C = load_masks(run / "sam3_t1" / "whole" / f"{fid}.npz")
    ck = sorted(np.flatnonzero(C["prompt"] == 0), key=lambda k: -C["score"][k])
    same_n = len(recs) == len(ck)
    det = {"frame_id": fid, "n_rerun": len(recs), "n_cache": len(ck), "same_n": same_n}
    if same_n and ck:
        det["max_abs_score_diff"] = float(max(abs(r["score"] - float(C["score"][k])) for r, k in zip(recs, ck)))
        det["n_masks_pixel_identical"] = int(sum(tuple(r["bbox"]) == tuple(int(b) for b in C["bbox"][k]) and np.array_equal(r["crop"], C["crops"][k])
                                                 for r, k in zip(recs, ck)))
    info = {"new_prompts": [t for _, t in new], "reused_from_t1": {SWEEP_PROMPTS[k]: PKEYS[v] for k, v in SWEEP_FROM_T1.items()},
            "n_frames": len(fids), "determinism_rat_whole": det,
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"}
    write_json(sd / "gpu_info.json", info)
    del pred
    torch.cuda.empty_cache()
    return info


def _draw_panel(base: np.ndarray, M: dict, clusters: list, uv: np.ndarray, scale: float, path: Path) -> None:
    import cv2
    im = base.copy()
    for ci, cl in enumerate(clusters):
        colr = SWEEP_COLOURS[ci % len(SWEEP_COLOURS)]
        for k in cl:
            crop = M["crops"][k]
            if crop.size == 0:
                continue
            cs, _ = cv2.findContours(crop.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            off = np.array([M["bbox"][k][0], M["bbox"][k][1]], np.float32)
            cv2.polylines(im, [((c.astype(np.float32) + off) * scale).astype(np.int32) for c in cs], True, colr, 2, cv2.LINE_AA)
    for u, v in uv:
        cv2.circle(im, (int(u * scale), int(v * scale)), 5, (0, 0, 0), -1, cv2.LINE_AA)
        cv2.circle(im, (int(u * scale), int(v * scale)), 3, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.imwrite(str(path), im, [cv2.IMWRITE_JPEG_QUALITY, 82])


def phase_sweep(run: Path, frames: pd.DataFrame, heads: pd.DataFrame, check: bool = True) -> dict:
    """Scores the sweep against the blind clicks (T1 matching), draws the panels and writes the page for the user."""
    import cv2
    sd = run / "prompt_sweep"
    sel = pd.read_csv(sd / "sweep_frames.csv")
    pdir = sd / "panels"
    if pdir.exists():
        shutil.rmtree(pdir)
    pdir.mkdir(parents=True)
    fpath = frames.set_index("frame_id")
    rows, page_frames = [], []
    blocks = [("ir", fid) for fid in sel.ir_frame] + [("colour", fid) for fid in sel.colour_frame if isinstance(fid, str)]
    for fi, (dom, fid) in enumerate(blocks):
        H = heads[heads.frame_id == fid].sort_values("click_id")
        uv = H[["u", "v"]].to_numpy(float)
        img = cv2.imread(fpath.at[fid, "path"], cv2.IMREAD_COLOR)
        scale = SWEEP_PANEL_W / img.shape[1]
        base = cv2.resize(img, (SWEEP_PANEL_W, SWEEP_PANEL_H), interpolation=cv2.INTER_AREA)
        tag = f"F{fi + 1:02d}"
        _draw_panel(base, {"crops": [], "bbox": []}, [], uv, scale, pdir / f"{tag}_clicks.jpg")
        panels: dict = {pk: {} for pk in SWEEP_PROMPTS}
        for var in ("whole", "tiled"):
            M = sweep_masks(run, fid, var)
            for r in t1_frame_sweep(M, uv, tiled=(var == "tiled"), taus=SWEEP_TAUS, pkeys=SWEEP_PROMPTS):
                clusters = r.pop("_clusters")
                for k in ("_match", "_units", "_ncov"):
                    r.pop(k)
                rows.append({"domain": dom, "frame_id": fid, "variant": var, **r})
                pi = SWEEP_PROMPTS.index(r["prompt"])
                name = f"{tag}_p{pi}_{var[0]}_{int(round(r['tau'] * 100)):03d}.jpg"
                _draw_panel(base, M, clusters, uv, scale, pdir / name)
                panels[r["prompt"]].setdefault(var, {})[f"{r['tau']:g}"] = {
                    "img": f"panels/{name}", "masks": r["n_masks"], "excl": r["excl"], "missed": r["missed"], "merged": r["merged"],
                    "empty": r["empty"]}
        page_frames.append({"tag": tag, "domain": dom, "frame_id": fid, "time": str(fpath.at[fid, "frame_time"]), "heads": len(uv),
                            "clicks": f"panels/{tag}_clicks.jpg", "rows": [{"prompt": pk, **panels[pk]} for pk in SWEEP_PROMPTS]})
        print(f"  sweep page {fi + 1}/{len(blocks)} {fid}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(sd / "sweep_frame_metrics.csv", index=False)
    summ = []
    for (dom, var, pk, tau), g in df.groupby(["domain", "variant", "prompt", "tau"], sort=False):
        nh = int(g.n_heads.sum())
        summ.append({"domain": dom, "variant": var, "prompt": pk, "prompt_no": SWEEP_PROMPTS.index(pk) + 1, "tau": tau,
                     "n_frames": len(g), "n_heads": nh, "n_masks": int(g.n_masks.sum()), "exclusive": int(g.excl.sum()),
                     "X": g.excl.sum() / nh if nh else np.nan, "missed": int(g.missed.sum()), "merged": int(g.merged.sum()),
                     "empty": int(g["empty"].sum()), "masks_per_frame": g.n_masks.mean(), "heads_per_frame": g.n_heads.mean(),
                     "count_err_mean": (g.n_masks - g.n_heads).mean()})
    sm = pd.DataFrame(summ).sort_values(["domain", "variant", "tau", "prompt_no"], key=lambda c: c.map({"ir": 0, "colour": 1}) if c.name == "domain" else c)
    sm.to_csv(sd / "sweep_summary.csv", index=False)
    (sd / "index.html").write_text(sweep_page_html(page_frames, run.name), encoding="utf-8")
    res = {"n_frames": len(blocks), "n_panels": int(len(df))}
    if check:
        res["page_check"] = sweep_page_check(sd, len(blocks))
        write_json(sd / "page_check.json", res["page_check"])
        print(f"sweep page check: {res['page_check']['verdict']}", flush=True)
    write_json(sd / "sweep_meta.json", res)
    return res


SWEEP_JS = r"""
(function(){
const D = JSON.parse(document.getElementById('data').textContent);
let tau = '0.25';
function esc(s){ return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function cap(p, h){ return p.masks + ' masks · ' + p.excl + '/' + h + ' heads exclusive · ' + p.missed + ' missed · ' + p.merged + ' merged · ' + p.empty + ' empty'; }
function render(){
  const main = document.getElementById('list'); main.innerHTML = '';
  let lastDom = null;
  D.frames.forEach((f, i) => {
    if (f.domain !== lastDom) { const h = document.createElement('h2'); h.className = 'dom';
      h.textContent = f.domain === 'ir' ? 'IR frames (target domain)' : 'Colour frames (separate block, never pooled with IR)'; main.appendChild(h); lastDom = f.domain; }
    const sec = document.createElement('section'); sec.className = 'frame'; sec.id = f.tag;
    let html = '<h3>' + esc(f.tag) + ' · ' + esc(f.frame_id) + ' · ' + esc(f.time) + ' · ' + f.heads + ' clicked heads</h3>'
      + '<figure class="clk"><img loading="lazy" src="' + esc(f.clicks) + '" alt="clicks"><figcaption>the user\'s blind head clicks (dots)</figcaption></figure>';
    f.rows.forEach(r => {
      html += '<div class="row"><div class="pname">' + esc(r.prompt) + '</div>';
      ['whole', 'tiled'].forEach(v => { const p = r[v][tau];
        html += '<figure><img loading="lazy" class="pan" data-v="' + v + '" data-p="' + esc(r.prompt) + '" src="' + esc(p.img) + '" alt="' + v + '"><figcaption><b>' + v + '</b>: ' + cap(p, f.heads) + '</figcaption></figure>'; });
      html += '</div>';
    });
    sec.innerHTML = html; main.appendChild(sec);
  });
  document.getElementById('nav').innerHTML = D.frames.map(f => '<a href="#' + f.tag + '">' + f.tag + (f.domain === 'colour' ? 'c' : '') + '</a>').join(' ');
}
document.querySelectorAll('input[name=tau]').forEach(i => i.addEventListener('change', e => { tau = e.target.value; render(); }));
render();
window.__sweep = {n: D.frames.length, setTau: t => { tau = t; render(); }, tau: () => tau};
})();
"""


def sweep_page_html(page_frames: list, run_name: str) -> str:
    import html as _html
    data = json.dumps({"frames": page_frames}, ensure_ascii=False).replace("</", "<\\/")
    css = PAGE_CSS + """
.dom{margin:18px 0 4px;font-size:18px}.frame{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:10px 0}
.frame h3{font-size:15px;margin:0 0 6px}.row{display:grid;grid-template-columns:150px minmax(0,1fr) minmax(0,1fr);gap:8px;align-items:start;margin:6px 0}
.pname{font-weight:600;padding-top:4px}.clk{max-width:520px}#nav a{margin-right:6px}
@media (max-width:900px){.row{grid-template-columns:minmax(0,1fr)}}
"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>In-box prompt sweep</title><style>{css}</style></head><body>
<header><h1>In-box CH07 — SAM 3 prompt sweep (exploratory, 10 IR + 10 colour frames)</h1>
<p>One panel per text prompt: SAM 3 on the whole frame (left) and on 2 × 2 tiles (right). Each machine mask is outlined in its own
colour; the white dots are your blind head clicks. The counts under each panel are mask ↔ click counts only (a mask "covers" a click within
15 px); nobody has judged these images. Exploratory: no threshold or prompt was chosen from it.</p>
<div class="bar"><span>mask score threshold:</span><label><input type="radio" name="tau" value="0.01"> 0.01 (the earlier test's dev choice)</label>
<label><input type="radio" name="tau" value="0.25" checked> 0.25</label><span style="color:var(--muted)">run {_html.escape(run_name)}</span></div>
<div class="bar" id="nav"></div></header>
<main id="list"></main>
<script id="data" type="application/json">{data}</script>
<script>{SWEEP_JS}</script></body></html>
"""


def sweep_page_check(page_dir: Path, n_frames: int) -> dict:
    """Headless Chrome (throwaway profile): every frame section and image renders at both thresholds; no network URL."""
    import inbox_identity_page as ipage
    txt = (page_dir / "index.html").read_text(encoding="utf-8")
    res = {"network_urls": re.findall(r"https?://[^\s\"'<>]+", txt), "n_panel_files": len(list((page_dir / "panels").glob("*.jpg")))}
    prof = Path(tempfile.mkdtemp(prefix="sweep_"))
    p, wsu, bws = ipage._chrome((page_dir / "index.html").resolve().as_uri(), prof, ipage._free_port())
    c = None
    try:
        c = ipage._CDP(wsu)
        c.call("Runtime.enable")

        def loaded():
            for _ in range(480):
                try:
                    c.ev("document.querySelectorAll('img').forEach(i => { if (i.loading !== 'eager') { i.loading = 'eager'; const s = i.src; i.src = ''; i.src = s; } })")
                    if c.ev("!!window.__sweep && Array.from(document.images).every(i => i.complete)"):
                        return True
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.25)
            return False
        for t in ("0.25", "0.01"):
            c.ev(f"window.__sweep && window.__sweep.setTau('{t}')")
            ok = loaded()
            res[f"tau_{t}"] = {"loaded": ok, "n_sections": c.ev("document.querySelectorAll('section.frame').length"),
                               "n_images": c.ev("document.images.length"),
                               "n_images_ok": c.ev("Array.from(document.images).filter(i => i.complete && i.naturalWidth > 0).length"),
                               "src_tau_ok": c.ev(f"Array.from(document.querySelectorAll('img.pan')).every(i => i.getAttribute('src').endsWith('_{int(round(float(t) * 100)):03d}.jpg'))")}
    finally:
        if c:
            c.close()
        ipage._close_chrome(p, bws)
        shutil.rmtree(prof, ignore_errors=True)
    n_img = n_frames * (1 + 2 * len(SWEEP_PROMPTS))
    res["verdict"] = "PASS" if (not res["network_urls"] and res["n_panel_files"] == n_frames * (1 + 2 * len(SWEEP_PROMPTS) * len(SWEEP_TAUS))
                                and all(res[f"tau_{t}"]["loaded"] and res[f"tau_{t}"]["n_sections"] == n_frames
                                        and res[f"tau_{t}"]["n_images"] == n_img and res[f"tau_{t}"]["n_images_ok"] == n_img
                                        and res[f"tau_{t}"]["src_tau_ok"] for t in ("0.25", "0.01"))) else "FAIL"
    return res


# ============================================================================================ prompt GUI (user request, after amendment 4)
GUI_TOPK = 60
GUI_EPS_PX = 2.0                 # approxPolyDP epsilon at full resolution
GUI_W, GUI_H = 1600, 1200        # display frame size (full 2560 x 1920)
GUI_PAGE_VERSION = "inbox_sam3_prompt_gui_2026c_v1"
GUI_EXPORT_DIR = REPO / "cv" / "configs" / "inbox_sam3_prompt_gui_2026c"


def gui_units(M: dict, uv: np.ndarray, pi: int, tiled: bool, topk: int = GUI_TOPK) -> list[dict]:
    """The top-k units of one prompt by score: whole = single masks; tiled = cross-tile clusters formed once over all cached
    masks of the prompt (score order, mask IoU >= MERGE_IOU, the T1 rule at the cache floor). Per unit: score, area, the
    blind heads it covers (<= 15 px; union over members), and its outer contours simplified with approxPolyDP."""
    import cv2
    idx = np.flatnonzero(M["prompt"] == pi)
    if not len(idx):
        return []
    order = [int(k) for k in idx[np.argsort(-M["score"][idx], kind="stable")]]
    clusters = tile_clusters(order, M["tile"], cross_tile_neighbours(M, idx)) if tiled else [[k] for k in order]
    clusters = clusters[:topk]
    out = []
    for cl in clusters:
        D = dist_matrix(uv, [M["crops"][k] for k in cl], [tuple(int(b) for b in M["bbox"][k]) for k in cl]) if len(uv) else np.zeros((0, len(cl)))
        cov = [int(i) for i in np.flatnonzero((D.min(1) if D.size else np.zeros(0)) <= COVER_PX)]
        area = int(M["area"][cl[0]]) if len(cl) == 1 else union_area([M["crops"][k] for k in cl], [tuple(int(b) for b in M["bbox"][k]) for k in cl])
        polys = []
        for k in cl:
            crop = M["crops"][k]
            if crop.size == 0:
                continue
            cs, _ = cv2.findContours(crop.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            x0, y0 = int(M["bbox"][k][0]), int(M["bbox"][k][1])
            for c in cs:
                a = cv2.approxPolyDP(c, GUI_EPS_PX, True).reshape(-1, 2)
                if len(a) < 3:
                    continue
                polys.append([int(v) for xy in a for v in (xy[0] + x0, xy[1] + y0)])
        out.append({"s": round(float(M["score"][cl[0]]), 4), "a": area, "c": cov, "n": len(cl), "p": polys})
    return out


def phase_prompt_gui(run: Path, frames: pd.DataFrame, heads: pd.DataFrame, check: bool = True) -> dict:
    """Self-contained GUI from the cached sweep masks (no SAM 3 run): <run>/prompt_gui/index.html + gui_data.js + frames/."""
    import cv2
    sd, gd = run / "prompt_sweep", run / "prompt_gui"
    sel = pd.read_csv(sd / "sweep_frames.csv")
    if gd.exists():
        shutil.rmtree(gd)
    (gd / "frames").mkdir(parents=True)
    fpath = frames.set_index("frame_id")
    data = {"page_version": GUI_PAGE_VERSION, "run": run.name, "prompts": SWEEP_PROMPTS, "full_w": IMG_W, "full_h": IMG_H,
            "disp_w": GUI_W, "disp_h": GUI_H, "cover_px": COVER_PX, "topk": GUI_TOPK, "export_prefix": "inbox_sam3_prompt_gui_2026c_",
            "frames": []}
    blocks = [("ir", fid) for fid in sel.ir_frame] + [("colour", fid) for fid in sel.colour_frame if isinstance(fid, str)]
    for fi, (dom, fid) in enumerate(blocks):
        H = heads[heads.frame_id == fid].sort_values("click_id")
        uv = H[["u", "v"]].to_numpy(float)
        img = cv2.imread(fpath.at[fid, "path"], cv2.IMREAD_COLOR)
        name = f"frames/{fid}.jpg"
        cv2.imwrite(str(gd / name), cv2.resize(img, (GUI_W, GUI_H), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 85])
        fr = {"id": fid, "domain": dom, "time": str(fpath.at[fid, "frame_time"]), "img": name,
              "heads": [[round(float(u), 1), round(float(v), 1)] for u, v in uv], "units": {}}
        for var in ("whole", "tiled"):
            M = sweep_masks(run, fid, var)
            fr["units"][var] = [gui_units(M, uv, pi, var == "tiled") for pi in range(len(SWEEP_PROMPTS))]
        data["frames"].append(fr)
        print(f"  gui {fi + 1}/{len(blocks)} {fid}", flush=True)
    js = "window.GUI_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n"
    (gd / "gui_data.js").write_text(js, encoding="utf-8")
    (gd / "index.html").write_text(prompt_gui_html(run.name), encoding="utf-8")
    size = {"gui_data_js_bytes": (gd / "gui_data.js").stat().st_size,
            "frames_jpg_bytes": int(sum(p.stat().st_size for p in (gd / "frames").glob("*.jpg"))),
            "index_html_bytes": (gd / "index.html").stat().st_size,
            "n_units": int(sum(len(u) for f in data["frames"] for v in f["units"].values() for u in v)),
            "n_polygon_points": int(sum(len(p) // 2 for f in data["frames"] for v in f["units"].values() for u in v for x in u for p in x["p"]))}
    res = {"size": size, "n_frames": len(blocks)}
    if check:
        res["page_check"] = prompt_gui_check(gd, run)
        write_json(gd / "page_check.json", res["page_check"])
        print(f"prompt GUI check: {res['page_check']['verdict']}", flush=True)
    write_json(gd / "gui_meta.json", res)
    return res


PROMPT_GUI_JS = r"""
(function(){
const D = window.GUI_DATA, P = D.prompts, K = D.disp_w / D.full_w;
const KEY = D.page_version + '::' + D.run;
const LMIN = Math.log10(0.005);
const st = {dom: 'ir', fi: 0, pi: 0, variant: 'whole', grid: false, topk: 60, minScore: 0.005, fill: true, dots: true, hover: true,
            view: null, mouse: null, drag: null};
let notes = {};
try { const t = localStorage.getItem(KEY); if (t) notes = JSON.parse(t).notes || {}; } catch (e) {}
function saveNotes(){ try { localStorage.setItem(KEY, JSON.stringify({notes})); } catch (e) {} }
const $ = id => document.getElementById(id);
const frames = () => D.frames.filter(f => f.domain === st.dom);
const frame = () => frames()[st.fi];
const imgs = {};
function img(f){ if (!imgs[f.img]) { const im = new Image(); im.onload = () => draw(); im.src = f.img; imgs[f.img] = im; } return imgs[f.img]; }
function colour(r){ return 'hsl(' + ((r * 137.508) % 360).toFixed(1) + ',90%,55%)'; }
function shown(pi){ const u = frame().units[st.variant][pi] || []; return u.slice(0, st.topk).filter(x => x.s >= st.minScore); }
function counts(units, nh){
  const cov = new Array(nh).fill(0), choice = new Array(nh).fill(-1);
  units.forEach((u, j) => u.c.forEach(i => { cov[i]++; const c = choice[i];
    if (c < 0 || u.s > units[c].s || (u.s === units[c].s && u.a < units[c].a)) choice[i] = j; }));
  let excl = 0; for (let i = 0; i < nh; i++) if (choice[i] >= 0 && units[choice[i]].c.length === 1) excl++;
  return {masks: units.length, heads: nh, covered: cov.filter(x => x > 0).length, excl: excl,
          empty: units.filter(u => u.c.length === 0).length, merged: units.filter(u => u.c.length >= 2).length};
}
function capText(c){ return c.masks + ' masks · ' + c.covered + '/' + c.heads + ' heads covered · ' + c.excl + ' with an own exclusive mask · '
  + c.empty + ' empty · ' + c.merged + ' merged'; }
function paths(u){ return u.p.map(pl => { const p = new Path2D(); for (let i = 0; i < pl.length; i += 2) {
  const x = pl[i] * K, y = pl[i + 1] * K; if (i === 0) p.moveTo(x, y); else p.lineTo(x, y); } p.closePath(); return p; }); }
function render(ctx, w, h, view, pi, hoverPt){
  const f = frame(), im = img(f), us = shown(pi);
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#111'; ctx.fillRect(0, 0, w, h);
  ctx.setTransform(view.s, 0, 0, view.s, view.ox, view.oy);
  if (im.complete && im.naturalWidth) ctx.drawImage(im, 0, 0, D.disp_w, D.disp_h);
  let hit = null;
  us.forEach((u, r) => { const col = colour(r); const ps = paths(u);
    ps.forEach(p => { if (st.fill) { ctx.globalAlpha = 0.33; ctx.fillStyle = col; ctx.fill(p); ctx.globalAlpha = 1; }
      ctx.lineWidth = 2 / view.s; ctx.strokeStyle = col; ctx.stroke(p);
      if (hoverPt && ctx.isPointInPath(p, hoverPt[0], hoverPt[1])) hit = {u, r}; }); });
  if (st.dots) f.heads.forEach(hd => { ctx.beginPath(); ctx.arc(hd[0] * K, hd[1] * K, 5 / view.s, 0, 2 * Math.PI);
    ctx.fillStyle = '#fff'; ctx.fill(); ctx.lineWidth = 2 / view.s; ctx.strokeStyle = '#000'; ctx.stroke(); });
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  if (hit && st.hover && hoverPt) { const t = 'score ' + hit.u.s.toFixed(3) + ' · rank ' + (hit.r + 1) + ' · ' + hit.u.c.length + ' head(s)' + (hit.u.n > 1 ? ' · ' + hit.u.n + ' tiles merged' : '');
    ctx.font = '13px system-ui, sans-serif'; const tw = ctx.measureText(t).width;
    ctx.fillStyle = 'rgba(0,0,0,0.75)'; ctx.fillRect(hoverPt[0] + 12, hoverPt[1] + 8, tw + 10, 20);
    ctx.fillStyle = '#fff'; ctx.fillText(t, hoverPt[0] + 17, hoverPt[1] + 22); }
  return us.length;
}
function fit(w, h){ const s = Math.min(w / D.disp_w, h / D.disp_h); return {s, ox: (w - D.disp_w * s) / 2, oy: (h - D.disp_h * s) / 2}; }
let lastDrawn = 0;
function draw(){
  const f = frame(); if (!f) return;
  $('fsel').value = String(st.fi); $('psel').value = String(st.pi);
  $('title').textContent = (st.dom === 'ir' ? 'IR' : 'Colour') + ' frame ' + (st.fi + 1) + '/' + frames().length + ' · ' + f.id + ' · ' + f.time;
  $('single').classList.toggle('hidden', st.grid); $('gridv').classList.toggle('hidden', !st.grid);
  if (!st.grid) {
    const cv = $('cv'), w = cv.clientWidth, h = cv.clientHeight; if (cv.width !== w) cv.width = w; if (cv.height !== h) cv.height = h;
    if (!st.view) st.view = fit(w, h);
    lastDrawn = render(cv.getContext('2d'), w, h, st.view, st.pi, st.mouse);
    $('counts').textContent = capText(counts(shown(st.pi), f.heads.length));
    $('ptitle').textContent = P[st.pi];
  } else {
    let tot = 0;
    P.forEach((p, i) => { const c = document.getElementById('g' + i), w = c.clientWidth, h = c.clientHeight;
      if (c.width !== w) c.width = w; if (c.height !== h) c.height = h;
      tot += render(c.getContext('2d'), w, h, fit(w, h), i, null);
      document.getElementById('gc' + i).textContent = capText(counts(shown(i), f.heads.length)); });
    lastDrawn = tot; $('counts').textContent = 'grid: all prompts on this frame (click a panel to open it)';
  }
  const nk = f.id + '||' + P[st.pi]; $('note').value = (notes[nk] || {}).note || ''; $('notekey').textContent = 'note for ' + f.id + ' · ' + P[st.pi];
  $('topkv').textContent = st.topk; $('minv').textContent = st.minScore.toFixed(3);
  $('nnotes').textContent = Object.values(notes).filter(n => n.note).length + ' notes';
}
function setFrame(i){ const n = frames().length; st.fi = (i + n) % n; st.view = null; draw(); }
function setPrompt(i){ st.pi = (i + P.length) % P.length; draw(); }
function buildGrid(){ $('gridv').innerHTML = P.map((p, i) => '<figure class="gp" data-i="' + i + '"><canvas id="g' + i + '"></canvas><figcaption><b>' + p + '</b><br><span id="gc' + i + '"></span></figcaption></figure>').join('');
  document.querySelectorAll('.gp').forEach(el => el.addEventListener('click', () => { st.pi = +el.dataset.i; st.grid = false; $('gridb').checked = false; draw(); })); }
function init(){
  $('fsel').innerHTML = frames().map((f, i) => '<option value="' + i + '">' + (i + 1) + ' · ' + f.id.replace('CH07_', '') + '</option>').join('');
  $('psel').innerHTML = P.map((p, i) => '<option value="' + i + '">' + (i + 1) + ' · ' + p + '</option>').join('');
}
buildGrid(); init();
$('fsel').addEventListener('change', e => setFrame(+e.target.value));
$('psel').addEventListener('change', e => setPrompt(+e.target.value));
document.querySelectorAll('input[name=dom]').forEach(r => r.addEventListener('change', e => { st.dom = e.target.value; st.fi = 0; st.view = null; init(); draw(); }));
document.querySelectorAll('input[name=var]').forEach(r => r.addEventListener('change', e => { st.variant = e.target.value; draw(); }));
$('topk').addEventListener('input', e => { st.topk = +e.target.value; draw(); });
$('mins').addEventListener('input', e => { st.minScore = Math.pow(10, LMIN + (+e.target.value / 1000) * (0 - LMIN)); draw(); });
$('fillb').addEventListener('change', e => { st.fill = e.target.checked; draw(); });
$('dotsb').addEventListener('change', e => { st.dots = e.target.checked; draw(); });
$('hovb').addEventListener('change', e => { st.hover = e.target.checked; draw(); });
$('gridb').addEventListener('change', e => { st.grid = e.target.checked; draw(); });
$('resetv').addEventListener('click', () => { st.view = null; draw(); });
$('note').addEventListener('input', e => { const f = frame(), nk = f.id + '||' + P[st.pi];
  notes[nk] = {frame_id: f.id, domain: f.domain, prompt: P[st.pi], note: e.target.value, updated_at: new Date().toISOString(),
               view: st.variant + ', top-K ' + st.topk + ', min score ' + st.minScore.toFixed(3)}; saveNotes(); $('nnotes').textContent = Object.values(notes).filter(n => n.note).length + ' notes'; });
const cv = $('cv');
cv.addEventListener('wheel', e => { e.preventDefault(); const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
  const z = Math.exp(-e.deltaY * 0.0015), v = st.view, s2 = Math.min(Math.max(v.s * z, 0.05), 20);
  v.ox = mx - (mx - v.ox) * s2 / v.s; v.oy = my - (my - v.oy) * s2 / v.s; v.s = s2; draw(); }, {passive: false});
cv.addEventListener('mousedown', e => { st.drag = [e.clientX, e.clientY, st.view.ox, st.view.oy]; });
window.addEventListener('mouseup', () => { st.drag = null; });
cv.addEventListener('mousemove', e => { const r = cv.getBoundingClientRect(); st.mouse = [e.clientX - r.left, e.clientY - r.top];
  if (st.drag) { st.view.ox = st.drag[2] + e.clientX - st.drag[0]; st.view.oy = st.drag[3] + e.clientY - st.drag[1]; } draw(); });
cv.addEventListener('mouseleave', () => { st.mouse = null; draw(); });
window.addEventListener('resize', () => { st.view = null; draw(); });
document.addEventListener('keydown', e => { if (['TEXTAREA', 'INPUT', 'SELECT'].includes(e.target.tagName) && e.target.type !== 'range' && e.target.type !== 'checkbox' && e.target.type !== 'radio') return;
  if (e.key === 'ArrowLeft') { setFrame(st.fi - 1); e.preventDefault(); } else if (e.key === 'ArrowRight') { setFrame(st.fi + 1); e.preventDefault(); }
  else if (e.key === 'ArrowUp') { setPrompt(st.pi - 1); e.preventDefault(); } else if (e.key === 'ArrowDown') { setPrompt(st.pi + 1); e.preventDefault(); }
  else if (e.key === 'g' || e.key === 'G') { st.grid = !st.grid; $('gridb').checked = st.grid; draw(); }
  else if (e.key === 'v' || e.key === 'V') { st.variant = st.variant === 'whole' ? 'tiled' : 'whole'; document.querySelector('input[name=var][value=' + st.variant + ']').checked = true; draw(); } });
function rows(){ return Object.values(notes).filter(n => n.note).sort((a, b) => (a.frame_id + a.prompt).localeCompare(b.frame_id + b.prompt)); }
function csvCell(v){ v = String(v == null ? '' : v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
function exportCSV(){ const cols = ['frame_id', 'domain', 'prompt', 'note', 'view', 'updated_at'];
  return [cols.join(',')].concat(rows().map(r => cols.map(c => csvCell(r[c])).join(','))).join('\n') + '\n'; }
function exportJSON(){ return {page_version: D.page_version, run: D.run, exported_at: new Date().toISOString(), prompts: P, notes: rows()}; }
function stamp(){ const d = new Date(), p = n => String(n).padStart(2, '0'); return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + '_' + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds()); }
function download(name, text, type){ const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {type})); a.download = name;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
$('ej').addEventListener('click', () => download(D.export_prefix + stamp() + '.json', JSON.stringify(exportJSON(), null, 2), 'application/json'));
$('ec').addEventListener('click', () => download(D.export_prefix + stamp() + '.csv', exportCSV(), 'text/csv'));
$('ij').addEventListener('change', e => { const f = e.target.files[0]; if (!f) return; f.text().then(t => { (JSON.parse(t).notes || []).forEach(n => { notes[n.frame_id + '||' + n.prompt] = n; }); saveNotes(); draw(); }); });
draw();
window.__gui = {st, draw, setFrame, setPrompt, drawn: () => lastDrawn, counts: (pi) => counts(shown(pi), frame().heads.length), exportCSV, exportJSON, key: KEY,
  setTopK: k => { st.topk = k; $('topk').value = k; draw(); }, setMinSlider: x => { $('mins').value = x; $('mins').dispatchEvent(new Event('input')); },
  frameId: () => frame().id, imagesReady: () => Object.values(imgs).every(i => i.complete && i.naturalWidth > 0)};
})();
"""


def prompt_gui_html(run_name: str) -> str:
    import html as _html
    css = PAGE_CSS + """
.wrap{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:12px;padding:10px 16px}
@media (max-width:1000px){.wrap{grid-template-columns:minmax(0,1fr)}}
#cv{width:100%;height:calc(100vh - 190px);min-height:420px;background:#111;border-radius:6px;cursor:grab;display:block}
#gridv{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px}
.gp canvas{width:100%;aspect-ratio:4/3;background:#111;border-radius:4px;display:block;cursor:pointer}.gp figcaption{font-size:12px}
.side{display:flex;flex-direction:column;gap:8px;font-size:14px}.side label{display:flex;gap:6px;align-items:center}
.side input[type=range]{width:100%}.side select{width:100%;font:inherit}.side textarea{min-height:110px}
#counts{font-weight:600}#title{font-size:15px;font-weight:600;margin:0 0 6px}.kbd{color:var(--muted);font-size:12.5px}
"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>In-box prompt explorer</title><style>{css}</style></head><body>
<header><h1>In-box CH07 — SAM 3 prompt explorer (exploratory)</h1>
<p>SAM 3 text-prompt masks (top 60 by score per frame × prompt × variant, from the cached sweep) on 10 IR and 10 colour frames. White dots =
your blind head clicks. The counts are mask ↔ click counts only (a mask covers a click within 15 px); nobody has judged these images. Notes
are kept in this browser; Export to <code>cv/configs/inbox_sam3_prompt_gui_2026c/</code>.</p></header>
<div class="wrap"><div><div id="title"></div>
<div id="single"><canvas id="cv"></canvas><div id="ptitle" style="font-weight:600;margin-top:4px"></div></div>
<div id="gridv" class="hidden"></div></div>
<div class="side">
<div><label><input type="radio" name="dom" value="ir" checked> IR</label><label><input type="radio" name="dom" value="colour"> colour</label></div>
<label>frame <select id="fsel"></select></label><label>prompt <select id="psel"></select></label>
<div><label><input type="radio" name="var" value="whole" checked> whole frame</label><label><input type="radio" name="var" value="tiled"> 2 × 2 tiles</label></div>
<label><input type="checkbox" id="gridb"> grid: all 10 prompts</label>
<div>top-K masks by score: <b id="topkv"></b><input type="range" id="topk" min="1" max="60" value="60"></div>
<div>min score (log): <b id="minv"></b><input type="range" id="mins" min="0" max="1000" value="0"></div>
<label><input type="checkbox" id="fillb" checked> fill masks (off = outline)</label>
<label><input type="checkbox" id="dotsb" checked> show my head clicks</label>
<label><input type="checkbox" id="hovb" checked> score label on hover</label>
<button id="resetv" type="button">reset zoom</button>
<div id="counts"></div>
<div id="notekey" class="kbd"></div><textarea id="note" placeholder="your note for this frame × prompt"></textarea>
<div class="bar"><span id="nnotes"></span><button id="ej" type="button">Export JSON</button><button id="ec" type="button">Export CSV</button>
<label class="btn">Import JSON<input id="ij" type="file" accept=".json,application/json" class="hidden"></label></div>
<div class="kbd">keys: ← / → frame · ↑ / ↓ prompt · G grid · V whole / tiles · wheel = zoom · drag = pan</div>
<div class="kbd">run {_html.escape(run_name)}</div>
</div></div>
<script src="gui_data.js"></script>
<script>{PROMPT_GUI_JS}</script></body></html>
"""


def prompt_gui_check(gd: Path, run: Path) -> dict:
    """Headless Chrome (throwaway profile): loads; frame / prompt / variant switching; both sliders change the drawn count;
    a note persists across a reload; the live counts equal the sweep's Python counts where the sets coincide."""
    import inbox_identity_page as ipage
    txt = (gd / "index.html").read_text(encoding="utf-8") + (gd / "gui_data.js").read_text(encoding="utf-8")[:0]
    res = {"network_urls": re.findall(r"https?://[^\s\"'<>]+", (gd / "index.html").read_text(encoding="utf-8"))
           + re.findall(r"https?://[^\s\"'<>]+", (gd / "gui_data.js").read_text(encoding="utf-8"))}
    del txt
    prof = Path(tempfile.mkdtemp(prefix="pgui_"))
    p, wsu, bws = ipage._chrome((gd / "index.html").resolve().as_uri(), prof, ipage._free_port())
    c = None
    try:
        c = ipage._CDP(wsu)
        c.call("Runtime.enable")

        def ready():
            for _ in range(240):
                try:
                    if c.ev("!!window.__gui && window.__gui.imagesReady()"):
                        return True
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.25)
            return False

        def key(k):
            c.ev(f"document.dispatchEvent(new KeyboardEvent('keydown', {{key: '{k}', bubbles: true}}))")
        res["loaded"] = ready()
        s0 = c.ev("JSON.stringify([window.__gui.frameId(), window.__gui.st.pi, window.__gui.st.variant])")
        key("ArrowRight")
        f1 = c.ev("window.__gui.frameId()")
        key("ArrowDown")
        p1 = c.ev("window.__gui.st.pi")
        key("v")
        v1 = c.ev("window.__gui.st.variant")
        res["switching"] = {"start": json.loads(s0), "after_right_frame": f1, "after_down_prompt": p1, "after_v_variant": v1,
                            "ok": f1 != json.loads(s0)[0] and p1 == 1 and v1 == "tiled"}
        key("v")
        c.ev("window.__gui.setPrompt(0)")                                # "rat", whole: many masks
        n60 = c.ev("window.__gui.drawn()")
        c.ev("window.__gui.setTopK(5)")
        n5 = c.ev("window.__gui.drawn()")
        c.ev("window.__gui.setTopK(60)")
        c.ev("window.__gui.setMinSlider(700)")
        nmin = c.ev("window.__gui.drawn()")
        c.ev("window.__gui.setMinSlider(0)")
        res["sliders"] = {"topk60": n60, "topk5": n5, "min_slider_700": nmin, "min_score_700": c.ev("Math.pow(10, Math.log10(0.005) * (1 - 0.7))"),
                          "ok": n5 == min(5, n60) and n60 > 5 and nmin < n60}
        c.ev("document.getElementById('gridb').click()")
        res["grid_panels"] = c.ev("document.querySelectorAll('#gridv canvas').length")
        res["grid_drawn"] = c.ev("window.__gui.drawn()")
        c.ev("document.getElementById('gridb').click()")
        # live counts vs the sweep's Python counts (whole variant, tau 0.25, where <= 60 masks pass)
        sm = pd.read_csv(run / "prompt_sweep" / "sweep_frame_metrics.csv")
        sm = sm[(sm.variant == "whole") & (sm.tau == 0.25)]
        tau_slider = 1000 * (np.log10(0.25) - np.log10(0.005)) / (0 - np.log10(0.005))
        c.ev(f"document.getElementById('mins').value = {tau_slider:.6f}; document.getElementById('mins').dispatchEvent(new Event('input'))")
        min_used = c.ev("window.__gui.st.minScore")
        agree, tested = 0, 0
        mism = []
        for dom in ("ir", "colour"):
            c.ev(f"document.querySelector('input[name=dom][value={dom}]').click()")
            nfr = c.ev("window.GUI_DATA.frames.filter(f => f.domain === window.__gui.st.dom).length")
            for fi in range(nfr):
                c.ev(f"window.__gui.setFrame({fi})")
                fid = c.ev("window.__gui.frameId()")
                for pi, pk in enumerate(SWEEP_PROMPTS):
                    r = sm[(sm.frame_id == fid) & (sm.prompt == pk)]
                    if r.empty or int(r.n_masks.iloc[0]) > GUI_TOPK:
                        continue
                    js = c.ev(f"window.__gui.counts({pi})")
                    r = r.iloc[0]
                    py = {"masks": int(r.n_masks), "covered": int(r.n_heads - r.missed), "excl": int(r.excl), "empty": int(r["empty"]),
                          "merged": int(r.merged)}
                    tested += 1
                    if all(js[k] == v for k, v in py.items()):
                        agree += 1
                    else:
                        mism.append({"frame": fid, "prompt": pk, "js": js, "py": py})
        res["counts_vs_python_whole_tau025"] = {"min_score_used": min_used, "tested": tested, "agree": agree, "mismatches": mism[:5]}
        c.ev("document.querySelector('input[name=dom][value=ir]').click()")
        c.ev("window.__gui.setFrame(2); window.__gui.setPrompt(3)")
        c.ev("(() => { const t = document.getElementById('note'); t.value = 'check note'; t.dispatchEvent(new Event('input')); })()")
        fid2 = c.ev("window.__gui.frameId()")
        c.call("Page.reload")
        time.sleep(1.5)
        ready()
        res["note_after_reload"] = c.ev(f"(JSON.parse(localStorage.getItem(window.__gui.key)).notes['{fid2}||{SWEEP_PROMPTS[3]}'] || {{}}).note")
        res["export_csv_lines"] = c.ev("window.__gui.exportCSV().trim().split('\\n').length")
        c.ev("localStorage.clear()")
    finally:
        if c:
            c.close()
        ipage._close_chrome(p, bws)
        shutil.rmtree(prof, ignore_errors=True)
    cv = res.get("counts_vs_python_whole_tau025", {})
    res["verdict"] = "PASS" if (res.get("loaded") and res["switching"]["ok"] and res["sliders"]["ok"] and res.get("grid_panels") == len(SWEEP_PROMPTS)
                                and res.get("note_after_reload") == "check note" and res.get("export_csv_lines") == 2
                                and cv.get("tested", 0) > 0 and cv.get("agree") == cv.get("tested") and not res["network_urls"]) else "FAIL"
    return res


# ============================================================================================ report
def f3(x, d=3):
    return "–" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{d}f}"


def fci(p, c, d=3):
    if not c or c[0] is None or not np.isfinite(c[0]):
        return f3(p, d)
    return f"{f3(p, d)} [{f3(c[0], d)}, {f3(c[1], d)}]"


def pct(p, c=None, d=1):
    if c is None or not c or c[0] is None or not np.isfinite(c[0]):
        return "–" if p is None or not np.isfinite(p) else f"{100 * p:.{d}f} %"
    return f"{100 * p:.{d}f} % [{100 * c[0]:.{d}f}, {100 * c[1]:.{d}f}]"


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        out.append("| " + " | ".join(str(v) for v in r) + " |")
    return "\n".join(out)


def _lohi(d: dict, key: str):
    lo, hi = d.get(f"{key}_lo"), d.get(f"{key}_hi")
    if lo is None or hi is None or (isinstance(lo, float) and not np.isfinite(lo)):
        return d.get(key) if isinstance(d.get(key), (list, tuple)) else None
    return (lo, hi)


def write_report(run: Path) -> Path:
    meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
    data = json.loads((run / "data.json").read_text(encoding="utf-8"))
    t1 = json.loads((run / "t1_result.json").read_text(encoding="utf-8"))
    t2 = json.loads((run / "t2_result.json").read_text(encoding="utf-8"))
    t3 = json.loads((run / "t3_result.json").read_text(encoding="utf-8"))
    rv = json.loads((run / "mask_review_meta.json").read_text(encoding="utf-8"))
    pc = json.loads((run / "mask_review_page_check.json").read_text(encoding="utf-8")) if (run / "mask_review_page_check.json").exists() else {}
    groups = pd.read_csv(run / "groups.csv")
    pairs = pd.read_csv(run / "group_pairs.csv")
    dec = pd.read_csv(run / "t3_decisions.csv")
    t3r = pd.read_csv(run / "t3_results.csv")
    frames = pd.read_csv(run / "frames.csv")
    sh = pd.read_csv(run / "t3_shuffled.csv") if (run / "t3_shuffled.csv").exists() else pd.DataFrame()
    rel = run.as_posix()
    ch = t1["choice"]
    ti, tib = t1["test_ir"]
    s2 = {(r["variant"], r["split"]): r for r in t2["summary"]}
    pos, neg = s2.get(("pos", "test"), {}), s2.get(("neg", "test"), {})
    prim = dec[(dec.domain == "ir") & (dec.role == "primary") & (dec.scheme == "LOGO")].to_dict("records")
    lodo = dec[(dec.domain == "ir") & (dec.role == "primary") & (dec.scheme == "LODO")].to_dict("records")
    alt = t3.get("group_alt") or {}

    def yn(b):
        return "**YES**" if b else "**NO**"
    L = [f"# In-box CH07: SAM 3 text-prompt detection, SAM 3 point-prompt masks and a frozen DINOv3 identity probe ({COHORT})", "",
         f"Driver `cv/cv_field/inbox_sam3_dino_test.py`; plan `{PLAN}` (approved by the user 2026-10-11). Amendment 1 = the Codex "
         "review *Yolo_identity*; amendment 2 = implementation details; amendment 3 = a grouping sensitivity. All three were written "
         f"before any T1–T3 result. Run `{rel}` (made {meta['made']}, commit `{meta['git_commit']}`). Truth = the user's **blind** head "
         "clicks. The agent never judged an image.", "",
         "**Scope of the T1 / T2 claims.** A head click proves only that a mask covers that head point. Until the user has scored the "
         "blind mask review (below), every T1 / T2 number here is **head-point exclusivity**: one mask per head point, no mask "
         "spanning two head points, no mask on no head point. None of them is a claim that SAM 3 gives one-whole-rat masks or "
         "usable single-rat boxes.", "", "## Headline", ""]
    L += [f"- **T1 (text prompt; the pre-named primary is the chosen prompt on test IR frames).** The dev choice is {ch['prompt']} "
          f"\"{ch['text']}\" at τ = {ch['tau']:g} (dev IR F1 {f3(ch['dev_F1'])}). On test IR ({ti['n_frames']} frames, {ti['n_heads']} "
          f"heads, {len(t1['test_groups'])} groups):",
          f"  - head-point exclusivity X = {pct(ti['X'], tib.get('X'))}; F1 = {fci(ti['F1'], tib.get('F1'))};",
          f"  - recall {pct(ti['R'], tib.get('R'))}, precision {pct(ti['P'], tib.get('P'))};",
          f"  - merged-mask rate {pct(ti['merged_rate'], tib.get('merged_rate'))}, empty-mask rate "
          f"{pct(ti['empty_rate'], tib.get('empty_rate'))};",
          f"  - count error {fci(ti['count_err_mean'], tib.get('count_err_mean'), 2)} masks per frame."]
    if pos:
        nd = t2.get("neg_minus_pos_X", {})
        L += [f"- **T2 (head point → mask, test IR, {pos['n_heads']} heads).**",
              f"  - Positive point only (the pre-named primary): exclusivity {pct(pos['X'], pos.get('X_ci'))}, merge "
              f"{pct(pos['merge'], pos.get('merge_ci'))}, own head missed {pct(pos['miss_own'], pos.get('miss_own_ci'))}.",
              f"  - With negative points at the other heads: exclusivity {pct(neg.get('X', np.nan), neg.get('X_ci'))}, merge "
              f"{pct(neg.get('merge', np.nan), neg.get('merge_ci'))}, own head missed {pct(neg.get('miss_own', np.nan), neg.get('miss_own_ci'))}.",
              f"  - Difference, negative − positive: {pct(nd.get('point', np.nan), nd.get('ci'))}. The negative variant is partly "
              "self-validating: its negative points are the very heads the metric checks."]
    if prim:
        p = prim[0]
        L += [f"- **T3 (frozen DINOv3 head crop, IR; primary = CLS + logistic regression, 4-in crop, leave-one-group-out, {p['n']} "
              f"clicks, {p['n_groups']} groups).**",
              f"  - Accuracy {pct(p['acc'], _lohi(p, 'acc_ci'))}; chance 20 %.",
              f"  - Best control: {p['best_control']}, {pct(p['best_control_acc'])}.",
              f"  - Δ vs chance {pct(p['d_chance'], _lohi(p, 'd_chance_ci'))}; Δ vs best control "
              f"{pct(p['d_ctrl'], _lohi(p, 'd_ctrl_ci'))}.",
              f"  - \"DINOv3 carries identity\" (engineering gate): {yn(p['carries_identity'])}; \"a gain of ≥ 15 pp is established\": "
              f"{yn(p['gain_15pp_established'])}."]
    if lodo:
        p = lodo[0]
        L += [f"- **T3 cross-day (leave-one-day-out: train 09-09 + 09-10, test 09-11, {p['n']} clicks).**",
              f"  - Accuracy {pct(p['acc'], _lohi(p, 'acc_ci'))}; best control {p['best_control']}, {pct(p['best_control_acc'])}.",
              f"  - Δ vs best control {pct(p['d_ctrl'], _lohi(p, 'd_ctrl_ci'))}.",
              f"  - Carries identity across days: {yn(p['carries_identity'])}."]
    L += [f"- **Blind mask review page for the user:** `{rel}/mask_review/index.html`. It holds {rv['n_items']} masks with method and "
          "score hidden; exports go to `cv/configs/inbox_sam3_mask_review_2026c/`. The agent does not score it.", ""]
    if prim and pos:
        p = prim[0]
        L += ["## Reading (what these numbers do and do not say)", "",
              f"- **T1:** SAM 3 text prompts do not find the in-box rats zero-shot on whole IR frames. The best dev setting reaches F1 "
              f"{f3(ch['dev_F1'], 2)} at the lowest τ, and on test only {pct(ti['X'])} of the head points get a mask of their own.",
              f"  - Tiling raises head coverage to about {pct(t1['tiled_test_ir'][0]['X'], d=0)}, at the cost of about "
              f"{t1['tiled_test_ir'][0]['count_err_mean']:.0f} surplus masks per frame (descriptive).",
              f"- **T2:** one head click gives a mask on that head every time ({pct(1 - pos['miss_own'], d=0)}), and the mask rarely "
              f"spans a second head point ({pct(pos['merge'])}).",
              f"  - The masks are numerically head-sized (median long side {pos['box_long_median']:,.0f} px).",
              "  - Whether they are usable single-rat masks or boxes waits for the user's blind review.",
              f"- **T3:** frozen DINOv3 embeddings of 4-in IR head crops separate the five rats well above chance and above every control "
              f"when whole still episodes are held out: {pct(p['acc'])} vs {pct(p['best_control_acc'])} for the best control.",
              "  - They do not do so when a whole day is held out: the cross-day difference vs the best control has a CI that "
              "includes 0.",
              "  - So the identity signal is shown within the two click days, not as a stable cross-day IR identity.",
              "  - Body-scale (16-in) crops carry none.", ""]
    # data
    L += ["## Data and units", "",
          f"- **Clicks:** `{CLICKS_CSV.relative_to(REPO).as_posix()}` (sha256 `{data['clicks_sha256'][:16]}…`).",
          f"  - Blind record = `before_reveal` true, not legacy, with `verdict_first` (the `first_*` columns): {data['n_blind']} clicks. "
          f"The {data['n_after_reveal_unused']} clicks made after a reveal are not used.",
          f"  - Frames without any blind click are dropped: {', '.join(data['dropped_frames']) or 'none'}.",
          f"  - Unusable segment, from the user's composition statement: {', '.join(data['unusable_segments']) or 'none'}.",
          f"- **Frames and heads:** {data['n_frames']} frames ({data['n_ir_frames']} IR, {data['n_colour_frames']} colour) with "
          f"{data['n_heads']} blind heads, all CH07 (house_2). The user states that every clicked frame is complete: every rat in the "
          "house was clicked.",
          f"- **Scale:** {data['px_per_in']:.2f} px/in, from the clicks run's proper similarity fit. That gives:",
          f"  - T3 crop 4 in = {meta['dino']['sides_px']['s4in']} px and 16 in = {meta['dino']['sides_px']['s16in']} px;",
          f"  - head disc 1.5 in = {meta['dino']['disc_radius_px']:.1f} px; pile link 6 in = {data['pile_link_px']:.0f} px.",
          "  - One scale cannot convert piles at different heights, so mask areas are given in px only (amendment 1).", ""]
    # groups
    gtab = groups.groupby("group").agg(segments=("segment_id", lambda x: ", ".join(s.split("_", 1)[1] for s in x)),
                                       group_alt=("group_alt", "first"), day=("day", "first"), split=("split", "first")).reset_index()
    nfr = frames.groupby("group").agg(ir_frames=("domain", lambda x: int((x == "ir").sum())),
                                      colour_frames=("domain", lambda x: int((x == "colour").sum())), heads=("n_heads", "sum")).reset_index()
    gtab = gtab.merge(nfr, on="group", how="left")
    pj = pairs.copy()
    pj["pair"] = pj.seg_a.str[5:] + " → " + pj.seg_b.str[5:]
    pj["gap_min"] = (pj.gap_s / 60).round(1)
    pj["min still share (all s)"] = pj.min_still_share.map(lambda x: f3(x, 2))
    pj["no IMU"] = pj.animals_without_imu.fillna("")
    L += ["## Still-episode groups (amendment 1 item 2, amendment 3)", "",
          "- **Join rule:** two consecutive usable segments are one group when both hold over the interval from the last frame of "
          "the earlier segment to the colour frame of the later one:",
          "  - the WISER house_2 roster (`box_occupancy_1s.csv.gz`) is the same in every second;",
          "  - every roster animal's head IMU is ok and still in ≥ 90 % of those seconds (a missing or failed IMU counts as not "
          "still).",
          f"- **Result:** **{int(pairs.joined.sum())} of {len(pairs)} pairs joined**, so each of the {groups.group.nunique()} usable "
          "segments is its own group.",
          f"- **Sensitivity grouping `group_alt` (amendment 3):** animals with no ok IMU second are left out of the rule. It joins "
          f"{int(pairs.joined_alt.sum())} pairs, giving {groups.group_alt.nunique()} groups: the 09-11 14:09 → 14:17 → 14:43 "
          "segments, where SF12's IMU is absent all afternoon.", "",
          md_table(gtab[["group", "segments", "group_alt", "day", "split", "ir_frames", "colour_frames", "heads"]]), "",
          md_table(pj[["pair", "gap_min", "roster_unchanged", "min still share (all s)", "no IMU", "joined", "joined_alt"]]), "",
          f"- **dev** = the groups holding the 5 earliest usable segments ({', '.join(sorted(groups[groups.split == 'dev'].group.unique()))}).",
          f"- **test** = the other {groups[groups.split == 'test'].group.nunique()} groups.",
          "- T3 uses all groups, leave-one-group-out.", ""]
    # T1
    L += ["## T1 — SAM 3 text-prompt detection", "",
          f"- **Model:** SAM3SemanticPredictor (ultralytics {meta['versions']['ultralytics']}), imgsz 1008 set explicitly, score floor "
          f"{SCORE_FLOOR}, within-image NMS {meta['t1gpu'].get('nms_iou')}, {meta['t1gpu'].get('precision')} on "
          f"{meta['t1gpu'].get('device')}.",
          "- **Prompts:** the image features are computed once per frame (or tile), and the four prompts are applied on them.",
          "- **Cache:** raw masks (row-major RLE in bbox crops) in `sam3_t1/whole/` and `sam3_t1/tiled/`.", "",
          f"**Choice on dev IR** (pooled F1; ties → higher τ, then the lower prompt number): {ch['prompt']} \"{ch['text']}\", "
          f"τ = {ch['tau']:g}.", "",
          "Each prompt at its own dev-best τ, on test IR. This is descriptive; only the chosen prompt is the pre-named primary.", ""]
    rows = []
    for pk_, v in t1["per_prompt"].items():
        m, b = v["test"]
        rows.append({"prompt": f"{pk_} \"{PROMPTS[pk_]}\"", "τ (dev)": f"{v['tau']:g}", "dev F1": f3(v["dev_F1"]),
                     "test X [95 % CI]": pct(m["X"], b.get("X")), "test F1 [95 % CI]": fci(m["F1"], b.get("F1")), "P": pct(m["P"]),
                     "R": pct(m["R"]), "merged": pct(m["merged_rate"]), "empty": pct(m["empty_rate"]),
                     "masks / heads": f"{m['n_masks']} / {m['n_heads']}", "count err": f3(m["count_err_mean"], 2)})
    L += [md_table(pd.DataFrame(rows)), ""]
    dv = t1["dev_ir"][0]
    if ch["tau"] <= min(TAUS):
        L += [f"- **τ at the grid floor:** the chosen τ = {ch['tau']:g} is the lowest grid value and equals the cache's score floor, so "
              "no lower τ could be evaluated."]
    L += [f"- **Chosen setting on dev IR** (reference): X {pct(dv['X'])}, F1 {f3(dv['F1'])}, P {pct(dv['P'])}, R {pct(dv['R'])}."]
    ga = t1.get("test_ir_group_alt_ci", {})
    L += [f"- **Resampling `group_alt`** ({t1.get('n_test_groups_alt')} test groups): X CI {pct(ti['X'], ga.get('X'))}, F1 CI "
          f"{fci(ti['F1'], ga.get('F1'))}."]
    if t1.get("tiled_test_ir"):
        tt, ttb = t1["tiled_test_ir"]
        ct_ = t1["choice_tiled"]
        ta, tab = t1["tiled_at_primary_choice"]
        L += ["- **Tiled sensitivity** (2 × 2 tiles of 1344 × 1008 px, cross-tile merge at mask IoU ≥ 0.5):",
              f"  - its own dev choice, {ct_['prompt']} τ = {ct_['tau']:g}: test IR X {pct(tt['X'], ttb.get('X'))}, F1 "
              f"{fci(tt['F1'], ttb.get('F1'))};",
              f"  - at the whole-frame choice: X {pct(ta['X'], tab.get('X'))}, F1 {fci(ta['F1'], tab.get('F1'))}."]
    tc = t1["test_colour"][0]
    L += [f"- **Colour frames** (reported separately, never pooled): the chosen setting on {tc['n_frames']} test colour frames gives "
          f"X {pct(tc['X'])}, F1 {f3(tc['F1'])}, P {pct(tc['P'])}, R {pct(tc['R'])}.", ""]
    if t1.get("by_pile"):
        bp = pd.DataFrame(t1["by_pile"])
        L += ["By pile size of the head (test IR, chosen setting; descriptive):", "",
              md_table(bp.assign(X=bp.X.map(pct), R=bp.R.map(pct), covered=bp.covered.map(pct))), ""]
    L += ["Further tables in the run folder:",
          "- the full sweep (every variant × prompt × τ × domain × split): `t1_sweep.csv`;",
          "- per frame: `t1_frame_metrics.csv.gz`; per head: `t1_head_detail.csv.gz`.", ""]
    # T2
    L += ["## T2 — SAM 3 point-prompt masks from the head clicks", "",
          f"- **Point prompts are exposed for SAM 3** in ultralytics {meta['versions']['ultralytics']}: `SAM3Predictor` (the "
          "interactive predictor, a `SAM2Predictor` subclass) takes `points` / `labels`. The SAM 2.1 fallback was therefore not "
          "triggered.",
          "- **Build workaround:** the builder passes `compile=False`, which the ViT trunk treats as a compile mode (`is not None`); "
          "that call fails without Triton. The model is built with `compile=None` instead, which changes neither the weights nor "
          "the outputs.",
          "- **Settings:** `multimask_output` False (the predictor default) and the default mask threshold.",
          "- **Cache:** raw masks in `sam3_t2/`.", ""]
    rows = []
    for (var, spl), r in sorted(s2.items(), key=lambda x: (x[0][1], x[0][0])):
        rows.append({"variant": "positive point" if var == "pos" else "+ negative points", "split": spl, "heads": r["n_heads"],
                     "exclusive": pct(r["X"], r.get("X_ci")), "merge": pct(r["merge"], r.get("merge_ci")),
                     "own head missed": pct(r["miss_own"], r.get("miss_own_ci")),
                     "area px median [p25, p75]": f"{r['area_median']:,.0f} [{r['area_p25']:,.0f}, {r['area_p75']:,.0f}]",
                     "box long side px (median)": f"{r['box_long_median']:,.0f}", "box aspect (median)": f3(r["box_aspect_median"], 2),
                     "pair IoU median": f3(r["pair_iou_median"]), "pairs IoU > 0.1": pct(r["pair_iou_gt_0_1"]),
                     "pairs IoU > 0.5": pct(r["pair_iou_gt_0_5"])})
    L += [md_table(pd.DataFrame(rows)), ""]
    if pos:
        L += [f"- **Box size (numerical, px):** the median box long side is {pos['box_long_median']:,.0f} px and the 95th percentile "
              f"{pos['box_long_p95']:,.0f} px (positive point, test). For orientation only, an 8-in rat body spans about "
              f"{8 * data['px_per_in']:,.0f} px at the house-fit scale; animals higher in a pile sit nearer the camera and appear larger, "
              "not smaller. So the masks are numerically head-sized rather than body-sized. Whether a mask covers a whole rat is what "
              "the user's blind review decides; this number does not."]
    ta2 = t2.get("test_group_alt", {})
    if ta2:
        L += [f"- **Resampling `group_alt`:** positive exclusivity CI {pct(ta2['pos']['X'], ta2['pos']['X_ci'])}; negative "
              f"{pct(ta2['neg']['X'], ta2['neg']['X_ci'])}."]
    if t2.get("by_pile"):
        bp = pd.DataFrame(t2["by_pile"])
        L += ["", "By pile size (test; descriptive):", "", md_table(bp.assign(X=bp.X.map(pct), merge=bp["merge"].map(pct), miss_own=bp.miss_own.map(pct)))]
    L += ["", "Further tables in the run folder:",
          "- per head: `t2_heads.csv` (areas, boxes, predicted mask score);",
          "- pairwise IoU: `t2_pair_iou.csv`.", ""]
    # T3
    L += ["## T3 — frozen DINOv3 identity probe (IR)", "",
          f"- **Model:** DINOv3 ViT-B/16 (`{meta['dino']['checkpoint']}`, local hub copy).",
          "- **Crops:** centred on the blind click, clipped to the frame and padded with the frame's median grey, resized to 224 "
          "(INTER_AREA), ImageNet normalisation.",
          "- **Embeddings:** CLS = `x_norm_clstoken`; mean-patch = the mean of `x_norm_patchtokens`. Cached in "
          "`t3_embeddings.npz` (units in `t3_units.csv`).", "",
          "### Decision table (amendment 1 item 3)", ""]
    dd = dec[dec.domain == "ir"].copy()
    dd["o"] = dd.role.map({"primary": 0, "secondary": 1, "sensitivity (16-in crop)": 2})
    dd = dd.sort_values(["o", "scheme", "embedding", "classifier"], ascending=[True, False, True, True])
    rows = []
    for r in dd.to_dict("records"):
        rows.append({"role": r["role"], "scheme": r["scheme"], "crop": "4 in" if r["crop"] == "s4in" else "16 in",
                     "embedding": "CLS" if r["embedding"] == "cls" else "mean-patch",
                     "classifier": "logistic" if r["classifier"] == "lr" else "nearest centroid", "n": r["n"],
                     "accuracy [95 % CI]": pct(r["acc"], _lohi(r, "acc_ci")), "(a) u,v": pct(r["acc_position u,v"]),
                     "(a) house frame": pct(r["acc_position house frame"]), "(b) head-masked": pct(r["acc_head-masked"]),
                     "(c) position-matched": pct(r["acc_position-matched"]), "Δ chance [CI]": pct(r["d_chance"], _lohi(r, "d_chance_ci")),
                     "Δ best control [CI]": pct(r["d_ctrl"], _lohi(r, "d_ctrl_ci")),
                     "carries identity": "YES" if r["carries_identity"] else "no",
                     "≥ 15 pp established": "YES" if r["gain_15pp_established"] else "no"})
    L += [md_table(pd.DataFrame(rows)), "",
          "- Only the first row (primary, LOGO) is the pre-named primary comparison.",
          "- LODO is the cross-day reading of the same configuration.",
          "- The other rows are descriptive. Chance = 1 / 5 = 20 %.",
          "- The best control is the highest of (a)–(c) under the same classifier and embedding.", ""]
    maj = t3r[(t3r.domain == "ir") & (t3r.scheme == "LOGO") & (t3r.feature == "head_s4in_cls") & (t3r.classifier == "lr")]
    if len(maj):
        L += [f"- **Primary, other measures:** balanced accuracy {pct(float(maj.bal_acc.iloc[0]))}; majority-class rate of the IR "
              f"clicks {pct(float(maj.majority_rate.iloc[0]))}; logistic C chosen per fold: {maj.C_chosen.iloc[0]}."]
    if len(sh):
        L += [f"- **(d) Shuffled labels** (CLS + logistic, LOGO, {len(sh)} permutations): mean accuracy {pct(sh.acc.mean())}, range "
              f"{pct(sh.acc.min())} – {pct(sh.acc.max())}."]
    if alt:
        L += [f"- **Grouping sensitivity** (amendment 3: leave-one-`group_alt`-out, {alt['n_groups']} groups):",
              f"  - primary accuracy {pct(alt['acc'], _lohi(alt, 'acc_ci'))}; best control {alt['best_control']}, "
              f"{pct(alt['best_control_acc'])};",
              f"  - Δ vs best control {pct(alt['d_ctrl'], _lohi(alt, 'd_ctrl_ci'))}; carries identity: {yn(alt['carries_identity'])}."]
    dup = t3r[t3r.scheme.astype(str).str.startswith("LOGO (no duplicate")]
    if len(dup):
        sub = json.loads(dup.C_chosen.iloc[0])
        L += [f"- **Without the clicks whose label occurs twice on their frame** ({int(dup.n.iloc[0])} clicks remain):",
              f"  - primary {pct(sub['head_s4in_cls'])};",
              f"  - controls: u,v {pct(sub['pos_uv'])}, house frame {pct(sub['pos_house'])}, head-masked "
              f"{pct(sub['masked_s4in_cls'])}, position-matched {pct(sub['posmatch_s4in_cls'])}."]
    cf = pd.read_csv(run / "t3_confusion.csv")
    c1 = cf[(cf.domain == "ir") & (cf.scheme == "LOGO")].pivot(index="true", columns="pred", values="n").reindex(index=list(CLASSES), columns=list(CLASSES))
    if len(c1):
        c1.insert(0, "true \\ predicted", c1.index)
        L += ["", "Confusion of the primary (IR, LOGO; rows = the user's label):", "", md_table(c1.reset_index(drop=True))]
    col = dec[(dec.domain == "colour") & (dec.role == "primary")].to_dict("records")
    if col:
        L += ["", "**Colour crops** (reported separately, never pooled with IR):"]
        L += [f"- {r['scheme']}: CLS + logistic {pct(r['acc'], _lohi(r, 'acc_ci'))}; best control {r['best_control']}, "
              f"{pct(r['best_control_acc'])}." for r in col]
    L += ["", "Further tables in the run folder:",
          "- all configurations (both domains, every feature × classifier × scheme, with the C chosen per fold): `t3_results.csv`;",
          "- predictions: `t3_predictions.csv.gz`; decisions: `t3_decisions.csv`.", ""]
    # review
    L += ["## Blind mask review page (amendment 1 item 1) — for the user", "",
          f"- **Page:** `{rel}/mask_review/index.html`. Open it from disk; it works offline.",
          f"- **Sample:** {rv['n_items']} masks from test-group IR frames: "
          + ", ".join(f"{k} {v}" for k, v in sorted(rv["by_method"].items())) + ".",
          "  - T1 = the chosen prompt and τ on the whole frame.",
          "  - T2pos / T2neg = the two point-prompt variants, on different heads.",
          "- **Strata:** pile size of the mask's head (single linkage of the frame's blind heads at 6 in): "
          + "; ".join(f"{r['method']} {r['stratum']}: {r['n']}" for r in rv["by_method_stratum"]) + ".",
          "- **Display:** items are shuffled and named M01…M40. The page shows the whole frame and a zoomed crop with the mask "
          "tinted (a toggle hides the tint). It never shows the method, the score or a head point.",
          "- **Choices:** one whole rat / part of a rat / two or more rats / not a rat, plus notes.",
          "- **Saving:** answers are kept in the browser (localStorage); Export CSV / JSON → "
          "`cv/configs/inbox_sam3_mask_review_2026c/`.",
          "- **Key:** item → method, prompt, τ, score, frame and head in `mask_key.csv` in the run folder; not linked from the page.",
          f"- **Headless check: {pc.get('verdict', 'not run')}** (`mask_review_page_check.json`). It covered: {pc.get('n_cards')} cards; "
          f"{pc.get('n_images_ok')} / {pc.get('n_images')} images loaded; a judgment kept across a reload; export of every item; no "
          "method or score words; no network URL.",
          "- **The agent has not looked at any mask.**", ""]
    L += sweep_report_md(run)
    pb = run / "prelabel_edit_v2" / "summary_B.md"       # part B of plan 2026-10-12 (inbox_prelabel_edit.py summarize); v2 = B1 / B1a
    if not pb.exists():
        pb = run / "prelabel_edit" / "summary_B.md"
    if pb.exists():
        L += [pb.read_text(encoding="utf-8"), ""]
    L += definitions_md()
    L += ["## Limits and what is not verified", "",
          "- **No usable-box claim yet.** Head-point exclusivity is necessary, not sufficient, for one-whole-rat masks. The blind mask "
          "review decides that, and the user has not scored it yet.",
          "- **T2's negative-point variant is partly self-validating:** the metric checks the same heads the prompt excludes. The "
          "positive-point variant is the pre-named primary.",
          "- **Sample size:** one house (CH07), one labeller, 20 still-episode groups. No pair met the join rule.",
          "  - The IR frames are 6 s and 15 s after the colour light, so one pile appears twice per segment, and sometimes again "
          "in the next segment; amendment 3 gives the sensitivity.",
          "  - Bootstrap CIs over about 15–20 groups are approximate.",
          "- **T3 labels and claims:**",
          "  - The truth labels are the user's blind IDs; two IR frames carry a duplicated label (the sensitivity is reported).",
          "  - Leave-one-group-out success alone is not a cross-day claim; LODO has one held-out day.",
          "  - The gate is an engineering test, not a biological claim.",
          "- **Inner-CV choice of C** for the logistic probe varies from 0.01 to 100 across the leave-one-group-out folds. The "
          "training sets are small, so the probe is not tuned finely.",
          "- **T1 τ sits at the cache floor (0.01).** The low end of the τ grid was set after the API probe had shown one prompt "
          "scoring ≤ 0.02 on one frame; that probe matched no head and computed no metric (plan, disclosure note).",
          "- **Execution:** the first GPU job stopped after 8 frames when its session ended. It resumed from atomic per-frame caches, "
          "and no frame was recomputed.",
          "- **Interpreter split:** scipy's L-BFGS-B crashes natively in the cv env (0xc06d007f). So the score and review "
          "phases ran in base Python (scikit-learn " + str(meta.get("score_versions", {}).get("scikit-learn", "?")) + "), and the "
          "GPU phases in the cv env.",
          "- **No training, no labels:** SAM 3 and DINOv3 are frozen; no detector was trained and no label was written.", ""]
    L += ["## Rerun", "", "```",
          "python cv/cv_field/inbox_sam3_dino_test.py --selftest",
          "C:/Users/Cornell/.conda/envs/cv/python.exe cv/cv_field/inbox_sam3_dino_test.py --phases data t1gpu t2gpu dino   # new run (GPU)",
          f"python cv/cv_field/inbox_sam3_dino_test.py --run {rel} --phases score review report",
          "```", "", "## Files", "", f"Run folder `{rel}`:",
          "- inputs and groups: `frames.csv`, `heads.csv`, `groups.csv`, `group_pairs.csv`, `data.json`;",
          "- raw masks: `sam3_t1/{whole,tiled}/*.npz`, `sam3_t2/*.npz`; timing: `timing_t1.csv`, `timing_t2.csv`;",
          "- T1: `t1_frame_metrics.csv.gz`, `t1_sweep.csv`, `t1_head_detail.csv.gz`, `t1_by_pile_test_ir.csv`, `t1_result.json`;",
          "- T2: `t2_heads.csv`, `t2_pair_iou.csv`, `t2_summary.csv`, `t2_by_pile_test.csv`, `t2_result.json`;",
          "- T3: `t3_units.csv`, `t3_embeddings.npz`, `t3_results.csv`, `t3_predictions.csv.gz`, `t3_decisions.csv`, "
          "`t3_confusion.csv`, `t3_shuffled.csv`, `t3_group_alt.json`, `t3_result.json`;",
          "- review: `mask_review/` (the page + `items/`), `mask_key.csv` (the hidden key), `mask_review_meta.json`, "
          "`mask_review_page_check.json`;",
          "- `run.json`.", ""]
    rp = REPO / "results" / COHORT / DIRECTION / "reports" / REPORT_NAME
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text("\n".join(L), encoding="utf-8")
    write_json(rp.parent / POINTER_NAME, {"name": NAME, "cohort": COHORT, "direction": DIRECTION, "run_dir": rel,
                                          "report": rp.relative_to(REPO).as_posix(), "plan": PLAN, "git_commit": meta["git_commit"],
                                          "made": meta["made"], "mask_review_page": f"{rel}/mask_review/index.html",
                                          "mask_key": f"{rel}/mask_key.csv",
                                          "review_exports": REVIEW_EXPORT_DIR.relative_to(REPO).as_posix()})
    return rp


def sweep_report_md(run: Path) -> list[str]:
    """Amendment 4 section (exploratory prompt sweep), only if the sweep has run."""
    sd = run / "prompt_sweep"
    if not (sd / "sweep_summary.csv").exists():
        return []
    sm = pd.read_csv(sd / "sweep_summary.csv")
    sel = pd.read_csv(sd / "sweep_frames.csv")
    gi = json.loads((sd / "gpu_info.json").read_text(encoding="utf-8")) if (sd / "gpu_info.json").exists() else {}
    pc = json.loads((sd / "page_check.json").read_text(encoding="utf-8")) if (sd / "page_check.json").exists() else {}
    det = gi.get("determinism_rat_whole", {})
    L = ["## Exploratory prompt sweep (amendment 4; user request, after results)", "",
         "**EXPLORATORY and descriptive only.** There is no gate, no choice and no claim beyond these 20 frames, and nothing here "
         "changes T1–T3. The user asked to try ten frames with rats in view and more prompts (2026-10-11).", "",
         "- **Frames** (rule fixed before running):",
         "  - per day, one segment per `group_alt` still episode, then 5 evenly spaced daytime segments with an IR frame holding "
         "≥ 3 blind heads;",
         "  - the colour mid-frames of the same segments are a separate block.", "",
         md_table(sel[["day", "segment_id", "group", "split", "ir_frame", "ir_heads", "colour_frame", "colour_heads"]]), "",
         "- **Prompts:** \"rat\", \"Long Evans rat\" and \"hooded rat\" are read from the T1 cache. The other seven are new, "
         "run with the T1 settings (score floor 0.01, imgsz 1008).",
         f"- **Determinism check:** \"rat\" re-run on {det.get('frame_id', '–')} (whole) gave {det.get('n_rerun', '–')} masks vs "
         f"{det.get('n_cache', '–')} in the cache; max score difference {det.get('max_abs_score_diff', float('nan')):.2g}; "
         f"{det.get('n_masks_pixel_identical', '–')} masks pixel-identical.",
         "- **Matching:** as in T1 (coverage within 15 px).", "",
         "**Columns:**",
         "- X = heads with their own exclusive mask;",
         "- missed = heads with no mask within 15 px;",
         "- merged = masks over ≥ 2 heads; empty = masks over no head;",
         "- masks = mask count (heads given in the caption).", "",
         "Pooled over the 10 frames per block.", ""]
    for dom, name in (("ir", "IR"), ("colour", "Colour (separate, never pooled with IR)")):
        for tau in SWEEP_TAUS:
            d = sm[(sm.domain == dom) & (sm.tau == tau)]
            if d.empty:
                continue
            nh = int(d.n_heads.iloc[0])
            rows = []
            for pk in SWEEP_PROMPTS:
                w, t = d[(d.prompt == pk) & (d.variant == "whole")], d[(d.prompt == pk) & (d.variant == "tiled")]
                if w.empty or t.empty:
                    continue
                w, t = w.iloc[0], t.iloc[0]
                rows.append({"prompt": pk, "whole X": f"{w.exclusive} ({pct(w.X, d=0)})", "whole missed": w.missed, "whole merged": w.merged,
                             "whole empty": int(w["empty"]), "whole masks": w.n_masks, "tiled X": f"{t.exclusive} ({pct(t.X, d=0)})",
                             "tiled missed": t.missed, "tiled merged": t.merged, "tiled empty": int(t["empty"]), "tiled masks": t.n_masks})
            L += [f"**{name}, τ = {tau:g}** ({nh} heads on {int(d.n_frames.iloc[0])} frames):", "", md_table(pd.DataFrame(rows)), ""]
    ir01 = sm[(sm.domain == "ir") & (sm.tau == min(SWEEP_TAUS)) & (sm.variant == "whole")]
    hi = ir01[ir01.X >= 0.5]
    if len(hi):
        L += [f"- **Descriptive reading of the counts** (no judgment of the images): at τ = {min(SWEEP_TAUS):g}, the prompts with X ≥ 50 % "
              f"on the whole IR frames ({', '.join(chr(34) + x + chr(34) for x in hi.prompt)}) return {int(hi.n_masks.min())}–"
              f"{int(hi.n_masks.max())} masks for {int(hi.n_heads.iloc[0])} heads ({int(hi['empty'].min())}–{int(hi['empty'].max())} "
              "of them empty).",
              "  - So a high X there comes with many masks per head, one of which covers each head point alone.",
              "  - It does not show a rat detector.",
              f"  - At τ = {max(SWEEP_TAUS):g} almost every prompt misses almost every head.",
              "  - Whether any mask outlines a rat is for the user to see on the page."]
    L += [f"- **Page for the user:** `{(sd / 'index.html').as_posix()}`.",
          "  - Per frame and prompt: whole and tiled panels with mask outlines in distinct colours, the blind clicks as dots, "
          "and a τ switch (0.01 / 0.25).",
          f"  - Headless check: **{pc.get('verdict', 'not run')}** (`prompt_sweep/page_check.json`).",
          "- Tables: `prompt_sweep/sweep_summary.csv` (pooled), `sweep_frame_metrics.csv` (per frame); raw masks of the new prompts "
          "in `prompt_sweep/sam3/`.",
          "- **The agent did not look at the panels.**", ""]
    return L


def definitions_md() -> list[str]:
    return ["## Definitions", "",
            "Units: image pixels (px) of the full-resolution frame (2560 × 1920), origin top-left; inches only where stated (scale "
            "s = 74.8 px/in from the clicks run's similarity fit). $h_i=(u_i,v_i)$ = blind head click $i$ of a frame; $M_j$ = a "
            "mask (set of pixels) with score $s_j$ and area $|M_j|$ px.", "",
            "### Head–mask distance and coverage ($d_{ij}$, $c_{ij}$)",
            "$$ d_{ij} = \\begin{cases}0 & \\lfloor h_i\\rfloor \\in M_j\\\\ \\min_{p\\in M_j}\\lVert (p+\\tfrac12) - h_i\\rVert_2 & \\text{otherwise}\\end{cases},\\qquad c_{ij}=\\mathbb 1[d_{ij}\\le 15\\,\\text{px}] $$",
            "**Text:** a mask covers a head if the clicked pixel is in the mask or a mask pixel centre lies within 15 px (plan). Units px.", "",
            "### T1 kept masks and matching",
            "$K_\\tau=\\{j: s_j\\ge\\tau\\}$. Head choice $a(i)=\\arg\\max_{j\\in K_\\tau, c_{ij}=1}(s_j,-|M_j|)$; mask $j$ keeps "
            "$k(j)=\\arg\\min_{i:a(i)=j}(d_{ij},\\lVert h_i-\\bar M_j\\rVert)$ ($\\bar M_j$ = mask centroid). **Text:** a head goes to "
            "the highest-scoring mask covering it; a mask chosen by several heads is matched to one (amendment 1 item 4).", "",
            "### T1 counts and rates (pooled over a frame set $F$)",
            "$$ TP=\\sum_{f\\in F}\\#\\{j: k(j)\\text{ exists}\\},\\quad P=\\frac{TP}{\\sum_f |K_\\tau|},\\quad R=\\frac{TP}{\\sum_f n_f},\\quad F_1=\\frac{2\\,TP}{\\sum_f(|K_\\tau|+n_f)} $$",
            "$$ X=\\frac{\\sum_f \\#\\{i: i=k(a(i)),\\ \\sum_{i'}c_{i'a(i)}=1\\}}{\\sum_f n_f},\\quad \\text{merged}=\\frac{\\#\\{j:\\sum_i c_{ij}\\ge2\\}}{\\sum_f|K_\\tau|},\\quad \\text{empty}=\\frac{\\#\\{j:\\sum_i c_{ij}=0\\}}{\\sum_f|K_\\tau|} $$",
            "$$ \\text{count error}=\\frac1{|F|}\\sum_f(|K_\\tau|-n_f) $$",
            "where $n_f$ = blind heads on frame $f$. **Text:** $X$ (**head-point exclusivity**) = share of heads that have their own mask "
            "covering no other head (0–1; 1 = one mask per head point); merged = share of masks spanning ≥ 2 head points; empty = "
            "share of masks on no head point; count error in masks per frame (+ = too many). $F_1$ is the dev selection criterion.", "",
            "### Threshold τ and prompt choice",
            "τ ∈ {0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15, …, 0.95}; the (prompt, τ) maximising pooled $F_1$ on dev IR frames (ties → "
            "higher τ, then lower prompt number). SAM 3 score $s=\\sigma(\\ell_{det})\\,\\sigma(\\ell_{presence})$ (ultralytics). "
            "**Text:** chosen once on dev, never on test.", "",
            "### Tiled merge",
            "Tile masks with $s\\ge\\tau$ in descending score; mask $m$ joins the first earlier-kept representative $r$ from another tile "
            "with $\\mathrm{IoU}(M_m,M_r)=|M_m\\cap M_r|/|M_m\\cup M_r|\\ge0.5$; a cluster covers a head if any member does; its score = "
            "$s_r$, its area = the union area. **Text:** removes duplicates of one object seen by two overlapping tiles.", "",
            "### T2 per-head mask metrics",
            "For head $i$ with point-prompted mask $M^{(i)}$: own $=c_{i,(i)}$, $n^{(i)}=\\sum_{i'}c_{i',(i)}$; exclusive $=\\text{own}\\wedge n^{(i)}=1$; "
            "merge $=n^{(i)}\\ge2$; own missed $=\\neg\\text{own}$. Rates = means over heads. Pairwise $\\mathrm{IoU}(M^{(i)},M^{(i')})$ "
            "over head pairs of a frame; box = bounding box of $M^{(i)}$, aspect = long / short side. **Text:** exclusivity near 1 = "
            "each point gives a mask on its own head only (head-point level, not a whole-rat check).", "",
            "### Still-episode group join rule",
            "$$ \\text{join}(i,i{+}1)=\\mathbb 1\\Big[\\text{roster}(t)\\ \\text{constant on}\\ [t_a,t_b]\\Big]\\cdot\\prod_{a\\in\\text{roster}}\\mathbb 1\\Big[\\tfrac{1}{N}\\textstyle\\sum_{t=t_a}^{t_b}\\text{ok}_a(t)\\,\\text{still}_a(t)\\ge0.9\\Big] $$",
            "$t_a$ = last frame of segment $i$, $t_b$ = colour frame of $i+1$, $N$ = seconds in $[t_a,t_b]$. **Text:** a still, "
            "unchanged pile between two flashes makes them one unit (amendment 1 item 2).", "",
            "### Grouped bootstrap CI",
            "$B=2000$ draws of the groups with replacement (seed 20261011); a pooled ratio $\\hat\\theta^{(b)}=\\sum_g w^{(b)}_g\\,\\text{num}_g/\\sum_g w^{(b)}_g\\,\\text{den}_g$ "
            "($w_g^{(b)}$ = times group $g$ is drawn); 95 % CI = 2.5th–97.5th percentiles. Paired = the same draws for the compared "
            "quantities. **Text:** uncertainty from which still episodes happened to be sampled.", "",
            "### T3 accuracy, balanced accuracy, chance",
            "$$ \\text{acc}=\\frac1N\\sum_n\\mathbb 1[\\hat y_n=y_n],\\quad \\text{bal}=\\frac1{|C|}\\sum_{c}\\frac{\\#\\{n:y_n=c,\\hat y_n=c\\}}{\\#\\{n:y_n=c\\}},\\quad \\text{chance}=1/5 $$",
            "$y_n$ = the user's blind label, $\\hat y_n$ = the prediction for click $n$ when its group (LOGO) or its day (LODO) was held out. "
            "Majority-class rate = largest class share.", "",
            "### T3 classifiers",
            "Logistic: standardised features, multinomial L2 logistic regression, $C\\in\\{10^{-3},…,10^{2}\\}$ by inner GroupKFold "
            "(min(5, groups) folds, pooled accuracy, ties → smaller C) inside each training fold. Nearest centroid: "
            "$\\hat y=\\arg\\max_c \\langle z/\\lVert z\\rVert,\\mu_c/\\lVert\\mu_c\\rVert\\rangle$ (embeddings) or "
            "$\\arg\\min_c\\lVert z-\\mu_c\\rVert$ on standardised coordinates (position).", "",
            "### T3 controls",
            "(a) position only: $(u,v)$ px and the house-frame $(\\text{along},\\text{across})$ in from the similarity fit; (b) head-masked: "
            "the same crop with the disc $\\lVert p-h\\rVert\\le1.5$ in filled with the crop's per-channel median; (c) position-matched: "
            "the crop at the same $(u,v)$ in one IR frame of another group (drawn uniformly, seed 20261011), labelled with the original "
            "rat; (d) shuffled: labels permuted across clicks (20 permutations). Best control = $\\max$ point accuracy among (a)–(c) "
            "under the same classifier (and embedding).", "",
            "### T3 decision rule (amendment 1 item 3)",
            "$$ \\Delta_{ch}=\\text{acc}-0.2,\\quad\\Delta_{ct}=\\text{acc}-\\text{acc}_{best},\\quad \\text{carries}=[\\Delta_{ch}\\ge0.15]\\wedge[\\Delta_{ct}\\ge0.15]\\wedge[\\mathrm{CI}_{lo}(\\Delta_{ch})>0]\\wedge[\\mathrm{CI}_{lo}(\\Delta_{ct})>0] $$",
            "established $=\\text{carries}\\wedge\\mathrm{CI}_{lo}(\\Delta_{ch})\\ge0.15\\wedge\\mathrm{CI}_{lo}(\\Delta_{ct})\\ge0.15$, CIs paired grouped bootstrap. "
            "**Text:** an engineering gate, not a biological claim.", "",
            "### Pile size",
            "Size of the head's single-linkage cluster among the frame's blind heads with link distance 6 in (= 449 px). Strata 1, 2–3, ≥ 4 "
            "(and 'none' for a T1 mask on no head). **Text:** used only to stratify the review sample and descriptive tables.", ""]


# ============================================================================================ selftest
def selftest() -> int:
    ok_all = True

    def rec(name, cond, detail=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    rng = np.random.default_rng(0)
    # 1 RLE
    good = True
    for shape in ((0, 0), (1, 1), (5, 7), (40, 33)):
        for p in (0.0, 0.3, 1.0):
            m = rng.random(shape) < p
            good &= np.array_equal(rle_decode(rle_encode(m), shape), m)
    rec("RLE round trip (empty, all-true, random)", good)
    # 2 distance / coverage
    full = np.zeros((200, 200), bool)
    full[50:100, 60:120] = True
    r = crop_record(full)
    rec("crop record bbox / area", r["bbox"] == (60, 50, 120, 100) and r["area"] == 50 * 60)
    d_in, d_10, d_20 = head_dist(r["crop"], r["bbox"], 80.3, 70.2), head_dist(r["crop"], r["bbox"], 130.5, 70.5), head_dist(r["crop"], r["bbox"], 140.5, 70.5)
    rec("head distance: inside 0, 10.5 px out, 20 px out -> > 15", d_in == 0 and abs(d_10 - 11.0) < 1e-9 and d_20 > COVER_PX, f"{d_in} {d_10} {d_20}")
    # 3 T1 matching
    heads = np.array([[10.0, 10.0], [100.0, 100.0], [110.0, 100.0]])
    D = np.array([[0, np.inf, np.inf, 3.0], [np.inf, 0, np.inf, np.inf], [np.inf, 2.0, np.inf, np.inf]])
    score, area = np.array([0.9, 0.8, 0.7, 0.5]), np.array([100, 500, 50, 30])
    cent = [(10, 10), (101, 100), (300, 300), (12, 10)]
    a = match_units(D[:, :3], score[:3], area[:3], cent[:3], heads)
    rec("T1 match: TP 2, merged 1, empty 1, exclusive 1", (a["tp"], a["merged"], a["empty"], a["excl"]) == (2, 1, 1, 1), str((a["tp"], a["merged"], a["empty"], a["excl"])))
    b = match_units(D, score, area, cent, heads)
    rec("T1 match: a head inside two masks goes to the higher score; the other is unmatched",
        b["choice"][0] == 0 and b["tp"] == 2 and b["n_masks"] == 4 and b["keeper"][3] == -1 and b["keeper"][1] == 1)
    pl = pooled(pd.DataFrame([{"n_heads": 3, "n_masks": 3, "tp": 2, "merged": 1, "empty": 1, "excl": 1}]))
    rec("pooled F1 = 2TP / (n masks + n heads)", abs(pl["F1"] - 4 / 6) < 1e-12 and abs(pl["X"] - 1 / 3) < 1e-12)
    # 4 tiled merge
    m1 = np.zeros((100, 100), bool)
    m1[10:50, 10:50] = True
    m2 = np.zeros((100, 100), bool)
    m2[12:50, 10:50] = True
    m3 = np.zeros((100, 100), bool)
    m3[60:90, 60:90] = True
    recs = [crop_record(x) for x in (m1, m2, m3, m2)]
    M = {"bbox": np.array([x["bbox"] for x in recs]), "area": np.array([x["area"] for x in recs]), "crops": [x["crop"] for x in recs],
         "tile": np.array([0, 1, 1, 0]), "score": np.array([0.9, 0.8, 0.7, 0.6], np.float32), "prompt": np.zeros(4, int)}
    nb = cross_tile_neighbours(M, np.arange(4))
    cl = tile_clusters([0, 1, 2, 3], M["tile"], nb)
    rec("tiled merge: cross-tile IoU >= 0.5 joins; same tile never", cl == [[0, 1], [2], [3]], str(cl))
    sw = t1_frame_sweep(M, np.array([[30.0, 30.0], [75.0, 75.0]]), tiled=True, taus=[0.5])
    p1 = [x for x in sw if x["prompt"] == "P1"][0]
    rec("tiled sweep: 3 units, TP 2, 1 merged-free duplicate unit unmatched", p1["n_masks"] == 3 and p1["tp"] == 2 and p1["n_cross_tile_merges"] == 1, str({k: p1[k] for k in ("n_masks", "tp")}))
    rec("mask IoU / union area", abs(mask_iou(recs[0]["crop"], recs[0]["bbox"], recs[1]["crop"], recs[1]["bbox"]) - 38 / 40) < 1e-12
        and union_area([recs[0]["crop"], recs[2]["crop"]], [recs[0]["bbox"], recs[2]["bbox"]]) == 1600 + 900)
    # 5 grouping
    t0 = datetime(2026, 9, 10, 12, 0, 0)
    secs = np.arange(int(unix_s(t0)) - 10, int(unix_s(t0)) + 400)
    occ = pd.DataFrame({"house_2": ["SF07;SF08"] * len(secs)}, index=secs)
    still95 = np.r_[np.ones(380, bool), np.zeros(30, bool)]
    imu = {"SF07": pd.DataFrame({"ok": True, "still": True}, index=secs), "SF08": pd.DataFrame({"ok": True, "still": still95}, index=secs)}
    j = pair_link(t0, t0 + timedelta(seconds=300), occ, imu)
    rec("join: roster constant + still >= 90 % -> joined", j["joined"], str(j))
    imu2 = {"SF07": imu["SF07"], "SF08": pd.DataFrame({"ok": True, "still": np.r_[np.zeros(60, bool), np.ones(350, bool)]}, index=secs)}
    j2 = pair_link(t0, t0 + timedelta(seconds=300), occ, imu2)
    rec("join: still 84 % -> not joined", not j2["joined"])
    occ3 = occ.copy()
    occ3.iloc[100, 0] = "SF07"
    rec("join: roster change -> not joined", not pair_link(t0, t0 + timedelta(seconds=300), occ3, imu)["joined"])
    imu4 = {"SF07": imu["SF07"], "SF08": imu["SF08"].drop(index=secs[20:60])}
    j4 = pair_link(t0, t0 + timedelta(seconds=300), occ, imu4)
    rec("join: missing IMU seconds count as not still (ok-only share still joins)", (not j4["joined"]) and j4["joined_okden"])
    segs = {f"S{k}": {"start": t0 + timedelta(minutes=10 * k), "frames": {"colour_mid": {"time": t0 + timedelta(minutes=10 * k, seconds=5)},
                                                                         "ir_p15": {"time": t0 + timedelta(minutes=10 * k, seconds=30)}}}
            for k in range(8)}
    joins = {("S0", "S1"): True, ("S1", "S2"): False, ("S2", "S3"): False, ("S3", "S4"): False, ("S4", "S5"): False,
             ("S5", "S6"): True, ("S6", "S7"): False}
    g, _ = build_groups(list(segs), segs, None, None, joiner=lambda a, b: {"joined": joins[(a, b)]})
    rec("groups: chains, dev = groups of the 5 earliest segments", list(g.group) == ["G01", "G01", "G02", "G03", "G04", "G05", "G05", "G06"]
        and list(g.split) == ["dev"] * 5 + ["test"] * 3, str(list(zip(g.group, g.split))))
    # 6 bootstrap
    W = boot_weights(6, 500, 1)
    rec("bootstrap weights: each draw sums to the group count", np.all(W.sum(1) == 6))
    lo, hi = ratio_ci(np.array([1, 2, 3, 4, 5, 6.0]), np.array([10, 10, 10, 10, 10, 10.0]), W)
    rec("ratio CI brackets the point estimate", lo <= 0.35 <= hi)
    # 7 crops
    img = np.zeros((100, 120, 3), np.uint8)
    img[:] = 50
    c, (x0, y0) = square_crop(img, 5.0, 5.0, 31, np.array([7, 7, 7], np.uint8))
    rec("crop: size, padding at the frame edge", c.shape == (31, 31, 3) and (x0, y0) == (-10, -10) and c[0, 0, 0] == 7 and c[20, 20, 0] == 50)
    c2 = c.copy()
    c2[10:20, 10:20] = 200
    dm = disc_masked(c2, 15.5, 15.5, 4)
    rec("head disc filled with the crop median", dm[15, 15, 0] == np.median(c2[..., 0]) and dm[0, 0, 0] == 7)
    # 8 piles
    ps = pile_sizes(np.array([[0, 0], [100, 0], [190, 0], [1000, 0.0]]), 100)
    rec("pile size by single linkage", list(ps) == [3, 3, 3, 1] and stratum(1) == "1" and stratum(3) == "2-3" and stratum(5) == "4+" and stratum(None) == "none")
    # 9 classifiers + decision
    if not lbfgs_ok():
        print("[SKIP] logistic-regression checks: scipy L-BFGS-B crashes in this interpreter (the cv env); run the selftest and the "
              "score phase with base Python")
    try:
        if not lbfgs_ok():
            raise RuntimeError("skip")
        n_g, per = 8, 15
        g = np.repeat([f"G{k}" for k in range(n_g)], per)
        y = np.tile(np.array(CLASSES * 3), n_g)
        cen = rng.normal(size=(5, 16)) * 3
        Xs = np.array([cen[CLASSES.index(c)] for c in y]) + rng.normal(size=(len(y), 16))
        Xn = rng.normal(size=(len(y), 16))
        ps_, _ = run_logo(Xs, y, g, "lr", True, n_jobs=1)
        pn_, _ = run_logo(Xn, y, g, "lr", True, n_jobs=1)
        pc_, _ = run_logo(Xs, y, g, "nc", True, n_jobs=1)
        a_s, a_n, a_c = (ps_ == y).mean(), (pn_ == y).mean(), (pc_ == y).mean()
        rec("LOGO logistic: signal -> high accuracy, noise -> near chance", a_s > 0.9 and a_n < 0.4, f"{a_s:.2f} {a_n:.2f}")
        rec("nearest centroid (cosine) on signal", a_c > 0.8, f"{a_c:.2f}")
        te = np.isin(g, ["G6", "G7"])
        pr_, C = run_split(Xs, y, g, ~te, te, "lr", True)
        rec("held-out split predicts only the test rows", pr_[~te].tolist() == [None] * int((~te).sum()) and (pr_[te] == y[te]).mean() > 0.9)
    except ImportError as e:
        rec("sklearn / joblib available", False, str(e))
    except RuntimeError:
        pc_ = NearestCentroid(True).fit(rng.normal(size=(10, 4)) + np.repeat(np.eye(2, 4) * 5, 5, 0), np.repeat(["a", "b"], 5)).predict(np.eye(2, 4) * 5)
        rec("nearest centroid (cosine) without sklearn", list(pc_) == ["a", "b"])
    bm = np.full(1000, 0.6) + rng.normal(0, 0.03, 1000)
    bc = np.full(1000, 0.3) + rng.normal(0, 0.03, 1000)
    d1 = decide(0.6, 0.3, bm, bc)
    d2 = decide(0.6, 0.5, bm, np.full(1000, 0.5) + rng.normal(0, 0.03, 1000))
    d3 = decide(0.6, 0.3, bm + rng.normal(0, 0.09, 1000), bc)
    rec("decision: clear gain -> carries + established", d1["carries_identity"] and d1["gain_15pp_established"])
    rec("decision: gain over best control < 15 pp -> no", not d2["carries_identity"])
    rec("decision: wide CI -> carries but not established", d3["carries_identity"] and not d3["gain_15pp_established"], str(d3))
    # 9b exploratory sweep frame rule (amendment 4)
    segs_ = [("2026-09-10", f"S{k:02d}", f"A{k:02d}", 8 + k) for k in range(12)] + \
            [("2026-09-11", f"T{k:02d}", ("B00" if k < 3 else f"B{k:02d}"), 9 + k) for k in range(7)]
    fr_, gr_ = [], []
    for day, sid, ga, hh in segs_:
        gr_.append({"segment_id": sid, "start": f"{day} {hh:02d}:00:00", "group": "G" + sid, "group_alt": ga, "split": "test"})
        fr_.append({"frame_id": sid + "__ir_p06", "segment_id": sid, "domain": "ir", "frame_kind": "ir_p06",
                    "frame_time": f"{day} {hh:02d}:00:30", "n_heads": 2 if sid == "S00" else 5})
        fr_.append({"frame_id": sid + "__ir_p15", "segment_id": sid, "domain": "ir", "frame_kind": "ir_p15",
                    "frame_time": f"{day} {hh:02d}:00:40", "n_heads": 5})
        fr_.append({"frame_id": sid + "__colour_mid", "segment_id": sid, "domain": "colour", "frame_kind": "colour_mid",
                    "frame_time": f"{day} {hh:02d}:00:10", "n_heads": 5})
    ss = select_sweep_frames(pd.DataFrame(fr_), pd.DataFrame(gr_))
    rec("sweep frames: 5 per day, one per still episode (middle), daytime only, ir_p06 unless < 3 heads",
        list(ss.day.value_counts().sort_index()) == [5, 5] and ss.group_alt.is_unique and "T01" in set(ss.segment_id)
        and not ({"T00", "T02"} & set(ss.segment_id)) and "S11" not in set(ss.segment_id)
        and ss.set_index("segment_id").at["S00", "ir_frame"] == "S00__ir_p15", str(list(ss.segment_id)))
    # 10 review sampler + page
    t1c = pd.DataFrame({"frame_id": "F", "mask_index": range(30), "click_id": [f"c{k}" for k in range(30)],
                        "stratum": (["1"] * 3 + ["2-3"] * 7 + ["4+"] * 18 + ["none"] * 2)})
    t2c = pd.DataFrame({"click_id": [f"h{k}" for k in range(40)], "frame_id": "F", "stratum": ["1"] * 4 + ["2-3"] * 10 + ["4+"] * 26})
    it = review_sample(t1c, t2c)
    cnt = it.method.value_counts().to_dict()
    rec("review sample: quotas 14 / 13 / 13", cnt == {"T1": 14, "T2pos": 13, "T2neg": 13}, str(cnt))
    rec("review sample: T2 variants on different heads", not (set(it[it.method == "T2pos"].click_id) & set(it[it.method == "T2neg"].click_id)))
    s1 = it[it.method == "T1"].stratum.value_counts().to_dict()
    rec("review sample: round-robin covers every stratum", s1.get("1") == 3 and s1.get("none") == 2 and s1.get("2-3", 0) >= 4, str(s1))
    rec("review sample: ids M01..M40, shuffled methods", list(it.item_id) == [f"M{k:02d}" for k in range(1, 41)] and it.method.iloc[:14].nunique() > 1)
    html_text = page_html([{"item_id": f"M{k:02d}", "ctx": f"items/M{k:02d}_ctx.jpg", "zoom": f"items/M{k:02d}_zoom.jpg",
                            "plain": f"items/M{k:02d}_plain.jpg"} for k in range(1, 41)], "cv_field_inbox_x_20261011_0000")
    rec("review page: no method / score words, no network URL", not blind_check_html(html_text) and not re.search(r"https?://", html_text), str(blind_check_html(html_text)))
    rec("blind check catches a leaked word", blind_check_html("<p>T2 positive score 0.4</p>") != [])
    node = shutil.which("node")
    if node:
        with tempfile.TemporaryDirectory() as td:
            js = Path(td) / "page.js"
            js.write_text(PAGE_JS, encoding="utf-8")
            r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
            rec("page script parses (node --check)", r.returncode == 0, r.stderr[-300:])
            for nm, src in (("sweep", SWEEP_JS), ("prompt GUI", PROMPT_GUI_JS)):
                js.write_text(src, encoding="utf-8")
                r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
                rec(f"{nm} page script parses (node --check)", r.returncode == 0, r.stderr[-300:])
    else:
        print("[SKIP] node not on PATH")
    # 11 truth loading from a synthetic export
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cols = ["record", "click_id", "segment_id", "camera", "house", "frame_kind", "frame_file", "frame_idx", "frame_time", "u_px", "v_px", "animal",
                "confidence", "before_reveal", "legacy", "edited_after_reveal", "deleted_after_reveal", "first_frame_kind", "first_u_px", "first_v_px",
                "first_animal", "first_confidence", "lid_segment", "lid_flag", "lid_target_frame", "b11", "b12", "b13", "b21", "b22", "b23",
                "pile_complete", "pile_complete_first", "revealed_at", "note", "clicked_at", "animal_before_sf09_sf10_fix", "relabelled_sf09_sf10",
                "first_animal_before_sf09_sf10_fix", "sf09_sf10_fix_applied_at", "sf09_sf10_fix_undone_at"]
        base = {c: "" for c in cols}
        base.update({"record": "click", "segment_id": "CH07_20260910_120000", "camera": "CH07", "house": "house_2", "b11": "1", "b12": "0",
                     "b13": "0", "b21": "0", "b22": "1", "b23": "0", "legacy": "false", "edited_after_reveal": "false", "deleted_after_reveal": "false"})
        rows_ = [dict(base, click_id="a", frame_kind="ir_p06", u_px="100", v_px="200", animal="SF08", before_reveal="true",
                      first_frame_kind="ir_p06", first_u_px="90", first_v_px="200", first_animal="SF07", edited_after_reveal="true"),
                 dict(base, click_id="b", frame_kind="ir_p06", u_px="500", v_px="500", animal="SF09", before_reveal="false"),
                 dict(base, click_id="c", frame_kind="ir_p15", u_px="5", v_px="6", animal="SF10", before_reveal="true",
                      first_frame_kind="ir_p15", first_u_px="5", first_v_px="6", first_animal="SF10")]
        rows_.append(dict({c: "" for c in cols}, record="segment", segment_id="CH07_20260910_120000", revealed_at="2026-10-11T00:00:00Z"))
        pd.DataFrame(rows_, columns=cols).to_csv(td / "clicks.csv", index=False)
        frs = [{"kind": k, "time": t, "path": f"frames/x_{k}.jpg"} for k, t in
               (("colour_mid", "2026-09-10 12:00:05.000"), ("ir_p06", "2026-09-10 12:00:20.000"), ("ir_p15", "2026-09-10 12:00:29.000"))]
        page = {"segments": [{"segment_id": "CH07_20260910_120000", "camera": "CH07", "house": "house_2", "start": "2026-09-10 12:00:00.000",
                              "end": "2026-09-10 12:00:10.000", "mid": "2026-09-10 12:00:05.000", "duration_s": 10.0, "frames": frs,
                              "wiser": {"roster": [], "positions": []}}]}
        (td / "p0" / "identity_page").mkdir(parents=True)
        (td / "p0" / "identity_page" / "page_data.json").write_text(json.dumps(page), encoding="utf-8")
        T = load_truth(td / "clicks.csv", td / "p0", statement=None)
        h = T["heads"]
        rec("truth: blind clicks only, first_* values (a: SF07 at u 90), after-reveal click unused",
            len(h) == 2 and h.set_index("click_id").at["a", "animal"] == "SF07" and h.set_index("click_id").at["a", "u"] == 90.0
            and T["n_after"] == 1 and set(T["frames"].frame_id) == {"CH07_20260910_120000__ir_p06", "CH07_20260910_120000__ir_p15"})
    # 12 mask cache round trip
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "m.npz"
        save_masks(p, recs, {"score": np.array([0.9, 0.8, 0.7, 0.6], np.float32), "click_id": np.array(["a", "b", "c", "d"], dtype="U32")})
        L_ = load_masks(p)
        rec("mask cache (npz + RLE) round trip", all(np.array_equal(x, y["crop"]) for x, y in zip(L_["crops"], recs)) and list(L_["click_id"]) == ["a", "b", "c", "d"])
    print("SELFTEST", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


# ============================================================================================ main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run", type=Path, help="existing run folder (resume / re-score)")
    ap.add_argument("--phases", nargs="+", default=["data", "t1gpu", "t2gpu", "dino", "score", "review", "report"],
                    choices=["data", "t1gpu", "t2gpu", "dino", "score", "review", "sweep_gpu", "sweep", "gui", "report"],
                    help="sweep_gpu / sweep = the exploratory prompt sweep of amendment 4 (run on request, after t1gpu)")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--no-page-check", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    run = a.run or OUT_ROOT / COHORT / f"{NAME}_{datetime.now():%Y%m%d_%H%M}"
    run.mkdir(parents=True, exist_ok=True)
    mp = run / "run.json"
    meta = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    import importlib.metadata as im
    vers = {}
    for pkg in ("ultralytics", "torch", "scikit-learn", "numpy", "pandas", "opencv-python"):
        try:
            vers[pkg] = im.version(pkg)
        except Exception:  # noqa: BLE001
            vers[pkg] = None
    meta.update({"made": meta.get("made", datetime.now().isoformat(timespec="seconds")), "git_commit": git_commit(), "plan": PLAN,
                 "run": run.as_posix(), "versions": {**meta.get("versions", {}), **{k: v for k, v in vers.items() if v}},
                 "versions_by_python": {**meta.get("versions_by_python", {}), sys.executable: vers}, "inputs": {"clicks": CLICKS_CSV.relative_to(REPO).as_posix(), "p0_run": P0_RUN.as_posix(),
                                                                       "clicks_run": CLICKS_RUN.as_posix(), "imu_root": IMU_ROOT.as_posix(),
                                                                       "sam3": SAM3_WEIGHTS.as_posix(), "dinov3": DINO_CKPT.as_posix()},
                 "params": {"prompts": PROMPTS, "taus": TAUS, "score_floor": SCORE_FLOOR, "cover_px": COVER_PX, "tiles": {"w": TILE_W, "h": TILE_H, "x": TILE_X, "y": TILE_Y},
                            "merge_iou": MERGE_IOU, "n_dev_segments": N_DEV_SEG, "still_share": STILL_SHARE, "n_boot": N_BOOT, "seed": SEED,
                            "crop_in": CROP_IN, "body_crop_in": BODY_CROP_IN, "disc_in": DISC_IN, "pile_link_in": PILE_LINK_IN, "c_grid": C_GRID,
                            "n_shuffle": N_SHUFFLE, "margin": MARGIN, "review_n": REVIEW_N}})
    write_json(mp, meta)
    timings = meta.setdefault("phase_seconds", {})

    def done(ph, t0):
        timings[ph] = round(time.perf_counter() - t0, 1)
        write_json(mp, meta)
    if "data" in a.phases:
        t0 = time.perf_counter()
        meta["data"] = phase_data(run)
        done("data", t0)
    frames, heads, groups = read_tables(run)
    if "t1gpu" in a.phases:
        t0 = time.perf_counter()
        meta["t1gpu"] = phase_t1gpu(run, frames)
        done("t1gpu", t0)
    if "t2gpu" in a.phases:
        t0 = time.perf_counter()
        meta["t2gpu"] = phase_t2gpu(run, frames, heads)
        done("t2gpu", t0)
    if "dino" in a.phases:
        t0 = time.perf_counter()
        import inbox_click_analysis as ica
        fp = pd.read_csv(CLICKS_RUN / "fit_points_primary.csv")
        fit = ica.sim_fit(fp[["p", "q"]].to_numpy(float), fp[["A", "C"]].to_numpy(float), mirror=False)
        meta["house_fit"] = {"px_per_in": 1 / abs(fit["a"]), "theta_house_deg": float(np.degrees(np.angle(fit["a"]))), "n": fit["n"]}
        units = t3_units(heads, frames, groups, fit)
        units.to_csv(run / "t3_units.csv", index=False)
        meta["dino"] = phase_dino(run, units, frames, json.loads((run / "data.json").read_text(encoding="utf-8"))["px_per_in"])
        done("dino", t0)
    if "score" in a.phases:
        t0 = time.perf_counter()
        sv = {}
        for pkg in ("scikit-learn", "scipy", "numpy", "pandas"):
            try:
                sv[pkg] = im.version(pkg)
            except Exception:  # noqa: BLE001
                sv[pkg] = None
        meta["score_versions"] = {**sv, "python": sys.executable}
        phase_score_t1(run, frames, heads)
        phase_score_t2(run, frames, heads)
        phase_score_t3(run, frames, heads, groups, a.jobs)
        done("score", t0)
    if "review" in a.phases:
        t0 = time.perf_counter()
        meta["review"] = {k: v for k, v in phase_review(run, frames, heads, check=not a.no_page_check).items() if k != "page_check"}
        done("review", t0)
    if "sweep_gpu" in a.phases:
        t0 = time.perf_counter()
        meta["sweep_gpu"] = phase_sweep_gpu(run, frames, groups)
        done("sweep_gpu", t0)
    if "sweep" in a.phases:
        t0 = time.perf_counter()
        meta["sweep"] = {k: v for k, v in phase_sweep(run, frames, heads, check=not a.no_page_check).items() if k != "page_check"}
        done("sweep", t0)
    if "gui" in a.phases:
        t0 = time.perf_counter()
        meta["prompt_gui"] = {k: v for k, v in phase_prompt_gui(run, frames, heads, check=not a.no_page_check).items() if k != "page_check"}
        done("gui", t0)
    if "report" in a.phases:
        rp = write_report(run)
        print(f"report: {rp}")
    print(f"run: {run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
