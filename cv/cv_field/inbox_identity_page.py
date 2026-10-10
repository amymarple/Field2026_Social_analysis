r"""inbox_identity_page.py — in-box cameras CH07 / CH08, phase 0, part C: the identity click page for the user.

Specification: implementation_plan/2026-10-10-inbox-ch0708-wiser-identity-p0.md (section C) + its dated amendments.
Reads an inbox_p0.py run (colour_segments.csv, colour_threshold.json, states_1s.npz, scan/ key-frame tables) and writes
<run>/identity_page/: index.html (self-contained, file://, no network), frames/ (full-resolution JPEG, quality 95,
upright as recorded), closeups/ (the six in-hand clips $OUT/2026c/inhand_closeups/SF07.MOV ... SF12.MOV - read-only,
sha256 checked against that folder's MANIFEST_sha256.csv - transcoded ONCE to H.264 MP4; sources untouched, their
sha256 recorded before and after), page_data.json, page_check.json.

One entry per colour segment (deduplicated by configuration = one entry per segment):
  frames   colour_mid = the first frame with time >= (start + end) / 2; ir_p06 / ir_p15 = the first frames with time >=
           end + 6 s / end + 15 s (after the ~3-s IR white-out); time = file-name start + PTS (field-PC local); each frame's
           chroma is recomputed and flagged if a colour frame is < thr or an IR frame >= thr.
  lid      each frame's lid-closed segment and its correction (frame px -> the 09-04 12:00 reference px, the 2 x 3 matrix B
           of frame_correction.Corrections("2026c").correction(cam, t)), with the flag; recorded only, nothing fitted.
  WISER    roster of the camera's house (CH07 -> house_2, CH08 -> house_1) at the segment middle from the cleaned per-second
           states (inbox_p0 states_1s.npz); "SF11 untagged after 09-07 06:10:45 — may be present"; per roster animal the
           mean position over [start - 60 s, start) in the house frame (along / across the ridge, inches), SE = sd(raw
           fixes) / sqrt(n), +-1 SD of the raw fixes, and the IMU still / active / locomoting shares of that minute.
The user clicks each visible rat's head (colour frame; optionally IR frames), picks SF07-SF12 / unknown and sure /
likely, and answers "pile composition complete? yes / no" per segment. localStorage autosave; Export CSV + JSON (named
inbox_identity_2026c_<timestamp>.*, to be saved into cv/configs/inbox_identity_2026c/); Import JSON. The page carries
NO pre-filled identity; the agent never looks at the frames.

Usage (cv env, PYTHONIOENCODING=utf-8):
  python cv/cv_field/inbox_identity_page.py --run <inbox_p0 run dir> [--closeups <folder with SF07.MOV ...>]
  python cv/cv_field/inbox_identity_page.py --run <inbox_p0 run dir> --refresh-legend   # legend only, same path, no decoding
  python cv/cv_field/inbox_identity_page.py --selftest
Legend (2026-10-10, the user's correction): built from wiser/configs/rat_identities_2026c.csv - the user's identifying
colour (id_colour, id_colour_note) first and bold, then the Notion coban / sticker / IR pattern for reference; click
markers take the identifying colour. The first days (about 08-30 / 08-31) are uncertain.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import inbox_p0 as ip  # noqa: E402

FFMPEG = Path("C:/ffmpeg/bin/ffmpeg.exe")
CLOSEUP_SRC = ip.OUT_ROOT / "2026c" / "inhand_closeups"     # read-only; MANIFEST_sha256.csv + README.md there
CLOSEUP_LABELS = ("SF07", "SF08", "SF09", "SF10", "SF11", "SF12")
IR_OFFSETS = (("ir_p06", 6.0), ("ir_p15", 15.0))
JPEG_Q = 95
PRE_WINDOW_S = 60.0
BODY_IN = (62.55 / 2.54, 45.72 / 2.54)           # house body, long side along the ridge (CAMERA_GEOMETRY_2026c.md section 4)
PAGE_VERSION = "inbox_identity_2026c_v1"
EXPORT_DIR = "cv/configs/inbox_identity_2026c/"
IDENTITY_CSV = REPO / "wiser" / "configs" / "rat_identities_2026c.csv"
LEGEND_SOURCE = "identifying colours: user 2026-10-10; Notion coban/sticker shown for reference"
LEGEND_UNCERTAIN = "The first days (about 08-30 / 08-31) are uncertain (the user: 'messy')."
# marker colour on the page for each identifying colour (rings get a contrasting halo); unknown = magenta
ID_CSS = {"green": "#2ca02c", "red": "#d62728", "blue": "#1f77b4", "black": "#111111", "white (looks grey)": "#d9d9d9",
          "white": "#f2f2f2", "grey": "#9a9a9a", "yellow": "#ffd400"}
UNKNOWN_CSS = "#ff3fd8"


def legend_from_csv(path: Path = IDENTITY_CSV) -> list[dict]:
    """One legend row per animal from wiser/configs/rat_identities_<cohort>.csv: the user's identifying colour (id_colour,
    id_colour_note) first, then the Notion coban / sticker / IR pattern of the animal's longest-valid tag row, and every
    tag with its validity window."""
    ids = pd.read_csv(path, dtype=str).fillna("")
    if "id_colour" not in ids.columns:
        raise ValueError(f"{path} has no id_colour column")
    rows = []
    for a in sorted(ids.animal.unique()):
        g = ids[ids.animal == a].copy()
        g["_from"], g["_until"] = pd.to_datetime(g.valid_from, utc=True), pd.to_datetime(g.valid_until, utc=True)
        g = g.sort_values("_from")
        prim = g.loc[(g._until - g._from).idxmax()]
        loc = lambda s: pd.Timestamp(s).tz_convert(ip.TZ).strftime("%m-%d %H:%M")  # noqa: E731
        tags = "; ".join(f"{r.physical_tag_id} ({loc(r.valid_from)} -> {loc(r.valid_until)})" for r in g.itertuples())
        colours = sorted(set(g.id_colour))
        if len(colours) != 1:
            raise ValueError(f"{a}: several id_colour values {colours}")
        rows.append({"animal": a, "tag": tags, "id_colour": colours[0], "id_colour_note": prim.id_colour_note,
                     "coban_notion": prim.coband_color, "sticker": prim.sticker_color, "ir_pattern": prim.pattern,
                     "css": ID_CSS.get(colours[0], "#888888")})
    return rows


# Top-view orientation references (paddock inches, origin pole A0): the nearest pole of each house, measured foot positions
# (rev g, CAMERA_GEOMETRY_2026c.md section 4b). house_1 sits by B1, house_2 by B3.
HOUSE_POLES = {"house_1": {"name": "B1", "xy": [131.2, 125.2]}, "house_2": {"name": "B3", "xy": [357.3, 119.5]}}
ORIENT_NOTE = ("display only: the top view can be rotated (0 / 90 / 180 / 270 deg) and mirrored per house; default = WISER / paddock "
               "orientation (+x right, +y up). Not a fit and not the pre-registered camera <-> WISER mapping (fitted later from the "
               "blind clicks); the chosen orientation is exported as orientation_by_house and may serve as an independent prior / check")


def legend_meta(path: Path = IDENTITY_CSV) -> dict:
    poses = ip.house_poses()
    refs = {h: {"centre": list(poses[h]["centre"]), "ridge_deg": float(poses[h]["ridge_deg"]), "pole": HOUSE_POLES[h]} for h in ip.HOUSES}
    return {"legend_source": LEGEND_SOURCE, "legend_uncertain": LEGEND_UNCERTAIN, "legend_csv": "wiser/configs/" + Path(path).name,
            "legend_csv_sha256": ip.sha256(Path(path)), "unknown_css": UNKNOWN_CSS, "house_refs": refs, "orientation_note": ORIENT_NOTE}


def orient_view(dx: float, dy: float, rot_deg: int, mirror: bool) -> tuple[float, float]:
    """Paddock offset (dx, dy) -> top-view coordinates (a right, b up): mirror flips x, then a counter-clockwise rotation by
    rot_deg (multiples of 90). The page's JS (viewXY) does the same; the browser check compares the two."""
    x = -dx if mirror else dx
    c, s = round(np.cos(np.radians(rot_deg))), round(np.sin(np.radians(rot_deg)))
    return x * c - dy * s, x * s + dy * c


def house_to_paddock(along: float, across: float, ridge_deg: float) -> tuple[float, float]:
    """House frame (along, across) -> paddock offset from the house centre (inverse of inbox_p0.to_house_frame)."""
    p = np.radians(ridge_deg)
    return along * np.cos(p) - across * np.sin(p), along * np.sin(p) + across * np.cos(p)


# ----------------------------------------------------------------------------------------------- frames
def key_index(run: Path) -> dict:
    """file path -> {pts: frame index} for every scanned key frame."""
    kf = ip.load_scan(run, "scan")
    return {f: dict(zip(g.pts.astype(int), g.frame_idx.astype(int))) for f, g in kf.groupby("file")}, kf


def grab_frame(files: pd.DataFrame, kidx: dict, cam: str, t: datetime) -> tuple[np.ndarray | None, dict]:
    """The first frame with time >= t (file-name start + PTS): RGB full resolution + its file, frame index, pts, time, chroma."""
    import av
    r = files[(files.camera == cam) & (files.start_t <= t) & (files.end_t > t)]
    if r.empty:
        return None, {"error": f"no file of {cam} covers {t}"}
    r = r.iloc[0]
    st = r.start_t.to_pydatetime()
    rel = (t - st).total_seconds()
    ki = kidx.get(r.file, {})
    with av.open(r.file) as c:
        s = c.streams.video[0]
        tb = float(s.time_base)
        c.seek(max(0, int((rel - 0.001) / tb)), stream=s, backward=True, any_frame=False)
        cur = None
        for f in c.decode(s):
            if f.pts is None:
                continue
            cur = ki.get(int(f.pts), None) if cur is None else cur + 1
            if cur is None:
                cur = -10**9
            trel = f.pts * tb
            if trel >= rel - 1e-6:
                c_val, _ = ip.frame_measures(f)
                img = f.to_ndarray(format="rgb24")
                tt = st + timedelta(seconds=trel)
                return img, {"file": Path(r.file).name, "file_path": r.file, "frame_idx": cur if cur >= 0 else None, "pts": int(f.pts),
                             "time": f"{tt:%Y-%m-%d %H:%M:%S.%f}"[:-3], "chroma": round(c_val, 4)}
    return None, {"error": f"no frame at/after {t} in {r.file}"}


def write_jpeg(img: np.ndarray, path: Path) -> None:
    import cv2
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_Q]):
        raise IOError(f"could not write {path}")


def lid_correction(C, cam: str, t: datetime) -> dict:
    try:
        B, info = C.correction(cam, t)
    except Exception as ex:  # noqa: BLE001
        return {"error": repr(ex)}
    return {"lid_segment": info.get("segment"), "lid_open": bool(info.get("lid_open")), "flag": info.get("flag"),
            "target_frame": info.get("target_frame"), "used": info.get("used"),
            "B_frame_to_ref": None if B is None else [[round(float(v), 8) for v in row] for row in np.asarray(B)]}


# ----------------------------------------------------------------------------------------------- WISER panel
def wiser_panel(run: Path, seg: pd.Series, z: dict, track_root: Path | None = None, cache: dict | None = None) -> dict:
    t0 = datetime.fromisoformat(str(z["t0"]))
    labs = [str(x) for x in z["labels"]]
    start, mid = datetime.fromisoformat(seg.start), datetime.fromisoformat(seg.mid)
    house = ip.CAM_HOUSE[seg.camera]
    code = ip.HOUSE_CODE[house]
    k = int((mid - t0).total_seconds())
    n = z["states"].shape[1]
    roster, other, out, unknown = [], [], [], []
    for j, lab in enumerate(labs):
        if lab not in ip.LABELS:
            continue
        s = int(z["states"][j, k]) if 0 <= k < n else ip.S_UNK
        if lab == "SF11" and ip.untagged("SF11", mid):
            continue
        if s == code:
            roster.append(lab)
        elif s in (ip.S_H1, ip.S_H2):
            other.append(f"{lab} ({ip.STATE_NAME[s]})")
        elif s == ip.S_OUT:
            out.append(lab)
        else:
            unknown.append(lab)
    mp, poses = ip.load_map(), ip.house_poses()
    cache = cache if cache is not None else {}
    pos = []
    a = start - timedelta(seconds=PRE_WINDOW_S)
    for lab in roster:
        key = (lab, a.date())
        if key not in cache:
            days = sorted({a.strftime("%Y-%m-%d"), start.strftime("%Y-%m-%d")})
            df = ip.load_label(lab, days, track_root)
            cache[key] = df.loc[ip.fix_mask(df, "primary")].reset_index(drop=True)
        df = cache[key]
        j = labs.index(lab)
        d = df[(df.t >= a) & (df.t < start)]
        if len(d):
            sec = ((d["t"] - pd.Timestamp(t0)).dt.total_seconds().to_numpy() // 1).astype(np.int64)
            inside = (sec >= 0) & (sec < n)
            keep = np.zeros(len(d), bool)
            keep[inside] = z["states"][j, sec[inside]] == code
            keep &= ip.house_membership(d["x"].to_numpy(), d["y"].to_numpy(), ip.load_rois())[house]   # as inbox_p0 in-house fixes
            d = d.loc[keep]
        st = ip.window_stats(d, mp, poses[house])
        pos.append({"animal": lab, **{kk: (round(v, 4) if isinstance(v, float) else v) for kk, v in st.items()}})
    sf11_note = ("SF11 untagged after 09-07 06:10:45 - may be present" if mid >= ip.SF11_UNTAGGED[1][0]
                 else "SF11 untagged 09-02 00:03-08:15 - may be present" if ip.untagged("SF11", mid) else "")
    return {"house": house, "at": seg.mid, "roster": roster, "other_house": other, "out": out, "untracked": unknown,
            "sf11_note": sf11_note, "window": f"{a:%H:%M:%S}-{start:%H:%M:%S} (the minute before colour ON)",
            "positions": pos, "pose": poses[house], "body_in": [round(BODY_IN[0], 3), round(BODY_IN[1], 3)]}


# ----------------------------------------------------------------------------------------------- close-ups
def transcode_closeups(src_dir: Path, out_dir: Path, ffmpeg: Path = FFMPEG, labels=CLOSEUP_LABELS) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    man = {}
    if (src_dir / "MANIFEST_sha256.csv").exists():
        man = dict(pd.read_csv(src_dir / "MANIFEST_sha256.csv")[["file", "sha256"]].itertuples(index=False, name=None))
    rows = []
    for lab in labels:
        src = src_dir / f"{lab}.MOV"
        dst = out_dir / f"{lab}.mp4"
        if not src.exists():
            rows.append({"animal": lab, "src": src.as_posix(), "error": "missing"})
            continue
        h0, m0 = ip.sha256(src), src.stat().st_mtime
        if man and man.get(src.name) != h0:
            rows.append({"animal": lab, "src": src.as_posix(), "error": f"sha256 {h0} does not match the folder manifest"})
            continue
        if not dst.exists():
            cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-n", "-i", str(src), "-c:v", "libx264", "-preset", "medium",
                   "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dst)]
            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode != 0:
                rows.append({"animal": lab, "src": src.as_posix(), "error": p.stderr[-500:]})
                continue
        h1, m1 = ip.sha256(src), src.stat().st_mtime
        rows.append({"animal": lab, "src": src.as_posix(), "dst": f"closeups/{lab}.mp4", "src_sha256": h0,
                     "manifest_match": (man.get(src.name) == h0) if man else None,
                     "src_unchanged": bool(h0 == h1 and m0 == m1), "dst_bytes": dst.stat().st_size})
    return rows


# ----------------------------------------------------------------------------------------------- page
def build(run: Path, closeup_src: Path = CLOSEUP_SRC, track_root: Path | None = None, corrections=None, ffmpeg: Path = FFMPEG) -> dict:
    page = run / "identity_page"
    (page / "frames").mkdir(parents=True, exist_ok=True)
    seg = pd.read_csv(run / "colour_segments.csv")
    thr = json.loads((run / "colour_threshold.json").read_text(encoding="utf-8"))["thr"]
    kidx, kf = key_index(run)
    files = ip.file_table(kf, run)
    z = dict(np.load(run / "states_1s.npz", allow_pickle=False))
    if corrections is None:
        from frame_correction import Corrections
        corrections = Corrections("2026c")
    cache, entries = {}, []
    for s in seg.itertuples():
        sid = s.segment_id
        start, end, mid = (datetime.fromisoformat(x) for x in (s.start, s.end, s.mid))
        frames = []
        for kind, t in (("colour_mid", mid),) + tuple((k, end + timedelta(seconds=o)) for k, o in IR_OFFSETS):
            img, info = grab_frame(files, kidx, s.camera, t)
            fn = f"frames/{sid}_{kind}.jpg"
            if img is not None:
                write_jpeg(img, page / fn)
                info["path"] = fn
                info["width"], info["height"] = int(img.shape[1]), int(img.shape[0])
                tt = datetime.fromisoformat(info["time"])
                info["mode_check"] = ("ok" if (info["chroma"] >= thr) == (kind == "colour_mid") else
                                      f"MISMATCH: chroma {info['chroma']} vs thr {thr:.4g}")
                info["lid"] = lid_correction(corrections, s.camera, tt)
            info.update({"kind": kind, "target_time": f"{t:%Y-%m-%d %H:%M:%S.%f}"[:-3]})
            info.pop("file_path", None)
            frames.append(info)
        panel = wiser_panel(run, pd.Series(s._asdict()), z, track_root, cache)
        entries.append({"segment_id": sid, "camera": s.camera, "house": s.house, "start": s.start, "end": s.end, "mid": s.mid,
                        "duration_s": s.duration_s, "median_chroma": s.median_chroma, "n_colour_keyframes": int(s.n_colour_keyframes),
                        "flags": "" if pd.isna(s.flags) else str(s.flags), "lid_event": "" if pd.isna(s.lid_event) else str(s.lid_event),
                        "log_row": None if pd.isna(s.log_row) else int(s.log_row), "log_kind": "" if pd.isna(s.log_kind) else str(s.log_kind),
                        "frames": frames, "wiser": panel})
        print(f"[page] {sid}: {[f.get('mode_check', f.get('error')) for f in frames]} roster {panel['roster']}", flush=True)
    clips = transcode_closeups(closeup_src, page / "closeups", ffmpeg)
    meta = {"page_version": PAGE_VERSION, "run": run.as_posix(), "made": datetime.now().isoformat(timespec="seconds"),
            "plan": ip.PLAN, "export_dir": EXPORT_DIR, "threshold": thr, "n_segments": len(entries), **legend_meta()}
    data = {"meta": meta, "legend": legend_from_csv(), "closeups": clips, "segments": entries}
    (page / "page_data.json").write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    (page / "index.html").write_text(render_html(data), encoding="utf-8")
    chk = check_page(page)
    (page / "page_check.json").write_text(json.dumps(chk, indent=2), encoding="utf-8")
    print(f"[page] {len(entries)} segments -> {(page / 'index.html').as_posix()}; check: {chk['verdict']}", flush=True)
    return chk


def refresh_legend(run: Path, csv_path: Path = IDENTITY_CSV) -> dict:
    """Rewrite only the legend (from the identity CSV) and re-render index.html at the SAME path from the existing
    page_data.json: frames, close-ups, segments, page_version and run are kept, so the localStorage key
    (page_version :: run) and the user's stored clicks carry over. No video is decoded."""
    page = run / "identity_page"
    data = json.loads((page / "page_data.json").read_text(encoding="utf-8"))
    before = {k: data["meta"].get(k) for k in ("page_version", "run")}
    frames_before = {p.name: p.stat().st_mtime for p in (page / "frames").glob("*.jpg")}
    data["legend"] = legend_from_csv(csv_path)
    data["meta"].update(legend_meta(csv_path))
    data["meta"]["legend_refreshed"] = datetime.now().isoformat(timespec="seconds")
    assert {k: data["meta"].get(k) for k in ("page_version", "run")} == before, "the localStorage key would change"
    (page / "page_data.json").write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    (page / "index.html").write_text(render_html(data), encoding="utf-8")
    chk = check_page(page)
    chk["frames_untouched"] = frames_before == {p.name: p.stat().st_mtime for p in (page / "frames").glob("*.jpg")}
    chk["local_storage_key"] = f"{before['page_version']}::{before['run']}"
    (page / "page_check.json").write_text(json.dumps(chk, indent=2), encoding="utf-8")
    print(f"[page] legend refreshed from {csv_path.name} -> {(page / 'index.html').as_posix()}; check: {chk['verdict']}", flush=True)
    return chk


def check_page(page: Path) -> dict:
    """Every media path referenced by the page resolves; no network URL anywhere in the page."""
    txt = (page / "index.html").read_text(encoding="utf-8")
    m = re.search(r"<script id=\"page-data\" type=\"application/json\">(.*?)</script>", txt, re.S)
    data = json.loads(html.unescape(m.group(1))) if m else {}
    paths = [f["path"] for s in data.get("segments", []) for f in s["frames"] if f.get("path")]
    paths += [c["dst"] for c in data.get("closeups", []) if c.get("dst")]
    static = re.sub(r"<script[^>]*>.*?</script>", "", txt, flags=re.S)
    paths += re.findall(r"(?:src|href)=\"([^\"#][^\"]*)\"", static)
    missing = sorted({p for p in paths if not re.match(r"(?i)[a-z][a-z0-9+.-]*:", p) and not (page / p).exists()})
    net = sorted(set(re.findall(r"(?i)(?:https?:|ftp:|wss?:)//[^\s\"'<>]*", txt)) | set(re.findall(r"(?i)[\"'(]//[a-z0-9.-]+\.[a-z]{2,}", txt)))
    n_frames = sum(1 for s in data.get("segments", []) for f in s["frames"] if f.get("path"))
    mism = [f"{s['segment_id']} {f['kind']}" for s in data.get("segments", []) for f in s["frames"] if str(f.get("mode_check", "")).startswith("MISMATCH")]
    errs = [f"{s['segment_id']} {f['kind']}: {f['error']}" for s in data.get("segments", []) for f in s["frames"] if f.get("error")]
    prefilled = [c for s in data.get("segments", []) for c in s.get("clicks", [])]
    return {"verdict": "PASS" if not missing and not net and not prefilled else "FAIL", "n_paths": len(set(paths)),
            "missing": missing, "network_urls": net, "n_segments": len(data.get("segments", [])), "n_frames": n_frames,
            "frame_errors": errs, "mode_mismatches": mism, "prefilled_identities": len(prefilled),
            "closeups": [c.get("dst") or c.get("error") for c in data.get("closeups", [])]}


PAGE_CSS = """
:root{--bg:#f6f6f4;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#d9d9d4;--acc:#1f6feb;--warn:#b54708;--ok:#1a7f37;--selbg:#e8f0fe}
@media (prefers-color-scheme: dark){:root{--bg:#161615;--fg:#ecece8;--mut:#a3a39c;--card:#20201e;--line:#3a3a36;--acc:#6ea8fe;--warn:#f79009;--ok:#4ac26b;--selbg:#1d2a44}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:8px 16px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center;flex-wrap:wrap}
header h1{font-size:17px;margin:0}header .sp{flex:1}button,select,input{font:inherit}
button{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:6px;padding:3px 9px;cursor:pointer}
button.on{background:var(--acc);color:#fff;border-color:var(--acc)}button.x{padding:0 7px;font-weight:700}
button.reveal{background:var(--warn);color:#fff;border-color:var(--warn);font-weight:600}
#wrap{display:grid;grid-template-columns:250px minmax(0,1fr) 380px;gap:0;height:calc(100vh - 92px)}
#list{overflow:auto;border-right:1px solid var(--line)}#side{overflow:auto;border-left:1px solid var(--line);padding:10px}
.seg{padding:7px 10px;border-bottom:1px solid var(--line);cursor:pointer}.seg.cur{background:var(--card);box-shadow:inset 3px 0 0 var(--acc)}
.seg small{color:var(--mut);display:block}.badge{font-size:11px;padding:0 5px;border-radius:8px;border:1px solid var(--line);margin-left:4px}
#main{display:flex;flex-direction:column;min-width:0}
#tabs{display:flex;gap:6px;padding:6px 8px;border-bottom:1px solid var(--line);flex-wrap:wrap;align-items:center}
#selinfo{font-size:12.5px;padding:2px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card)}
#viewer{position:relative;flex:1;overflow:hidden;background:#000;cursor:crosshair;min-height:300px}
#stage{position:absolute;left:0;top:0;transform-origin:0 0}#stage img{display:block;user-select:none;-webkit-user-drag:none}
#stage svg{position:absolute;left:0;top:0;pointer-events:none}
#pop{position:absolute;display:none;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px;z-index:5;box-shadow:0 4px 16px rgba(0,0,0,.35);max-width:420px}
#pop .ids button{margin:2px}#below{max-height:34vh;overflow:auto;padding:8px;border-top:1px solid var(--line)}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:3px 5px;text-align:left;font-size:12.5px;vertical-align:top}
tr.selrow td{background:var(--selbg)}#clist tr.crow{cursor:pointer}
h2{font-size:14px;margin:12px 0 6px}.mut{color:var(--mut)}.warn{color:var(--warn)}.ok{color:var(--ok)}
.hidden-wiser{border:1px dashed var(--warn);border-radius:8px;padding:10px;margin:8px 0}
video{width:100%;max-height:260px;background:#000}details{margin:6px 0}code{font-size:12px}
#help{font-size:12px;color:var(--mut);padding:4px 16px;border-bottom:1px solid var(--line)}#help kbd{border:1px solid var(--line);border-radius:3px;padding:0 3px;font-size:11px}
.sw{display:inline-block;width:10px;height:10px;border:1px solid var(--fg);border-radius:2px;margin-right:4px;vertical-align:-1px}
@media (max-width:1100px){#wrap{grid-template-columns:1fr;height:auto}#viewer{height:70vh}#list,#side{max-height:40vh;border:0}}
"""

PAGE_JS = r"""
(function(){
'use strict';
const DATA = JSON.parse(document.getElementById('page-data').textContent);
const SEGS = DATA.segments;
const IDS = ['SF07','SF08','SF09','SF10','SF11','SF12','unknown'];
const KEYS = {'1':'SF07','2':'SF08','3':'SF09','4':'SF10','5':'SF11','6':'SF12','0':'unknown'};
const KEYOF = {SF07:'1', SF08:'2', SF09:'3', SF10:'4', SF11:'5', SF12:'6', unknown:'0'};
const SHORT = {SF07:'07', SF08:'08', SF09:'09', SF10:'10', SF11:'11', SF12:'12', unknown:'?'};
const COLS = {'unknown': DATA.meta.unknown_css || '#ff3fd8'};
DATA.legend.forEach(r => { COLS[r.animal] = r.css || '#888'; });   // marker colour = the user's identifying colour
function halo(c){ const v = parseInt(String(c).slice(1), 16); return (((v >> 16) & 255) * 0.299 + ((v >> 8) & 255) * 0.587 + (v & 255) * 0.114) < 128 ? '#fff' : '#000'; }
const LSKEY = DATA.meta.page_version + '::' + DATA.meta.run;     // unchanged since v1: stored clicks carry over
const STATE_VERSION = 2;
const R_SCREEN = 11, HIT_EXTRA = 12;                               // marker radius and selection reach, SCREEN pixels
let state = {version: STATE_VERSION, clicks: [], segments: {}};
let cur = 0, kind = 'colour_mid', selId = null, conf = 'sure';
let view = {s: 1, tx: 0, ty: 0};
let undoStack = [], redoStack = [], legacyMigrated = 0;
let mdrag = null, pdrag = null;
function uid(){ return 'k' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }
function now(){ return new Date().toISOString(); }
function snap(c){ return c ? JSON.parse(JSON.stringify(c)) : null; }
function r1(x){ return Math.round(x * 10) / 10; }
// Clicks stored before this page version have no reveal flag: they were saved before it loaded -> before_reveal, legacy.
function migrate(o){
  let n = 0;
  o.clicks = (o.clicks || []).map(c => { c = Object.assign({}, c); if (!c.click_id) c.click_id = uid();
    if (c.before_reveal === undefined) { c.before_reveal = true; c.legacy = true; n++; } return c; });
  o.segments = o.segments || {};
  if (n) o.legacy_migrated_at = o.legacy_migrated_at || now();
  o.version = STATE_VERSION;
  return n;
}
function load(){ try { const s = localStorage.getItem(LSKEY); if (s) { const o = JSON.parse(s); if (o && o.clicks) { legacyMigrated = migrate(o); state = o; if (legacyMigrated) persist(); } } } catch (e) {} }
function persist(){ try { localStorage.setItem(LSKEY, JSON.stringify(state)); } catch (e) {} }
function save(){ persist(); renderList(); }
function esc(s){ return String(s === null || s === undefined ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function seg(){ return SEGS[cur]; }
function frame(){ return seg().frames.find(f => f.kind === kind); }
function segState(id){ return state.segments[id] || (state.segments[id] = {}); }
function revealed(id){ return !!(state.segments[id] || {}).revealed_at; }
function live(c){ return !c.deleted_after_reveal; }
function byId(id){ return state.clicks.find(c => c.click_id === id) || null; }
function idxOf(id){ return state.clicks.findIndex(c => c.click_id === id); }
function segClicks(id){ return state.clicks.filter(c => c.segment_id === id && live(c)); }
function frameClicks(){ const s = seg(); return state.clicks.filter(c => c.segment_id === s.segment_id && c.frame_kind === kind && live(c)); }
// ---------------------------------------------------------------- edits with undo / redo (op = click snapshots before / after)
function setClick(id, sn, idx){
  const i = idxOf(id);
  if (sn === null) { if (i >= 0) state.clicks.splice(i, 1); if (selId === id) selId = null; return; }
  if (i >= 0) state.clicks[i] = snap(sn); else state.clicks.splice(Math.min(idx, state.clicks.length), 0, snap(sn));
}
function record(id, idx, before){
  const after = snap(byId(id));
  if (JSON.stringify(before) === JSON.stringify(after)) return;
  undoStack.push({id: id, idx: idx, before: before, after: after}); redoStack = [];
}
function change(id, fn){ const before = snap(byId(id)), idx = Math.max(idxOf(id), 0); fn(); record(id, idx, before); save(); }
function markEdit(c){ if (c && c.before_reveal && revealed(c.segment_id)) { c.edited_after_reveal = true; c.edited_at = now(); } }
function relabel(id, animal){ change(id, () => { const c = byId(id); c.animal = animal; markEdit(c); }); refresh(); }
function setConf(id, v){ change(id, () => { const c = byId(id); c.confidence = v; conf = v; markEdit(c); }); refresh(); }
function toggleConf(id){ const c = byId(id); setConf(id, c.confidence === 'likely' ? 'sure' : 'likely'); }
function moveBy(id, du, dv){ change(id, () => { const c = byId(id), f = frame(); c.u_px = r1(clamp(c.u_px + du, 0, f.width || 2560)); c.v_px = r1(clamp(c.v_px + dv, 0, f.height || 1920)); markEdit(c); }); refresh(); }
function deleteClick(id){
  const c = byId(id); if (!c) return;
  change(id, () => { if (c.before_reveal && revealed(c.segment_id)) { c.deleted_after_reveal = true; c.deleted_at = now(); } else state.clicks.splice(idxOf(id), 1); });
  if (selId === id) selId = null; hidePop(); refresh();
}
function undo(){ const op = undoStack.pop(); if (!op) return; setClick(op.id, op.before, op.idx); redoStack.push(op); selId = byId(op.id) && live(byId(op.id)) ? op.id : null; save(); refresh(); }
function redo(){ const op = redoStack.pop(); if (!op) return; setClick(op.id, op.after, op.idx); undoStack.push(op); selId = byId(op.id) && live(byId(op.id)) ? op.id : null; save(); refresh(); }
function clamp(x, a, b){ return Math.min(Math.max(x, a), b); }
function addClick(u, v, px, py){
  const s = seg(), f = frame(), lid = f.lid || {};
  const c = {click_id: uid(), segment_id: s.segment_id, camera: s.camera, house: s.house, frame_kind: f.kind, frame_file: f.file, frame_idx: f.frame_idx,
    frame_time: f.time, frame_path: f.path, u_px: r1(u), v_px: r1(v), animal: null, confidence: conf, before_reveal: !revealed(s.segment_id), legacy: false,
    lid_segment: lid.lid_segment, lid_flag: lid.flag, lid_target_frame: lid.target_frame, B_frame_to_ref: lid.B_frame_to_ref || null, clicked_at: now()};
  change(c.click_id, () => state.clicks.push(c));
  selId = c.click_id; refresh(); showPop(c.click_id, px, py);
}
// ---------------------------------------------------------------- reveal (blind first; per segment; cannot be undone)
function reveal(){
  const s = seg(), ss = segState(s.segment_id);
  if (ss.revealed_at) return;
  const mine = segClicks(s.segment_id);
  if (!confirm('Save the ' + mine.length + ' clicks of this segment as your blind record and reveal the WISER panel?\n\n' +
               'This cannot be undone. You can still edit afterwards; later edits are recorded separately.')) return;
  const t = now();
  mine.forEach(c => { c.before_reveal = true; c.saved_at = t;
    c.verdict_first = {animal: c.animal, confidence: c.confidence, u_px: c.u_px, v_px: c.v_px, frame_kind: c.frame_kind}; });
  ss.saved_at = t; ss.revealed_at = t; ss.n_saved_before_reveal = mine.length; ss.complete_first = ss.complete || '';
  undoStack = []; redoStack = [];                     // the pre-reveal record cannot be undone after the reveal
  save(); show(false);
}
// ---------------------------------------------------------------- rendering
function renderList(){
  const L = document.getElementById('list'); L.innerHTML = '';
  SEGS.forEach((s, i) => {
    const n = segClicks(s.segment_id).length, ss = state.segments[s.segment_id] || {};
    const d = document.createElement('div'); d.className = 'seg' + (i === cur ? ' cur' : '');
    d.innerHTML = '<b>' + esc(s.camera) + '</b> ' + esc(s.start.slice(5, 19)) + '<span class="badge">' + n + ' clicks</span>' +
      (ss.complete ? '<span class="badge">complete: ' + esc(ss.complete) + '</span>' : '') + (ss.revealed_at ? '<span class="badge">WISER revealed</span>' : '') +
      '<small>' + esc(s.duration_s) + ' s · ' + esc(s.house) + (s.lid_event ? ' · lid event' : '') + (s.log_kind ? ' · log: ' + esc(s.log_kind) : ' · not in the log') + '</small>';
    d.onclick = () => go(i);
    L.appendChild(d);
  });
}
function fit(){
  const V = document.getElementById('viewer'), f = frame(); if (!f) return;
  const W = f.width || 2560, H = f.height || 1920;
  view.s = Math.min(V.clientWidth / W, V.clientHeight / H); view.tx = (V.clientWidth - W * view.s) / 2; view.ty = (V.clientHeight - H * view.s) / 2; apply();
}
function apply(){ document.getElementById('stage').style.transform = 'translate(' + view.tx + 'px,' + view.ty + 'px) scale(' + view.s + ')'; drawPoints(); }
function drawPoints(){
  const svg = document.getElementById('pts'), f = frame(); svg.innerHTML = '';
  if (!f) return;
  svg.setAttribute('viewBox', '0 0 ' + (f.width || 2560) + ' ' + (f.height || 1920));
  svg.setAttribute('width', f.width || 2560); svg.setAttribute('height', f.height || 1920);
  const k = 1 / view.s, r = R_SCREEN * k;                       // constant screen size at any zoom
  frameClicks().forEach(c => {
    const col = c.animal ? (COLS[c.animal] || '#fff') : '#ffffff', hl = halo(col), isSel = c.click_id === selId;
    const g = document.createElementNS(svg.namespaceURI, 'g');
    g.setAttribute('data-click', c.click_id);
    let h = '';
    if (isSel) h += '<circle cx="' + c.u_px + '" cy="' + c.v_px + '" r="' + (r + 5 * k) + '" fill="none" stroke="#00e5ff" stroke-width="' + (4 * k) + '"/>';
    h += '<circle cx="' + c.u_px + '" cy="' + c.v_px + '" r="' + r + '" fill="' + col + '" fill-opacity=".35" stroke="' + hl + '" stroke-width="' + ((isSel ? 6 : 4.5) * k) + '"/>' +
         '<circle cx="' + c.u_px + '" cy="' + c.v_px + '" r="' + r + '" fill="none" stroke="' + col + '" stroke-width="' + ((isSel ? 3.5 : 2.5) * k) + '"' + (c.confidence === 'likely' ? ' stroke-dasharray="' + (4 * k) + ' ' + (3 * k) + '"' : '') + '/>' +
         '<text x="' + c.u_px + '" y="' + (c.v_px + 4 * k) + '" text-anchor="middle" font-size="' + (11 * k) + '" font-weight="800" fill="' + col + '" stroke="' + hl + '" stroke-width="' + (2.2 * k) + '" paint-order="stroke">' + esc(SHORT[c.animal] || '?') + '</text>';
    if (isSel) h += '<text x="' + (c.u_px + r + 7 * k) + '" y="' + (c.v_px - r) + '" font-size="' + (14 * k) + '" font-weight="800" fill="#00e5ff" stroke="#000" stroke-width="' + (3 * k) + '" paint-order="stroke">' + esc(c.animal || '(no id)') + ' · ' + esc(c.confidence) + '</text>';
    g.innerHTML = h; svg.appendChild(g);
  });
}
function renderSel(){
  const c = selId ? byId(selId) : null, E = document.getElementById('selinfo');
  E.innerHTML = c ? 'selected: <b>' + esc(c.animal || '(no id)') + '</b> · ' + esc(c.confidence) + ' · ' + esc(c.frame_kind) + ' · (' + c.u_px.toFixed(1) + ', ' + c.v_px.toFixed(1) + ') px' +
    (c.legacy ? ' · legacy' : '') + (revealed(c.segment_id) ? (c.before_reveal ? ' · saved before the reveal' : ' · added after the reveal') : '') : 'no marker selected';
}
function renderBelow(){
  const s = seg(), ss = state.segments[s.segment_id] || {}, rows = frameClicks(), rev = !!ss.revealed_at;
  let h = '<b>Clicks on this frame (' + esc(kind) + '): ' + rows.length + '</b> <span class="mut">— other frames of this segment: ' +
    s.frames.filter(f => f.kind !== kind).map(f => esc(f.kind) + ' ' + segClicks(s.segment_id).filter(c => c.frame_kind === f.kind).length).join(', ') + '</span>' +
    '<table id="clist"><tr><th></th><th>id</th><th>confidence</th><th>image px (u, v)</th><th>status</th><th></th></tr>';
  rows.forEach(c => {
    const st = (c.legacy ? 'legacy · ' : '') + (rev ? (c.before_reveal ? 'saved before reveal' + (c.edited_after_reveal ? ' · edited after' : '') : 'added after reveal') : 'not yet saved');
    h += '<tr class="crow' + (c.click_id === selId ? ' selrow' : '') + '" data-id="' + c.click_id + '"><td><button class="bsel" data-id="' + c.click_id + '">select</button></td>' +
      '<td><span class="sw" style="background:' + (c.animal ? (COLS[c.animal] || '#888') : '#fff') + '"></span><select class="sid" data-id="' + c.click_id + '">' +
      ['<option value="">(pick)</option>'].concat(IDS.map(x => '<option value="' + x + '"' + (x === c.animal ? ' selected' : '') + '>' + x + ' [' + KEYOF[x] + ']</option>')).join('') + '</select></td>' +
      '<td><select class="scf" data-id="' + c.click_id + '"><option' + (c.confidence === 'sure' ? ' selected' : '') + '>sure</option><option' + (c.confidence === 'likely' ? ' selected' : '') + '>likely</option></select></td>' +
      '<td>' + c.u_px.toFixed(1) + ', ' + c.v_px.toFixed(1) + '</td><td class="mut">' + esc(st) + '</td>' +
      '<td><button class="x" title="delete" data-id="' + c.click_id + '">×</button></td></tr>';
  });
  h += '</table>';
  h += '<p><b>Pile composition complete?</b> <label><input type="radio" name="pc" value="yes"' + (ss.complete === 'yes' ? ' checked' : '') + '> yes</label> ' +
       '<label><input type="radio" name="pc" value="no"' + (ss.complete === 'no' ? ' checked' : '') + '> no</label> ' +
       '<label><input type="radio" name="pc" value=""' + (!ss.complete ? ' checked' : '') + '> not answered</label> &nbsp; note: <input id="snote" size="36" value="' + esc(ss.note || '') + '"></p>';
  h += rev ? '<p class="ok">WISER revealed ' + esc(ss.revealed_at) + '; ' + esc(ss.n_saved_before_reveal) + ' clicks were saved before the reveal (the blind record). Edits since are recorded separately.</p>'
           : '<p><button class="reveal" id="breveal2">Save clicks &amp; reveal WISER</button> <span class="mut">The WISER roster and arrangement stay hidden until you save this segment (blind first).</span></p>';
  const B = document.getElementById('below'); B.innerHTML = h;
  B.querySelectorAll('tr.crow').forEach(e => e.onclick = ev => { if (ev.target.closest('select,button')) return; select(e.dataset.id); });
  B.querySelectorAll('.bsel').forEach(e => e.onclick = () => select(e.dataset.id));
  B.querySelectorAll('.sid').forEach(e => e.onchange = () => { if (e.value) relabel(e.dataset.id, e.value); });
  B.querySelectorAll('.scf').forEach(e => e.onchange = () => setConf(e.dataset.id, e.value));
  B.querySelectorAll('button.x').forEach(e => e.onclick = () => deleteClick(e.dataset.id));
  B.querySelectorAll('input[name=pc]').forEach(e => e.onchange = () => { segState(s.segment_id).complete = e.value; save(); });
  document.getElementById('snote').onchange = e => { segState(s.segment_id).note = e.target.value; save(); };
  const b2 = document.getElementById('breveal2'); if (b2) b2.onclick = reveal;
}
function select(id){ selId = id; hidePop(); refresh(); }
// ---------------------------------------------------------------- top-view orientation (display only; per house; default = paddock)
const ORIENTS = [[0, false], [90, false], [180, false], [270, false], [0, true], [90, true], [180, true], [270, true]];
function orientName(r, m){ return (r === 0 && !m) ? 'WISER / paddock: +x right, +y up (default)' : (m ? 'mirrored (x flipped), ' : '') + (r ? 'rotated ' + r + '° counter-clockwise' : 'not rotated'); }
function orientOf(house){ const o = (state.orientation_by_house || {})[house]; return o ? {rot: +o.rot_deg, mirror: !!o.mirror, chosen_at: o.chosen_at} : {rot: 0, mirror: false, chosen_at: null}; }
function setOrient(house, rot, mirror){ state.orientation_by_house = state.orientation_by_house || {}; state.orientation_by_house[house] = {rot_deg: rot, mirror: mirror, chosen_at: now()}; save(); renderSide(); }
function viewXY(dx, dy, o){ const x = o.mirror ? -dx : dx, t = o.rot * Math.PI / 180, c = Math.round(Math.cos(t)), s = Math.round(Math.sin(t)); return [x * c - dy * s, x * s + dy * c]; }
function houseToPad(al, ac, phi){ const p = phi * Math.PI / 180; return [al * Math.cos(p) - ac * Math.sin(p), al * Math.sin(p) + ac * Math.cos(p)]; }
function sideOf(v){ return Math.abs(v[0]) > Math.abs(v[1]) ? (v[0] > 0 ? 'right' : 'left') : (v[1] > 0 ? 'top' : 'bottom'); }
function wiserPanel(w){
  const o = orientOf(w.house), phi = w.pose.ridge_deg;
  const sel = '<select id="orient-sel" data-house="' + esc(w.house) + '">' + ORIENTS.map(q => '<option value="' + q[0] + '|' + (q[1] ? 1 : 0) + '"' +
    (q[0] === o.rot && q[1] === o.mirror ? ' selected' : '') + '>' + esc(orientName(q[0], q[1])) + '</option>').join('') + '</select>';
  return '<h2>WISER at the flash (' + esc(w.house) + ')</h2><p>Roster (tagged animals in this house at the segment middle): <b>' + (w.roster.length ? esc(w.roster.join(', ')) : 'none') + '</b>' +
    (w.sf11_note ? '<br><span class="warn">' + esc(w.sf11_note) + '</span>' : '') +
    (w.other_house.length ? '<br>other house: ' + esc(w.other_house.join(', ')) : '') + (w.out.length ? '<br>outside: ' + esc(w.out.join(', ')) : '') +
    (w.untracked.length ? '<br>untracked: ' + esc(w.untracked.join(', ')) : '') + '</p>' +
    '<p>Top-view orientation for <b>' + esc(w.house) + '</b> (all its segments): ' + sel + '<br><span class="mut">Display only — not a fit and not the camera ↔ WISER mapping (that is fitted later from your blind clicks). ' +
    (o.chosen_at ? 'Chosen ' + esc(o.chosen_at) + '.' : 'Default (not chosen yet).') + '</span></p>' + topView(w) +
    '<p class="mut">WISER top view of the house in paddock directions (inches from the house centre), turned as chosen above; the edge labels name the paddock walls, the square is the nearest pole. Mean of ' + esc(w.window) +
    '; bars along and across the ridge: thick = +-1 SE of the mean, thin = +-1 SD of the fixes. The WISER tag sits on the head.</p>' +
    '<table><tr><th>animal</th><th>dx, dy (paddock)</th><th>along, across (ridge)</th><th>SE</th><th>n fixes</th><th>IMU still / active / loco</th></tr>' +
    w.positions.map(p => { const d = (p.along_in === null || p.along_in === undefined) ? null : houseToPad(p.along_in, p.across_in, phi);
      return '<tr><td>' + esc(p.animal) + '</td><td>' + (d ? num(d[0]) + ', ' + num(d[1]) : '-') + '</td><td>' + num(p.along_in) + ', ' + num(p.across_in) + '</td><td>' + num(p.along_se_in, 2) + ', ' + num(p.across_se_in, 2) +
      '</td><td>' + esc(p.n_fix) + '</td><td>' + num(p.still_share, 2) + ' / ' + num(p.active_share, 2) + ' / ' + num(p.loco_share, 2) + '</td></tr>'; }).join('') + '</table>';
}
function renderSide(){
  const s = seg(), f = frame(), rev = revealed(s.segment_id);
  let h = '<h2>Segment ' + esc(s.segment_id) + '</h2><table>' +
    '<tr><td>camera / house</td><td>' + esc(s.camera) + ' / ' + esc(s.house) + '</td></tr>' +
    '<tr><td>colour ON-OFF</td><td>' + esc(s.start.slice(11)) + ' - ' + esc(s.end.slice(11)) + ' (' + esc(s.duration_s) + ' s)</td></tr>' +
    '<tr><td>colour log</td><td>' + (s.log_kind ? 'row ' + esc(s.log_row) + ': ' + esc(s.log_kind) : '<span class="warn">no matching row</span>') + '</td></tr>' +
    '<tr><td>lid event</td><td>' + esc(s.lid_event || '-') + '</td></tr>' + (s.flags ? '<tr><td>flags</td><td class="warn">' + esc(s.flags) + '</td></tr>' : '') + '</table>';
  if (f) {
    h += '<h2>This frame</h2><table><tr><td>kind</td><td>' + esc(f.kind) + '</td></tr><tr><td>time</td><td>' + esc(f.time || '') + '</td></tr>' +
      '<tr><td>file / frame</td><td>' + esc(f.file || '') + ' / ' + esc(f.frame_idx) + '</td></tr><tr><td>chroma</td><td>' + esc(f.chroma) + ' (' + esc(f.mode_check || '') + ')</td></tr>';
    if (f.lid) h += '<tr><td>lid segment</td><td>' + esc(f.lid.lid_segment) + ' (' + esc(f.lid.flag) + ', target ' + esc(f.lid.target_frame) + ')</td></tr>';
    h += '</table>';
  }
  h += rev ? '<div id="wiser-panel">' + wiserPanel(s.wiser) + '</div>'
           : '<div class="hidden-wiser" id="wiser-hidden"><b>WISER roster and arrangement: hidden</b> until you save this segment\'s clicks (blind first: the clicks saved before the reveal are the ones the order test uses).<br><br>' +
             '<button class="reveal" id="breveal">Save clicks &amp; reveal WISER</button></div>';
  h += '<h2>Identity legend</h2><p class="mut legend-src">' + esc(DATA.meta.legend_source || '') + '. ' + esc(DATA.meta.legend_uncertain || '') + '</p>' +
    '<table class="legend"><tr><th>animal</th><th>tag</th><th>identifying colour (user)</th><th>coban (Notion)</th><th>sticker</th><th>IR pattern</th></tr>' +
    DATA.legend.map(r => '<tr><td><span class="sw" style="background:' + esc(r.css) + '"></span>' + esc(r.animal) + '</td><td>' + esc(r.tag) + '</td><td><b>' + esc(r.id_colour) + '</b>' +
      (r.id_colour_note ? '<br><span class="mut">' + esc(r.id_colour_note) + '</span>' : '') + '</td><td>' + esc(r.coban_notion) + '</td><td>' + esc(r.sticker) + '</td><td>' + esc(r.ir_pattern) + '</td></tr>').join('') + '</table>';
  h += '<h2>In-hand close-up clips (phone)</h2><p class="mut">SF07, SF08, SF09, SF10, SF12 filmed 2026-09-10 07:54-08:19 (AM round); SF11 filmed 2026-08-30 (its implant came off early, so an earlier clip is used).</p>' + DATA.closeups.map(c => c.dst ? '<details><summary>' + esc(c.animal) + '</summary><video controls preload="none" src="' + esc(c.dst) + '"></video></details>' : '<p class="warn">' + esc(c.animal) + ': ' + esc(c.error) + '</p>').join('');
  document.getElementById('side').innerHTML = h;
  const b = document.getElementById('breveal'); if (b) b.onclick = reveal;
  const os = document.getElementById('orient-sel');
  if (os) os.onchange = () => { const q = os.value.split('|'); setOrient(os.dataset.house, +q[0], q[1] === '1'); };
}
function num(v, d){ return (v === null || v === undefined || v === '') ? '-' : Number(v).toFixed(d === undefined ? 1 : d); }
function topView(w){
  const o = orientOf(w.house), phi = w.pose.ridge_deg, C = w.pose.centre, L = w.body_in[0], Wd = w.body_in[1];
  const S = 7.5, half = 24, P = 30, cx = P + half * S, cy = P + half * S, size = 2 * cx;
  const V = (dx, dy) => { const ab = viewXY(dx, dy, o); return [cx + ab[0] * S, cy - ab[1] * S]; };
  const H = (al, ac) => { const d = houseToPad(al, ac, phi); return V(d[0], d[1]); };
  const pt = q => q[0].toFixed(2) + ',' + q[1].toFixed(2);
  const line = (a, b, col, wd, op) => '<line x1="' + a[0] + '" y1="' + a[1] + '" x2="' + b[0] + '" y2="' + b[1] + '" stroke="' + col + '" stroke-width="' + wd + '"' + (op ? ' opacity="' + op + '"' : '') + '/>';
  let s = '<svg id="topview" viewBox="0 0 ' + size + ' ' + size + '" width="100%" style="max-width:360px;background:var(--card);border:1px solid var(--line)" data-house="' + esc(w.house) +
    '" data-cx="' + cx + '" data-cy="' + cy + '" data-scale="' + S + '" data-rot="' + o.rot + '" data-mirror="' + (o.mirror ? 1 : 0) + '">';
  s += '<polygon points="' + [[-L / 2, -Wd / 2], [L / 2, -Wd / 2], [L / 2, Wd / 2], [-L / 2, Wd / 2]].map(q => pt(H(q[0], q[1]))).join(' ') + '" fill="none" stroke="currentColor" stroke-dasharray="5 4"/>';
  const r0 = H(-L / 2 - 3, 0), r1 = H(L / 2 + 3, 0);
  s += line(r0, r1, 'currentColor', 1, '.35') + '<text x="' + (r1[0] + 3) + '" y="' + (r1[1] - 3) + '" font-size="10" fill="currentColor" opacity=".7">ridge</text>';
  const LBL = [[[1, 0], 'toward x = 480 wall'], [[-1, 0], 'toward x = 0 wall'], [[0, 1], 'toward y = 240 (row C)'], [[0, -1], 'toward y = 0 (row A)']];
  LBL.forEach(q => { const sd = sideOf(viewXY(q[0][0], q[0][1], o));
    const at = {right: [size - 9, cy, 90], left: [9, cy, -90], top: [cx, 13, 0], bottom: [cx, size - 5, 0]}[sd];
    s += '<text class="edge" data-side="' + sd + '" x="' + at[0] + '" y="' + at[1] + '" text-anchor="middle" font-size="11" font-weight="600" fill="currentColor"' +
         (at[2] ? ' transform="rotate(' + at[2] + ' ' + at[0] + ' ' + at[1] + ')"' : '') + '>' + esc(q[1]) + '</text>'; });
  const ref = ((DATA.meta.house_refs || {})[w.house] || {}).pole;
  if (ref) { const q = V(ref.xy[0] - C[0], ref.xy[1] - C[1]);
    s += '<rect class="pole" data-pole="' + esc(ref.name) + '" data-x="' + q[0] + '" data-y="' + q[1] + '" x="' + (q[0] - 4) + '" y="' + (q[1] - 4) + '" width="8" height="8" fill="currentColor"/>' +
         '<text x="' + (q[0] + 7) + '" y="' + (q[1] + 4) + '" font-size="11" fill="currentColor">pole ' + esc(ref.name) + '</text>'; }
  w.positions.forEach(p => {
    if (p.along_in === undefined || p.along_in === null) return;
    const col = COLS[p.animal] || '#888', m = H(p.along_in, p.across_in);
    const sdA = p.sd_along_raw_in || 0, sdC = p.sd_across_raw_in || 0, seA = Math.max(p.along_se_in || 0, 0.25), seC = Math.max(p.across_se_in || 0, 0.25);
    s += line(H(p.along_in - sdA, p.across_in), H(p.along_in + sdA, p.across_in), col, 1, '.6') + line(H(p.along_in, p.across_in - sdC), H(p.along_in, p.across_in + sdC), col, 1, '.6') +
         line(H(p.along_in - seA, p.across_in), H(p.along_in + seA, p.across_in), col, 4) + line(H(p.along_in, p.across_in - seC), H(p.along_in, p.across_in + seC), col, 4) +
         '<circle class="pos" data-animal="' + esc(p.animal) + '" cx="' + m[0] + '" cy="' + m[1] + '" r="4" fill="' + col + '" stroke="' + halo(col) + '"/>' +
         '<text x="' + (m[0] + 6) + '" y="' + (m[1] - 6) + '" font-size="12" font-weight="700" fill="' + col + '" stroke="' + halo(col) + '" stroke-width=".5" paint-order="stroke">' + esc(p.animal) + '</text>';
  });
  return s + '</svg><p class="mut">Orientation: ' + esc(orientName(o.rot, o.mirror)) + '. House body ' + num(L) + ' x ' + num(Wd) + ' in (dashed), ridge at ' + esc(phi) + ' deg in the paddock.</p>';
}
function refresh(){ drawPoints(); renderBelow(); renderSel(); renderList(); }
function show(refit){
  const f = frame();
  document.querySelectorAll('#tabs button[data-k]').forEach(b => b.classList.toggle('on', b.dataset.k === kind));
  const img = document.getElementById('img');
  if (f && f.path) { if (img.getAttribute('src') !== f.path) { img.setAttribute('src', f.path); img.onload = () => { if (refit !== false) fit(); drawPoints(); }; } else { if (refit !== false) fit(); } }
  else { img.removeAttribute('src'); }
  document.getElementById('fname').textContent = f ? (f.kind + ' · ' + (f.time || f.error || '')) : '';
  hidePop(); renderList(); renderBelow(); renderSide(); renderSel(); drawPoints();
}
function go(i){ cur = clamp(i, 0, SEGS.length - 1); selId = null; kind = 'colour_mid'; show(); }
function hidePop(){ document.getElementById('pop').style.display = 'none'; }
function showPop(id, px, py){
  const P = document.getElementById('pop'), c = byId(id); if (!c) return;
  P.innerHTML = '<div class="ids">' + IDS.map(x => '<button data-id="' + x + '"' + (c.animal === x ? ' class="on"' : '') + '><span class="sw" style="background:' + (COLS[x] || '#888') + '"></span>' + x + ' [' + KEYOF[x] + ']</button>').join('') + '</div>' +
    '<div>confidence: <button data-c="sure"' + (c.confidence === 'sure' ? ' class="on"' : '') + '>sure</button> <button data-c="likely"' + (c.confidence === 'likely' ? ' class="on"' : '') + '>likely</button> [c] ' +
    '<button data-x="1">delete [Del]</button> <button data-o="1">ok [Esc]</button></div>';
  P.style.left = Math.max(4, px + 16) + 'px'; P.style.top = Math.max(4, py + 16) + 'px'; P.style.display = 'block';
  P.querySelectorAll('[data-id]').forEach(b => b.onclick = ev => { ev.stopPropagation(); relabel(id, b.dataset.id); hidePop(); });
  P.querySelectorAll('[data-c]').forEach(b => b.onclick = ev => { ev.stopPropagation(); setConf(id, b.dataset.c); showPop(id, px, py); });
  P.querySelector('[data-x]').onclick = ev => { ev.stopPropagation(); deleteClick(id); };
  P.querySelector('[data-o]').onclick = ev => { ev.stopPropagation(); hidePop(); };
}
function hitTest(x, y){
  const r = document.getElementById('viewer').getBoundingClientRect();
  let best = null, bd = Infinity;
  frameClicks().forEach(c => { const d = Math.hypot(r.left + view.tx + c.u_px * view.s - x, r.top + view.ty + c.v_px * view.s - y); if (d < bd) { bd = d; best = c; } });
  return bd <= R_SCREEN + HIT_EXTRA ? best : null;              // within 12 screen px of the marker (its edge)
}
function setup(){
  const V = document.getElementById('viewer');
  V.addEventListener('mousedown', e => {
    if (e.target.closest('#pop') || e.button !== 0) return;
    e.preventDefault();
    const h = hitTest(e.clientX, e.clientY);
    hidePop();
    if (h) { selId = h.click_id; mdrag = {id: h.click_id, idx: idxOf(h.click_id), before: snap(h), x: e.clientX, y: e.clientY, u0: h.u_px, v0: h.v_px, moved: false}; refresh(); return; }
    pdrag = {x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty, moved: false};
  });
  window.addEventListener('mousemove', e => {
    if (mdrag) { const dx = e.clientX - mdrag.x, dy = e.clientY - mdrag.y;
      if (!mdrag.moved && Math.hypot(dx, dy) > 3) mdrag.moved = true;
      if (mdrag.moved) { const c = byId(mdrag.id), f = frame(); c.u_px = r1(clamp(mdrag.u0 + dx / view.s, 0, f.width || 2560)); c.v_px = r1(clamp(mdrag.v0 + dy / view.s, 0, f.height || 1920)); drawPoints(); renderSel(); }
      return; }
    if (!pdrag) return;
    const dx = e.clientX - pdrag.x, dy = e.clientY - pdrag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) pdrag.moved = true;
    if (pdrag.moved) { view.tx = pdrag.tx + dx; view.ty = pdrag.ty + dy; apply(); }
  });
  window.addEventListener('mouseup', e => {
    if (mdrag) { const d = mdrag; mdrag = null; if (d.moved) { markEdit(byId(d.id)); record(d.id, d.idx, d.before); save(); } refresh(); return; }
    if (!pdrag) return;
    const d = pdrag; pdrag = null;
    if (!d.moved && e.target.closest('#viewer') && !e.target.closest('#pop')) { const r = V.getBoundingClientRect(), f = frame(); if (!f || !f.path) return;
      const u = (e.clientX - r.left - view.tx) / view.s, v = (e.clientY - r.top - view.ty) / view.s;
      if (u < 0 || v < 0 || u > (f.width || 2560) || v > (f.height || 1920)) return; addClick(u, v, e.clientX - r.left, e.clientY - r.top); }
  });
  V.addEventListener('contextmenu', e => { e.preventDefault(); const h = hitTest(e.clientX, e.clientY); if (h) deleteClick(h.click_id); });
  V.addEventListener('wheel', e => { e.preventDefault(); const r = V.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    const k = Math.exp(-e.deltaY * 0.0015), s2 = Math.min(Math.max(view.s * k, 0.05), 8); view.tx = mx - (mx - view.tx) * s2 / view.s; view.ty = my - (my - view.ty) * s2 / view.s; view.s = s2; apply(); }, {passive: false});
  window.addEventListener('resize', () => fit());
  window.addEventListener('keydown', e => {
    const tg = e.target.tagName; if (tg === 'INPUT' || tg === 'SELECT' || tg === 'TEXTAREA') return;
    if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) { e.preventDefault(); if (e.shiftKey) redo(); else undo(); return; }
    if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || e.key === 'Y')) { e.preventDefault(); redo(); return; }
    if (e.ctrlKey || e.metaKey) return;
    const c = selId ? byId(selId) : null;
    if (c && live(c)) {
      if (KEYS[e.key] !== undefined && !e.altKey) { e.preventDefault(); relabel(c.click_id, KEYS[e.key]); hidePop(); return; }
      if (e.key === 'c' && !e.altKey) { e.preventDefault(); toggleConf(c.click_id); return; }
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); deleteClick(c.click_id); return; }
      const A = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[e.key];
      if (A && (e.shiftKey || e.altKey)) { e.preventDefault(); const k = e.altKey ? 10 : 1; moveBy(c.click_id, A[0] * k, A[1] * k); return; }
    }
    if (e.key === 'Escape') { selId = null; hidePop(); refresh(); return; }
    if (e.key === 'n' || e.key === 'PageDown') { go(cur + 1); return; }
    if (e.key === 'p' || e.key === 'PageUp') { go(cur - 1); return; }
    if (e.key === 'f') fit();
  });
  document.querySelectorAll('#tabs button[data-k]').forEach(b => b.onclick = () => { kind = b.dataset.k; selId = null; show(); });
  document.getElementById('bfit').onclick = () => fit();
  document.getElementById('bjson').onclick = exportJSON;
  document.getElementById('bcsv').onclick = exportCSV;
  document.getElementById('bimp').onclick = () => document.getElementById('fimp').click();
  document.getElementById('fimp').onchange = importJSON;
}
// ---------------------------------------------------------------- export / import
function stamp(){ const d = new Date(), p = n => String(n).padStart(2, '0'); return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + '_' + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds()); }
function download(name, text, type){ const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {type: type})); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
function segRows(){ return SEGS.map(s => { const ss = state.segments[s.segment_id] || {}, all = state.clicks.filter(c => c.segment_id === s.segment_id);
  return {segment_id: s.segment_id, camera: s.camera, house: s.house, start: s.start, end: s.end, complete: ss.complete || '', complete_first: ss.complete_first || '',
    note: ss.note || '', revealed_at: ss.revealed_at || '', saved_at: ss.saved_at || '', n_clicks: all.filter(live).length,
    n_before_reveal: all.filter(c => c.before_reveal && ss.revealed_at).length, n_after_reveal: all.filter(c => !c.before_reveal).length,
    n_legacy: all.filter(c => c.legacy).length, n_deleted_after_reveal: all.filter(c => c.deleted_after_reveal).length}; }); }
function orientExport(){ const o = {}; Array.from(new Set(SEGS.map(s => s.house))).sort().forEach(h => { const q = (state.orientation_by_house || {})[h];
  o[h] = q ? {rot_deg: +q.rot_deg, mirror: !!q.mirror, chosen_at: q.chosen_at} : {rot_deg: 0, mirror: false, chosen_at: null, default: true}; }); return o; }
function payload(){ return {page_version: DATA.meta.page_version, state_version: STATE_VERSION, run: DATA.meta.run, exported_at: now(), save_into: DATA.meta.export_dir,
  legend_source: DATA.meta.legend_source, legacy_migrated_at: state.legacy_migrated_at || '', orientation_by_house: orientExport(),
  orientation_note: DATA.meta.orientation_note || '', clicks: state.clicks, segments: segRows()}; }
function exportJSON(){ download('inbox_identity_2026c_' + stamp() + '.json', JSON.stringify(payload(), null, 1), 'application/json'); }
function csvq(v){ v = (v === null || v === undefined) ? '' : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
const CSV_COLS = ['record','click_id','segment_id','camera','house','frame_kind','frame_file','frame_idx','frame_time','u_px','v_px','animal','confidence',
  'before_reveal','legacy','edited_after_reveal','deleted_after_reveal','first_frame_kind','first_u_px','first_v_px','first_animal','first_confidence',
  'lid_segment','lid_flag','lid_target_frame','b11','b12','b13','b21','b22','b23','pile_complete','pile_complete_first','revealed_at','note','clicked_at'];
function exportCSV(){
  const lines = [CSV_COLS.join(',')];
  state.clicks.forEach(c => { const B = c.B_frame_to_ref || [[null, null, null], [null, null, null]], ss = state.segments[c.segment_id] || {}, F = c.verdict_first || {};
    lines.push(['click', c.click_id, c.segment_id, c.camera, c.house, c.frame_kind, c.frame_file, c.frame_idx, c.frame_time, c.u_px, c.v_px, c.animal, c.confidence,
      !!c.before_reveal, !!c.legacy, !!c.edited_after_reveal, !!c.deleted_after_reveal, F.frame_kind, F.u_px, F.v_px, F.animal, F.confidence,
      c.lid_segment, c.lid_flag, c.lid_target_frame, B[0][0], B[0][1], B[0][2], B[1][0], B[1][1], B[1][2], ss.complete || '', ss.complete_first || '', ss.revealed_at || '', '', c.clicked_at].map(csvq).join(',')); });
  segRows().forEach(s => { const r = CSV_COLS.map(() => ''); r[0] = 'segment'; r[2] = s.segment_id; r[3] = s.camera; r[4] = s.house;
    r[CSV_COLS.indexOf('pile_complete')] = s.complete; r[CSV_COLS.indexOf('pile_complete_first')] = s.complete_first;
    r[CSV_COLS.indexOf('revealed_at')] = s.revealed_at; r[CSV_COLS.indexOf('note')] = s.note; lines.push(r.map(csvq).join(',')); });
  download('inbox_identity_2026c_' + stamp() + '.csv', lines.join('\n') + '\n', 'text/csv');
}
function importJSON(ev){
  const f = ev.target.files[0]; if (!f) return; const r = new FileReader();
  r.onload = () => { try { const o = JSON.parse(r.result); if (!o.clicks) throw new Error('no clicks in file');
      if (!confirm('Replace the current clicks (' + state.clicks.length + ') with the ' + o.clicks.length + ' clicks in ' + f.name + '?')) return;
      const st = {clicks: o.clicks, segments: {}, legacy_migrated_at: o.legacy_migrated_at || undefined, orientation_by_house: {}};
      Object.entries(o.orientation_by_house || {}).forEach(([h, q]) => { if (q && q.chosen_at) st.orientation_by_house[h] = {rot_deg: +q.rot_deg, mirror: !!q.mirror, chosen_at: q.chosen_at}; });
      (o.segments || []).forEach(s => { st.segments[s.segment_id] = {complete: s.complete || '', complete_first: s.complete_first || '', note: s.note || '',
        revealed_at: s.revealed_at || '', saved_at: s.saved_at || '', n_saved_before_reveal: s.n_before_reveal}; if (!s.revealed_at) delete st.segments[s.segment_id].revealed_at; });
      migrate(st); state = st; undoStack = []; redoStack = []; selId = null; save(); show(); } catch (e) { alert('Import failed: ' + e.message); } };
  r.readAsText(f); ev.target.value = '';
}
window.__inbox = {view: () => ({s: view.s, tx: view.tx, ty: view.ty}), selected: () => selId, state: () => JSON.parse(JSON.stringify(state)),
                  undo: () => undoStack.length, redo: () => redoStack.length, legacyMigrated: () => legacyMigrated, R: R_SCREEN,
                  viewXY: (dx, dy, rot, mirror) => viewXY(dx, dy, {rot: rot, mirror: mirror})};   // read-only, for the checks
load(); setup(); show();
})();
"""


def render_html(data: dict) -> str:
    blob = json.dumps(data, default=str).replace("</", "<\\/")
    m = data["meta"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>In-box identity clicks</title><style>{PAGE_CSS}</style></head><body>
<header><h1>In-box identity clicks (CH07 / CH08, cohort 3)</h1>
<span class="mut">Click each visible rat's <b>head</b> on the colour frame (optionally the IR frames), give its id and sure / likely, answer
"pile composition complete?", then <b>Save clicks &amp; reveal WISER</b>. Autosaved in this browser; Export, then move the files into
<code>{html.escape(m['export_dir'])}</code>.</span>
<span class="sp"></span><button id="bjson">Export JSON</button><button id="bcsv">Export CSV</button><button id="bimp">Import JSON</button>
<input type="file" id="fimp" accept=".json,application/json" style="display:none"></header>
<div id="help">Keys and mouse: click empty image = add a marker · click within 12 px of a marker = select (never adds) · drag a marker = move ·
drag empty image = pan · wheel = zoom · <kbd>f</kbd> fit · <kbd>1</kbd>–<kbd>6</kbd> = SF07–SF12, <kbd>0</kbd> = unknown · <kbd>c</kbd> = sure / likely ·
<kbd>Del</kbd> / <kbd>Backspace</kbd> / right-click on a marker / × in the list = delete · <kbd>Shift</kbd>+arrows = nudge 1 px, <kbd>Alt</kbd>+arrows = 10 px ·
<kbd>Ctrl</kbd>+<kbd>Z</kbd> undo, <kbd>Ctrl</kbd>+<kbd>Y</kbd> redo · <kbd>Esc</kbd> deselect · <kbd>n</kbd> / <kbd>p</kbd> next / previous segment.
Markers: number = SF id, dashed = likely.</div>
<div id="wrap"><div id="list"></div>
<div id="main"><div id="tabs"><button data-k="colour_mid">colour (segment middle)</button><button data-k="ir_p06">IR +6 s after OFF</button>
<button data-k="ir_p15">IR +15 s after OFF</button><button id="bfit">fit</button><span id="selinfo"></span><span id="fname" class="mut"></span></div>
<div id="viewer"><div id="stage"><img id="img" alt="frame"><svg id="pts"></svg></div><div id="pop"></div></div>
<div id="below"></div></div>
<div id="side"></div></div>
<script id="page-data" type="application/json">{blob}</script>
<script>{PAGE_JS}</script></body></html>
"""


# ----------------------------------------------------------------------------------------------- browser check (DevTools protocol)
CHROME = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")


class _CDP:
    """Minimal DevTools-protocol client (websocket-client if installed, else websockets' sync client)."""

    def __init__(self, url: str):
        try:
            import websocket
            self.ws = websocket.create_connection(url, suppress_origin=True, timeout=60)
        except ImportError:
            from websockets.sync.client import connect
            self.ws = connect(url, max_size=2 ** 27, open_timeout=30)
        self.n = 0

    def call(self, method: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})

    def ev(self, expr: str, await_: bool = False):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=await_)
        if r.get("exceptionDetails"):
            raise RuntimeError(f"JS error in {expr[:80]!r}: {r['exceptionDetails'].get('exception', {}).get('description')}")
        return r.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _chrome(url: str, profile: Path, port: int):
    import urllib.request
    p = subprocess.Popen([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                          f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "--remote-allow-origins=*",
                          "--allow-file-access-from-files", "--window-size=1600,1000", url],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(160):
        try:
            tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2).read())
            pg = [t for t in tabs if t.get("type") == "page"]
            if pg:
                ver = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2).read())
                return p, pg[0]["webSocketDebuggerUrl"], ver["webSocketDebuggerUrl"]
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.25)
    p.terminate()
    raise RuntimeError("Chrome did not start")


def _close_chrome(p, browser_ws: str) -> None:
    """Close Chrome through the protocol so the profile flushes localStorage to disk."""
    try:
        b = _CDP(browser_ws)
        b.ws.send(json.dumps({"id": 1, "method": "Browser.close", "params": {}}))
        b.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        p.wait(timeout=30)
    except Exception:  # noqa: BLE001
        p.terminate()


def ui_check(page: Path, profile: Path, seg_index: int = 0, seed_legacy: dict | None = None) -> dict:
    """Drive the click page in headless Chrome like a user: add 3 markers, select one 8 px off its centre (no new marker),
    drag it, delete one with Delete and one with a right-click, undo, relabel with a number key, nudge (Shift / Alt +
    arrows) with undo / redo, check the constant marker size, reload (persisted), check the WISER panel stays hidden until
    "Save clicks & reveal WISER", then edit after the reveal and export (before_reveal / legacy / verdict_first flags).
    seed_legacy: a v1-style stored state (clicks without the reveal flag) written before the first reload."""
    data = json.loads((page / "page_data.json").read_text(encoding="utf-8"))
    lskey = f"{data['meta']['page_version']}::{data['meta']['run']}"
    sg = data["segments"][seg_index]
    sid = sg["segment_id"]
    fr = next(f for f in sg["frames"] if f["kind"] == "colour_mid")
    W, H = fr.get("width", 2560), fr.get("height", 1920)
    port = _free_port()
    p, wsu, bws = _chrome((page / "index.html").resolve().as_uri(), profile, port)
    res, okk = {}, {}
    c = None
    try:
        c = _CDP(wsu)
        c.call("Runtime.enable")

        def wait():
            for _ in range(120):
                try:
                    if c.ev("!!(window.__inbox && document.getElementById('img').complete && document.getElementById('img').naturalWidth > 0)"):
                        time.sleep(0.3)
                        return
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.25)
            raise RuntimeError("page did not load")

        def reload():
            c.ev("location.reload(); 1")
            time.sleep(0.8)
            wait()

        def go(i):
            c.ev(f"document.querySelectorAll('#list .seg')[{i}].click(); 1")
            time.sleep(0.4)
            wait()

        def st():
            return c.ev("window.__inbox.state()")

        def mine(s, all_=False):
            return [k for k in s["clicks"] if k["segment_id"] == sid and k["frame_kind"] == "colour_mid" and (all_ or not k.get("deleted_after_reveal"))]

        def scr(u, v):
            r = c.ev("(() => { const r = document.getElementById('viewer').getBoundingClientRect(); return [r.left, r.top]; })()")
            vw = c.ev("window.__inbox.view()")
            return r[0] + vw["tx"] + u * vw["s"], r[1] + vw["ty"] + v * vw["s"]

        def mouse(t, x, y, button="left", buttons=1):
            c.call("Input.dispatchMouseEvent", type=t, x=x, y=y, button=button, buttons=buttons if t != "mouseReleased" else 0, clickCount=1)

        def click(x, y, button="left"):
            mouse("mousePressed", x, y, button, 1 if button == "left" else 2)
            mouse("mouseReleased", x, y, button)
            time.sleep(0.15)

        def key(k, code=None, vk=None, mods=0, text=None):
            kw = {"key": k, "code": code or k, "modifiers": mods}
            if vk is not None:
                kw["windowsVirtualKeyCode"] = vk
            c.call("Input.dispatchKeyEvent", type="keyDown", **({**kw, "text": text} if text else kw))
            c.call("Input.dispatchKeyEvent", type="keyUp", **kw)
            time.sleep(0.15)

        def digit(d):
            key(d, f"Digit{d}", 48 + int(d), text=d)

        wait()
        if seed_legacy is not None:
            c.ev(f"localStorage.setItem({json.dumps(lskey)}, {json.dumps(json.dumps(seed_legacy))}); 1")
            reload()
        s0 = st()
        legacy = [k for k in s0["clicks"] if k.get("legacy")]
        res["legacy_clicks"] = len(legacy)
        okk["legacy_migrated"] = (len(legacy) >= 1 and all(k["before_reveal"] for k in legacy)) if (seed_legacy or legacy) else True
        go(seg_index)
        side = c.ev("document.getElementById('side').innerText")
        okk["orientation_hidden_before_reveal"] = c.ev("!document.getElementById('orient-sel') && !document.getElementById('topview')")
        okk["wiser_hidden_before_reveal"] = ("Roster" not in side and "Save clicks & reveal WISER" in side and "Identity legend" in side
                                             and "close-up clips" in side and c.ev("!document.getElementById('wiser-panel')"))
        n0 = len(mine(st()))
        pts = {"A": (0.30 * W, 0.40 * H), "B": (0.50 * W, 0.58 * H), "C": (0.70 * W, 0.42 * H)}
        ids = {}
        for (nm, (u, v)), d in zip(pts.items(), "123"):
            x, y = scr(u, v)
            before = {k["click_id"] for k in mine(st())}
            click(x, y)
            if nm == "A":
                okk["popup_after_add"] = c.ev("document.getElementById('pop').style.display") == "block"
            digit(d)
            ids[nm] = ({k["click_id"] for k in mine(st())} - before).pop()
        s1 = st()
        lab = {k["click_id"]: k for k in mine(s1)}
        okk["three_added_and_labelled"] = (len(mine(s1)) == n0 + 3 and [lab[ids[n]]["animal"] for n in "ABC"] == ["SF07", "SF08", "SF09"])
        # select A by clicking 8 px off its centre: no new marker
        xa, ya = scr(*pts["A"])
        click(xa + 8 / 2 ** 0.5, ya + 8 / 2 ** 0.5)
        okk["select_8px_off_no_new"] = c.ev("window.__inbox.selected()") == ids["A"] and len(mine(st())) == n0 + 3
        okk["selected_readout"] = "SF07" in c.ev("document.getElementById('selinfo').innerText")
        # drag A by (+40, +25) screen px
        sc = c.ev("window.__inbox.view()")["s"]
        mouse("mousePressed", xa, ya)
        for k in range(1, 6):
            mouse("mouseMoved", xa + 8 * k, ya + 5 * k)
        mouse("mouseReleased", xa + 40, ya + 25)
        time.sleep(0.2)
        a = next(k for k in mine(st()) if k["click_id"] == ids["A"])
        res["drag_du_dv_px"] = (round(a["u_px"] - pts["A"][0], 2), round(a["v_px"] - pts["A"][1], 2), round(40 / sc, 2), round(25 / sc, 2))
        tol = 1.0 / sc + 0.1                    # mouse-event coordinates are whole screen pixels: +-1 screen px
        okk["drag_moves"] = abs(a["u_px"] - pts["A"][0] - 40 / sc) <= tol and abs(a["v_px"] - pts["A"][1] - 25 / sc) <= tol
        a_pos = (a["u_px"], a["v_px"])
        # delete B with the Delete key, C with a right-click
        click(*scr(*pts["B"]))
        key("Delete", "Delete", 46)
        okk["delete_key"] = ids["B"] not in {k["click_id"] for k in mine(st())}
        xc, yc = scr(*pts["C"])
        click(xc, yc, "right")
        native = ids["C"] not in {k["click_id"] for k in mine(st())}
        if not native:                         # headless Chrome may not synthesise contextmenu from a raw right press
            c.ev(f"document.getElementById('viewer').dispatchEvent(new MouseEvent('contextmenu', {{bubbles: true, cancelable: true, clientX: {xc}, clientY: {yc}, button: 2}})); 1")
            time.sleep(0.15)
        res["right_click_native_contextmenu"] = native
        okk["right_click_delete"] = ids["C"] not in {k["click_id"] for k in mine(st())}
        key("z", "KeyZ", 90, mods=2)
        okk["undo_restores"] = ids["C"] in {k["click_id"] for k in mine(st())} and len(mine(st())) == n0 + 2
        # relabel C with a number key; nudge; undo / redo of a nudge
        click(*scr(*pts["C"]))
        digit("6")
        cc = next(k for k in mine(st()) if k["click_id"] == ids["C"])
        okk["relabel_number_key"] = cc["animal"] == "SF12"
        key("ArrowRight", "ArrowRight", 39, mods=8)
        key("ArrowDown", "ArrowDown", 40, mods=1)
        c1 = next(k for k in mine(st()) if k["click_id"] == ids["C"])
        key("z", "KeyZ", 90, mods=2)
        c2 = next(k for k in mine(st()) if k["click_id"] == ids["C"])
        key("y", "KeyY", 89, mods=2)
        c3 = next(k for k in mine(st()) if k["click_id"] == ids["C"])
        res["nudge"] = [(c1["u_px"] - cc["u_px"], c1["v_px"] - cc["v_px"]), (c2["v_px"] - cc["v_px"]), (c3["v_px"] - cc["v_px"])]
        okk["nudge_shift_alt_undo_redo"] = (abs(c1["u_px"] - cc["u_px"] - 1) < 1e-6 and abs(c1["v_px"] - cc["v_px"] - 10) < 1e-6
                                           and abs(c2["v_px"] - cc["v_px"]) < 1e-6 and abs(c3["v_px"] - cc["v_px"] - 10) < 1e-6)
        c_final = (c3["u_px"], c3["v_px"])
        # constant screen size of the markers
        key("Escape", "Escape", 27)

        def marker_px():
            r = c.ev(f"parseFloat(document.querySelector('#pts g[data-click=\"{ids['A']}\"] circle').getAttribute('r'))")
            return r * c.ev("window.__inbox.view()")["s"]
        m1 = marker_px()
        xv, yv = scr(W / 2, H / 2)
        c.call("Input.dispatchMouseEvent", type="mouseWheel", x=xv, y=yv, deltaX=0, deltaY=-400)
        time.sleep(0.3)
        m2 = marker_px()
        res["marker_screen_radius_px"] = (round(m1, 3), round(m2, 3), round(c.ev("window.__inbox.view()")["s"], 4))
        okk["marker_constant_screen_size"] = abs(m1 - m2) < 0.01 and abs(m1 - c.ev("window.__inbox.R")) < 0.01
        # reload: everything persisted, WISER still hidden
        reload()
        go(seg_index)
        s2 = {k["click_id"]: k for k in mine(st())}
        okk["persisted_after_reload"] = (set(s2) >= {ids["A"], ids["C"]} and ids["B"] not in s2 and s2[ids["A"]]["animal"] == "SF07"
                                         and (s2[ids["A"]]["u_px"], s2[ids["A"]]["v_px"]) == a_pos and s2[ids["C"]]["animal"] == "SF12"
                                         and (s2[ids["C"]]["u_px"], s2[ids["C"]]["v_px"]) == c_final
                                         and len([k for k in st()["clicks"] if k.get("legacy")]) == res["legacy_clicks"])
        okk["wiser_hidden_after_reload"] = "Roster" not in c.ev("document.getElementById('side').innerText")
        # reveal (per segment, cannot be undone)
        c.ev("window.confirm = () => true; document.getElementById('breveal').click(); 1")
        time.sleep(0.4)
        s3 = st()
        okk["reveal_shows_wiser"] = "Roster" in c.ev("document.getElementById('side').innerText") and bool(s3["segments"][sid].get("revealed_at"))
        okk["saved_before_reveal_frozen"] = all(k["before_reveal"] and k.get("verdict_first", {}).get("animal") == k["animal"] for k in mine(s3))

        # top-view orientation (display only, per house): 8 options vs the Python reference on known points, edge labels
        house = sg["house"]
        refs = data["meta"]["house_refs"][house]
        phi, C0, pole = refs["ridge_deg"], refs["centre"], refs["pole"]
        posd = [q for q in sg["wiser"]["positions"] if q.get("along_in") is not None]

        def topview():
            return c.ev("(() => { const v = document.getElementById('topview'); if (!v) return null;"
                        " const r = v.querySelector('rect.pole'); const cs = Array.from(v.querySelectorAll('circle.pos'));"
                        " return {cx: +v.dataset.cx, cy: +v.dataset.cy, S: +v.dataset.scale, rot: +v.dataset.rot, mirror: v.dataset.mirror === '1',"
                        " pole: r ? [+r.dataset.x, +r.dataset.y] : null, pos: Object.fromEntries(cs.map(e => [e.dataset.animal, [+e.getAttribute('cx'), +e.getAttribute('cy')]])),"
                        " edges: Object.fromEntries(Array.from(v.querySelectorAll('text.edge')).map(e => [e.dataset.side, e.textContent])),"
                        " sel: (document.getElementById('orient-sel') || {}).value}; })()")

        def expect(tv, dx, dy, rot, mir):
            a, b = orient_view(dx, dy, rot, mir)
            return tv["cx"] + a * tv["S"], tv["cy"] - b * tv["S"]

        def setsel(v):
            c.ev("(() => { const e = document.getElementById('orient-sel'); e.value = " + json.dumps(v) + "; e.dispatchEvent(new Event('change')); })(); 1")
            time.sleep(0.2)

        tv0 = topview()
        okk["orientation_default_paddock"] = tv0 is not None and tv0["rot"] == 0 and not tv0["mirror"] and tv0["sel"] == "0|0" and \
            tv0["edges"] == {"right": "toward x = 480 wall", "left": "toward x = 0 wall", "top": "toward y = 240 (row C)", "bottom": "toward y = 0 (row A)"}
        errs, labs = [], []
        wall = {(1, 0): "toward x = 480 wall", (-1, 0): "toward x = 0 wall", (0, 1): "toward y = 240 (row C)", (0, -1): "toward y = 0 (row A)"}
        for rot in (0, 90, 180, 270):
            for mir in (False, True):
                setsel(f"{rot}|{int(mir)}")
                tv = topview()
                ex = expect(tv, pole["xy"][0] - C0[0], pole["xy"][1] - C0[1], rot, mir)
                errs.append(max(abs(ex[0] - tv["pole"][0]), abs(ex[1] - tv["pole"][1])))
                for q in posd:
                    dx, dy = house_to_paddock(q["along_in"], q["across_in"], phi)
                    ex = expect(tv, dx, dy, rot, mir)
                    errs.append(max(abs(ex[0] - tv["pos"][q["animal"]][0]), abs(ex[1] - tv["pos"][q["animal"]][1])))
                want = {}
                for v, name in wall.items():
                    a, b = orient_view(v[0], v[1], rot, mir)
                    want["right" if a > 0.5 else "left" if a < -0.5 else "top" if b > 0.5 else "bottom"] = name
                labs.append(tv["edges"] == want and tv["rot"] == rot and tv["mirror"] == mir)
        res["orientation_max_err_px"] = round(max(errs), 4)
        res["orientation_points_checked"] = len(errs)
        okk["orientation_8_options_transform"] = max(errs) < 0.05 and all(labs) and len(labs) == 8
        setsel("90|1")                      # leave a non-default choice for the persistence / export checks
        okk["orientation_stored"] = (st().get("orientation_by_house", {}).get(house, {}).get("rot_deg") == 90
                                     and st()["orientation_by_house"][house]["mirror"] is True and bool(st()["orientation_by_house"][house]["chosen_at"]))
        # after the reveal: add D, relabel C (edited after the reveal), delete A (kept, flagged)
        xd, yd = scr(0.5 * W, 0.25 * H)
        before = {k["click_id"] for k in mine(st())}
        click(xd, yd)
        digit("4")
        ids["D"] = ({k["click_id"] for k in mine(st())} - before).pop()
        click(*scr(*c_final))
        digit("5")
        click(*scr(*a_pos))
        key("Backspace", "Backspace", 8)
        s4 = {k["click_id"]: k for k in mine(st(), all_=True)}
        okk["after_reveal_flags"] = (s4[ids["D"]]["before_reveal"] is False and s4[ids["C"]]["animal"] == "SF11"
                                     and s4[ids["C"]]["verdict_first"]["animal"] == "SF12" and s4[ids["C"]].get("edited_after_reveal") is True
                                     and s4[ids["A"]].get("deleted_after_reveal") is True and s4[ids["A"]]["verdict_first"]["animal"] == "SF07")
        # export JSON + CSV (blobs intercepted)
        c.ev("window.__blobs = []; URL.createObjectURL = b => { window.__blobs.push(b); return 'blob:x'; }; 1")
        c.ev("document.getElementById('bjson').click(); document.getElementById('bcsv').click(); 1")
        time.sleep(0.3)
        js = json.loads(c.ev("window.__blobs[0].text()", await_=True))
        csv_txt = c.ev("window.__blobs[1].text()", await_=True)
        ex = {k["click_id"]: k for k in js["clicks"]}
        sgx = next(s for s in js["segments"] if s["segment_id"] == sid)
        rows = list(__import__("csv").DictReader(csv_txt.splitlines()))
        crow = {r["click_id"]: r for r in rows if r["record"] == "click"}
        srow = next(r for r in rows if r["record"] == "segment" and r["segment_id"] == sid)
        okk["export_flags"] = (bool(sgx["revealed_at"]) and srow["revealed_at"] == sgx["revealed_at"] and ex[ids["D"]]["before_reveal"] is False
                               and ex[ids["A"]]["before_reveal"] is True and crow[ids["D"]]["before_reveal"] == "false"
                               and crow[ids["C"]]["before_reveal"] == "true" and crow[ids["C"]]["first_animal"] == "SF12" and crow[ids["C"]]["animal"] == "SF11"
                               and crow[ids["A"]]["deleted_after_reveal"] == "true"
                               and all(crow[k]["legacy"] == "true" and crow[k]["before_reveal"] == "true" for k in ex if ex[k].get("legacy"))
                               and len(crow) == len(js["clicks"]) and sum(r["record"] == "segment" for r in rows) == len(data["segments"]))
        ob = js.get("orientation_by_house", {})
        okk["orientation_exported"] = (ob.get(house, {}).get("rot_deg") == 90 and ob[house].get("mirror") is True and bool(ob[house].get("chosen_at"))
                                       and set(ob) == {q["house"] for q in data["segments"]})
        res["export"] = {"n_clicks": len(js["clicks"]), "n_legacy": sum(bool(k.get("legacy")) for k in js["clicks"]), "segment": sgx,
                         "orientation_by_house": ob}
        reload()
        go(seg_index)
        okk["reveal_persists"] = "Roster" in c.ev("document.getElementById('side').innerText")
        tv = topview()
        ex = expect(tv, pole["xy"][0] - C0[0], pole["xy"][1] - C0[1], 90, True)
        okk["orientation_persists_after_reload"] = (tv["sel"] == "90|1" and tv["rot"] == 90 and tv["mirror"]
                                                    and max(abs(ex[0] - tv["pole"][0]), abs(ex[1] - tv["pole"][1])) < 0.05)
    finally:
        if c is not None:
            c.close()
        _close_chrome(p, bws)
    res["checks"] = okk
    res["verdict"] = "PASS" if all(okk.values()) else "FAIL"
    return res


# ----------------------------------------------------------------------------------------------- self-test
def selftest() -> int:
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    try:
        import av  # noqa: F401
        import cv2  # noqa: F401
    except ImportError:
        print("[SKIP] needs PyAV + OpenCV (cv env)")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run = tmp / "run"
        (run / "scan" / "CH07").mkdir(parents=True)
        day = "2026-09-10"
        vid = tmp / "video" / day / "CH07"
        vid.mkdir(parents=True)
        vp = vid / "CH07_2026-09-10_12-00-00_to_12-00-40.mp4"
        if not ip._synthetic_video(vp, 10.3, 18.75, dur=40.0):
            print("[SKIP] could not write a synthetic video")
            return 0
        csvp = run / "scan" / "CH07" / (vp.stem + ".csv")
        ip.scan_file(vp.as_posix(), "2026-09-10T12:00:00", csvp.as_posix())
        pd.DataFrame([{"set": "scan", "camera": "CH07", "file": vp.as_posix(), "start": "2026-09-10 12:00:00", "csv": csvp.as_posix()}]).to_csv(
            run / "scan_inventory.csv", index=False)
        (run / "colour_threshold.json").write_text(json.dumps({"thr": 1.0}), encoding="utf-8")
        pd.DataFrame([{"segment_id": "CH07_20260910_120010", "camera": "CH07", "house": "house_2", "start": "2026-09-10 12:00:10.300",
                       "end": "2026-09-10 12:00:18.750", "duration_s": 8.45, "mid": "2026-09-10 12:00:14.525", "n_colour_keyframes": 4,
                       "median_chroma": 100.0, "flags": "", "lid_event": "", "log_row": None, "log_kind": ""}]).to_csv(run / "colour_segments.csv", index=False)
        # tracks: SF07, SF09 in house_2 at different ends, SF08 outside; states from the WISER phase on the synthetic tracks
        rois = ip.load_rois()
        root = tmp / "tracks"
        for lab, (dx, dy) in {"SF07": (0, 8), "SF09": (0, -8), "SF08": (-150, -80)}.items():
            t_local = pd.date_range(f"{day} 11:55:00", f"{day} 12:05:00", freq="250ms")
            x = rois["house_2"]["x"] + dx + np.random.default_rng(1).normal(0, 1.5, len(t_local))
            y = rois["house_2"]["y"] + dy + np.random.default_rng(2).normal(0, 1.5, len(t_local))
            t_ms = ((t_local.tz_localize(ip.TZ).tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(milliseconds=1)).to_numpy(np.int64)
            (root / lab).mkdir(parents=True, exist_ok=True)
            pd.DataFrame({"t_ms": t_ms, "t_al_ms": t_ms, "shortid": 1, "x_raw": x, "y_raw": y, "anchors_used": 8, "valid": 1, "m_handling": 0,
                          "m_silence": 0, "m_tag_validity": 0, "m_adc_lane": 0, "m_off_animal": 0, "x": x, "y": y, "vx": 0.0, "vy": 0.0,
                          "method": "V3", "imu_ok": 1, "imu_state": 1, "zupt": 0, "loco_boost": 0}).to_csv(root / lab / "20260910.csv.gz", index=False)
        ip.phase_wiser(run, track_root=root, t0=datetime(2026, 9, 10, 11, 55), t1=datetime(2026, 9, 10, 12, 5), labels=("SF07", "SF08", "SF09"),
                       days=[day])
        # close-ups: two tiny synthetic clips named like the phone files
        cs = tmp / "downloads"
        cs.mkdir()
        for lab in ("SF07", "SF08"):
            ip._synthetic_video(cs / f"{lab}.mp4", 0, 1, dur=2.0)
            shutil.move(str(cs / f"{lab}.mp4"), str(cs / f"{lab}.MOV"))

        class FakeCorr:
            def correction(self, cam, t):
                return np.array([[1.0, 0.0, 2.5], [0.0, 1.0, -1.0]]), {"segment": 27, "lid_open": False, "flag": "ok",
                                                                       "target_frame": "09-04 12:00 (user-labelled frame)", "used": "median"}
        chk = build(run, closeup_src=cs, track_root=root, corrections=FakeCorr())
        data = json.loads((run / "identity_page" / "page_data.json").read_text(encoding="utf-8"))
        s0 = data["segments"][0]
        fr = {f["kind"]: f for f in s0["frames"]}
        rec("three frames per segment, colour at the middle, IR at +6 / +15 s", set(fr) == {"colour_mid", "ir_p06", "ir_p15"}
            and fr["colour_mid"]["time"] == "2026-09-10 12:00:14.550" and fr["ir_p06"]["time"] == "2026-09-10 12:00:24.750"
            and fr["ir_p15"]["time"] == "2026-09-10 12:00:33.750", str({k: v.get("time") for k, v in fr.items()}))
        rec("frame index counted from the key frame (colour mid = frame 291)", fr["colour_mid"]["frame_idx"] == 291, str(fr["colour_mid"]["frame_idx"]))
        rec("mode check: colour frame >= thr, IR frames < thr", all(f["mode_check"] == "ok" for f in s0["frames"]))
        rec("lid segment and correction stored per frame", fr["ir_p15"]["lid"]["lid_segment"] == 27 and fr["colour_mid"]["lid"]["B_frame_to_ref"][0][2] == 2.5)
        w = s0["wiser"]
        rec("WISER roster: SF07 + SF09 in house_2, SF08 outside", sorted(w["roster"]) == ["SF07", "SF09"] and w["out"] == ["SF08"], str(w))
        p = {q["animal"]: q for q in w["positions"]}
        rec("WISER positions: the two animals ~16 in apart in the house frame, SE < 0.5 in",
            abs(np.hypot(p["SF07"]["along_in"] - p["SF09"]["along_in"], p["SF07"]["across_in"] - p["SF09"]["across_in"]) - 16 * 0.9634) < 1.0
            and p["SF07"]["along_se_in"] < 0.5)
        rec("close-ups transcoded, originals unchanged", all(c.get("src_unchanged") for c in data["closeups"] if c["animal"] in ("SF07", "SF08"))
            and (run / "identity_page" / "closeups" / "SF07.mp4").exists())
        rec("page check: paths resolve, no network URL, no pre-filled identity", chk["verdict"] == "PASS" and not chk["missing"], str(chk))
        txt = (run / "identity_page" / "index.html").read_text(encoding="utf-8")
        rec("no identity pre-filled in the page data", '"clicks"' not in txt.split("<script>")[0] and "animal\": \"SF" not in json.dumps(data["segments"][0]["frames"]))
        node = shutil.which("node")
        if node:
            js = tmp / "page.js"
            js.write_text(PAGE_JS, encoding="utf-8")
            r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
            rec("page script parses (node --check)", r.returncode == 0, r.stderr[-300:])
        else:
            print("[SKIP] node not on PATH: page script not syntax-checked")
        # check_page catches a missing file and a network URL
        bad = tmp / "bad"
        bad.mkdir()
        (bad / "index.html").write_text('<script id="page-data" type="application/json">{"segments": [], "closeups": []}</script>'
                                        '<img src="frames/x.jpg"><a href="https://example.org/a">x</a>', encoding="utf-8")
        cb = check_page(bad)
        rec("page check flags a missing file and a network URL", cb["verdict"] == "FAIL" and cb["missing"] == ["frames/x.jpg"] and cb["network_urls"])
        # legend from the identity CSV (2026-10-10 correction): the user's identifying colour per animal, Notion for reference
        lg = {r["animal"]: r for r in data["legend"]}
        want = {"SF07": "green", "SF08": "red", "SF09": "blue", "SF10": "black", "SF11": "white (looks grey)", "SF12": "yellow"}
        rec("legend built from the CSV: identifying colours, Notion coban kept, notes on SF09 / SF10 / SF12, source line",
            {a: r["id_colour"] for a, r in lg.items()} == want and lg["SF09"]["coban_notion"] == "pink/black/brown"
            and all(bool(lg[a]["id_colour_note"]) == (a in ("SF09", "SF10", "SF12")) for a in want)
            and data["meta"]["legend_source"] == LEGEND_SOURCE and "3058" in lg["SF11"]["tag"] and "305a" in lg["SF11"]["tag"])
        # refresh: legend from a changed CSV, same page path, page_version / run (= the localStorage key) and frames kept
        alt = tmp / "ids.csv"
        ids = pd.read_csv(IDENTITY_CSV, dtype=str)
        ids.loc[ids.animal == "SF10", "id_colour"] = "grey"
        ids.to_csv(alt, index=False)
        key0 = (data["meta"]["page_version"], data["meta"]["run"])
        rc = refresh_legend(run, alt)
        d2 = json.loads((run / "identity_page" / "page_data.json").read_text(encoding="utf-8"))
        rec("refresh-legend: new legend, same localStorage key, frames untouched, segments unchanged, page check PASS",
            {r["animal"]: r["id_colour"] for r in d2["legend"]}["SF10"] == "grey" and (d2["meta"]["page_version"], d2["meta"]["run"]) == key0
            and rc["frames_untouched"] and d2["segments"] == data["segments"] and rc["verdict"] == "PASS")
        bad_ids = ids.drop(columns=["id_colour"])
        bad_ids.to_csv(alt, index=False)
        try:
            legend_from_csv(alt)
            raised = False
        except ValueError:
            raised = True
        rec("legend refuses a CSV without id_colour", raised)
        # orientation reference maths (display only): paddock default, rotation counter-clockwise, mirror flips x; house frame inverse
        hf = ip.to_house_frame([[342.4 + 3.0, 117.7 - 5.0]], {"centre": (342.4, 117.7), "ridge_deg": 92.0})[0]
        rec("orientation maths: (1, 0) -> (1, 0) / (0, 1) at 90 / (-1, 0) mirrored; house_to_paddock inverts to_house_frame",
            orient_view(1, 0, 0, False) == (1, 0) and orient_view(1, 0, 90, False) == (0, 1) and orient_view(1, 0, 0, True) == (-1, 0)
            and orient_view(0, 1, 270, True) == (1, 0) and np.allclose(house_to_paddock(hf[0], hf[1], 92.0), (3.0, -5.0))
            and set(data["meta"]["house_refs"]) == {"house_1", "house_2"} and data["meta"]["house_refs"]["house_2"]["pole"]["name"] == "B3")
        # the click page driven in headless Chrome: select / move / delete / undo / relabel / nudge, persistence, blind reveal, export
        if CHROME.exists():
            seed = {"clicks": [{"segment_id": s0["segment_id"], "camera": "CH07", "house": "house_2", "frame_kind": "ir_p06", "u_px": 50.0, "v_px": 60.0,
                                "animal": "SF10", "confidence": "sure", "clicked_at": "2026-10-10T20:00:00Z"}], "segments": {}}
            ui = ui_check(run / "identity_page", tmp / "chrome_profile", 0, seed)
            rec("browser: 3 markers, select 8 px off centre (no new), drag, Delete, right-click, undo, relabel, nudge + undo / redo, "
                "constant marker size, reload persists, WISER hidden until reveal, flags exported, legacy migrated, "
                "top-view orientation (8 options vs the Python reference, edge labels, stored, exported, persists)",
                ui["verdict"] == "PASS", str({k: v for k, v in ui["checks"].items() if not v}) + f" right-click native {ui.get('right_click_native_contextmenu')}")
        else:
            print("[SKIP] Chrome not found: browser UI check not run")
    print(("PASS" if ok else "FAIL") + " - inbox_identity_page self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run", default=None)
    ap.add_argument("--closeups", default=str(CLOSEUP_SRC))
    ap.add_argument("--refresh-legend", action="store_true",
                    help="re-render the page (legend from the identity CSV + the current page code) at the same path; no decoding")
    ap.add_argument("--ui-check", action="store_true", help="drive the run's page in headless Chrome (throwaway profile)")
    ap.add_argument("--profile", default=None, help="Chrome profile folder for --ui-check (default: a new temporary one)")
    ap.add_argument("--seg", type=int, default=1, help="segment index for --ui-check")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.run:
        ap.error("--run <inbox_p0 run dir> or --selftest")
    if args.ui_check:
        prof = Path(args.profile) if args.profile else Path(tempfile.mkdtemp(prefix="inbox_ui_"))
        res = ui_check(Path(args.run) / "identity_page", prof, args.seg)
        print(json.dumps(res, indent=1, default=str))
        return 0 if res["verdict"] == "PASS" else 1
    chk = refresh_legend(Path(args.run)) if args.refresh_legend else build(Path(args.run), Path(args.closeups))
    return 0 if chk["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
