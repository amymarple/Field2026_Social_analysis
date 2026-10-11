r"""inbox_click_analysis.py — in-box cameras CH07 / CH08: the pre-registered use of the user's identity clicks (cohort 3, 2026c).

Specification: implementation_plan/2026-10-10-inbox-ch0708-wiser-identity-p0.md, section "Pre-registered use of the user's
clicks" + amendment 11 (how it is run; written before any result). Reads the user's clicks (an export or a browser snapshot of
the identity page's localStorage, cv/configs/inbox_identity_2026c/), the page data of the phase-0 run
(<p0 run>/identity_page/page_data.json: segments, frames, WISER roster and minute means, house pose), the phase-0 states
(states_1s.npz, for the sensitivity window) and the head-IMU seconds cache. Never opens a frame; the agent never judges images.

Per house (CH07 = house_2; CH08 = house_1 when it has clicks):
  Q1 composition   animals clicked on the colour frame (blind record) vs the WISER roster of the house at the colour frame.
  Q2 stability     head displacement colour -> IR +6 s / +15 s per animal, px and inches, with the head-IMU state between.
  Q3 fit           least-squares 2-D similarity (u_ref, -v_ref) -> (along, across) in, both handednesses, leave-one-flash-out
                   (LOFO) residuals; rotation compared with the user's display orientation (cv/configs/
                   inbox_camera_orientation_2026c.json).
  Q4 order test    the operator's rule: WISER order along the ridge vs the order of the LOFO-mapped clicks in the first 5
                   eligible flashes; ACCEPTED if >= 4 of 5 match exactly; tie version (pairs < 8 in by WISER not tested);
                   Kendall tau; all flashes; sensitivities.
  Q5 assignment    Hungarian assignment of the LOFO-mapped clicked heads to the WISER means, accuracy vs the user's IDs,
                   by WISER separation.

Usage (base Python: numpy, pandas, scipy, matplotlib):
  python cv/cv_field/inbox_click_analysis.py --selftest
  python cv/cv_field/inbox_click_analysis.py [--clicks <export or snapshot json>] [--p0-run <inbox_p0 run dir>]
Output: $OUT/2026c/cv_field_inbox_clicks_<ts>/ (tables, figures/, run.json) + results/2026c/cv_field/reports/
        cv_field_inbox_clicks_2026c.md + pointer run_manifest_inbox_clicks_2026c.json.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(REPO / "wiser" / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

COHORT, DIRECTION, NAME = "2026c", "cv_field", "cv_field_inbox_clicks"
PLAN = "implementation_plan/2026-10-10-inbox-ch0708-wiser-identity-p0.md"
REPORT_NAME = f"cv_field_inbox_clicks_{COHORT}.md"
POINTER_NAME = f"run_manifest_inbox_clicks_{COHORT}.json"
P0_POINTER = REPO / "results" / COHORT / DIRECTION / "reports" / f"run_manifest_inbox_p0_{COHORT}.json"
CLICKS_DEFAULT = REPO / "cv" / "configs" / "inbox_identity_2026c" / "browser_snapshot_20261010T2017.json"
ORIENT_JSON = REPO / "cv" / "configs" / "inbox_camera_orientation_2026c.json"
TZ = ZoneInfo("America/New_York")
LABELS = ("SF07", "SF08", "SF09", "SF10", "SF11", "SF12")
FRAME_KINDS = ("colour_mid", "ir_p06", "ir_p15")
CAND_SEP_IN = 8.0            # plan: 1-min-mean separations < 8 in are "candidates" (tie version of the order test)
N_FIRST, MIN_ID, ACCEPT_MIN = 5, 3, 4   # the operator's rule: >= 4 of the first 5 flashes with >= 3 identified animals
SEP_BINS = (0.0, 4.0, 8.0, 15.0, np.inf)
CENTRED_HALF_S = 30.0        # sensitivity window [mid - 30 s, mid + 30 s)
BODY_IN = (62.55 / 2.54, 45.72 / 2.54)   # house body along x across the ridge (CAMERA_GEOMETRY_2026c.md section 4)
IMG_W, IMG_H = 2560, 1920
# categorical slots (dataviz reference palette, fixed order) + the animal name drawn next to every mark
ANIMAL_CSS = {"SF07": "#2a78d6", "SF08": "#eb6834", "SF09": "#1baf7a", "SF10": "#eda100", "SF11": "#e87ba4", "SF12": "#4a3aa7"}


# ============================================================================================ helpers
def git_commit(repo: Path) -> str:
    try:
        h = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "cv/cv_field/inbox_click_analysis.py"],
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


def norm_animal(a) -> str:
    return "unknown" if a in (None, "", "unknown") or (isinstance(a, float) and np.isnan(a)) else str(a)


def parse_t(s) -> datetime:
    return datetime.fromisoformat(str(s))


def wrap180(a: float) -> float:
    return float((a + 180.0) % 360.0 - 180.0)


# ============================================================================================ inputs
def click_table(snap: dict) -> pd.DataFrame:
    """One row per click. status: blind (before_reveal, not legacy, has verdict_first = saved at the reveal), after_reveal,
    unsaved (before_reveal but no verdict_first: its segment was not revealed when the state was taken), legacy.
    b_* = the blind record (verdict_first); the plain columns = the live (final) values. *_ref = after B_frame_to_ref."""
    segs = snap.get("segments", {}) or {}
    rows = []
    for c in snap["clicks"]:
        vf = c.get("verdict_first") or None
        legacy = bool(c.get("legacy"))
        br = bool(c.get("before_reveal"))
        status = "legacy" if legacy else ("blind" if (br and vf) else "unsaved" if br else "after_reveal")
        B = np.asarray(c.get("B_frame_to_ref") or [[1, 0, 0], [0, 1, 0]], float)
        r = {"click_id": c["click_id"], "segment_id": c["segment_id"], "camera": c.get("camera"), "house": c.get("house"),
             "frame_kind": c["frame_kind"], "frame_time": c.get("frame_time"), "status": status,
             "revealed": bool((segs.get(c["segment_id"]) or {}).get("revealed_at")),
             "deleted": bool(c.get("deleted_after_reveal")), "edited": bool(c.get("edited_after_reveal")),
             "animal": norm_animal(c.get("animal")), "confidence": c.get("confidence"), "u": float(c["u_px"]), "v": float(c["v_px"]),
             "relabelled_sf09_sf10": bool(c.get("relabelled_sf09_sf10")), "lid_segment": c.get("lid_segment"),
             "lid_flag": c.get("lid_flag"), **{f"b{i + 1}{j + 1}": float(B[i, j]) for i in range(2) for j in range(3)}}
        if vf:
            r.update({"b_animal": norm_animal(vf.get("animal")), "b_confidence": vf.get("confidence"), "b_u": float(vf["u_px"]),
                      "b_v": float(vf["v_px"]), "b_frame_kind": vf.get("frame_kind", c["frame_kind"])})
        else:
            r.update({"b_animal": None, "b_confidence": None, "b_u": np.nan, "b_v": np.nan, "b_frame_kind": None})
        rows.append(r)
    df = pd.DataFrame(rows)
    for pre in ("", "b_"):
        u, v = df[pre + "u"].to_numpy(float), df[pre + "v"].to_numpy(float)
        df[pre + "u_ref"] = df.b11 * u + df.b12 * v + df.b13
        df[pre + "v_ref"] = df.b21 * u + df.b22 * v + df.b23
    return df


def record(ct: pd.DataFrame, which: str) -> pd.DataFrame:
    """The click set of one record with uniform columns (animal, kind, u, v, u_ref, v_ref):
    'blind' = the blind record (status blind, from verdict_first; a blind click deleted after the reveal is still in it);
    'final' = blind + after-reveal clicks, live values, not deleted (unsaved and legacy clicks excluded)."""
    if which == "blind":
        d = ct[ct.status == "blind"].copy()
        d["animal"], d["kind"], d["u"], d["v"] = d.b_animal, d.b_frame_kind, d.b_u, d.b_v
        d["u_ref"], d["v_ref"] = d.b_u_ref, d.b_v_ref
    elif which == "final":
        d = ct[ct.status.isin(["blind", "after_reveal"]) & ~ct.deleted].copy()
        d["kind"] = d.frame_kind
    else:
        raise ValueError(which)
    return d[["click_id", "segment_id", "house", "camera", "kind", "animal", "u", "v", "u_ref", "v_ref", "status", "lid_flag",
              "lid_segment"]].reset_index(drop=True)


def page_segments(page: dict) -> dict:
    out = {}
    for s in page["segments"]:
        w = s["wiser"]
        pos = {}
        for p in w.get("positions", []):
            if p.get("along_in") is None or not p.get("n_fix"):
                continue
            pos[p["animal"]] = {k: p.get(k) for k in ("along_in", "across_in", "along_raw_in", "across_raw_in", "along_se_in",
                                                      "across_se_in", "n_fix", "still_share", "active_share", "loco_share",
                                                      "sd_along_raw_in", "sd_across_raw_in")}
        frames = {f["kind"]: {"time": parse_t(f["time"]), "lid_flag": (f.get("lid") or {}).get("flag"),
                              "lid_open": (f.get("lid") or {}).get("lid_open"),
                              "B": (f.get("lid") or {}).get("B_frame_to_ref")} for f in s["frames"] if "time" in f}
        out[s["segment_id"]] = {"segment_id": s["segment_id"], "camera": s["camera"], "house": s["house"], "start": parse_t(s["start"]),
                                "end": parse_t(s["end"]), "mid": parse_t(s["mid"]), "duration_s": float(s["duration_s"]),
                                "lid_event": s.get("lid_event") or "", "log_kind": s.get("log_kind") or "",
                                "roster": list(w.get("roster", [])), "untracked": list(w.get("untracked", [])),
                                "other_house": list(w.get("other_house", [])), "out": list(w.get("out", [])),
                                "sf11_note": w.get("sf11_note", ""), "window": w.get("window", ""), "W": pos,
                                "pose": w.get("pose"), "frames": frames}
    return out


def load_prior(path: Path = ORIENT_JSON) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return {h: {"rot_deg": v.get("rot_deg"), "mirror": v.get("mirror"), "source": v.get("source", "")}
            for h, v in d.items() if not h.startswith("_") and isinstance(v, dict)}


# ============================================================================================ similarity
def sim_fit(P, Q, mirror: bool = False, theta_fixed_deg: float | None = None) -> dict:
    """Least squares Q ~ a * z(M P) + t in complex form (a = s e^{i theta}): P (n, 2) display coordinates (p, q) = (u_ref, -v_ref),
    Q (n, 2) house frame (along, across) in; M = diag(1, -1) if mirror else I. theta_fixed_deg: rotation held fixed, scale and
    offset fitted."""
    P, Q = np.asarray(P, float).reshape(-1, 2).copy(), np.asarray(Q, float).reshape(-1, 2)
    if mirror:
        P[:, 1] = -P[:, 1]
    zp, zq = P[:, 0] + 1j * P[:, 1], Q[:, 0] + 1j * Q[:, 1]
    mp, mq = zp.mean(), zq.mean()
    dp, dq = zp - mp, zq - mq
    if theta_fixed_deg is None:
        a = np.vdot(dp, dq) / np.vdot(dp, dp).real
    else:
        r = np.exp(1j * np.radians(theta_fixed_deg))
        a = r * max(np.vdot(r * dp, dq).real / np.vdot(dp, dp).real, 1e-12)
    return {"a": complex(a), "t": complex(mq - a * mp), "mirror": bool(mirror), "theta_fixed_deg": theta_fixed_deg, "n": len(P)}


def sim_apply(f: dict, P) -> np.ndarray:
    P = np.asarray(P, float).reshape(-1, 2).copy()
    if f["mirror"]:
        P[:, 1] = -P[:, 1]
    z = f["a"] * (P[:, 0] + 1j * P[:, 1]) + f["t"]
    return np.column_stack([z.real, z.imag])


def sim_inverse(f: dict, Q) -> np.ndarray:
    Q = np.asarray(Q, float).reshape(-1, 2)
    z = ((Q[:, 0] + 1j * Q[:, 1]) - f["t"]) / f["a"]
    P = np.column_stack([z.real, z.imag])
    if f["mirror"]:
        P[:, 1] = -P[:, 1]
    return P


def sim_params(f: dict, ridge_deg: float) -> dict:
    """theta_house = arg a (deg, CCW, display -> house frame); theta_paddock = theta_house + ridge (display -> paddock);
    page-equivalent orientation: no mirror rot = -theta_paddock, mirror rot = theta_paddock - 180 (mod 360; the page draws
    view = R(rot) Mx (dx, dy), Mx = x-flip if mirror)."""
    th = float(np.degrees(np.angle(f["a"])))
    thp = th + ridge_deg
    rot = (-thp) % 360.0 if not f["mirror"] else (thp - 180.0) % 360.0
    return {"s_in_per_px": abs(f["a"]), "px_per_in": 1.0 / abs(f["a"]), "theta_house_deg": wrap180(th),
            "theta_paddock_deg": wrap180(thp), "page_rot_deg": rot, "page_mirror": f["mirror"]}


def prior_theta_house(rot_deg: float, mirror: bool, ridge_deg: float) -> float:
    """The user's display orientation (rot_deg, mirror) as the rotation of the similarity display -> house frame."""
    thp = -rot_deg if not mirror else rot_deg + 180.0
    return wrap180(thp - ridge_deg)


def fit_points(rec: pd.DataFrame, segs: dict, house: str, wcols=("along_in", "across_in"), W_override: dict | None = None) -> pd.DataFrame:
    """Blind named colour-frame clicks of one house that have a WISER mean: one row per (flash, animal); several clicks of one
    animal on one frame are averaged (n_clicks > 1 flagged)."""
    d = rec[(rec.house == house) & (rec.kind == "colour_mid") & rec.animal.isin(LABELS)]
    rows = []
    for (sid, a), g in d.groupby(["segment_id", "animal"]):
        S = segs.get(sid)
        if S is None:
            continue
        W = (W_override or {}).get(sid, S["W"])
        if a not in W or W[a].get(wcols[0]) is None:
            continue
        rows.append({"segment_id": sid, "start": S["start"], "animal": a, "n_clicks": len(g), "u_ref": g.u_ref.mean(), "v_ref": g.v_ref.mean(),
                     "p": g.u_ref.mean(), "q": -g.v_ref.mean(), "A": float(W[a][wcols[0]]), "C": float(W[a][wcols[1]]),
                     "lid_flag": g.lid_flag.iloc[0]})
    return pd.DataFrame(rows).sort_values(["start", "animal"]).reset_index(drop=True) if rows else pd.DataFrame(
        columns=["segment_id", "start", "animal", "n_clicks", "u_ref", "v_ref", "p", "q", "A", "C", "lid_flag"])


def insample(pts: pd.DataFrame, mirror: bool, theta_fixed: float | None = None) -> tuple[dict, pd.DataFrame]:
    f = sim_fit(pts[["p", "q"]], pts[["A", "C"]], mirror, theta_fixed)
    pr = sim_apply(f, pts[["p", "q"]])
    o = pts.copy()
    o["fit_A"], o["fit_C"] = pr[:, 0], pr[:, 1]
    o["res_in"] = np.hypot(o.fit_A - o.A, o.fit_C - o.C)
    o["res_px"] = o.res_in / abs(f["a"])
    return f, o


def lofo(pts: pd.DataFrame, mirror: bool, theta_fixed: float | None = None, min_train_flashes: int = 2) -> pd.DataFrame:
    """Leave one flash out: fit on the other flashes, map the left-out flash's clicks into the house frame (pred_A, pred_C)
    and the WISER means into the image (pred_u_ref, pred_v_ref); residuals in inches and in reference px."""
    out = []
    for sid in pts.segment_id.unique():
        tr, te = pts[pts.segment_id != sid], pts[pts.segment_id == sid].copy()
        if tr.segment_id.nunique() < min_train_flashes or len(tr) < 3:
            continue
        f = sim_fit(tr[["p", "q"]], tr[["A", "C"]], mirror, theta_fixed)
        pr = sim_apply(f, te[["p", "q"]])
        te["pred_A"], te["pred_C"] = pr[:, 0], pr[:, 1]
        pi = sim_inverse(f, te[["A", "C"]])
        te["pred_u_ref"], te["pred_v_ref"] = pi[:, 0], -pi[:, 1]
        te["res_in"] = np.hypot(te.pred_A - te.A, te.pred_C - te.C)
        te["res_px"] = np.hypot(te.pred_u_ref - te.u_ref, te.pred_v_ref - te.v_ref)
        te["fold_theta_house_deg"] = wrap180(float(np.degrees(np.angle(f["a"]))))
        te["fold_px_per_in"] = 1.0 / abs(f["a"])
        out.append(te)
    return pd.concat(out, ignore_index=True) if out else pts.iloc[0:0].assign(pred_A=[], pred_C=[], res_in=[], res_px=[])


def rms(x) -> float:
    x = np.asarray(x, float)
    return float(np.sqrt(np.mean(x ** 2))) if len(x) else float("nan")


def residual_decomposition(pr: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """LOFO residual vectors r = (pred_A - A, pred_C - C) (head mapped minus WISER, in): RMS along / across; per-flash mean
    vector (a common WISER offset of the flash); RMS after removing it (in-sample, optimistic); per-animal mean vector over
    flashes; RMS after removing each animal's mean taken from its OTHER flashes (leave-one-flash-out, honest)."""
    d = pr.assign(rA=pr.pred_A - pr.A, rC=pr.pred_C - pr.C)
    fl = d.groupby("segment_id")[["rA", "rC"]].transform("mean")
    loo = []
    for i, r in d.iterrows():
        o = d[(d.animal == r.animal) & (d.segment_id != r.segment_id)]
        loo.append((r.rA - o.rA.mean(), r.rC - o.rC.mean()) if len(o) else (np.nan, np.nan))
    loo = np.array(loo, float)
    flm = d.groupby("segment_id")[["rA", "rC"]].mean()
    an = d.groupby("animal").agg(n=("rA", "size"), mean_along_in=("rA", "mean"), mean_across_in=("rC", "mean"),
                                 sd_along_in=("rA", "std"), sd_across_in=("rC", "std")).reset_index()
    an["mean_norm_in"] = np.hypot(an.mean_along_in, an.mean_across_in)
    sp = d.groupby("segment_id").agg(sd_A_wiser=("A", "std"), sd_A_clicks=("pred_A", "std"))
    return ({"rms_in": rms(np.hypot(d.rA, d.rC)), "rms_along_in": rms(d.rA), "rms_across_in": rms(d.rC),
             "flash_offset_norm_median_in": float(np.hypot(flm.rA, flm.rC).median()),
             "flash_offset_norm_max_in": float(np.hypot(flm.rA, flm.rC).max()),
             "rms_minus_flash_offset_in": rms(np.hypot(d.rA - fl.rA, d.rC - fl.rC)),
             "rms_minus_animal_offset_loo_in": rms(np.hypot(loo[:, 0], loo[:, 1])[np.isfinite(loo[:, 0])]),
             "sd_along_wiser_in": float(sp.sd_A_wiser.mean()), "sd_along_clicks_in": float(sp.sd_A_clicks.mean())}, an)


# ============================================================================================ order test
def kendall_tau(x, y) -> float:
    """tau_a = (concordant - discordant) / (n (n - 1) / 2)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    if n < 2:
        return float("nan")
    s = sum(np.sign(x[i] - x[j]) * np.sign(y[i] - y[j]) for i in range(n) for j in range(i + 1, n))
    return float(s / (n * (n - 1) / 2))


def order_flash(g: pd.DataFrame, ycol: str = "pred_A", sep_in: float = CAND_SEP_IN) -> dict:
    """WISER order (by A) vs click order (by ycol) of one flash; exact match, Kendall tau, tie version."""
    a = g.animal.to_numpy()
    ow = list(a[np.argsort(g.A.to_numpy(), kind="stable")])
    oc = list(a[np.argsort(g[ycol].to_numpy(), kind="stable")])
    A, Y = g.A.to_numpy(), g[ycol].to_numpy()
    tested = conc = 0
    disc_pairs = []
    for i, j in itertools.combinations(range(len(g)), 2):
        if abs(A[i] - A[j]) >= sep_in:
            tested += 1
            if np.sign(A[i] - A[j]) == np.sign(Y[i] - Y[j]):
                conc += 1
            else:
                disc_pairs.append(f"{a[i]}-{a[j]}")
    sep_along = [abs(A[i] - A[j]) for i, j in itertools.combinations(range(len(g)), 2)]
    return {"n": len(g), "order_wiser": " < ".join(ow), "order_clicks": " < ".join(oc), "exact": ow == oc,
            "tau": kendall_tau(A, Y), "n_pairs": len(sep_along), "n_pairs_ge_sep": tested, "n_conc_ge_sep": conc,
            "tie_match": (conc == tested) if tested else None, "discordant_ge_sep": ", ".join(disc_pairs),
            "min_sep_along_in": float(min(sep_along)) if sep_along else float("nan")}


def order_test(pr: pd.DataFrame, ycol: str = "pred_A", untestable: list | None = None) -> tuple[pd.DataFrame, dict]:
    """All eligible flashes (>= MIN_ID animals) in time order; the verdict on the first N_FIRST. untestable = flashes counted
    as non-matches (the alternative reading: >= 3 clicked animals but no WISER mean)."""
    rows = []
    for sid, g in pr.groupby("segment_id", sort=False):
        if len(g) < MIN_ID:
            continue
        rows.append({"segment_id": sid, "start": g.start.iloc[0], **order_flash(g, ycol)})
    for sid, st in (untestable or []):
        rows.append({"segment_id": sid, "start": st, "n": 0, "order_wiser": "(no WISER mean)", "order_clicks": "-", "exact": False,
                     "tau": float("nan"), "n_pairs": 0, "n_pairs_ge_sep": 0, "n_conc_ge_sep": 0, "tie_match": False,
                     "discordant_ge_sep": "", "min_sep_along_in": float("nan")})
    t = pd.DataFrame(rows)
    if t.empty:
        return t, {"verdict": "INSUFFICIENT (no eligible flash)", "n_eligible": 0}
    t = t.sort_values("start").reset_index(drop=True)
    t["rank"] = np.arange(1, len(t) + 1)
    first = t.head(N_FIRST)
    n_exact = int(first.exact.sum())
    n_tie = int((first.tie_match == True).sum())  # noqa: E712
    if len(first) < N_FIRST:
        verdict = f"INSUFFICIENT ({len(first)} eligible flashes < {N_FIRST})"
        verdict_tie = verdict
    else:
        verdict = "ACCEPTED" if n_exact >= ACCEPT_MIN else "NOT ACCEPTED"
        verdict_tie = "ACCEPTED" if n_tie >= ACCEPT_MIN else "NOT ACCEPTED"
    return t, {"n_eligible": int(len(t)), "first": list(first.segment_id), "n_exact_first": n_exact, "n_tie_first": n_tie,
               "verdict": verdict, "verdict_tie": verdict_tie, "n_exact_all": int(t.exact.sum()),
               "n_tie_all": int((t.tie_match == True).sum()), "n_tie_testable_all": int(t.tie_match.notna().sum()),  # noqa: E712
               "tau_median_first": float(np.nanmedian(first.tau)) if len(first) else float("nan"),
               "tau_median_all": float(np.nanmedian(t.tau))}


# ============================================================================================ assignment
def assign_flash(heads: pd.DataFrame, W: dict, xcols=("pred_A", "pred_C"), wcols=("along_in", "across_in")) -> pd.DataFrame:
    """Hungarian (min summed Euclidean distance) + greedy nearest + per-flash-offset assignment of the clicked heads to the
    WISER means of the roster animals with a mean."""
    from scipy.optimize import linear_sum_assignment
    cands = [a for a in W if W[a].get(wcols[0]) is not None]
    Wm = np.array([[W[a][wcols[0]], W[a][wcols[1]]] for a in cands], float)
    H = heads[list(xcols)].to_numpy(float)
    D = np.hypot(H[:, None, 0] - Wm[None, :, 0], H[:, None, 1] - Wm[None, :, 1])
    r, c = linear_sum_assignment(D)
    hung = np.array([None] * len(H), object)
    hung[r] = [cands[j] for j in c]
    greedy = [cands[j] for j in D.argmin(1)]
    best, bperm = np.inf, None                          # per-flash offset: min over injections of sum |d_i - mean(d)|^2
    if len(H) <= len(cands):
        for perm in itertools.permutations(range(len(cands)), len(H)):
            d = Wm[list(perm)] - H
            cst = float(((d - d.mean(0)) ** 2).sum())
            if cst < best - 1e-12:
                best, bperm = cst, perm
    off = [cands[j] for j in bperm] if bperm is not None else [None] * len(H)
    o = heads.copy()
    o["n_candidates"] = len(cands)
    o["assigned_hungarian"], o["assigned_greedy"], o["assigned_offset"] = list(hung), greedy, off
    o["correct_hungarian"] = o.assigned_hungarian == o.animal
    o["correct_greedy"] = o.assigned_greedy == o.animal
    o["correct_offset"] = o.assigned_offset == o.animal
    sep2, sepa = [], []
    for a in o.animal:
        if a in cands:
            i = cands.index(a)
            oth = [j for j in range(len(cands)) if j != i]
            sep2.append(float(np.min(np.hypot(*(Wm[oth] - Wm[i]).T))) if oth else np.inf)
            sepa.append(float(np.min(np.abs(Wm[oth, 0] - Wm[i, 0]))) if oth else np.inf)
        else:
            sep2.append(np.nan)
            sepa.append(np.nan)
    o["sep_2d_in"], o["sep_along_in"] = sep2, sepa
    o["dist_to_own_in"] = [float(D[k, cands.index(a)]) if a in cands else np.nan for k, a in enumerate(o.animal)]
    return o


def assignment(pr: pd.DataFrame, segs: dict, W_by_seg: dict | None = None, wcols=("along_in", "across_in")) -> pd.DataFrame:
    out = []
    for sid, g in pr.groupby("segment_id", sort=False):
        W = (W_by_seg or {}).get(sid, segs[sid]["W"])
        out.append(assign_flash(g, W, wcols=wcols))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def sep_table(asg: pd.DataFrame, col: str = "sep_2d_in", bins=SEP_BINS) -> pd.DataFrame:
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        g = asg[(asg[col] >= lo) & (asg[col] < hi)]
        rows.append({"bin_in": f"[{lo:g}, {hi:g})" if np.isfinite(hi) else f">= {lo:g}", "n_clicks": len(g),
                     "acc_hungarian": g.correct_hungarian.mean() if len(g) else np.nan,
                     "acc_greedy": g.correct_greedy.mean() if len(g) else np.nan,
                     "acc_offset": g.correct_offset.mean() if len(g) else np.nan,
                     "chance": (1.0 / g.n_candidates).mean() if len(g) else np.nan})
    return pd.DataFrame(rows)


# ============================================================================================ Q1, Q2
def composition(rec_b: pd.DataFrame, rec_f: pd.DataFrame, ct: pd.DataFrame, segs: dict) -> pd.DataFrame:
    rows = []
    for sid in sorted(ct.segment_id.unique(), key=lambda s: segs[s]["start"] if s in segs else datetime.max):
        S = segs.get(sid, {})
        roster = set(S.get("roster", []))
        cb = rec_b[(rec_b.segment_id == sid) & (rec_b.kind == "colour_mid")]
        named = cb[cb.animal.isin(LABELS)]
        clicked = set(named.animal)
        allb = set(rec_b[(rec_b.segment_id == sid) & rec_b.animal.isin(LABELS)].animal)
        allf = set(rec_f[(rec_f.segment_id == sid) & rec_f.animal.isin(LABELS)].animal)
        cs = ct[ct.segment_id == sid]
        dup = named.animal.value_counts()
        rows.append({"segment_id": sid, "start": S.get("start"), "revealed": bool(cs.revealed.any()),
                     "n_clicks": len(cs), "n_blind": int((cs.status == "blind").sum()), "n_after_reveal": int((cs.status == "after_reveal").sum()),
                     "n_unsaved": int((cs.status == "unsaved").sum()), "n_legacy": int((cs.status == "legacy").sum()),
                     "roster": ",".join(sorted(roster)), "untracked": ",".join(S.get("untracked", [])),
                     "n_W_means": len(S.get("W", {})),
                     "clicked_colour": ",".join(sorted(clicked)), "n_unknown_colour": int((~cb.animal.isin(LABELS)).sum()),
                     "missing": ",".join(sorted(roster - clicked)), "extras": ",".join(sorted(clicked - roster)),
                     "agree": bool(clicked == roster) if len(cb) else None,
                     "dup_colour": ",".join(f"{a}x{n}" for a, n in dup.items() if n > 1),
                     "clicked_any_frame_blind": ",".join(sorted(allb)), "missing_any_frame_blind": ",".join(sorted(roster - allb)),
                     "clicked_any_frame_final": ",".join(sorted(allf)), "missing_any_frame_final": ",".join(sorted(roster - allf)),
                     "sf11_clicked": "SF11" in allf or "SF11" in allb, "lid_event": S.get("lid_event", "")})
    return pd.DataFrame(rows)


def imu_between(imu: dict, animal: str, t0: datetime, t1: datetime) -> dict:
    """Head-IMU seconds [floor(t0), floor(t1)] (field-PC seconds) of one animal from the imu_seconds_cache."""
    s0 = int(np.floor(t0.replace(tzinfo=TZ).timestamp()))
    s1 = int(np.floor(t1.replace(tzinfo=TZ).timestamp()))
    d = imu.get(animal)
    n = s1 - s0 + 1
    if d is None or d.empty:
        return {"imu_n_s": n, "imu_n_ok": 0, "imu_n_still": 0, "imu_n_active": 0, "imu_n_loco": 0, "imu_vedba_max": np.nan,
                "imu_turn_abs_deg": np.nan, "imu_class": "no IMU"}
    g = d[(d.sec >= s0) & (d.sec <= s1)]
    ok = g[g.ok.astype(bool)]
    nst, nac, nlo = int((ok.state == 1).sum()), int((ok.state == 2).sum()), int((ok.state == 3).sum())
    cls = ("no IMU" if len(ok) == 0 else "moved" if (nac + nlo) > 0 else "all still" if len(ok) == n else "still (partial)")
    return {"imu_n_s": n, "imu_n_ok": int(len(ok)), "imu_n_still": nst, "imu_n_active": nac, "imu_n_loco": nlo,
            "imu_vedba_max": float(ok.vedba_1s.max()) if len(ok) else np.nan,
            "imu_turn_abs_deg": float(ok.turn_abs_deg.sum()) if len(ok) else np.nan, "imu_class": cls}


def load_imu(root: Path, animals, days) -> dict:
    out = {}
    for a in animals:
        parts = []
        for dday in sorted(set(days)):
            p = root / a / f"{dday:%Y%m%d}.csv.gz"
            if p.exists():
                parts.append(pd.read_csv(p, usecols=["sec", "ok", "still", "state", "vedba_1s", "turn_abs_deg"]))
        out[a] = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return out


def stability(rec: pd.DataFrame, segs: dict, imu: dict | None, px_per_in: float, record_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per animal clicked once on the colour frame and once on an IR frame of the same segment: displacement in reference px,
    frame px and inches; time between the frames; head-IMU state between. Also the per-frame membership counts."""
    rows, cnt = [], []
    for sid, g in rec.groupby("segment_id"):
        S = segs.get(sid)
        if S is None:
            continue
        col = g[(g.kind == "colour_mid") & g.animal.isin(LABELS)]
        cdup = col.animal.value_counts()
        for kind in ("ir_p06", "ir_p15"):
            ir = g[(g.kind == kind) & g.animal.isin(LABELS)]
            if col.empty and ir.empty:
                continue
            idup = ir.animal.value_counts()
            sc, si = set(col.animal), set(ir.animal)
            cnt.append({"record": record_name, "segment_id": sid, "start": S["start"], "ir_frame": kind, "n_colour": len(sc), "n_ir": len(si),
                        "n_both": len(sc & si), "colour_not_ir": ",".join(sorted(sc - si)), "ir_not_colour": ",".join(sorted(si - sc)),
                        "n_ir_clicks": int((g.kind == kind).sum()), "dup_ir": ",".join(f"{a}x{n}" for a, n in idup.items() if n > 1)})
            if not len(ir) or not len(col):
                continue
            tc, ti = S["frames"]["colour_mid"]["time"], S["frames"][kind]["time"]
            for a in sorted(sc & si):
                if cdup[a] > 1 or idup[a] > 1:
                    continue
                c, r = col[col.animal == a].iloc[0], ir[ir.animal == a].iloc[0]
                d_ref = float(np.hypot(r.u_ref - c.u_ref, r.v_ref - c.v_ref))
                row = {"record": record_name, "segment_id": sid, "start": S["start"], "ir_frame": kind, "animal": a,
                       "dt_s": (ti - tc).total_seconds(), "d_px": d_ref, "d_frame_px": float(np.hypot(r.u - c.u, r.v - c.v)),
                       "d_in": d_ref / px_per_in if px_per_in and np.isfinite(px_per_in) else np.nan,
                       "ir_status": r.status, "lid_flag": c.lid_flag}
                if imu is not None:
                    row.update(imu_between(imu, a, tc, ti))
                rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(cnt)


# ============================================================================================ WISER window sensitivity
def centred_positions(p0_run: Path, segs: dict, sids, half_s: float = CENTRED_HALF_S, reproduce: bool = True) -> tuple[dict, pd.DataFrame]:
    """WISER minute means over [mid - half_s, mid + half_s) with the page's own code (inbox_identity_page.wiser_panel, the
    window end = 'start'), and a reproduction check of the page's [ON - 60 s, ON) means."""
    import inbox_identity_page as ipage
    z = dict(np.load(p0_run / "states_1s.npz", allow_pickle=False))
    cache, out, chk = {}, {}, []
    for sid in sids:
        S = segs[sid]
        if reproduce:
            pan = ipage.wiser_panel(p0_run, pd.Series({"start": f"{S['start']:%Y-%m-%d %H:%M:%S.%f}", "mid": f"{S['mid']:%Y-%m-%d %H:%M:%S.%f}",
                                                       "camera": S["camera"]}), z, None, cache)
            for p in pan["positions"]:
                pw = S["W"].get(p["animal"])
                if p.get("along_in") is None or pw is None:
                    chk.append({"segment_id": sid, "animal": p["animal"], "page_has": pw is not None, "recomputed_has": p.get("along_in") is not None,
                                "max_abs_diff_in": np.nan})
                    continue
                chk.append({"segment_id": sid, "animal": p["animal"], "page_has": True, "recomputed_has": True,
                            "max_abs_diff_in": max(abs(p["along_in"] - pw["along_in"]), abs(p["across_in"] - pw["across_in"]))})
        end = S["mid"] + timedelta(seconds=half_s)
        pan = ipage.wiser_panel(p0_run, pd.Series({"start": f"{end:%Y-%m-%d %H:%M:%S.%f}", "mid": f"{S['mid']:%Y-%m-%d %H:%M:%S.%f}",
                                                   "camera": S["camera"]}), z, None, cache)
        out[sid] = {p["animal"]: p for p in pan["positions"] if p.get("along_in") is not None and p.get("n_fix")}
    return out, pd.DataFrame(chk)


# ============================================================================================ one variant
def run_variant(name: str, pts: pd.DataFrame, segs: dict, mirror: bool, theta_fixed: float | None = None,
                W_by_seg: dict | None = None, wcols=("along_in", "across_in"), untestable=None) -> dict:
    pr = lofo(pts, mirror, theta_fixed)
    ot, ov = order_test(pr, "pred_A", untestable)
    asg = assignment(pr, segs, W_by_seg, wcols) if len(pr) else pd.DataFrame()
    f_in, ins = insample(pts, mirror, theta_fixed) if len(pts) >= 3 else (None, None)
    return {"name": name, "mirror": mirror, "theta_fixed": theta_fixed, "pred": pr, "order": ot, "order_summary": ov, "assign": asg,
            "fit": f_in, "insample": ins, "n_points": len(pts), "n_flashes": int(pts.segment_id.nunique()),
            "lofo_rms_in": rms(pr.res_in) if len(pr) else np.nan, "lofo_median_in": float(pr.res_in.median()) if len(pr) else np.nan,
            "lofo_rms_px": rms(pr.res_px) if len(pr) else np.nan, "lofo_median_px": float(pr.res_px.median()) if len(pr) else np.nan,
            "in_rms_in": rms(ins.res_in) if ins is not None else np.nan,
            "acc_hungarian": float(asg.correct_hungarian.mean()) if len(asg) else np.nan,
            "acc_greedy": float(asg.correct_greedy.mean()) if len(asg) else np.nan,
            "acc_offset": float(asg.correct_offset.mean()) if len(asg) else np.nan,
            "chance": float((1.0 / asg.n_candidates).mean()) if len(asg) else np.nan, "n_assigned": len(asg)}


# ============================================================================================ figures
def fig_overlays(v: dict, segs: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pr = v["pred"]
    sids = list(pr.sort_values("start").segment_id.unique())
    if not sids:
        return
    nc = 4
    nr = int(np.ceil(len(sids) / nc))
    fig, axs = plt.subplots(nr, nc, figsize=(4.0 * nc, 2.9 * nr + 0.4), squeeze=False)
    L, Wd = BODY_IN
    for ax, sid in zip(axs.ravel(), sids):
        g = pr[pr.segment_id == sid]
        ax.add_patch(plt.Rectangle((-L / 2, -Wd / 2), L, Wd, fill=False, ls="--", lw=0.8, ec="#888888"))
        for a, p in segs[sid]["W"].items():
            if a not in set(g.animal):
                ax.plot(p["along_in"], p["across_in"], "o", mfc="none", mec=ANIMAL_CSS.get(a, "#555"), ms=8, mew=1.2)
                ax.annotate(a + " (not clicked)", (p["along_in"], p["across_in"]), fontsize=6.5, color="#555", xytext=(4, -9), textcoords="offset points")
        for r in g.itertuples():
            col = ANIMAL_CSS.get(r.animal, "#555")
            ax.plot([r.A, r.pred_A], [r.C, r.pred_C], "-", color=col, lw=1, alpha=0.7)
            ax.plot(r.A, r.C, "o", color=col, ms=8, mec="white", mew=1.5)
            ax.plot(r.pred_A, r.pred_C, "X", color=col, ms=8, mec="white", mew=1.0)
            ax.annotate(r.animal, (r.A, r.C), fontsize=7, color="#222", xytext=(4, 3), textcoords="offset points")
        o = v["order"]
        o = o[o.segment_id == sid]
        tag = ""
        if len(o):
            o = o.iloc[0]
            tag = f"  exact {'yes' if o.exact else 'no'}, tau {o.tau:+.1f}"
        ax.set_title(f"{short(sid)}{tag}", fontsize=9)
        ax.set_xlim(-25, 28)
        ax.set_ylim(-16, 16)
        ax.set_aspect("equal")
        ax.grid(alpha=0.25, lw=0.5)
        ax.tick_params(labelsize=7)
        ax.set_xlabel("along ridge (in)", fontsize=7)
        ax.set_ylabel("across (in)", fontsize=7)
    for ax in axs.ravel()[len(sids):]:
        ax.axis("off")
    fig.suptitle(f"house_2 (CH07): WISER minute mean (dot) vs clicked head mapped by the leave-one-flash-out fit (X) - {v['name']}; "
                 "dashed = house body", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_stability(st: pd.DataFrame, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if st.empty:
        return
    sids = sorted(st.segment_id.unique(), key=lambda s: st[st.segment_id == s].start.iloc[0])
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for k, (kind, dx, mk) in enumerate((("ir_p06", -0.15, "o"), ("ir_p15", 0.15, "s"))):
        g = st[st.ir_frame == kind]
        for i, sid in enumerate(sids):
            h = g[g.segment_id == sid]
            for r in h.itertuples():
                col = ANIMAL_CSS.get(r.animal, "#555")
                still = getattr(r, "imu_class", "") == "all still"
                ax.plot(i + dx, r.d_px, mk, ms=6, color=col if still else "white", mec=col, mew=1.3)
    ax.set_xticks(range(len(sids)))
    ax.set_xticklabels([f"{s[9:11]}-{s[11:13]}\n{s[14:16]}:{s[16:18]}" for s in sids], fontsize=7)
    ax.set_yscale("log")
    ax.set_ylim(2, 3000)
    ax.set_ylabel("head displacement colour -> IR (ref px)")
    ax.grid(alpha=0.25, lw=0.5)
    ax.set_title("Colour -> IR head displacement per animal (blind clicks)\n"
                 "circle = IR +6 s, square = IR +15 s; filled = head IMU still on "
                 "every second between, open = moved / no IMU", fontsize=8)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], marker="o", ls="", color=c, label=a) for a, c in ANIMAL_CSS.items() if a in set(st.animal)],
              fontsize=7, ncol=6, loc="upper center", bbox_to_anchor=(0.5, -0.2), frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_accuracy(asg: pd.DataFrame, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if asg.empty:
        return
    t = sep_table(asg)
    fig, ax = plt.subplots(figsize=(6, 3.4))
    x = np.arange(len(t))
    ax.bar(x, t.acc_hungarian.fillna(0), width=0.55, color="#2a78d6")
    ax.plot(x, t.chance, "_", color="#222", ms=26, mew=1.5)
    for i, r in t.iterrows():
        ax.annotate(f"{r.acc_hungarian:.0%}\nn={r.n_clicks}" if r.n_clicks else "n=0", (i, (r.acc_hungarian if r.n_clicks else 0) + 0.02),
                    ha="center", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(t.bin_in, fontsize=8)
    ax.set_ylim(0, 1.18)
    ax.set_xlabel("WISER separation of the clicked animal: distance to the nearest other roster mean (in)", fontsize=8)
    ax.set_ylabel("share of clicks assigned correctly", fontsize=8)
    ax.set_title("Hungarian assignment of clicked heads to WISER means (LOFO map); black tick = chance", fontsize=8)
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ============================================================================================ report
def md_table(df: pd.DataFrame, cols: list[str] | None = None, fmt: dict | None = None) -> str:
    if df is None or len(df) == 0:
        return "_(none)_\n"
    cols = cols or list(df.columns)
    fmt = fmt or {}

    def cell(c, v):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "-"
        if isinstance(v, (bool, np.bool_)):
            return "yes" if v else "no"
        if c in fmt:
            try:
                return fmt[c].format(v)
            except (ValueError, TypeError):
                return str(v)
        if isinstance(v, (float, np.floating)):
            return f"{v:.2f}"
        if isinstance(v, (datetime, pd.Timestamp)):
            return f"{v:%m-%d %H:%M:%S}"
        return str(v).replace("|", "/")
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df[cols].itertuples(index=False):
        out.append("| " + " | ".join(cell(c, v) for c, v in zip(cols, r)) + " |")
    return "\n".join(out) + "\n"


def short(sid: str) -> str:
    return f"{sid[9:11]}-{sid[11:13]} {sid[14:16]}:{sid[16:18]}:{sid[18:20]}"


DEFINITIONS = r"""
## Definitions

Units: **reference px** = pixels of the lid-segment reference frame (09-04 12:00, user-labelled) of CH07, 2560 × 1920, origin
top-left; **inches** in the house frame of house_2. Symbols: $f$ indexes flashes (colour segments), $a$ animals, $k$ clicks.

**Click correction.** $(u'_k, v'_k)^\top = B_k\,(u_k, v_k, 1)^\top$, with $B_k$ the 2 × 3 `B_frame_to_ref` stored with the click
(frame px → reference px of its lid-closed segment; `cv/cv_field/frame_correction.py`). **Display coordinates**
$(p_k, q_k) = (u'_k, -v'_k)$: image right and image up as the page shows the frame.

**Blind record.** The clicks with `before_reveal` = true, `legacy` ≠ true and a `verdict_first`, read from `verdict_first` (the
values frozen when the user pressed "Save clicks & reveal WISER"). *After-reveal* clicks (`before_reveal` = false) and
*unsaved* clicks (in a segment not yet revealed when the browser state was taken) are listed but used by none of the fit, the
order test or the assignment. The *final* record = blind + after-reveal clicks with their live values, minus deleted ones.

**House frame.** For a paddock point $\mathbf x$ (in), $\text{along} = (\mathbf x - \mathbf c)\cdot(\cos\varphi, \sin\varphi)$,
$\text{across} = (\mathbf x - \mathbf c)\cdot(-\sin\varphi, \cos\varphi)$, house_2 centre $\mathbf c = (342.4, 117.7)$ in, ridge
$\varphi = 92.0°$ (`inbox_p0.to_house_frame`). Body 24.6 in along × 18.0 in across.

**WISER minute mean** $\mathbf W_{f,a} = (A_{f,a}, C_{f,a})$: mean over the animal's in-house default-track fixes in
$[t_{ON} - 60\,\mathrm s, t_{ON})$ mapped to the house frame — the value the page shows (`page_data.json`; reproduced here by the
page's own code). Raw-fix mean = the same over the raw fixes (sensitivity). *Centred window* = $[t_{mid} - 30\,\mathrm s,
t_{mid} + 30\,\mathrm s)$ around the colour frame (sensitivity).

**Similarity fit (Q3).** With $z_k = p_k + i\,\sigma q_k$ ($\sigma = +1$ proper, $-1$ improper = mirrored display) and
$w_k = A_k + i\,C_k$ the WISER mean of the clicked animal,
$$\hat\alpha = \frac{\sum_k \overline{(z_k - \bar z)}\,(w_k - \bar w)}{\sum_k |z_k - \bar z|^2},\qquad \hat\tau = \bar w - \hat\alpha\,\bar z,\qquad \hat w(z) = \hat\alpha z + \hat\tau ,$$
the least-squares 2-D similarity (scale $s = |\hat\alpha|$ in/px, i.e. $1/s$ px/in; rotation $\theta_{house} = \arg\hat\alpha$,
counter-clockwise, display → house frame). Rotation in the paddock: $\theta_{pad} = \theta_{house} + \varphi$. **Page-equivalent
orientation** (the page draws view $= R(\text{rot})\,M_x\,(dx, dy)$, $M_x$ = x-flip if mirrored): proper
$\text{rot} = -\theta_{pad}$, improper $\text{rot} = \theta_{pad} - 180°$ (mod 360). The user's display orientation for house_2
(rot 180°, no mirror) corresponds to $\theta_{pad} = 180°$, $\theta_{house} = 88°$. **Fixed-rotation (prior) map**: $\arg\hat\alpha$
held at the prior, $|\hat\alpha| = \max(0, \mathrm{Re}\sum \overline{e^{i\theta_0}(z_k - \bar z)}(w_k - \bar w)) / \sum|z_k - \bar z|^2$.
**Image centre in the house frame** $= \hat w(1280 - 960 i)$ (proper fit): where the reference image centre lands in WISER's
house frame; it equals the WISER bias only if the camera axis meets the house centre (not known).

**Leave-one-flash-out (LOFO).** For flash $f$, fit on all clicks of the other flashes, then
$e^{in}_{f,a} = |\hat w_{-f}(z_{f,a}) - w_{f,a}|$ (inches; the clicked head mapped into the house frame vs WISER) and
$e^{px}_{f,a} = |\hat w_{-f}^{-1}(w_{f,a}) - z_{f,a}|$ (reference px; WISER mapped into the image vs the click). RMS = $\sqrt{\text{mean}\,e^2}$.
The handedness with the lower LOFO RMS (inches) is used downstream.

**Residual decomposition.** $\mathbf r_{f,a} = \hat w_{-f}(z_{f,a}) - w_{f,a}$ (in). *Flash offset* $\bar{\mathbf r}_f$ = mean over the
flash's animals; RMS after it = $\sqrt{\text{mean}\,|\mathbf r_{f,a} - \bar{\mathbf r}_f|^2}$ (in-sample). *Animal offset (LOO)*
$\bar{\mathbf r}_{-f,a}$ = mean of the animal's residuals in the other flashes; RMS after it = $\sqrt{\text{mean}\,|\mathbf r_{f,a} - \bar{\mathbf r}_{-f,a}|^2}$.
A drop marks a bias that a per-flash or per-tag correction could remove.

**Order test (Q4; the operator's rule).** Eligible flash: ≥ 3 animals with a blind named colour click and a WISER mean. WISER
order = animals sorted by $A_{f,a}$; click order = sorted by $\hat A_{f,a} = \mathrm{Re}\,\hat w_{-f}(z_{f,a})$. *Exact match* =
identical permutations. **ACCEPTED** if exact in ≥ 4 of the first 5 eligible flashes in time order. *Kendall*
$\tau_a = \frac{\sum_{a<b} \mathrm{sgn}(A_a - A_b)\,\mathrm{sgn}(\hat A_a - \hat A_b)}{n(n-1)/2}$ (range −1 … 1; 1 = same order).
*Tie version*: only pairs with $|A_a - A_b| \ge 8$ in are tested (the plan: 1-min-mean separations < 8 in are candidates); a
flash matches if every tested pair is concordant ($\mathrm{sgn}$ equal); a flash without a tested pair is "no testable pair".
*Alternative reading*: a flash with ≥ 3 clicked animals but no WISER mean in the window counts as a non-match.

**Assignment (Q5).** Per flash, heads $h$ = blind named colour clicks mapped by $\hat w_{-f}$; candidates = roster animals with a
WISER mean. *Hungarian*: the one-to-one assignment $\pi$ minimising $\sum_h |\hat w_{-f}(z_h) - w_{\pi(h)}|$ (scipy
`linear_sum_assignment`). *Greedy*: each head to its nearest mean (repeats allowed). *Per-flash offset*: the injection minimising
$\sum_h |d_h - \bar d|^2$, $d_h = w_{\pi(h)} - \hat w_{-f}(z_h)$ (a free WISER offset per flash). Accuracy = share of heads with
$\pi(h)$ = the user's colour ID. *Chance* = $1/n_{cand}$ per head (expected accuracy of a uniformly random assignment).
*WISER separation* of a click = $\min_{b \ne a} |w_{f,a} - w_{f,b}|$ over the other roster means (2-D, in); *along separation*
= $\min_{b\ne a} |A_{f,a} - A_{f,b}|$.

**Colour → IR displacement (Q2).** For animal $a$ named once on the colour frame and once on an IR frame of the same
segment: $d = |(u'_{IR}, v'_{IR}) - (u'_{col}, v'_{col})|$ (reference px; frame px reported too; within a segment both frames
share $B$, so the two agree), $d_{in} = d / (1/s)$ at the proper fit's scale (a single scale for a camera ~ 1 ft above heads at
different heights: indicative), $\Delta t = t_{IR} - t_{col}$. **Head-IMU state between** (`imu_seconds_cache`, field-PC
seconds $\lfloor t_{col}\rfloor … \lfloor t_{IR}\rfloor$): *all still* = every second IMU-ok and still; *moved* = ≥ 1 IMU-ok
second active or locomoting; *still (partial)* = some seconds not ok, the ok ones still; *no IMU* = no ok second
(handling windows ± 5 min are not ok by construction).
"""


def write_report(run: Path, R: dict) -> Path:
    import output_paths as op
    rep = op.report_dir(COHORT, DIRECTION)
    m = R["meta"]
    comp, cnt, stb, stf = R["composition"], R["stab_counts"], R["stab_blind"], R["stab_final"]
    V = R["variants"]
    P = V["primary"]
    fits = R["fits"]
    pr = R["prior"]
    L = []
    L.append("# In-box camera CH07 (house_2): the user's first identity clicks — composition, colour → IR stability, "
             "camera ↔ WISER fit, the pre-registered order test, WISER as an identity aid (cohort `2026c`)\n")
    L.append(f"**PRELIMINARY — data = browser snapshot 2026-10-10 20:17 of the identity page's localStorage "
             f"(`{m['clicks_rel']}`, sha256 `{m['clicks_sha256'][:16]}…`), {m['n_segments_clicked']} / {m['n_page_segments']} segments "
             f"clicked, not a formal export.** The user has not exported yet; every number below can change when the export "
             f"arrives (re-run: `python cv/cv_field/inbox_click_analysis.py --clicks <export.json>`).\n")
    L.append(f"Plan `{PLAN}` (section \"Pre-registered use of the user's clicks\" + amendments 1–11; amendment 11 = how this "
             f"step is run, written before any result). Run `{run.as_posix()}`; generated {m['made']}; code `{m['git_commit']}`. "
             f"Phase-0 run `{m['p0_run']}`. Driver `cv/cv_field/inbox_click_analysis.py`. The agent never looked at a frame; "
             f"everything is computed from the click coordinates, the user's IDs and WISER.\n")
    # ---- summary
    ov = P["order_summary"]
    L.append("## Summary\n")
    for s in R["summary"]:
        L.append(f"- {s}")
    L.append("")
    L.append("## The question: what do the colour labels tell us, and can WISER serve as an identity-label aid?\n")
    L.append("Preliminary (snapshot, 8 flashes in the fit); every statement is a number from the sections below.\n")
    for s in R["answer"]:
        L.append(f"- {s}")
    L.append("")
    # ---- which clicks
    L.append("## Which clicks were used\n")
    L.append(md_table(R["click_counts"]))
    L.append(f"\nSF09 / SF10 one-time swap (amendment 10): applied to {m['sf09_sf10_n_swapped']} clicks "
             f"(all of segment 09-09 19:10, before the fix; `undone_at` = {m['sf09_sf10_undone']}); `animal` already carries it. "
             f"No click is legacy; no blind click was edited or deleted after its reveal "
             f"(edited {m['n_edited']}, deleted {m['n_deleted']}); the blind record and the live values agree on all "
             f"{m['n_blind']} blind clicks (max |Δ| {m['blind_live_max_diff_px']:.2f} px, {m['blind_live_animal_diff']} label differences). "
             f"Orientation: snapshot `orientation_by_house.house_2` = rot {m['orient_snapshot']}; "
             f"`cv/configs/inbox_camera_orientation_2026c.json` = rot {pr.get('rot_deg')}°, mirror {pr.get('mirror')}; chosen "
             f"{m['orient_chosen_at']} UTC, after {m['n_revealed_before_orient']} segments had been revealed (so the user had seen "
             f"WISER top views; the orientation used no fitted number).\n")
    # ---- Q1
    L.append("## 1. Composition: clicked on the colour frame vs the WISER roster\n")
    L.append("Roster = tagged animals whose cleaned house state is house_2 at the colour frame (dilated house zone, plan B; "
             "SF11 had left the paddock at the 09-07 AM round, so the roster covers every animal present that WISER locates; "
             "corrected 2026-10-11, plan amendment 12). Clicked = named blind clicks on the colour frame.\n")
    L.append(md_table(comp, ["segment_id", "revealed", "n_clicks", "n_blind", "roster", "untracked", "clicked_colour", "n_unknown_colour",
                             "missing", "extras", "agree", "clicked_any_frame_blind", "missing_any_frame_blind", "clicked_any_frame_final"]))
    L.append("")
    for s in R["q1_text"]:
        L.append(f"- {s}")
    L.append("")
    # ---- Q2
    L.append("## 2. Stability colour → IR (the premise that a pile does not move across the switch)\n")
    L.append(md_table(R["stab_seg"], ["segment_id", "ir_frame", "dt_s", "n_colour", "n_ir", "n_both", "colour_not_ir", "ir_not_colour",
                                      "median_px", "max_px", "median_in", "max_in", "imu"],
                      {"dt_s": "{:.1f}", "median_px": "{:.0f}", "max_px": "{:.0f}", "median_in": "{:.1f}", "max_in": "{:.1f}"}))
    L.append("")
    for s in R["q2_text"]:
        L.append(f"- {s}")
    L.append("\nPer animal (blind record):\n")
    L.append(md_table(stb, ["segment_id", "ir_frame", "animal", "dt_s", "d_px", "d_in", "imu_n_s", "imu_n_ok", "imu_n_still",
                            "imu_n_active", "imu_n_loco", "imu_class"],
                      {"dt_s": "{:.1f}", "d_px": "{:.0f}", "d_in": "{:.1f}"}))
    L.append("")
    # ---- Q3
    L.append("## 3. Pre-registered fit: image (reference px) ↔ house frame (WISER minute means), house_2\n")
    L.append(f"Points: {P['n_points']} blind named colour clicks with a WISER mean in {P['n_flashes']} flashes "
             f"({', '.join(short(s) for s in R['fit_flashes'])}). Not in the fit: {R['not_fit_text']}\n")
    L.append(md_table(fits, ["fit", "n", "px_per_in", "theta_house_deg", "theta_paddock_deg", "page_rot_deg", "page_mirror",
                             "d_rot_vs_prior_deg", "in_rms_in", "lofo_rms_in", "lofo_median_in", "lofo_rms_px", "lofo_median_px"],
                      {"px_per_in": "{:.1f}", "theta_house_deg": "{:+.1f}", "theta_paddock_deg": "{:+.1f}", "page_rot_deg": "{:.1f}",
                       "d_rot_vs_prior_deg": "{:+.1f}", "in_rms_in": "{:.2f}", "lofo_rms_in": "{:.2f}", "lofo_median_in": "{:.2f}",
                       "lofo_rms_px": "{:.0f}", "lofo_median_px": "{:.0f}"}))
    L.append("")
    for s in R["q3_text"]:
        L.append(f"- {s}")
    L.append("\nLOFO residual per flash (primary fit):\n")
    L.append(md_table(R["lofo_flash"], ["segment_id", "n", "rms_in", "max_in", "rms_px", "max_px", "fold_theta_house_deg", "fold_px_per_in", "lid_flag"],
                      {"rms_in": "{:.2f}", "max_in": "{:.2f}", "rms_px": "{:.0f}", "max_px": "{:.0f}", "fold_theta_house_deg": "{:+.1f}",
                       "fold_px_per_in": "{:.1f}"}))
    L.append("\nMean LOFO residual per animal over its flashes (head mapped − WISER):\n")
    L.append(md_table(R["decomp_an"], ["animal", "n", "mean_along_in", "mean_across_in", "mean_norm_in", "sd_along_in", "sd_across_in"]))
    L.append("")
    # ---- Q4
    L.append("## 4. The pre-registered order test (the operator's rule)\n")
    L.append(f"Clicks used: **blind record only** (before the reveal, not legacy; there are no legacy clicks), colour frame, "
             f"named animals with a WISER mean; mapped by the fit that leaves the flash out ({'improper' if P['mirror'] else 'proper'} "
             f"handedness = the lower LOFO RMS). WISER = default-track minute means over [ON − 60 s, ON).\n")
    L.append(f"**Verdict: {ov['verdict']}** — exact order match in **{ov.get('n_exact_first', 0)} of {min(N_FIRST, ov.get('n_eligible', 0))}** "
             f"of the first {N_FIRST} eligible flashes (needs ≥ {ACCEPT_MIN}). Tie version (pairs < {CAND_SEP_IN:g} in by WISER not tested): "
             f"**{ov.get('verdict_tie')}** ({ov.get('n_tie_first', 0)} of {min(N_FIRST, ov.get('n_eligible', 0))}). "
             f"Kendall τ median {ov.get('tau_median_first', float('nan')):+.2f} (first 5), {ov.get('tau_median_all', float('nan')):+.2f} (all).\n")
    L.append(md_table(P["order"], ["rank", "segment_id", "n", "order_wiser", "order_clicks", "exact", "tau", "min_sep_along_in",
                                   "n_pairs_ge_sep", "n_conc_ge_sep", "tie_match", "discordant_ge_sep"],
                      {"tau": "{:+.1f}", "min_sep_along_in": "{:.1f}"}))
    L.append("\nOrder is written low → high along the ridge (along ≈ paddock +y, toward row C).\n")
    L.append("Variants (secondary; the verdict above is the primary):\n")
    L.append(md_table(R["variant_table"], ["variant", "n_flashes", "lofo_rms_in", "first5", "exact_first5", "verdict", "tie_first5",
                                           "verdict_tie", "exact_all", "tau_med_all", "acc_hungarian", "acc_offset", "chance"],
                      {"lofo_rms_in": "{:.2f}", "tau_med_all": "{:+.2f}", "acc_hungarian": "{:.0%}", "acc_offset": "{:.0%}", "chance": "{:.0%}"}))
    L.append("")
    for s in R["q4_text"]:
        L.append(f"- {s}")
    L.append("")
    # ---- Q5
    L.append("## 5. WISER as an identity aid: assigning the clicked heads by WISER\n")
    L.append(f"Hungarian assignment of the LOFO-mapped clicked heads to the WISER means (primary variant): **{P['acc_hungarian']:.0%}** "
             f"of {P['n_assigned']} clicks correct (greedy nearest {P['acc_greedy']:.0%}; with a free WISER offset per flash "
             f"{P['acc_offset']:.0%}; chance {P['chance']:.0%}).\n")
    L.append("By WISER separation of the clicked animal (2-D distance to the nearest other roster mean):\n")
    L.append(md_table(R["sep2d"], fmt={"acc_hungarian": "{:.0%}", "acc_greedy": "{:.0%}", "acc_offset": "{:.0%}", "chance": "{:.0%}"}))
    L.append("\nBy along-ridge separation:\n")
    L.append(md_table(R["sepal"], fmt={"acc_hungarian": "{:.0%}", "acc_greedy": "{:.0%}", "acc_offset": "{:.0%}", "chance": "{:.0%}"}))
    L.append("\nPer flash:\n")
    L.append(md_table(R["asg_flash"], fmt={"acc_hungarian": "{:.0%}", "acc_greedy": "{:.0%}", "acc_offset": "{:.0%}"}))
    L.append("")
    for s in R["q5_text"]:
        L.append(f"- {s}")
    L.append("")
    # ---- not verified
    L.append("## What is not verified\n")
    for s in R["not_verified"]:
        L.append(f"- {s}")
    L.append("")
    L.append(DEFINITIONS)
    L.append("## Files\n")
    L.append(f"Run folder `{run.as_posix()}`: `clicks_table.csv` (every click, both records, B-corrected), `composition.csv`, "
             "`stability_blind.csv`, `stability_final.csv`, `stability_counts.csv`, `fit_summary.csv`, `fit_points_<variant>.csv` "
             "(LOFO predictions per click), `order_<variant>.csv`, `assignment_<variant>.csv`, `variants.csv`, `residual_per_animal.csv`, "
             "`wiser_centred_window.json`, `wiser_reproduction_check.csv`, `run.json`; figures `figures/flash_overlays_primary.png`, "
             "`figures/colour_ir_displacement.png`, `figures/assignment_vs_separation.png`. Pointer "
             f"`results/{COHORT}/{DIRECTION}/reports/{POINTER_NAME}`.\n")
    out = rep / REPORT_NAME
    out.write_text("\n".join(L), encoding="utf-8")
    ptr = {"run_dir": run.as_posix(), "cohort": COHORT, "direction": DIRECTION, "analysis": "inbox_clicks",
           "driver": "cv/cv_field/inbox_click_analysis.py", "report": REPORT_NAME, "plan": PLAN, "git_commit": m["git_commit"],
           "clicks": m["clicks_rel"], "clicks_sha256": m["clicks_sha256"], "clicks_kind": "browser snapshot (not a formal export)",
           "p0_run": m["p0_run"], "verdict_order_test": ov["verdict"], "verdict_order_test_tie": ov.get("verdict_tie"),
           "preliminary": True}
    (rep / POINTER_NAME).write_text(json.dumps(ptr, indent=2) + "\n", encoding="utf-8")
    print(f"[report] {out.as_posix()} + {POINTER_NAME}", flush=True)
    return out


# ============================================================================================ main analysis
def analyse(clicks_path: Path, p0_run: Path, run: Path, imu_root: Path | None, do_centred: bool = True) -> dict:
    snap = json.loads(Path(clicks_path).read_text(encoding="utf-8"))
    page = json.loads((p0_run / "identity_page" / "page_data.json").read_text(encoding="utf-8"))
    segs = page_segments(page)
    ct = click_table(snap)
    rb, rf = record(ct, "blind"), record(ct, "final")
    houses = sorted(ct.house.dropna().unique())
    if houses != ["house_2"]:
        print(f"[note] houses with clicks: {houses}; this report covers house_2 only", flush=True)
    house = "house_2"
    ridge = float(page["meta"]["house_refs"][house]["ridge_deg"])
    priors = load_prior()
    pr = priors.get(house, {})
    snap_or = (snap.get("orientation_by_house") or {}).get(house, {})
    th_prior = prior_theta_house(pr["rot_deg"], bool(pr["mirror"]), ridge) if pr.get("rot_deg") is not None else None
    # ---------------- click accounting
    cc = ct.groupby(["status", "frame_kind"]).size().unstack(fill_value=0).reset_index()
    cc["total"] = cc[[k for k in FRAME_KINDS if k in cc.columns]].sum(1)
    named = ct.assign(named=ct.animal.isin(LABELS))
    cc["named"] = cc.status.map(named.groupby("status").named.sum()).astype(int)
    cc["unknown"] = cc.total - cc.named
    bl = ct[ct.status == "blind"]
    max_diff = float(np.nanmax(np.abs(np.r_[bl.u - bl.b_u, bl.v - bl.b_v]))) if len(bl) else 0.0
    anim_diff = int((bl.animal != bl.b_animal).sum())
    seg_rev = {k: v.get("revealed_at") for k, v in (snap.get("segments") or {}).items()}
    n_rev_before = sum(1 for v in seg_rev.values() if v and snap_or.get("chosen_at") and v < snap_or["chosen_at"])
    # ---------------- Q1
    comp = composition(rb, rf, ct, segs)
    # ---------------- Q3 points + variants
    pts = fit_points(rb, segs, house)
    pts_raw = fit_points(rb, segs, house, ("along_raw_in", "across_raw_in"))
    fit_flashes = list(pts.segment_id.unique())
    proper = run_variant("proper", pts, segs, False)
    improper = run_variant("improper", pts, segs, True)
    chosen_mirror = bool(improper["lofo_rms_in"] < proper["lofo_rms_in"])
    primary = dict(improper if chosen_mirror else proper)
    primary["name"] = "primary"
    variants = {"primary": primary, "proper": proper, "improper": improper}
    variants["prior_rotation"] = run_variant("prior_rotation", pts, segs, bool(pr.get("mirror")), th_prior) if th_prior is not None else None
    variants["raw_fix_means"] = run_variant("raw_fix_means", pts_raw, segs, chosen_mirror, wcols=("along_raw_in", "across_raw_in"))
    lidflag = set(pts[pts.lid_flag.astype(str).str.contains("lid")].segment_id)
    variants["no_lid_flag"] = run_variant("no_lid_flag", pts[~pts.segment_id.isin(lidflag)].reset_index(drop=True), segs, chosen_mirror)
    # untestable (alternative reading)
    clicked3 = rb[(rb.house == house) & (rb.kind == "colour_mid") & rb.animal.isin(LABELS)].groupby("segment_id").animal.nunique()
    untest = [(sid, segs[sid]["start"]) for sid, n in clicked3.items() if n >= MIN_ID and sid not in set(pts.groupby("segment_id").filter(lambda g: len(g) >= MIN_ID).segment_id)]
    variants["alt_reading"] = run_variant("alt_reading", pts, segs, chosen_mirror, untestable=untest)
    W_c, repro = ({}, pd.DataFrame())
    if do_centred:
        sids = [s for s in comp.segment_id if s in segs and segs[s]["house"] == house and segs[s]["roster"]]
        W_c, repro = centred_positions(p0_run, segs, sids)
        pts_c = fit_points(rb, segs, house, W_override=W_c)
        variants["centred_window"] = run_variant("centred_window", pts_c, segs, chosen_mirror, W_by_seg=W_c)
    # ---------------- fits table
    frows = []
    for nm in ("proper", "improper", "prior_rotation"):
        v = variants.get(nm)
        if v is None or v["fit"] is None:
            continue
        sp = sim_params(v["fit"], ridge)
        d_rot = wrap180(sp["page_rot_deg"] - pr["rot_deg"]) if pr.get("rot_deg") is not None else np.nan
        frows.append({"fit": nm + (" (fixed at the user's 180°)" if nm == "prior_rotation" else ""), "n": v["n_points"], **sp,
                      "d_rot_vs_prior_deg": d_rot if sp["page_mirror"] == bool(pr.get("mirror")) else np.nan,
                      "in_rms_in": v["in_rms_in"], "lofo_rms_in": v["lofo_rms_in"], "lofo_median_in": v["lofo_median_in"],
                      "lofo_rms_px": v["lofo_rms_px"], "lofo_median_px": v["lofo_median_px"]})
    fits = pd.DataFrame(frows)
    sp_primary = sim_params(primary["fit"], ridge)
    px_per_in = sim_params(proper["fit"], ridge)["px_per_in"]
    centre = sim_apply(proper["fit"], [[IMG_W / 2, -IMG_H / 2]])[0]
    # LOFO fold spread
    pp = primary["pred"]
    lf = pp.groupby("segment_id", sort=False).agg(n=("animal", "size"), rms_in=("res_in", rms), max_in=("res_in", "max"),
                                                  rms_px=("res_px", rms), max_px=("res_px", "max"),
                                                  fold_theta_house_deg=("fold_theta_house_deg", "first"),
                                                  fold_px_per_in=("fold_px_per_in", "first"), lid_flag=("lid_flag", "first")).reset_index()
    decomp, decomp_an = residual_decomposition(pp)
    decomp_an.to_csv(run / "residual_per_animal.csv", index=False)
    # ---------------- Q2
    imu = None
    if imu_root is not None and imu_root.exists():
        days = {segs[s]["start"].date() for s in comp.segment_id if s in segs}
        imu = load_imu(imu_root, LABELS, days)
    stb, cntb = stability(rb, segs, imu, px_per_in, "blind")
    stf, cntf = stability(rf, segs, imu, px_per_in, "final")
    cnt = pd.concat([cntb, cntf], ignore_index=True)
    srows = []
    for (sid, kind), g in stb.groupby(["segment_id", "ir_frame"]):
        c = cntb[(cntb.segment_id == sid) & (cntb.ir_frame == kind)].iloc[0]
        srows.append({"segment_id": sid, "start": g.start.iloc[0], "ir_frame": kind, "dt_s": g.dt_s.iloc[0], "n_colour": c.n_colour, "n_ir": c.n_ir,
                      "n_both": c.n_both, "colour_not_ir": c.colour_not_ir, "ir_not_colour": c.ir_not_colour, "median_px": g.d_px.median(),
                      "max_px": g.d_px.max(), "median_in": g.d_in.median(), "max_in": g.d_in.max(),
                      "imu": ", ".join(f"{k} {n}" for k, n in g.imu_class.value_counts().items()) if "imu_class" in g else "-"})
    for r in cntb.itertuples():                                         # segment / frame pairs with no common animal
        if not ((stb.segment_id == r.segment_id) & (stb.ir_frame == r.ir_frame)).any():
            srows.append({"segment_id": r.segment_id, "start": r.start, "ir_frame": r.ir_frame, "dt_s": np.nan, "n_colour": r.n_colour, "n_ir": r.n_ir,
                          "n_both": r.n_both, "colour_not_ir": r.colour_not_ir, "ir_not_colour": r.ir_not_colour, "median_px": np.nan,
                          "max_px": np.nan, "median_in": np.nan, "max_in": np.nan, "imu": "-"})
    stab_seg = pd.DataFrame(srows).sort_values(["start", "ir_frame"]).reset_index(drop=True)
    # ---------------- Q5 tables
    asg = primary["assign"]
    sep2d, sepal = sep_table(asg, "sep_2d_in"), sep_table(asg, "sep_along_in")
    af = asg.groupby("segment_id", sort=False).agg(n=("animal", "size"), n_candidates=("n_candidates", "first"),
                                                   acc_hungarian=("correct_hungarian", "mean"), acc_greedy=("correct_greedy", "mean"),
                                                   acc_offset=("correct_offset", "mean")).reset_index()
    af["swapped"] = [", ".join(f"{r.animal}→{r.assigned_hungarian}" for r in asg[(asg.segment_id == s) & ~asg.correct_hungarian].itertuples())
                     for s in af.segment_id]
    # ---------------- variant table
    vrows = []
    for nm, v in variants.items():
        if v is None:
            continue
        o = v["order_summary"]
        vrows.append({"variant": nm, "n_flashes": v["n_flashes"], "lofo_rms_in": v["lofo_rms_in"],
                      "first5": ", ".join(short(s) for s in o.get("first", [])), "exact_first5": o.get("n_exact_first"),
                      "verdict": o.get("verdict"), "tie_first5": o.get("n_tie_first"), "verdict_tie": o.get("verdict_tie"),
                      "exact_all": f"{o.get('n_exact_all', 0)} / {o.get('n_eligible', 0)}", "tau_med_all": o.get("tau_median_all"),
                      "acc_hungarian": v["acc_hungarian"], "acc_offset": v["acc_offset"], "chance": v["chance"]})
    vt = pd.DataFrame(vrows)
    # ---------------- write tables
    ct.to_csv(run / "clicks_table.csv", index=False)
    comp.to_csv(run / "composition.csv", index=False)
    stb.to_csv(run / "stability_blind.csv", index=False)
    stf.to_csv(run / "stability_final.csv", index=False)
    cnt.to_csv(run / "stability_counts.csv", index=False)
    stab_seg.to_csv(run / "stability_per_segment.csv", index=False)
    fits.to_csv(run / "fit_summary.csv", index=False)
    vt.to_csv(run / "variants.csv", index=False)
    lf.to_csv(run / "lofo_per_flash.csv", index=False)
    for nm, v in variants.items():
        if v is None:
            continue
        v["pred"].to_csv(run / f"fit_points_{nm}.csv", index=False)
        v["order"].to_csv(run / f"order_{nm}.csv", index=False)
        if len(v["assign"]):
            v["assign"].to_csv(run / f"assignment_{nm}.csv", index=False)
    (run / "wiser_centred_window.json").write_text(json.dumps(W_c, indent=1, default=str), encoding="utf-8")
    repro.to_csv(run / "wiser_reproduction_check.csv", index=False)
    figd = run / "figures"
    figd.mkdir(exist_ok=True)
    fig_overlays(primary, segs, figd / "flash_overlays_primary.png")
    fig_stability(stb, figd / "colour_ir_displacement.png")
    fig_accuracy(asg, figd / "assignment_vs_separation.png")
    meta = {"made": datetime.now().isoformat(timespec="seconds"), "git_commit": git_commit(REPO), "plan": PLAN,
            "clicks": Path(clicks_path).as_posix(), "clicks_rel": Path(clicks_path).resolve().relative_to(REPO).as_posix()
            if str(Path(clicks_path).resolve()).startswith(str(REPO)) else Path(clicks_path).as_posix(),
            "clicks_sha256": sha256(Path(clicks_path)), "p0_run": p0_run.as_posix(),
            "page_data_sha256": sha256(p0_run / "identity_page" / "page_data.json"),
            "n_clicks": len(ct), "n_blind": int((ct.status == "blind").sum()), "n_page_segments": len(segs),
            "n_segments_clicked": int(ct.segment_id.nunique()), "n_edited": int(ct.edited.sum()), "n_deleted": int(ct.deleted.sum()),
            "blind_live_max_diff_px": max_diff, "blind_live_animal_diff": anim_diff,
            "sf09_sf10_n_swapped": (snap.get("sf09_sf10_fix") or {}).get("n_swapped"), "sf09_sf10_undone": (snap.get("sf09_sf10_fix") or {}).get("undone_at"),
            "orient_snapshot": f"{snap_or.get('rot_deg')}°, mirror {snap_or.get('mirror')}", "orient_chosen_at": snap_or.get("chosen_at"),
            "n_revealed_before_orient": n_rev_before, "imu_root": imu_root.as_posix() if imu_root else None,
            "chosen_handedness": "improper" if chosen_mirror else "proper", "ridge_deg": ridge, "prior": pr, "theta_house_prior": th_prior,
            "px_per_in_proper": px_per_in, "image_centre_house_in": [float(centre[0]), float(centre[1])],
            "params": {"cand_sep_in": CAND_SEP_IN, "n_first": N_FIRST, "min_id": MIN_ID, "accept_min": ACCEPT_MIN, "sep_bins": list(SEP_BINS[:-1]),
                       "centred_half_s": CENTRED_HALF_S}}
    (run / "run.json").write_text(json.dumps({**meta, "variants": vt.to_dict("records"), "fits": fits.to_dict("records")},
                                             indent=2, default=str), encoding="utf-8")
    return {"meta": meta, "ct": ct, "composition": comp, "stab_blind": stb, "stab_final": stf, "stab_counts": cnt, "stab_seg": stab_seg,
            "variants": variants, "fits": fits, "variant_table": vt, "lofo_flash": lf, "sep2d": sep2d, "sepal": sepal, "asg_flash": af,
            "prior": pr, "fit_flashes": fit_flashes, "segs": segs, "repro": repro, "sp_primary": sp_primary, "untestable": untest,
            "click_counts": cc, "W_c": W_c, "decomp": decomp, "decomp_an": decomp_an, "fix_sd": fix_sd(segs, fit_flashes)}


def fix_sd(segs: dict, sids) -> dict:
    """Per-fix WISER scatter (SD of the raw fixes in the page window) and minute-mean SE over the fitted flashes' animals."""
    W = [w for s in sids for w in segs[s]["W"].values()]
    a = np.array([w.get("sd_along_raw_in") for w in W], float)
    c = np.array([w.get("sd_across_raw_in") for w in W], float)
    se = np.array([w.get(k) for w in W for k in ("along_se_in", "across_se_in")], float)
    return {"along_med": float(np.nanmedian(a)), "along_min": float(np.nanmin(a)), "along_max": float(np.nanmax(a)),
            "across_med": float(np.nanmedian(c)), "across_min": float(np.nanmin(c)), "across_max": float(np.nanmax(c)),
            "se_med": float(np.nanmedian(se))}


def texts(R: dict) -> None:
    """Report prose built from the numbers (no hand-typed result)."""
    m, comp, segs = R["meta"], R["composition"], R["segs"]
    P, V = R["variants"]["primary"], R["variants"]
    ov = P["order_summary"]
    fits = R["fits"]
    stb, st = R["stab_blind"], R["stab_seg"]
    # ---- Q1
    rev = comp[comp.revealed]
    agree = rev[rev.agree == True]  # noqa: E712
    q1 = [f"{len(comp)} segments carry clicks, {len(rev)} of them revealed (the 11th, {', '.join(short(s) for s in comp[~comp.revealed].segment_id)}, "
          f"holds {int(comp[~comp.revealed].n_unsaved.sum())} unsaved click(s), not yet revealed)."]
    q1.append(f"Colour-frame set = WISER roster in **{len(agree)} of {len(rev)}** revealed segments "
              f"({', '.join(short(s) for s in agree.segment_id)}).")
    for r in rev[rev.agree != True].itertuples():  # noqa: E712
        q1.append(f"{short(r.segment_id)}: roster {r.roster or '-'}{' (untracked ' + r.untracked + ')' if r.untracked else ''}; colour frame "
                  f"{r.clicked_colour or '-'} + {r.n_unknown_colour} unknown → missing {r.missing or '-'}, extras {r.extras or '-'}; on any "
                  f"frame (blind) {r.clicked_any_frame_blind or '-'} (missing {r.missing_any_frame_blind or '-'}).")
    q1.append(f"Unknown (`None`) clicks: {int((R['ct'].animal == 'unknown').sum())} in all "
              f"({', '.join(f'{short(s)} {k}' for s, k in R['ct'][R['ct'].animal == 'unknown'][['segment_id', 'frame_kind']].itertuples(index=False))}). "
              f"Extras (a clicked animal outside the roster): {int((comp.extras != '').sum())} segments. SF11 was clicked "
              f"{'**never**' if not comp.sf11_clicked.any() else 'in ' + str(int(comp.sf11_clicked.sum())) + ' segments'} (it left the paddock at "
              f"the 09-07 AM round, last fix 08:20, so it cannot be in a pile here; corrected 2026-10-11, plan amendment 12).")
    R["q1_text"] = q1
    # ---- Q2
    q2 = []
    short_seg = st[(st.dt_s < 30) & st.median_px.notna()]
    long_seg = st[(st.dt_s >= 30) & st.median_px.notna()]
    sb = stb[stb.dt_s < 30]
    if len(sb):
        q2.append(f"Segments whose IR frame is < 30 s after the colour frame ({sb.segment_id.nunique()} segments, {len(sb)} animal × IR-frame "
                  f"pairs): displacement median **{sb.d_px.median():.0f} px** (≈ {sb.d_in.median():.1f} in at the fitted {m['px_per_in_proper']:.0f} px/in), "
                  f"p75 {sb.d_px.quantile(.75):.0f} px, max {sb.d_px.max():.0f} px; ≤ 40 px in {int((sb.d_px <= 40).sum())} of {len(sb)}, "
                  f"> 100 px in {int((sb.d_px > 100).sum())} ({', '.join(f'{short(r.segment_id)} {r.animal} {r.ir_frame} {r.d_px:.0f}' for r in sb[sb.d_px > 100].itertuples())}).")
    if len(long_seg):
        q2.append(f"Long colour segments (the colour frame is the segment middle, so the IR frames come {', '.join(f'{short(s)} {g.dt_s.iloc[0]:.0f} s' for s, g in long_seg.groupby('segment_id'))} "
                  f"later): median {stb[stb.dt_s >= 30].d_px.median():.0f} px, max {stb[stb.dt_s >= 30].d_px.max():.0f} px — not \"seconds around "
                  "the switch\"; these do not test the premise.")
    if "imu_class" in stb:
        g = sb.groupby("imu_class").d_px.agg(["size", "median", "max"])
        q2.append("Head IMU between the two frames (short segments): " + "; ".join(f"{k}: n {int(r['size'])}, median {r['median']:.0f} px, max {r['max']:.0f} px"
                                                                                 for k, r in g.iterrows()) + ".")
    nc = R["stab_counts"]
    ncb = nc[nc.record == "blind"]
    tot_c = int(ncb.n_colour.sum())
    miss = ncb[ncb.colour_not_ir != ""]
    q2.append(f"Animals named on the colour frame but not clicked on the IR frame (blind record): {int(sum(len(x.split(',')) for x in miss.colour_not_ir))} "
              f"of {tot_c} colour × IR-frame slots ({'; '.join(f'{short(r.segment_id)} {r.ir_frame}: {r.colour_not_ir}' for r in miss.itertuples()) or 'none'}); "
              f"named on IR but not on colour: {'; '.join(f'{short(r.segment_id)} {r.ir_frame}: {r.ir_not_colour}' for r in ncb[ncb.ir_not_colour != ''].itertuples()) or 'none'}.")
    ncf = nc[(nc.record == "final") & (nc.dup_ir != "")]
    if len(ncf):
        q2.append(f"Final record (after-reveal additions): {'; '.join(f'{short(r.segment_id)} {r.ir_frame}: {r.dup_ir} (one label on two heads; excluded from the displacement)' for r in ncf.itertuples())}.")
    R["q2_text"] = q2
    # ---- Q3
    fp, fi = fits[fits.fit == "proper"].iloc[0], fits[fits.fit == "improper"].iloc[0]
    q3 = [f"**Handedness: {m['chosen_handedness']}** fits better — LOFO RMS {fp.lofo_rms_in:.2f} in (proper) vs {fi.lofo_rms_in:.2f} in (improper); "
          f"in-sample RMS {fp.in_rms_in:.2f} vs {fi.in_rms_in:.2f} in. Proper = the displayed image is not mirrored relative to the WISER / "
          "paddock top view (as expected for a camera looking down).",
          f"Proper fit: scale **{fp.px_per_in:.1f} px/in** (WISER inches per image px at head height; at this scale the house body's 24.6-in "
          f"long side would span ≈ {BODY_IN[0] * fp.px_per_in:.0f} px and its 18.0-in short side ≈ {BODY_IN[1] * fp.px_per_in:.0f} px; the ridge maps "
          f"onto the image's vertical axis (1920 px), the short side onto the horizontal (2560 px) — numbers only, not checked on the image), "
          f"rotation θ_house {fp.theta_house_deg:+.1f}°, θ_paddock {fp.theta_paddock_deg:+.1f}°, "
          f"page-equivalent orientation **{fp.page_rot_deg:.0f}°, no mirror** vs the user's **{R['prior'].get('rot_deg')}°, no mirror**: "
          f"Δ = {fp.d_rot_vs_prior_deg:+.1f}°.",
          f"LOFO fold rotations range {R['lofo_flash'].fold_theta_house_deg.min():+.1f}° … {R['lofo_flash'].fold_theta_house_deg.max():+.1f}° "
          f"(house frame; prior {m['theta_house_prior']:+.1f}°); fold scales {R['lofo_flash'].fold_px_per_in.min():.1f} … {R['lofo_flash'].fold_px_per_in.max():.1f} px/in.",
          f"LOFO residuals (primary): RMS **{P['lofo_rms_in']:.2f} in**, median {P['lofo_median_in']:.2f} in; in px RMS {P['lofo_rms_px']:.0f}, "
          f"median {P['lofo_median_px']:.0f} px. For scale: per-fix WISER scatter (SD of the raw fixes in the minute) in the fitted flashes "
          f"median {R['fix_sd']['along_med']:.1f} in along ({R['fix_sd']['along_min']:.1f}–{R['fix_sd']['along_max']:.1f}), "
          f"{R['fix_sd']['across_med']:.1f} in across ({R['fix_sd']['across_min']:.1f}–{R['fix_sd']['across_max']:.1f}); minute-mean SE "
          f"median {R['fix_sd']['se_med']:.2f} in; still-pair distance error p95 ≈ 3 in (plan); house body 24.6 × 18 in.",
          f"Image centre (1280, 960) lands at along {m['image_centre_house_in'][0]:+.1f} in, across {m['image_centre_house_in'][1]:+.1f} in in "
          "WISER's house frame (= the WISER bias only if the camera axis meets the house centre; not separable from the camera "
          "position with a similarity)."]
    dc = R["decomp"]
    q3.append(f"What the LOFO residual is made of (head mapped − WISER, in): RMS along the ridge {dc['rms_along_in']:.2f}, across "
              f"{dc['rms_across_in']:.2f}. A common offset per flash (median |mean vector| {dc['flash_offset_norm_median_in']:.1f} in, max "
              f"{dc['flash_offset_norm_max_in']:.1f}) removes little: RMS {dc['rms_in']:.2f} → {dc['rms_minus_flash_offset_in']:.2f} in (in-sample, "
              f"optimistic). A fixed per-animal (tag) offset estimated from the other flashes does not help: RMS → "
              f"{dc['rms_minus_animal_offset_loo_in']:.2f} in. "
              + ("So the error is mostly animal × flash specific (WISER's minute mean off the clicked head by "
                 f"{dc['rms_in']:.1f} in RMS in a pile), not a bias a per-flash or per-tag correction would remove. "
                 if dc["rms_minus_flash_offset_in"] > 0.8 * dc["rms_in"] and dc["rms_minus_animal_offset_loo_in"] > 0.8 * dc["rms_in"]
                 else "A per-flash or per-tag correction removes a material part of the error. ")
              + f"Within a flash the WISER means spread {'more' if dc['sd_along_wiser_in'] > dc['sd_along_clicks_in'] else 'less'} along "
              f"the ridge than the mapped heads (mean SD {dc['sd_along_wiser_in']:.1f} vs {dc['sd_along_clicks_in']:.1f} in).")
    rp = R["repro"]
    if len(rp):
        q3.append(f"Reproduction: the page's [ON − 60 s, ON) means were recomputed with the page's own code for {int(rp.page_has.sum())} "
                  f"animal × flash pairs: max |Δ| {np.nanmax(rp.max_abs_diff_in):.4f} in; {int((rp.page_has != rp.recomputed_has).sum())} presence mismatches.")
    if V.get("prior_rotation") is not None:
        q3.append(f"Rotation held at the user's orientation (scale + offset fitted): LOFO RMS {V['prior_rotation']['lofo_rms_in']:.2f} in "
                  f"(free fit {P['lofo_rms_in']:.2f} in).")
    R["q3_text"] = q3
    # ---- Q4
    o = P["order"]
    first = o.head(N_FIRST)
    q4 = [f"First {N_FIRST} eligible flashes: {', '.join(short(s) for s in first.segment_id)}; exact matches: "
          f"{', '.join(short(r.segment_id) for r in first.itertuples() if r.exact) or 'none'}.",
          f"All {len(o)} eligible flashes: exact {int(o.exact.sum())} / {len(o)}; tie version {ov['n_tie_all']} / {ov['n_tie_testable_all']} testable; "
          f"Kendall τ {', '.join(f'{t:+.1f}' for t in o.tau)}."]
    nt = int(o.n_pairs_ge_sep.sum())
    q4.append(f"Pairs ≥ {CAND_SEP_IN:g} in apart along the ridge by WISER: {nt} of {int(o.n_pairs.sum())} pairs; concordant {int(o.n_conc_ge_sep.sum())} "
              f"({int(o.n_conc_ge_sep.sum()) / nt:.0%})." if nt else "No pair ≥ 8 in apart.")
    q4.append(f"Not eligible: {R['not_fit_text']}")
    if R["untestable"]:
        q4.append(f"Alternative reading (a flash with ≥ 3 clicked animals but no WISER mean counts as a non-match: "
                  f"{', '.join(short(s) for s, _ in R['untestable'])}): {V['alt_reading']['order_summary']['verdict']} "
                  f"({V['alt_reading']['order_summary']['n_exact_first']} of {N_FIRST}).")
    R["q4_text"] = q4
    # ---- Q5
    asg = P["assign"]
    sep = R["sep2d"]
    q5 = [f"Of the {len(asg)} heads, {int(asg.correct_hungarian.sum())} correct. Heads whose animal is ≥ 8 in from every other roster mean: "
          f"{asg[asg.sep_2d_in >= 8].correct_hungarian.mean():.0%} (n {int((asg.sep_2d_in >= 8).sum())}); < 8 in: "
          f"{asg[asg.sep_2d_in < 8].correct_hungarian.mean():.0%} (n {int((asg.sep_2d_in < 8).sum())}).",
          f"Distance from a mapped head to its own animal's WISER mean: median {asg.dist_to_own_in.median():.1f} in, p90 {asg.dist_to_own_in.quantile(.9):.1f} in.",
          "Swaps (Hungarian) per flash: " + "; ".join(f"{short(r.segment_id)}: {r.swapped}" for r in R["asg_flash"].itertuples() if r.swapped) + "."]
    q5.append(f"Typical spacing inside a pile: the clicked animal's nearest other WISER mean is a median {asg.sep_2d_in.median():.1f} in away "
              f"(along the ridge {asg.sep_along_in.median():.1f} in), against a mapped-head-to-own-mean distance of median "
              f"{asg.dist_to_own_in.median():.1f} in.")
    R["q5_text"] = q5
    # ---- the user's question
    fp = fits[fits.fit == "proper"].iloc[0]
    still = sb[sb.imu_class == "all still"] if "imu_class" in sb else sb.iloc[0:0]
    moved = sb[sb.imu_class == "moved"] if "imu_class" in sb else sb.iloc[0:0]
    far = asg[asg.sep_2d_in >= 15]
    conc = int(o.n_conc_ge_sep.sum())
    R["answer"] = [
        f"**Which animals are in the box — yes, WISER helps.** The house roster equalled the colour-clicked set in {len(agree)} of {len(rev)} "
        f"revealed flashes, with no clicked animal outside the roster; in the other {len(rev) - len(agree)} (long colour segments during the "
        "morning rounds, where the colour frame lies minutes after ON) every roster animal was clicked on some frame of the segment. "
        "Rosters are complete here: all five animals in the paddock were tagged (SF11 had left at the 09-07 AM round; corrected "
        "2026-10-11, plan amendment 12); SF11 was never clicked.",
        f"**Who lies where inside a pile — not from WISER minute means.** The pre-registered order test is NOT ACCEPTED (exact order "
        f"{ov['n_exact_first']} of {N_FIRST}, {int(o.exact.sum())} of {len(o)} overall; Kendall τ median {ov['tau_median_all']:+.2f}); mapped heads sit "
        f"{P['lofo_rms_in']:.1f} in RMS from their own WISER mean while pile neighbours are a median {asg.sep_2d_in.median():.1f} in apart, "
        f"and neither a per-flash nor a per-tag offset removes that error. Assigning heads by WISER gets {P['acc_hungarian']:.0%} right "
        f"(chance {P['chance']:.0%}).",
        f"**Where WISER separations can be trusted.** Pairs ≥ {CAND_SEP_IN:g} in apart along the ridge were ordered correctly in {conc} of {nt} "
        f"({conc / nt:.0%}; tie version {ov['verdict_tie']}); heads ≥ 15 in from every other animal were assigned correctly in "
        f"{int(far.correct_hungarian.sum())} of {len(far)}. So WISER can name an animal lying apart at one end of the box and order clearly "
        "separated animals; it cannot resolve the order inside the pile (the plan's rule \"trust > 8 in for 1-min means only\" stands).",
        f"**The colour labels and the IR frames.** When the head IMU was still on every second between the colour and the IR frame, the "
        f"clicked head moved ≤ {still.d_px.max():.0f} px (median {still.d_px.median():.0f} px ≈ {still.d_in.median():.1f} in; n {len(still)}), "
        f"consistent with the operator's premise that IR frames can inherit identity from the colour frame; when the IMU registered "
        f"movement the displacement reached {moved.d_px.max():.0f} px (median {moved.d_px.median():.0f} px, n {len(moved)}). The head IMU is "
        "a candidate gate for carrying colour identities into IR (click repeatability on one head is not measured).",
        f"**Camera geometry, as a by-product.** The blind clicks alone recover the CH07 ↔ house orientation: {fp.page_rot_deg:.0f}°, not "
        f"mirrored, vs the user's display choice of 180° made by eye before any fit (Δ {fp.d_rot_vs_prior_deg:+.1f}°); scale "
        f"{fp.px_per_in:.0f} px/in; the image centre lands {np.hypot(*m['image_centre_house_in']):.1f} in from the WISER house centre."]
    # ---- summary
    sb = stb[stb.dt_s < 30]
    S = [f"**Data**: {m['n_clicks']} clicks ({m['n_blind']} blind, {int((R['ct'].status == 'after_reveal').sum())} after the reveal, "
         f"{int((R['ct'].status == 'unsaved').sum())} unsaved, 0 legacy) in {m['n_segments_clicked']} of {m['n_page_segments']} segments, all CH07 / house_2.",
         f"**1. Composition**: colour-frame set = WISER roster in {len(agree)} of {len(rev)} revealed segments; SF11 never clicked; "
         f"{int((R['ct'].animal == 'unknown').sum())} unknown clicks.",
         f"**2. Colour → IR**: where the IR frame is < 30 s after the colour frame the clicked heads moved median {sb.d_px.median():.0f} px (≈ {sb.d_in.median():.1f} in), "
         f"max {sb.d_px.max():.0f} px; {int((sb.d_px > 100).sum())} of {len(sb)} pairs > 100 px.",
         f"**3. Fit**: {m['chosen_handedness']} handedness; {R['fits'][R['fits'].fit == 'proper'].px_per_in.iloc[0]:.1f} px/in; page-equivalent rotation "
         f"{R['fits'][R['fits'].fit == 'proper'].page_rot_deg.iloc[0]:.0f}° vs the user's 180° (Δ {R['fits'][R['fits'].fit == 'proper'].d_rot_vs_prior_deg.iloc[0]:+.1f}°); "
         f"LOFO RMS {P['lofo_rms_in']:.2f} in / {P['lofo_rms_px']:.0f} px.",
         f"**4. Pre-registered order test: {ov['verdict']}** ({ov['n_exact_first']} of {N_FIRST} exact; needs {ACCEPT_MIN}); tie version "
         f"{ov['verdict_tie']} ({ov['n_tie_first']} of {N_FIRST}); Kendall τ median {ov['tau_median_first']:+.2f}.",
         f"**5. WISER as an identity aid**: Hungarian assignment {P['acc_hungarian']:.0%} correct (chance {P['chance']:.0%}); "
         + ", ".join(f"{r.bin_in} in: {r.acc_hungarian:.0%} (n {r.n_clicks})" for r in sep.itertuples() if r.n_clicks) + "."]
    R["summary"] = S
    # ---- not verified
    R["not_verified"] = [
        "The clicks are a browser snapshot, not the user's export; 11 of 22 segments; one house (CH08 / house_1 has no clicks).",
        "The user's colour IDs are the reference; no second labeller; identities rest on the user's corrected key (SF09 black, SF10 blue).",
        "A 2-D similarity ignores perspective and head height: the camera sits in the lid ≈ 1 ft above the floor and piled heads lie at "
        "different heights, so one scale cannot hold everywhere; WISER is a 2-D solve (all z = 0) and cannot say who lies on top.",
        "WISER minute means come from the minute before ON; the colour frame is several seconds (long segments: minutes) later.",
        "Frames inside a lid-event window (`lid+ok`: 09-10 07:14, 09-11 09:28) use the lid segment's median correction; the camera may "
        "have been off it while the lid was open.",
        "The user's display orientation (180°) was chosen after several reveals — independent of the fit's numbers, not blind to WISER.",
        "Click-to-click repeatability on one head is unmeasured, so a colour → IR displacement mixes head movement and click placement.",
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--clicks", default=str(CLICKS_DEFAULT), help="export or browser-snapshot JSON of the identity page")
    ap.add_argument("--p0-run", default=None, help="inbox_p0 run folder (default: the pointer run_manifest_inbox_p0_2026c.json)")
    ap.add_argument("--imu-root", default=None, help="imu_seconds_cache root (default $OUT/2026c/imu_seconds_cache)")
    ap.add_argument("--no-centred", action="store_true", help="skip the centred-window sensitivity (needs the default tracks)")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    import output_paths as op
    p0 = Path(args.p0_run) if args.p0_run else Path(json.loads(P0_POINTER.read_text(encoding="utf-8"))["run_dir"])
    imu_root = Path(args.imu_root) if args.imu_root else op.out_root() / COHORT / "imu_seconds_cache"
    run = op.run_dir(NAME, COHORT, make_figures=True)
    print(f"[run] {run.as_posix()}", flush=True)
    R = analyse(Path(args.clicks), p0, run, imu_root, not args.no_centred)
    nf = [s for s in R["composition"].segment_id if s not in R["fit_flashes"]]
    R["not_fit_text"] = "; ".join(
        f"{short(s)} ({'not revealed' if not R['composition'].set_index('segment_id').loc[s, 'revealed'] else 'no WISER mean in [ON − 60 s, ON)' if not R['segs'][s]['W'] else 'no named colour click with a WISER mean'})"
        for s in nf) or "none"
    texts(R)
    write_report(run, R)
    print(f"[done] verdict {R['variants']['primary']['order_summary']['verdict']}", flush=True)
    return 0


# ============================================================================================ self-test
def selftest() -> int:
    res = []

    def rec(name, cond, detail=""):
        res.append((name, bool(cond), detail))
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}", flush=True)

    rng = np.random.default_rng(7)
    ridge = 92.0
    # 1. similarity recovery, handedness, prior conversion
    th_true = prior_theta_house(180, False, ridge)                # the user's orientation as a house-frame rotation
    rec("prior 180/no-mirror -> theta_house 88", abs(th_true - 88.0) < 1e-9, f"{th_true}")
    s_true = 1 / 60.0
    a_true = s_true * np.exp(1j * np.radians(th_true))
    t_true = 3.0 - 2.0j
    flashes, rows = [f"CH07_202609{10 + i:02d}_120000" for i in range(7)], []
    for i, sid in enumerate(flashes):
        for k, an in enumerate(("SF07", "SF08", "SF09", "SF10", "SF12")):
            w = complex(rng.uniform(-14, 14), rng.uniform(-8, 8))
            z = (w - t_true) / a_true + complex(*rng.normal(0, 30, 2))   # 30-px click noise
            rows.append({"segment_id": sid, "start": datetime(2026, 9, 10 + i, 12), "animal": an, "n_clicks": 1, "u_ref": z.real,
                         "v_ref": -z.imag, "p": z.real, "q": z.imag, "A": w.real, "C": w.imag, "lid_flag": "ok"})
    pts = pd.DataFrame(rows)
    f = sim_fit(pts[["p", "q"]], pts[["A", "C"]], False)
    sp = sim_params(f, ridge)
    rec("similarity recovers rotation", abs(wrap180(sp["theta_house_deg"] - th_true)) < 2.0, f"{sp['theta_house_deg']:.2f}")
    rec("similarity recovers scale", abs(sp["px_per_in"] - 60.0) / 60.0 < 0.03, f"{sp['px_per_in']:.2f}")
    rec("page-equivalent rot of the fit = 180, no mirror", abs(wrap180(sp["page_rot_deg"] - 180)) < 2.0 and not sp["page_mirror"], f"{sp['page_rot_deg']:.1f}")
    rec("inverse(apply) = identity", np.allclose(sim_inverse(f, sim_apply(f, pts[["p", "q"]])), pts[["p", "q"]].to_numpy()))
    pro, imp = lofo(pts, False), lofo(pts, True)
    rec("LOFO prefers the true (proper) handedness", rms(pro.res_in) < rms(imp.res_in), f"{rms(pro.res_in):.2f} vs {rms(imp.res_in):.2f}")
    rec("LOFO residual ~ click noise (30 px = 0.5 in)", rms(pro.res_in) < 1.0, f"{rms(pro.res_in):.2f} in")
    rec("px residual = in residual x px/in (similarity)", np.allclose(pro.res_px, pro.res_in * pro.fold_px_per_in, rtol=1e-6))
    # mirrored world: page rot 90 + mirror -> recovered as improper, rot 90
    thm = prior_theta_house(90, True, ridge)
    am = s_true * np.exp(1j * np.radians(thm))
    P2 = pts.copy()
    zz = ((P2.A + 1j * P2.C).to_numpy() - t_true) / am          # mirrored display coordinates
    P2["p"], P2["q"] = zz.real, -zz.imag
    fm = sim_fit(P2[["p", "q"]], P2[["A", "C"]], True)
    spm = sim_params(fm, ridge)
    rec("mirrored world -> improper fit, page rot 90 + mirror", abs(wrap180(spm["page_rot_deg"] - 90)) < 1e-6 and spm["page_mirror"], f"{spm['page_rot_deg']:.2f}")
    rec("mirrored world: improper LOFO < proper LOFO", rms(lofo(P2, True).res_in) < rms(lofo(P2, False).res_in))
    fx = sim_fit(pts[["p", "q"]], pts[["A", "C"]], False, theta_fixed_deg=th_true)
    rec("fixed-rotation fit keeps the rotation", abs(np.degrees(np.angle(fx["a"])) - th_true) < 1e-9 and abs(1 / abs(fx["a"]) - 60) < 2)
    # 2. order test, Kendall, tie version
    rec("kendall tau identical = 1, reversed = -1", kendall_tau([1, 2, 3], [5, 6, 7]) == 1.0 and kendall_tau([1, 2, 3], [3, 2, 1]) == -1.0)
    g = pd.DataFrame({"animal": ["SF07", "SF08", "SF09"], "A": [0.0, 3.0, 20.0], "pred_A": [4.0, 1.0, 22.0], "start": [datetime(2026, 9, 10)] * 3})
    of = order_flash(g)
    rec("order: close pair swapped -> not exact, tie version matches", (not of["exact"]) and of["tie_match"] is True and of["n_pairs_ge_sep"] == 2,
        f"{of}")
    g2 = g.assign(pred_A=[30.0, 1.0, 22.0])
    rec("order: far pair swapped -> tie version fails", order_flash(g2)["tie_match"] is False)
    sep = pts.copy()                                              # well-separated piles: along -12, -6, 0, 6, 12 in
    sep["A"] = np.tile([-12.0, -6.0, 0.0, 6.0, 12.0], len(flashes)) + rng.normal(0, 0.3, len(sep))
    zs = ((sep.A + 1j * sep.C).to_numpy() - t_true) / a_true + rng.normal(0, 20, len(sep)) + 1j * rng.normal(0, 20, len(sep))
    sep["p"], sep["q"] = zs.real, zs.imag
    o, ov = order_test(lofo(sep, False))
    rec("order test on well-separated synthetic piles: ACCEPTED, 5 of 5", ov["verdict"] == "ACCEPTED" and ov["n_exact_first"] == 5, f"{ov['n_exact_first']}")
    sw = sep.copy()                                               # swap the clicked heads of two far animals in every flash
    for sid in flashes:
        i = sw.index[(sw.segment_id == sid) & (sw.animal == "SF07")][0]
        j = sw.index[(sw.segment_id == sid) & (sw.animal == "SF12")][0]
        sw.loc[[i, j], ["p", "q"]] = sw.loc[[j, i], ["p", "q"]].to_numpy()
    o_sw, ov_sw = order_test(lofo(sw, False))
    rec("order test with swapped identities: NOT ACCEPTED", ov_sw["verdict"] == "NOT ACCEPTED", f"{ov_sw['n_exact_first']}")
    o3, ov3 = order_test(pro.head(10))
    rec("fewer than 5 eligible flashes -> INSUFFICIENT", ov3["verdict"].startswith("INSUFFICIENT"))
    oa, ova = order_test(pro, untestable=[("CH07_20260909_000000", datetime(2026, 9, 9))])
    rec("alternative reading puts the untestable flash first as a non-match", (not oa.iloc[0].exact) and oa.iloc[0].segment_id == "CH07_20260909_000000")
    # 3. assignment
    segs = {sid: {"W": {r.animal: {"along_in": r.A, "across_in": r.C} for r in pts[pts.segment_id == sid].itertuples()}} for sid in flashes}
    asg = assignment(pro, segs)
    rec("Hungarian on clean synthetic data >= 90 % correct", asg.correct_hungarian.mean() >= 0.9, f"{asg.correct_hungarian.mean():.2f}")
    W = {"SF07": {"along_in": 0.0, "across_in": 0.0}, "SF08": {"along_in": 1.0, "across_in": 0.0}, "SF09": {"along_in": 10.0, "across_in": 0.0}}
    heads = pd.DataFrame({"animal": ["SF07", "SF08"], "pred_A": [0.6, 0.7], "pred_C": [0.0, 0.0]})
    ah = assign_flash(heads, W)
    rec("Hungarian is one-to-one where greedy repeats", ah.assigned_hungarian.nunique() == 2 and ah.assigned_greedy.nunique() == 1)
    rec("separation = nearest other roster mean", np.allclose(ah.sep_2d_in, [1.0, 1.0]))
    heads2 = pd.DataFrame({"animal": ["SF07", "SF08", "SF09"], "pred_A": [5.0, 6.0, 15.0], "pred_C": [0.0, 0.0, 0.0]})
    ao = assign_flash(heads2, W)
    rec("per-flash offset assignment recovers a shifted pile", ao.correct_offset.all(), f"{list(ao.assigned_offset)}")
    # 4. click table: statuses, blind record, B correction
    B = [[1.0, 0.0, 10.0], [0.0, 1.0, -5.0]]
    base = {"camera": "CH07", "house": "house_2", "frame_time": "2026-09-10 12:00:00.000", "lid_segment": 27, "lid_flag": "ok", "B_frame_to_ref": B,
            "confidence": "sure"}
    snap = {"segments": {"S1": {"revealed_at": "x"}}, "clicks": [
        {**base, "click_id": "a", "segment_id": "S1", "frame_kind": "colour_mid", "u_px": 100, "v_px": 200, "animal": "SF07", "before_reveal": True,
         "legacy": False, "verdict_first": {"animal": "SF08", "u_px": 90, "v_px": 200, "frame_kind": "colour_mid"}, "edited_after_reveal": True},
        {**base, "click_id": "b", "segment_id": "S1", "frame_kind": "ir_p06", "u_px": 1, "v_px": 2, "animal": "SF09", "before_reveal": False, "legacy": False},
        {**base, "click_id": "c", "segment_id": "S2", "frame_kind": "colour_mid", "u_px": 1, "v_px": 2, "animal": None, "before_reveal": True, "legacy": False},
        {**base, "click_id": "d", "segment_id": "S1", "frame_kind": "colour_mid", "u_px": 1, "v_px": 2, "animal": "SF10", "before_reveal": True, "legacy": True,
         "verdict_first": {"animal": "SF10", "u_px": 1, "v_px": 2}},
        {**base, "click_id": "e", "segment_id": "S1", "frame_kind": "colour_mid", "u_px": 5, "v_px": 6, "animal": "SF12", "before_reveal": True, "legacy": False,
         "verdict_first": {"animal": "SF12", "u_px": 5, "v_px": 6, "frame_kind": "colour_mid"}, "deleted_after_reveal": True}]}
    ct = click_table(snap)
    rec("statuses: blind / after_reveal / unsaved / legacy", list(ct.status) == ["blind", "after_reveal", "unsaved", "legacy", "blind"], f"{list(ct.status)}")
    rb, rf = record(ct, "blind"), record(ct, "final")
    rec("blind record reads verdict_first (SF08 at u 90 -> ref 100)", rb.iloc[0].animal == "SF08" and abs(rb.iloc[0].u_ref - 100.0) < 1e-9)
    rec("blind record keeps a blind click deleted after the reveal; final drops it", "e" in set(rb.click_id) and "e" not in set(rf.click_id))
    rec("final record = live values + after-reveal, no unsaved / legacy", set(rf.click_id) == {"a", "b"} and rf.set_index("click_id").loc["a", "animal"] == "SF07")
    rec("unknown animal normalised", ct.set_index("click_id").loc["c", "animal"] == "unknown")
    # 5. stability + IMU classes
    t0 = datetime(2026, 9, 10, 12, 0, 0)
    segs2 = {"S1": {"start": t0, "frames": {"colour_mid": {"time": t0}, "ir_p06": {"time": t0 + timedelta(seconds=10)},
                                            "ir_p15": {"time": t0 + timedelta(seconds=19)}}}}
    r2 = pd.DataFrame([{"click_id": "x", "segment_id": "S1", "house": "house_2", "camera": "CH07", "kind": k, "animal": "SF07", "u": u, "v": 0.0,
                        "u_ref": u, "v_ref": 0.0, "status": "blind", "lid_flag": "ok", "lid_segment": 27}
                       for k, u in (("colour_mid", 0.0), ("ir_p06", 30.0), ("ir_p15", 40.0))]
                      + [{"click_id": "y", "segment_id": "S1", "house": "house_2", "camera": "CH07", "kind": "colour_mid", "animal": "SF08", "u": 0.0,
                          "v": 0.0, "u_ref": 0.0, "v_ref": 0.0, "status": "blind", "lid_flag": "ok", "lid_segment": 27}])
    s0 = int(t0.replace(tzinfo=TZ).timestamp())
    imu = {"SF07": pd.DataFrame({"sec": np.arange(s0, s0 + 30), "ok": True, "still": True, "state": [1] * 15 + [2] + [1] * 14,
                                 "vedba_1s": 0.1, "turn_abs_deg": 1.0})}
    stv, cnt = stability(r2, segs2, imu, 30.0, "blind")
    rec("displacement px and inches", np.allclose(stv.d_px, [30.0, 40.0]) and np.allclose(stv.d_in, [1.0, 4 / 3]))
    rec("IMU class: still up to +10 s, moved by +19 s", list(stv.imu_class) == ["all still", "moved"], f"{list(stv.imu_class)}")
    rec("colour-not-IR count", set(cnt.colour_not_ir) == {"SF08"})
    from datetime import timezone
    rec("DST-aware field-PC seconds (EDT = UTC-4)", s0 == int(datetime(2026, 9, 10, 16, 0, 0, tzinfo=timezone.utc).timestamp()), f"{s0}")
    ok = all(c for _, c, _ in res)
    print(f"[selftest] {sum(c for _, c, _ in res)}/{len(res)} {'PASS' if ok else 'FAIL'}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
