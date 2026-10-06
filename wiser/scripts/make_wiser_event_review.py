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

GUI v2 (--circles; plan implementation_plan/2026-10-06-wiser-event-review-circles.md + its amendments): the same events,
W ids and order, with the reviewed animal's WISER position drawn as the projected 14-in circle. WISER (V3 track, aligned
clock t_al) -> paddock by the accepted similarity map of `cv/cv_field/wiser_assist_p0.py` (`mapping.json` of --map-run;
accepted on ONE hour of CH01 only) -> upright camera pixel by the Newton inverse (`wiser_assist_p0.invert_mapper`, started
at the nearest mapped grid centre of its `Support`) of `frame_correction.Corrections(c).to_paddock(cam, t, uv, z_mm=60)`,
evaluated at each 0.25-s overlay step's whole second; the ring = 48 paddock points 14 in from the centre, each inverted.
  BLIND clip (`clips/`): v1's overlay + a static dashed white circle at the start position P0 (I1: the audit reference;
        I2: V3 median over the first second of the window), projected at the event onset, labelled "start".
  REVEAL clip (`clips_reveal/`, shown after the first answer): + the moving solid circle (V3 at each step centre, linear
        between rows <= 5 s apart) and the raw fix nearest the step centre (<= 0.5 s) as a dot; second question "Does the
        WISER circle stay on the rat?" -> `circle_verdict` (on_rat / drifts_off / cannot_tell; `no_circle` set by the page
        when the reveal clip has no circle); "start circle off" tick -> `map_flag`.
  No projection (to_paddock refuses: CH05, CH07, CH08; target outside the camera's mapped ground; inverse failed): no
        circle, on-screen "no projection — use the IR mark". Day frames use the nearest night correction (flagged on screen).
  Both clips come from one ffmpeg decode (split -> two subtitle passes). Extra outputs: `clips_reveal/`,
  `overlay_ass_reveal/`, `projection_coverage.csv` (per event and camera: circle shares, convergence, round trip).

Usage (base Python + matplotlib + ffmpeg; node for the self-test and the page check):
  python wiser/scripts/make_wiser_event_review.py --cohort 2026c [--audit-run <dir>] [--root F:\3rd_rat] [--workers 3]
         [--encoder auto|nvenc|x264] [--no-clips] [--only W03 W17] [--circles [--map-run <p0 run>]]
  python wiser/scripts/make_wiser_event_review.py --html-only <run_dir>      # rebuild index.html from events.json
  python wiser/scripts/make_wiser_event_review.py --selftest                 # synthetic data and video, no field data
Without --circles the run is GUI v1 (identical clips, page and export).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
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
                cache: TrackCache | None, scale: float = 1.0, audit_run: str = "", circ: "CircleCtx | None" = None) -> tuple[dict, dict]:
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
    if circ is not None:                                     # GUI v2: start circle on the blind clip, moving circle on the reveal clip
        if cache is None:
            raise ValueError("--circles needs the WISER tracks (TrackCache)")
        Fc, _ = cache.window(ev["animal"], clip["lo_ms"] - 1000 * (GAP_MAX_S + 1), clip["hi_ms"] + 1000 * (GAP_MAX_S + 1), float(ev["tau_ms"]))
        sizes = [circ.native_size(c, pp, ffprobe) for (c, _), pp in zip(cams, vparts)]
        views = event_circles(ev, clip, Fc, cams, lay, circ, sizes)
        Tc = write_circle_overlays(out_dir / "overlay_ass" / f"{stem}.ass", out_dir / "overlay_ass_reveal" / f"{stem}.ass", lay, views,
                                   clip["dur_s"], fonts)
        payload["circles"] = circles_payload(views, f"{stem}.mp4")
        job.update({"out_reveal": str(out_dir / "clips_reveal" / f"{stem}.mp4"), "ass_reveal_rel": f"overlay_ass_reveal/{stem}.ass",
                    "circle_timing": Tc, "coverage": coverage_rows(payload, views)})
    return payload, job


# ====================================================================================================== circles (GUI v2, --circles)
PLAN_V2 = "implementation_plan/2026-10-06-wiser-event-review-circles.md"
MAP_RUN = r"D:/Field2026_analysis_out/2026c/cv_field_wiser_assist_p0_20261005_2211"
CIRCLE_R_IN = 14.0              # ring radius (paddock inches)
RING_N = 48                     # ring points (each inverted separately)
Z_MM = 60.0                     # assumed height of the rat's back (wiser_assist_p0 / calibration README)
GAP_MAX_S = 5.0                 # V3 at a step centre: linear between the bracketing rows if <= 5 s apart (p0's Tracks rule)
RAW_WIN_S = 0.5                 # raw dot: the unmasked raw fix nearest the step centre, if within +- 0.5 s
DAY_HOLD_S = 1800.0             # > 30 min outside its night's sampled correction span -> 'day frame' (nearest night sample)
RT_STEP_PX, RT_OFF_PX = 120, (17.0, 11.0)   # round-trip grid (upright px), offset from the support grid centres
SEAM_BAND_PX = 150.0            # pano stitch seam band |u - W/2| < 150 px: two pixels map to one ground point there (paddock_map
                                # RayCamera note); every round-trip miss of the dry run lay within 137 px of it
PANO_CAMS = {"CH01", "CH02"}
NATIVE = {"CH01": (7680, 2160), "CH02": (7680, 2160), "CH03": (4512, 2512), "CH04": (4512, 2512),
          "CH05": (2560, 1920), "CH06": (2560, 1920), "CH07": (2560, 1920), "CH08": (2560, 1920)}     # upright px
NO_PROJ_WHY = {"CH05": "house_1 relocated on 09-18: CH05's correction targets a 09-04 frame, not the calibration",
               "CH07": "in-box camera, not calibrated", "CH08": "in-box camera, not calibrated"}
NOTE_NOPROJ = "no projection — use the IR mark"
CIRC_COL = {"start": "#ffffff", "track": "#ffd400", "raw": "#ff3b6b", "note": "#ffd700"}
CIRCLE_QUESTION = {"key": "circle", "text": "Does the WISER circle stay on the rat?",
                   "options": [["on_rat", "on the rat", "7"], ["drifts_off", "drifts off the rat", "8"], ["cannot_tell", "cannot tell", "9"]]}
MAP_CAVEAT = ("Map caveat: the WISER → paddock map was fitted and accepted on ONE hour of CH01 (2026-09-06 21–22 h, test median "
              "residual 4.4 in); other nights, CH02 and CH06 are extrapolations. If the dashed start circle is not on the rat at the "
              "onset, the map (not WISER) is off for this clip — tick 'start circle off' (m).")
LEGEND_BLIND = "dashed white circle = the start position (where the rat was before the EVENT), 14 in, projected"
LEGEND_REVEAL = ("solid yellow = WISER V3 track (14 in) · red dot = raw WISER fix · dashed white = start position · map fitted on 1 h of "
                 "CH01: if the dashed circle misses the rat at the onset, the map is off, not WISER")


class CamProjector:
    """Paddock inches -> upright pixels of one camera around one time: Newton inverse (wiser_assist_p0.invert_mapper, round
    trip <= 1 in) of mapper(t, uv) -> (paddock (n, 2) | None, info), started at the nearest mapped grid centre of p0's
    Support (40-px cells, built at t_ref); the forward map is evaluated at each target's whole second (as p0's clips).
    mapper = Corrections.to_paddock (real run) or a synthetic camera (self-test). Not projectable when the mapper refuses."""

    def __init__(self, P0, cam: str, mapper, t_ref_ms: int, size: tuple, grid_px: int = 40):
        self.P0, self.cam, self.mapper, self.size = P0, cam, mapper, (int(size[0]), int(size[1]))
        self.ok, self.reason, self.info, self.sup, self.flag = False, "", {}, None, ""
        self.day, self.day_used = False, ""
        if mapper is None:
            self.reason = f"{cam}: no mapper"
            return
        t = MV.ms_to_dt(t_ref_ms)
        W, H = self.size
        p, info = mapper(t, np.array([[W / 2.0, H / 2.0]]))
        self.info = {k: v for k, v in dict(info).items() if not str(k).startswith("_")}
        self.flag = str(info.get("flag", ""))
        if p is None:
            why = NO_PROJ_WHY.get(cam, "")
            self.reason = f"{cam}: to_paddock refuses ({self.flag})" + (f" - {why}" if why else "")
            return
        prm = replace(P0.Params(), width=W, height=H, grid_px=grid_px)
        try:
            self.sup = P0.Support(self._ok_flag, t, prm)
        except Exception as e:  # noqa: BLE001
            self.reason = f"{cam}: support grid not mappable ({e})"
            return
        if not len(self.sup.cen_uv):
            self.reason = f"{cam}: no mapped ground in the frame"
            return
        self.ok = True
        self.day, self.day_used = day_frame(info, t)

    def _ok_flag(self, t, uv):
        """p0's Support refuses any correction flag but 'ok'; a flagged correction is still drawn (and shown on screen)."""
        p, info = self.mapper(t, uv)
        return (p, {**info, "flag": "ok"}) if p is not None else (p, info)

    def fwd_at(self, s_ms: int):
        t = MV.ms_to_dt(s_ms)

        def f(q):
            p, _ = self.mapper(t, np.asarray(q, float))
            return np.full((len(q), 2), np.nan) if p is None else np.asarray(p, float).reshape(-1, 2)
        return f

    def project(self, t_ms, P: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """t_ms (n,) ms; P (n, k, 2) paddock in -> uv (n, k, 2) upright px (NaN = none), status (n, k) in
        {ok, out of view, inverse failed, no projection, no target}, round-trip err (n, k) in."""
        P = np.asarray(P, float)
        n, k = P.shape[:2]
        uv = np.full((n, k, 2), np.nan)
        err = np.full((n, k), np.nan)
        status = np.full((n, k), "no target", dtype=object)
        fin = np.isfinite(P).all(2)
        if not self.ok:
            status[fin] = "no projection"
            return uv, status, err
        insup = np.zeros((n, k), bool)
        if fin.any():
            insup[fin] = self.sup.contains(P[fin])
        sec = (np.round(np.asarray(t_ms, float) / 1000.0) * 1000.0).astype(np.int64)
        for s in np.unique(sec):
            rows = np.flatnonzero(sec == s)
            fi, fj = np.nonzero(insup[rows])
            if not fi.size:
                continue
            tgt = P[rows[fi], fj]
            u0, _ = self.sup.nearest_px(tgt)
            u_, _J, e_ = self.P0.invert_mapper(self.fwd_at(int(s)), tgt, u0.astype(float))
            uv[rows[fi], fj] = u_
            err[rows[fi], fj] = e_
        good = np.isfinite(uv).all(2)
        status[fin & ~insup] = "out of view"
        status[insup & good] = "ok"
        status[insup & ~good] = "inverse failed"
        return uv, status, err

    def roundtrip(self, t_ms: int, step: int = RT_STEP_PX, off=RT_OFF_PX) -> dict:
        """Grid pixel -> paddock (forward) -> pixel (inverse, from the nearest support centre): error in px."""
        if not self.ok:
            return {}
        W, H = self.size
        uu, vv = np.meshgrid(np.arange(off[0], W, step), np.arange(off[1], H, step))
        uv = np.stack([uu.ravel(), vv.ravel()], 1).astype(float)
        f = self.fwd_at(int(round(t_ms / 1000.0) * 1000))
        P = f(uv)
        keep = np.isfinite(P).all(1)
        keep[keep] = self.sup.contains(P[keep])
        if not keep.any():
            return {"rt_n": 0}
        u0, _ = self.sup.nearest_px(P[keep])
        uh, _J, _e = self.P0.invert_mapper(f, P[keep], u0.astype(float))
        d = np.hypot(uh[:, 0] - uv[keep, 0], uh[:, 1] - uv[keep, 1])
        conv = np.isfinite(d)
        seam = (np.abs(uv[keep, 0] - W / 2.0) < SEAM_BAND_PX) if self.cam in PANO_CAMS else np.zeros(len(d), bool)
        dc = d[conv]
        off_seam = conv & ~seam
        return {"rt_n": int(keep.sum()), "rt_converged_share": round(float(conv.mean()), 4),
                "rt_med_px": round(float(np.median(dc)), 4) if dc.size else None,
                "rt_p99_px": round(float(np.percentile(dc, 99)), 4) if dc.size else None,
                "rt_max_px": round(float(dc.max()), 4) if dc.size else None,
                "rt_le1_share": round(float(np.sum(d <= 1.0) / len(d)), 4),
                "rt_gt1_n": int(np.sum(conv & (d > 1.0))), "rt_gt1_seam_n": int(np.sum(conv & seam & (d > 1.0))),
                "rt_max_px_off_seam": round(float(d[off_seam].max()), 4) if off_seam.any() else None}


def day_frame(info: dict, t: datetime) -> tuple[bool, str]:
    """A frame > 30 min outside its night's sampled span gets the nearest night sample (frame_correction): flag it."""
    used = info.get("used")
    if not isinstance(used, list) or len(used) != 1:
        return False, ""
    try:
        tu = datetime.strptime(str(used[0]), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False, ""
    return abs((t - tu).total_seconds()) > DAY_HOLD_S, f"{tu:%H:%M}"


class CircleCtx:
    """What the circles need, loaded once: p0's module (Map, Support, invert_mapper, Tracks), the accepted map + lag, one
    mapper per camera (to_paddock), the cameras' upright sizes."""

    def __init__(self, P0, m, L: float, mappers: dict, native: dict, desc: dict, map_run: str):
        self.P0, self.map, self.L, self.mappers, self.native, self.desc, self.map_run = P0, m, float(L), mappers, dict(native), desc, map_run
        self._proj, self._size = {}, {}
        self.size_notes = []

    def projector(self, cam: str, t_ref_ms: int, size: tuple) -> CamProjector:
        k = (cam, int(t_ref_ms), tuple(size))
        if k not in self._proj:
            self._proj[k] = CamProjector(self.P0, cam, self.mappers.get(cam), int(t_ref_ms), size)
        return self._proj[k]

    def native_size(self, cam: str, parts: list, ffprobe: str | None) -> tuple:
        """Upright size of the camera: the calibration's (NATIVE), checked against the first source file (stored size;
        panos are stored rotated). A mismatch is logged and the probed size used."""
        exp = self.native.get(cam, (0, 0))
        if not parts or not ffprobe or not parts[0].get("path"):
            return exp
        f = parts[0]["path"]
        if f not in self._size:
            pr = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", f],
                                capture_output=True, text=True)
            try:
                w, h = [int(x) for x in pr.stdout.strip().split(",")[:2]]
                self._size[f] = (h, w) if cam in PANO_CAMS else (w, h)
            except ValueError:
                self._size[f] = exp
        got = self._size[f]
        if tuple(got) != tuple(exp):
            self.size_notes.append(f"{cam} {Path(f).name}: upright {got[0]}x{got[1]} != expected {exp[0]}x{exp[1]}")
        return got


def import_p0(with_corrections: str | None = None):
    """wiser_assist_p0 (and, if a cohort is given, frame_correction.Corrections(cohort) with its calibration loaded), imported
    unchanged with cv/ on sys.path only while importing / loading. -> (P0 module, Corrections or None)."""
    saved = list(sys.path)
    for p in (str(REPO / "cv" / "cv_field"), str(REPO / "cv")):
        if p not in sys.path:
            sys.path.append(p)
    try:
        import wiser_assist_p0 as P0  # noqa: E402  (Map, Params, Support, invert_mapper, Tracks; imported unchanged)
        C = None
        if with_corrections:
            import frame_correction as FC  # noqa: E402  (Corrections.to_paddock; imported unchanged)
            C = FC.Corrections(with_corrections)
            C.to_paddock("CH01", datetime(2026, 9, 6, 21, 30), np.array([[3840.0, 1500.0]]), z_mm=Z_MM, units="in")  # loads paddock_map
    finally:
        sys.path[:] = saved
    return P0, C


def load_circle_ctx(map_run: str, cohort: str) -> CircleCtx:
    """Read the accepted map of --map-run; one mapper per camera = Corrections(cohort).to_paddock (z 60 mm, inches)."""
    P0, C = import_p0(with_corrections=cohort)
    mj = json.loads((Path(map_run) / "mapping.json").read_text(encoding="utf-8"))
    if not mj.get("accepted"):
        raise SystemExit(f"{map_run}: the WISER -> paddock map was not accepted - no circles")
    am = mj["accepted_map"]
    m = P0.Map(float(am["dx_in"]), float(am["dy_in"]), float(np.radians(am["theta_deg"])), float(am["scale"]),
               float(am["centre_wiser_in"][0]), float(am["centre_wiser_in"][1]))
    L = float(mj["accepted_L_s"])
    t = mj.get("test_chosen", {})
    desc = {"map_run": str(map_run), "adopted": mj.get("adopted"), "map": am, "L_s": L, "camera_fitted": mj.get("camera"),
            "hour_fitted": mj.get("hour_start"), "test_median_in": t.get("resid_median_in"), "test_p90_in": t.get("resid_p90_in"),
            "text": (f"paddock = s R(θ)(WISER − c) + c + d, d ({am['dx_in']:.2f}, {am['dy_in']:.2f}) in, θ {am['theta_deg']:.3f}°, "
                     f"s {am['scale']:.4f}, lag {L:+.1f} s; fitted on {mj.get('camera')} {mj.get('hour_start')} + 1 h, test median "
                     f"{float(t.get('resid_median_in', float('nan'))):.2f} in")}

    def mk(cam):
        return lambda tt, uv: C.to_paddock(cam, tt, np.asarray(uv, float), z_mm=Z_MM, units="in")
    return CircleCtx(P0, m, L, {cam: mk(cam) for cam in NATIVE}, NATIVE, desc, str(map_run))


def start_position(ev: dict, clip: dict, F: pd.DataFrame) -> np.ndarray:
    """P0 in the WISER frame, as the v1 panel: I1 the audit reference; I2 V3 median over the first second of the window
    (else over the clip)."""
    if ev["type"] == "I1":
        return np.array([float(ev["ref_x"]), float(ev["ref_y"])])
    if not len(F):
        return np.array([np.nan, np.nan])
    t = (F["t_al"].to_numpy(float) - float(clip["lo_ms"])) / 1000.0
    xv, yv = F["x"].to_numpy(float), F["y"].to_numpy(float)
    e0 = float(clip["ev_t0_s"])
    k = (t >= e0) & (t < e0 + 1.0)
    if k.sum():
        return np.array([np.median(xv[k]), np.median(yv[k])])
    k = (t >= 0) & (t <= float(clip["dur_s"]))
    return np.array([np.median(xv[k]), np.median(yv[k])]) if k.sum() else np.array([np.nan, np.nan])


def to_view(uv: np.ndarray, v: dict, size: tuple) -> np.ndarray:
    """Upright px (pixel centres at integers) -> ASS coordinates of the view (pixel i spans [i, i + 1)): x = x0 + (u + 0.5) w / W."""
    uv = np.asarray(uv, float)
    out = np.full(uv.shape, np.nan)
    out[..., 0] = v["x"] + (uv[..., 0] + 0.5) * v["w"] / float(size[0])
    out[..., 1] = v["y"] + (uv[..., 1] + 0.5) * v["h"] / float(size[1])
    return out


def event_circles(ev: dict, clip: dict, F: pd.DataFrame, cams: list, lay: dict, circ: CircleCtx, sizes: list) -> list:
    """Per view: the static start ring (projected at the onset) and, per 0.25-s step, the moving ring (V3 at the step centre)
    and the raw dot, in view (ASS) coordinates, with statuses and the counts of the coverage table."""
    lo = int(clip["lo_ms"])
    D = float(clip["dur_s"])
    nb = int(math.ceil(D / DYN_STEP_S - 1e-9))
    tc = lo + np.round((np.arange(nb) + 0.5) * DYN_STEP_S * 1000.0).astype(np.int64)      # step centres, aligned ms
    t_on = int(round(float(ev["t0"]) * 1000.0))
    Fv = F.dropna(subset=["x", "y"]).sort_values("t_al")
    data = pd.DataFrame({"s": (Fv["t_al"].to_numpy(float) - lo) / 1000.0, "x": Fv["x"].to_numpy(float), "y": Fv["y"].to_numpy(float),
                         "imu_state": Fv["imu_state"].fillna(-1).to_numpy(float).astype(int)})
    tracks = circ.P0.Tracks({ev["animal"]: data}, GAP_MAX_S)
    X, _S, okx = tracks.at((tc - lo) / 1000.0 + circ.L)
    located = okx[:, 0]
    Xw = np.where(located[:, None], X[:, 0, :], np.nan)
    Fr = F.dropna(subset=["x_raw", "y_raw"]).sort_values("t_al")
    tr = Fr["t_al"].to_numpy(float)
    raw = np.full((nb, 2), np.nan)
    if len(tr):
        i = np.searchsorted(tr, tc + 1000.0 * circ.L)
        cand = np.stack([np.clip(i - 1, 0, len(tr) - 1), np.clip(i, 0, len(tr) - 1)], 1)
        dt = np.abs(tr[cand] - (tc + 1000.0 * circ.L)[:, None])
        j = cand[np.arange(nb), np.argmin(dt, 1)]
        near = dt.min(1) <= RAW_WIN_S * 1000.0
        raw[near] = np.column_stack([Fr["x_raw"].to_numpy(float), Fr["y_raw"].to_numpy(float)])[j[near]]
    p0w = start_position(ev, clip, F)
    phi = np.linspace(0.0, 2.0 * np.pi, RING_N, endpoint=False)
    ring = CIRCLE_R_IN * np.column_stack([np.cos(phi), np.sin(phi)])
    Pc, Pr = circ.map.fwd(Xw), circ.map.fwd(raw)
    Ps = circ.map.fwd(p0w[None, :])[0] if np.isfinite(p0w).all() else np.array([np.nan, np.nan])
    views = []
    for (cam, role), v, size in zip(cams, lay["views"], sizes):
        pr = circ.projector(cam, t_on, size)
        vw = {"cam": cam, "role": role, "projectable": pr.ok, "reason": pr.reason, "flag": pr.flag, "day": bool(pr.day),
              "day_used": pr.day_used, "size": list(size), "nb": nb, "located": located.copy(),
              "start_pos_ok": bool(np.isfinite(Ps).all())}
        tgtS = (Ps[None, None, :] + np.vstack([[0.0, 0.0], ring])[None, :, :])
        uvS, stS, errS = pr.project(np.array([t_on]), tgtS)
        vw["start_status"] = "no start position" if not vw["start_pos_ok"] else str(stS[0, 0])
        vw["start_ok"] = vw["start_status"] == "ok"
        vw["start_centre"] = to_view(uvS[0, 0], v, size) if vw["start_ok"] else None
        vw["start_ring"] = to_view(uvS[0, 1:], v, size) if vw["start_ok"] else None
        vw["start_ring_px"] = uvS[0, 1:] if vw["start_ok"] else None
        tgtM = np.concatenate([Pc[:, None, :], Pc[:, None, :] + ring[None, :, :], Pr[:, None, :]], axis=1)
        uvM, stM, errM = pr.project(tc, tgtM)
        st_c = np.where(located, stM[:, 0], "not located").astype(object)
        vw["st_centre"] = st_c
        vw["st_raw"] = np.where(np.isfinite(Pr).all(1), stM[:, -1], "no raw fix").astype(object)
        vw["centre"] = to_view(uvM[:, 0], v, size)
        vw["ring"] = to_view(uvM[:, 1:-1], v, size)
        vw["ring_px"] = uvM[:, 1:-1]
        vw["centre_px"] = uvM[:, 0]
        vw["raw"] = to_view(uvM[:, -1], v, size)
        vw["paddock_centre"] = Pc
        insup = np.isin(stM, ["ok", "inverse failed"])
        insS = np.isin(stS, ["ok", "inverse failed"])
        n_in = int(insup.sum() + insS.sum())
        n_ok = int((stM == "ok").sum() + (stS == "ok").sum())
        e_ok = np.r_[errM[stM == "ok"], errS[stS == "ok"]]
        seam = (np.abs(uvM[:, 0, 0] - size[0] / 2.0) < SEAM_BAND_PX) & (st_c == "ok") if cam in PANO_CAMS else np.zeros(nb, bool)
        vw["seam"] = seam
        vw["counts"] = {"steps": nb, "steps_located": int(located.sum()), "steps_circle": int(np.sum(st_c == "ok")),
                        "steps_seam": int(seam.sum()),
                        "steps_out_of_view": int(np.sum(st_c == "out of view")), "steps_inverse_failed": int(np.sum(st_c == "inverse failed")),
                        "steps_raw_dot": int(np.sum(vw["st_raw"] == "ok")),
                        "ring_points_drawn_share": round(float(np.mean(stM[st_c == "ok"][:, 1:-1] == "ok")), 4) if np.any(st_c == "ok") else None,
                        "targets_in_support": n_in, "targets_converged": n_ok,
                        "convergence_rate": round(n_ok / n_in, 4) if n_in else None,
                        "inverse_err_max_in": round(float(e_ok.max()), 4) if e_ok.size else None}
        vw["roundtrip"] = pr.roundtrip(t_on) if pr.ok else {}
        views.append(vw)
    return views


# ---------------------------------------------------------------------------------------------- overlay drawing (ASS \p3)
def _q4(x: float) -> int:
    return int(round(4.0 * float(x)))           # \p3 drawing units = 1/4 px


def ass_ring(pts: np.ndarray, dashed: bool = False, w: float = 3.0) -> str:
    """Closed ring through pts (view coords, NaN = point not projected) as filled stroke quads (\\p3 units); dashed = every
    other segment; a segment with a missing end, or > 3x the median segment, is left out (seam / support edge)."""
    pts = np.asarray(pts, float)
    n = len(pts)
    seg = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        if np.isfinite(a).all() and np.isfinite(b).all():
            seg.append((i, a, b, math.hypot(*(b - a))))
    if not seg:
        return ""
    med = float(np.median([s[3] for s in seg]))
    parts = []
    for i, a, b, L in seg:
        if (dashed and i % 2) or L < 1e-6 or L > 3.0 * max(med, 1e-6):
            continue
        d = (b - a) / L
        nn = np.array([-d[1], d[0]]) * (w / 2.0)
        q = (a + nn, b + nn, b - nn, a - nn)
        parts.append("m {} {} l {} {} {} {} {} {}".format(*[_q4(c) for p in q for c in p]))
    return " ".join(parts)


def ass_disc(c: np.ndarray, r: float, n: int = 12) -> str:
    phi = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    P = np.column_stack([c[0] + r * np.cos(phi), c[1] + r * np.sin(phi)])
    return "m {} {} l ".format(_q4(P[0, 0]), _q4(P[0, 1])) + " ".join(f"{_q4(x)} {_q4(y)}" for x, y in P[1:])


def _draw_tag(col: str, bord: float) -> str:
    return f"{{\\an7\\pos(0,0)\\p3\\bord{bord:.1f}\\shad0\\1a&H00&\\1c{MV.ass_c(col)}\\3c&H000000&\\3a&H30&}}"


def _runs(labels: np.ndarray) -> list:
    """[(start index, end index exclusive, label)] of consecutive equal labels."""
    out, k = [], 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[k]:
            out.append((k, i, labels[k]))
            k = i
    return out


DYN_NOTE = {"not located": "circle: WISER has no fix here (gap > 5 s)",
            "out of view": "circle outside this camera's mapped ground — use the IR mark",
            "inverse failed": NOTE_NOPROJ + " (inverse failed)"}


def static_notes(vw: dict, phase: str) -> list:
    n = []
    if not vw["projectable"]:
        why = NO_PROJ_WHY.get(vw["cam"], "")
        n.append(NOTE_NOPROJ + (f" ({why})" if why else ""))
    else:
        if phase == "blind" and not vw["start_ok"]:
            n.append(NOTE_NOPROJ + (" (start position outside this camera's mapped ground)" if vw["start_status"] == "out of view"
                                    else f" ({vw['start_status']})"))
        if vw["day"]:
            n.append(f"outside the corrected night hours: nearest night correction ({vw['day_used']}) — circles approximate")
        if vw["flag"] and vw["flag"] != "ok":
            n.append(f"correction flag: {vw['flag']}")
    return n


def write_circle_overlays(blind_path: Path, reveal_path: Path, lay: dict, views: list, D: float, fonts: dict,
                          step: float = DYN_STEP_S) -> dict:
    """blind_path holds v1's blind overlay (write_ass_blind): copy it to reveal_path, then add the static start ring + notes
    to the blind file and start ring + moving ring + raw dot + legend + notes to the reveal file. Returns a timing table."""
    base = blind_path.read_text(encoding="utf-8")
    sc = lay["scale"]
    m = max(8, int(round(24 * sc)))
    w = max(2.0, 3.0 * sc)
    bord = max(1.0, 1.5 * sc)
    fs_note, fs_lab = 34 * sc, 32 * sc
    T = {"blind_start": [], "reveal_start": [], "reveal_moving": [], "reveal_raw": [], "notes": {"blind": [], "reveal": []},
         "dyn": [], "text": {"blind": [], "reveal": []}}
    out = {"blind": [], "reveal": []}

    def note(phase, vi, v, row, txt, a=0.0, b=D):
        y = v["y"] + m + int(round((64 + 46 * row) * sc))
        s = MV.fit_size(txt, fs_note, False, v["w"] - 2 * m, fonts)
        out[phase].append(f"Dialogue: 4,{MV.ass_time(a)},{MV.ass_time(b)},Label,,0,0,0,,{{\\pos({v['x'] + m},{y})\\fs{s:.0f}"
                          f"\\1c{MV.ass_c(CIRC_COL['note'] if row else '#ffffff')}}}{MV.ass_escape(txt)}")
        T["text"][phase].append(txt)
        return (vi, a, b, txt)

    def label(phase, ring, txt, col, a, b):
        f = np.isfinite(ring).all(1)
        if not f.any():
            return
        x, y = float(np.mean(ring[f, 0])), float(np.min(ring[f, 1])) - 4 * sc
        out[phase].append(f"Dialogue: 4,{MV.ass_time(a)},{MV.ass_time(b)},Static,,0,0,0,,{{\\an2\\pos({x:.0f},{y:.0f})\\fs{fs_lab:.0f}"
                          f"\\bord{max(1.0, 2 * sc):.1f}\\1c{MV.ass_c(col)}\\3c&H000000&}}{MV.ass_escape(txt)}")
        T["text"][phase].append(txt)

    for vi, (vw, v) in enumerate(zip(views, lay["views"])):
        for phase in ("blind", "reveal"):
            if vw["start_ok"]:
                dr = ass_ring(vw["start_ring"], dashed=True, w=w)
                if dr:
                    out[phase].append(f"Dialogue: 3,{MV.ass_time(0)},{MV.ass_time(D)},Static,,0,0,0,,{_draw_tag(CIRC_COL['start'], bord)}{dr}{{\\p0}}")
                    T[f"{phase}_start"].append((vi, 0.0, D, tuple(vw["start_centre"])))
                    label(phase, vw["start_ring"], "start", CIRC_COL["start"], 0.0, D)
            row = 0
            if phase == "blind" and vw["start_ok"]:
                note(phase, vi, v, row, LEGEND_BLIND)
                row += 1
            if phase == "reveal" and vw["projectable"]:
                note(phase, vi, v, row, LEGEND_REVEAL)
                row += 1
            sn = static_notes(vw, phase)
            if sn:
                T["notes"][phase].append(note(phase, vi, v, max(row, 1), " · ".join(sn)))
                row = max(row, 1) + 1
            if phase == "reveal" and vw["projectable"]:
                for k0, k1, lab in _runs(np.asarray(vw["st_centre"], dtype=object)):
                    if lab in DYN_NOTE:
                        T["dyn"].append(note(phase, vi, v, max(row, 1), DYN_NOTE[lab], k0 * step, min(D, k1 * step)))
        for k in range(vw["nb"]):
            a, b = k * step, min(D, (k + 1) * step)
            if b <= a:
                continue
            if vw["st_centre"][k] == "ok":
                dr = ass_ring(vw["ring"][k], dashed=False, w=w)
                if dr:
                    out["reveal"].append(f"Dialogue: 3,{MV.ass_time(a)},{MV.ass_time(b)},Static,,0,0,0,,{_draw_tag(CIRC_COL['track'], bord)}{dr}{{\\p0}}")
                    T["reveal_moving"].append((vi, a, b, tuple(vw["centre"][k])))
                    label("reveal", vw["ring"][k], "WISER", CIRC_COL["track"], a, b)
            if vw["st_raw"][k] == "ok":
                out["reveal"].append(f"Dialogue: 3,{MV.ass_time(a)},{MV.ass_time(b)},Static,,0,0,0,,{_draw_tag(CIRC_COL['raw'], bord)}"
                                     f"{ass_disc(vw['raw'][k], max(3.0, 6.0 * sc))}{{\\p0}}")
                T["reveal_raw"].append((vi, a, b, tuple(vw["raw"][k])))
    reveal_path.parent.mkdir(parents=True, exist_ok=True)
    reveal_path.write_text(base + "\n".join(out["reveal"]) + ("\n" if out["reveal"] else ""), encoding="utf-8")
    blind_path.write_text(base + "\n".join(out["blind"]) + ("\n" if out["blind"] else ""), encoding="utf-8")
    return T


def _pct(x) -> str:
    return "—" if x is None else f"{100 * x:.0f} %"


def circles_payload(views: list, reveal_file: str) -> dict:
    cams = []
    for vw in views:
        c = vw["counts"]
        share = c["steps_circle"] / c["steps"] if c["steps"] else 0.0
        if not vw["projectable"]:
            tb = tr = f"{NOTE_NOPROJ} — {vw['reason']}"
        else:
            tb = "start circle" if vw["start_ok"] else f"no start circle ({vw['start_status']}) — {NOTE_NOPROJ}"
            extra = [f"outside the corrected night hours: nearest night correction ({vw['day_used']}), circles approximate"] if vw["day"] else []
            if vw["flag"] and vw["flag"] != "ok":
                extra.append(f"correction flag {vw['flag']}")
            tb = "; ".join([tb] + extra)
            tr = "; ".join([("start circle" if vw["start_ok"] else "no start circle") +
                            f"; WISER circle in {_pct(share)} of the clip (WISER located {_pct(c['steps_located'] / c['steps'] if c['steps'] else None)})"] + extra)
        cams.append({"cam": vw["cam"], "role": vw["role"], "projectable": bool(vw["projectable"]), "reason": vw["reason"],
                     "flag": vw["flag"], "day_frame": bool(vw["day"]), "day_used": vw["day_used"], "start": bool(vw["start_ok"]),
                     "share": round(share, 4), "text_blind": tb, "text_reveal": tr})
    any_start = any(c["start"] for c in cams)
    any_moving = any(c["share"] > 0 for c in cams)
    why = ""
    if not any_start and not any_moving:
        pc = np.asarray(views[0]["paddock_centre"], float) if views else np.zeros((0, 2))
        pc = pc[np.isfinite(pc).all(1)] if len(pc) else pc
        where = (f" (the mapped WISER position, median paddock ({np.median(pc[:, 0]):.0f}, {np.median(pc[:, 1]):.0f}) in, is outside the "
                 "camera's mapped ground)") if len(pc) else ""
        why = "; ".join((vw["reason"] if not vw["projectable"] else
                         f"{vw['cam']}: start {vw['start_status']}, moving circle in 0 of {vw['counts']['steps']} steps "
                         f"(located {vw['counts']['steps_located']})" + where) for vw in views)
    return {"reveal_file": reveal_file, "reveal_ok": False, "any_start": any_start, "any_moving": any_moving, "cams": cams,
            "no_circle_reason": why}


COVERAGE_COLS = ["review_id", "type", "animal", "zone", "camera", "role", "projectable", "no_projection_reason", "correction_flag",
                 "day_frame", "day_correction_from", "start_position", "start_circle", "start_status", "steps", "steps_located",
                 "steps_circle", "share_circle", "share_circle_of_located", "steps_seam", "steps_out_of_view", "steps_inverse_failed",
                 "steps_raw_dot", "ring_points_drawn_share", "targets_in_support", "targets_converged", "convergence_rate",
                 "inverse_err_max_in", "rt_n", "rt_converged_share", "rt_med_px", "rt_p99_px", "rt_max_px", "rt_le1_share",
                 "rt_gt1_n", "rt_gt1_seam_n", "rt_max_px_off_seam"]


def coverage_rows(payload: dict, views: list) -> list:
    rows = []
    for vw in views:
        c, rt = vw["counts"], vw["roundtrip"]
        rows.append({"review_id": payload["id"], "type": payload["type"], "animal": payload["animal"], "zone": payload["zone"],
                     "camera": vw["cam"], "role": vw["role"], "projectable": bool(vw["projectable"]),
                     "no_projection_reason": "" if vw["projectable"] else vw["reason"], "correction_flag": vw["flag"],
                     "day_frame": bool(vw["day"]), "day_correction_from": vw["day_used"], "start_position": bool(vw["start_pos_ok"]),
                     "start_circle": bool(vw["start_ok"]), "start_status": vw["start_status"], "steps": c["steps"],
                     "steps_located": c["steps_located"], "steps_circle": c["steps_circle"],
                     "share_circle": round(c["steps_circle"] / c["steps"], 4) if c["steps"] else None,
                     "share_circle_of_located": round(c["steps_circle"] / c["steps_located"], 4) if c["steps_located"] else None,
                     **{k: c[k] for k in ("steps_seam", "steps_out_of_view", "steps_inverse_failed", "steps_raw_dot", "ring_points_drawn_share",
                                          "targets_in_support", "targets_converged", "convergence_rate", "inverse_err_max_in")},
                     **{k: rt.get(k) for k in COVERAGE_COLS if k.startswith("rt_")}})
    return rows


def ffmpeg_cmd_pair(ffmpeg: str, lay: dict, view_parts_list: list, D: float, ass_rels: list, fonts_rel: str, outs: list, enc: str) -> list:
    """make_imu_video_review.ffmpeg_cmd's canvas / overlay chain, decoded once, split into one subtitle pass per output."""
    W, H = lay["W"], lay["H"]
    base = "0x{:02X}{:02X}{:02X}".format(*MV.BASE_RGB)
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-v", "info"]
    filt = [f"color=c={base}:s={W}x{H}:r={MV.FPS}:d={D:.3f},format=yuv420p[base]"]
    last, k = "base", 0
    for v, parts in zip(lay["views"], view_parts_list):
        for p in parts:
            cmd += ["-ss", f"{p['offset_s']:.3f}", "-t", f"{p['dur_s']:.3f}", "-i", p["path"]]
            chain = (f"scale={v['h']}:{v['w']}:flags=bicubic,transpose=2" if v["pano"] else f"scale={v['w']}:{v['h']}:flags=bicubic")
            filt.append(f"[{k}:v]setpts=PTS+{p['clip_t0_s']:.3f}/TB,{chain},format=yuv420p[p{k}]")
            filt.append(f"[{last}][p{k}]overlay=x={v['x']}:y={v['y']}:eof_action=pass:repeatlast=0[o{k}]")
            last, k = f"o{k}", k + 1
    n = len(ass_rels)
    filt.append(f"[{last}]split={n}" + "".join(f"[s{i}]" for i in range(n)))
    for i, a in enumerate(ass_rels):
        filt.append(f"[s{i}]subtitles=f={a}:fontsdir={fonts_rel},format=yuv420p[v{i}]")
    cmd += ["-filter_complex", ";".join(filt)]
    for i, o in enumerate(outs):
        cmd += ["-map", f"[v{i}]", "-t", f"{D:.3f}", "-r", str(MV.FPS), "-an", *MV.ENC[enc], "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(o)]
    return cmd


def _probe(ffprobe: str, path: Path) -> dict:
    pr = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=codec_name,width,height,pix_fmt,avg_frame_rate,nb_frames:format=duration,size",
                         "-of", "json", str(path)], capture_output=True, text=True)
    try:
        info = json.loads(pr.stdout)
        st = info["streams"][0]
        return {"width": int(st["width"]), "height": int(st["height"]), "codec": st["codec_name"], "pix_fmt": st["pix_fmt"],
                "duration_s": float(info["format"]["duration"]), "size_bytes": int(info["format"]["size"]),
                "nb_frames": int(st.get("nb_frames") or 0)}
    except Exception as e:  # noqa: BLE001
        return {"probe_error": str(e)}


def render_pair(ffmpeg: str, ffprobe: str, job: dict, workdir: Path, enc: str) -> dict:
    """Blind + reveal clips from one decode (MV.render's contract for the blind clip; the reveal result under 'reveal')."""
    t0 = time.time()
    outs = [Path(job["out"]), Path(job["out_reveal"])]
    tmps = [o.with_name(o.stem + ".partial.mp4") for o in outs]
    ass = [job["ass_rel"], job["ass_reveal_rel"]]
    cmd = ffmpeg_cmd_pair(ffmpeg, job["layout"], job["view_parts"], job["D"], ass, job["fonts_rel"], tmps, enc)
    p = subprocess.run(cmd, cwd=str(workdir), capture_output=True)
    used = enc
    if p.returncode != 0 and enc == "nvenc":
        used = "x264"
        cmd = ffmpeg_cmd_pair(ffmpeg, job["layout"], job["view_parts"], job["D"], ass, job["fonts_rel"], tmps, "x264")
        p = subprocess.run(cmd, cwd=str(workdir), capture_output=True)
    err = p.stderr.decode(errors="replace")
    ok = p.returncode == 0 and all(t.exists() for t in tmps)
    res = {"id": job["id"], "ok": ok, "encoder": used, "seconds": round(time.time() - t0, 1),
           "glyph_warnings": sorted(set(mm.group(0) for mm in MV.GLYPH_WARN.finditer(err)))[:5], "cmd": cmd}
    if not ok:
        res["error"] = err[-1500:]
        for t in tmps:
            if t.exists():
                t.unlink()
        res["reveal"] = {"ok": False}
        return res
    for t, o in zip(tmps, outs):
        os.replace(t, o)
    res.update(_probe(ffprobe, outs[0]))
    res["reveal"] = {"ok": True, **_probe(ffprobe, outs[1])}
    return res


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
.dot.partial{background:var(--warn)}.dot.done{background:var(--ok)}.dot.revealed{background:var(--acc)}
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
 <b id="ttl">WISER event review (blind) · cohort __COHORT__</b>
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
  <div class="box" id="circbox" hidden></div>
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
const CIRC = DATA.circles || null;      // GUI v2 (WISER circles); null = GUI v1
let J = {}, reviewer = "";
function nowIso(){ return new Date().toISOString(); }
function evById(id){ return EV.find(e => e.id === id); }
function jget(id){
  if (!J[id]) {
    J[id] = {verdict: "", reason: "", note: "", verdict_blind: "", reason_blind: "", saved_at: "", revealed_at: "",
             changed_after_reveal: false, n_changes_after_reveal: 0, reviewer: "", updated: ""};
    if (CIRC) Object.assign(J[id], {circle_verdict: "", circle_at: "", map_flag: false});
  }
  return J[id];
}
function isRevealed(id){ const j = J[id]; return !!(j && j.revealed_at); }
function evCirc(id){ const ev = evById(id); return (CIRC && ev && ev.circles) ? ev.circles : null; }
function hasCircle(id){ const c = evCirc(id); return !!(c && c.any_moving); }
function hasStart(id){ const c = evCirc(id); return !!(c && c.any_start); }
function status(id){
  const j = J[id]; if (!j) return "todo";
  if (j.revealed_at) return (CIRC && hasCircle(id) && !j.circle_verdict) ? "revealed" : "done";
  return (j.verdict || j.reason || j.note || (CIRC && j.map_flag)) ? "partial" : "todo";
}
function setCircle(id, v){
  if (!CIRC || !isRevealed(id) || !hasCircle(id) || !CIRC.question.options.some(o => o[0] === v)) return false;
  const j = jget(id); j.circle_verdict = v; j.circle_at = nowIso(); j.updated = nowIso(); j.reviewer = reviewer;
  return true;
}
function setMapFlag(id, b){
  if (!CIRC || !hasStart(id)) return false;
  const j = jget(id); j.map_flag = !!b; j.updated = nowIso(); j.reviewer = reviewer;
  return true;
}
function circleVerdict(id){ if (!hasCircle(id)) return "no_circle"; const j = J[id]; return (j && j.circle_verdict) || ""; }
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
    const r = {review_id: ev.id, idx: ev.idx, type: ev.type, animal: ev.animal, event_key: ev.event_key, audit_event_id: ev.audit_event_id,
      track: "V3", selection: ev.selection, selection_rank: ev.selection_rank == null ? "" : ev.selection_rank,
      size_quartile: ev.size_quartile == null ? "" : ev.size_quartile, onset_local: ev.onset_local, end_local: ev.end_local,
      onset_al_ms: ev.onset_al_ms, end_al_ms: ev.end_al_ms, clip: ev.clip.file, clip_ok: ev.clip.ok, zone: ev.zone, cameras: ev.cams_text,
      question: ev.question.text, verdict: j.verdict_blind || "", verdict_blind: j.verdict_blind || "", reason_blind: j.reason_blind || "", verdict_final: j.verdict || "",
      reason_final: j.reason || "", changed_after_reveal: !!j.changed_after_reveal, n_changes_after_reveal: j.n_changes_after_reveal || 0,
      note: j.note || "", saved_at: j.saved_at || "", revealed_at: j.revealed_at || "", reviewer: j.reviewer || reviewer,
      updated: j.updated || "", status: status(ev.id)};
    if (CIRC) Object.assign(r, {circle_verdict: circleVerdict(ev.id), circle_at: j.circle_at || "",
      map_flag: hasStart(ev.id) ? !!j.map_flag : "", circle_available: hasCircle(ev.id), start_circle_available: hasStart(ev.id),
      reveal_clip: ev.circles ? ev.circles.reveal_file : ""});
    return r; });
}
function exportObject(){
  const o = {schema: "wiser_event_review_labels/1", cohort: DATA.cohort, run_id: DATA.run_id, run_dir: DATA.run_dir, tool: DATA.tool,
    plan: DATA.plan, audit_run: DATA.audit_run, selection: DATA.selection, exported_local: new Date().toString(), reviewer: reviewer,
    n_events: EV.length, n_saved: EV.filter(e => isRevealed(e.id)).length,
    note: "verdict_blind = the first saved verdict, given before the panel was shown; verdict_final = the answer at export time",
    rows: exportRows(), judgements: J};
  if (CIRC) {
    o.gui = "v2 (WISER circles)"; o.circles = {plan: CIRC.plan, map_run: CIRC.map_run, map: CIRC.map_text, caveat: CIRC.caveat};
    o.note += "; circle_verdict = the answer to '" + CIRC.question.text + "' (after the reveal; no_circle = the reveal clip had no circle); " +
      "map_flag = the reviewer ticked 'start circle off' (blank = no start circle on either camera)";
  }
  return o;
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
    const s = status(ev.id); if (s === "done" || s === "revealed") nd++;
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
  let pt = nd + " / " + EV.length + " verdicts saved";
  if (CIRC) pt += " · " + EV.filter(e => isRevealed(e.id) && hasCircle(e.id) && (J[e.id] || {}).circle_verdict).length + " / " +
    EV.filter(e => hasCircle(e.id)).length + " circle answers";
  $("progress").textContent = pt;
}

// ---------------------------------------------------------------- event
function clipSrc(ev){
  if (CIRC && ev.circles && ev.circles.reveal_ok && isRevealed(ev.id)) return "clips_reveal/" + ev.circles.reveal_file;
  return ev.clip.ok ? "clips/" + ev.clip.file : "";
}
function loadVideo(ev, t){
  const src = clipSrc(ev);
  if (src) {
    vid.defaultPlaybackRate = rate; vid.src = src; vid.load(); vid.playbackRate = rate;
    if (t) vid.addEventListener("loadedmetadata", () => { vid.currentTime = Math.min(t, (vid.duration || t) - 0.001); }, {once: true});
  }
  else { vid.pause(); vid.removeAttribute("src"); vid.load(); }
}
function select(i){
  cur = Math.max(0, Math.min(EV.length - 1, i));
  const ev = EV[cur];
  flash = "";
  loadVideo(ev, 0);
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
    if (CIRC && hasCircle(ev.id) && !j.circle_verdict) vs += "<br><span class='warnline'>Now watch the revealed clip and answer the circle question (7 / 8 / 9).</span>";
  } else vs = "<span class='mut'>Not saved yet — the panel stays hidden until you save.</span>";
  let circ = "";
  if (CIRC) {
    const st = hasStart(ev.id), mc = hasCircle(ev.id), open = !!j.revealed_at, cq = CIRC.question;
    circ = "<fieldset id='fsMap'" + (st ? "" : " disabled") + "><legend>Start circle (map check)</legend><label class='opt'><input type='checkbox' id='fMap'" +
        (j.map_flag ? " checked" : "") + "> <kbd>m</kbd>start circle off — the dashed circle is not on the rat at the onset</label>" +
        (st ? "" : "<div class='mut'>no start circle on either camera (no projection)</div>") + "</fieldset>" +
      "<fieldset id='fsCircle'" + (open && mc ? "" : " disabled") + "><legend>After the reveal · WISER circle</legend><div class='qtext'>" + esc(cq.text) + "</div>" +
        radio("circ", cq.options, j.circle_verdict || "") +
        (!mc ? "<div class='mut'>this clip has no WISER circle (no projection) — exported as no_circle</div>" :
         (!open ? "<div class='mut'>opens after you save the first verdict; the clip then shows the moving circle</div>" : "")) + "</fieldset>";
  }
  $("form").innerHTML =
    "<fieldset><legend>" + esc(q.short) + "</legend><div class='qtext'>" + esc(q.text) + "</div>" + radio("ans", q.options, j.verdict) + "</fieldset>" +
    "<fieldset id='fsReason'" + (j.verdict === "cannot_tell" ? "" : " disabled") + "><legend>Why can't you tell? (optional)</legend>" + radio("reason", REASONS, j.reason) + "</fieldset>" +
    "<fieldset><legend>Note (optional)</legend><textarea id='fNote' placeholder='what you saw'>" + esc(j.note) + "</textarea></fieldset>" + circ +
    "<div id='vstate'>" + vs + (flash ? "<br><span class='warnline'>" + esc(flash) + "</span>" : "") + "</div>";
  $("bSave").textContent = j.revealed_at ? ((CIRC && hasCircle(ev.id) && !j.circle_verdict) ? "Answer the circle question (7 / 8 / 9)" : "Saved — next event (Enter)") : "Save verdict & reveal (Enter)";
  document.querySelectorAll("input[name=ans]").forEach(el => el.onchange = () => { setAnswer(ev.id, el.value); after(); });
  document.querySelectorAll("input[name=reason]").forEach(el => el.onclick = () => { setReason(ev.id, el.value); after(); });
  $("fNote").oninput = () => { setNote(ev.id, $("fNote").value); saveState(); renderList(); };
  if (CIRC) {
    document.querySelectorAll("input[name=circ]").forEach(el => el.onchange = () => { setCircle(ev.id, el.value); after(); });
    if ($("fMap")) $("fMap").onchange = () => { setMapFlag(ev.id, $("fMap").checked); after(); };
  }
}
function after(){ saveState(); renderForm(); renderList(); }
function renderCirc(){
  const box = $("circbox");
  if (!CIRC) { box.hidden = true; return; }
  const ev = EV[cur], c = ev.circles, open = isRevealed(ev.id);
  box.hidden = false;
  let h = "<b>Circles</b> <span class='mut'>" + esc(open ? CIRC.legend_reveal : CIRC.legend_blind) + "</span>";
  if (c) h += "<br>" + c.cams.map(k => "<b>" + esc(k.cam) + "</b>: " + esc(open ? k.text_reveal : k.text_blind)).join("<br>");
  if (open && c && !c.reveal_ok) h += "<br><span class='warnline'>the reveal clip is missing — the blind clip is shown</span>";
  h += "<br><span class='warnline'>" + esc(CIRC.caveat) + "</span>";
  box.innerHTML = h;
}
function renderReveal(){
  const ev = EV[cur], open = isRevealed(ev.id);
  renderCirc();
  $("locked").hidden = open; $("revealBody").hidden = !open;
  if (!open) { $("panelImg").removeAttribute("src"); $("facts").innerHTML = ""; return; }
  $("panelImg").src = "panels/" + ev.panel.file;
  $("revealNote").innerHTML = "Dots = raw WISER fixes, line = V3 production track (distance from P0), the IMU state per second and the head turn; shaded = EVENT bar. " +
    "WISER frame inches, unverified origin; raw fixes jitter ~4–7 in.";
  $("facts").innerHTML = ev.reveal.facts.map(r => "<tr><th>" + esc(r[0]) + "</th><td>" + esc(r[1]) + "</td></tr>").join("");
}
function doSave(){
  const ev = EV[cur];
  if (isRevealed(ev.id)) {
    if (CIRC && hasCircle(ev.id) && !jget(ev.id).circle_verdict) { flash = "Answer the circle question first (7 / 8 / 9) — or press n to move on without it."; renderForm(); return; }
    select(cur + 1); return;
  }
  const r = saveVerdict(ev.id);
  flash = r.ok ? "" : r.msg;
  if (r.ok && CIRC) loadVideo(ev, vid.currentTime || 0);
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
  else if (CIRC && k >= "7" && k <= "9") { if (setCircle(ev.id, CIRC.question.options[+k - 7][0])) { flash = ""; after(); } }
  else if (CIRC && k === "m") { if (setMapFlag(ev.id, !jget(ev.id).map_flag)) after(); }
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
  const keys = [["Space", "play / pause"], ["← / →", "one frame (1/" + EV[0].clip.fps + " s); Shift = 1 s"], ["[ / ] / \\", "slower / faster / 1×"], ["j", "jump to the EVENT start"],
      ["↑ / ↓ or p / n", "previous / next event"], ["1 2 3", "answer (the three options of the question)"], ["4 5 6", "why you cannot tell (only with 'cannot tell')"],
      ["Enter", "save the verdict and reveal the panel; Enter again = next event"], ["? / Esc", "this help"]];
  if (CIRC) {
    keys.splice(7, 0, ["7 8 9", "after the reveal: the WISER circle is on the rat / drifts off the rat / cannot tell"], ["m", "start circle off (the dashed circle is not on the rat at the onset)"]);
    $("ttl").textContent = "WISER event review (blind, WISER circles) · cohort " + DATA.cohort;
    const o = document.createElement("option"); o.value = "revealed"; o.textContent = "saved, circle question open"; $("fStatus").appendChild(o);
  }
  $("helpcard").innerHTML = "<h3 style='margin-top:0'>How to review</h3><p>" + DATA.help.map(esc).join("</p><p>") + "</p>" +
    "<h4>Keyboard</h4><table>" + keys.map(r => "<tr><td><span class='kbd'>" + esc(r[0]) + "</span></td><td>" + esc(r[1]) + "</td></tr>").join("") + "</table>" +
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


def circles_page_info(circ: "CircleCtx") -> dict:
    return {"plan": PLAN_V2, "map_run": circ.map_run, "map_text": circ.desc["text"], "caveat": MAP_CAVEAT, "question": CIRCLE_QUESTION,
            "legend_blind": LEGEND_BLIND, "legend_reveal": LEGEND_REVEAL, "radius_in": CIRCLE_R_IN, "z_mm": Z_MM,
            "step_s": DYN_STEP_S}


def page_payload(cohort: str, run_dir: Path, events: list, ids: pd.DataFrame, sel_info: dict, audit_run: str,
                 circles: dict | None = None) -> dict:
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
    out = {"cohort": cohort, "run_id": run_dir.name, "run_dir": str(run_dir), "tool": TOOL, "plan": PLAN, "audit_run": audit_run,
           "generated": time.strftime("%Y-%m-%d %H:%M"), "selection": sel_info, "reasons": REASONS,
           "identity": identity_rows(ids), "help": help_, "events": events}
    if circles is not None:
        help_[0] = help_[0].replace("nothing the tracker or the IMU computed.",
                                    "nothing the tracker or the IMU computed — except the dashed start circle (below).")
        help_[1:1] = [
            "Circles (GUI v2). Before your first answer each clip shows only a dashed white circle labelled 'start': 14 in around the rat's position "
            "before the EVENT (the reference WISER position), projected into each camera. It helps you find the right rat; it does not show where "
            "WISER went. After you save the first verdict the clip is replaced by a version with the moving WISER circle (solid yellow, V3 track, "
            "every 0.25 s), the raw WISER fix (red dot) and the start circle, and a second question opens: does the WISER circle stay on the rat? "
            "(7 on the rat / 8 drifts off the rat / 9 cannot tell; saved as circle_verdict). Your first answer stays the blind verdict.",
            "No projection: CH05 (house_1 relocated on 09-18), the in-box CH07 / CH08 and ground outside a camera's mapped area get no circle — the clip "
            "says 'no projection — use the IR mark'; the other camera may still have one. Day frames use the nearest night camera correction "
            "(flagged in the clip): their circles can be tens of pixels off.",
            circles["caveat"],
        ]
        out.update({"circles": circles, "help": help_})
    return out


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
def coverage_text(r: dict) -> str:
    if not r["projectable"]:
        return f"{r['camera']} no projection ({r['no_projection_reason']})"
    st = "yes" if r["start_circle"] else f"no ({r['start_status']})"
    return (f"{r['camera']} start {st}, moving {r['steps_circle']}/{r['steps']} steps (located {r['steps_located']}), conv "
            f"{r['convergence_rate']}, rt max {r['rt_max_px']} px, flag {r['correction_flag']}" + (", DAY" if r["day_frame"] else ""))


def write_tables(out: Path, evs: list) -> None:
    circ = bool(evs) and all("circles" in p for p in evs)
    with open(out / "event_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "type", "animal", "event_key", "selection", "selection_rank", "size_quartile", "onset_local", "end_local",
                    "onset_al_ms", "end_al_ms", "zone", "cameras", "clip", "clip_ok", "clip_s", "clip_mb", "event_s", "truncated", "missing_reason",
                    "cam_notes", "panel", "panel_ok"]
                   + (["reveal_clip", "reveal_ok", "reveal_mb", "start_circle_any_camera", "moving_circle_any_camera", "no_circle_reason"] if circ else []))
        for p in evs:
            c = p["clip"]
            row = [p["id"], p["type"], p["animal"], p["event_key"], p["selection"], p["selection_rank"], p["size_quartile"], p["onset_local"],
                   p["end_local"], p["onset_al_ms"], p["end_al_ms"], p["zone"], p["cams_text"], c["file"], c["ok"], c.get("duration_probe_s"),
                   round((c.get("size_bytes") or 0) / 1e6, 1), c["event_s"], c["truncated"], c["missing_reason"], "; ".join(p["cam_notes"]),
                   p["panel"]["file"], p["panel"]["ok"]]
            if circ:
                q = p["circles"]
                row += [q["reveal_file"], q["reveal_ok"], round((q.get("reveal_size_bytes") or 0) / 1e6, 1), q["any_start"], q["any_moving"],
                        q["no_circle_reason"]]
            w.writerow(row)


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


CAM_TYPE = {"CH01": "panorama", "CH02": "panorama", "CH05": "top-down", "CH06": "top-down", "CH07": "in-box", "CH08": "in-box"}


def circle_summary(evs: list, cov: pd.DataFrame) -> dict:
    """Coverage numbers for the README / log / change log."""
    s = {"n_events": len(evs), "any_circle": [p["id"] for p in evs if p["circles"]["any_start"] or p["circles"]["any_moving"]],
         "no_circle": [(p["id"], p["zone"], p["cams_text"], p["circles"]["no_circle_reason"]) for p in evs
                       if not (p["circles"]["any_start"] or p["circles"]["any_moving"])]}
    rows = []
    if len(cov):
        cov = cov.assign(cam_type=cov["camera"].map(CAM_TYPE).fillna("other"))
        for t, g in cov.groupby("cam_type", sort=False):
            pj = g[g["projectable"].astype(bool)]
            rows.append({"camera type": t, "event-cameras": len(g), "projectable": len(pj),
                         "with start circle": int(g["start_circle"].astype(bool).sum()),
                         "with any moving circle": int((g["steps_circle"] > 0).sum()),
                         "median share of steps with a circle (projectable)": round(float(pj["share_circle"].median()), 3) if len(pj) else None,
                         "median share of located steps with a circle": round(float(pj["share_circle_of_located"].median()), 3) if len(pj) else None,
                         "events with a circle on this type": int((g["start_circle"].astype(bool) | (g["steps_circle"] > 0))
                                                                  .groupby(g["review_id"]).any().sum())})
        pj = cov[cov["projectable"].astype(bool)]
        s["rt"] = {"n_event_cameras": int(len(pj)), "points": int(pj["rt_n"].fillna(0).sum()),
                   "max_px": float(pj["rt_max_px"].max()) if len(pj) else None,
                   "p99_max_px": float(pj["rt_p99_px"].max()) if len(pj) else None,
                   "med_med_px": float(pj["rt_med_px"].median()) if len(pj) else None,
                   "min_converged_share": float(pj["rt_converged_share"].min()) if len(pj) else None,
                   "min_le1_share": float(pj["rt_le1_share"].min()) if len(pj) else None,
                   "gt1_n": int(pj["rt_gt1_n"].fillna(0).sum()), "gt1_seam_n": int(pj["rt_gt1_seam_n"].fillna(0).sum()),
                   "max_px_off_seam": float(pj["rt_max_px_off_seam"].max()) if len(pj) else None,
                   "event_cameras_all_le1": int((pj["rt_max_px"] <= 1.0).sum())}
        s["conv"] = {"min": float(pj["convergence_rate"].min()) if len(pj) else None,
                     "median": float(pj["convergence_rate"].median()) if len(pj) else None,
                     "targets": int(pj["targets_in_support"].sum()), "converged": int(pj["targets_converged"].sum()),
                     "inverse_err_max_in": float(pj["inverse_err_max_in"].max()) if len(pj) else None}
        s["day_event_cameras"] = int(cov["day_frame"].astype(bool).sum())
        s["flagged_event_cameras"] = int(((cov["correction_flag"] != "ok") & cov["projectable"].astype(bool)).sum())
    s["by_type"] = rows
    return s


def write_circle_readme(out: Path, evs: list, cov: pd.DataFrame, circ: "CircleCtx", summ: dict) -> None:
    """Append the GUI v2 section to the run README."""
    rt, cv = summ.get("rt", {}), summ.get("conv", {})
    n_rev = sum(1 for p in evs if p["circles"]["reveal_ok"])
    L = ["", "## Circles (GUI v2, `--circles`)", "",
         f"Plan `{PLAN_V2}` (+ amendments). Same 80 events, W ids and order as GUI v1. `clips/` = the blind clip **with the static "
         "dashed start circle**; `clips_reveal/` = the clip shown after the first answer, with the moving WISER circle (V3, solid yellow), "
         f"the raw fix (red dot) and the start circle ({n_rev} of {len(evs)} reveal clips rendered). Second question: "
         f"\"{CIRCLE_QUESTION['text']}\" → `circle_verdict`; tick \"start circle off\" → `map_flag`.", "",
         f"**{MAP_CAVEAT}**", "",
         f"Map: {circ.desc['text']} (run `{circ.map_run}`). Pixels: Newton inverse of `Corrections(\"2026c\").to_paddock(cam, t, uv, "
         f"z_mm={Z_MM:g})` (wiser_assist_p0.invert_mapper, round trip ≤ 1 in), started at the nearest mapped 40-px grid centre; ring = "
         f"{RING_N} paddock points {CIRCLE_R_IN:g} in from the centre, each inverted; one position per 0.25-s overlay step (V3 at the step "
         f"centre, linear between rows ≤ {GAP_MAX_S:g} s apart; raw dot = nearest unmasked raw fix within ± {RAW_WIN_S:g} s); WISER on the "
         "aligned clock t_al = t_WISER − τ*. Day frames (> 30 min outside the night's sampled corrections) use the nearest night sample "
         "and are flagged in the clip; flagged corrections (`night`, `sample`) are drawn and named in the clip.", "",
         "### Projection coverage", "",
         f"Events with a circle on at least one camera: **{len(summ['any_circle'])} / {summ['n_events']}**. "
         f"Per event and camera: `projection_coverage.csv`.", "",
         "| camera type | event-cameras | projectable | with start circle | with any moving circle | median share of steps with a circle | median share of located steps | events with a circle on this type |",
         "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in summ["by_type"]:
        L.append(f"| {r['camera type']} | {r['event-cameras']} | {r['projectable']} | {r['with start circle']} | {r['with any moving circle']} | "
                 f"{r['median share of steps with a circle (projectable)']} | {r['median share of located steps with a circle']} | "
                 f"{r['events with a circle on this type']} |")
    L += ["", "Events without any circle:", ""]
    L += [f"- {i} ({z}, {c}): {w}" for i, z, c, w in summ["no_circle"]] or ["- none"]
    L += ["", "### Checks", "",
          f"- Round trip pixel → paddock → pixel on a {RT_STEP_PX}-px grid (offset {RT_OFF_PX}) per projected event-camera at the onset: "
          f"{rt.get('n_event_cameras')} event-cameras, {rt.get('points')} points; median of medians {rt.get('med_med_px')} px, worst p99 "
          f"{rt.get('p99_max_px')} px, max {rt.get('max_px')} px; event-cameras with every point ≤ 1 px: {rt.get('event_cameras_all_le1')}; "
          f"points > 1 px: {rt.get('gt1_n')} (in the pano seam band ± {SEAM_BAND_PX:g} px: {rt.get('gt1_seam_n')}); max outside the seam band "
          f"{rt.get('max_px_off_seam')} px; lowest converged share {rt.get('min_converged_share')}.",
          f"- Inverse convergence (targets inside a camera's mapped ground): {cv.get('converged')} / {cv.get('targets')}; per clip-camera median "
          f"{cv.get('median')}, lowest {cv.get('min')}; largest round-trip error of a drawn point {cv.get('inverse_err_max_in')} in.",
          f"- Day-frame event-cameras (nearest night correction): {summ.get('day_event_cameras')}; projectable event-cameras with a non-ok "
          f"correction flag: {summ.get('flagged_event_cameras')}."]
    if circ.size_notes:
        L += [f"- Camera size mismatches: {sorted(set(circ.size_notes))}"]
    with open(out / "README.md", "a", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


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
    subs = ("clips", "panels", "overlay_ass", "_fonts") + (("clips_reveal", "overlay_ass_reveal") if args.circles else ())
    for sub in subs:
        (out / sub).mkdir(parents=True, exist_ok=True)
    fh = open(out / "log.txt", "a", encoding="utf-8")
    log(f"{NAME}: out {out}; audit {audit}; root {args.root}; git {MV.git_commit()}" + (f"; CIRCLES (GUI v2), map run {args.map_run}" if args.circles else ""), fh)
    circ = None
    if args.circles:
        circ = load_circle_ctx(args.map_run, cohort)
        log(f"circles: {circ.desc['text']}; z {Z_MM:g} mm; ring {RING_N} points x {CIRCLE_R_IN:g} in; step {DYN_STEP_S} s", fh)
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
        pl, job = build_event(ev, sel_info, houses, ids, Path(args.root), ffprobe, out, fonts, cache, audit_run=str(audit), circ=circ)
        payloads.append(pl)
        jobs[pl["id"]] = job
        if circ is not None:
            log("    circles: " + "; ".join(coverage_text(r) for r in job["coverage"]), fh)
        log(f"  {pl['id']} {pl['type']} {pl['animal']} {pl['onset_local']} ({pl['selection']}): {pl['zone_label']} -> {pl['cams_text']}; "
            f"clip {pl['clip']['dur_s']:.0f} s, EVENT {pl['clip']['ev_t0_s']:.0f}-{pl['clip']['ev_t1_s']:.0f} s; parts "
            f"{[len(c['parts']) for c in pl['cams']]}, gaps {[c['gaps'] for c in pl['cams']]}; panel fixes {pl['panel'].get('summary', {}).get('n_fix')}"
            + (f"; MISSING: {pl['clip']['missing_reason']}" if pl["clip"]["missing_reason"] else ""), fh)
    results = {}
    if not args.no_clips:
        todo = [p["id"] for p in payloads if jobs[p["id"]]["has_video"]]
        log(f"rendering {len(todo)} clips with {args.workers} workers ...", fh)
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futs = {i: ex.submit(render_pair if circ is not None else MV.render, ffmpeg, ffprobe, jobs[i], out, enc) for i in todo}
            for i in todo:
                r = futs[i].result()
                results[i] = r
                if r["ok"]:
                    rv = r.get("reveal", {})
                    log(f"  clip {Path(jobs[i]['out']).name}: {r.get('width')}x{r.get('height')} {r.get('duration_s', 0):.1f} s "
                        f"{r.get('size_bytes', 0) / 1e6:.1f} MB {r['encoder']} in {r['seconds']} s"
                        + (f"; reveal {rv.get('duration_s', 0):.1f} s {rv.get('size_bytes', 0) / 1e6:.1f} MB" if circ is not None else "")
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
        if circ is not None:
            rv = (r or {}).get("reveal", {})
            p["circles"]["reveal_ok"] = bool(rv.get("ok")) if r is not None else bool(
                args.no_clips and jobs[p["id"]]["has_video"] and (out / "clips_reveal" / p["circles"]["reveal_file"]).exists())
            p["circles"].update({"reveal_size_bytes": rv.get("size_bytes"), "reveal_duration_probe_s": rv.get("duration_s")})
    payloads.sort(key=lambda p: p["idx"])
    page = page_payload(cohort, out, payloads, ids, sel_info, str(audit), circles=circles_page_info(circ) if circ is not None else None)
    (out / "events.json").write_text(json.dumps(page, ensure_ascii=False, indent=1), encoding="utf-8")
    html = write_html(out, page)
    ok_js, msg = check_js(html)
    log(f"index.html {html.stat().st_size / 1e6:.2f} MB; node --check {'OK' if ok_js else 'FAILED ' + msg}", fh)
    write_tables(out, payloads)
    write_readme(out, cohort, payloads, sel_info, enc, str(audit), time.time() - t_start)
    n_ok = sum(1 for p in payloads if p["clip"]["ok"])
    miss = [f"{p['id']} {p['event_key']}: {p['clip']['missing_reason']}" for p in payloads if not p["clip"]["ok"]]
    n_rev = len(payloads)
    if circ is not None:
        cov = pd.DataFrame([r for p in payloads for r in jobs[p["id"]]["coverage"]], columns=COVERAGE_COLS)
        cov.to_csv(out / "projection_coverage.csv", index=False)
        summ = circle_summary(payloads, cov)
        (out / "circles_summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf-8")
        write_circle_readme(out, payloads, cov, circ, summ)
        n_rev = sum(1 for p in payloads if p["circles"]["reveal_ok"])
        log(f"circles: events with a circle {len(summ['any_circle'])}/{summ['n_events']}; by camera type {summ['by_type']}; "
            f"round trip {summ.get('rt')}; convergence {summ.get('conv')}; no circle {summ['no_circle']}; reveal clips {n_rev}/{len(payloads)}"
            + (f"; SIZE MISMATCH {sorted(set(circ.size_notes))}" if circ.size_notes else ""), fh)
    log(f"done: {n_ok}/{len(payloads)} clips, panels {sum(1 for p in payloads if p['panel']['ok'])}; missing {miss}; "
        f"wall {(time.time() - t_start) / 60:.1f} min -> {out}", fh)
    fh.close()
    return 0 if ok_js and (args.no_clips or (n_ok == len(payloads) and n_rev == len(payloads))) else 1


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
            check("GUI v1 page (no --circles): export columns unchanged (no circle fields)",
                  not ({"circle_verdict", "map_flag", "circle_available"} & set(row1)) and "circles" not in O and "gui" not in O)
    ok_all &= selftest_circles(check, ids, taus)
    print("PASS - make_wiser_event_review self-test" if ok_all else "FAIL - make_wiser_event_review self-test")
    return 0 if ok_all else 1


def _syn_mapper(W: int, H: int, x0: float, y0: float, sx: float, sy: float, k: float = 4e-4):
    """Synthetic camera: upright px -> paddock in, mildly nonlinear, NaN outside the frame / the 480 x 240 paddock."""
    def mapper(t, uv):
        uv = np.asarray(uv, float).reshape(-1, 2)
        du, dv = uv[:, 0] - W / 2.0, uv[:, 1] - H / 2.0
        p = np.column_stack([x0 + sx * (uv[:, 0] + k * du * dv), y0 + sy * uv[:, 1] + 2e-4 * du * du])
        bad = ~((uv[:, 0] >= -0.5) & (uv[:, 0] < W - 0.5) & (uv[:, 1] >= -0.5) & (uv[:, 1] < H - 0.5))
        bad |= ~((p[:, 0] >= 0) & (p[:, 0] <= 480) & (p[:, 1] >= 0) & (p[:, 1] <= 240))
        p[bad] = np.nan
        return p, {"flag": "ok", "target_frame": "09-18 (calibration)", "used": ["2026-09-05 01:00:00", "2026-09-05 02:00:00"]}
    return mapper


def selftest_circles(check, ids: pd.DataFrame, taus: dict) -> bool:
    """GUI v2: synthetic camera model + map -> circle placement, the static / moving split between the phases, the export
    fields and the no-projection branch; one synthetic render checked numerically (luma at known positions, never viewed)."""
    ok0 = True

    def chk(name, cond, info=""):
        nonlocal ok0
        ok0 &= bool(cond)
        check("circles: " + name, cond, info)

    P0, _ = import_p0()
    W, H = 640, 200                                         # synthetic pano, upright (stored 200 x 640, rotated); multiples of p0's 40-px grid
    syn = _syn_mapper(W, H, 100.0, 40.0, 0.5, 0.9)
    refuse = lambda t, uv: (None, {"flag": "ok+not calibrated (target 09-04 12:00 (user-labelled frame))"})  # noqa: E731
    m = P0.Map(-270.0, -600.0, np.radians(0.2), 0.97, 500.0, 760.0)
    circ = CircleCtx(P0, m, 0.0, {"SYNA": syn, "SYNB": refuse}, {"SYNA": (W, H), "SYNB": (W, H)}, {"text": "synthetic map"}, "synthetic")
    t0 = int(pd.Timestamp("2026-09-05 01:30:00").tz_localize(TZ).value // 10**6)
    # ---- projector: inverse of known pixels, ring radius, round trip
    pr = circ.projector("SYNA", t0, (W, H))
    uv_true = np.array([[50.3, 20.7], [320.0, 90.0], [611.2, 170.4], [400.9, 3.1]])
    Pt, _ = syn(None, uv_true)
    uvh, st, err = pr.project(np.full(4, t0), Pt[:, None, :])
    chk("Newton inverse recovers known pixels (< 0.05 px)", (st == "ok").all() and np.nanmax(np.hypot(*(uvh[:, 0] - uv_true).T)) < 0.05,
        f"{np.round(uvh[:, 0], 3).tolist()}")
    phi = np.linspace(0.0, 2.0 * np.pi, RING_N, endpoint=False)
    ring = CIRCLE_R_IN * np.column_stack([np.cos(phi), np.sin(phi)])
    c = np.array([250.0, 110.0])
    uvr, str_, _ = pr.project(np.full(1, t0), (c + ring)[None])
    back, _ = syn(None, uvr[0])
    chk("ring pixels map back to paddock points 14 in from the centre (each ring point inverted)",
        (str_ == "ok").all() and np.allclose(np.hypot(*(back - c).T), CIRCLE_R_IN, atol=0.05), f"{np.round(np.hypot(*(back - c).T)[:4], 3)}")
    rt = pr.roundtrip(t0, step=40, off=(7.0, 5.0))
    chk("round trip pixel -> paddock -> pixel <= 1 px on a grid, all converged", rt["rt_n"] > 30 and rt["rt_max_px"] <= 1.0
        and rt["rt_converged_share"] == 1.0, str(rt))
    chk("refused camera = not projectable, reason kept", not circ.projector("SYNB", t0, (W, H)).ok
        and "to_paddock refuses" in circ.projector("SYNB", t0, (W, H)).reason)
    dfl, used = day_frame({"used": ["2026-09-05 04:20:00"]}, datetime(2026, 9, 5, 10, 5))
    dfn, _ = day_frame({"used": ["2026-09-05 04:20:00"]}, datetime(2026, 9, 5, 4, 40))
    chk("day frame = > 30 min from the single nearest night sample", dfl and used == "04:20" and not dfn)
    # ---- synthetic event: start (200, 100) -> (300, 100) during the EVENT -> out of view (y 230) -> WISER gap
    cw = clip_window(t0, t0 + 10_000)                       # clip t0 - 10 s .. t0 + 20 s, D = 30 s
    lo = cw["lo_ms"]

    def pad_at(s):
        if s < 10:
            return (200.0, 100.0)
        if s < 18:
            return (200.0 + 100.0 * (s - 10) / 8.0, 100.0)
        if s < 21:
            return (300.0, 100.0)
        if s < 23:
            return (300.0, 100.0 + 130.0 * (s - 21) / 2.0)
        return (300.0, 230.0)
    ss = np.arange(-6.0, 24.0 + 1e-9, 0.25)                 # no WISER rows after 24 s (gap -> 'not located')
    Pp = np.array([pad_at(s) for s in ss])
    Wp = m.inv(Pp)
    rng = np.random.default_rng(5)
    F = pd.DataFrame({"t_al": lo + np.round(ss * 1000.0), "x": Wp[:, 0], "y": Wp[:, 1], "x_raw": Wp[:, 0] + rng.normal(0, 0.7, len(ss)),
                      "y_raw": Wp[:, 1] + rng.normal(0, 0.7, len(ss)), "imu_state": 1, "anchors_used": 8})
    w0 = m.inv(np.array([[200.0, 100.0]]))[0]
    ev = {"review_id": "W01", "type": "I1", "animal": "SF07", "t0": t0 / 1000.0, "ref_x": w0[0], "ref_y": w0[1]}
    lay = MV.layout("outside", scale=0.25)
    cams = [("SYNA", "panorama (upright)"), ("SYNB", "panorama (upright)")]
    views = event_circles(ev, cw, F, cams, lay, circ, [(W, H), (W, H)])
    va, vb = views
    p_start, _ = syn(None, np.atleast_2d(np.r_[(va["start_centre"][0] - lay["views"][0]["x"]) * W / lay["views"][0]["w"] - 0.5,
                                                (va["start_centre"][1] - lay["views"][0]["y"]) * H / lay["views"][0]["h"] - 0.5]))
    chk("start circle: centre maps back to the start position (map + camera inverse)", va["start_ok"] and np.allclose(p_start[0], [200.0, 100.0], atol=0.05),
        f"{p_start}")
    stc = np.asarray(va["st_centre"], dtype=object)
    s_mid = (np.arange(va["nb"]) + 0.5) * DYN_STEP_S
    exp = np.array(["ok" if s < 22.2 else ("not located" if s > 24.0 else "x") for s in s_mid], dtype=object)
    k_ok, k_nl = exp == "ok", exp == "not located"
    chk("moving circle: drawn while located and in view, 'out of view' past the frame edge, 'not located' in the WISER gap",
        (stc[k_ok] == "ok").all() and (stc[k_nl] == "not located").all() and np.any(stc == "out of view"),
        f"{dict(zip(*np.unique(stc.astype(str), return_counts=True)))}")
    back_c, _ = syn(None, va["centre_px"][k_ok])
    expP = np.array([pad_at(s) for s in s_mid[k_ok]])
    chk("moving circle: centre at the track's paddock position at the step centre (< 0.1 in)",
        np.nanmax(np.hypot(*(back_c - expP).T)) < 0.1, f"{np.nanmax(np.hypot(*(back_c - expP).T)):.4f}")
    chk("no-projection camera: no circle, every step 'no projection'", not vb["projectable"] and not vb["start_ok"]
        and all(s in ("no projection", "not located") for s in vb["st_centre"]))
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        for sub in ("overlay_ass", "overlay_ass_reveal", "clips", "clips_reveal", "_fonts"):
            (out / sub).mkdir()
        fonts = MV.find_fonts()
        for f in fonts.values():
            shutil.copy2(f, out / "_fonts" / f.name)
        ident = identity(ids, "SF07", t0)
        rows = overlay_rows("W01", "SF07", ident, "outside", "SYNA + SYNB panoramas", cw)
        lo_dt = MV.ms_to_dt(lo)
        sod = lo_dt.hour * 3600 + lo_dt.minute * 60 + lo_dt.second
        write_ass_blind(out / "overlay_ass" / "e.ass", lay, rows, cw["dur_s"], (cw["ev_t0_s"], cw["ev_t1_s"]), ["SYNA · pano", "SYNB · pano"],
                        [[], []], sod, fonts)
        Tc = write_circle_overlays(out / "overlay_ass" / "e.ass", out / "overlay_ass_reveal" / "e.ass", lay, views, cw["dur_s"], fonts)
        tb = (out / "overlay_ass" / "e.ass").read_text(encoding="utf-8")
        trv = (out / "overlay_ass_reveal" / "e.ass").read_text(encoding="utf-8")
        trk, rawc = MV.ass_c(CIRC_COL["track"]), MV.ass_c(CIRC_COL["raw"])
        chk("blind overlay: one static start circle (whole clip, dashed), no moving circle, no raw dot",
            len(Tc["blind_start"]) == 1 and Tc["blind_start"][0][1:3] == (0.0, cw["dur_s"]) and trk not in tb and rawc not in tb
            and sum("\\p3" in x for x in tb.splitlines()) == 1, f"{Tc['blind_start']}")
        dash = re.search(r"\\p3[^}]*\}(.*?)\{\\p0\}", tb).group(1).count("m ")
        chk("blind start circle is dashed (every other ring segment)", dash == RING_N // 2, f"{dash} subpaths")
        n_ok = int(np.sum(stc == "ok"))
        chk("reveal overlay: start circle + one moving circle per drawn step + raw dots",
            len(Tc["reveal_start"]) == 1 and len(Tc["reveal_moving"]) == n_ok and len(Tc["reveal_raw"]) > 0 and trk in trv and rawc in trv,
            f"moving {len(Tc['reveal_moving'])} / ok steps {n_ok}, raw {len(Tc['reveal_raw'])}")
        chk("moving circles tile time in 0.25-s steps", all(abs((b - a) - DYN_STEP_S) < 1e-9 or abs(b - cw["dur_s"]) < 1e-9 for _, a, b, _ in Tc["reveal_moving"]))
        chk("circles only on the projectable view", all(t[0] == 0 for k in ("blind_start", "reveal_start", "reveal_moving", "reveal_raw") for t in Tc[k]))
        chk("no-projection note on the other view in both phases",
            any(vi == 1 and NOTE_NOPROJ in txt for vi, _, _, txt in Tc["notes"]["blind"]) and any(vi == 1 and NOTE_NOPROJ in txt for vi, _, _, txt in Tc["notes"]["reveal"]))
        chk("reveal: dynamic notes for 'out of view' and the WISER gap", any("outside this camera" in t[3] for t in Tc["dyn"])
            and any("no fix" in t[3] for t in Tc["dyn"]), str([t[3] for t in Tc["dyn"]]))
        body = "\n".join(x for x in tb.splitlines() if x.startswith("Dialogue"))
        leaks = [w_ for w_ in FORBIDDEN_OVERLAY if w_ in body]
        chk("blind overlay with the start circle stays blind (no WISER / answer words)", not leaks, f"leaks {leaks}")
        pl = circles_payload(views, "e.mp4")
        none = circles_payload([dict(vb, cam="SYNB"), dict(vb, cam="SYNC")], "n.mp4")
        chk("payload: start + moving circle flags; an event with no projection on either camera -> no circle + reason",
            pl["any_start"] and pl["any_moving"] and not none["any_start"] and not none["any_moving"] and "to_paddock refuses" in none["no_circle_reason"])
        # ---- one decode, two outputs; luma checks at computed positions (synthetic frames, never viewed)
        ffmpeg, ffprobe = GF.find_ffmpeg()
        src = out / "syn_pano.mp4"
        subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={H}x{W}:r=20:d={cw['dur_s']}",
                        "-vf", "drawbox=x=40:y=500:w=6:h=6:color=white:t=fill", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
        parts = [{"path": str(src), "offset_s": 0.0, "dur_s": cw["dur_s"], "clip_t0_s": 0.0}]
        job = {"id": "e", "out": str(out / "clips" / "e.mp4"), "out_reveal": str(out / "clips_reveal" / "e.mp4"), "layout": lay,
               "view_parts": [parts, []], "D": cw["dur_s"], "ass_rel": "overlay_ass/e.ass", "ass_reveal_rel": "overlay_ass_reveal/e.ass",
               "fonts_rel": "_fonts"}
        enc = "nvenc" if MV.nvenc_works(ffmpeg) else "x264"
        r = render_pair(ffmpeg, ffprobe, job, out, enc)
        chk(f"render_pair ({r.get('encoder')}): blind + reveal clips, H.264, same size and duration",
            r["ok"] and r["reveal"]["ok"] and r.get("codec") == "h264" and r["reveal"].get("codec") == "h264" and r.get("width") == lay["W"]
            and r["reveal"].get("width") == lay["W"] and abs(r["reveal"]["duration_s"] - cw["dur_s"]) <= 0.06, r.get("error", "")[-300:])
        if r["ok"]:
            def frames(path):
                p = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
                return np.frombuffer(p.stdout, np.uint8).reshape(-1, lay["H"], lay["W"])
            fb, fr_ = frames(job["out"]), frames(job["out_reveal"])
            v0 = lay["views"][0]
            ex = to_view(np.array([502.5, H - 43.5]), v0, (W, H)) - 0.5      # the box's centre (stored x 40-45, y 500-505 -> upright)
            win = fb[100, int(ex[1]) - 12:int(ex[1]) + 13, int(ex[0]) - 12:int(ex[0]) + 13].astype(float)
            yy, xx = np.nonzero(win > 200)
            cen = (xx.mean() + int(ex[0]) - 12, yy.mean() + int(ex[1]) - 12) if len(xx) else (np.nan, np.nan)
            chk("pano upright px -> clip px: a source marker lands where to_view predicts (< 1 px)",
                len(xx) > 4 and math.hypot(cen[0] - ex[0], cen[1] - ex[1]) < 1.0, f"measured {np.round(cen, 2)}, expected {np.round(ex, 2)}")

            def lit(fr, pts, thr):
                """share of points whose 3 x 3 neighbourhood max luma exceeds thr (background ~126)"""
                pts = np.asarray(pts, float)
                pts = pts[np.isfinite(pts).all(1)]
                vals = [fr[max(0, int(y) - 1):int(y) + 2, max(0, int(x) - 1):int(x) + 2].max() for x, y in pts
                        if 1 <= x < lay["W"] - 1 and 1 <= y < lay["H"] - 1]
                return float(np.mean(np.asarray(vals) > thr)) if vals else 0.0
            rs = va["start_ring"]
            mids = np.array([(rs[i] + rs[(i + 1) % RING_N]) / 2 for i in range(0, RING_N, 2)])
            chk("blind clip: the dashed start circle is drawn at its computed pixels (white)", lit(fb[30], mids, 175) >= 0.8, f"{lit(fb[30], mids, 175):.2f}")
            k = int(np.flatnonzero(np.isclose(s_mid, 19.125))[0])           # rat at (300, 100), 100 in from the start
            fi = int(round(s_mid[k] * MV.FPS))
            rk = va["ring"][k]
            mk = np.array([(rk[i] + rk[(i + 1) % RING_N]) / 2 for i in range(RING_N)])
            chk("reveal clip: the moving circle is drawn at its computed pixels (yellow); the blind clip has nothing there",
                lit(fr_[fi], mk, 150) >= 0.8 and lit(fb[fi], mk, 150) <= 0.1, f"reveal {lit(fr_[fi], mk, 150):.2f}, blind {lit(fb[fi], mk, 150):.2f}")
    # ---- page: second question, map flag, no-circle branch, export fields (node)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        E2, L12, L22 = _synth_events()
        evs_s, info_s = select_events(E2, L12, L22, taus)
        pls = []
        for j_, e in enumerate(evs_s[:3]):
            cw_ = clip_window(int(e["t0"] * 1000), int(e["t1"] * 1000))
            circ_ev = {"reveal_file": f"r{j_}.mp4", "reveal_ok": True, "any_start": j_ != 1, "any_moving": j_ != 1, "no_circle_reason": "" if j_ != 1 else "x",
                       "cams": [{"cam": "CH01", "role": "pano", "projectable": j_ != 1, "reason": "", "flag": "ok", "day_frame": False, "day_used": "",
                                 "start": j_ != 1, "share": 0.8 if j_ != 1 else 0.0, "text_blind": "start circle", "text_reveal": "circle 80 %"}]}
            pls.append({"idx": e["review_idx"], "id": e["review_id"], "type": e["type"], "question": QUESTIONS[e["type"]], "animal": e["animal"],
                        "event_key": f"{e['animal']}|V3|{e['type']}|{int(e['event_id'])}", "audit_event_id": int(e["event_id"]),
                        "selection": e["selection"], "selection_rank": e["selection_rank"], "size_quartile": e["size_quartile"],
                        "onset_local": fmt_local(cw_["lo_ms"] + 10_000), "end_local": fmt_local(cw_["hi_ms"]), "onset_al_ms": cw_["lo_ms"] + 10_000,
                        "end_al_ms": cw_["hi_ms"], "tau_ms": 150.0, "identity": identity(ids, e["animal"], cw_["lo_ms"]), "zone": "outside",
                        "zone_label": "open field", "zone_why": "test", "cams_text": "CH01 + CH02 panoramas", "overlay_static": ["a", "b"],
                        "population_note": "", "cam_notes": [], "cams": [{"cam": "CH01", "role": "pano", "parts": [], "gaps": []}],
                        "clip": {"file": f"b{j_}.mp4", "ok": True, "missing_reason": "", "lo_local": "2026-09-05 01:59:54.000",
                                 "hi_local": "2026-09-05 02:00:20.000", "lo_ms": cw_["lo_ms"], "hi_ms": cw_["hi_ms"], "lo_sod": 7194.0,
                                 "dur_s": cw_["dur_s"], "ev_t0_s": cw_["ev_t0_s"], "ev_t1_s": cw_["ev_t1_s"], "truncated": cw_["truncated"],
                                 "continues_s": cw_["continues_s"], "event_s": cw_["event_s"], "fps": 20, "width": 960, "height": 414},
                        "panel": {"file": "a.png", "ok": True}, "reveal": {"facts": [["selection", "secret"]]}, "audit_run": "x", "circles": circ_ev})
        info_c = {"plan": PLAN_V2, "map_run": "x", "map_text": "synthetic", "caveat": MAP_CAVEAT, "question": CIRCLE_QUESTION,
                  "legend_blind": LEGEND_BLIND, "legend_reveal": LEGEND_REVEAL, "radius_in": CIRCLE_R_IN, "z_mm": Z_MM, "step_s": DYN_STEP_S}
        page = page_payload("2026c", out, pls, ids, info_s, "x", circles=info_c)
        html = write_html(out, page)
        okj, msg = check_js(html)
        chk("v2 page: both script blocks pass node --check", okj, msg)
        harness = script_blocks(html)[0] + r"""
;(function(){
  const a = EV[0].id, n = EV[1].id, c = EV[2].id, res = {};
  res.circBefore = setCircle(a, "on_rat");
  res.mapNoStart = setMapFlag(n, true);
  res.mapA = setMapFlag(a, true);
  setAnswer(a, EV[0].question.options[0][0]); saveVerdict(a);
  res.stRevealed = status(a);
  res.circBad = setCircle(a, "nonsense");
  res.circA = setCircle(a, "drifts_off");
  res.stDone = status(a);
  setAnswer(n, "cannot_tell"); saveVerdict(n);
  res.stN = status(n); res.cvN = circleVerdict(n); res.circN = setCircle(n, "on_rat");
  res.cvC = circleVerdict(c); res.stC = status(c);
  process.stdout.write(JSON.stringify({res: res, obj: exportObject(), csv: csvText()}));
})();
"""
        jsf = out / "harness.js"
        jsf.write_text(harness, encoding="utf-8")
        pr_ = subprocess.run([node_exe(), str(jsf)], capture_output=True, text=True, encoding="utf-8")
        try:
            got = json.loads(pr_.stdout)
        except Exception:  # noqa: BLE001
            got = None
        chk("v2 page logic runs in node", got is not None, (pr_.stderr or "")[-400:])
        if got is not None:
            R, O = got["res"], got["obj"]
            chk("second question only after the reveal; invalid answers refused; 'revealed' until it is answered",
                R["circBefore"] is False and R["stRevealed"] == "revealed" and R["circBad"] is False and R["circA"] is True and R["stDone"] == "done")
            chk("no-circle branch: no second question, circle_verdict = no_circle, map flag refused",
                R["mapNoStart"] is False and R["stN"] == "done" and R["cvN"] == "no_circle" and R["circN"] is False)
            r0, r1, r2 = O["rows"]
            chk("export: circle_verdict + map_flag (+ availability) per row; blind verdict unchanged",
                r0["circle_verdict"] == "drifts_off" and r0["map_flag"] is True and r0["circle_available"] is True and r0["verdict_blind"] == pls[0]["question"]["options"][0][0]
                and r1["circle_verdict"] == "no_circle" and r1["map_flag"] == "" and r1["start_circle_available"] is False
                and r2["circle_verdict"] == "" and r2["map_flag"] is False and R["stC"] == "todo" and O.get("gui", "").startswith("v2")
                and O["circles"]["caveat"] == MAP_CAVEAT, f"{r0.get('circle_verdict')} {r0.get('map_flag')} / {r1.get('circle_verdict')} {r1.get('map_flag')}")
            rows_csv = list(csv.DictReader(io.StringIO(got["csv"])))
            chk("export CSV carries circle_verdict and map_flag", len(rows_csv) == 3 and rows_csv[0]["circle_verdict"] == "drifts_off"
                and rows_csv[0]["map_flag"] == "true" and rows_csv[1]["circle_verdict"] == "no_circle")
        # ---- the page's UI script in node with a minimal DOM stub: keys -> clip switch, second question, blocked Enter
        ui = ui_flow(page, out)
        chk("UI flow: blind clip first; Enter after the answer switches to the reveal clip and opens the circle question",
            ui.get("src0") == "clips/b0.mp4" and ui.get("src1") == "clips_reveal/r0.mp4" and ui.get("circleOpen") is True
            and ui.get("caveat") is True, str(ui))
        chk("UI flow: Enter is held until the circle question is answered (8 = drifts off), then the next event loads its blind clip",
            ui.get("curBlocked") == 0 and ui.get("cv") == "drifts_off" and ui.get("cur2") == 1 and ui.get("src2") == "clips/b1.mp4", str(ui))
        chk("UI flow: no-circle event -> Enter goes straight on; 'm' ticks the map flag only where a start circle exists",
            ui.get("cur3") == 2 and ui.get("mapNoStart") is False and ui.get("mapStart") is True, str(ui))
        v1page = page_payload("2026c", out, [{k: v for k, v in p_.items() if k != "circles"} for p_ in pls], ids, info_s, "x")
        u1 = ui_flow(v1page, out)
        chk("UI flow, GUI v1 page: Enter reveals the panel but keeps the blind clip; no circle box", u1.get("src1") == "clips/b0.mp4"
            and u1.get("circHidden") is True and u1.get("cur2") == 1, str(u1))
    return ok0


UI_STUB = r"""
function El(id){ this.id = id; this.innerHTML = ""; this.textContent = ""; this.hidden = false; this.value = ""; this.style = {};
  this.children = []; this.listeners = {}; this.checked = false; this.src = ""; this.paused = true; this.currentTime = 0; this.duration = 30;
  this.playbackRate = 1; this.defaultPlaybackRate = 1; const s = new Set();
  this.classList = {add: c => s.add(c), remove: c => s.delete(c), contains: c => s.has(c)}; }
El.prototype.appendChild = function(c){ this.children.push(c); return c; };
El.prototype.addEventListener = function(n, f){ (this.listeners[n] = this.listeners[n] || []).push(f); };
El.prototype.removeAttribute = function(a){ if (a === "src") this.src = ""; };
["load", "scrollIntoView", "click", "remove"].forEach(m => { El.prototype[m] = function(){}; });
El.prototype.pause = function(){ this.paused = true; }; El.prototype.play = function(){ this.paused = false; };
El.prototype.getBoundingClientRect = function(){ return {left: 0, width: 100}; };
const __els = {}, __docL = {};
global.document = {getElementById: id => __els[id] || (__els[id] = new El(id)), createElement: t => new El(t), querySelectorAll: () => [],
  querySelector: () => null, body: new El("body"), addEventListener: (n, f) => { (__docL[n] = __docL[n] || []).push(f); }};
global.localStorage = {_d: {}, getItem(k){ return this._d[k] || null; }, setItem(k, v){ this._d[k] = String(v); }};
global.requestAnimationFrame = () => 0; global.alert = () => {}; global.Blob = function(){}; global.FileReader = function(){};
global.URL = {createObjectURL: () => "", revokeObjectURL: () => {}};
"""
UI_DRIVE = r"""
;(function(){
  function key(k){ (__docL.keydown || []).forEach(f => f({key: k, target: {tagName: "BODY"}, preventDefault(){}, shiftKey: false, ctrlKey: false, metaKey: false, altKey: false})); }
  const o = {}, V = document.getElementById("vid"), form = () => document.getElementById("form").innerHTML;
  o.src0 = V.src;
  key("1"); key("Enter");
  o.src1 = V.src; o.circleOpen = form().indexOf("<fieldset id='fsCircle'>") >= 0;
  const cb = document.getElementById("circbox"); o.circHidden = !!cb.hidden; o.caveat = cb.innerHTML.indexOf("Map caveat") >= 0;
  key("Enter"); o.curBlocked = cur;
  key("8"); o.cv = (J[EV[0].id] || {}).circle_verdict;
  key("Enter"); o.cur2 = cur; o.src2 = V.src;
  key("m"); o.mapNoStart = !!(J[EV[1].id] || {}).map_flag;
  key("1"); key("Enter"); key("Enter"); o.cur3 = cur;
  key("m"); o.mapStart = !!(J[EV[2].id] || {}).map_flag;
  process.stdout.write(JSON.stringify(o));
})();
"""


def ui_flow(page: dict, out: Path) -> dict:
    """Run both script blocks of the page in node over a minimal DOM stub and drive it with key events (text checks only)."""
    html = write_html(out, page)
    js = UI_STUB + "\n;\n" + "\n;\n".join(script_blocks(html)) + UI_DRIVE
    f = out / "ui_flow.js"
    f.write_text(js, encoding="utf-8")
    p = subprocess.run([node_exe(), str(f)], capture_output=True, text=True, encoding="utf-8")
    try:
        return json.loads(p.stdout)
    except Exception:  # noqa: BLE001
        return {"error": (p.stderr or p.stdout)[-600:]}


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
    ap.add_argument("--circles", action="store_true",
                    help=f"GUI v2: WISER circles (static start circle blind, moving circle after the first answer); plan {PLAN_V2}")
    ap.add_argument("--map-run", default=MAP_RUN, help="wiser_assist_p0 run whose mapping.json holds the accepted WISER -> paddock map")
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
