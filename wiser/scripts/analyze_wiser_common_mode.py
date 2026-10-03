r"""WISER common-mode error across tags and pairwise-distance precision (cohort 2026c) - step C.

Plan: implementation_plan/2026-10-03-wiser-common-mode.md (approved by the user 2026-10-03, step C of A -> B -> C).
Report (full Definitions section): results/<cohort>/wiser_baseline/reports/wiser_baseline_common_mode_<cohort>.md

Question: is part of the WISER still error shared between tags (an anchor-side common mode)? A shared error cannot be
removed by a per-tag smoother, but it cancels in inter-animal distances and can be estimated from other tags that are known
to be still (the still rats act as reference stations, as in differential GPS).

  joint stillness  pairs of the failure audit's primary >= 30-s certified still segments (both heads still): trimmed
                   spans intersected, kept when >= 30 s. Residual e = the 1-s (or 10-s) median of a method's fixes minus
                   the segment's truth (median raw fix), on the integer-second grid of the IMU-aligned clock
  C1               cross-tag residual correlation per axis and as a vector, tr(C_ij) / sqrt(tr C_ii tr C_jj), lags 0, +-1,
                   +-2 s, 1-s and 10-s scales, by zone pairing x calm/rain x day/night; anchors_list stratification;
                   shared excursions (both tags >= 12 in) and the anchors lost during them
  C2               pairwise-distance error d_ij - d_truth: SD, p95 / p99 of |error|, R = SD_obs / SD_indep, by zone pairing
                   and truth-distance band
  C3               leave-one-tag-out differential correction from the other certified-still tags (variant z: same zone,
                   a: any zone) for raw-1-s and B2-1-s inputs; paired block-bootstrap of the relative change; coverage
  verdict          pre-registered in the plan: material / not material / material for raw only

Inputs (all read-only): the failure audit's run (tables/segments.csv, tracks/*.npz, tables/still_fixes.csv.gz) and the
WISER fix caches (anchors_list). No SQLite, no IMU, no Kalman run. analyze_wiser_failure_audit.py is imported, never
modified.

Usage:
  python wiser/scripts/analyze_wiser_common_mode.py --cohort 2026c [--workers 6]
  python wiser/scripts/analyze_wiser_common_mode.py --report-only <run_dir>   # re-aggregate / re-render from saved seconds
  python wiser/scripts/analyze_wiser_common_mode.py --selftest                # synthetic data, no field data
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiser" / "src"))
sys.path.insert(0, str(REPO / "wiser" / "scripts"))
sys.path.append(str(REPO / "ephys"))
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import analyze_wiser_failure_audit as FA  # noqa: E402  (roll_median, block bootstrap, helpers; unmodified)

C = FA.C  # analyze_imu_wiser_calibration (to_ms, true_runs, git_commit; unmodified)

DIRECTION = "wiser_baseline"
NAME = "wiser_common_mode"
STEM = f"{DIRECTION}_common_mode"
PLAN = "implementation_plan/2026-10-03-wiser-common-mode.md"
DRIVER = "wiser/scripts/analyze_wiser_common_mode.py"
METHODS = ["raw", "B1", "B2", "B2p"]
SCALES = {"1s": "e1", "10s": "e10"}
ZP = ["same_house", "diff_house", "house_outside", "both_outside"]
ZPG = ["all", "same_zone"] + ZP
SETS = ["all", "calm", "rain"]
KINDS = ["all", "day", "night"]
BANDS = ["all", "<14", "14-48", ">48"]
PAD = 3                       # empty dense positions between pair overlaps (> max |lag|)
LABEL = {"raw": "raw", "B1": "B1 median-7", "B2": "B2 robust CV", "B2p": "B2′ (p)"}
ZLABEL = {"all": "all pairings", "same_zone": "same zone", "same_house": "same house", "diff_house": "different houses",
          "house_outside": "house–outside", "both_outside": "both outside"}
# categorical slots of the validated default palette (dataviz skill; ΔE checks pass), fixed order, plus markers
COL = {"raw": "#2a78d6", "B1": "#eb6834", "B2": "#1baf7a", "B2p": "#eda100"}
MARK = {"raw": "o", "B1": "s", "B2": "D", "B2p": "^"}
TAGCOL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]


def log_to(fh, msg: str) -> None:
    print(msg, flush=True)
    if fh is not None:
        fh.write(msg + "\n")
        fh.flush()


# ====================================================================================================== config / inputs
def load_cfg(cohort: str, path: str | None = None) -> dict:
    cp = Path(path) if path else REPO / "wiser" / "configs" / f"wiser_common_mode_{cohort}.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    cfg["_path"] = str(cp)
    cfg["_cohort"] = cohort
    cfg["_audit"] = json.loads((REPO / cfg["audit_config"]).read_text(encoding="utf-8"))
    return cfg


def period_lo(cfg: dict, pkey: str) -> int:
    return C.to_ms(cfg["_audit"]["periods"][pkey]["start"], cfg["tz"])


def load_segments(cfg: dict, S: pd.DataFrame | None = None) -> pd.DataFrame:
    """The audit's primary, scored, >= 30-s certified still segments with trimmed spans (ms), zone, block."""
    if S is None:
        S = pd.read_csv(Path(cfg["audit_run"]) / "tables" / "segments.csv")
    S = S.copy()
    for c in ("primary", "scored", "ge30"):
        S[c] = S[c].astype(str).str.lower().isin(["true", "1"])
    S = S[S.primary & S.scored & S.ge30].copy()
    trim = float(cfg["_audit"]["still"]["trim_s"]) * 1000.0
    S["ts_ms"] = S.t0_ms + trim
    S["te_ms"] = S.t1_ms - trim
    S["lo_ms"] = S.period.map(lambda p: period_lo(cfg, p)).astype(np.int64)
    S["mid_ms"] = 0.5 * (S.ts_ms + S.te_ms)
    S["blk"] = ((S.mid_ms - S.lo_ms) // (float(cfg["bootstrap"]["block_s"]) * 1000.0)).astype(np.int64)
    S["zd"] = S["zone_detail"].astype(str)
    S["zone2"] = S["zd"].map(FA.zone2)
    return S.sort_values(["period", "animal", "ts_ms"]).reset_index(drop=True)


def parse_bits(lists: pd.Series, pos: dict) -> np.ndarray:
    """anchors_list strings (',1,2,5,') -> int64 bitmask over the anchor positions pos (id -> bit)."""
    s = lists.fillna("").astype(str)
    uni = s.unique()
    lut = {}
    for u in uni:
        b = 0
        for x in u.split(","):
            x = x.strip()
            if x:
                b |= 1 << pos[int(x)]
        lut[u] = b
    return s.map(lut).to_numpy(np.int64)


def ids_job(job: dict) -> list:
    f = pd.read_csv(job["path"], usecols=["anchors_list"])
    ids = set()
    for u in f.anchors_list.dropna().astype(str).unique():
        ids.update(int(x) for x in u.split(",") if x.strip())
    return sorted(ids)


# ====================================================================================================== per-tag seconds
def seconds_for_tag(t: np.ndarray, tracks: dict, a_used: np.ndarray, bits: np.ndarray, segs: pd.DataFrame, methods: list,
                    n_bits: int, gp: dict, anc: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """1-s and 10-s residuals of every method on the integer-second grid of each segment.

    t (s, relative to the period start, sorted) = IMU-aligned fix times; tracks[m] (n, 2) in; a_used (n,) anchors_used;
    bits (n,) anchors_list bitmask; segs rows: seg_id, ts, te (trimmed span, s rel.), truth_x, truth_y, n_fix (audit).
    A 1-s value at g = coordinate-wise median of the fixes in [g - h1, g + h1) (>= min_fix_1s), a 10-s value the median in
    [g - h10, g + h10) (>= min_fix_10s); windows wholly inside [ts, te). Residual = value - truth."""
    h1, h10 = float(gp["half_1s"]), float(gp["half_10s"])
    nb = int(n_bits)
    sh_bits = np.arange(nb, dtype=np.int64)
    pres = ((bits[:, None] >> sh_bits) & 1).astype(np.int64)
    cpres = np.vstack([np.zeros((1, nb), np.int64), np.cumsum(pres, axis=0)])
    ca = np.r_[0.0, np.cumsum(np.asarray(a_used, float))]
    parts, info = [], []
    for s in segs.itertuples(index=False):
        i0, i1 = np.searchsorted(t, [s.ts, s.te])
        nfix = int(i1 - i0)
        truth = np.array([s.truth_x, s.truth_y], float)
        refset = 0
        tr_dev = np.nan
        if nfix:
            tr_dev = float(np.hypot(*(np.median(tracks["raw"][i0:i1], axis=0) - truth)))
            share = (cpres[i1] - cpres[i0]) / nfix
            for k in np.flatnonzero(share >= float(anc["ref_share"])):
                refset |= 1 << int(k)
        g = np.arange(math.ceil(s.ts + h1 - 1e-9), math.floor(s.te - h1 + 1e-9) + 1, dtype=np.float64)
        info.append({"seg_id": s.seg_id, "n_fix": nfix, "n_fix_audit": int(getattr(s, "n_fix", -1)), "truth_dev_in": tr_dev,
                     "ref_mask": int(refset), "n_ref_anchors": int(bin(refset).count("1")), "n_grid": int(len(g))})
        if not len(g) or nfix == 0:
            continue
        j0 = np.searchsorted(t, g - h1)
        j1 = np.searchsorted(t, g + h1)
        cnt = j1 - j0
        shr = (cpres[j1] - cpres[j0]) / np.maximum(cnt, 1)[:, None]
        inref = ((refset >> sh_bits) & 1).astype(bool)
        lostb = (shr < float(anc["lost_share"])) & inref[None, :] & (cnt > 0)[:, None]
        lost = (lostb.astype(np.int64) << sh_bits).sum(axis=1)
        amean = (ca[j1] - ca[j0]) / np.maximum(cnt, 1)
        amean[cnt == 0] = np.nan
        ok10 = (g - h10 >= s.ts) & (g + h10 <= s.te)
        ts_ = t[i0:i1]
        rec = {"seg_id": np.repeat(s.seg_id, len(g)), "g": g.astype(np.int64), "n1": cnt.astype(np.int32),
               "a_mean": amean.astype(np.float32), "lost": lost}
        for m in methods:
            p = tracks[m][i0:i1]
            m1, _ = FA.roll_median(ts_, p, g, h1, int(gp["min_fix_1s"]))
            e1 = m1 - truth
            e10 = np.full((len(g), 2), np.nan)
            if ok10.any():
                m10, _ = FA.roll_median(ts_, p, g[ok10], h10, int(gp["min_fix_10s"]))
                e10[ok10] = m10 - truth
            rec[f"e1x_{m}"], rec[f"e1y_{m}"] = e1[:, 0].astype(np.float32), e1[:, 1].astype(np.float32)
            rec[f"e10x_{m}"], rec[f"e10y_{m}"] = e10[:, 0].astype(np.float32), e10[:, 1].astype(np.float32)
        parts.append(pd.DataFrame(rec))
    return (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()), pd.DataFrame(info)


def tag_job(job: dict) -> dict:
    """One animal-period: load the audit's track + the fix cache's anchors_list, compute the seconds table."""
    t0 = time.time()
    cfg, animal, pkey = job["cfg"], job["animal"], job["pkey"]
    run = Path(cfg["audit_run"])
    lo = int(job["lo"])
    methods = cfg["methods"]
    with np.load(run / "tracks" / f"{animal}_{pkey}.npz") as z:
        t_ms = z["t_ms"].astype(np.int64)
        t_al = z["t_al_ms"].astype(np.float64)
        a_used = z["anchors"].astype(np.float64)
        tracks = {m: z[m].astype(np.float64) for m in methods}
    fx = pd.read_csv(Path(cfg["fix_cache_root"]) / FA.period_cache_key(pkey) / f"{animal}.csv.gz",
                     usecols=["t_ms", "anchors_used", "anchors_list"])
    fx = fx.drop_duplicates("t_ms").set_index("t_ms")
    miss = int((~pd.Index(t_ms).isin(fx.index)).sum())
    fx = fx.reindex(t_ms)
    au_mismatch = int((fx["anchors_used"].to_numpy(float) != a_used).sum())
    bits = parse_bits(fx["anchors_list"], job["pos"])
    t = (t_al - lo) / 1000.0
    segs = pd.DataFrame(job["segs"])
    segs["ts"] = (segs.ts_ms - lo) / 1000.0
    segs["te"] = (segs.te_ms - lo) / 1000.0
    sec, info = seconds_for_tag(t, tracks, a_used, bits, segs, methods, len(job["pos"]), cfg["grid"], cfg["anchors"])
    if len(sec):
        sec.insert(0, "period", pkey)
        sec.insert(0, "animal", animal)
        sec["g_ms"] = lo + sec.pop("g") * 1000
    info.insert(0, "period", pkey)
    info.insert(0, "animal", animal)
    ctx = None
    cc = cfg.get("cluster_case") or {}
    if cc.get("period") == pkey:
        T = C.to_ms(cc["time"], cfg["tz"])
        hw = (float(cc["half_window_s"]) + 60.0) * 1000.0
        sel = (t_al >= T - hw) & (t_al <= T + hw)
        ctx = pd.DataFrame({"animal": animal, "t_al_ms": t_al[sel], "raw_x": tracks["raw"][sel, 0], "raw_y": tracks["raw"][sel, 1],
                            "B2_x": tracks["B2"][sel, 0], "B2_y": tracks["B2"][sel, 1], "anchors_used": a_used[sel],
                            "lost_list": fx["anchors_list"].to_numpy()[sel]})
    return {"animal": animal, "pkey": pkey, "sec": sec, "info": info, "ctx": ctx, "n_fix": int(len(t_ms)), "cache_missing": miss,
            "anchors_used_mismatch": au_mismatch, "runtime_s": round(time.time() - t0, 1)}


def _tag_job_safe(job: dict) -> dict:
    try:
        return tag_job(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(), "animal": job["animal"], "pkey": job["pkey"]}


# ====================================================================================================== pairs
def zone_pairing(za: str, zb: str) -> str:
    ha, hb = str(za).startswith("house"), str(zb).startswith("house")
    if ha and hb:
        return "same_house" if za == zb else "diff_house"
    if ha or hb:
        return "house_outside"
    return "both_outside"


def overlap_spans(A: np.ndarray, B: np.ndarray, min_s: float):
    """A (k, 2), B (l, 2) trimmed spans (ms) -> indices (ia, ib) and the intersection [s, e) of every pair with e - s >= min_s."""
    A = np.asarray(A, float).reshape(-1, 2)
    B = np.asarray(B, float).reshape(-1, 2)
    if not len(A) or not len(B):
        z = np.zeros(0, np.int64)
        return z, z, np.zeros(0), np.zeros(0)
    s = np.maximum(A[:, None, 0], B[None, :, 0])
    e = np.minimum(A[:, None, 1], B[None, :, 1])
    ia, ib = np.nonzero(e - s >= float(min_s) * 1000.0 - 1e-6)
    return ia, ib, s[ia, ib], e[ia, ib]


def build_pairs(SEC: pd.DataFrame, SEGS: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Joint-stillness pair overlaps (OV) and pair-seconds (PS; suffix _i = first animal, _j = second)."""
    animals = sorted(SEGS.animal.unique())
    ecol = [c for c in SEC.columns if c.startswith("e1") or c.startswith("e10")]
    keep = ["seg_id", "g_ms", "n1", "a_mean", "lost"] + ecol
    sg = SEGS.set_index("seg_id")
    ov_rows, parts = [], []
    k = 0
    bs = float(cfg["bootstrap"]["block_s"]) * 1000.0
    for pkey in sorted(SEGS.period.unique()):
        Sp, Xp = SEGS[SEGS.period == pkey], SEC[SEC.period == pkey]
        lo = period_lo(cfg, pkey)
        for a, b in itertools.combinations(animals, 2):
            sa, sb = Sp[Sp.animal == a], Sp[Sp.animal == b]
            ia, ib, s, e = overlap_spans(sa[["ts_ms", "te_ms"]].to_numpy(), sb[["ts_ms", "te_ms"]].to_numpy(), cfg["overlap_min_s"])
            if not len(ia):
                continue
            ov = pd.DataFrame({"ov_id": np.arange(k, k + len(ia)), "period": pkey, "a": a, "b": b, "seg_a": sa.seg_id.to_numpy()[ia],
                               "seg_b": sb.seg_id.to_numpy()[ib], "s_ms": s, "e_ms": e})
            k += len(ia)
            ov_rows.append(ov)
            xa = Xp.loc[Xp.animal == a, keep].rename(columns={c: f"{c}_i" for c in keep if c != "g_ms"})
            xb = Xp.loc[Xp.animal == b, keep].rename(columns={c: f"{c}_j" for c in keep if c != "g_ms"})
            M = xa.merge(xb, on="g_ms", how="inner")
            M = M.merge(ov[["seg_a", "seg_b", "ov_id"]], left_on=["seg_id_i", "seg_id_j"], right_on=["seg_a", "seg_b"], how="inner")
            M = M.drop(columns=["seg_a", "seg_b"])
            M["period"] = pkey
            M["blk"] = ((M.g_ms - lo) // bs).astype(np.int64)
            parts.append(M)
    if not ov_rows:
        return pd.DataFrame(), pd.DataFrame()
    OV = pd.concat(ov_rows, ignore_index=True)
    OV["set"] = OV.period.map(lambda p: cfg["_audit"]["periods"][p]["set"])
    OV["kind"] = OV.period.map(lambda p: cfg["_audit"]["periods"][p]["kind"])
    OV["pair"] = OV.a + "-" + OV.b
    OV["dur_s"] = (OV.e_ms - OV.s_ms) / 1000.0
    OV["za"] = OV.seg_a.map(sg["zd"])
    OV["zb"] = OV.seg_b.map(sg["zd"])
    OV["zp"] = [zone_pairing(x, y) for x, y in zip(OV.za, OV.zb)]
    OV["ca_x"], OV["ca_y"] = OV.seg_a.map(sg["truth_x"]).to_numpy(), OV.seg_a.map(sg["truth_y"]).to_numpy()
    OV["cb_x"], OV["cb_y"] = OV.seg_b.map(sg["truth_x"]).to_numpy(), OV.seg_b.map(sg["truth_y"]).to_numpy()
    dx, dy = OV.ca_x - OV.cb_x, OV.ca_y - OV.cb_y
    OV["d_truth"] = np.hypot(dx, dy)
    with np.errstate(invalid="ignore", divide="ignore"):
        OV["ux"], OV["uy"] = dx / OV.d_truth, dy / OV.d_truth
    e1, e2 = cfg["distance_bands_in"]
    OV["band"] = np.where(OV.d_truth < e1, "<14", np.where(OV.d_truth <= e2, "14-48", ">48"))
    PS = pd.concat(parts, ignore_index=True).sort_values(["ov_id", "g_ms"]).reset_index(drop=True)
    cnt = PS.groupby("ov_id").size()
    OV["n_sec"] = OV.ov_id.map(cnt).fillna(0).astype(int)
    v = PS[["e1x_raw_i", "e1x_raw_j"]].notna().all(axis=1).groupby(PS.ov_id).sum() if "e1x_raw_i" in PS else cnt * 0
    OV["n_sec_raw1"] = OV.ov_id.map(v).fillna(0).astype(int)
    keys = PS.period + "|" + PS.blk.astype(str)
    PS["bcode"] = pd.factorize(keys, sort=True)[0].astype(np.int64)
    return OV, PS


def stratum_masks(OV: pd.DataFrame, same_zone: list, kinds=KINDS, with_band: bool = False) -> dict:
    """(zpg, set, kind[, band]) -> boolean mask over OV rows (= ov_id positions)."""
    out = {}
    zp = OV.zp.to_numpy()
    bands = BANDS if with_band else ["all"]
    for zpg in ZPG:
        mz = np.ones(len(OV), bool) if zpg == "all" else (np.isin(zp, same_zone) if zpg == "same_zone" else zp == zpg)
        for st in SETS:
            ms = mz if st == "all" else mz & (OV.set.to_numpy() == st)
            for kd in kinds:
                mk = ms if kd == "all" else ms & (OV.kind.to_numpy() == kd)
                for bd in bands:
                    mb = mk if bd == "all" else mk & (OV.band.to_numpy() == bd)
                    if mb.any():
                        out[(zpg, st, kd, bd) if with_band else (zpg, st, kd)] = mb
    return out


# ====================================================================================================== bootstrap helpers
def ci3(x: np.ndarray) -> tuple[float, float, float]:
    """Point estimate (row 0) and the 2.5 / 97.5 % percentiles of the bootstrap rows (finite ones)."""
    return FA.ci(np.asarray(x, float))


def wq_boot(x: np.ndarray, blk: np.ndarray, cnt: np.ndarray, q: float) -> np.ndarray:
    """Weighted lower quantile of x under each row of block counts: the smallest x whose cumulative weight share >= q.
    blk = position of each value's block in cnt's columns; row 0 of cnt = ones (the plain empirical quantile)."""
    x = np.asarray(x, float)
    if not len(x):
        return np.full(cnt.shape[0], np.nan)
    o = np.argsort(x, kind="stable")
    xs = x[o]
    W = cnt[:, blk[o]]
    cw = np.cumsum(W, axis=1)
    tot = cw[:, -1:]
    j = (cw < q * tot - 1e-9).sum(axis=1)
    out = xs[np.minimum(j, len(xs) - 1)]
    out[tot[:, 0] <= 0] = np.nan
    return out


def hist_boot_q(vals: np.ndarray, blk: np.ndarray, cnt: np.ndarray, edges: np.ndarray, qs) -> np.ndarray:
    """Block-bootstrap quantiles from per-block histograms (sparse product); rows = cnt rows, columns = qs."""
    from scipy import sparse
    nb = len(edges) - 1
    K = cnt.shape[1]
    if not len(vals):
        return np.full((cnt.shape[0], len(qs)), np.nan)
    j = np.clip(np.searchsorted(edges, vals, side="right") - 1, 0, nb - 1)
    H = sparse.csr_matrix((np.ones(len(vals)), (blk.astype(np.int64), j)), shape=(K, nb))
    Wm = np.asarray((H.T @ cnt.T).T)
    return np.column_stack([FA.hist_q(Wm, edges, q) for q in qs])


def block_sums(blk: np.ndarray, Q: np.ndarray, K: int) -> np.ndarray:
    return np.stack([np.bincount(blk, weights=Q[:, c], minlength=K) for c in range(Q.shape[1])], axis=1)


def rho_from(T: np.ndarray) -> dict:
    """T (B, 7) sums: xx_ij, yy_ij, xx_ii, yy_ii, xx_jj, yy_jj, n -> per-axis and vector correlations."""
    with np.errstate(invalid="ignore", divide="ignore"):
        rx = T[:, 0] / np.sqrt(T[:, 2] * T[:, 4])
        ry = T[:, 1] / np.sqrt(T[:, 3] * T[:, 5])
        rv = (T[:, 0] + T[:, 1]) / np.sqrt((T[:, 2] + T[:, 3]) * (T[:, 4] + T[:, 5]))
    return {"rho_x": rx, "rho_y": ry, "rho_v": rv}


# ====================================================================================================== C1
def dense_layout(PS: pd.DataFrame) -> dict:
    """Dense time axis: each pair overlap occupies its contiguous integer seconds, PAD empty seconds in between."""
    ov = PS.ov_id.to_numpy(np.int64)
    gs = (PS.g_ms.to_numpy(np.int64) // 1000)
    st = PS.groupby("ov_id").g_ms.agg(["min", "max"])
    st["min"] //= 1000
    st["max"] //= 1000
    lens = (st["max"] - st["min"] + 1).to_numpy(np.int64)
    offs = np.r_[0, np.cumsum(lens + PAD)][:-1]
    om = pd.Series(offs, index=st.index)
    gm = st["min"]
    pos = om.reindex(ov).to_numpy(np.int64) + (gs - gm.reindex(ov).to_numpy(np.int64))
    N = int(offs[-1] + lens[-1] + PAD) if len(offs) else 0
    pos_ov = np.full(N, -1, np.int64)
    pos_ov[pos] = ov
    pos_blk = np.full(N, -1, np.int64)
    pos_blk[pos] = PS.bcode.to_numpy(np.int64)
    return {"pos": pos, "N": N, "pos_ov": pos_ov, "pos_blk": pos_blk, "K": int(PS.bcode.max()) + 1}


def dense_vec(lay: dict, PS: pd.DataFrame, cx: str, cy: str) -> np.ndarray:
    E = np.full((lay["N"], 2), np.nan)
    E[lay["pos"], 0] = PS[cx].to_numpy(float)
    E[lay["pos"], 1] = PS[cy].to_numpy(float)
    return E


def shift(E: np.ndarray, L: int) -> np.ndarray:
    """Es[k] = E[k + L] (NaN outside)."""
    out = np.full_like(E, np.nan)
    if L == 0:
        return E.copy()
    if L > 0:
        out[:-L] = E[L:]
    else:
        out[-L:] = E[:L]
    return out


def centre_by_overlap(Ei: np.ndarray, Ej: np.ndarray, pos_ov: np.ndarray, n_ov: int) -> tuple[np.ndarray, np.ndarray]:
    """Subtract each overlap's mean residual (over the seconds where both tags are valid) from both series."""
    v = np.isfinite(Ei).all(1) & np.isfinite(Ej).all(1) & (pos_ov >= 0)
    o = pos_ov[v]
    n = np.bincount(o, minlength=n_ov).astype(float)
    out = []
    for E in (Ei, Ej):
        mx = np.bincount(o, weights=E[v, 0], minlength=n_ov) / np.maximum(n, 1)
        my = np.bincount(o, weights=E[v, 1], minlength=n_ov) / np.maximum(n, 1)
        Ec = E.copy()
        ok = pos_ov >= 0
        Ec[ok, 0] -= mx[pos_ov[ok]]
        Ec[ok, 1] -= my[pos_ov[ok]]
        out.append(Ec)
    return out[0], out[1]


def moments(Ei: np.ndarray, Ej: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    v = np.isfinite(Ei).all(1) & np.isfinite(Ej).all(1)
    Q = np.column_stack([Ei[:, 0] * Ej[:, 0], Ei[:, 1] * Ej[:, 1], Ei[:, 0] ** 2, Ei[:, 1] ** 2, Ej[:, 0] ** 2, Ej[:, 1] ** 2,
                         np.ones(len(Ei))])
    Q[~v] = 0.0
    return Q, v


def stratum_counts(masks: dict, pos_ov: np.ndarray, pos_blk: np.ndarray, n_boot: int, rng: np.random.Generator) -> dict:
    """Per stratum: the blocks that hold any of its pair-seconds and one resampling count matrix (shared by all methods,
    scales, lags and categories, so differences between them are paired)."""
    out = {}
    okp = pos_ov >= 0
    for key, m in masks.items():
        inm = np.zeros(len(pos_ov), bool)
        inm[okp] = m[pos_ov[okp]]
        bl = np.unique(pos_blk[inm])
        out[key] = {"pmask": inm, "blocks": bl, "cnt": FA.boot_counts(len(bl), n_boot, rng)}
    return out


def c1_compute(PS: pd.DataFrame, OV: pd.DataFrame, cfg: dict, methods: list, n_bits: int, bit_ids: list, fh=None) -> dict:
    """C1 correlations (+ lags, truth-centred sensitivity), per-overlap correlations, anchor-loss stratification."""
    t0 = time.time()
    lay = dense_layout(PS)
    n_ov = int(OV.ov_id.max()) + 1
    bc = cfg["bootstrap"]
    rng = np.random.default_rng(int(bc["seed"]) + 1)
    masks = stratum_masks(OV.sort_values("ov_id").reset_index(drop=True), cfg["same_zone_pairings"])
    SC = stratum_counts(masks, lay["pos_ov"], lay["pos_blk"], int(bc["n_boot"]), rng)
    K = lay["K"]
    rows, per_ov = [], []
    store = {}
    for m in methods:
        for sname, pre in SCALES.items():
            Ei = dense_vec(lay, PS, f"{pre}x_{m}_i", f"{pre}y_{m}_i")
            Ej = dense_vec(lay, PS, f"{pre}x_{m}_j", f"{pre}y_{m}_j")
            Eic, Ejc = centre_by_overlap(Ei, Ej, lay["pos_ov"], n_ov)
            store[(m, sname)] = (Ei, Ej, Eic, Ejc)
            variants = [("overlap", L, Eic, shift(Ejc, L)) for L in cfg["lags_s"]] + [("truth", 0, Ei, Ej)]
            for center, L, A_, B_ in variants:
                Q, v = moments(A_, B_)
                vb = v & (lay["pos_blk"] >= 0)
                for key, sc in SC.items():
                    mm = vb & sc["pmask"]
                    Sb = block_sums(lay["pos_blk"][mm], Q[mm], K)[sc["blocks"]]
                    T = sc["cnt"] @ Sb
                    r = rho_from(T)
                    row = {"zpg": key[0], "set": key[1], "kind": key[2], "method": m, "scale": sname, "lag_s": int(L), "center": center,
                           "n_sec": int(T[0, 6]), "hours": float(T[0, 6] / 3600.0), "n_ov": int(np.unique(lay["pos_ov"][mm]).size),
                           "n_blocks": int(len(sc["blocks"]))}
                    for k_, x in r.items():
                        e, lo_, hi_ = ci3(x)
                        row.update({k_: e, f"{k_}_lo": lo_, f"{k_}_hi": hi_})
                    rows.append(row)
                if center == "overlap" and L == 0:
                    o = lay["pos_ov"][vb]
                    So = np.stack([np.bincount(o, weights=Q[vb, c], minlength=n_ov) for c in range(7)], axis=1)
                    r = rho_from(So)
                    per_ov.append(pd.DataFrame({"ov_id": np.arange(n_ov), "method": m, "scale": sname, "n": So[:, 6].astype(int),
                                                "rho_x": r["rho_x"], "rho_y": r["rho_y"], "rho_v": r["rho_v"]}))
    C1 = pd.DataFrame(rows)
    PO = pd.concat(per_ov, ignore_index=True)
    PO = PO[PO.n > 0].merge(OV[["ov_id", "period", "set", "kind", "pair", "zp", "dur_s", "d_truth"]], on="ov_id", how="left")
    log_to(fh, f"C1 correlations: {len(C1)} rows ({time.time() - t0:.1f} s)")
    # ---- anchor-loss stratification (1-s, lag 0, overlap-centred), on a subset of strata
    t1 = time.time()
    Li = np.zeros(lay["N"], np.int64)
    Lj = np.zeros(lay["N"], np.int64)
    Li[lay["pos"]] = PS["lost_i"].to_numpy(np.int64)
    Lj[lay["pos"]] = PS["lost_j"].to_numpy(np.int64)
    Ai = np.full(lay["N"], np.nan)
    Aj = np.full(lay["N"], np.nan)
    Ai[lay["pos"]] = PS["a_mean_i"].to_numpy(float)
    Aj[lay["pos"]] = PS["a_mean_j"].to_numpy(float)
    shared = (Li & Lj) != 0
    cat = np.where(shared, 3, np.where((Li == 0) & (Lj == 0), 0, np.where((Li == 0) ^ (Lj == 0), 1, 2)))
    lowt = float(cfg["anchors"]["low_used_lt"])
    lo_i, lo_j = Ai < lowt, Aj < lowt
    ucat = np.where(lo_i & lo_j, 2, np.where(lo_i | lo_j, 1, 0))
    CATN = {0: "neither_lost", 1: "one_lost", 2: "both_lost_different", 3: "shared_lost"}
    UCATN = {0: "neither_low", 1: "one_low", 2: "both_low"}
    arows, prow = [], []
    akeys = [k_ for k_ in SC if k_[2] == "all" and k_[0] in ("all", "same_zone", "same_house", "diff_house")]
    for m in methods:
        Ei, Ej, Eic, Ejc = store[(m, "1s")]
        Q, v = moments(Eic, Ejc)
        vb = v & (lay["pos_blk"] >= 0)
        for key in akeys:
            sc = SC[key]
            base = vb & sc["pmask"]
            nall = base.sum()
            for fam, cc, names in (("anchors_list", cat, CATN), ("anchors_used", ucat, UCATN)):
                Ts = {}
                for c_, nm in names.items():
                    mm = base & (cc == c_)
                    Sb = block_sums(lay["pos_blk"][mm], Q[mm], K)[sc["blocks"]]
                    Ts[nm] = sc["cnt"] @ Sb
                ref = "neither_lost" if fam == "anchors_list" else "neither_low"
                top = "shared_lost" if fam == "anchors_list" else "both_low"
                for nm, T in Ts.items():
                    rv = rho_from(T)["rho_v"]
                    e, lo_, hi_ = ci3(rv)
                    d_ = rv - rho_from(Ts[ref])["rho_v"]
                    de, dlo, dhi = ci3(d_)
                    arows.append({"family": fam, "category": nm, "zpg": key[0], "set": key[1], "method": m, "n_sec": int(T[0, 6]),
                                  "share": float(T[0, 6] / max(nall, 1)), "rho_v": e, "rho_v_lo": lo_, "rho_v_hi": hi_,
                                  "diff_vs_ref": de, "diff_lo": dlo, "diff_hi": dhi, "ref": ref, "top": top})
        if m in ("raw", "B2"):
            sc = SC[("all", "all", "all")]
            base = vb & sc["pmask"]
            e10i, e10j = store[(m, "10s")][0], store[(m, "10s")][1]
            mmin = np.fmin(np.hypot(e10i[:, 0], e10i[:, 1]), np.hypot(e10j[:, 0], e10j[:, 1]))
            for k_ in range(n_bits):
                mm = base & (((Li & Lj) >> k_) & 1).astype(bool)
                Sb = block_sums(lay["pos_blk"][mm], Q[mm], K)[sc["blocks"]]
                T = sc["cnt"] @ Sb
                rv = rho_from(T)["rho_v"]
                e, lo_, hi_ = ci3(rv)
                mi = mmin[mm]
                prow.append({"method": m, "anchor": bit_ids[k_], "n_sec_shared_lost": int(T[0, 6]), "share": float(T[0, 6] / max(base.sum(), 1)),
                             "rho_v": e, "rho_v_lo": lo_, "rho_v_hi": hi_,
                             "both_e10_min_med_in": float(np.nanmedian(mi)) if np.isfinite(mi).any() else np.nan,
                             "both_e10_ge12_share": float(np.nanmean(mi >= 12.0)) if np.isfinite(mi).any() else np.nan})
    log_to(fh, f"C1 anchor stratification ({time.time() - t1:.1f} s)")
    return {"C1": C1, "PO": PO, "ANC": pd.DataFrame(arows), "ANC_BIT": pd.DataFrame(prow)}


# ====================================================================================================== shared excursions
def shared_excursions(PS: pd.DataFrame, OV: pd.DataFrame, cfg: dict, bit_ids: list, tz: str) -> dict:
    sx = cfg["shared_excursion"]
    m, pre, thr = sx["method"], SCALES[sx["scale"]], float(sx["min_in"])
    xi, yi = PS[f"{pre}x_{m}_i"].to_numpy(float), PS[f"{pre}y_{m}_i"].to_numpy(float)
    xj, yj = PS[f"{pre}x_{m}_j"].to_numpy(float), PS[f"{pre}y_{m}_j"].to_numpy(float)
    mi, mj = np.hypot(xi, yi), np.hypot(xj, yj)
    valid = np.isfinite(mi) & np.isfinite(mj)
    both = valid & (mi >= thr) & (mj >= thr)
    ov = PS.ov_id.to_numpy()
    g = PS.g_ms.to_numpy(np.int64)
    Li, Lj = PS.lost_i.to_numpy(np.int64), PS.lost_j.to_numpy(np.int64)
    nb = len(bit_ids)
    brk = np.r_[True, (ov[1:] != ov[:-1]) | (g[1:] - g[:-1] != 1000)]
    ev = []
    idx = np.flatnonzero(both)
    if len(idx):
        run_id = np.cumsum(np.r_[True, (np.diff(idx) != 1) | brk[idx[1:]]])
        ovm = OV.set_index("ov_id")
        for r_ in np.unique(run_id):
            k = idx[run_id == r_]
            o = int(ov[k[0]])
            sz = np.fmin(mi[k], mj[k])
            vi = np.array([xi[k].mean(), yi[k].mean()])
            vj = np.array([xj[k].mean(), yj[k].mean()])
            cosv = float(vi @ vj / (np.linalg.norm(vi) * np.linalg.norm(vj)))
            shl = ((Li[k] & Lj[k])[:, None] >> np.arange(nb)) & 1
            row = {"ov_id": o, "period": ovm.at[o, "period"], "pair": ovm.at[o, "pair"], "a": ovm.at[o, "a"], "b": ovm.at[o, "b"],
                   "zp": ovm.at[o, "zp"], "set": ovm.at[o, "set"], "s_ms": int(g[k[0]]), "e_ms": int(g[k[-1]]), "n_sec": int(len(k)),
                   "size_in": float(sz.max()), "max_i_in": float(mi[k].max()), "max_j_in": float(mj[k].max()), "cos_mean_vec": cosv,
                   "a_mean_i": float(np.nanmean(PS.a_mean_i.to_numpy(float)[k])), "a_mean_j": float(np.nanmean(PS.a_mean_j.to_numpy(float)[k])),
                   "shared_lost_any_share": float(((Li[k] & Lj[k]) != 0).mean()), "either_lost_share": float(((Li[k] | Lj[k]) != 0).mean())}
            for kb in range(nb):
                row[f"sl_{bit_ids[kb]}"] = float(shl[:, kb].mean())
            ev.append(row)
    EV = pd.DataFrame(ev)
    CL = pd.DataFrame()
    if len(EV):
        EV = EV.sort_values(["period", "s_ms"]).reset_index(drop=True)
        gap = float(sx["merge_gap_s"]) * 1000.0
        cid, cur_p, cur_e, c = [], None, -np.inf, -1
        for r in EV.itertuples():
            if r.period != cur_p or r.s_ms > cur_e + gap:
                c += 1
                cur_p, cur_e = r.period, r.e_ms
            else:
                cur_e = max(cur_e, r.e_ms)
            cid.append(c)
        EV["cluster"] = cid
        crow = []
        for c_, gq in EV.groupby("cluster"):
            tags = sorted(set(gq.a) | set(gq.b))
            w = gq.n_sec.to_numpy(float)
            sl = {f"sl_{b}": float(np.average(gq[f"sl_{b}"], weights=w)) for b in bit_ids}
            top = sorted(sl.items(), key=lambda kv: -kv[1])[:3]
            crow.append({"cluster": c_, "period": gq.period.iloc[0], "set": gq.set.iloc[0], "s_ms": int(gq.s_ms.min()), "e_ms": int(gq.e_ms.max()),
                         "start_local": FA.ms_local(gq.s_ms.min(), tz), "end_local": FA.ms_local(gq.e_ms.max(), tz),
                         "dur_s": float((gq.e_ms.max() - gq.s_ms.min()) / 1000.0 + 1.0), "n_tags": len(tags), "tags": ",".join(tags),
                         "n_pairs": int(gq.pair.nunique()), "pairings": ",".join(sorted(gq.zp.unique())), "size_in": float(gq.size_in.max()),
                         "cos_mean_vec_min": float(gq.cos_mean_vec.min()), "a_mean": float(np.nanmean(np.r_[gq.a_mean_i, gq.a_mean_j])),
                         "shared_lost_any_share": float(np.average(gq.shared_lost_any_share, weights=w)),
                         "top_shared_lost": "; ".join(f"{k[3:]} {v:.0%}" for k, v in top if v > 0), **sl})
        CL = pd.DataFrame(crow).sort_values("size_in", ascending=False).reset_index(drop=True)
    # anchor enrichment: top-N clusters' event pair-seconds vs all valid joint pair-seconds
    enr = []
    if len(CL):
        topc = set(CL.head(int(sx["top_n"])).cluster)
        sel = np.zeros(len(PS), bool)
        for r in EV[EV.cluster.isin(topc)].itertuples():
            sel |= (ov == r.ov_id) & (g >= r.s_ms) & (g <= r.e_ms)
        sel &= both
        for kb in range(nb):
            bit = (((Li & Lj) >> kb) & 1).astype(bool)
            p_top = float(bit[sel].mean()) if sel.any() else np.nan
            p_all = float(bit[valid].mean()) if valid.any() else np.nan
            enr.append({"anchor": bit_ids[kb], "shared_lost_top": p_top, "shared_lost_all": p_all,
                        "enrichment": p_top / p_all if p_all and p_all > 0 else np.nan,
                        "either_lost_top": float(((((Li | Lj) >> kb) & 1).astype(bool))[sel].mean()) if sel.any() else np.nan,
                        "either_lost_all": float(((((Li | Lj) >> kb) & 1).astype(bool))[valid].mean()) if valid.any() else np.nan})
    return {"EV": EV, "CL": CL, "ENR": pd.DataFrame(enr), "n_valid": int(valid.sum()), "n_both": int(both.sum())}


# ====================================================================================================== C2
def c2_compute(PS: pd.DataFrame, OV: pd.DataFrame, cfg: dict, methods: list, fh=None) -> pd.DataFrame:
    t0 = time.time()
    bc = cfg["bootstrap"]
    rng = np.random.default_rng(int(bc["seed"]) + 2)
    OVs = OV.sort_values("ov_id").reset_index(drop=True)
    ovi = PS.ov_id.to_numpy(np.int64)
    cax, cay = OVs.ca_x.to_numpy()[ovi], OVs.ca_y.to_numpy()[ovi]
    cbx, cby = OVs.cb_x.to_numpy()[ovi], OVs.cb_y.to_numpy()[ovi]
    dtr, ux, uy = OVs.d_truth.to_numpy()[ovi], OVs.ux.to_numpy()[ovi], OVs.uy.to_numpy()[ovi]
    masks = stratum_masks(OVs, cfg["same_zone_pairings"], with_band=True)
    blk = PS.bcode.to_numpy(np.int64)
    K = int(blk.max()) + 1
    hc = cfg["abs_err_hist"]
    edges = np.arange(0.0, float(hc["max_in"]) + 1e-9, float(hc["step_in"]))
    SCN = {}
    for key, mk in masks.items():
        rm = mk[ovi]
        bl = np.unique(blk[rm])
        cnt = FA.boot_counts(len(bl), int(bc["n_boot"]), rng) if key[2] == "all" else np.ones((1, len(bl)))
        SCN[key] = {"rmask": rm, "blocks": bl, "cnt": cnt}
    rows = []
    for m in methods:
        for sname, pre in SCALES.items():
            exi, eyi = PS[f"{pre}x_{m}_i"].to_numpy(float), PS[f"{pre}y_{m}_i"].to_numpy(float)
            exj, eyj = PS[f"{pre}x_{m}_j"].to_numpy(float), PS[f"{pre}y_{m}_j"].to_numpy(float)
            v = np.isfinite(exi) & np.isfinite(eyi) & np.isfinite(exj) & np.isfinite(eyj) & (dtr > 1e-6)
            d = np.hypot((cax + exi) - (cbx + exj), (cay + eyi) - (cby + eyj))
            eps = d - dtr
            a_ = exi * ux + eyi * uy
            b_ = exj * ux + eyj * uy
            Q = np.column_stack([np.ones(len(eps)), eps, eps ** 2, a_, a_ ** 2, b_, b_ ** 2])
            Q[~v] = 0.0
            aeps = np.abs(eps)
            for key, sc in SCN.items():
                mm = v & sc["rmask"]
                if not mm.any():
                    continue
                pos = np.searchsorted(sc["blocks"], blk[mm])
                Sb = block_sums(pos, Q[mm], len(sc["blocks"]))
                T = sc["cnt"] @ Sb
                n = T[:, 0]
                with np.errstate(invalid="ignore", divide="ignore"):
                    mu = T[:, 1] / n
                    sd = np.sqrt(np.maximum(T[:, 2] / n - mu ** 2, 0))
                    va = np.maximum(T[:, 4] / n - (T[:, 3] / n) ** 2, 0)
                    vb_ = np.maximum(T[:, 6] / n - (T[:, 5] / n) ** 2, 0)
                    sdi = np.sqrt(va + vb_)
                    R = sd / sdi
                qq = hist_boot_q(aeps[mm], pos, sc["cnt"], edges, [0.95, 0.99])
                row = {"zpg": key[0], "set": key[1], "kind": key[2], "band": key[3], "method": m, "scale": sname, "n_sec": int(n[0]),
                       "hours": float(n[0] / 3600.0), "n_ov": int(np.unique(ovi[mm]).size), "n_blocks": int(len(sc["blocks"])),
                       "mean_err": float(mu[0]), "d_truth_med": float(np.median(dtr[mm])),
                       "p95_abs_exact": float(np.percentile(aeps[mm], 95)), "p99_abs_exact": float(np.percentile(aeps[mm], 99))}
                for nm, x in (("sd_err", sd), ("p95_abs", qq[:, 0]), ("p99_abs", qq[:, 1]), ("sd_indep", sdi), ("R", R)):
                    e, lo_, hi_ = ci3(x) if x.shape[0] > 1 else (float(x[0]), np.nan, np.nan)
                    row.update({nm: e, f"{nm}_lo": lo_, f"{nm}_hi": hi_})
                rows.append(row)
    log_to(fh, f"C2 distance precision: {len(rows)} rows ({time.time() - t0:.1f} s)")
    return pd.DataFrame(rows)


# ====================================================================================================== C3
ZCODE = {"house_1": 0, "house_2": 1, "outside": 2}


def c3_seg_metrics(tt: np.ndarray, u: np.ndarray, mh: np.ndarray, c3: dict) -> dict:
    """One target segment: tt (s, 1-s grid, valid target seconds), u (n, 2) uncorrected residual, mh (n, 2) the reference
    estimate (NaN = no reference). Covered-only metrics compare u and v = u - mh on the same seconds; whole-segment metrics
    use v_all = u - mh where covered, u elsewhere."""
    h, mn = float(c3["roll_half_s"]), int(c3["roll_min_n"])
    thr, mins = float(c3["crazy_in"]), int(c3["crazy_min_s"])
    cov = np.isfinite(mh).all(axis=1)
    v = u - np.where(cov[:, None], mh, 0.0)
    r = {"n_sec": int(len(u)), "n_cov": int(cov.sum()),
         "ss_u": float((u[cov] ** 2).sum()), "ss_v": float((v[cov] ** 2).sum()),
         "ss_u_all": float((u ** 2).sum()), "ss_v_all": float((v ** 2).sum())}
    cen = np.arange(tt[0] + h, tt[-1] - h + 1.0 + 1e-9, 1.0) if len(tt) else np.zeros(0)

    def drift(ts_, val):
        if len(ts_) < mn or not len(cen):
            return np.nan, 0
        mm, _ = FA.roll_median(ts_, val, cen, h, mn)
        d = np.hypot(mm[:, 0], mm[:, 1])
        if not np.isfinite(d).any():
            return np.nan, 0
        ev = [1 for a, b in C.true_runs(np.nan_to_num(d, nan=-1.0) >= thr) if b - a >= mins]
        return float(np.nanmax(d)), int(len(ev))
    r["drift_u"], r["ev_u"] = drift(tt[cov], u[cov])
    r["drift_v"], r["ev_v"] = drift(tt[cov], v[cov])
    r["drift_u_all"], r["ev_u_all"] = drift(tt, u)
    r["drift_v_all"], r["ev_v_all"] = drift(tt, v)
    return r


def c3_compute(SEC: pd.DataFrame, SEGS: pd.DataFrame, cfg: dict, window: tuple | None = None, fh=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Leave-one-tag-out differential correction. Returns per (segment, method, variant) metrics and, inside window
    (period, t0_ms, t1_ms), the per-second residuals and reference estimates."""
    t0 = time.time()
    c3 = cfg["c3"]
    sg = SEGS.set_index("seg_id")
    rows, wrows = [], []
    for pkey, g in SEC.groupby("period"):
        lo = period_lo(cfg, pkey)
        animals = sorted(g.animal.unique())
        A = len(animals)
        gs = np.unique(g.g_ms.to_numpy(np.int64))
        T = len(gs)
        ti = np.searchsorted(gs, g.g_ms.to_numpy(np.int64))
        ai = g.animal.map({a: k for k, a in enumerate(animals)}).to_numpy()
        codes, uni = pd.factorize(g.seg_id)
        SEGI = np.full((T, A), -1, np.int64)
        SEGI[ti, ai] = codes
        Z = np.full((T, A), -1, np.int64)
        Z[ti, ai] = g.seg_id.map(sg["zd"]).map(lambda z: ZCODE.get(z, 3)).to_numpy()
        tt_all = (gs - lo) / 1000.0
        inwin = np.zeros(T, bool)
        if window is not None and window[0] == pkey:
            inwin = (gs >= window[1]) & (gs <= window[2])
        for m in c3["methods"]:
            E = np.full((T, A, 2), np.nan)
            E[ti, ai, 0] = g[f"e1x_{m}"].to_numpy(float)
            E[ti, ai, 1] = g[f"e1y_{m}"].to_numpy(float)
            V = np.isfinite(E).all(axis=2)
            E0 = np.where(V[..., None], E, 0.0)
            for var in c3["variants"]:
                for i in range(A):
                    ref = V.copy()
                    ref[:, i] = False
                    if var == "z":
                        ref &= (Z == Z[:, [i]]) & (Z[:, [i]] >= 0)
                    nref = ref.sum(axis=1)
                    with np.errstate(invalid="ignore", divide="ignore"):
                        mh = (E0 * ref[..., None]).sum(axis=1) / np.where(nref > 0, nref, np.nan)[:, None]
                    rows_i = np.flatnonzero((SEGI[:, i] >= 0) & V[:, i])
                    if not len(rows_i):
                        continue
                    sc_ = SEGI[rows_i, i]
                    o = np.argsort(sc_, kind="stable")
                    rs, ss = rows_i[o], sc_[o]
                    cuts = np.flatnonzero(np.diff(ss)) + 1
                    for grp in np.split(np.arange(len(rs)), cuts):
                        r_ = rs[grp]
                        seg = uni[ss[grp[0]]]
                        met = c3_seg_metrics(tt_all[r_], E[r_, i], mh[r_], c3)
                        met.update({"seg_id": seg, "animal": animals[i], "period": pkey, "method": m, "variant": var,
                                    "nref_mean": float(nref[r_][np.isfinite(mh[r_]).all(axis=1)].mean()) if np.isfinite(mh[r_]).all(axis=1).any() else 0.0})
                        rows.append(met)
                    if inwin.any():
                        w = rows_i[inwin[rows_i]]
                        if len(w):
                            wrows.append(pd.DataFrame({"g_ms": gs[w], "animal": animals[i], "method": m, "variant": var,
                                                       "ux": E[w, i, 0], "uy": E[w, i, 1], "mhx": mh[w, 0], "mhy": mh[w, 1], "nref": nref[w]}))
    C3S = pd.DataFrame(rows)
    if len(C3S):
        C3S = C3S.merge(SEGS[["seg_id", "set", "kind", "zone2", "zd", "period", "blk", "dur_trim_s"]].rename(columns={"period": "_p"}),
                        on="seg_id", how="left").drop(columns=["_p"])
    log_to(fh, f"C3 leave-one-tag-out: {len(C3S)} segment rows ({time.time() - t0:.1f} s)")
    return C3S, (pd.concat(wrows, ignore_index=True) if wrows else pd.DataFrame())


def c3_summary(C3S: pd.DataFrame, cfg: dict, fh=None) -> pd.DataFrame:
    """Paired block bootstrap of the relative change corrected vs uncorrected, per stratum x method x variant."""
    bc = cfg["bootstrap"]
    rng = np.random.default_rng(int(bc["seed"]) + 3)
    D = C3S.copy()
    D["bkey"] = D.period + "|" + D.blk.astype(str)
    strata = [(st, kd, "all") for st in SETS for kd in KINDS] + [("all", "all", "house"), ("all", "all", "outside")]
    out = []
    for st, kd, zn in strata:
        sel = np.ones(len(D), bool)
        if st != "all":
            sel &= D.set.to_numpy() == st
        if kd != "all":
            sel &= D.kind.to_numpy() == kd
        if zn != "all":
            sel &= D.zone2.to_numpy() == zn
        if not sel.any():
            continue
        bl = np.unique(D.bkey[sel])
        cnt = FA.boot_counts(len(bl), int(bc["n_boot"]), rng)
        for (m, var), d in D[sel].groupby(["method", "variant"]):
            pos = np.searchsorted(bl, d.bkey.to_numpy())
            cols = ["n_sec", "n_cov", "ss_u", "ss_v", "ss_u_all", "ss_v_all", "ev_u", "ev_v", "ev_u_all", "ev_v_all"]
            Sb = block_sums(pos, d[cols].to_numpy(float), len(bl))
            T = cnt @ Sb
            Tm = dict(zip(cols, T.T))
            base = {"set": st, "kind": kd, "zone": zn, "method": m, "variant": var, "n_seg": int(len(d)), "n_blocks": int(len(bl)),
                    "still_h": float(Tm["n_sec"][0] / 3600.0), "covered_h": float(Tm["n_cov"][0] / 3600.0)}
            with np.errstate(invalid="ignore", divide="ignore"):
                cov = Tm["n_cov"] / Tm["n_sec"]
                e, lo_, hi_ = ci3(cov)
                base.update({"coverage": e, "coverage_lo": lo_, "coverage_hi": hi_})

                def add(metric, unc, cor, extra=None):
                    rel = cor / unc - 1.0
                    e, lo_, hi_ = ci3(rel)
                    out.append({**base, "metric": metric, "uncorrected": float(unc[0]), "corrected": float(cor[0]), "rel_change": e,
                                "rel_lo": lo_, "rel_hi": hi_, **(extra or {})})
                add("rms_1s", np.sqrt(Tm["ss_u"] / Tm["n_cov"]), np.sqrt(Tm["ss_v"] / Tm["n_cov"]))
                add("rms_1s_whole", np.sqrt(Tm["ss_u_all"] / Tm["n_sec"]), np.sqrt(Tm["ss_v_all"] / Tm["n_sec"]))
                for sfx, lab in (("", ""), ("_all", "_whole")):
                    ok = np.isfinite(d[f"drift_u{sfx}"].to_numpy(float)) & np.isfinite(d[f"drift_v{sfx}"].to_numpy(float))
                    if ok.sum() >= 5:
                        for q, nm in ((0.9, "drift10_p90"), (0.5, "drift10_med")):
                            qu = wq_boot(d[f"drift_u{sfx}"].to_numpy(float)[ok], pos[ok], cnt, q)
                            qv = wq_boot(d[f"drift_v{sfx}"].to_numpy(float)[ok], pos[ok], cnt, q)
                            add(nm + lab, qu, qv, {"n_seg_drift": int(ok.sum())})
                    hrs = (Tm["n_cov"] if sfx == "" else Tm["n_sec"]) / 3600.0
                    eu, evv = Tm[f"ev_u{sfx}"], Tm[f"ev_v{sfx}"]
                    add("events12" + lab, eu, evv, {"events_u": int(eu[0]), "events_v": int(evv[0]),
                                                     "rate_u_per_h": float(eu[0] / hrs[0]) if hrs[0] else np.nan,
                                                     "rate_v_per_h": float(evv[0] / hrs[0]) if hrs[0] else np.nan})
    S3 = pd.DataFrame(out)
    log_to(fh, f"C3 summary: {len(S3)} rows")
    return S3


# ====================================================================================================== verdict
def verdict(C1: pd.DataFrame, S3: pd.DataFrame, vc: dict) -> dict:
    def r1(m):
        r = C1[(C1.zpg == vc["corr_pairing"]) & (C1.set == "all") & (C1.kind == "all") & (C1.method == m) & (C1.scale == vc["corr_scale"])
               & (C1.lag_s == 0) & (C1.center == "overlap")]
        if not len(r):
            return {"ok": False, "rho_v": np.nan, "lo": np.nan, "hi": np.nan}
        r = r.iloc[0]
        return {"ok": bool(r.rho_v >= vc["corr_min"] and r.rho_v_lo > 0), "rho_v": float(r.rho_v), "lo": float(r.rho_v_lo), "hi": float(r.rho_v_hi)}

    def r2(m):
        parts = {}
        for met in vc["c3_metrics"]:
            r = S3[(S3.set == "all") & (S3.kind == "all") & (S3.zone == "all") & (S3.method == m) & (S3.variant == vc["c3_variant"]) & (S3.metric == met)]
            if not len(r):
                parts[met] = {"ok": False, "rel": np.nan, "lo": np.nan, "hi": np.nan}
                continue
            r = r.iloc[0]
            parts[met] = {"ok": bool(r.rel_change <= vc["rel_change_max"] and r.rel_hi < 0), "rel": float(r.rel_change),
                          "lo": float(r.rel_lo), "hi": float(r.rel_hi)}
        return {"ok": any(p["ok"] for p in parts.values()), "parts": parts}
    res = {}
    for lab, m in (("B2", vc["method"]), ("raw", vc["raw_method"])):
        a, b = r1(m), r2(m)
        res[lab] = {"cond1": a, "cond2": b, "both": bool(a["ok"] and b["ok"])}
    if res["B2"]["both"]:
        v = "material"
    elif res["raw"]["both"]:
        v = "material for raw only"
    else:
        v = "not material"
    res["verdict"] = v
    return res


# ====================================================================================================== cluster case
def cluster_case(SEC: pd.DataFrame, CTX: pd.DataFrame, W3: pd.DataFrame, SX: dict, cfg: dict, bit_ids: list) -> dict:
    cc = cfg["cluster_case"]
    tz = cfg["tz"]
    T = C.to_ms(cc["time"], tz)
    hw = float(cc["half_window_s"]) * 1000.0
    s = SEC[(SEC.period == cc["period"]) & (SEC.g_ms >= T - hw) & (SEC.g_ms <= T + hw)]
    rows = []
    for a, g in s.groupby("animal"):
        m10 = np.hypot(g.e10x_raw, g.e10y_raw).to_numpy(float)
        m1 = np.hypot(g.e1x_raw, g.e1y_raw).to_numpy(float)
        b10 = np.hypot(g.e10x_B2, g.e10y_B2).to_numpy(float)
        b1 = np.hypot(g.e1x_B2, g.e1y_B2).to_numpy(float)
        L = g.lost.to_numpy(np.int64)
        j = int(np.nanargmax(m10)) if np.isfinite(m10).any() else None
        lost_share = {bit_ids[k]: float(((L >> k) & 1).mean()) for k in range(len(bit_ids))}
        row = {"animal": a, "n_sec": int(len(g)), "segments": ",".join(sorted(g.seg_id.unique())),
               "first_local": FA.ms_local(g.g_ms.min(), tz), "last_local": FA.ms_local(g.g_ms.max(), tz),
               "raw10_max_in": float(np.nanmax(m10)) if j is not None else np.nan,
               "raw10_max_at": FA.ms_local(g.g_ms.to_numpy()[j], tz) if j is not None else "",
               "raw1_max_in": float(np.nanmax(m1)) if np.isfinite(m1).any() else np.nan,
               "B2_10_max_in": float(np.nanmax(b10)) if np.isfinite(b10).any() else np.nan,
               "B2_1_max_in": float(np.nanmax(b1)) if np.isfinite(b1).any() else np.nan,
               "a_mean": float(np.nanmean(g.a_mean)), "a_min_1s": float(np.nanmin(g.a_mean)),
               "lost_top": "; ".join(f"{k} {v:.0%}" for k, v in sorted(lost_share.items(), key=lambda kv: -kv[1])[:3] if v > 0)}
        if len(W3):
            for m in ("raw", "B2"):
                for var in ("z", "a"):
                    w = W3[(W3.animal == a) & (W3.method == m) & (W3.variant == var)]
                    if len(w):
                        u = np.hypot(w.ux, w.uy).to_numpy(float)
                        cv = np.isfinite(w.mhx.to_numpy(float))
                        vv = np.hypot(w.ux - w.mhx, w.uy - w.mhy).to_numpy(float)
                        row[f"{m}_{var}_cov"] = float(cv.mean())
                        row[f"{m}_{var}_u_max_cov"] = float(np.nanmax(u[cv])) if cv.any() else np.nan
                        row[f"{m}_{var}_v_max_cov"] = float(np.nanmax(vv[cv])) if cv.any() else np.nan
                        row[f"{m}_{var}_rms_u_cov"] = float(np.sqrt(np.nanmean(u[cv] ** 2))) if cv.any() else np.nan
                        row[f"{m}_{var}_rms_v_cov"] = float(np.sqrt(np.nanmean(vv[cv] ** 2))) if cv.any() else np.nan
        rows.append(row)
    CL = SX.get("CL", pd.DataFrame())
    hit = CL[(CL.period == cc["period"]) & (CL.s_ms <= T + hw) & (CL.e_ms >= T - hw)] if len(CL) else pd.DataFrame()
    return {"tags": pd.DataFrame(rows), "clusters": hit, "T": T}


# ====================================================================================================== reproduction
def _rep_row(a: str, st: str, g: pd.DataFrame, f: pd.DataFrame) -> dict:
    """1-s RMS (each second weighted 1, and weighted by its fix count n1) vs the audit's per-fix RMS."""
    row = {"animal": a, "set": st, "n_sec": int(len(g)), "n_fix": int(len(f))}
    for m in ("raw", "B2"):
        r2 = g[f"e1x_{m}"].to_numpy(float) ** 2 + g[f"e1y_{m}"].to_numpy(float) ** 2
        ok = np.isfinite(r2)
        row[f"rms_1s_{m}"] = float(np.sqrt(np.mean(r2[ok])))
        row[f"rms_1s_w_{m}"] = float(np.sqrt(np.average(r2[ok], weights=g["n1"].to_numpy(float)[ok])))
        row[f"rms_fix_{m}"] = float(np.sqrt(np.mean(f[f"r_{m}"].to_numpy(float) ** 2)))
        row[f"ok_{m}"] = bool(row[f"rms_1s_{m}"] <= row[f"rms_fix_{m}"])
        row[f"okw_{m}"] = bool(row[f"rms_1s_w_{m}"] <= row[f"rms_fix_{m}"])
    return row


def reproduction(SEC: pd.DataFrame, INFO: pd.DataFrame, SEGS: pd.DataFrame, cfg: dict) -> dict:
    F = pd.read_csv(Path(cfg["audit_run"]) / "tables" / "still_fixes.csv.gz", usecols=["seg_id", "r_raw", "r_B2"])
    F = F[F.seg_id.isin(set(SEGS.seg_id))].merge(SEGS[["seg_id", "animal", "set"]], on="seg_id")
    rows = []
    s = SEC.merge(SEGS[["seg_id", "set"]], on="seg_id")
    for (a, st), g in s.groupby(["animal", "set"]):
        f = F[(F.animal == a) & (F.set == st)]
        rows.append(_rep_row(a, st, g, f))
    for st in ("calm", "rain"):
        g = s[s.set == st]
        f = F[F.set == st]
        rows.append(_rep_row("pooled", st, g, f))
    R = pd.DataFrame(rows)
    chk = {"n_segments": int(len(INFO)), "fix_count_mismatch": int((INFO.n_fix != INFO.n_fix_audit).sum()),
           "truth_dev_max_in": float(INFO.truth_dev_in.max()), "all_rms_1s_le_fix": bool(R[["ok_raw", "ok_B2"]].all().all()),
           "all_rms_1s_fixweighted_le_fix": bool(R[["okw_raw", "okw_B2"]].all().all())}
    return {"R": R, "chk": chk}


# ====================================================================================================== orchestration
def sha256(p: Path, limit: int | None = None) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def run_compute(cfg: dict, workers: int, fh_path: Path | None = None) -> Path:
    out = Path(output_paths.run_dir(NAME, cfg["_cohort"]))
    (out / "tables").mkdir(parents=True, exist_ok=True)
    (out / "figures").mkdir(exist_ok=True)
    fh = open(out / "log.txt", "a", encoding="utf-8")
    log_to(fh, f"run dir {out}; git {C.git_commit()}; config {cfg['_path']}")
    t0 = time.time()
    SEGS = load_segments(cfg)
    periods = list(cfg["_audit"]["periods"])
    animals = cfg["_audit"]["animals"]
    keys = [(a, p) for p in periods for a in animals]
    workers = max(1, min(int(workers), 8))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        idl = list(ex.map(ids_job, [{"path": str(Path(cfg["fix_cache_root"]) / FA.period_cache_key(p) / f"{a}.csv.gz")} for a, p in keys]))
    bit_ids = sorted(set().union(*map(set, idl)))
    pos = {b: k for k, b in enumerate(bit_ids)}
    log_to(fh, f"anchor ids in the fix caches: {bit_ids}")
    jobs = []
    for a, p in keys:
        sg = SEGS[(SEGS.animal == a) & (SEGS.period == p)]
        jobs.append({"cfg": cfg, "animal": a, "pkey": p, "lo": period_lo(cfg, p), "pos": pos,
                     "segs": sg[["seg_id", "ts_ms", "te_ms", "truth_x", "truth_y", "n_fix"]].to_dict("list")})
    secs, infos, ctxs, meta = [], [], [], []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(_tag_job_safe, jobs):
            if "error" in r:
                log_to(fh, f"ERROR {r['animal']} {r['pkey']}: {r['error']}\n{r['trace']}")
                raise SystemExit(1)
            secs.append(r["sec"])
            infos.append(r["info"])
            if r["ctx"] is not None:
                ctxs.append(r["ctx"])
            meta.append({k: r[k] for k in ("animal", "pkey", "n_fix", "cache_missing", "anchors_used_mismatch", "runtime_s")})
            log_to(fh, f"{r['animal']} {r['pkey']}: {len(r['sec'])} s, fixes {r['n_fix']}, cache-missing {r['cache_missing']}, "
                       f"anchors_used mismatch {r['anchors_used_mismatch']}, {r['runtime_s']} s")
    SEC = pd.concat(secs, ignore_index=True)
    INFO = pd.concat(infos, ignore_index=True)
    tb = out / "tables"
    SEC.to_csv(tb / "still_seconds.csv.gz", index=False, float_format="%.4f")
    INFO.to_csv(tb / "segment_info.csv", index=False)
    pd.DataFrame(meta).to_csv(tb / "tag_periods.csv", index=False)
    if ctxs:
        pd.concat(ctxs, ignore_index=True).to_csv(tb / "cluster_case_fixes.csv.gz", index=False)
    (out / "anchor_ids.json").write_text(json.dumps(bit_ids), encoding="utf-8")
    # provenance
    run = Path(cfg["audit_run"])
    prov = {"config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "git_commit": C.git_commit(), "audit_run": str(run),
            "audit_driver_sha256": sha256(REPO / "wiser" / "scripts" / "analyze_wiser_failure_audit.py"),
            "segments_csv": {"bytes": (run / "tables" / "segments.csv").stat().st_size, "sha256": sha256(run / "tables" / "segments.csv")},
            "still_fixes_csv": {"bytes": (run / "tables" / "still_fixes.csv.gz").stat().st_size, "sha256": sha256(run / "tables" / "still_fixes.csv.gz")},
            "tracks": {f.name: {"bytes": f.stat().st_size, "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.stat().st_mtime))}
                       for f in sorted((run / "tracks").glob("*.npz"))},
            "fix_caches": {f"{p}/{a}": {"bytes": (Path(cfg["fix_cache_root"]) / p / f"{a}.csv.gz").stat().st_size,
                                        "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime((Path(cfg["fix_cache_root"]) / p / f"{a}.csv.gz").stat().st_mtime))}
                           for a, p in keys},
            "anchor_ids": bit_ids}
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    log_to(fh, f"compute done ({time.time() - t0:.0f} s): {len(SEC)} certified seconds, {len(INFO)} segments")
    fh.close()
    return out


def analyze(out: Path, cfg: dict, fh=None) -> dict:
    t0 = time.time()
    tb = out / "tables"
    SEC = pd.read_csv(tb / "still_seconds.csv.gz")
    INFO = pd.read_csv(tb / "segment_info.csv")
    bit_ids = json.loads((out / "anchor_ids.json").read_text(encoding="utf-8"))
    SEGS = load_segments(cfg)
    methods = cfg["methods"]
    REP = reproduction(SEC, INFO, SEGS, cfg)
    REP["R"].to_csv(tb / "reproduction_rms.csv", index=False)
    log_to(fh, f"reproduction: {REP['chk']}")
    OV, PS = build_pairs(SEC, SEGS, cfg)
    OV.to_csv(tb / "pair_overlaps.csv", index=False)
    PS.to_csv(tb / "pair_seconds.csv.gz", index=False, float_format="%.4f")
    log_to(fh, f"pairs: {len(OV)} overlaps >= {cfg['overlap_min_s']:.0f} s, {len(PS)} pair-seconds ({time.time() - t0:.0f} s)")
    R1 = c1_compute(PS, OV, cfg, methods, len(bit_ids), bit_ids, fh)
    for k, f in (("C1", "c1_correlations.csv"), ("PO", "c1_per_overlap.csv"), ("ANC", "c1_anchor_loss.csv"), ("ANC_BIT", "c1_anchor_loss_by_anchor.csv")):
        R1[k].to_csv(tb / f, index=False)
    SX = shared_excursions(PS, OV, cfg, bit_ids, cfg["tz"])
    SX["EV"].to_csv(tb / "shared_excursion_events.csv", index=False)
    SX["CL"].to_csv(tb / "shared_excursion_clusters.csv", index=False)
    SX["ENR"].to_csv(tb / "shared_excursion_anchor_enrichment.csv", index=False)
    C2 = c2_compute(PS, OV, cfg, methods, fh)
    C2.to_csv(tb / "c2_distance_errors.csv", index=False)
    cc = cfg["cluster_case"]
    T = C.to_ms(cc["time"], cfg["tz"])
    hw = float(cc["half_window_s"]) * 1000.0
    C3S, W3 = c3_compute(SEC, SEGS, cfg, (cc["period"], T - hw, T + hw), fh)
    C3S.to_csv(tb / "c3_segments.csv.gz", index=False)
    W3.to_csv(tb / "c3_cluster_window_seconds.csv.gz", index=False)
    S3 = c3_summary(C3S, cfg, fh)
    S3.to_csv(tb / "c3_bootstrap.csv", index=False)
    try:
        CTX = pd.read_csv(tb / "cluster_case_fixes.csv.gz")
    except Exception:  # noqa: BLE001
        CTX = pd.DataFrame()
    CC = cluster_case(SEC, CTX, W3, SX, cfg, bit_ids)
    CC["tags"].to_csv(tb / "cluster_case_tags.csv", index=False)
    V = verdict(R1["C1"], S3, cfg["verdict"])
    cov = OV.groupby(["zp", "set"]).agg(n_ov=("ov_id", "size"), hours=("n_sec", lambda x: x.sum() / 3600.0)).reset_index()
    cov.to_csv(tb / "pair_coverage.csv", index=False)
    res = {"run_dir": str(out), "cfg_path": cfg["_path"], "verdict": V, "reproduction": REP["chk"], "n_overlaps": int(len(OV)),
           "pair_hours": float(len(PS) / 3600.0), "certified_hours": float(len(SEC) / 3600.0), "anchor_ids": bit_ids,
           "shared_excursion_pair_seconds": SX["n_both"], "runtime_analyze_s": round(time.time() - t0, 1)}
    (out / "summary.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    log_to(fh, f"analysis done ({res['runtime_analyze_s']} s); verdict: {V['verdict']}")
    return {"res": res, "SEC": SEC, "SEGS": SEGS, "INFO": INFO, "OV": OV, "PS": PS, "REP": REP, "SX": SX, "C2": C2, "C3S": C3S,
            "S3": S3, "W3": W3, "CC": CC, "CTX": CTX, "V": V, "cov": cov, "bit_ids": bit_ids, **R1}


# ====================================================================================================== figures
def make_figures(A: dict, cfg: dict, out: Path, fdir: Path, cohort: str) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#e6e6e6",
                         "grid.linewidth": 0.6, "axes.axisbelow": True, "font.size": 9})
    figs = {}
    methods = cfg["methods"]
    C1 = A["C1"]
    # 1) C1: vector correlation by zone pairing, scale and set
    pairings = ["same_house", "diff_house", "house_outside"]
    fig, axs = plt.subplots(2, 2, figsize=(11, 7), sharey=True)
    for r, sc in enumerate(["1s", "10s"]):
        for c, st in enumerate(["calm", "rain"]):
            ax = axs[r, c]
            w = 0.8 / len(methods)
            for k, m in enumerate(methods):
                xs, ys, lo_, hi_ = [], [], [], []
                for j, zp in enumerate(pairings):
                    q = C1[(C1.zpg == zp) & (C1.set == st) & (C1.kind == "all") & (C1.method == m) & (C1.scale == sc) & (C1.lag_s == 0) & (C1.center == "overlap")]
                    if len(q):
                        q = q.iloc[0]
                        xs.append(j - 0.4 + w * (k + 0.5))
                        ys.append(q.rho_v)
                        lo_.append(q.rho_v - q.rho_v_lo)
                        hi_.append(q.rho_v_hi - q.rho_v)
                ax.errorbar(xs, ys, yerr=[lo_, hi_], fmt=MARK[m], color=COL[m], ms=6, capsize=2, lw=1.2, label=LABEL[m])
            ax.axhline(0, color="#999", lw=0.8)
            ax.axhline(cfg["verdict"]["corr_min"], color="#555", lw=0.8, ls="--")
            ax.set_xticks(range(len(pairings)))
            ax.set_xticklabels([ZLABEL[z] for z in pairings])
            ax.set_title(f"{st}, {sc} residuals", fontsize=10)
            if c == 0:
                ax.set_ylabel("vector correlation (lag 0)")
    axs[0, 0].legend(fontsize=8, loc="upper right")
    fig.suptitle("C1 — cross-tag residual correlation during joint stillness (95 % block-bootstrap CI; dashed = verdict 0.3)", fontsize=10)
    fig.tight_layout()
    fn = f"{STEM}_c1_correlation_{cohort}.png"
    fig.savefig(fdir / fn, dpi=130)
    plt.close(fig)
    figs["c1"] = fn
    # 2) C2: p95 |error| and R by zone pairing; p95 by distance band
    C2 = A["C2"]
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.2))
    for k, m in enumerate(methods):
        xs, ys, lo_, hi_, xr, yr, rl, rh = [], [], [], [], [], [], [], []
        for j, zp in enumerate(pairings):
            q = C2[(C2.zpg == zp) & (C2.set == "all") & (C2.kind == "all") & (C2.band == "all") & (C2.method == m) & (C2.scale == "1s")]
            if len(q):
                q = q.iloc[0]
                x = j - 0.4 + 0.2 * (k + 0.5)
                xs.append(x)
                ys.append(q.p95_abs)
                lo_.append(q.p95_abs - q.p95_abs_lo)
                hi_.append(q.p95_abs_hi - q.p95_abs)
                xr.append(x)
                yr.append(q.R)
                rl.append(q.R - q.R_lo)
                rh.append(q.R_hi - q.R)
        axs[0].errorbar(xs, ys, yerr=[lo_, hi_], fmt=MARK[m], color=COL[m], ms=6, capsize=2, lw=1.2, label=LABEL[m])
        axs[1].errorbar(xr, yr, yerr=[rl, rh], fmt=MARK[m], color=COL[m], ms=6, capsize=2, lw=1.2, label=LABEL[m])
        xb, yb, bl, bh = [], [], [], []
        for j, bd in enumerate(["<14", "14-48", ">48"]):
            q = C2[(C2.zpg == "all") & (C2.set == "all") & (C2.kind == "all") & (C2.band == bd) & (C2.method == m) & (C2.scale == "1s")]
            if len(q):
                q = q.iloc[0]
                xb.append(j - 0.4 + 0.2 * (k + 0.5))
                yb.append(q.p95_abs)
                bl.append(q.p95_abs - q.p95_abs_lo)
                bh.append(q.p95_abs_hi - q.p95_abs)
        axs[2].errorbar(xb, yb, yerr=[bl, bh], fmt=MARK[m], color=COL[m], ms=6, capsize=2, lw=1.2, label=LABEL[m])
    for ax in axs[:2]:
        ax.set_xticks(range(len(pairings)))
        ax.set_xticklabels([ZLABEL[z] for z in pairings])
    axs[2].set_xticks(range(3))
    axs[2].set_xticklabels(["truth < 14 in", "14–48 in", "> 48 in"])
    axs[0].axhline(14.0, color="#555", lw=0.8, ls="--")
    axs[2].axhline(14.0, color="#555", lw=0.8, ls="--")
    axs[1].axhline(1.0, color="#555", lw=0.8, ls="--")
    axs[0].set_ylabel("p95 |d − d_truth| (in), 1-s")
    axs[1].set_ylabel("R = SD_obs / SD_indep (1 = no cancellation)")
    axs[2].set_ylabel("p95 |d − d_truth| (in), 1-s, all pairings")
    axs[0].set_title("distance error p95 (dashed = 14-in rule)", fontsize=10)
    axs[1].set_title("cancellation ratio R", fontsize=10)
    axs[2].set_title("by truth distance", fontsize=10)
    axs[0].legend(fontsize=8)
    fig.suptitle("C2 — pairwise-distance precision during joint stillness (95 % block-bootstrap CI)", fontsize=10)
    fig.tight_layout()
    fn = f"{STEM}_c2_distance_{cohort}.png"
    fig.savefig(fdir / fn, dpi=130)
    plt.close(fig)
    figs["c2"] = fn
    # 3) C3 forest plot
    S3 = A["S3"]
    mets = [("rms_1s", "1-s RMS"), ("drift10_p90", "10-s drift p90"), ("drift10_med", "10-s drift median"), ("events12", "≥ 12-in events")]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ticks, labs, yy = [], [], 0.0
    for m in cfg["c3"]["methods"]:
        for var in cfg["c3"]["variants"]:
            for met, lab in mets:
                q = S3[(S3.set == "all") & (S3.kind == "all") & (S3.zone == "all") & (S3.method == m) & (S3.variant == var) & (S3.metric == met)]
                if len(q) and np.isfinite(q.iloc[0].rel_change):
                    q = q.iloc[0]
                    ax.errorbar([100 * q.rel_change], [yy], xerr=[[100 * max(q.rel_change - q.rel_lo, 0)], [100 * max(q.rel_hi - q.rel_change, 0)]],
                                fmt=MARK[m], color=COL[m], ms=6, capsize=2, lw=1.2)
                ticks.append(yy)
                labs.append(f"{LABEL[m]} · variant {var} · {lab}")
                yy += 1
            yy += 0.5
    ax.set_yticks(ticks)
    ax.set_yticklabels(labs, fontsize=8)
    ax.invert_yaxis()
    ax.axvline(0, color="#999", lw=0.8)
    ax.axvline(100 * cfg["verdict"]["rel_change_max"], color="#555", lw=0.8, ls="--")
    ax.set_xlabel("relative change, corrected vs uncorrected (%), covered seconds (95 % paired block-bootstrap CI)")
    ax.set_title("C3 — leave-one-tag-out differential correction (dashed = −10 % verdict bar)", fontsize=10)
    fig.tight_layout()
    fn = f"{STEM}_c3_correction_{cohort}.png"
    fig.savefig(fdir / fn, dpi=130)
    plt.close(fig)
    figs["c3"] = fn
    # 4) the 09-10 09:48 cluster
    SEC, W3 = A["SEC"], A["W3"]
    cc = cfg["cluster_case"]
    T = A["CC"]["T"]
    hw = float(cc["half_window_s"]) * 1000.0
    s = SEC[(SEC.period == cc["period"]) & (SEC.g_ms >= T - hw) & (SEC.g_ms <= T + hw)]
    if len(s):
        animals = sorted(SEC.animal.unique())
        fig, axs = plt.subplots(len(animals) + 1, 1, figsize=(11, 2.0 * (len(animals) + 1)), sharex=True)

        def nanbreak(t_ms, y):
            yv = np.asarray(y, float).copy()
            yv[np.r_[False, np.diff(np.asarray(t_ms)) > 1000]] = np.nan
            return (np.asarray(t_ms, float) - T) / 1000.0, yv
        for k, a in enumerate(animals):
            ax = axs[k]
            g = s[s.animal == a].sort_values("g_ms")
            if len(g):
                x, y = nanbreak(g.g_ms.to_numpy(), np.hypot(g.e10x_raw, g.e10y_raw))
                ax.plot(x, y, color="#9a9a9a", lw=1.0, label="raw, 10-s")
                if len(W3):
                    w = W3[(W3.animal == a) & (W3.method == "B2") & (W3.variant == "z")].sort_values("g_ms")
                    if len(w):
                        x, y = nanbreak(w.g_ms.to_numpy(), np.hypot(w.ux, w.uy))
                        ax.plot(x, y, color=TAGCOL[k % 5], lw=1.3, label="B2, 1-s")
                        x, y = nanbreak(w.g_ms.to_numpy(), np.hypot(w.ux - w.mhx, w.uy - w.mhy))
                        ax.plot(x, y, color="#333333", lw=0.9, ls=":", label="B2 − m̂ (z), 1-s")
                axs[-1].plot(*nanbreak(g.g_ms.to_numpy(), g.a_mean), color=TAGCOL[k % 5], lw=0.9, label=a)
            ax.axhline(12, color="#555", lw=0.7, ls="--")
            ax.axvline(0, color="#999", lw=0.8)
            ax.set_ylabel(f"{a}\n|residual| (in)")
            if k == 0:
                ax.legend(fontsize=8, ncol=3, loc="upper left")
        axs[-1].axvline(0, color="#999", lw=0.8)
        axs[-1].set_ylabel("anchors_used\n1-s mean")
        axs[-1].legend(fontsize=8, ncol=5, loc="lower left")
        axs[-1].set_xlabel(f"seconds from {cc['time']} (field-PC local); certified still seconds only")
        fig.suptitle("The 2026-09-10 09:48 episode: residual vs each segment's own median raw fix\n"
                     "dotted = after subtracting the same-zone still tags' mean residual (C3, z); dashed = 12 in", fontsize=9.5)
        fig.tight_layout()
        fn = f"{STEM}_cluster_0910_{cohort}.png"
        fig.savefig(fdir / fn, dpi=130)
        plt.close(fig)
        figs["cluster"] = fn
    # 5) anchor-loss categories
    ANC = A["ANC"]
    q = ANC[(ANC.family == "anchors_list") & (ANC.set.isin(["calm", "rain"])) & (ANC.zpg == "same_house") & ANC.method.isin(["raw", "B2"])]
    if len(q):
        cats = ["neither_lost", "one_lost", "both_lost_different", "shared_lost"]
        fig, axs = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
        for c, st in enumerate(["calm", "rain"]):
            ax = axs[c]
            for k, m in enumerate(["raw", "B2"]):
                xs, ys, lo_, hi_ = [], [], [], []
                for j, ct in enumerate(cats):
                    r = q[(q.set == st) & (q.method == m) & (q.category == ct)]
                    if len(r) and r.iloc[0].n_sec > 0:
                        r = r.iloc[0]
                        xs.append(j - 0.15 + 0.3 * k)
                        ys.append(r.rho_v)
                        lo_.append(r.rho_v - r.rho_v_lo)
                        hi_.append(r.rho_v_hi - r.rho_v)
                ax.errorbar(xs, ys, yerr=[lo_, hi_], fmt=MARK[m], color=COL[m], ms=6, capsize=2, lw=1.2, label=LABEL[m])
            ax.set_xticks(range(len(cats)))
            ax.set_xticklabels(["neither lost", "one lost", "both, different", "same anchor lost"])
            ax.axhline(0, color="#999", lw=0.8)
            ax.set_title(f"same house, {st}", fontsize=10)
        axs[0].set_ylabel("1-s vector correlation (lag 0)")
        axs[0].legend(fontsize=8)
        fig.suptitle("C1 — residual correlation by anchor loss (anchors_list), 95 % block-bootstrap CI", fontsize=10)
        fig.tight_layout()
        fn = f"{STEM}_c1_anchor_loss_{cohort}.png"
        fig.savefig(fdir / fn, dpi=130)
        plt.close(fig)
        figs["anchors"] = fn
    return figs


# ====================================================================================================== report
def _f(x, nd: int = 2) -> str:
    try:
        if x is None or not np.isfinite(float(x)):
            return "–"
    except (TypeError, ValueError):
        return str(x)
    return f"{float(x):.{nd}f}"


def _ci(r, k: str, nd: int = 2) -> str:
    if r is None:
        return "–"
    return f"{_f(r[k], nd)} [{_f(r[k + '_lo'], nd)}, {_f(r[k + '_hi'], nd)}]"


def _pc(r) -> str:
    if r is None:
        return "–"
    return f"{100 * r['rel_change']:+.1f} % [{100 * r['rel_lo']:+.1f}, {100 * r['rel_hi']:+.1f}]"


def _row(df: pd.DataFrame, **kw):
    if df is None or not len(df):
        return None
    m = np.ones(len(df), bool)
    for k, v in kw.items():
        m &= (df[k] == v).to_numpy()
    return df[m].iloc[0] if m.any() else None


DEFINITIONS = r"""
## Definitions

All positions are WISER **inches in the unverified offset frame**; only distances and correlations are reported, which
do not depend on the frame's origin or orientation. Times are field-PC local (EDT). Symbols: $i, j$ = tags (one per
animal: SF07, SF08, SF09, SF10, SF12); $\sigma_i$ = a certified still segment of tag $i$ (the failure audit's primary
segments, ≥ 30 s, 1 s trimmed at both ends; S50 or gate-v2 strict stillness of the head IMU, which carries the tag);
$[t^0_{\sigma}, t^1_{\sigma})$ its trimmed span; $\mathbf z_k$ = raw fix $k$ at IMU-aligned time $t_k$ ($t_k$ = WISER
time − the animal's lag $\tau^*$ of 0.10–0.20 s); $\hat{\mathbf p}_k$ = a method's position at fix $k$ (raw: $\mathbf z_k$;
B1, B2, B2′ as in the failure audit, at the fix times, saved in its `tracks/`).

### Truth of a still segment ($\mathbf c_\sigma$)
$$ \mathbf c_\sigma = \big(\operatorname{med}_{k\in\sigma} z_{k,x},\ \operatorname{med}_{k\in\sigma} z_{k,y}\big) $$
**Text:** the failure audit's truth, unchanged: the head is still, so the tag is one point; its estimate is the
coordinate-wise median of the segment's raw fixes. An error that is constant over the whole segment is absorbed into it and
is invisible here (every number below is a lower bound of the error, and of the common mode).

### 1-s and 10-s residuals ($\mathbf e^{(1)}_i(g)$, $\mathbf e^{(10)}_i(g)$)
$$ \tilde{\mathbf p}^{(L)}_i(g) = \operatorname{med}_{k:\ t_k\in[g-L/2,\ g+L/2)} \hat{\mathbf p}_k ,\qquad
   \mathbf e^{(L)}_i(g) = \tilde{\mathbf p}^{(L)}_i(g) - \mathbf c_{\sigma_i} $$
coordinate-wise medians on the integer seconds $g$ of the IMU-aligned clock, $L$ = 1 s (≥ 2 fixes) or 10 s (≥ 10 fixes, as
the audit's 10-s drift), with the window wholly inside the trimmed segment; otherwise undefined. **Text:** where WISER puts a
still head, relative to where it is, at the 1-s and 10-s time scales (in). 0 = perfect.

### Joint stillness (pair overlap $o$)
$$ o = [\max(t^0_{\sigma_i}, t^0_{\sigma_j}),\ \min(t^1_{\sigma_i}, t^1_{\sigma_j})),\qquad |o| \ge 30\ \text{s} $$
for every pair of tags and every pair of their segments. Pair-seconds = the grid seconds $g$ where both residuals are
defined (their windows then lie inside $o$). **Text:** both heads certified still at the same time; the ≥ 30-s rule is the
plan's (same as the primary segment rule).

### Zone and zone pairing
Zone of a segment = `house_1` / `house_2` when its truth lies inside the house ROI grown by 14 in, else `outside` (the audit's
`zone_detail`). Pairing of an overlap: **same house** (both in the same house), **different houses**, **house–outside**,
**both outside**. **Same zone** = same house or both outside (identical zone label); used by the verdict and by C3 variant z.

### Cross-tag residual correlation (C1; $\rho_x$, $\rho_y$, $\rho_v$)
Centred residuals $\mathbf{\bar e}_i(g) = \mathbf e_i(g) - \overline{\mathbf e_i}^{\,o}$, with $\overline{\mathbf e_i}^{\,o}$ =
the mean of $\mathbf e_i$ over the overlap's pair-seconds (both defined). Pooled sums over the pair-seconds $g$ of a stratum
(all its overlaps), at lag $\ell$ (tag $j$ taken at $g+\ell$, same overlap):
$$ S_{ab}^{(c)} = \sum_g \bar e_{a,c}(g)\,\bar e_{b,c}(g+\ell_{ab}),\qquad
   \rho_c = \frac{S_{ij}^{(c)}}{\sqrt{S_{ii}^{(c)} S_{jj}^{(c)}}}\ (c = x, y),\qquad
   \rho_v = \frac{\operatorname{tr} \mathbf S_{ij}}{\sqrt{\operatorname{tr}\mathbf S_{ii}\,\operatorname{tr}\mathbf S_{jj}}}
          = \frac{S^{(x)}_{ij}+S^{(y)}_{ij}}{\sqrt{(S^{(x)}_{ii}+S^{(y)}_{ii})(S^{(x)}_{jj}+S^{(y)}_{jj})}} $$
($\ell_{ij} = \ell$, $\ell_{ii} = \ell_{jj} = 0$ but restricted to the same seconds). **Text:** Pearson correlation of the two
tags' simultaneous errors per axis, and its vector form = the **common-mode share of variance**: if
$\mathbf e_i = \mathbf m + \mathbf n_i$ with a shared term $\mathbf m$ and independent $\mathbf n_i$ of equal variance,
$\rho_v = \operatorname{tr}\Sigma_m / (\operatorname{tr}\Sigma_m + \operatorname{tr}\Sigma_n)$. Range [−1, 1]; 0 = independent
errors, 1 = identical errors. Lags 0, ±1, ±2 s; scales 1 s and 10 s. Per-overlap values use the same formula on one overlap.
**Sensitivity (truth-centred):** the same with $\mathbf e$ instead of $\bar{\mathbf e}$ (second moments about the truth, so an
offset shared over a whole overlap counts as common mode); reported, not used by the verdict.

### Anchor loss (anchors_list)
Per fix, the cache's `anchors_list` = the anchors listed for the fix (a superset of the anchors used: anchors_used ≤ list
length in every fix; which listed anchors were used is not stored). Reference set of a segment
$\mathcal R_\sigma$ = anchors listed in ≥ 50 % of its fixes. An anchor $a\in\mathcal R_\sigma$ is **lost** in second $g$ when it is
listed in < 50 % of the fixes in $[g-0.5, g+0.5)$: $\mathcal L_i(g)$. Per pair-second: **neither lost**
($\mathcal L_i = \mathcal L_j = \varnothing$), **one lost** (exactly one non-empty), **both lost, different anchors**
(both non-empty, disjoint), **same anchor lost** ($\mathcal L_i\cap\mathcal L_j \ne \varnothing$). The 1-s, lag-0, overlap-centred
$\rho_v$ is computed within each category (sums restricted to its seconds, centring unchanged) and compared with "neither
lost" (difference with a paired bootstrap CI). Secondary: anchors_used, low = 1-s mean < 8; both low / one / neither.
**Text:** does the error become shared when both tags lose the same anchor? A pointer to an anchor-side cause, not a correction.

### Shared excursion and cluster
Pair-seconds with $\lVert\mathbf e^{(10)}_i\rVert \ge 12$ in **and** $\lVert\mathbf e^{(10)}_j\rVert \ge 12$ in (raw; 12 in = the
audit's crazy-drift size); a maximal run of consecutive such seconds within one overlap = an **event**, size
$=\max_g \min(\lVert\mathbf e^{(10)}_i\rVert, \lVert\mathbf e^{(10)}_j\rVert)$; events of all pairs that overlap in time (gap ≤ 1 s) = a
**cluster** (its tags = the union). Anchor enrichment = share of the top-20 clusters' event pair-seconds with anchor $a$ in
$\mathcal L_i\cap\mathcal L_j$ ÷ the same share over all valid joint pair-seconds. **Text:** moments when two or more still tags are
displaced ≥ 1 ft together, and which anchors were missing then.

### Pairwise-distance error (C2; $\varepsilon_{ij}$, SD, p95, p99, $R$)
$$ d_{ij}(g) = \lVert \tilde{\mathbf p}_i(g) - \tilde{\mathbf p}_j(g)\rVert,\quad d^{\text{truth}}_{ij} = \lVert\mathbf c_{\sigma_i}-\mathbf c_{\sigma_j}\rVert,\quad
   \varepsilon_{ij}(g) = d_{ij}(g) - d^{\text{truth}}_{ij} $$
$$ \mathrm{SD}_{\text{obs}} = \operatorname{SD}(\varepsilon),\qquad
   \mathrm{SD}^2_{\text{indep}} = \operatorname{Var}(\mathbf e_i\cdot\mathbf u) + \operatorname{Var}(\mathbf e_j\cdot\mathbf u),\qquad
   \mathbf u = \frac{\mathbf c_{\sigma_i}-\mathbf c_{\sigma_j}}{d^{\text{truth}}_{ij}},\qquad R = \mathrm{SD}_{\text{obs}}/\mathrm{SD}_{\text{indep}} $$
variances and SD pooled over the stratum's pair-seconds (about the stratum mean); p95 / p99 = quantiles of $|\varepsilon|$
(0.05-in histogram for the bootstrap; exact values also tabulated); mean $\varepsilon$ = bias. **Text:** how wrong an
inter-animal distance is while both animals are still (in). Since $\varepsilon \approx (\mathbf e_i - \mathbf e_j)\cdot\mathbf u$ for
$d^{\text{truth}} \gg$ the error, $R$ < 1 means the shared part of the two errors cancels in the distance, $R$ = 1 no
cancellation; for $d^{\text{truth}}$ < ~2 × the error the linearisation fails and $\varepsilon$ is biased upward (a distance
cannot be negative). Truth-distance bands: < 14 in, 14–48 in, > 48 in. **Resolvable distance difference** (stated, not adopted):
p95 $|\varepsilon|$ = the change in a single 1-s distance that exceeds its error 95 % of the time.

### Leave-one-tag-out differential correction (C3; $\hat{\mathbf m}_{-i}$)
$$ \hat{\mathbf m}_{-i}(g) = \frac{1}{|J_i(g)|}\sum_{j\in J_i(g)} \mathbf e^{(1)}_j(g),\qquad
   \mathbf v_i(g) = \mathbf e^{(1)}_i(g) - \hat{\mathbf m}_{-i}(g) $$
$J_i(g)$ = the other tags with a defined 1-s residual of the same method at $g$ (i.e. inside one of their certified segments);
variant **z**: only tags whose segment has the same zone label as $i$'s; variant **a**: any zone. Defined when
$|J_i(g)|\ge 1$ (**covered** seconds); coverage = covered seconds ÷ the target's certified seconds. Non-circular for the target:
$\hat{\mathbf m}_{-i}$ uses neither $i$'s fixes nor its truth. Inputs: raw-1-s and B2-1-s (the references use the same method).
**Metrics, on the covered seconds of each target segment, uncorrected $\mathbf e^{(1)}_i$ vs corrected $\mathbf v_i$ (same seconds):**
1-s RMS $=(\sum_g\lVert\cdot\rVert^2/N_{\text{cov}})^{1/2}$ pooled over segments; 10-s drift of a segment
$=\max_c \lVert\operatorname{med}\{\cdot(g): g\in[c-5, c+5)\}\rVert$ over 1-s centres $c$ with the window inside the segment's grid
and ≥ 5 covered seconds (coordinate-wise median), summarised by the median and p90 over segments; ≥ 12-in events = runs of
≥ 10 consecutive centres with that 10-s distance ≥ 12 in (the audit's crazy-drift rule on the 1-s series), counted per
covered hour. Secondary "whole-segment" versions use every certified second ($\mathbf v_i = \mathbf e_i$ where uncovered).
**Relative change** $=\theta_{\text{corrected}}/\theta_{\text{uncorrected}} - 1$; < 0 = the correction helps. **Text:** what
subtracting the simultaneous error of other still tags does to a tag's own still error.

### Expected C3 ratio (analytic check, added in this step)
$$ \frac{\mathrm{RMS}(\mathbf v)}{\mathrm{RMS}(\mathbf e)} \approx \sqrt{(1-\rho)\,(1 + 1/\bar n)},\qquad \text{break-even } \rho = \frac{1}{\bar n + 1} $$
under $\mathbf e_k = \mathbf m + \mathbf n_k$ (shared $\mathbf m$ of share $\rho$, independent $\mathbf n_k$ of equal variance);
$\rho$ = the truth-centred 1-s $\rho_v$ of the matching pairing, $\bar n$ = the mean number of references over covered seconds
(weighted by covered seconds). **Text:** each reference removes its share of the common mode but adds its own independent
error; the correction helps only when the shared share exceeds $1/(\bar n+1)$. A consistency check, not a criterion.

### Reproduction (1-s vs per-fix RMS)
1-s RMS $=(\sum_g\lVert\mathbf e^{(1)}(g)\rVert^2/N_g)^{1/2}$ over all certified grid seconds of a tag (each second weight 1);
fix-weighted: each second weighted by its fix count $n_1(g)$; per-fix RMS = the audit's $(\sum_k r_k^2/N)^{1/2}$ over the same
segments' fixes. **Text:** the plan's consistency check; the median of a second's fixes removes jitter, so the 1-s value should
not exceed the per-fix value.

### Block bootstrap (95 % CI)
Blocks = 10 min of clock time within a period (all pairs / tags in that window together, because simultaneous pairs share
tags and the common mode itself); the blocks holding a stratum's data are drawn with replacement 1000 times (seed
20261003 + section); every statistic is recomputed from the per-block sums (correlations, variances, RMS), per-block
0.05-in histograms (|ε| quantiles) or block-weighted lower quantiles over segments (drift median / p90); CI = 2.5–97.5 % of
the resampled values. Within a stratum the same resamples serve every method, scale, lag and category (paired comparisons);
C3's corrected and uncorrected values are computed on the same resample (paired relative change).

### Pre-registered verdict (plan)
**Material** if (1) the pooled same-zone $\rho_v$ of 10-s B2 residuals (lag 0, overlap-centred, all periods) is ≥ 0.3 with
its CI lower bound > 0, **and** (2) C3 variant z with B2 input reduces the target's 10-s drift p90 **or** its 1-s RMS by
≥ 10 % (relative change ≤ −10 % and CI upper bound < 0). **Material for raw only** when (1)–(2) hold for raw but not for B2;
otherwise **not material**. No change to the 14-in distance rule is made in this step.
"""


def expected_ratio(rho: float, nref: float) -> float:
    """RMS ratio corrected / uncorrected under e_k = m + n_k (shared m, independent n_k of equal variance, share rho) with
    nref references: v = n_i - mean(n_j) -> Var = (1 - rho)(1 + 1/nref) of the uncorrected variance."""
    return float(np.sqrt((1.0 - rho) * (1.0 + 1.0 / nref))) if nref > 0 else np.nan


def c3_check(A: dict) -> pd.DataFrame:
    """Analytic check of C3 (not pre-registered): predicted RMS ratio from the measured 1-s same-zone rho and the mean
    number of references, vs the observed one, per input x variant x set."""
    C1, S3, C3S = A["C1"], A["S3"], A["C3S"]
    rows = []
    for m in sorted(C3S.method.unique()):
        for var in sorted(C3S.variant.unique()):
            for st in SETS:
                zp = "same_zone" if var == "z" else "all"
                r = _row(C1, zpg=zp, set=st, kind="all", method=m, scale="1s", lag_s=0, center="truth")
                d = C3S[(C3S.method == m) & (C3S.variant == var) & ((C3S.set == st) if st != "all" else True)]
                w = d.n_cov.to_numpy(float)
                nref = float(np.average(d.nref_mean[w > 0], weights=w[w > 0])) if (w > 0).any() else np.nan
                o = _row(S3, set=st, kind="all", zone="all", method=m, variant=var, metric="rms_1s")
                if r is None or o is None:
                    continue
                rows.append({"method": m, "variant": var, "set": st, "rho_1s_truth": float(r.rho_v), "nref_mean": nref,
                             "predicted_ratio": expected_ratio(float(r.rho_v), nref), "observed_ratio": float(1 + o.rel_change),
                             "break_even_rho": 1.0 / (nref + 1.0) if np.isfinite(nref) else np.nan})
    return pd.DataFrame(rows)


def findings(A: dict, cfg: dict) -> list:
    """Plain-language findings, every number taken from the tables of this run."""
    C1, C2, S3, SX, ANC, CC = A["C1"], A["C2"], A["S3"], A["SX"], A["ANC"], A["CC"]
    g1 = lambda **k: _row(C1, kind="all", lag_s=0, center="overlap", **k)  # noqa: E731
    L = ["## Findings\n"]
    bc, br = g1(zpg="same_zone", set="calm", method="B2", scale="10s"), g1(zpg="same_zone", set="rain", method="B2", scale="10s")
    b1c, b1r = g1(zpg="same_zone", set="calm", method="B2", scale="1s"), g1(zpg="same_zone", set="rain", method="B2", scale="1s")
    dh = g1(zpg="diff_house", set="calm", method="B2", scale="10s")
    if bc is not None and br is not None:
        L.append(f"- **The still error is mostly not shared.** Same-zone (in practice: same-house) B2 residuals correlate "
                 f"ρ_v = {_ci(bc, 'rho_v')} in calm-dry periods and {_ci(br, 'rho_v')} in rain at 10 s "
                 f"(1 s: {_f(b1c.rho_v)} | {_f(b1r.rho_v)}); tags in different houses {_ci(dh, 'rho_v')} (calm). The shared part is "
                 f"stronger along the WISER x axis in rain (ρ_x {_f(b1r.rho_x)} vs ρ_y {_f(b1r.rho_y)}, 1 s) — a frame-axis statement, "
                 f"not a physical direction.")
    a_u = _row(ANC, family="anchors_used", category="both_low", zpg="same_house", set="rain", method="raw")
    a_l = _row(ANC, family="anchors_list", category="shared_lost", zpg="same_house", set="rain", method="raw")
    a_lc = _row(ANC, family="anchors_list", category="shared_lost", zpg="same_house", set="calm", method="raw")
    if a_u is not None and a_l is not None:
        L.append(f"- **Where it is shared, fewer / the same missing anchors are involved.** In rain, same-house 1-s raw correlation is "
                 f"{_f(a_l.rho_v)} in the {100 * a_l.share:.1f} % of seconds when both tags lost the same listed anchor (Δ vs neither "
                 f"lost {_f(a_l.diff_vs_ref)} [{_f(a_l.diff_lo)}, {_f(a_l.diff_hi)}]; calm Δ {_f(a_lc.diff_vs_ref)} "
                 f"[{_f(a_lc.diff_lo)}, {_f(a_lc.diff_hi)}]) and {_f(a_u.rho_v)} when both used < 8 anchors (Δ {_f(a_u.diff_vs_ref)} "
                 f"[{_f(a_u.diff_lo)}, {_f(a_u.diff_hi)}]).")
    CL, ENR = SX["CL"], SX["ENR"]
    if len(CL):
        days = sorted(CL.start_local.str[:10].unique())
        e104 = ENR.sort_values("enrichment", ascending=False).iloc[0] if len(ENR) else None
        L.append(f"- **Shared ≥ 12-in excursions are rare and confined to one episode:** {SX['n_both']} of {SX['n_valid']} joint "
                 f"pair-seconds ({100 * SX['n_both'] / max(SX['n_valid'], 1):.3f} %), {len(CL)} clusters, all on {', '.join(days)} between "
                 f"{CL.start_local.min()[11:]} and {CL.start_local.max()[11:]} (rain day). Anchor {int(e104.anchor) if e104 is not None else '–'} "
                 f"was lost by both tags in {100 * e104.shared_lost_top:.0f} % of their seconds vs {100 * e104.shared_lost_all:.1f} % of all "
                 f"joint seconds (enrichment {_f(e104.enrichment, 1)}) — a pointer to an anchor-side cause, not a correction.")
    c2a = _row(C2, zpg="all", set="all", kind="all", band="all", method="B2", scale="1s")
    c2c = _row(C2, zpg="all", set="calm", kind="all", band="all", method="B2", scale="1s")
    c2r = _row(C2, zpg="all", set="rain", kind="all", band="all", method="B2", scale="1s")
    c2h = _row(C2, zpg="same_house", set="all", kind="all", band="all", method="B2", scale="1s")
    c2d = _row(C2, zpg="diff_house", set="all", kind="all", band="all", method="B2", scale="1s")
    c2w = _row(C2, zpg="all", set="all", kind="all", band="all", method="raw", scale="1s")
    if c2a is not None:
        L.append(f"- **Inter-animal distances of still animals are precise:** B2 1-s distance error p95 |ε| = {_ci(c2a, 'p95_abs')} in "
                 f"(calm {_f(c2c.p95_abs)}, rain {_f(c2r.p95_abs)}; same house {_f(c2h.p95_abs)}, different houses {_f(c2d.p95_abs)}; raw "
                 f"{_f(c2w.p95_abs)}). The shared error cancels only a little: R = {_ci(c2a, 'R')} (calm {_f(c2c.R)}, rain "
                 f"{_f(c2r.R)}). The 14-in rule is unchanged; a tighter value for still animals is a proposal to the user.")
    s3z = _row(S3, set="all", kind="all", zone="all", method="B2", variant="z", metric="rms_1s")
    s3c = _row(S3, set="calm", kind="all", zone="all", method="B2", variant="z", metric="rms_1s")
    s3r = _row(S3, set="rain", kind="all", zone="all", method="B2", variant="z", metric="rms_1s")
    ev = _row(S3, set="all", kind="all", zone="all", method="B2", variant="z", metric="events12")
    chk = c3_check(A)
    ck_c = _row(chk, method="B2", variant="z", set="calm")
    ck_r = _row(chk, method="B2", variant="z", set="rain")
    if s3z is not None:
        L.append(f"- **Differential correction from other still tags hurts on average:** B2 1-s RMS {_pc(s3z)} (calm {_pc(s3c)}, rain "
                 f"{_pc(s3r)}), coverage {100 * s3z.coverage:.0f} %. With a small shared share each reference adds its own "
                 f"independent error; the equal-noise model predicts × {_f(ck_c.predicted_ratio)} in calm (observed × "
                 f"{_f(ck_c.observed_ratio)}) and × {_f(ck_r.predicted_ratio)} in rain (observed × {_f(ck_r.observed_ratio)}); the "
                 f"correction only pays when ρ exceeds ≈ 1/(n_ref + 1) ({_f(ck_c.break_even_rho)} calm, {_f(ck_r.break_even_rho)} rain). "
                 f"It does remove the shared episodes (≥ 12-in events {int(ev.events_u)} → {int(ev.events_v)}).")
    ct = CC["tags"]
    if len(ct) and "B2_z_rms_u_cov" in ct:
        imp = ", ".join(f"{r.animal} {_f(r.B2_z_rms_u_cov, 1)} → {_f(r.B2_z_rms_v_cov, 1)}" for r in ct.itertuples())
        L.append(f"- **09-10 09:48 episode:** B2 1-s RMS in the ± 5-min window, uncorrected → corrected (z): {imp} in — the displaced "
                 f"tags improve, the undisplaced ones get worse.")
    L.append("")
    return L


def render_report(A: dict, cfg: dict, out: Path, figs: dict, meta: dict) -> str:
    cohort = cfg["_cohort"]
    V, C1, C2, S3, ANC, ABIT = A["V"], A["C1"], A["C2"], A["S3"], A["ANC"], A["ANC_BIT"]
    OV, SX, CC, REP = A["OV"], A["SX"], A["CC"], A["REP"]
    L = []
    L.append(f"# WISER common-mode error across tags and pairwise-distance precision ({cohort})\n")
    L.append(f"**Step C** of the A → B → C sequence approved by the user on 2026-10-03. **Plan (pre-registered, with amendments):** "
             f"[`{PLAN}`](../../../../{PLAN}). **Driver:** `{DRIVER}` (`--selftest`). **Config:** `{meta['config']}`.  ")
    L.append(f"**Bulk run:** `{out}` (pointer `run_manifest_common_mode_{cohort}.json`). **Git:** {meta['git_commit']}. "
             f"**Inputs:** the failure audit's run `{cfg['audit_run']}` (certified segments, truths, saved tracks raw/B1/B2/B2′) and the "
             f"WISER fix caches (`anchors_list`); read-only, no SQLite, no IMU, no Kalman run.\n")
    L.append("All positions are in the unverified WISER inch frame; only distances and correlations are used. Joint stillness is "
             "almost all inside the two houses (often huddles), so the common mode between distant tags and in the open field is "
             "barely sampled; each segment's truth is its own median raw fix, so an offset constant over a whole segment is invisible.\n")
    # ---- verdict
    vb, vr = V["B2"], V["raw"]
    L.append("## Verdict (pre-registered)\n")
    L.append(f"**Common mode: {V['verdict'].upper()}.**\n")
    L.append("| criterion | B2 | raw |\n|---|---|---|")
    L.append(f"| (1) pooled same-zone ρ_v, 10-s residuals, lag 0 (≥ 0.3, CI > 0) | {_f(vb['cond1']['rho_v'])} [{_f(vb['cond1']['lo'])}, {_f(vb['cond1']['hi'])}] → "
             f"{'pass' if vb['cond1']['ok'] else 'fail'} | {_f(vr['cond1']['rho_v'])} [{_f(vr['cond1']['lo'])}, {_f(vr['cond1']['hi'])}] → {'pass' if vr['cond1']['ok'] else 'fail'} |")
    for met, lab in (("drift10_p90", "10-s drift p90"), ("rms_1s", "1-s RMS")):
        pb, pr = vb["cond2"]["parts"].get(met, {}), vr["cond2"]["parts"].get(met, {})
        fmt = lambda p: (f"{100 * p['rel']:+.1f} % [{100 * p['lo']:+.1f}, {100 * p['hi']:+.1f}] → {'pass' if p['ok'] else 'fail'}") if p and np.isfinite(p.get("rel", np.nan)) else "–"  # noqa: E731
        L.append(f"| (2) C3 variant z, {lab} (≤ −10 %, CI < 0) | {fmt(pb)} | {fmt(pr)} |")
    L.append(f"| both | {'yes' if vb['both'] else 'no'} | {'yes' if vr['both'] else 'no'} |\n")
    L.extend(findings(A, cfg))
    # ---- coverage
    L.append("## Joint stillness\n")
    cov = A["cov"]
    L.append(f"{len(OV)} pair overlaps ≥ {cfg['overlap_min_s']:.0f} s, {A['res']['pair_hours']:.1f} pair-hours "
             f"(certified still time of all tags: {A['res']['certified_hours']:.1f} tag-hours on the 1-s grid).\n")
    L.append("| zone pairing | calm overlaps | calm pair-h | rain overlaps | rain pair-h |\n|---|---|---|---|---|")
    for zp in ZP:
        rc, rr = _row(cov, zp=zp, set="calm"), _row(cov, zp=zp, set="rain")
        L.append(f"| {ZLABEL[zp]} | {int(rc.n_ov) if rc is not None else 0} | {_f(rc.hours, 1) if rc is not None else '0'} | "
                 f"{int(rr.n_ov) if rr is not None else 0} | {_f(rr.hours, 1) if rr is not None else '0'} |")
    dmed = OV.groupby("zp").d_truth.median()
    L.append("\nMedian truth distance per pairing: " + ", ".join(f"{ZLABEL[z]} {_f(dmed.get(z), 1)} in" for z in ZP if z in dmed) + ".\n")
    # ---- C1
    L.append("## C1 — is the error shared?\n")
    L.append(f"![C1]({'../figures/' + figs['c1']})\n" if "c1" in figs else "")
    L.append("Pooled vector correlation $\\rho_v$ of the residuals (lag 0, overlap-centred) with 95 % block-bootstrap CIs; "
             "calm | rain.\n")
    L.append("| method | scale | same zone | same house | different houses | house–outside |\n|---|---|---|---|---|---|")
    for m in cfg["methods"]:
        for sc in SCALES:
            cells = []
            for zp in ["same_zone", "same_house", "diff_house", "house_outside"]:
                rc = _row(C1, zpg=zp, set="calm", kind="all", method=m, scale=sc, lag_s=0, center="overlap")
                rr = _row(C1, zpg=zp, set="rain", kind="all", method=m, scale=sc, lag_s=0, center="overlap")
                cells.append(f"{_ci(rc, 'rho_v')} \\| {_ci(rr, 'rho_v')}")
            L.append(f"| {LABEL[m]} | {sc} | " + " | ".join(cells) + " |")
    small = C1[(C1.kind == "all") & (C1.lag_s == 0) & (C1.center == "overlap") & (C1.method == "B2") & (C1.scale == "1s")
               & (C1.set != "all") & C1.zpg.isin(["diff_house", "house_outside", "both_outside"]) & (C1.n_blocks < 10)]
    if len(small):
        L.append("\nStrata resting on fewer than 10 ten-minute blocks (their CIs are not reliable): "
                 + "; ".join(f"{ZLABEL[r.zpg]}, {r.set}: {r.hours:.1f} pair-h in {r.n_blocks} blocks" for r in small.itertuples()) + ".")
    L.append("\nAll periods pooled (calm + rain), same zone; per axis, day | night, lags and the truth-centred sensitivity:\n")
    L.append("| method | scale | ρ_v | ρ_x | ρ_y | day ρ_v | night ρ_v | lag −1 / +1 s ρ_v | lag −2 / +2 s ρ_v | truth-centred ρ_v | pair-h |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for m in cfg["methods"]:
        for sc in SCALES:
            r0 = _row(C1, zpg="same_zone", set="all", kind="all", method=m, scale=sc, lag_s=0, center="overlap")
            rd = _row(C1, zpg="same_zone", set="all", kind="day", method=m, scale=sc, lag_s=0, center="overlap")
            rn = _row(C1, zpg="same_zone", set="all", kind="night", method=m, scale=sc, lag_s=0, center="overlap")
            lg = {L_: _row(C1, zpg="same_zone", set="all", kind="all", method=m, scale=sc, lag_s=L_, center="overlap") for L_ in (-2, -1, 1, 2)}
            rt = _row(C1, zpg="same_zone", set="all", kind="all", method=m, scale=sc, lag_s=0, center="truth")
            L.append(f"| {LABEL[m]} | {sc} | {_ci(r0, 'rho_v')} | {_ci(r0, 'rho_x')} | {_ci(r0, 'rho_y')} | {_ci(rd, 'rho_v')} | {_ci(rn, 'rho_v')} | "
                     f"{_f(lg[-1].rho_v if lg[-1] is not None else np.nan)} / {_f(lg[1].rho_v if lg[1] is not None else np.nan)} | "
                     f"{_f(lg[-2].rho_v if lg[-2] is not None else np.nan)} / {_f(lg[2].rho_v if lg[2] is not None else np.nan)} | "
                     f"{_ci(rt, 'rho_v')} | {_f(r0.hours if r0 is not None else np.nan, 1)} |")
    PO = A["PO"]
    if len(PO):
        q = PO[(PO.method == "B2") & (PO.scale == "10s") & PO.zp.isin(cfg["same_zone_pairings"])]
        if len(q):
            L.append(f"\nPer-overlap ρ_v (B2, 10-s, same zone, {len(q)} overlaps): median {_f(q.rho_v.median())}, IQR "
                     f"{_f(q.rho_v.quantile(0.25))}–{_f(q.rho_v.quantile(0.75))}; share > 0.3: {100 * (q.rho_v > 0.3).mean():.0f} %.\n")
    # anchors
    L.append("### Anchor sets (anchors_list)\n")
    L.append(f"![anchors]({'../figures/' + figs['anchors']})\n" if "anchors" in figs else "")
    L.append("1-s ρ_v (lag 0, overlap-centred) by anchor-loss category; difference vs \"neither lost\" with a paired CI. "
             "Same house, calm | rain.\n")
    L.append("| method | category | share of seconds (calm \\| rain) | ρ_v calm | ρ_v rain | Δ vs neither, calm | Δ vs neither, rain |\n|---|---|---|---|---|---|---|")
    for m in ("raw", "B2"):
        for fam, cats in (("anchors_list", ["neither_lost", "one_lost", "both_lost_different", "shared_lost"]),
                          ("anchors_used", ["neither_low", "one_low", "both_low"])):
            for ct in cats:
                rc = _row(ANC, family=fam, category=ct, zpg="same_house", set="calm", method=m)
                rr = _row(ANC, family=fam, category=ct, zpg="same_house", set="rain", method=m)
                sh = f"{100 * rc.share:.1f} % \\| {100 * rr.share:.1f} %" if rc is not None and rr is not None else "–"
                dc = f"{_f(rc.diff_vs_ref)} [{_f(rc.diff_lo)}, {_f(rc.diff_hi)}]" if rc is not None and ct not in ("neither_lost", "neither_low") else ""
                dr = f"{_f(rr.diff_vs_ref)} [{_f(rr.diff_lo)}, {_f(rr.diff_hi)}]" if rr is not None and ct not in ("neither_lost", "neither_low") else ""
                L.append(f"| {LABEL[m]} | {fam}: {ct.replace('_', ' ')} | {sh} | {_ci(rc, 'rho_v')} | {_ci(rr, 'rho_v')} | {dc} | {dr} |")
    if len(ABIT):
        q = ABIT[ABIT.method == "raw"].sort_values("anchor")
        L.append("\nPer anchor (raw, all pairings and periods): seconds in which both tags lost that anchor, their 1-s ρ_v, and how often "
                 "both 10-s residuals were ≥ 12 in then.\n")
        L.append("| anchor | shared-lost seconds | share | 1-s ρ_v | both ≥ 12 in (10-s) |\n|---|---|---|---|---|")
        for r in q.itertuples():
            L.append(f"| {r.anchor} | {r.n_sec_shared_lost} | {100 * r.share:.2f} % | {_f(r.rho_v)} [{_f(r.rho_v_lo)}, {_f(r.rho_v_hi)}] | "
                     f"{'–' if not np.isfinite(r.both_e10_ge12_share) else f'{100 * r.both_e10_ge12_share:.1f} %'} |")
    CL, ENR = SX["CL"], SX["ENR"]
    L.append(f"\n### Shared excursions\n\n{SX['n_both']} of {SX['n_valid']} valid joint pair-seconds have both raw 10-s residuals ≥ 12 in; "
             f"{len(SX['EV'])} events in {len(CL)} clusters. Largest clusters (raw 10-s; size = the larger of the two tags' smaller residual):\n")
    if len(CL):
        L.append("| start (local) | dur s | tags | pairings | size in | anchors_used mean | same anchor lost (share of seconds) | top shared-lost anchors |\n|---|---|---|---|---|---|---|---|")
        for r in CL.head(int(cfg["shared_excursion"]["top_n"])).itertuples():
            L.append(f"| {r.start_local} | {r.dur_s:.0f} | {r.tags} | {r.pairings.replace('_', ' ')} | {r.size_in:.1f} | {r.a_mean:.1f} | "
                     f"{100 * r.shared_lost_any_share:.0f} % | {r.top_shared_lost or '–'} |")
    if len(ENR):
        L.append("\nAnchor enrichment in the top clusters (share of event pair-seconds where both tags lost the anchor ÷ the same share over all joint pair-seconds):\n")
        L.append("| anchor | top clusters | all joint | enrichment | either tag lost: top / all |\n|---|---|---|---|---|")
        for r in ENR.itertuples():
            L.append(f"| {r.anchor} | {100 * r.shared_lost_top:.1f} % | {100 * r.shared_lost_all:.1f} % | {_f(r.enrichment, 1)} | "
                     f"{100 * r.either_lost_top:.1f} % / {100 * r.either_lost_all:.1f} % |")
    # ---- C2
    L.append("\n## C2 — pairwise-distance precision\n")
    L.append(f"![C2]({'../figures/' + figs['c2']})\n" if "c2" in figs else "")
    L.append("1-s distances, all periods; error $\\varepsilon = d - d^{\\text{truth}}$ (in). SD, p95 and R with 95 % block-bootstrap CIs.\n")
    L.append("| method | pairing | pair-h | mean ε | SD ε | p95 \\|ε\\| | p99 \\|ε\\| | SD_indep | R |\n|---|---|---|---|---|---|---|---|---|")
    for m in cfg["methods"]:
        for zp in ["all", "same_house", "diff_house", "house_outside"]:
            r = _row(C2, zpg=zp, set="all", kind="all", band="all", method=m, scale="1s")
            if r is None:
                continue
            L.append(f"| {LABEL[m]} | {ZLABEL[zp]} | {_f(r.hours, 1)} | {_f(r.mean_err)} | {_ci(r, 'sd_err')} | {_ci(r, 'p95_abs')} | {_f(r.p99_abs)} | "
                     f"{_f(r.sd_indep)} | {_ci(r, 'R')} |")
    L.append("\nBy truth distance (all pairings), calm | rain, 1-s and 10-s — p95 |ε| (in) and R:\n")
    L.append("| method | band | pair-h | p95 1-s calm \\| rain | p95 10-s calm \\| rain | R 1-s (all) | mean ε 1-s |\n|---|---|---|---|---|---|---|")
    for m in cfg["methods"]:
        for bd in BANDS:
            r = _row(C2, zpg="all", set="all", kind="all", band=bd, method=m, scale="1s")
            if r is None:
                continue
            c1_ = _row(C2, zpg="all", set="calm", kind="all", band=bd, method=m, scale="1s")
            r1_ = _row(C2, zpg="all", set="rain", kind="all", band=bd, method=m, scale="1s")
            c10 = _row(C2, zpg="all", set="calm", kind="all", band=bd, method=m, scale="10s")
            r10 = _row(C2, zpg="all", set="rain", kind="all", band=bd, method=m, scale="10s")
            g = lambda x: _f(x.p95_abs) if x is not None else "–"  # noqa: E731
            L.append(f"| {LABEL[m]} | {bd} | {_f(r.hours, 1)} | {g(c1_)} \\| {g(r1_)} | {g(c10)} \\| {g(r10)} | {_ci(r, 'R')} | {_f(r.mean_err)} |")
    rb = _row(C2, zpg="all", set="all", kind="all", band="all", method="B2", scale="1s")
    if rb is not None:
        L.append(f"\n**Distance precision statement (pre-registered):** during joint stillness the B2 1-s inter-animal distance error has "
                 f"p95 |ε| = {_f(rb.p95_abs)} in [{_f(rb.p95_abs_lo)}, {_f(rb.p95_abs_hi)}] (all pairings and periods; per pairing and "
                 f"band in the tables). A single 1-s B2 distance therefore resolves a difference of about {_f(rb.p95_abs, 1)} in at 95 %; "
                 f"comparing two independent 1-s distances needs about √2 × that. **No change to the 14-in rule is made here**; a tighter "
                 f"value is a proposal to the user, and it holds only for still animals mostly in the houses (moving-animal distances "
                 f"have no truth here).\n")
    # ---- C3
    L.append("## C3 — differential correction, leave-one-tag-out\n")
    L.append(f"![C3]({'../figures/' + figs['c3']})\n" if "c3" in figs else "")
    L.append("Covered seconds only (corrected and uncorrected on the same seconds); relative change with paired 95 % block-bootstrap CI.\n")
    L.append("| input | variant | coverage | 1-s RMS unc → cor (in) | Δ 1-s RMS | 10-s drift p90 unc → cor | Δ drift p90 | Δ drift median | ≥ 12-in events unc → cor | Δ whole-segment RMS |\n|---|---|---|---|---|---|---|---|---|---|")
    for m in cfg["c3"]["methods"]:
        for var in cfg["c3"]["variants"]:
            g_ = lambda met: _row(S3, set="all", kind="all", zone="all", method=m, variant=var, metric=met)  # noqa: E731
            rr, dp, dm, ev, rw = g_("rms_1s"), g_("drift10_p90"), g_("drift10_med"), g_("events12"), g_("rms_1s_whole")
            if rr is None:
                continue
            L.append(f"| {LABEL[m]} | {var} | {100 * rr.coverage:.1f} % | {_f(rr.uncorrected)} → {_f(rr.corrected)} | {_pc(rr)} | "
                     f"{_f(dp.uncorrected if dp is not None else np.nan)} → {_f(dp.corrected if dp is not None else np.nan)} | {_pc(dp)} | {_pc(dm)} | "
                     f"{int(ev.events_u) if ev is not None else 0} → {int(ev.events_v) if ev is not None else 0} | {_pc(rw)} |")
    L.append("\nBy stratum (variant z): Δ 1-s RMS and Δ 10-s drift p90, coverage.\n")
    L.append("| input | stratum | coverage | Δ 1-s RMS | Δ drift p90 |\n|---|---|---|---|---|")
    for m in cfg["c3"]["methods"]:
        for st, kd, zn in [("calm", "all", "all"), ("rain", "all", "all"), ("all", "day", "all"), ("all", "night", "all"),
                           ("all", "all", "house"), ("all", "all", "outside")]:
            rr = _row(S3, set=st, kind=kd, zone=zn, method=m, variant="z", metric="rms_1s")
            dp = _row(S3, set=st, kind=kd, zone=zn, method=m, variant="z", metric="drift10_p90")
            if rr is None:
                continue
            L.append(f"| {LABEL[m]} | {st} / {kd} / {zn} | {100 * rr.coverage:.1f} % | {_pc(rr)} | {_pc(dp)} |")
    chk = c3_check(A)
    if len(chk):
        L.append("\n**Analytic check (added in this step, not pre-registered).** If $\\mathbf e_k = \\mathbf m + \\mathbf n_k$ with a shared "
                 "share ρ and independent errors of equal variance, subtracting the mean of $n$ references gives "
                 "$\\mathrm{Var}(\\mathbf v)/\\mathrm{Var}(\\mathbf e) = (1-\\rho)(1+1/n)$, so the correction helps only when "
                 "ρ > 1/(n + 1). ρ = the truth-centred 1-s ρ_v of the matching pairing (same zone for z, all for a); n = the mean number "
                 "of references over covered seconds.\n")
        L.append("| input | variant | set | ρ (1 s) | mean refs | break-even ρ | predicted RMS ratio | observed |\n|---|---|---|---|---|---|---|---|")
        for r in chk.itertuples():
            L.append(f"| {LABEL[r.method]} | {r.variant} | {r.set} | {_f(r.rho_1s_truth)} | {_f(r.nref_mean)} | {_f(r.break_even_rho)} | "
                     f"{_f(r.predicted_ratio)} | {_f(r.observed_ratio)} |")
    # ---- cluster case
    L.append("\n## The 2026-09-10 09:48 cluster\n")
    L.append(f"![cluster]({'../figures/' + figs['cluster']})\n" if "cluster" in figs else "")
    ct = CC["tags"]
    if len(ct):
        L.append(f"Certified still seconds within ± {cfg['cluster_case']['half_window_s'] // 60:.0f} min of {cfg['cluster_case']['time']} (residual vs each segment's own truth):\n")
        L.append("| tag | certified s | max raw 10-s (in) at | max B2 10-s | anchors_used mean / min | most-lost anchors | B2 z: coverage, 1-s RMS \\|e\\| → \\|e − m̂\\| (max) | raw z: 1-s RMS \\|e\\| → \\|e − m̂\\| |\n|---|---|---|---|---|---|---|---|")
        for r in ct.itertuples():
            bz = (f"{100 * getattr(r, 'B2_z_cov', np.nan):.0f} %, {_f(getattr(r, 'B2_z_rms_u_cov', np.nan), 1)} → {_f(getattr(r, 'B2_z_rms_v_cov', np.nan), 1)} "
                  f"({_f(getattr(r, 'B2_z_u_max_cov', np.nan), 1)} → {_f(getattr(r, 'B2_z_v_max_cov', np.nan), 1)})") if hasattr(r, "B2_z_cov") else "–"
            rz = f"{_f(getattr(r, 'raw_z_rms_u_cov', np.nan), 1)} → {_f(getattr(r, 'raw_z_rms_v_cov', np.nan), 1)}" if hasattr(r, "raw_z_cov") else "–"
            L.append(f"| {r.animal} | {r.n_sec} | {_f(r.raw10_max_in, 1)} at {r.raw10_max_at[11:]} | {_f(r.B2_10_max_in, 1)} | {_f(r.a_mean, 1)} / {_f(r.a_min_1s, 1)} | "
                     f"{r.lost_top or '–'} | {bz} | {rz} |")
    hit = CC["clusters"]
    if len(hit):
        L.append("\nShared-excursion clusters in this window:\n")
        L.append("| start | dur s | tags | size in | top shared-lost anchors |\n|---|---|---|---|---|")
        for r in hit.itertuples():
            L.append(f"| {r.start_local} | {r.dur_s:.0f} | {r.tags} | {r.size_in:.1f} | {r.top_shared_lost or '–'} |")
    # ---- reproduction
    L.append("\n## Reproduction\n")
    chk = REP["chk"]
    L.append(f"Segments re-read: {chk['n_segments']}; fix-count mismatches vs the audit: {chk['fix_count_mismatch']}; max |recomputed − audit truth| "
             f"{_f(chk['truth_dev_max_in'], 4)} in (float32 storage of the tracks). Per-tag still RMS on the 1-s grid vs the audit's per-fix RMS "
             f"(they differ by construction; the plan expects the 1-s value ≤ the per-fix one): "
             f"{'all ≤' if chk['all_rms_1s_le_fix'] else 'raw: all ≤; B2: NOT all ≤ (see the table and the note below)'}; "
             f"with each second weighted by its fix count: {'all ≤' if chk.get('all_rms_1s_fixweighted_le_fix') else 'NOT all ≤'}.\n")
    L.append("| tag | set | 1-s RMS raw | per-fix RMS raw | 1-s RMS B2 | 1-s RMS B2, fix-weighted | per-fix RMS B2 |\n|---|---|---|---|---|---|---|")
    for r in REP["R"].itertuples():
        L.append(f"| {r.animal} | {r.set} | {_f(r.rms_1s_raw)} | {_f(r.rms_fix_raw)} | {_f(r.rms_1s_B2)} | {_f(r.rms_1s_w_B2)} | {_f(r.rms_fix_B2)} |")
    if not chk["all_rms_1s_le_fix"]:
        L.append("\nNote: the 1-s median cannot reduce B2's error much (B2 is already smooth at 1 s), so its 1-s and per-fix values differ "
                 "mainly by weighting: every second counts once on the 1-s grid, while the per-fix RMS weights a second by its number of "
                 "fixes, and seconds with few fixes (dropouts) carry larger errors. Weighted by fix count, the 1-s B2 value is below the "
                 "per-fix one; the raw 1-s value is below the per-fix one either way (the median removes jitter).")
    L.append("\n## Caveats\n")
    L.append("- Joint stillness is almost entirely inside the two houses, often in huddles: the common mode between distant tags and "
             "in the open field is barely sampled (see the coverage table), and C3's references are almost always house-mates.\n"
             "- The truth is each segment's own median raw fix: a common-mode offset constant over a segment is absorbed and invisible; "
             "overlap-centring additionally removes offsets constant over a pair overlap (the truth-centred sensitivity keeps them).\n"
             "- Rain is three weather episodes (two nights, one day); 10-min blocks within them are not independent weather samples.\n"
             "- anchors_list lists the anchors reported for a fix, a superset of those used; \"lost\" means not listed (certainly not "
             "used), so anchors listed but dropped by the solver are not seen.\n"
             "- Distances are in the unverified WISER inch frame (frame-invariant); nothing here says where the houses are physically.\n")
    L.append(DEFINITIONS)
    L.append(f"\n## Rerun\n\n```\npython {DRIVER} --cohort {cohort} --workers 6\npython {DRIVER} --report-only <run_dir>\npython {DRIVER} --selftest\n```\n")
    return "\n".join(L)


def publish(A: dict, cfg: dict, out: Path, fh=None) -> None:
    import shutil
    cohort = cfg["_cohort"]
    fdir = output_paths.figure_dir(cohort, DIRECTION)
    figs = make_figures(A, cfg, out, fdir, cohort)
    for f in figs.values():
        try:
            shutil.copy2(fdir / f, out / "figures" / f)
        except Exception:  # noqa: BLE001
            pass
    rdir = output_paths.report_dir(cohort, DIRECTION)
    rep = rdir / f"{STEM}_{cohort}.md"
    meta = {"cohort": cohort, "direction": DIRECTION, "analysis": NAME, "report": rep.name, "driver": DRIVER,
            "config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "plan": PLAN, "git_commit": C.git_commit(),
            "figures": sorted(figs.values()), "verdict": A["V"]["verdict"]}
    rep.write_text(render_report(A, cfg, out, figs, meta), encoding="utf-8")
    output_paths.write_run_manifest(out, out, **meta)
    mp = rdir / f"run_manifest_common_mode_{cohort}.json"
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **meta}, indent=2) + "\n", encoding="utf-8")
    log_to(fh, f"report {rep}\nmanifest {mp}")


# ====================================================================================================== selftest
def _synthetic(seed: int, share: float = 0.5, hours: float = 8.0, with_cm: bool = True, excursion: bool = False) -> dict:
    """Four still tags: A, B, C in house_1 carry a shared OU common mode (tau 10 s) of variance share `share` plus white
    independent noise; D in house_2 has independent noise only. All processes are constant within each clock second
    [k - 0.5, k + 0.5) so the 1-s medians are exact. Fixes at ~4 Hz. Optional: a planted 30-s, 20-in common excursion."""
    rng = np.random.default_rng(seed)
    lo = 1_788_000_000_000
    nsec = int(hours * 3600)
    s_tot = 3.0
    s_m = math.sqrt(share) * s_tot if with_cm else 0.0
    s_n = math.sqrt(1 - share) * s_tot if with_cm else s_tot
    tau = 10.0
    a = math.exp(-1.0 / tau)
    m = np.zeros((nsec, 2))
    m[0] = rng.normal(0, s_m, 2)
    for k in range(1, nsec):
        m[k] = a * m[k - 1] + rng.normal(0, s_m * math.sqrt(1 - a * a), 2)
    if excursion:
        m[1800:1830, 0] += 20.0
    truths = {"A": (100.0, 100.0), "B": (130.0, 100.0), "C": (100.0, 160.0), "D": (400.0, 100.0)}
    zones = {"A": "house_1", "B": "house_1", "C": "house_1", "D": "house_2"}
    cm = {"A": True, "B": True, "C": True, "D": False}
    seg_len = 3600 if hours >= 1 else nsec
    tracks, segrows = {}, []
    for tg, c in truths.items():
        noise = rng.normal(0, s_n if cm[tg] else s_tot, (nsec, 2))
        val = np.array(c) + noise + (m if cm[tg] else 0.0)
        t = np.arange(0.0, nsec - 1.0, 0.25) + rng.uniform(-0.05, 0.05, int(4 * (nsec - 1)))
        t = np.sort(t[(t > 0.2) & (t < nsec - 1.2)])
        k = np.floor(t + 0.5).astype(int)
        z = val[k]
        tracks[tg] = {"t": t, "raw": z, "B2": z.copy(), "a": np.full(len(t), 9.0), "bits": np.full(len(t), 0b111, np.int64)}
        for s0 in range(0, nsec - 60, seg_len):
            s1 = min(s0 + seg_len, nsec - 2)
            ts, te = s0 + 1.0 + 0.3, s1 - 1.0 + 0.3
            sel = (t >= ts) & (t < te)
            tr = np.median(z[sel], axis=0)
            segrows.append({"seg_id": f"{tg}|syn|{s0:06d}", "animal": tg, "period": "syn", "set": "calm", "kind": "day",
                            "ts_ms": lo + ts * 1000, "te_ms": lo + te * 1000, "truth_x": tr[0], "truth_y": tr[1], "n_fix": int(sel.sum()),
                            "zd": zones[tg], "zone2": "house", "dur_trim_s": te - ts, "lo_ms": lo})
    S = pd.DataFrame(segrows)
    S["mid_ms"] = 0.5 * (S.ts_ms + S.te_ms)
    S["blk"] = ((S.mid_ms - S.lo_ms) // 600_000).astype(np.int64)
    return {"lo": lo, "tracks": tracks, "S": S, "s_m": s_m, "s_n": s_n, "s_tot": s_tot}


def _syn_cfg() -> dict:
    return {"tz": "America/New_York", "methods": ["raw", "B2"], "grid": {"half_1s": 0.5, "min_fix_1s": 2, "half_10s": 5.0, "min_fix_10s": 10},
            "overlap_min_s": 30.0, "lags_s": [-1, 0, 1], "same_zone_pairings": ["same_house", "both_outside"], "distance_bands_in": [14.0, 48.0],
            "abs_err_hist": {"max_in": 100.0, "step_in": 0.05}, "anchors": {"ref_share": 0.5, "lost_share": 0.5, "low_used_lt": 8.0},
            "shared_excursion": {"method": "raw", "scale": "10s", "min_in": 12.0, "merge_gap_s": 1.0, "top_n": 20},
            "c3": {"methods": ["raw", "B2"], "variants": ["z", "a"], "roll_half_s": 5.0, "roll_min_n": 5, "crazy_in": 12.0, "crazy_min_s": 10},
            "bootstrap": {"block_s": 600, "n_boot": 200, "seed": 7},
            "verdict": {"corr_min": 0.3, "rel_change_max": -0.10, "method": "B2", "raw_method": "raw", "corr_scale": "10s",
                        "corr_pairing": "same_zone", "c3_variant": "z", "c3_metrics": ["drift10_p90", "rms_1s"]},
            "_audit": {"periods": {"syn": {"set": "calm", "kind": "day", "start": "2026-08-29 10:00:00"}}}}


def _syn_seconds(syn: dict, cfg: dict) -> pd.DataFrame:
    parts = []
    for tg, tr in syn["tracks"].items():
        sg = syn["S"][syn["S"].animal == tg].copy()
        sg["ts"] = (sg.ts_ms - syn["lo"]) / 1000.0
        sg["te"] = (sg.te_ms - syn["lo"]) / 1000.0
        sec, _ = seconds_for_tag(tr["t"], {"raw": tr["raw"], "B2": tr["B2"]}, tr["a"], tr["bits"], sg, ["raw", "B2"], 3, cfg["grid"], cfg["anchors"])
        sec.insert(0, "period", "syn")
        sec.insert(0, "animal", tg)
        sec["g_ms"] = syn["lo"] + sec.pop("g") * 1000
        parts.append(sec)
    return pd.concat(parts, ignore_index=True)


def selftest() -> int:
    ok_all = True
    t_start = time.time()

    def check(name, cond, info=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}", flush=True)

    global period_lo
    _orig_lo = period_lo
    cfg = _syn_cfg()
    syn = _synthetic(11, share=0.5, hours=8.0)
    period_lo = lambda c, p: syn["lo"]  # noqa: E731  (synthetic period start)
    try:
        # ---- zone stratifier and overlap rule
        check("zone pairing: planted cases", zone_pairing("house_1", "house_1") == "same_house" and zone_pairing("house_1", "house_2") == "diff_house"
              and zone_pairing("house_2", "outside") == "house_outside" and zone_pairing("outside", "outside") == "both_outside")
        A_ = np.array([[1000.0, 99000.0]])
        B_ = np.array([[76000.0, 199000.0], [61000.0, 199000.0]])
        ia, ib, s_, e_ = overlap_spans(A_, B_, 30.0)
        check("overlap rule: a 23-s intersection is dropped, a 38-s one kept", list(ib) == [1] and abs((e_[0] - s_[0]) / 1000 - 38.0) < 1e-9,
              f"kept {list(ib)}, {((e_ - s_) / 1000).round(1).tolist()} s")
        # ---- seconds, pairs
        SEC = _syn_seconds(syn, cfg)
        S = syn["S"]
        r1 = np.hypot(SEC.e1x_raw, SEC.e1y_raw)
        check("1-s residuals exist on the integer-second grid of every segment", len(SEC) > 0.95 * 4 * (8 * 3600 - 8 * 3) and np.isfinite(r1).mean() > 0.99,
              f"{len(SEC)} s, finite {np.isfinite(r1).mean():.3f}")
        OV, PS = build_pairs(SEC, S, cfg)
        check("pairs: 6 tag pairs x 8 segment overlaps; zone pairings 3 same house + 3 different houses",
              len(OV) == 48 and (OV.zp == "same_house").sum() == 24 and (OV.zp == "diff_house").sum() == 24, f"{len(OV)} overlaps")
        # ---- C1 share
        R1 = c1_compute(PS, OV, cfg, ["raw", "B2"], 3, [1, 2, 3])
        C1 = R1["C1"]
        rs = _row(C1, zpg="same_house", set="all", kind="all", method="raw", scale="1s", lag_s=0, center="overlap")
        rd = _row(C1, zpg="diff_house", set="all", kind="all", method="raw", scale="1s", lag_s=0, center="overlap")
        check("C1: 1-s vector correlation of the shared-term pairs recovers the planted share 0.50 (+-0.05)", abs(rs.rho_v - 0.5) < 0.05,
              f"{rs.rho_v:.3f} [{rs.rho_v_lo:.3f}, {rs.rho_v_hi:.3f}]")
        check("C1: pairs with the independent tag D are uncorrelated (|rho_v| < 0.05)", abs(rd.rho_v) < 0.05, f"{rd.rho_v:.3f}")
        r10 = _row(C1, zpg="same_house", set="all", kind="all", method="raw", scale="10s", lag_s=0, center="overlap")
        check("C1: at 10 s the white independent noise averages out -> share higher than at 1 s", r10.rho_v > rs.rho_v + 0.2, f"10-s {r10.rho_v:.3f}")
        rl = _row(C1, zpg="same_house", set="all", kind="all", method="raw", scale="1s", lag_s=1, center="overlap")
        exp_l = 0.5 * math.exp(-1.0 / 10.0)
        check("C1: lag-1 s correlation follows the OU decay (0.5 e^-0.1 = 0.452, +-0.05)", abs(rl.rho_v - exp_l) < 0.05, f"{rl.rho_v:.3f}")
        # ---- C2 R
        C2 = c2_compute(PS, OV, cfg, ["raw", "B2"])
        q_ab = _row(C2, zpg="same_house", set="all", kind="all", band="all", method="raw", scale="1s")
        q_d = _row(C2, zpg="diff_house", set="all", kind="all", band="all", method="raw", scale="1s")
        check("C2: R of the shared-term pairs = sqrt(1/2) = 0.707 (+-0.05)", abs(q_ab.R - math.sqrt(0.5)) < 0.05, f"{q_ab.R:.3f}")
        check("C2: R with the independent tag = 1 (+-0.05)", abs(q_d.R - 1.0) < 0.05, f"{q_d.R:.3f}")
        exp_sd = math.sqrt(2 * syn["s_n"] ** 2)
        check("C2: SD of the distance error of shared-term pairs = sqrt(2) s_n (+-5 %)", abs(q_ab.sd_err / exp_sd - 1) < 0.05, f"{q_ab.sd_err:.3f} vs {exp_sd:.3f}")
        # ---- C3
        C3S, _ = c3_compute(SEC, S, cfg)

        def ratio(tg, var, m="raw"):
            d = C3S[(C3S.animal == tg) & (C3S.variant == var) & (C3S.method == m)]
            with np.errstate(invalid="ignore", divide="ignore"):
                return math.sqrt(d.ss_v.sum() / d.ss_u.sum()) if d.ss_u.sum() > 0 and d.n_cov.sum() > 0 else np.nan, d.n_cov.sum() / d.n_sec.sum()
        rz, cz = ratio("A", "z")
        ra, ca = ratio("A", "a")
        rdz, cdz = ratio("D", "z")
        rda, cda = ratio("D", "a")
        check("C3 variant z: shared-term tag A error x sqrt(0.75) = 0.866 (+-0.03), coverage 1", abs(rz - math.sqrt(0.75)) < 0.03 and cz > 0.99,
              f"{rz:.3f}, coverage {cz:.3f}")
        # variant a, target A, refs B, C, D: v = m/3 + n_A - (n_B + n_C)/3 - n_D/3 -> var (0.5/9 + 0.5 + 1/9 + 1/9) = 7/9 of 1
        check("C3 variant a: tag A error x sqrt(7/9) = 0.882 (+-0.03)", abs(ra - math.sqrt(7 / 9)) < 0.03, f"{ra:.3f}")
        # variant a, target D, refs A, B, C: v = n_D - m - (n_A + n_B + n_C)/3 -> var 1 + 0.5 + 0.5/3 = 5/3
        check("C3: the independent tag D is not improved (variant a ratio sqrt(5/3) = 1.29 +-0.05; variant z has no reference)",
              abs(rda - math.sqrt(5 / 3)) < 0.05 and cdz == 0, f"a {rda:.3f}, z coverage {cdz:.3f}")
        dA = C3S[(C3S.animal.isin(["A", "B", "C"])) & (C3S.variant == "z") & (C3S.method == "raw")]
        check("C3 variant z: 10-s drift of the shared-term tags decreases (OU common mode removed)",
              np.nanmedian(dA.drift_v) < np.nanmedian(dA.drift_u), f"median {np.nanmedian(dA.drift_u):.2f} -> {np.nanmedian(dA.drift_v):.2f} in")
        S3 = c3_summary(C3S, cfg)
        V = verdict(C1, S3, cfg["verdict"])
        check("verdict on the synthetic common mode = material", V["verdict"] == "material", f"{V['verdict']}")
        # ---- no common mode -> not material
        syn0 = _synthetic(12, share=0.5, hours=3.0, with_cm=False)
        period_lo = lambda c, p: syn0["lo"]  # noqa: E731
        SEC0 = _syn_seconds(syn0, cfg)
        OV0, PS0 = build_pairs(SEC0, syn0["S"], cfg)
        R10 = c1_compute(PS0, OV0, cfg, ["raw", "B2"], 3, [1, 2, 3])
        C3S0, _ = c3_compute(SEC0, syn0["S"], cfg)
        V0 = verdict(R10["C1"], c3_summary(C3S0, cfg), cfg["verdict"])
        r0 = _row(R10["C1"], zpg="same_house", set="all", kind="all", method="raw", scale="10s", lag_s=0, center="overlap")
        check("no common mode: same-house 10-s correlation ~ 0 and verdict = not material", abs(r0.rho_v) < 0.1 and V0["verdict"] == "not material",
              f"rho_v {r0.rho_v:.3f}, {V0['verdict']}")
        # ---- shared excursion detection (a planted 30-s 20-in common excursion)
        syn2 = _synthetic(13, share=0.3, hours=1.0, excursion=True)
        period_lo = lambda c, p: syn2["lo"]  # noqa: E731
        SEC2 = _syn_seconds(syn2, cfg)
        OV2, PS2 = build_pairs(SEC2, syn2["S"], cfg)
        SX = shared_excursions(PS2, OV2, cfg, [1, 2, 3], cfg["tz"])
        CL = SX["CL"]
        top = CL.iloc[0] if len(CL) else None
        t_ex = syn2["lo"] + 1800 * 1000
        check("shared excursion: the planted 20-in excursion of A, B, C is the top cluster, at the planted time, D not in it",
              top is not None and top.tags == "A,B,C" and abs(top.s_ms - t_ex) < 15_000 and top.size_in > 12,
              f"{(top.tags, round((top.s_ms - t_ex) / 1000), round(top.size_in, 1)) if top is not None else None}")
        # ---- anchor-loss categories
        Li = np.array([0, 1, 0, 2, 3])
        Lj = np.array([0, 0, 4, 1, 1])
        shared = (Li & Lj) != 0
        cat = np.where(shared, 3, np.where((Li == 0) & (Lj == 0), 0, np.where((Li == 0) ^ (Lj == 0), 1, 2)))
        check("anchor-loss categories on planted masks", list(cat) == [0, 1, 1, 2, 3], f"{list(cat)}")
        bits = parse_bits(pd.Series([",1,2,", ",5,", "", ",2,5,"]), {1: 0, 2: 1, 5: 2})
        check("anchors_list parsing to bitmasks", list(bits) == [3, 4, 0, 6], f"{list(bits)}")
    finally:
        period_lo = _orig_lo
    print(f"selftest {time.time() - t_start:.1f} s -> {'ALL PASS' if ok_all else 'FAILED'}", flush=True)
    return 0 if ok_all else 1


# ====================================================================================================== main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--config", default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--report-only", default=None, help="existing run dir: re-aggregate and re-render from its saved seconds table")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    cfg = load_cfg(a.cohort, a.config)
    out = Path(a.report_only) if a.report_only else run_compute(cfg, a.workers or int(cfg.get("workers", 6)))
    fh = open(out / "log_report.txt", "a", encoding="utf-8")
    A = analyze(out, cfg, fh)
    publish(A, cfg, out, fh)
    fh.close()


if __name__ == "__main__":
    main()
