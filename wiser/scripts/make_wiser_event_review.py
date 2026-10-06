# -*- coding: utf-8 -*-
r"""Blind video review of the IMU-WISER consistency audit's events (cohort 2026c): one clip per event, a review page that
asks one question per event and reveals the WISER / IMU panel only AFTER the reviewer has saved a verdict.

Plan: implementation_plan/2026-10-05-wiser-i1-return-test-and-video-review.md, Part 2 (approved by the user 2026-10-05,
committed d722ec0 before any result; deviations in its "Amendment (Part 2)" sections). The PERSON judges every frame; this
script never looks at an image (the self-test checks synthetic luma-coded frames numerically only). Part 1 (the return
test) is a separate driver; its classes are not used here.

EVENTS  from the audit run `wiser_imu_consistency_<ts>/tables/` (V3 track): the 30 largest I1 (`event_list_I1_V3.csv`), the
        30 largest I2 (`event_list_I2_V3.csv`), and 20 I1 drawn at random from `events.csv.gz`, 5 per size quartile (quartile
        edges over ALL V3 I1 events; the top 30 excluded from the pool; pool sorted by (animal, event_id); numpy
        default_rng(seed), seed 20261005, one draw of 5 without replacement per quartile Q1 -> Q4). The 80 are shown in a
        random order (default_rng(seed + 1).permutation) under neutral ids W01..W80, so the list does not reveal which
        events are the extremes.
TIME    the audit's event times are ALIGNED seconds t_al = t_WISER - tau*_a, i.e. the head-IMU / field-PC clock on which the
        events and the IMU states were defined. Clips are cut on that clock by the video FILE-NAME time (field-PC, +-1 s;
        `make_imu_video_review.view_parts` -> `cv/cv_field/grab_frames.segments`, incl. never-renamed segments and the
        previous date folder); never the burnt-in OSD (NVR clock, ~59.5 min behind). The audit's printed lists show
        t_al + tau* (the WISER-stamp time, 0.10-0.20 s later) - below the file-name precision.
CLIP    [t_on - 10 s, min(t_end, t_on + 60 s) + 10 s]; I1: t_on = first second >= 12 in from the run reference, t_end = end
        of the last >= 12-in segment; I2: t_on / t_end = the merged pair window [c_first - 2 s, c_last + 2 s]. The EVENT bar
        covers [t_on, min(t_end, clip end)].
CAMERAS by zone: I1 -> the zone of the run reference P0 = (ref_x, ref_y) (where the rat was before the event; the audit's
        house rule: wiser_rois.json house rectangle grown by 14 in); I2 -> the audit's zone at the window start.
        house_1 -> CH08 in-box + CH05 top-down; house_2 -> CH07 in-box + CH06 top-down; open field -> CH01 + CH02 panoramas
        (stored rotated; shown upright, stacked). Layout, encoder and overlay rendering are make_imu_video_review's
        (imported unchanged): 20 fps H.264 yuv420p, h264_nvenc VBR cq 26 with libx264 crf 24 fallback.
OVERLAY BLIND: rows = "<Wid> . <SFxx> . IR mark . coban . zone" / "<date> . clip start -> end field-PC . cameras . ignore
        the OSD" / "field-PC hh:mm:ss.ss" every 0.25 s + a red "EVENT" box during the event window; per-view labels and
        "NO VIDEO" where a camera has no frames. No WISER displacement, no IMU state, no class, no selection set.
PANEL   (revealed after the verdict; panels/<Wid>_*.png): distance of the raw fixes (dots) and the V3 track (line) from P0
        vs clip time (I1: P0 = the audit reference; I2: P0 = V3 median over the first second of the window), 12-in line;
        the IMU state per second (imu_seconds_cache: 0 unusable, 1 still, 2 active, 3 locomoting); the cumulative head
        turn psi from `turn_net_deg` (+ = CCW from above) and, for I2, the V3 path heading change (1-s differences of
        0.5-s-window V3 medians where >= 10 in/s; display only, not the Phase-0 estimator); an x-y map of the fixes in
        the WISER frame (inches, unverified origin) with the house rectangles. Masked fixes are not drawn.
PAGE    index.html (data embedded, works from file://): event list, video, question, Save verdict & reveal, export.
        I1: "Did this rat actually change place during the EVENT bar?" moved / stayed / cannot tell (+ optional reason);
        I2: "Did the rat's body turn sharply?" turned / ran straight / cannot tell. The FIRST saved verdict is kept as
        `verdict_blind`; a change after the reveal updates `verdict_final` and sets `changed_after_reveal`.
        Export JSON + CSV -> wiser/configs/wiser_event_review_<cohort>/ (commit; Part 1's --with-verdicts reads them).

Outputs (off-repo): `$FIELD2026_ANALYSIS_OUT_ROOT/<c>/wiser_event_review_<ts>/` = `clips/`, `panels/`, `index.html`,
`events.json`, `event_summary.csv`, `selection.csv`, `overlay_ass/`, `_fonts/`, `README.md`, `log.txt`.

Usage (base Python + matplotlib + ffmpeg; node for the self-test and the page check):
  python wiser/scripts/make_wiser_event_review.py --cohort 2026c [--audit-run <dir>] [--root F:\3rd_rat] [--workers 3]
         [--encoder auto|nvenc|x264] [--no-clips] [--only W03 W17]
  python wiser/scripts/make_wiser_event_review.py --html-only <run_dir>      # rebuild index.html from events.json
  python wiser/scripts/make_wiser_event_review.py --selftest                 # synthetic data and video, no field data
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiser" / "src"))
sys.path.insert(0, str(REPO / "wiser" / "scripts"))
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import default_tracks as DT  # noqa: E402  (reader of the production tracks)
import make_imu_video_review as MV  # noqa: E402  (view_parts, layout, render, ASS helpers, identity; imported unchanged)

GF = MV.GF                                     # cv/cv_field/grab_frames (segments, find_ffmpeg), as MV imported it
NAME = "wiser_event_review"
TOOL = "wiser/scripts/make_wiser_event_review.py"
PLAN = "implementation_plan/2026-10-05-wiser-i1-return-test-and-video-review.md"
TZ = "America/New_York"
AUDIT_RUN = r"D:/Field2026_analysis_out/2026c/wiser_imu_consistency_20261005_2038"
TRACKS_ROOT = r"D:/Field2026_analysis_out/2026c/wiser_default_tracks"
IMU_SECONDS_ROOT = r"D:/Field2026_analysis_out/2026c/imu_seconds_cache"
SEED = 20261005
N_TOP = 30
N_PER_Q = 5
PAD_S = 10.0
MAX_EVENT_S = 60.0
DYN_STEP_S = 0.25
DISP_IN = 12.0
MASKS = ["m_handling", "m_silence", "m_tag_validity", "m_adc_lane", "m_off_animal"]
FEMALES_LOCAL = "2026-09-11 19:40:00"         # five non-implanted females released (cohorts/2026c.yaml field_events)
ZONE_CAMS = {"house_1": "house_1", "house_2": "house_2", "field": "outside", "outside": "outside"}
ZONE_LABEL = {"house_1": "house_1", "house_2": "house_2", "outside": "open field"}
STATE_NAMES = {0: "unusable", 1: "still", 2: "active", 3: "locomoting"}
STATE_COLS = {0: "#d9d8d4", 1: "#6aa9e9", 2: "#e8b04b", 3: "#3a9e5c"}
COL = {"v3": "#2a78d6", "raw": "#8a8986", "ev": "#eb6834", "ink": "#0b0b0b", "ink2": "#52514e", "grid": "#d9d8d4"}

QUESTIONS = {
    "I1": {"key": "I1", "short": "I1 · place", "text": "Did this rat actually change place during the EVENT bar?",
           "options": [["moved", "moved (changed place)", "1"], ["stayed", "stayed (in place)", "2"],
                       ["cannot_tell", "cannot tell (rat not visible / identity unsure)", "3"]]},
    "I2": {"key": "I2", "short": "I2 · turn", "text": "Did the rat's body turn sharply (during the EVENT bar)?",
           "options": [["turned", "turned sharply", "1"], ["ran_straight", "ran straight", "2"],
                       ["cannot_tell", "cannot tell (rat not visible / identity unsure)", "3"]]},
}
REASONS = [["not_visible", "rat not visible", "4"], ["identity_unsure", "identity unsure", "5"], ["other", "other (say in the note)", "6"]]
FORBIDDEN_OVERLAY = ("WISER", "IMU", "size", "in/s", "rank", "random", "top-30", "top 30", "quartile", "I1", "I2", "moved", "stayed",
                     "turned", "straight", "°", "displacement", "locomot", "still")


def log(msg: str, fh=None) -> None:
    MV.log(msg, fh)


def fmt_local(ms: float, nd: int = 1) -> str:
    s = f"{MV.ms_to_dt(ms):%Y-%m-%d %H:%M:%S.%f}"
    return s[:-6] + s[-6:-6 + nd] if nd > 0 else s[:-7]


def females_ms() -> int:
    return int(pd.Timestamp(FEMALES_LOCAL).tz_localize(TZ).value // 10**6)


# ====================================================================================================== selection
def quartile_edges(sizes: np.ndarray) -> np.ndarray:
    return np.percentile(np.asarray(sizes, float), [25.0, 50.0, 75.0])


def quartile_of(size: float, edges: np.ndarray) -> int:
    return int(np.searchsorted(edges, size, side="right")) + 1          # Q1 = size < q25 ... Q4 = size >= q75


def select_events(E: pd.DataFrame, L1: pd.DataFrame, L2: pd.DataFrame, taus: dict, seed: int = SEED,
                  n_top: int = N_TOP, n_per_q: int = N_PER_Q) -> tuple[list, dict]:
    """E = the audit's events table (all tracks); L1 / L2 = its top lists. Returns (events in review order, info)."""
    V = E[E["track"] == "V3"]
    I1 = V[V["type"] == "I1"].copy()
    I2 = V[V["type"] == "I2"].copy()
    rows = []
    for typ, L, D in (("I1", L1, I1), ("I2", L2, I2)):
        Lk = L.sort_values("rank").head(n_top)
        m = Lk[["rank", "animal", "event_id"]].merge(D, on=["animal", "event_id"], how="left", validate="one_to_one")
        if m["t0"].isna().any():
            raise ValueError(f"{typ}: top-list events missing from events.csv.gz: {m[m.t0.isna()][['animal', 'event_id']].values.tolist()}")
        # the lists are the n largest by size: confirm against the events table
        top_ids = set(zip(D.sort_values("size", ascending=False).head(n_top)["animal"], D.sort_values("size", ascending=False).head(n_top)["event_id"]))
        if top_ids != set(zip(m["animal"], m["event_id"])):
            raise ValueError(f"{typ}: the top list differs from the {n_top} largest events of events.csv.gz")
        for r in m.to_dict("records"):
            r.update({"selection": "top", "selection_rank": int(r["rank"]), "size_quartile": None})
            rows.append(r)
    edges = quartile_edges(I1["size"].to_numpy())
    top1 = set((r["animal"], int(r["event_id"])) for r in rows if r["type"] == "I1")
    pool = I1[[(a, int(e)) not in top1 for a, e in zip(I1["animal"], I1["event_id"])]].sort_values(["animal", "event_id"], kind="stable")
    q = np.array([quartile_of(s, edges) for s in pool["size"].to_numpy()])
    rng = np.random.default_rng(seed)
    q_counts = {}
    for k in (1, 2, 3, 4):
        P = pool[q == k]
        q_counts[k] = int(len(P))
        pick = rng.choice(len(P), size=min(n_per_q, len(P)), replace=False)
        for j in sorted(pick.tolist()):
            r = P.iloc[j].to_dict()
            r.update({"selection": "random", "selection_rank": None, "size_quartile": k, "rank": None})
            rows.append(r)
    order = np.random.default_rng(seed + 1).permutation(len(rows))
    out = []
    width = max(2, len(str(len(rows))))
    for k, i in enumerate(order.tolist(), start=1):
        r = dict(rows[i])
        r["review_idx"] = k
        r["review_id"] = f"W{k:0{width}d}"
        r["tau_ms"] = float(taus.get(r["animal"], 0.0))
        out.append(r)
    info = {"seed": seed, "n_top": n_top, "n_per_quartile": n_per_q, "i1_total": int(len(I1)), "i2_total": int(len(I2)),
            "i1_quartile_edges_in": [round(float(x), 4) for x in edges], "pool_sizes_by_quartile": q_counts,
            "order_seed": seed + 1}
    return out, info


# ====================================================================================================== windows / zones / identity
def clip_window(t0_ms: int, t1_ms: int, pad_s: float = PAD_S, max_s: float = MAX_EVENT_S) -> dict:
    """Clip [t_on - pad, min(t_end, t_on + max) + pad] (ms) and the EVENT bar in clip seconds."""
    lo = int(t0_ms - pad_s * 1000)
    hi = int(min(t1_ms, t0_ms + max_s * 1000) + pad_s * 1000)
    ev0 = (t0_ms - lo) / 1000.0
    ev1 = (min(t1_ms, hi) - lo) / 1000.0
    return {"lo_ms": lo, "hi_ms": hi, "dur_s": round((hi - lo) / 1000.0, 3), "ev_t0_s": round(ev0, 3), "ev_t1_s": round(ev1, 3),
            "truncated": bool(t1_ms > hi), "continues_s": round(max(0.0, (t1_ms - hi) / 1000.0), 3),
            "event_s": round((t1_ms - t0_ms) / 1000.0, 3)}


def camera_zone(ev: dict, houses: list) -> tuple[str, str]:
    """(zone key of MV.CAMS, explanation)."""
    if ev["type"] == "I1" and np.isfinite(ev.get("ref_x", np.nan)) and np.isfinite(ev.get("ref_y", np.nan)):
        z, _core = MV.house_label(float(ev["ref_x"]), float(ev["ref_y"]), houses)
        return z, "the rat's position before the event (the run reference P0)"
    z = ZONE_CAMS.get(str(ev.get("zone_detail")), "outside")
    return z, "the audit's zone at the window start"


def identity(ids: pd.DataFrame, animal: str, t_ms: float) -> dict:
    d = MV.identity_at(ids, animal, t_ms)
    if d["pattern"] == "?":                       # outside every tag window: the marks do not depend on the tag
        r = ids[ids["animal"] == animal]
        if len(r):
            r0 = r.iloc[0]
            col = str(r0.coband_color)
            m = re.match(r"^\s*([\w/ ]+?)\s*\(\s*([\w/ ]+?)\s+coban from (\d\d)-(\d\d)\s*\)\s*$", col)
            if m:
                ch = pd.Timestamp(f"2026-{m.group(3)}-{m.group(4)}").tz_localize(TZ).value // 10**6
                col = m.group(2) if t_ms >= ch else m.group(1)
            d.update({"pattern": str(r0.pattern), "coban": col, "sticker": str(r0.sticker_color)})
    return d


def identity_rows(ids: pd.DataFrame) -> list:
    rows = []
    for a in sorted(ids["animal"].unique()):
        r = ids[ids["animal"] == a]
        note = ""
        if a == "SF11":
            note = "implant + tag off 09-07 06:10 (no WISER / IMU events after that)"
        rows.append({"animal": a, "tags": ", ".join(sorted(set(r["physical_tag_id"].astype(str)))), "pattern": str(r.iloc[0].pattern),
                     "coban": str(r.iloc[0].coband_color), "sticker": str(r.iloc[0].sticker_color), "note": note})
    return rows


# ====================================================================================================== overlay (blind ASS)
def overlay_rows(rid: str, animal: str, ident: dict, zone: str, cams_text: str, clip: dict) -> list:
    lo, hi = MV.ms_to_dt(clip["lo_ms"]), MV.ms_to_dt(clip["hi_ms"])
    return [f"{rid} · {animal} · IR mark: {ident['pattern']} · coban {ident['coban']} · zone: {ZONE_LABEL.get(zone, zone)}",
            f"{lo:%Y-%m-%d} · clip {lo:%H:%M:%S} → {hi:%H:%M:%S} field-PC (file-name time, ±1 s) · {cams_text} · "
            f"ignore the clock burnt into the image (≈ 59½ min behind)"]


def write_ass_blind(path: Path, lay: dict, static_rows: list, D: float, ev_span: tuple, view_labels: list, view_gaps: list,
                    clip_lo_sod: float, fonts: dict, step: float = DYN_STEP_S) -> dict:
    """Blind overlay: two static rows, the field-PC clock every `step` s, the EVENT box, view labels, NO VIDEO gaps.
    Returns the dialogue timing table (self-test)."""
    W, H, sc = lay["W"], lay["H"], lay["scale"]
    m = max(8, int(round(24 * sc)))
    fs_static, fs_dyn, fs_lab, fs_nov = 52 * sc, 60 * sc, 40 * sc, 72 * sc
    y1, y2, y3 = int(round(12 * sc)), int(round(78 * sc)), int(round(142 * sc))
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2",
             "ScaledBorderAndShadow: yes", "YCbCr Matrix: None", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
             "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
             "MarginV, Encoding",
             f"Style: Static,{MV.FONT_NAME},{fs_static:.0f},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,{max(1, 2 * sc):.0f},0,7,0,0,0,1",
             f"Style: Dyn,{MV.FONT_NAME},{fs_dyn:.0f},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,{max(1, 2 * sc):.0f},0,7,0,0,0,1",
             f"Style: Event,{MV.FONT_NAME},{fs_dyn:.0f},&H00FFFFFF,&H00FFFFFF,&H000000C8,&H000000C8,1,0,0,0,100,100,0,0,3,{max(2, 10 * sc):.0f},0,9,0,0,0,1",
             f"Style: Label,{MV.FONT_NAME},{fs_lab:.0f},&H00FFFFFF,&H00FFFFFF,&H60000000,&H60000000,0,0,0,0,100,100,0,0,3,{max(2, 8 * sc):.0f},0,7,0,0,0,1",
             f"Style: NoVideo,{MV.FONT_NAME},{fs_nov:.0f},&H0000D7FF,&H0000D7FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,{max(1, 3 * sc):.0f},0,5,0,0,0,1",
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    T = {"static": [], "dyn": [], "event": [], "nov": [], "label": []}
    ev_tag = "▶ EVENT"
    for r, y in zip(static_rows, (y1, y2)):
        s = MV.fit_size(r, fs_static, False, W - 2 * m, fonts)
        lines.append(f"Dialogue: 0,{MV.ass_time(0)},{MV.ass_time(D)},Static,,0,0,0,,{{\\pos({m},{y})\\fs{s:.0f}}}{MV.ass_escape(r)}")
        T["static"].append((0.0, D, r))
    nb = int(math.ceil(D / step - 1e-9))
    for k in range(nb):
        a, b = k * step, min(D, (k + 1) * step)
        if b <= a:
            continue
        txt = f"field-PC {MV.hms(clip_lo_sod + a)}"
        lines.append(f"Dialogue: 1,{MV.ass_time(a)},{MV.ass_time(b)},Dyn,,0,0,0,,{{\\pos({m},{y3})}}{MV.ass_escape(txt)}")
        T["dyn"].append((a, b, txt))
    e0, e1 = max(0.0, ev_span[0]), min(D, ev_span[1])
    if e1 > e0:
        lines.append(f"Dialogue: 2,{MV.ass_time(e0)},{MV.ass_time(e1)},Event,,0,0,0,,{{\\pos({W - m},{y3})}}{ev_tag}")
        T["event"].append((e0, e1, ev_tag))
    for v, lab, gaps in zip(lay["views"], view_labels, view_gaps):
        lines.append(f"Dialogue: 1,{MV.ass_time(0)},{MV.ass_time(D)},Label,,0,0,0,,{{\\pos({v['x'] + m},{v['y'] + m})}}{MV.ass_escape(lab)}")
        T["label"].append((0.0, D, lab))
        for ga, gb in gaps:
            lines.append(f"Dialogue: 1,{MV.ass_time(ga)},{MV.ass_time(gb)},NoVideo,,0,0,0,,{{\\pos({v['x'] + v['w'] // 2},{v['y'] + v['h'] // 2})}}"
                         f"NO VIDEO ({MV.ass_escape(lab.split(' ')[0])} has no frames here)")
            T["nov"].append((ga, gb, lab))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return T


# ====================================================================================================== panel data
class TrackCache:
    """Production tracks (unmasked fixes) and IMU seconds, loaded once per (animal, day)."""

    def __init__(self, tracks_root: str, imu_root: str):
        self.tracks_root, self.imu_root = tracks_root, imu_root
        self._tr, self._imu = {}, {}

    def track_day(self, animal: str, day: str) -> pd.DataFrame:
        k = (animal, day)
        if k not in self._tr:
            cols = ["t_ms", "t_al_ms", "x_raw", "y_raw", "anchors_used", "x", "y", "imu_state"] + MASKS
            try:
                F = DT.load_default_track(animal, day, root=self.tracks_root, columns=cols)
            except FileNotFoundError:
                F = pd.DataFrame(columns=cols)
            if len(F):
                msk = np.zeros(len(F), bool)
                for c in MASKS:
                    msk |= F[c].to_numpy(bool)
                F = F[~msk & F["t_al_ms"].notna().to_numpy()].copy()
                F["t_al"] = F["t_al_ms"].astype("float64")
            else:
                F["t_al"] = pd.Series(dtype=float)
            self._tr[k] = F[["t_al", "x_raw", "y_raw", "anchors_used", "x", "y", "imu_state"]].reset_index(drop=True)
        return self._tr[k]

    def imu_day(self, animal: str, day: str) -> pd.DataFrame:
        k = (animal, day)
        if k not in self._imu:
            p = Path(self.imu_root) / animal / f"{day.replace('-', '')}.csv.gz"
            self._imu[k] = (pd.read_csv(p, usecols=["sec", "ok", "state", "turn_net_deg"]) if p.exists()
                            else pd.DataFrame(columns=["sec", "ok", "state", "turn_net_deg"]))
        return self._imu[k]

    def window(self, animal: str, lo_ms: float, hi_ms: float, tau_ms: float) -> tuple[pd.DataFrame, pd.DataFrame]:
        days = sorted({f"{MV.ms_to_dt(t):%Y-%m-%d}" for t in (lo_ms + tau_ms - 2000, hi_ms + tau_ms + 2000, lo_ms, hi_ms)})
        F = pd.concat([self.track_day(animal, d) for d in days], ignore_index=True)
        F = F[(F["t_al"] >= lo_ms) & (F["t_al"] <= hi_ms)].sort_values("t_al").reset_index(drop=True)
        I = pd.concat([self.imu_day(animal, d) for d in days], ignore_index=True)
        I = I[(I["sec"] * 1000 >= lo_ms - 1000) & (I["sec"] * 1000 <= hi_ms)].drop_duplicates("sec").sort_values("sec").reset_index(drop=True)
        return F, I


def medians_on_grid(t: np.ndarray, x: np.ndarray, y: np.ndarray, grid: np.ndarray, half: float = 0.5, minfix: int = 2) -> np.ndarray:
    out = np.full((len(grid), 2), np.nan)
    i0 = np.searchsorted(t, grid - half, "left")
    i1 = np.searchsorted(t, grid + half, "left")
    for k in range(len(grid)):
        if i1[k] - i0[k] >= minfix:
            out[k] = [np.median(x[i0[k]:i1[k]]), np.median(y[i0[k]:i1[k]])]
    return out


def path_heading(t: np.ndarray, x: np.ndarray, y: np.ndarray, grid: np.ndarray, min_speed: float = 10.0) -> np.ndarray:
    """Display heading (deg, unwrapped over finite stretches): direction of p(g + 0.5) - p(g - 0.5), p = median of the
    track over [g' - 0.5, g' + 0.5), only where that 1-s displacement is >= min_speed in."""
    p1 = medians_on_grid(t, x, y, grid + 0.5)
    p0 = medians_on_grid(t, x, y, grid - 0.5)
    v = p1 - p0
    sp = np.hypot(v[:, 0], v[:, 1])
    th = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    th[~(sp >= min_speed)] = np.nan
    f = np.isfinite(th)
    if f.sum() >= 2:
        th[f] = np.degrees(np.unwrap(np.radians(th[f])))
    return th


def cumulative_turn(sec_clip: np.ndarray, turn: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """psi at the second boundaries (clip s): psi(b_0) = 0, psi(b_i+1) = psi(b_i) + turn_i (NaN -> 0, flagged)."""
    T = np.asarray(turn, float)
    gap = ~np.isfinite(T)
    P = np.r_[0.0, np.cumsum(np.where(gap, 0.0, T))]
    b = np.r_[sec_clip, sec_clip[-1] + 1.0] if len(sec_clip) else np.zeros(1)
    return b, P, gap


def rect_corners(roi: dict, buffer_in: float = 0.0) -> np.ndarray:
    th = np.radians(roi.get("orientation_deg", 0.0))
    c, s = np.cos(-th), np.sin(-th)
    hw, hh = roi.get("width_in", 10.0) / 2 + buffer_in, roi.get("height_in", 10.0) / 2 + buffer_in
    L = np.array([[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh], [-hw, -hh]])
    dx = c * L[:, 0] + s * L[:, 1]
    dy = -s * L[:, 0] + c * L[:, 1]
    return np.column_stack([roi["x"] + dx, roi["y"] + dy])


def make_panel(ev: dict, clip: dict, F: pd.DataFrame, I: pd.DataFrame, houses: list, path: Path) -> dict:
    """Static panel (PNG). F: unmasked fixes (t_al ms, x_raw, y_raw, x, y); I: IMU seconds. Returns summary numbers."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec

    lo, D = float(clip["lo_ms"]), float(clip["dur_s"])
    e0, e1 = clip["ev_t0_s"], clip["ev_t1_s"]
    t = (F["t_al"].to_numpy(float) - lo) / 1000.0 if len(F) else np.zeros(0)
    xr, yr = (F["x_raw"].to_numpy(float), F["y_raw"].to_numpy(float)) if len(F) else (np.zeros(0), np.zeros(0))
    xv, yv = (F["x"].to_numpy(float), F["y"].to_numpy(float)) if len(F) else (np.zeros(0), np.zeros(0))
    if ev["type"] == "I1":
        P0 = np.array([float(ev["ref_x"]), float(ev["ref_y"])])
        p0_txt = "P0 = the audit reference (median of the V3 1-s medians over the first 2 s of the trimmed run)"
    else:
        k = (t >= e0) & (t < e0 + 1.0)
        P0 = np.array([np.median(xv[k]), np.median(yv[k])]) if k.sum() else (np.array([np.median(xv), np.median(yv)]) if len(xv) else np.array([np.nan, np.nan]))
        p0_txt = "P0 = V3 median over the first second of the window"
    dr = np.hypot(xr - P0[0], yr - P0[1])
    dv = np.hypot(xv - P0[0], yv - P0[1])

    fig = plt.figure(figsize=(14.0, 5.6), dpi=100)
    fig.patch.set_facecolor("white")
    gs = GridSpec(3, 2, width_ratios=[2.35, 1.0], height_ratios=[2.2, 0.42, 1.35], hspace=0.10, wspace=0.10,
                  left=0.06, right=0.985, top=0.86, bottom=0.15)
    ax_d = fig.add_subplot(gs[0, 0])
    ax_s = fig.add_subplot(gs[1, 0], sharex=ax_d)
    ax_g = fig.add_subplot(gs[2, 0], sharex=ax_d)
    ax_m = fig.add_subplot(gs[:, 1])
    for ax in (ax_d, ax_s, ax_g):
        ax.axvspan(e0, e1, color=COL["ev"], alpha=0.12, lw=0)
        ax.set_xlim(0, D)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    # ---- distance from P0
    ax_d.scatter(t, dr, s=7, color=COL["raw"], alpha=0.65, lw=0, label="raw fixes", zorder=2)
    ax_d.plot(t, dv, color=COL["v3"], lw=1.6, label="V3 track", zorder=3)
    if ev["type"] == "I1":
        ax_d.axhline(DISP_IN, color=COL["ink2"], ls="--", lw=0.9, zorder=1)
        ax_d.text(0.3, DISP_IN, " 12 in", va="bottom", ha="left", fontsize=8, color=COL["ink2"])
        r0 = (float(ev["run_t0"]) * 1000.0 - lo) / 1000.0
        r1 = (float(ev["run_t1"]) * 1000.0 - lo) / 1000.0
        if 0 <= r0 + 2 and r0 <= D:
            ax_d.axvspan(max(0, r0), min(D, r0 + 2.0), color=COL["ink2"], alpha=0.12, lw=0)
        for rr, lab in ((r0, "run start"), (r1, "run end")):
            if 0 <= rr <= D:
                ax_d.axvline(rr, color=COL["ink2"], lw=0.8, ls=":")
                ax_d.text(rr, 0.98, f" {lab}", transform=ax_d.get_xaxis_transform(), fontsize=7.5, color=COL["ink2"], va="top")
    ymax = max(30.0, 1.08 * float(np.nanmax(np.r_[dr, dv, 0.0])) if len(dr) else 30.0)
    ax_d.set_ylim(0, ymax)
    ax_d.set_ylabel("distance from P0 (in)", fontsize=9)
    ax_d.grid(axis="y", color=COL["grid"], lw=0.6)
    ax_d.legend(loc="upper left", fontsize=8, frameon=False, ncol=2)
    plt.setp(ax_d.get_xticklabels(), visible=False)
    # ---- IMU state row
    sec_clip = (I["sec"].to_numpy(float) * 1000.0 - lo) / 1000.0 if len(I) else np.zeros(0)
    st = np.where(I["ok"].astype(bool).to_numpy(), I["state"].to_numpy(int), 0) if len(I) else np.zeros(0, int)
    for a, s_ in zip(sec_clip, st):
        ax_s.axvspan(a, a + 1.0, color=STATE_COLS.get(int(s_), "#ffffff"), lw=0)
    ax_s.set_yticks([])
    ax_s.set_ylabel("IMU", fontsize=9, rotation=0, ha="right", va="center")
    handles = [plt.Rectangle((0, 0), 1, 1, color=STATE_COLS[k]) for k in (1, 2, 3, 0)]
    fig.legend(handles, [f"IMU state: {STATE_NAMES[1]}"] + [STATE_NAMES[k] for k in (2, 3, 0)], loc="lower left",
               bbox_to_anchor=(0.055, 0.0), ncol=4, fontsize=8, frameon=False, handlelength=1.2)
    plt.setp(ax_s.get_xticklabels(), visible=False)
    # ---- head turn (+ path heading for I2)
    turn_info = {}
    if len(I):
        b, P, gap = cumulative_turn(sec_clip, I["turn_net_deg"].to_numpy(float))
        ref_t = e0 if ev["type"] == "I1" else (float(ev["c_max"]) * 1000.0 - lo) / 1000.0 - 1.0
        psi_ref = float(np.interp(ref_t, b, P))
        ax_g.plot(b, P - psi_ref, color=COL["ink2"], lw=1.4, label="head turn ψ (gyro, cumulative)")
        for a, g_ in zip(sec_clip, gap):
            if g_:
                ax_g.axvspan(a, a + 1.0, color="#000000", alpha=0.06, lw=0)
        turn_info["psi_range_deg"] = round(float(np.nanmax(P) - np.nanmin(P)), 1)
    if ev["type"] == "I2" and len(t) > 3:
        grid = np.arange(0.0, D + 1e-9, 0.25)
        th = path_heading(t, xv, yv, grid)
        cm = (float(ev["c_max"]) * 1000.0 - lo) / 1000.0
        f = np.isfinite(th)
        if f.any():
            j = int(np.argmin(np.where(f, np.abs(grid - (cm - 1.0)), np.inf)))
            ax_g.plot(grid, th - th[j], color=COL["ev"], lw=1.4, label="V3 path heading (display)")
        for xx in (cm - 1.0, cm + 1.0):
            ax_g.axvline(xx, color=COL["ev"], lw=0.8, ls=":")
    ax_g.axhline(0, color=COL["grid"], lw=0.8)
    ax_g.set_ylabel("turn (°, + = CCW)", fontsize=9)
    ax_g.set_xlabel(f"clip time (s) = the video's time axis; clip {MV.ms_to_dt(lo):%H:%M:%S} → {MV.ms_to_dt(lo + 1000 * D):%H:%M:%S} field-PC",
                    fontsize=9)
    ax_g.grid(axis="y", color=COL["grid"], lw=0.6)
    ax_g.legend(loc="upper left", fontsize=8, frameon=False, ncol=2)
    # ---- x-y map
    for roi in houses:
        cc = rect_corners(roi)
        ax_m.plot(cc[:, 0], cc[:, 1], color=COL["ink2"], lw=1.0)
        ax_m.text(roi["x"], roi["y"], roi["name"], fontsize=7.5, color=COL["ink2"], ha="center", va="center")
    if len(t):
        sc = ax_m.scatter(xr, yr, c=t, cmap="viridis", s=8, lw=0, alpha=0.8, vmin=0, vmax=D, zorder=2)
        ax_m.plot(xv, yv, color=COL["v3"], lw=1.0, alpha=0.8, zorder=3)
        ke = (t >= e0) & (t <= e1)
        ax_m.plot(np.where(ke, xv, np.nan), np.where(ke, yv, np.nan), color=COL["ev"], lw=2.0, zorder=4)
        cb = fig.colorbar(sc, ax=ax_m, fraction=0.04, pad=0.01)
        cb.set_label("clip time (s)", fontsize=8)
        cb.ax.tick_params(labelsize=7)
    if np.all(np.isfinite(P0)):
        ax_m.plot(P0[0], P0[1], marker="*", ms=13, color=COL["ink"], zorder=5)
        if ev["type"] == "I1":
            a_ = np.linspace(0, 2 * np.pi, 120)
            ax_m.plot(P0[0] + DISP_IN * np.cos(a_), P0[1] + DISP_IN * np.sin(a_), color=COL["ink"], lw=0.8, ls="--", zorder=5)
    pts = np.r_[np.column_stack([xr, yr]), np.column_stack([xv, yv]), P0[None, :]]
    pts = pts[np.all(np.isfinite(pts), axis=1)]
    if len(pts):
        lo_xy = np.percentile(pts, 1, axis=0) - 12
        hi_xy = np.percentile(pts, 99, axis=0) + 12
        ctr, span = (lo_xy + hi_xy) / 2, max(48.0, float(np.max(hi_xy - lo_xy)))
        ax_m.set_xlim(ctr[0] - span / 2, ctr[0] + span / 2)
        ax_m.set_ylim(ctr[1] - span / 2, ctr[1] + span / 2)
    ax_m.set_aspect("equal", adjustable="box")
    ax_m.set_xlabel("WISER x (in, unverified origin)", fontsize=8.5)
    ax_m.set_ylabel("WISER y (in)", fontsize=8.5)
    ax_m.tick_params(labelsize=7.5)
    ax_m.set_title("★ P0 · orange = V3 during the EVENT bar", fontsize=8.5, color=COL["ink2"])
    for ax in (ax_d, ax_s, ax_g):
        ax.tick_params(labelsize=8)
    title = (f"{ev['review_id']} · {ev['type']} · {ev['animal']} · {fmt_local(float(ev['t0']) * 1000.0)} field-PC — "
             f"revealed after the verdict")
    if ev["type"] == "I1":
        sub = (f"audit: size {float(ev['size']):.1f} in, {int(ev['dur_s'])} s ≥ 12 in in {int(ev['n_segments'])} segment(s), "
               f"run {int(ev['run_len_s'])} s ({ev['subtype']}); {p0_txt}")
    else:
        sub = (f"audit: Δθ {float(ev['dtheta']):.0f}° path vs Δψ {float(ev['dpsi']):.0f}° head (W = 2 s at the dotted lines), "
               f"speeds {float(ev['spd1']):.0f} / {float(ev['spd2']):.0f} in/s; {p0_txt}")
    fig.suptitle(title, x=0.06, ha="left", fontsize=11.5, fontweight="bold", y=0.975)
    fig.text(0.06, 0.905, sub, fontsize=9, color=COL["ink2"], ha="left")
    fig.savefig(path, dpi=100, facecolor="white")
    plt.close(fig)
    k_ev = (t >= e0) & (t <= e1)
    return {"n_fix": int(len(t)), "n_fix_event": int(k_ev.sum()), "max_raw_in": round(float(np.nanmax(dr)), 1) if len(dr) else None,
            "max_v3_in": round(float(np.nanmax(dv)), 1) if len(dv) else None, "imu_seconds": int(len(I)),
            "P0": [round(float(P0[0]), 2), round(float(P0[1]), 2)] if np.all(np.isfinite(P0)) else None, **turn_info}


# ====================================================================================================== one event
def reveal_facts(ev: dict, info: dict, clip: dict, cam_zone: str, cam_why: str, panel: dict) -> list:
    f = []
    if ev["selection"] == "top":
        tot = info["i1_total"] if ev["type"] == "I1" else info["i2_total"]
        f.append(["selection", f"top-{info['n_top']} largest V3 {ev['type']} (rank {ev['selection_rank']} of {tot:,})"])
    else:
        e = info["i1_quartile_edges_in"]
        rng_ = {1: f"< {e[0]:.1f} in", 2: f"{e[0]:.1f}–{e[1]:.1f} in", 3: f"{e[1]:.1f}–{e[2]:.1f} in", 4: f"≥ {e[2]:.1f} in"}[int(ev["size_quartile"])]
        f.append(["selection", f"random V3 I1, size quartile Q{int(ev['size_quartile'])} ({rng_}); {info['n_per_quartile']} per quartile, "
                               f"top {info['n_top']} excluded, seed {info['seed']}"])
    f.append(["audit event", f"{ev['animal']} · V3 · {ev['type']} · event_id {int(ev['event_id'])}"])
    le6 = (float(ev["n_le6"]) / float(ev["n"])) if float(ev["n"]) else float("nan")
    if ev["type"] == "I1":
        f.append(["size", f"{float(ev['size']):.1f} in = max distance of the V3 1-s medians from the run reference"])
        f.append(["duration", f"{int(ev['dur_s'])} s ≥ 12 in in {int(ev['n_segments'])} segment(s); event window {clip['event_s']:.0f} s"
                              + (f" (the clip shows the first {MAX_EVENT_S:.0f} s + 10 s; {clip['continues_s']:.0f} s more after the clip)" if clip["truncated"] else "")])
        f.append(["no-locomotion run", f"{int(ev['run_len_s'])} s trimmed, {fmt_local(float(ev['run_t0']) * 1000.0, 0)[11:]} → "
                                       f"{fmt_local(float(ev['run_t1']) * 1000.0, 0)[11:]}, subtype {ev['subtype']}"])
        f.append(["P0", f"({float(ev['ref_x']):.1f}, {float(ev['ref_y']):.1f}) in (WISER frame, unverified origin)"])
    else:
        f.append(["turn", f"path Δθ {float(ev['dtheta']):.1f}° vs head Δψ {float(ev['dpsi']):.1f}° (W = 2 s at the centre of max); "
                          f"speeds {float(ev['spd1']):.1f} / {float(ev['spd2']):.1f} in/s; {int(ev['n_centres'])} centre(s) merged"])
    f.append(["cameras", f"{ZONE_LABEL.get(cam_zone, cam_zone)} from {cam_why}"])
    f.append(["strata (audit)", f"zone at onset {ev['zone_detail']} · {ev['dn']} · weather {ev['wx']}"])
    f.append(["raw fixes in the event window", f"{int(ev['n'])} fixes, ≤ 6 anchors {100 * le6:.0f} %, anchors median {float(ev['anchors_med']):.1f}, "
                                               f"dispersion median {float(ev['disp_med']):.1f} in"])
    if panel:
        f.append(["panel window", f"{panel.get('n_fix', 0)} unmasked fixes, {panel.get('imu_seconds', 0)} IMU seconds; max distance from P0: raw "
                                  f"{panel.get('max_raw_in')} in, V3 {panel.get('max_v3_in')} in"])
    return f


def build_event(ev: dict, info: dict, houses: list, ids: pd.DataFrame, root: Path, ffprobe: str, out_dir: Path, fonts: dict,
                cache: TrackCache | None, scale: float = 1.0, audit_run: str = "") -> tuple[dict, dict]:
    t0_ms = int(round(float(ev["t0"]) * 1000.0))
    t1_ms = int(round(float(ev["t1"]) * 1000.0))
    clip = clip_window(t0_ms, t1_ms)
    clip_lo, clip_hi = MV.ms_to_dt(clip["lo_ms"]), MV.ms_to_dt(clip["hi_ms"])
    clip_lo_sod = clip_lo.hour * 3600 + clip_lo.minute * 60 + clip_lo.second + clip_lo.microsecond / 1e6
    ident = identity(ids, ev["animal"], t0_ms)
    zone, why = camera_zone(ev, houses)
    cams = MV.CAMS[zone]
    lay = MV.layout(zone, scale)
    vparts, vgaps, labels = [], [], []
    for cam, role in cams:
        parts, gaps = MV.view_parts(root, cam, clip_lo, clip_hi, ffprobe)
        vparts.append(parts)
        vgaps.append(gaps)
        labels.append(f"{cam} · {role}")
    cams_text = (f"{cams[0][0]} + {cams[1][0]} panoramas" if zone == "outside" else f"{cams[0][0]} in-box + {cams[1][0]} top-down")
    rid = ev["review_id"]
    st = MV.ms_to_dt(t0_ms)
    stem = f"{rid}_{ev['type']}_{ev['animal']}_{st:%Y%m%d_%H%M%S}"
    rows = overlay_rows(rid, ev["animal"], ident, zone, cams_text, clip)
    T = write_ass_blind(out_dir / "overlay_ass" / f"{stem}.ass", lay, rows, clip["dur_s"], (clip["ev_t0_s"], clip["ev_t1_s"]),
                        labels, vgaps, clip_lo_sod, fonts)
    has_video = any(len(p) for p in vparts)
    missing = ""
    if not has_video:
        missing = f"no video file of {cams[0][0]} or {cams[1][0]} covers {clip_lo:%Y-%m-%d %H:%M:%S} → {clip_hi:%H:%M:%S} under {root}"
    cam_notes = [f"{c} has no frames {', '.join(f'{a:.1f}–{b:.1f} s' for a, b in g)}" for (c, _), g in zip(cams, vgaps) if g]
    panel = {}
    panel_file = f"{stem}.png"
    if cache is not None:
        F, I = cache.window(ev["animal"], clip["lo_ms"], clip["hi_ms"], float(ev["tau_ms"]))
        panel = make_panel(ev, clip, F, I, houses, out_dir / "panels" / panel_file)
    pop = (f"after {FEMALES_LOCAL[:16]}: five non-implanted females (no marks stated) are also in the paddock"
           if t0_ms >= females_ms() else "")
    q = QUESTIONS[ev["type"]]
    payload = {
        "idx": int(ev["review_idx"]), "id": rid, "type": ev["type"], "question": q, "animal": ev["animal"],
        "event_key": f"{ev['animal']}|V3|{ev['type']}|{int(ev['event_id'])}", "audit_event_id": int(ev["event_id"]),
        "selection": ev["selection"], "selection_rank": ev["selection_rank"],
        "size_quartile": None if ev["size_quartile"] is None else int(ev["size_quartile"]),
        "onset_local": fmt_local(t0_ms), "end_local": fmt_local(t1_ms), "onset_al_ms": t0_ms, "end_al_ms": t1_ms,
        "tau_ms": float(ev["tau_ms"]), "identity": ident, "zone": zone, "zone_label": ZONE_LABEL.get(zone, zone),
        "zone_why": why, "cams_text": cams_text, "overlay_static": rows, "population_note": pop,
        "cams": [{"cam": c, "role": r, "parts": [{k: p[k] for k in ("file", "offset_s", "dur_s", "clip_t0_s", "seg_start", "seg_end_by_name",
                                                                     "file_duration_s")} for p in pp], "gaps": gg}
                 for (c, r), pp, gg in zip(cams, vparts, vgaps)],
        "cam_notes": cam_notes,
        "clip": {"file": f"{stem}.mp4", "ok": False, "missing_reason": missing, "lo_local": fmt_local(clip["lo_ms"], 3),
                 "hi_local": fmt_local(clip["hi_ms"], 3), "lo_ms": clip["lo_ms"], "hi_ms": clip["hi_ms"], "lo_sod": round(clip_lo_sod, 3),
                 "dur_s": clip["dur_s"], "ev_t0_s": clip["ev_t0_s"], "ev_t1_s": clip["ev_t1_s"], "truncated": clip["truncated"],
                 "continues_s": clip["continues_s"], "event_s": clip["event_s"], "fps": MV.FPS, "width": lay["W"], "height": lay["H"]},
        "panel": {"file": panel_file, "ok": bool(panel), **({"summary": panel} if panel else {})},
        "reveal": {"facts": reveal_facts(ev, info, clip, zone, why, panel)},
        "audit_run": audit_run,
    }
    job = {"id": rid, "out": str(out_dir / "clips" / f"{stem}.mp4"), "layout": lay, "view_parts": vparts, "D": clip["dur_s"],
           "ass_rel": f"overlay_ass/{stem}.ass", "fonts_rel": "_fonts", "timing": T, "has_video": has_video}
    return payload, job


# ====================================================================================================== HTML
HTML_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WISER Event Review</title>
<style>
:root{--bg:#0f1216;--panel:#181d23;--panel2:#20262e;--line:#2c343d;--fg:#e6e9ee;--mut:#97a1ac;--acc:#4da3ff;--ok:#3fb950;--warn:#d29922;--bad:#f85149}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.4 system-ui,"Segoe UI",sans-serif;height:100vh;display:flex;flex-direction:column}
header{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:6px 10px;background:var(--panel);border-bottom:1px solid var(--line)}
header b{font-size:14px}
button,.btn{background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:4px;padding:3px 9px;cursor:pointer;font:inherit}
button:hover,.btn:hover{border-color:var(--acc)}
button.primary{background:#1f3550;border-color:#2f5d8a}
input,select,textarea{background:#0b0e12;color:var(--fg);border:1px solid var(--line);border-radius:4px;font:inherit;padding:2px 5px}
main{flex:1;display:grid;grid-template-columns:270px minmax(0,1fr) 360px;min-height:0}
#list{overflow:auto;border-right:1px solid var(--line);background:var(--panel)}
#filters{display:flex;gap:4px;padding:6px;position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--line)}
#filters select{flex:1;min-width:0}
.item{padding:5px 8px;border-bottom:1px solid var(--line);cursor:pointer}
.item:hover{background:var(--panel2)}
.item.sel{background:#1f3550}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;background:#555}
.dot.partial{background:var(--warn)}.dot.done{background:var(--ok)}
.tag{display:inline-block;padding:0 5px;border-radius:3px;font-size:11px;background:#333}
.t-I1{background:#1d4e89}.t-I2{background:#6b5310}
.mut{color:var(--mut)}
#centre{display:flex;flex-direction:column;min-width:0;overflow:auto;padding:6px 8px;gap:6px}
#evhead{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:6px 8px}
#evhead .row1{font-weight:600}
video{width:100%;max-height:62vh;background:#000;border-radius:4px}
#controls{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
#tread{font-variant-numeric:tabular-nums;color:var(--mut)}
#evbar{position:relative;height:10px;background:#0a0c0f;border:1px solid var(--line);border-radius:3px;cursor:pointer}
#evbar .ev{position:absolute;top:0;bottom:0;background:#c80000;opacity:.75}
#evbar .cur{position:absolute;top:-2px;bottom:-2px;width:2px;background:#ffd600}
.box{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:6px 8px}
#reveal img{width:100%;background:#fff;border-radius:3px;display:block;margin:4px 0}
#locked{color:var(--mut);padding:10px 4px}
#right{overflow:auto;border-left:1px solid var(--line);padding:8px;background:var(--panel)}
fieldset{border:1px solid var(--line);border-radius:4px;margin:0 0 8px;padding:5px 8px}
fieldset[disabled]{opacity:.45}
legend{color:var(--acc);padding:0 4px}
.qtext{font-weight:600;margin:2px 0 5px}
.opt{display:block;padding:2px 0;cursor:pointer}
.opt kbd,.kbd{display:inline-block;min-width:16px;text-align:center;border:1px solid var(--line);border-radius:3px;background:#0b0e12;color:var(--mut);font-size:11px;margin-right:5px;padding:0 3px}
textarea{width:100%;min-height:60px}
table{border-collapse:collapse;width:100%}
td,th{border-bottom:1px solid var(--line);padding:2px 4px;text-align:left;vertical-align:top;font-size:12px}
th{color:var(--mut);font-weight:500}
#help{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:10}
#help.show{display:flex}
#help .card{background:var(--panel);border:1px solid var(--line);border-radius:6px;max-width:960px;max-height:88vh;overflow:auto;padding:14px 18px}
#saved{color:var(--mut);font-size:12px}
.warnline{color:var(--warn)}
#vstate{margin:4px 0 8px;font-size:12px}
</style></head>
<body>
<header>
 <b>WISER event review (blind) · cohort __COHORT__</b>
 <span id="progress"></span>
 <label>Reviewer <input id="reviewer" size="8" placeholder="initials"></label>
 <button id="btnJson" title="download all verdicts as JSON">Export JSON</button>
 <button id="btnCsv" title="download all verdicts as CSV">Export CSV</button>
 <label class="btn" title="load a previously exported JSON">Import<input type="file" id="importFile" accept=".json,application/json" hidden></label>
 <button id="btnHelp">Help (?)</button>
 <span id="saved"></span>
</header>
<main>
 <aside id="list">
  <div id="filters">
   <select id="fType"><option value="">all questions</option><option value="I1">I1 · place</option><option value="I2">I2 · turn</option></select>
   <select id="fAnimal"><option value="">all rats</option></select>
   <select id="fStatus"><option value="">any status</option><option value="todo">to do</option><option value="partial">answered, not saved</option><option value="done">verdict saved</option></select>
  </div>
  <div id="events"></div>
 </aside>
 <section id="centre">
  <div id="evhead"></div>
  <video id="vid" preload="auto" muted playsinline></video>
  <div id="evbar" title="red = EVENT window; yellow = current time; click to seek"><div class="ev" id="evbarEv"></div><div class="cur" id="evbarCur"></div></div>
  <div id="controls">
   <button id="bPlay" title="Space">▶ / ❚❚</button>
   <button id="bBack1" title="Shift+←">−1 s</button>
   <button id="bBackF" title="←">−1 frame</button>
   <button id="bFwdF" title="→">+1 frame</button>
   <button id="bFwd1" title="Shift+→">+1 s</button>
   <button id="bEvent" title="j">⇥ EVENT start</button>
   <label>speed <select id="speed"></select></label>
   <span id="tread"></span>
  </div>
  <div class="box" id="camreason"></div>
  <div class="box" id="reveal">
   <b>WISER / IMU panel</b>
   <div id="locked">Hidden until you save a verdict for this event (blind review). Judge from the video only.</div>
   <div id="revealBody" hidden>
    <div id="revealNote" class="mut"></div>
    <img id="panelImg" alt="WISER / IMU panel">
    <table id="facts"></table>
   </div>
  </div>
 </section>
 <aside id="right">
  <div id="form"></div>
  <button id="bSave" class="primary" style="width:100%;margin:2px 0 6px">Save verdict &amp; reveal (Enter)</button>
  <button id="bNext" style="width:100%;margin:0 0 10px">Next event (n)</button>
  <div class="box"><b>Identity cues</b> <span class="mut">(IR frames are monochrome: use the pattern; coban colour only in colour frames)</span>
   <table id="idtab"></table></div>
 </aside>
</main>
<div id="help"><div class="card" id="helpcard"></div></div>
<script>
"use strict";
// ------------------------------------------------------------------ data + pure logic (no DOM; the self-test runs this block in node)
const DATA = __DATA_JSON__;
const EV = DATA.events;
const REASONS = DATA.reasons;
let J = {}, reviewer = "";
function nowIso(){ return new Date().toISOString(); }
function evById(id){ return EV.find(e => e.id === id); }
function jget(id){
  if (!J[id]) J[id] = {verdict: "", reason: "", note: "", verdict_blind: "", reason_blind: "", saved_at: "", revealed_at: "",
                       changed_after_reveal: false, n_changes_after_reveal: 0, reviewer: "", updated: ""};
  return J[id];
}
function isRevealed(id){ const j = J[id]; return !!(j && j.revealed_at); }
function status(id){
  const j = J[id]; if (!j) return "todo";
  if (j.revealed_at) return "done";
  return (j.verdict || j.reason || j.note) ? "partial" : "todo";
}
function validAnswer(id, v){ const ev = evById(id); return !!ev && ev.question.options.some(o => o[0] === v); }
function setAnswer(id, v){
  if (!validAnswer(id, v)) return false;
  const j = jget(id);
  if (j.revealed_at && j.verdict !== v) { j.changed_after_reveal = true; j.n_changes_after_reveal = (j.n_changes_after_reveal || 0) + 1; }
  j.verdict = v;
  if (v !== "cannot_tell") j.reason = "";
  j.updated = nowIso(); j.reviewer = reviewer;
  return true;
}
function setReason(id, r){
  const j = jget(id);
  if (j.verdict !== "cannot_tell" || !REASONS.some(o => o[0] === r)) return false;
  j.reason = (j.reason === r) ? "" : r;
  j.updated = nowIso(); j.reviewer = reviewer;
  return true;
}
function setNote(id, t){ const j = jget(id); j.note = String(t); j.updated = nowIso(); j.reviewer = reviewer; }
function saveVerdict(id){
  const j = jget(id);
  if (!j.verdict) return {ok: false, msg: "Choose an answer first."};
  if (!j.revealed_at) { j.verdict_blind = j.verdict; j.reason_blind = j.reason; j.saved_at = nowIso(); j.revealed_at = j.saved_at; }
  j.updated = nowIso(); j.reviewer = reviewer;
  return {ok: true, msg: ""};
}
function exportRows(){
  return EV.map(ev => { const j = J[ev.id] || {};
    return {review_id: ev.id, idx: ev.idx, type: ev.type, animal: ev.animal, event_key: ev.event_key, audit_event_id: ev.audit_event_id,
      track: "V3", selection: ev.selection, selection_rank: ev.selection_rank == null ? "" : ev.selection_rank,
      size_quartile: ev.size_quartile == null ? "" : ev.size_quartile, onset_local: ev.onset_local, end_local: ev.end_local,
      onset_al_ms: ev.onset_al_ms, end_al_ms: ev.end_al_ms, clip: ev.clip.file, clip_ok: ev.clip.ok, zone: ev.zone, cameras: ev.cams_text,
      question: ev.question.text, verdict: j.verdict_blind || "", verdict_blind: j.verdict_blind || "", reason_blind: j.reason_blind || "", verdict_final: j.verdict || "",
      reason_final: j.reason || "", changed_after_reveal: !!j.changed_after_reveal, n_changes_after_reveal: j.n_changes_after_reveal || 0,
      note: j.note || "", saved_at: j.saved_at || "", revealed_at: j.revealed_at || "", reviewer: j.reviewer || reviewer,
      updated: j.updated || "", status: status(ev.id)}; });
}
function exportObject(){
  return {schema: "wiser_event_review_labels/1", cohort: DATA.cohort, run_id: DATA.run_id, run_dir: DATA.run_dir, tool: DATA.tool,
    plan: DATA.plan, audit_run: DATA.audit_run, selection: DATA.selection, exported_local: new Date().toString(), reviewer: reviewer,
    n_events: EV.length, n_saved: EV.filter(e => isRevealed(e.id)).length,
    note: "verdict_blind = the first saved verdict, given before the panel was shown; verdict_final = the answer at export time",
    rows: exportRows(), judgements: J};
}
function csvText(){
  const R = exportRows(), cols = Object.keys(R[0]);
  const q = v => { const s = String(v == null ? "" : v); return /[",\n\r]/.test(s) ? "\"" + s.replace(/"/g, "\"\"") + "\"" : s; };
  return [cols.join(",")].concat(R.map(r => cols.map(c => q(r[c])).join(","))).join("\r\n") + "\r\n";
}
function importObject(o){
  const src = (o && o.judgements) || {}; let n = 0;
  Object.keys(src).forEach(id => { if (src[id] && evById(id)) { J[id] = Object.assign(jget(id), src[id]); n++; } });
  if (o && o.reviewer && !reviewer) reviewer = o.reviewer;
  return n;
}
</script>
<script>
"use strict";
// ------------------------------------------------------------------ UI
const SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2];
const KEY = "wiser_event_review_" + DATA.run_id;
const $ = id => document.getElementById(id);
const vid = $("vid");
let cur = 0, rate = 1, flash = "";
const filt = {type: "", animal: "", status: ""};

function esc(s){ return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }
function clock(sod){
  sod = ((sod % 86400) + 86400) % 86400;
  const h = Math.floor(sod / 3600), m = Math.floor((sod - 3600 * h) / 60), s = sod - 3600 * h - 60 * m;
  return String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0") + ":" + s.toFixed(2).padStart(5, "0");
}
function loadState(){
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || "null");
    if (s && typeof s === "object") {
      J = s.judgements || {}; reviewer = s.reviewer || "";
      if (Number.isInteger(s.cur) && s.cur >= 0 && s.cur < EV.length) cur = s.cur;
      if (typeof s.rate === "number") rate = s.rate;
    }
  } catch (e) { console.warn("localStorage unavailable", e); }
}
function saveState(){
  try {
    localStorage.setItem(KEY, JSON.stringify({judgements: J, reviewer: reviewer, cur: cur, rate: rate, saved: nowIso()}));
    $("saved").textContent = "autosaved " + new Date().toLocaleTimeString();
  } catch (e) { $("saved").innerHTML = "<span class='warnline'>autosave unavailable — Export often</span>"; }
}

// ---------------------------------------------------------------- list
function renderList(){
  const box = $("events"); box.innerHTML = "";
  let nd = 0;
  EV.forEach((ev, i) => {
    const s = status(ev.id); if (s === "done") nd++;
    if (filt.type && ev.type !== filt.type) return;
    if (filt.animal && ev.animal !== filt.animal) return;
    if (filt.status && s !== filt.status) return;
    const d = document.createElement("div");
    d.className = "item" + (i === cur ? " sel" : "");
    d.innerHTML = "<span class='dot " + s + "'></span><b>" + esc(ev.id) + "</b> <span class='tag t-" + esc(ev.type) + "'>" + esc(ev.question.short) +
      "</span> <b>" + esc(ev.animal) + "</b><br><span class='mut'>" + esc(ev.onset_local.slice(5, 19)) + " · " + esc(ev.zone_label) +
      (ev.clip.ok ? "" : " · <span class='warnline'>no clip</span>") + "</span>";
    d.onclick = () => select(i);
    box.appendChild(d);
  });
  $("progress").textContent = nd + " / " + EV.length + " verdicts saved";
}

// ---------------------------------------------------------------- event
function select(i){
  cur = Math.max(0, Math.min(EV.length - 1, i));
  const ev = EV[cur];
  flash = "";
  if (ev.clip.ok) { vid.defaultPlaybackRate = rate; vid.src = "clips/" + ev.clip.file; vid.load(); vid.playbackRate = rate; }
  else { vid.pause(); vid.removeAttribute("src"); vid.load(); }
  renderHead(); renderForm(); renderReveal(); renderList(); drawBar(); saveState();
  const it = document.querySelector(".item.sel"); if (it) it.scrollIntoView({block: "nearest"});
}
function renderHead(){
  const ev = EV[cur], c = ev.clip;
  let h = "<div class='row1'>" + esc(ev.id) + " · " + esc(ev.question.short) + " · " + esc(ev.animal) + " · IR mark: " + esc(ev.identity.pattern) +
    " · coban " + esc(ev.identity.coban) + " · " + esc(ev.zone_label) + " (" + esc(ev.cams_text) + ")</div>" +
    "<div>" + esc(c.lo_local.slice(0, 10)) + " · clip " + esc(c.lo_local.slice(11, 19)) + " → " + esc(c.hi_local.slice(11, 19)) +
    " field-PC (" + c.dur_s.toFixed(0) + " s) · EVENT bar at " + c.ev_t0_s.toFixed(1) + "–" + c.ev_t1_s.toFixed(1) + " s of the clip</div>";
  const w = [];
  if (!c.ok) w.push("no clip: " + (c.missing_reason || "render failed"));
  if (c.truncated) w.push("the EVENT continues " + c.continues_s.toFixed(0) + " s after the clip end (clips show at most 60 s of an event)");
  if (ev.population_note) w.push(ev.population_note);
  (ev.cam_notes || []).forEach(x => w.push(x));
  if (w.length) h += "<div class='warnline'>" + w.map(esc).join(" · ") + "</div>";
  $("evhead").innerHTML = h;
  const cams = ev.cams.map(cm => "<b>" + esc(cm.cam) + "</b> " + esc(cm.role) + ": " + (cm.parts.length ? cm.parts.map(p => esc(p.file) + " @ " + p.offset_s.toFixed(2) + " s (" + p.dur_s.toFixed(1) + " s)").join(" + ") : "<span class='warnline'>no file</span>")).join("<br>");
  $("camreason").innerHTML = "<b>Cameras</b> chosen from " + esc(ev.zone_why) + ": " + esc(ev.zone_label) + " → " + esc(ev.cams_text) + ".<br>" + cams +
    "<br><span class='mut'>Times are field-PC file-name times (±1 s); the clock burnt into the image runs ≈ 59½ min behind — ignore it.</span>";
}
function renderForm(){
  const ev = EV[cur], j = jget(ev.id), q = ev.question;
  const radio = (name, opts, val) => opts.map(o => "<label class='opt'><input type='radio' name='" + name + "' value='" + o[0] + "'" + (val === o[0] ? " checked" : "") + "> <kbd>" + o[2] + "</kbd>" + esc(o[1]) + "</label>").join("");
  let vs;
  if (j.revealed_at) {
    vs = "<span style='color:var(--ok)'>Blind verdict saved " + esc(j.saved_at.slice(0, 19).replace("T", " ")) + " UTC: <b>" + esc(j.verdict_blind) + "</b>" + (j.reason_blind ? " (" + esc(j.reason_blind) + ")" : "") + "</span>" +
      (j.changed_after_reveal ? "<br><span class='warnline'>changed after the reveal → now <b>" + esc(j.verdict) + "</b> (both are exported)</span>" : "");
  } else vs = "<span class='mut'>Not saved yet — the panel stays hidden until you save.</span>";
  $("form").innerHTML =
    "<fieldset><legend>" + esc(q.short) + "</legend><div class='qtext'>" + esc(q.text) + "</div>" + radio("ans", q.options, j.verdict) + "</fieldset>" +
    "<fieldset id='fsReason'" + (j.verdict === "cannot_tell" ? "" : " disabled") + "><legend>Why can't you tell? (optional)</legend>" + radio("reason", REASONS, j.reason) + "</fieldset>" +
    "<fieldset><legend>Note (optional)</legend><textarea id='fNote' placeholder='what you saw'>" + esc(j.note) + "</textarea></fieldset>" +
    "<div id='vstate'>" + vs + (flash ? "<br><span class='warnline'>" + esc(flash) + "</span>" : "") + "</div>";
  $("bSave").textContent = j.revealed_at ? "Saved — next event (Enter)" : "Save verdict & reveal (Enter)";
  document.querySelectorAll("input[name=ans]").forEach(el => el.onchange = () => { setAnswer(ev.id, el.value); after(); });
  document.querySelectorAll("input[name=reason]").forEach(el => el.onclick = () => { setReason(ev.id, el.value); after(); });
  $("fNote").oninput = () => { setNote(ev.id, $("fNote").value); saveState(); renderList(); };
}
function after(){ saveState(); renderForm(); renderList(); }
function renderReveal(){
  const ev = EV[cur], open = isRevealed(ev.id);
  $("locked").hidden = open; $("revealBody").hidden = !open;
  if (!open) { $("panelImg").removeAttribute("src"); $("facts").innerHTML = ""; return; }
  $("panelImg").src = "panels/" + ev.panel.file;
  $("revealNote").innerHTML = "Dots = raw WISER fixes, line = V3 production track (distance from P0), the IMU state per second and the head turn; shaded = EVENT bar. " +
    "WISER frame inches, unverified origin; raw fixes jitter ~4–7 in.";
  $("facts").innerHTML = ev.reveal.facts.map(r => "<tr><th>" + esc(r[0]) + "</th><td>" + esc(r[1]) + "</td></tr>").join("");
}
function doSave(){
  const ev = EV[cur];
  if (isRevealed(ev.id)) { select(cur + 1); return; }
  const r = saveVerdict(ev.id);
  flash = r.ok ? "" : r.msg;
  saveState(); renderForm(); renderReveal(); renderList();
}

// ---------------------------------------------------------------- video controls
function drawBar(){
  const c = EV[cur].clip, D = c.dur_s || 1;
  $("evbarEv").style.left = (100 * c.ev_t0_s / D) + "%"; $("evbarEv").style.width = Math.max(0.3, 100 * (c.ev_t1_s - c.ev_t0_s) / D) + "%";
  const tv = vid.currentTime || 0;
  $("evbarCur").style.left = Math.min(100, 100 * tv / D) + "%";
  const inEv = tv >= c.ev_t0_s && tv <= c.ev_t1_s;
  $("tread").textContent = "clip " + tv.toFixed(2) + " s · field-PC " + clock(c.lo_sod + tv) + (inEv ? " · ▶ EVENT" : "") + " · " + vid.playbackRate + "×";
}
function loop(){ drawBar(); if (!vid.paused && !vid.ended) requestAnimationFrame(loop); }
["seeked", "timeupdate", "pause", "loadeddata", "ratechange"].forEach(n => vid.addEventListener(n, drawBar));
vid.addEventListener("play", () => requestAnimationFrame(loop));
vid.addEventListener("error", () => { if (EV[cur].clip.ok) $("tread").innerHTML = "<span class='warnline'>cannot load clips/" + esc(EV[cur].clip.file) + " — keep index.html next to the clips/ folder</span>"; });
$("evbar").addEventListener("click", e => { const r = $("evbar").getBoundingClientRect(); vid.currentTime = Math.max(0, (e.clientX - r.left) / r.width * EV[cur].clip.dur_s); });
function stepBy(dt){ vid.pause(); vid.currentTime = Math.max(0, Math.min((vid.duration || EV[cur].clip.dur_s) - 0.001, (vid.currentTime || 0) + dt)); }
function setRate(r){ rate = r; vid.playbackRate = r; vid.defaultPlaybackRate = r; $("speed").value = String(r); saveState(); drawBar(); }
function speedStep(d){ let i = SPEEDS.indexOf(rate); if (i < 0) i = 3; setRate(SPEEDS[Math.max(0, Math.min(SPEEDS.length - 1, i + d))]); }
SPEEDS.forEach(s => { const o = document.createElement("option"); o.value = String(s); o.textContent = s + "×"; $("speed").appendChild(o); });
$("speed").onchange = () => setRate(parseFloat($("speed").value));
$("bPlay").onclick = () => { vid.paused ? vid.play() : vid.pause(); };
$("bBack1").onclick = () => stepBy(-1); $("bFwd1").onclick = () => stepBy(1);
$("bBackF").onclick = () => stepBy(-1 / EV[cur].clip.fps); $("bFwdF").onclick = () => stepBy(1 / EV[cur].clip.fps);
$("bEvent").onclick = () => { vid.pause(); vid.currentTime = Math.max(0, EV[cur].clip.ev_t0_s); };
$("bSave").onclick = doSave;
$("bNext").onclick = () => select(cur + 1);
$("reviewer").oninput = () => { reviewer = $("reviewer").value.trim(); saveState(); };
$("fType").onchange = () => { filt.type = $("fType").value; renderList(); };
$("fAnimal").onchange = () => { filt.animal = $("fAnimal").value; renderList(); };
$("fStatus").onchange = () => { filt.status = $("fStatus").value; renderList(); };
Array.from(new Set(EV.map(e => e.animal))).sort().forEach(a => { const o = document.createElement("option"); o.value = a; o.textContent = a; $("fAnimal").appendChild(o); });

document.addEventListener("keydown", e => {
  const t = e.target, tag = t && t.tagName ? t.tagName : "";
  if (tag === "TEXTAREA" || tag === "SELECT" || (tag === "INPUT" && t.type !== "radio" && t.type !== "checkbox")) { if (e.key === "Escape") t.blur(); return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if ($("help").classList.contains("show")) { if (e.key === "Escape" || e.key === "?") { $("help").classList.remove("show"); e.preventDefault(); } return; }
  const ev = EV[cur], fr = 1 / (ev.clip.fps || 20), k = e.key;
  if (k === " ") { e.preventDefault(); vid.paused ? vid.play() : vid.pause(); }
  else if (k === "ArrowLeft") { e.preventDefault(); stepBy(e.shiftKey ? -1 : -fr); }
  else if (k === "ArrowRight") { e.preventDefault(); stepBy(e.shiftKey ? 1 : fr); }
  else if (k === "ArrowUp" || k === "p") { e.preventDefault(); select(cur - 1); }
  else if (k === "ArrowDown" || k === "n") { e.preventDefault(); select(cur + 1); }
  else if (k === "[") speedStep(-1);
  else if (k === "]") speedStep(1);
  else if (k === "\\") setRate(1);
  else if (k === "j") $("bEvent").onclick();
  else if (k === "Home") { vid.currentTime = 0; }
  else if (k === "Enter") { e.preventDefault(); doSave(); }
  else if (k === "?") { $("help").classList.add("show"); }
  else if (k >= "1" && k <= "3") { if (setAnswer(ev.id, ev.question.options[+k - 1][0])) after(); }
  else if (k >= "4" && k <= "6") { if (setReason(ev.id, REASONS[+k - 4][0])) after(); }
});

// ---------------------------------------------------------------- export / import
function stamp(){ const d = new Date(), p = n => String(n).padStart(2, "0"); return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + "_" + p(d.getHours()) + p(d.getMinutes()); }
function download(name, text, mime){
  const b = new Blob([text], {type: mime}), a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = name; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
}
function fname(ext){ return "wiser_event_review_" + DATA.cohort + "_" + (reviewer || "anon").replace(/[^A-Za-z0-9_-]/g, "") + "_" + stamp() + "." + ext; }
$("btnJson").onclick = () => download(fname("json"), JSON.stringify(exportObject(), null, 1), "application/json");
$("btnCsv").onclick = () => download(fname("csv"), csvText(), "text/csv");
$("importFile").onchange = e => {
  const f = e.target.files[0]; if (!f) return;
  const rd = new FileReader();
  rd.onload = () => {
    try { const n = importObject(JSON.parse(rd.result)); $("reviewer").value = reviewer; saveState(); select(cur); alert("Imported " + n + " verdicts from " + f.name); }
    catch (err) { alert("Import failed: " + err); }
  };
  rd.readAsText(f); e.target.value = "";
};

// ---------------------------------------------------------------- static panels
function renderStatic(){
  $("idtab").innerHTML = "<tr><th>rat</th><th>IR mark</th><th>coban</th><th>sticker</th><th>tag</th></tr>" +
    DATA.identity.map(r => "<tr><td><b>" + esc(r.animal) + "</b></td><td>" + esc(r.pattern) + "</td><td>" + esc(r.coban) + "</td><td>" + esc(r.sticker) + "</td><td class='mut'>" + esc(r.tags) + (r.note ? "<br>" + esc(r.note) : "") + "</td></tr>").join("");
  $("helpcard").innerHTML = "<h3 style='margin-top:0'>How to review</h3><p>" + DATA.help.map(esc).join("</p><p>") + "</p>" +
    "<h4>Keyboard</h4><table>" + [["Space", "play / pause"], ["← / →", "one frame (1/" + EV[0].clip.fps + " s); Shift = 1 s"], ["[ / ] / \\", "slower / faster / 1×"], ["j", "jump to the EVENT start"],
      ["↑ / ↓ or p / n", "previous / next event"], ["1 2 3", "answer (the three options of the question)"], ["4 5 6", "why you cannot tell (only with 'cannot tell')"],
      ["Enter", "save the verdict and reveal the panel; Enter again = next event"], ["? / Esc", "this help"]].map(r => "<tr><td><span class='kbd'>" + esc(r[0]) + "</span></td><td>" + esc(r[1]) + "</td></tr>").join("") + "</table>" +
    "<p class='mut'>Run " + esc(DATA.run_dir) + " · " + esc(DATA.tool) + " · plan " + esc(DATA.plan) + " · generated " + esc(DATA.generated) + "</p><p><button onclick=\"document.getElementById('help').classList.remove('show')\">close (Esc)</button></p>";
}
$("btnHelp").onclick = () => $("help").classList.add("show");
$("help").onclick = e => { if (e.target === $("help")) $("help").classList.remove("show"); };

loadState();
$("reviewer").value = reviewer;
$("speed").value = String(rate);
renderStatic();
select(cur);
</script>
</body></html>
"""


def page_payload(cohort: str, run_dir: Path, events: list, ids: pd.DataFrame, sel_info: dict, audit_run: str) -> dict:
    help_ = [
        "Each clip runs from 10 s before the event to 10 s after it (an event longer than 60 s is shown for its first 60 s). The red ▶ EVENT box in the video "
        "banner and the red stretch of the bar under the video mark the event window. The banner shows only the animal, its IR mark and coban colour, the zone, "
        "the cameras and the field-PC clock — nothing the tracker or the IMU computed.",
        "Question per event. I1 (place): did this rat actually change place during the EVENT bar? → moved / stayed (in place) / cannot tell. "
        "I2 (turn): did the rat's body turn sharply? → turned / ran straight / cannot tell. Choose 'cannot tell' when the rat is not visible or you are not "
        "sure it is the labelled rat (optional reason 4/5/6). A free-text note is always welcome.",
        "Blind order. Events are in a random order under neutral ids (W01 …). Save the verdict (Enter) → the WISER / IMU panel and the event's numbers are "
        "revealed. Your first saved answer is kept as the blind verdict; you may still change the answer afterwards (it is exported as the final verdict, "
        "flagged as changed after the reveal).",
        "Cameras were chosen from the rat's WISER zone (for I1: where it was before the event): house_1 → CH08 in-box + CH05 top-down; house_2 → CH07 in-box + "
        "CH06 top-down; open field → CH01 + CH02 panoramas (upright). If the rat is not where the cameras look, answer 'cannot tell' (rat not visible).",
        "Find the labelled rat by its IR mark (night and in-box frames are monochrome) or its coban colour (colour frames only); table on the right. "
        "From 2026-09-11 19:40 five non-implanted females (marks not stated) are also in the paddock. Never read the clock burnt into the image (≈ 59½ min behind).",
        "Verdicts autosave in this browser only. Export JSON and CSV when done and put both files in wiser/configs/wiser_event_review_" + cohort + "/ of the "
        "analysis repo (commit them; the return test reads them with --with-verdicts).",
    ]
    return {"cohort": cohort, "run_id": run_dir.name, "run_dir": str(run_dir), "tool": TOOL, "plan": PLAN, "audit_run": audit_run,
            "generated": time.strftime("%Y-%m-%d %H:%M"), "selection": sel_info, "reasons": REASONS,
            "identity": identity_rows(ids), "help": help_, "events": events}


def write_html(out_dir: Path, payload: dict) -> Path:
    js = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__DATA_JSON__", js).replace("__COHORT__", payload["cohort"])
    p = out_dir / "index.html"
    p.write_text(html, encoding="utf-8")
    return p


def script_blocks(html_path: Path) -> list:
    return re.findall(r"<script>(.*?)</script>", html_path.read_text(encoding="utf-8"), re.S)


def node_exe() -> str:
    return shutil.which("node") or r"C:\Program Files\nodejs\node.exe"


def check_js(html_path: Path) -> tuple[bool, str]:
    blocks = script_blocks(html_path)
    if len(blocks) != 2:
        return False, f"expected 2 <script> blocks, found {len(blocks)}"
    with tempfile.TemporaryDirectory() as td:
        jsf = Path(td) / "page.js"
        jsf.write_text("\n;\n".join(blocks), encoding="utf-8")
        p = subprocess.run([node_exe(), "--check", str(jsf)], capture_output=True, text=True)
        return p.returncode == 0, (p.stderr or p.stdout).strip()[-800:]


# ====================================================================================================== README / tables
def write_tables(out: Path, evs: list) -> None:
    with open(out / "event_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "type", "animal", "event_key", "selection", "selection_rank", "size_quartile", "onset_local", "end_local",
                    "onset_al_ms", "end_al_ms", "zone", "cameras", "clip", "clip_ok", "clip_s", "clip_mb", "event_s", "truncated", "missing_reason",
                    "cam_notes", "panel", "panel_ok"])
        for p in evs:
            c = p["clip"]
            w.writerow([p["id"], p["type"], p["animal"], p["event_key"], p["selection"], p["selection_rank"], p["size_quartile"], p["onset_local"],
                        p["end_local"], p["onset_al_ms"], p["end_al_ms"], p["zone"], p["cams_text"], c["file"], c["ok"], c.get("duration_probe_s"),
                        round((c.get("size_bytes") or 0) / 1e6, 1), c["event_s"], c["truncated"], c["missing_reason"], "; ".join(p["cam_notes"]),
                        p["panel"]["file"], p["panel"]["ok"]])


def write_readme(out: Path, cohort: str, evs: list, sel_info: dict, enc: str, audit_run: str, wall_s: float) -> None:
    ok = [p for p in evs if p["clip"]["ok"]]
    tot_mb = sum(p["clip"].get("size_bytes") or 0 for p in ok) / 1e6
    tot_s = sum(p["clip"].get("duration_probe_s") or 0 for p in ok)
    nt = {t: sum(1 for p in evs if p["type"] == t) for t in ("I1", "I2")}
    ns = {s: sum(1 for p in evs if p["selection"] == s) for s in ("top", "random")}
    lines = [f"# WISER event review (blind) — cohort {cohort}", "",
             f"Written by `{TOOL}` (git {MV.git_commit()}) on {time.strftime('%Y-%m-%d %H:%M')}; plan `{PLAN}` (Part 2). "
             f"Events: audit run `{audit_run}` (V3).", "",
             "## How to use", "",
             "1. Open `index.html` in Chrome / Edge / Firefox (double-click; works from file:// — keep it next to `clips/` and `panels/`).",
             "2. Pick an event (random order, neutral ids), play the clip (Space; ←/→ one frame, Shift 1 s; [ ] speed; j = EVENT start).",
             "3. Answer the question (1/2/3; for 'cannot tell' optionally 4/5/6 why), add a note if useful, press Enter = save the verdict → "
             "the WISER / IMU panel and the event's numbers are revealed. Enter again = next event.",
             f"4. Verdicts autosave in the browser only. **Export JSON + CSV** and put both in `wiser/configs/wiser_event_review_{cohort}/` "
             "(commit). `verdict_blind` = the first saved verdict (before the reveal); `verdict_final` = the answer at export.", "",
             "## Events", "",
             f"{len(evs)} events: I1 {nt['I1']} (top {sel_info['n_top']} by size + {sel_info['n_per_quartile']} random per size quartile), "
             f"I2 {nt['I2']} (top {sel_info['n_top']}); top {ns['top']}, random {ns['random']}. V3 I1 total {sel_info['i1_total']:,}, "
             f"quartile edges {sel_info['i1_quartile_edges_in']} in, pool per quartile {sel_info['pool_sizes_by_quartile']}; seed {sel_info['seed']} "
             f"(order seed {sel_info['order_seed']}). `selection.csv` maps review ids to audit events (do not open it before reviewing).", "",
             "## Files", "",
             f"- `clips/` — {len(ok)} H.264 clips ({enc}), {tot_mb:.0f} MB, {tot_s / 60:.1f} min; 20 fps; blind banner (animal, IR mark, coban, zone, "
             "cameras, field-PC clock, EVENT box).",
             "- `panels/` — one PNG per event (revealed after the verdict): distance of raw fixes / V3 from P0, IMU state per second, head turn "
             "(+ V3 path heading for I2), x-y map in the WISER frame (inches, unverified origin).",
             "- `index.html` — the review page (data embedded); `events.json` — the same data; `event_summary.csv`, `selection.csv`;",
             "- `overlay_ass/` — the exact overlays; `_fonts/` — DejaVu Sans; `log.txt`.", "",
             "Clip time = video file-name time (field-PC clock, ±1 s); event times are the audit's aligned clock t_al = t_WISER − τ* "
             "(the head-IMU / field-PC clock). Never read the clock burnt into the image.", ""]
    miss = [p for p in evs if not p["clip"]["ok"]]
    if miss:
        lines += ["## Missing clips", ""] + [f"- {p['id']} ({p['event_key']}, {p['onset_local']}): {p['clip']['missing_reason'] or 'render failed'}" for p in miss] + [""]
    gaps = [p for p in evs if p["clip"]["ok"] and p["cam_notes"]]
    if gaps:
        lines += ["## Clips with a camera gap", ""] + [f"- {p['id']}: {'; '.join(p['cam_notes'])}" for p in gaps] + [""]
    lines += [f"Wall time {wall_s / 60:.1f} min."]
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ====================================================================================================== driver
def load_audit(audit: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    tb = audit / "tables"
    E = pd.read_csv(tb / "events.csv.gz")
    L1 = pd.read_csv(tb / "event_list_I1_V3.csv")
    L2 = pd.read_csv(tb / "event_list_I2_V3.csv")
    info = pd.read_csv(tb / "animals_info.csv")
    return E, L1, L2, dict(zip(info["animal"], info["tau_ms"].astype(float)))


def run(args) -> int:
    t_start = time.time()
    cohort = args.cohort
    audit = Path(args.audit_run)
    out = Path(args.out) if args.out else output_paths.run_dir(NAME, cohort, make_figures=False)
    for sub in ("clips", "panels", "overlay_ass", "_fonts"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    fh = open(out / "log.txt", "a", encoding="utf-8")
    log(f"{NAME}: out {out}; audit {audit}; root {args.root}; git {MV.git_commit()}", fh)
    fonts = MV.find_fonts()
    if "regular" not in fonts or "bold" not in fonts:
        raise SystemExit("DejaVu Sans (DejaVuSans.ttf / DejaVuSans-Bold.ttf) not found - needed for the overlay glyphs")
    for f in fonts.values():
        shutil.copy2(f, out / "_fonts" / f.name)
    ffmpeg, ffprobe = GF.find_ffmpeg()
    enc = args.encoder
    if enc == "auto" and not args.no_clips:
        enc = "nvenc" if MV.nvenc_works(ffmpeg) else "x264"
    rois = json.loads((REPO / "wiser" / "configs" / "wiser_rois.json").read_text(encoding="utf-8"))
    houses = [r for r in rois["rois"] if r["name"] in ("house_1", "house_2")]
    ids = MV.load_identity(cohort)
    E, L1, L2, taus = load_audit(audit)
    events, sel_info = select_events(E, L1, L2, taus, seed=args.seed)
    log(f"selection: {len(events)} events; I1 total {sel_info['i1_total']}, I2 total {sel_info['i2_total']}; quartile edges "
        f"{sel_info['i1_quartile_edges_in']} in; pool per quartile {sel_info['pool_sizes_by_quartile']}; encoder {enc}", fh)
    pd.DataFrame([{k: e.get(k) for k in ("review_id", "type", "animal", "event_id", "selection", "selection_rank", "size_quartile", "size",
                                          "t0", "t1", "zone_detail", "tau_ms")} for e in events]).to_csv(out / "selection.csv", index=False)
    if args.only:
        keep = set(args.only)
        events = [e for e in events if e["review_id"] in keep]
    cache = TrackCache(args.tracks_root, args.imu_seconds_root)
    payloads, jobs = [], {}
    for ev in events:
        pl, job = build_event(ev, sel_info, houses, ids, Path(args.root), ffprobe, out, fonts, cache, audit_run=str(audit))
        payloads.append(pl)
        jobs[pl["id"]] = job
        log(f"  {pl['id']} {pl['type']} {pl['animal']} {pl['onset_local']} ({pl['selection']}): {pl['zone_label']} -> {pl['cams_text']}; "
            f"clip {pl['clip']['dur_s']:.0f} s, EVENT {pl['clip']['ev_t0_s']:.0f}-{pl['clip']['ev_t1_s']:.0f} s; parts "
            f"{[len(c['parts']) for c in pl['cams']]}, gaps {[c['gaps'] for c in pl['cams']]}; panel fixes {pl['panel'].get('summary', {}).get('n_fix')}"
            + (f"; MISSING: {pl['clip']['missing_reason']}" if pl["clip"]["missing_reason"] else ""), fh)
    results = {}
    if not args.no_clips:
        todo = [p["id"] for p in payloads if jobs[p["id"]]["has_video"]]
        log(f"rendering {len(todo)} clips with {args.workers} workers ...", fh)
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futs = {i: ex.submit(MV.render, ffmpeg, ffprobe, jobs[i], out, enc) for i in todo}
            for i in todo:
                r = futs[i].result()
                results[i] = r
                if r["ok"]:
                    log(f"  clip {Path(jobs[i]['out']).name}: {r.get('width')}x{r.get('height')} {r.get('duration_s', 0):.1f} s "
                        f"{r.get('size_bytes', 0) / 1e6:.1f} MB {r['encoder']} in {r['seconds']} s"
                        + (f"; GLYPH WARNINGS {r['glyph_warnings']}" if r["glyph_warnings"] else ""), fh)
                else:
                    log(f"  clip {Path(jobs[i]['out']).name}: FAILED - {r.get('error', '')[-600:]}", fh)
    for p in payloads:
        r = results.get(p["id"])
        if r is not None:
            p["clip"].update({"ok": bool(r["ok"]), "encoder": r.get("encoder"), "size_bytes": r.get("size_bytes"),
                              "duration_probe_s": r.get("duration_s")})
            if not r["ok"] and not p["clip"]["missing_reason"]:
                p["clip"]["missing_reason"] = "ffmpeg render failed (see log.txt)"
        elif args.no_clips and jobs[p["id"]]["has_video"] and (out / "clips" / p["clip"]["file"]).exists():
            p["clip"]["ok"] = True
    payloads.sort(key=lambda p: p["idx"])
    page = page_payload(cohort, out, payloads, ids, sel_info, str(audit))
    (out / "events.json").write_text(json.dumps(page, ensure_ascii=False, indent=1), encoding="utf-8")
    html = write_html(out, page)
    ok_js, msg = check_js(html)
    log(f"index.html {html.stat().st_size / 1e6:.2f} MB; node --check {'OK' if ok_js else 'FAILED ' + msg}", fh)
    write_tables(out, payloads)
    write_readme(out, cohort, payloads, sel_info, enc, str(audit), time.time() - t_start)
    n_ok = sum(1 for p in payloads if p["clip"]["ok"])
    miss = [f"{p['id']} {p['event_key']}: {p['clip']['missing_reason']}" for p in payloads if not p["clip"]["ok"]]
    log(f"done: {n_ok}/{len(payloads)} clips, panels {sum(1 for p in payloads if p['panel']['ok'])}; missing {miss}; "
        f"wall {(time.time() - t_start) / 60:.1f} min -> {out}", fh)
    fh.close()
    return 0 if ok_js and (args.no_clips or n_ok == len(payloads)) else 1


def html_only(run_dir: Path) -> int:
    page = json.loads((run_dir / "events.json").read_text(encoding="utf-8"))
    page["generated"] = time.strftime("%Y-%m-%d %H:%M") + " (html rebuilt)"
    html = write_html(run_dir, page)
    ok, msg = check_js(html)
    print(f"index.html rebuilt ({html.stat().st_size / 1e6:.2f} MB); node --check {'OK' if ok else 'FAILED ' + msg}")
    return 0 if ok else 1


# ====================================================================================================== self-test
def _synth_events(n_i1: int = 400, n_i2: int = 40, seed: int = 3) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    rows = []
    base = 1788500000.0
    for tr in ("V3", "B2"):
        for i in range(n_i1):
            a = f"SF{7 + i % 6:02d}"
            t0 = base + 100.0 * i
            rows.append({"animal": a, "track": tr, "type": "I1", "event_id": i // 6, "size": float(12 + rng.gamma(1.5, 8.0)),
                         "t0": t0, "t1": t0 + float(rng.integers(2, 200)), "zone_detail": "house_2", "ref_x": 613.0, "ref_y": 717.0})
        for i in range(n_i2):
            a = f"SF{7 + i % 6:02d}"
            t0 = base + 50.0 + 1000.0 * i
            rows.append({"animal": a, "track": tr, "type": "I2", "event_id": i // 6, "size": float(90 + rng.uniform(0, 90)),
                         "t0": t0, "t1": t0 + 4.0, "zone_detail": "field", "ref_x": np.nan, "ref_y": np.nan})
    E = pd.DataFrame(rows)
    V = E[E.track == "V3"]
    L1 = V[V.type == "I1"].sort_values("size", ascending=False).head(N_TOP).reset_index(drop=True)
    L1.insert(0, "rank", np.arange(1, len(L1) + 1))
    L2 = V[V.type == "I2"].sort_values("size", ascending=False).head(N_TOP).reset_index(drop=True)
    L2.insert(0, "rank", np.arange(1, len(L2) + 1))
    return E, L1[["rank", "animal", "event_id"]], L2[["rank", "animal", "event_id"]]


def selftest() -> int:
    ok_all = True

    def check(name, cond, info=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}", flush=True)

    # ---------------------------------------------------------------- 1. selection
    E, L1, L2 = _synth_events()
    taus = {f"SF{k:02d}": 150.0 for k in range(7, 13)}
    evs, info = select_events(E, L1, L2, taus, seed=SEED)
    evs2, _ = select_events(E, L1, L2, taus, seed=SEED)
    keys = [(e["type"], e["animal"], int(e["event_id"])) for e in evs]
    check("selection: 30 top I1 + 30 top I2 + 20 random I1 = 80 unique events",
          len(evs) == 80 and len(set(keys)) == 80 and sum(e["type"] == "I2" for e in evs) == 30
          and sum(e["selection"] == "random" for e in evs) == 20, f"{len(evs)} / {len(set(keys))}")
    V1 = E[(E.track == "V3") & (E.type == "I1")]
    edges = quartile_edges(V1["size"].to_numpy())
    rq = [e for e in evs if e["selection"] == "random"]
    check("selection: 5 random per size quartile, quartile edges over all V3 I1",
          all(sum(1 for e in rq if e["size_quartile"] == k) == 5 for k in (1, 2, 3, 4))
          and all(quartile_of(e["size"], edges) == e["size_quartile"] for e in rq), str(sorted(e["size_quartile"] for e in rq)))
    top1 = set(zip(V1.sort_values("size", ascending=False).head(30)["animal"], V1.sort_values("size", ascending=False).head(30)["event_id"]))
    check("selection: random draws exclude the top 30 and come from the V3 track only",
          all((e["animal"], e["event_id"]) not in top1 for e in rq) and all(e["track"] == "V3" for e in evs))
    check("selection: deterministic for a fixed seed (same events, same order)",
          keys == [(e["type"], e["animal"], int(e["event_id"])) for e in evs2])
    check("selection: review order is shuffled (not the top-list order) with ids W01..W80",
          [e["review_id"] for e in evs] == [f"W{k:02d}" for k in range(1, 81)]
          and [e["selection_rank"] for e in evs[:30]] != list(range(1, 31)))
    evs3, _ = select_events(E, L1, L2, taus, seed=SEED + 7)
    check("selection: a different seed draws different random events",
          {(e["animal"], e["event_id"]) for e in evs3 if e["selection"] == "random"} != {(e["animal"], e["event_id"]) for e in rq})
    bad = L1.copy()
    bad.loc[0, "event_id"] = 999
    try:
        select_events(E, bad, L2, taus)
        check("selection: a top list that is not in events.csv.gz is refused", False)
    except ValueError:
        check("selection: a top list that is not in events.csv.gz is refused", True)

    # ---------------------------------------------------------------- 2. window arithmetic
    t0 = 1_788_500_000_000
    w = clip_window(t0, t0 + 20_000)
    check("window: 20-s event -> clip [t-10, t+30], EVENT 10-30 s", w["lo_ms"] == t0 - 10_000 and w["hi_ms"] == t0 + 30_000 and w["dur_s"] == 40.0
          and w["ev_t0_s"] == 10.0 and w["ev_t1_s"] == 30.0 and not w["truncated"], str(w))
    w = clip_window(t0, t0 + 222_000)
    check("window: 222-s event -> clip capped at t+70, EVENT to the clip end, 152 s after", w["hi_ms"] == t0 + 70_000 and w["dur_s"] == 80.0
          and w["ev_t1_s"] == 80.0 and w["truncated"] and w["continues_s"] == 152.0, str(w))
    w = clip_window(t0, t0 + 65_000)
    check("window: 65-s event -> clip 80 s, EVENT 10-75 s (ends inside the clip)", w["dur_s"] == 80.0 and w["ev_t1_s"] == 75.0 and not w["truncated"], str(w))
    w = clip_window(t0 + 500, t0 + 4_500)
    check("window: I2 4-s window on a half second -> 24-s clip", w["dur_s"] == 24.0 and w["ev_t0_s"] == 10.0 and w["ev_t1_s"] == 14.0, str(w))

    # ---------------------------------------------------------------- 3. zones / identity
    houses = [{"name": "house_1", "shape": "rect", "x": 411.46, "y": 718.61, "width_in": 36.39, "height_in": 26.59, "orientation_deg": 90.0},
              {"name": "house_2", "shape": "rect", "x": 613.58, "y": 717.34, "width_in": 36.39, "height_in": 26.59, "orientation_deg": 90.0}]
    z1 = camera_zone({"type": "I1", "ref_x": 620.0, "ref_y": 731.0, "zone_detail": "field"}, houses)
    z2 = camera_zone({"type": "I1", "ref_x": 300.0, "ref_y": 600.0, "zone_detail": "house_2"}, houses)
    z3 = camera_zone({"type": "I2", "ref_x": np.nan, "ref_y": np.nan, "zone_detail": "house_1"}, houses)
    z4 = camera_zone({"type": "I2", "ref_x": np.nan, "ref_y": np.nan, "zone_detail": "field"}, houses)
    check("cameras: I1 by the reference position (house_2 core / open field), I2 by the audit zone",
          z1[0] == "house_2" and z2[0] == "outside" and z3[0] == "house_1" and z4[0] == "outside"
          and [c for c, _ in MV.CAMS[z1[0]]] == ["CH07", "CH06"] and [c for c, _ in MV.CAMS[z2[0]]] == ["CH01", "CH02"]
          and [c for c, _ in MV.CAMS[z3[0]]] == ["CH08", "CH05"], f"{z1[0]} {z2[0]} {z3[0]} {z4[0]}")
    cc = rect_corners(houses[0])
    from_core = MV.WU._rect_membership(cc[:4, 0] * 0.999 + 0.001 * houses[0]["x"], cc[:4, 1] * 0.999 + 0.001 * houses[0]["y"], houses[0], 0.0)[0]
    check("panel: house rectangle corners lie on the ROI boundary (same rotation as _rect_membership)", bool(np.all(from_core)))
    ids = MV.load_identity("2026c")
    i12a = identity(ids, "SF12", pd.Timestamp("2026-08-30 22:00").tz_localize(TZ).value // 10**6)
    i12b = identity(ids, "SF12", pd.Timestamp("2026-09-05 22:00").tz_localize(TZ).value // 10**6)
    i11 = identity(ids, "SF11", pd.Timestamp("2026-09-02 03:00").tz_localize(TZ).value // 10**6)     # between SF11's tags
    check("identity: SF12 two lines, coban yellow before 08-31 and blue after; SF11 circle between its tags",
          i12a["pattern"] == "two lines" and i12a["coban"] == "yellow" and i12b["coban"] == "blue" and i11["pattern"] == "circle", f"{i12a} {i12b} {i11}")

    # ---------------------------------------------------------------- 4. synthetic hourly video: lookup across an hour boundary, overlay, render
    ffmpeg, ffprobe = GF.find_ffmpeg()
    fonts = MV.find_fonts()
    check("DejaVu Sans fonts found", "regular" in fonts and "bold" in fonts, str(fonts))
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "video"
        out = Path(td) / "run"
        for sub in ("clips", "panels", "overlay_ass", "_fonts"):
            (out / sub).mkdir(parents=True)
        for f in fonts.values():
            shutil.copy2(f, out / "_fonts" / f.name)

        def make(cam: str, day: str, name: str, secs: float):
            d = root / day / cam
            d.mkdir(parents=True, exist_ok=True)
            subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s=320x240:r=20:d={secs}",
                            "-vf", "geq=lum=100+mod(5*N\\,130):cb=128:cr=128", "-c:v", "libx264", "-g", "40",
                            "-pix_fmt", "yuv420p", str(d / name)], check=True)
        # hour boundary 02:00 with the usual ~1-s start offsets: CH07 closes at 02:00:01, the next file starts there
        make("CH07", "2026-09-05", "CH07_2026-09-05_01-59-50_to_02-00-01.mp4", 11)
        make("CH07", "2026-09-05", "CH07_2026-09-05_02-00-01_to_02-00-30.mp4", 29)
        make("CH06", "2026-09-05", "CH06_2026-09-05_01-59-50_to_02-00-00.mp4", 10)
        make("CH06", "2026-09-05", "CH06_2026-09-05_02-00-02.mp4", 20)               # never renamed, 2-s hole before it
        ev_t0 = int(pd.Timestamp("2026-09-05 02:00:04").tz_localize(TZ).value // 10**6)
        cw = clip_window(ev_t0, ev_t0 + 6_000)                                     # clip 01:59:54 -> 02:00:20
        lo_dt, hi_dt = MV.ms_to_dt(cw["lo_ms"]), MV.ms_to_dt(cw["hi_ms"])
        check("time: clip bounds are naive field-PC datetimes of the aligned ms", lo_dt == datetime(2026, 9, 5, 1, 59, 54) and hi_dt == datetime(2026, 9, 5, 2, 0, 20),
              f"{lo_dt} {hi_dt}")
        p7, g7 = MV.view_parts(root, "CH07", lo_dt, hi_dt, ffprobe)
        p6, g6 = MV.view_parts(root, "CH06", lo_dt, hi_dt, ffprobe)
        check("lookup: CH07 = 01:59:50 file @ 4 s for 7 s + 02:00:01 file @ 0 s from clip 7 s, no gap",
              len(p7) == 2 and abs(p7[0]["offset_s"] - 4.0) < 1e-6 and abs(p7[0]["dur_s"] - 7.0) < 1e-6 and abs(p7[1]["clip_t0_s"] - 7.0) < 1e-6
              and abs(p7[1]["offset_s"]) < 1e-6 and not g7, f"{[(p['file'], p['offset_s'], p['dur_s'], p['clip_t0_s']) for p in p7]} gaps {g7}")
        check("lookup: CH06 hole 6-8 s (02:00:00 -> 02:00:02) found, never-renamed file used", len(p6) == 2 and g6 == [[6.0, 8.0]]
              and p6[1]["file"].endswith("02-00-02.mp4"), f"gaps {g6}")
        lay = MV.layout("house_2", scale=0.25)
        ident = identity(ids, "SF07", ev_t0)
        rows = overlay_rows("W07", "SF07", ident, "house_2", "CH07 in-box + CH06 top-down", cw)
        sod = 1 * 3600 + 59 * 60 + 54.0
        T_ = write_ass_blind(out / "overlay_ass" / "t.ass", lay, rows, cw["dur_s"], (cw["ev_t0_s"], cw["ev_t1_s"]),
                             ["CH07 · in-box · house_2", "CH06 · top-down · house_2"], [g7, g6], sod, fonts)
        dyn = T_["dyn"]
        tiles = all(abs(dyn[i][1] - dyn[i + 1][0]) < 1e-9 for i in range(len(dyn) - 1)) and abs(dyn[0][0]) < 1e-9 and abs(dyn[-1][1] - cw["dur_s"]) < 1e-9
        check("overlay: field-PC clock tiles the clip in 0.25-s steps", tiles and len(dyn) == int(cw["dur_s"] / 0.25), f"{len(dyn)} lines")
        check("overlay: clock text = clip start + t (01:59:54.00, 02:00:04.00 at the EVENT start)",
              dyn[0][2] == "field-PC 01:59:54.00" and dyn[40][2] == "field-PC 02:00:04.00", f"{dyn[0][2]} / {dyn[40][2]}")
        check("overlay: EVENT box exactly over the event window", T_["event"] == [(10.0, 16.0, "▶ EVENT")], str(T_["event"]))
        check("overlay: NO VIDEO only in the CH06 hole", T_["nov"] == [(6.0, 8.0, "CH06 · top-down · house_2")], str(T_["nov"]))
        txt = (out / "overlay_ass" / "t.ass").read_text(encoding="utf-8")
        body = "\n".join(x for x in txt.splitlines() if x.startswith("Dialogue"))
        leaks = [w_ for w_ in FORBIDDEN_OVERLAY if w_ in body]
        check("overlay is blind: no WISER / IMU / size / class / selection words or numbers", not leaks, f"leaks {leaks}")
        check("overlay names the animal, IR mark, coban and zone", all(s in body for s in ("SF07", "IR mark: x", "coban green", "zone: house_2")), rows[0])
        enc = "nvenc" if MV.nvenc_works(ffmpeg) else "x264"
        job = {"id": "t", "out": str(out / "clips" / "t.mp4"), "layout": lay, "view_parts": [p7, p6], "D": cw["dur_s"],
               "ass_rel": "overlay_ass/t.ass", "fonts_rel": "_fonts"}
        r = MV.render(ffmpeg, ffprobe, job, out, enc)
        check(f"render ({r.get('encoder')}): H.264 yuv420p {lay['W']}x{lay['H']}, duration = clip",
              r["ok"] and r.get("codec") == "h264" and r.get("pix_fmt") == "yuv420p" and r.get("width") == lay["W"]
              and abs(r.get("duration_s", 0) - cw["dur_s"]) <= 1.0 / MV.FPS + 1e-3, r.get("error", "")[-300:])
        check("render: no missing-glyph warnings", r["ok"] and not r["glyph_warnings"], str(r.get("glyph_warnings")))
        if r["ok"]:
            W, H = lay["W"], lay["H"]
            p = subprocess.run([ffmpeg, "-v", "error", "-i", job["out"], "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"], capture_output=True)
            fr = np.frombuffer(p.stdout, np.uint8).reshape(-1, W * H * 3 // 2)[:, :W * H].reshape(-1, H, W)

            def region(v, k):
                return float(fr[k, v["y"] + int(0.6 * v["h"]):v["y"] + int(0.9 * v["h"]), v["x"] + int(0.1 * v["w"]):v["x"] + int(0.9 * v["w"])].mean())

            def expected(parts, tc):
                for pp in parts:
                    if pp["clip_t0_s"] - 1e-6 <= tc < pp["clip_t0_s"] + pp["dur_s"] - 1e-6:
                        N = int(math.floor((tc - pp["clip_t0_s"] + pp["offset_s"]) * 20 + 1e-6))
                        return 100 + (5 * N) % 130
                return None
            good = tot = 0
            gap_vals, bad = [], []
            for k in range(len(fr)):
                for v, parts in zip(lay["views"], [p7, p6]):
                    e_ = expected(parts, k / MV.FPS)
                    val = region(v, k)
                    if e_ is None:
                        gap_vals.append(val)
                        continue
                    tot += 1
                    good += abs(val - e_) <= 4
                    if abs(val - e_) > 4 and len(bad) < 6:
                        bad.append((k, round(val, 1), e_))
            check("timing: each view shows the source frame of its file-name time across the hour boundary (luma-coded)",
                  tot and good / tot >= 0.95, f"{good}/{tot}; first misses {bad}")
            check("timing: the CH06 hole shows the empty canvas", len(gap_vals) >= 30 and max(gap_vals) < 90, f"n {len(gap_vals)}")

        # ---------------------------------------------------------------- 5. panel (synthetic fixes; the file is checked, never viewed)
        tt = np.arange(cw["lo_ms"], cw["hi_ms"], 250.0)
        xs = 613.0 + np.where((tt >= ev_t0) & (tt < ev_t0 + 6000), 20.0, 0.0) + np.random.default_rng(1).normal(0, 3, len(tt))
        Fsyn = pd.DataFrame({"t_al": tt, "x_raw": xs, "y_raw": 717.0 + np.random.default_rng(2).normal(0, 3, len(tt)), "x": 613.0, "y": 717.0,
                             "anchors_used": 8, "imu_state": 1})
        secs = np.arange(cw["lo_ms"] // 1000, cw["hi_ms"] // 1000 + 1)
        Isyn = pd.DataFrame({"sec": secs, "ok": True, "state": 1, "turn_net_deg": 0.5})
        evp = {"review_id": "W07", "type": "I1", "animal": "SF07", "t0": ev_t0 / 1000.0, "ref_x": 613.0, "ref_y": 717.0,
               "run_t0": ev_t0 / 1000.0 - 30, "run_t1": ev_t0 / 1000.0 + 12, "size": 20.0, "dur_s": 6, "n_segments": 1, "run_len_s": 42,
               "subtype": "all_still"}
        pinfo = make_panel(evp, cw, Fsyn, Isyn, houses, out / "panels" / "t.png")
        sig = (out / "panels" / "t.png").read_bytes()[:8] if (out / "panels" / "t.png").exists() else b""
        check("panel: PNG written with the window's fixes and IMU seconds", sig == b"\x89PNG\r\n\x1a\n" and pinfo["n_fix"] == len(tt)
              and pinfo["imu_seconds"] == len(secs) and abs(pinfo["P0"][0] - 613.0) < 1e-6, str(pinfo))
        evq = dict(evp, type="I2", c_max=ev_t0 / 1000.0 + 3, dtheta=120.0, dpsi=5.0, spd1=12.0, spd2=14.0)
        pinfo2 = make_panel(evq, cw, Fsyn, Isyn, houses, out / "panels" / "t2.png")
        check("panel: I2 variant (path heading + turn) written", (out / "panels" / "t2.png").exists() and pinfo2["n_fix"] == len(tt))
        b_, P_, g_ = cumulative_turn(np.array([0.0, 1.0, 2.0]), np.array([10.0, np.nan, -5.0]))
        check("panel: cumulative head turn integrates per-second turns, gaps -> 0 and flagged",
              np.allclose(P_, [0, 10, 10, 5]) and g_.tolist() == [False, True, False] and np.allclose(b_, [0, 1, 2, 3]))
        th = path_heading(np.arange(0, 10, 0.1), 20.0 * np.arange(0, 10, 0.1), np.zeros(100), np.arange(1.0, 9.0, 0.5))
        check("panel: display heading of a straight +x run at 20 in/s = 0 deg", np.nanmax(np.abs(th)) < 1e-6 and np.isfinite(th).all())

    # ---------------------------------------------------------------- 6. page: node --check + verdict / reveal / export logic in node
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        E2, L12, L22 = _synth_events()
        evs_s, info_s = select_events(E2, L12, L22, taus)
        pls = []
        for e in evs_s[:3]:
            cw_ = clip_window(int(e["t0"] * 1000), int(e["t1"] * 1000))
            pls.append({"idx": e["review_idx"], "id": e["review_id"], "type": e["type"], "question": QUESTIONS[e["type"]], "animal": e["animal"],
                        "event_key": f"{e['animal']}|V3|{e['type']}|{int(e['event_id'])}", "audit_event_id": int(e["event_id"]),
                        "selection": e["selection"], "selection_rank": e["selection_rank"], "size_quartile": e["size_quartile"],
                        "onset_local": fmt_local(cw_["lo_ms"] + 10_000), "end_local": fmt_local(cw_["hi_ms"]), "onset_al_ms": cw_["lo_ms"] + 10_000,
                        "end_al_ms": cw_["hi_ms"], "tau_ms": 150.0, "identity": identity(ids, e["animal"], cw_["lo_ms"]), "zone": "house_2",
                        "zone_label": "house_2", "zone_why": "test", "cams_text": "CH07 in-box + CH06 top-down",
                        "overlay_static": ["row 1 </script> test", "row 2"], "population_note": "", "cam_notes": [],
                        "cams": [{"cam": "CH07", "role": "in-box", "parts": [], "gaps": []}],
                        "clip": {"file": "a.mp4", "ok": True, "missing_reason": "", "lo_local": "2026-09-05 01:59:54.000", "hi_local": "2026-09-05 02:00:20.000",
                                 "lo_ms": cw_["lo_ms"], "hi_ms": cw_["hi_ms"], "lo_sod": 7194.0, "dur_s": cw_["dur_s"], "ev_t0_s": cw_["ev_t0_s"],
                                 "ev_t1_s": cw_["ev_t1_s"], "truncated": cw_["truncated"], "continues_s": cw_["continues_s"], "event_s": cw_["event_s"],
                                 "fps": 20, "width": 960, "height": 414},
                        "panel": {"file": "a.png", "ok": True}, "reveal": {"facts": [["selection", "secret"]]}, "audit_run": "x"})
        page = page_payload("2026c", out, pls, ids, info_s, "x")
        html = write_html(out, page)
        txt = html.read_text(encoding="utf-8")
        check("HTML: data embedded, '</script>' inside data escaped", txt.count("</script>") == 2 and "row 1 <\\/script> test" in txt)
        okj, msg = check_js(html)
        check("HTML: both script blocks pass node --check", okj, msg)
        logic = script_blocks(html)[0]
        q1 = pls[0]["question"]["options"]
        harness = logic + r"""
;(function(){
  const id1 = EV[0].id, id2 = EV[1].id, id3 = EV[2].id;
  const res = {};
  res.before = isRevealed(id1);
  res.r0 = saveVerdict(id1);
  res.badAnswer = setAnswer(id1, "nonsense");
  res.reasonWithoutCannot = setReason(id1, "not_visible");
  setAnswer(id1, EV[0].question.options[0][0]);
  res.st_partial = status(id1);
  res.r1 = saveVerdict(id1);
  res.after = isRevealed(id1);
  setAnswer(id1, EV[0].question.options[1][0]);
  res.r2 = saveVerdict(id1);
  setAnswer(id2, "cannot_tell"); setReason(id2, "not_visible"); setNote(id2, 'a "quoted", note' + "\n" + 'line2');
  res.revealed2 = isRevealed(id2);
  res.st1 = status(id1); res.st2 = status(id2); res.st3 = status(id3);
  const o = exportObject();
  const n = importObject({judgements: {[id3]: {verdict: "cannot_tell", revealed_at: "2026-10-05T00:00:00Z", verdict_blind: "cannot_tell"}}, reviewer: "zz"});
  res.imported = n; res.st3b = status(id3); res.reviewer = reviewer;
  process.stdout.write(JSON.stringify({res: res, obj: o, csv: csvText()}));
})();
"""
        jsf = out / "harness.js"
        jsf.write_text(harness, encoding="utf-8")
        pr = subprocess.run([node_exe(), str(jsf)], capture_output=True, text=True, encoding="utf-8")
        try:
            got = json.loads(pr.stdout)
        except Exception:  # noqa: BLE001
            got = None
        check("page logic runs in node", got is not None, (pr.stderr or "")[-400:])
        if got is not None:
            R, O = got["res"], got["obj"]
            check("verdict: refused without an answer; invalid answers / reasons rejected",
                  R["r0"]["ok"] is False and R["badAnswer"] is False and R["reasonWithoutCannot"] is False and R["before"] is False)
            check("reveal: only after a saved verdict (answered-but-unsaved = partial, hidden)",
                  R["st_partial"] == "partial" and R["r1"]["ok"] and R["after"] is True and R["revealed2"] is False)
            row1, row2 = O["rows"][0], O["rows"][1]
            check("export: blind verdict kept (also as `verdict`, the column the return test reads), change after the reveal recorded",
                  row1["verdict_blind"] == q1[0][0] and row1["verdict"] == q1[0][0] and row1["verdict_final"] == q1[1][0]
                  and row1["changed_after_reveal"] is True
                  and row1["n_changes_after_reveal"] == 1 and row1["saved_at"] and row1["revealed_at"], str(row1))
            check("export: unsaved answer has no blind verdict; cannot-tell reason and note carried",
                  row2["verdict_blind"] == "" and row2["verdict"] == "" and row2["verdict_final"] == "cannot_tell" and row2["reason_final"] == "not_visible"
                  and row2["status"] == "partial", str(row2))
            need = {"review_id", "type", "animal", "event_key", "audit_event_id", "track", "selection", "selection_rank", "size_quartile",
                    "onset_local", "onset_al_ms", "end_al_ms", "clip", "zone", "question", "verdict", "verdict_blind", "verdict_final", "reason_blind",
                    "reason_final", "changed_after_reveal", "note", "saved_at", "revealed_at", "reviewer", "status"}
            check("export: JSON schema + one row per event with the join keys", O["schema"] == "wiser_event_review_labels/1" and len(O["rows"]) == 3
                  and need <= set(row1) and O["n_saved"] == 1 and O["selection"]["seed"] == SEED and row1["event_key"].count("|") == 3, str(sorted(set(row1))))
            rows_csv = list(csv.DictReader(io.StringIO(got["csv"])))
            check("export: CSV parses back (quotes, comma, newline in the note) with the same columns",
                  len(rows_csv) == 3 and rows_csv[1]["note"] == 'a "quoted", note\nline2' and list(rows_csv[0]) == list(row1)
                  and rows_csv[0]["verdict_blind"] == q1[0][0], str(rows_csv[1].get("note")))
            check("import: merges verdicts of known ids, keeps the reviewer", R["imported"] == 1 and R["st3b"] == "done" and R["st3"] == "todo"
                  and R["reviewer"] == "zz")
    print("PASS - make_wiser_event_review self-test" if ok_all else "FAIL - make_wiser_event_review self-test")
    return 0 if ok_all else 1


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--audit-run", default=AUDIT_RUN, help="IMU-WISER consistency audit run dir (tables/)")
    ap.add_argument("--root", default=r"F:\3rd_rat", help="cohort video root <root>/<date>/<CH>/")
    ap.add_argument("--tracks-root", default=TRACKS_ROOT)
    ap.add_argument("--imu-seconds-root", default=IMU_SECONDS_ROOT)
    ap.add_argument("--out", default=None, help="output folder (default: a new run dir under $FIELD2026_ANALYSIS_OUT_ROOT/<c>/)")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--encoder", choices=["auto", "nvenc", "x264"], default="auto")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--no-clips", action="store_true", help="panels + page only (clips already in --out are kept)")
    ap.add_argument("--only", nargs="+", default=None, help="review ids (W01 ...) - for testing; writes a page with only these")
    ap.add_argument("--html-only", default=None, help="rebuild index.html of an existing run from its events.json")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.html_only:
        return html_only(Path(a.html_only))
    return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
