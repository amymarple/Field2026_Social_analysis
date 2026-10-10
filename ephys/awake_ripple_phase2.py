r"""Awake-ripple map, Phase 2 (plan implementation_plan/2026-10-10-awake-ripple-map.md, Amendment 6, fixed before any map):
where in the paddock do the rats make awake ripples at night, per animal.

Usage:  python ephys/awake_ripple_map.py phase2 [--perms 1000] [--sens-perms 500]
        python ephys/awake_ripple_phase2.py --selftest

Input: the Phase 0 per-second tables `<run>/seconds_<SF>.csv.gz` (awake_ripple_map.py phase0): non-locomotor detectable
wake seconds (`nonloco`) with their V3 position, house membership zone, probe block, night, record, and the awake
ripples in them (`aswr` = production kept events in WAKE).

Places: 48-in field bins on the WISER frame anchored at the P0 position of pole A0 (no cropping); house_1 / house_2 =
the membership zones; unknown zone left out. Rings: house = 0; field distance to the nearest house rest-cluster centre in
0-24, 24-48, 48-96, 96-144, 144-192, > 192 in.
Bout: a maximal run of consecutive non-locomotor seconds within a record.
Null: within night x block x duration class (ratio 1.25) x clock hour, the bouts' event sequences are permuted, offsets
rescaled to the recipient's length.
Statistics: T1 Skaggs spatial information of the field map (bins >= 60 s, within block, occupancy-weighted over blocks);
T2 leave-one-night-out r; T3 house vs field Mantel-Haenszel rate ratio; 1-D ring O / E and its log-log slope; Holm over
the animals in inference; a bout-level Poisson GLM (description).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

COHORT = "2026c"
GRID_IN = 48.0
MIN_OCC_S = 60
HOUSES = {1: (417.7, 716.9), 2: (621.2, 732.6)}
RING_EDGES = [24.0, 48.0, 96.0, 144.0, 192.0]
RING_LABELS = ["house", "0-24", "24-48", "48-96", "96-144", "144-192", ">192"]
SCREEN = dict(field_events=300, field_bins=10)
ANIMALS = ["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"]
NOTES = {"SF09": "field not validated (EMG-ICA could not clean its shank; raw reading 1 / 3 / 4)",
         "SF08": "strict field reading 4 / 8",
         "SF11": "houses only (0.01 h of field time)",
         "SF07": "field descriptive (35 field events)"}
RAIN_NIGHTS = {"09-03", "09-09"}
SF08_SETTLE = pd.Timestamp("2026-09-06 19:43")
EPOCH = pd.Timestamp("1970-01-01")
COLS = ["sec", "night", "rec", "zone", "x", "y", "anchors", "qc_i1", "blk", "ble_pass", "nonloco", "aswr", "trial"]


# ------------------------------------------------------------------ preparation
def prepare(S: pd.DataFrame, origin: np.ndarray) -> dict:
    """Non-locomotor seconds -> arrays: place, ring, distance, bout, offset, events, block, night; plus the bout table."""
    S = S[S.nonloco & S.zone.isin([1, 2, 3])].sort_values(["rec", "sec"]).reset_index(drop=True)
    n = len(S)
    field = S.zone.to_numpy() == 3
    gx = np.floor((S.x.to_numpy() - origin[0]) / GRID_IN).astype(int)
    gy = np.floor((S.y.to_numpy() - origin[1]) / GRID_IN).astype(int)
    d = np.min(np.stack([np.hypot(S.x - hx, S.y - hy) for hx, hy in HOUSES.values()]), axis=0)
    OFF, BASE = 500, 1000                                               # cells may sit left of / below pole A0 (no cropping)
    key = np.where(field, 10_000_000 + (gy + OFF) * BASE + (gx + OFF), S.zone.to_numpy())   # houses keep codes 1 / 2
    uk, place = np.unique(key, return_inverse=True)
    pinfo = pd.DataFrame({"key": uk})
    pinfo["kind"] = np.where(pinfo.key == 1, "house_1", np.where(pinfo.key == 2, "house_2", "field"))
    fk = pinfo.key.to_numpy() - 10_000_000
    pinfo["gx"] = np.where(pinfo.kind == "field", np.mod(fk, BASE) - OFF, -9999)
    pinfo["gy"] = np.where(pinfo.kind == "field", fk // BASE - OFF, -9999)
    ring = np.where(field, np.digitize(d, RING_EDGES) + 1, 0)
    rec, sec = S.rec.to_numpy(), S.sec.to_numpy()
    new = np.r_[True, (rec[1:] != rec[:-1]) | (np.diff(sec) != 1)]
    bout = np.cumsum(new) - 1
    start = np.flatnonzero(new)
    L = np.diff(np.r_[start, n])
    off = np.arange(n) - start[bout]
    blk_u, blk = np.unique(S.blk.to_numpy(), return_inverse=True)
    nt_u, night = np.unique(S.night.astype(str).to_numpy(), return_inverse=True)
    hour = pd.to_datetime(sec[start], unit="s").hour.to_numpy()
    dcls = np.floor(np.log(L) / np.log(1.25)).astype(int)
    strat = pd.factorize(pd.Series(list(zip(night[start], blk[start], dcls, hour))))[0]
    groups = [g for g in pd.Series(np.arange(len(start))).groupby(strat).apply(lambda v: v.to_numpy()) if len(g) >= 2]
    e = S.aswr.to_numpy().astype(np.int64)
    ev = np.flatnonzero(e > 0)
    # odd / even trials (Amendment 1's secondary stability split): trials ranked by start time
    tr = S.trial.to_numpy() if "trial" in S else np.zeros(n, int)
    tr_rank = pd.Series(tr).map(pd.Series(np.arange(len(np.unique(tr))), index=np.unique(tr))).to_numpy()
    half = (tr_rank % 2).astype(np.int64)
    return dict(S=S, n=n, place=place, pinfo=pinfo, ring=ring, dist=d, field=field, bout=bout, start=start, L=L, off=off,
                blk=blk, blk_u=blk_u, night=night, night_u=nt_u, hour_start=hour, groups=groups, e=e, half=half,
                ev_bout=bout[ev], ev_off=off[ev], ev_cnt=e[ev], swappable=float(sum(len(g) for g in groups) / max(len(start), 1)))


def permuted_events(P: dict, rng: np.random.Generator) -> np.ndarray:
    """One bout-swap draw: per-second event counts after permuting event sequences within strata."""
    rec = np.arange(len(P["start"]))
    for g in P["groups"]:
        rec[g] = rng.permutation(g)                                     # bout g[k]'s sequence goes to bout rec[g[k]]
    r = rec[P["ev_bout"]]
    no = np.minimum(np.floor(P["ev_off"] * P["L"][r] / P["L"][P["ev_bout"]]).astype(np.int64), P["L"][r] - 1)
    rows = P["start"][r] + no
    return np.bincount(rows, weights=P["ev_cnt"], minlength=P["n"])


# ------------------------------------------------------------------ statistics
def spatial_info(c: np.ndarray, o: np.ndarray) -> float:
    m = o >= MIN_OCC_S
    if m.sum() < 2 or c[m].sum() <= 0:
        return np.nan
    c, o = c[m], o[m]
    lb = c.sum() / o.sum()
    r = (c / o) / lb
    p = o / o.sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(r > 0, p * r * np.log2(np.where(r > 0, r, 1)), 0.0)
    return float(t.sum())


def stats(P: dict, e: np.ndarray) -> dict:
    nb, npl, nn = len(P["blk_u"]), len(P["pinfo"]), len(P["night_u"])
    fieldp = (P["pinfo"].kind == "field").to_numpy()
    housep = ~fieldp
    occ = P.get("_occ")
    if occ is None:
        occ = np.bincount(P["blk"] * npl + P["place"], minlength=nb * npl).reshape(nb, npl).astype(float)
        P["_occ"] = occ
        P["_occ_n"] = np.bincount(P["night"] * npl + P["place"], minlength=nn * npl).reshape(nn, npl).astype(float)
        P["_occ_r"] = np.bincount(P["blk"] * 7 + P["ring"], minlength=nb * 7).reshape(nb, 7).astype(float)
        dsum = np.bincount(P["ring"], weights=np.where(P["field"], P["dist"], 0), minlength=7)
        P["_dring"] = dsum / np.maximum(np.bincount(P["ring"], minlength=7), 1)
    occ_n, occ_r = P["_occ_n"], P["_occ_r"]
    c = np.bincount(P["blk"] * npl + P["place"], weights=e, minlength=nb * npl).reshape(nb, npl)
    cn = np.bincount(P["night"] * npl + P["place"], weights=e, minlength=nn * npl).reshape(nn, npl)
    cr = np.bincount(P["blk"] * 7 + P["ring"], weights=e, minlength=nb * 7).reshape(nb, 7)
    # T1
    si, w = [], []
    for b in range(nb):
        v = spatial_info(c[b, fieldp], occ[b, fieldp])
        if np.isfinite(v):
            si.append(v)
            w.append(occ[b, fieldp][occ[b, fieldp] >= MIN_OCC_S].sum())
    T1 = float(np.average(si, weights=w)) if si else np.nan
    # T2 leave-one-night-out
    rs, ws = [], []
    tot_c, tot_o = cn[:, fieldp].sum(0), occ_n[:, fieldp].sum(0)
    for k in range(nn):
        on, ok = occ_n[k, fieldp], tot_o - occ_n[k, fieldp]
        m = (on >= MIN_OCC_S) & (ok >= MIN_OCC_S)
        if m.sum() >= 3:
            a_ = cn[k, fieldp][m] / on[m]
            b_ = (tot_c - cn[k, fieldp])[m] / ok[m]
            if a_.std() > 0 and b_.std() > 0:
                rs.append(np.corrcoef(a_, b_)[0, 1])
                ws.append(m.sum())
    T2 = float(np.average(rs, weights=ws)) if rs else np.nan
    # T2b odd vs even trials
    if "_occ_h" not in P:
        P["_occ_h"] = np.bincount(P["half"] * npl + P["place"], minlength=2 * npl).reshape(2, npl).astype(float)
    oh2 = P["_occ_h"][:, fieldp]
    ch2 = np.bincount(P["half"] * npl + P["place"], weights=e, minlength=2 * npl).reshape(2, npl)[:, fieldp]
    m = (oh2[0] >= MIN_OCC_S) & (oh2[1] >= MIN_OCC_S)
    T2b = np.nan
    if m.sum() >= 3:
        a_, b_ = ch2[0][m] / oh2[0][m], ch2[1][m] / oh2[1][m]
        if a_.std() > 0 and b_.std() > 0:
            T2b = float(np.corrcoef(a_, b_)[0, 1])
    # T3 house vs field, Mantel-Haenszel over blocks
    ch, oh = c[:, housep].sum(1), occ[:, housep].sum(1)
    cf, of = c[:, fieldp].sum(1), occ[:, fieldp].sum(1)
    ot = oh + of
    num = np.sum(np.where(ot > 0, ch * of / np.where(ot > 0, ot, 1), 0))
    den = np.sum(np.where(ot > 0, cf * oh / np.where(ot > 0, ot, 1), 0))
    T3 = float(np.log(num / den)) if num > 0 and den > 0 else np.nan
    # rings: O / E against the block's field rate
    lf = np.where(of > 0, cf / np.where(of > 0, of, 1), np.nan)
    E = np.nansum(occ_r * lf[:, None], axis=0)
    O = cr.sum(0)
    oe = np.where(E > 0, O / np.where(E > 0, E, 1), np.nan)
    occ_ring = occ_r.sum(0)
    k = np.arange(1, 7)
    k = k[(occ_ring[k] >= MIN_OCC_S) & (E[k] > 0)]
    slope = np.nan
    if len(k) >= 3:
        x, y, wt = np.log(P["_dring"][k]), np.log((O[k] + 0.5) / E[k]), occ_ring[k] / 60
        X = np.column_stack([np.ones(len(k)), x])
        Wm = np.diag(wt)
        beta = np.linalg.solve(X.T @ Wm @ X, X.T @ Wm @ y)
        slope = float(beta[1])
    return dict(T1=T1, T2=T2, T2b=T2b, T3=T3, slope=slope, oe=oe, O=O, E=E)


def null_test(P: dict, n_perm: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    obs = stats(P, P["e"].astype(float))
    keys = ["T1", "T2", "T2b", "T3", "slope"]
    nul = {k: np.full(n_perm, np.nan) for k in keys}
    oe_null = np.full((n_perm, 7), np.nan)
    for i in range(n_perm):
        s = stats(P, permuted_events(P, rng))
        for k in keys:
            nul[k][i] = s[k]
        oe_null[i] = s["oe"]
    out = dict(obs=obs, null=nul, oe_null=oe_null)
    for k in keys:
        v = nul[k][np.isfinite(nul[k])]
        o = obs[k]
        if not np.isfinite(o) or not len(v):
            out[f"p_{k}"] = np.nan
            out[f"med_{k}"] = np.nan
            continue
        out[f"med_{k}"] = float(np.median(v))
        hi, lo = (1 + np.sum(v >= o)) / (len(v) + 1), (1 + np.sum(v <= o)) / (len(v) + 1)
        out[f"p_{k}"] = float(hi) if k in ("T1", "T2", "T2b") else float(min(1.0, 2 * min(hi, lo)))
    return out


def holm(p: pd.Series) -> pd.Series:
    q = p.dropna().sort_values()
    m = len(q)
    adj = pd.Series(np.minimum(1, np.maximum.accumulate([(m - i) * v for i, v in enumerate(q.to_numpy())])), index=q.index)
    return adj.reindex(p.index)


def bout_glm(P: dict) -> dict:
    """events ~ house + log bout length + clock harmonics + night (+ block), offset log piece length; cluster SE by night."""
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    house = ~P["field"]
    piece_new = np.r_[True, (P["bout"][1:] != P["bout"][:-1]) | (house[1:] != house[:-1])]
    pid = np.cumsum(piece_new) - 1
    sec = P["S"].sec.to_numpy()
    D = pd.DataFrame({"pid": pid, "events": P["e"], "house": house.astype(int), "bout": P["bout"], "night": P["night"],
                      "blk": P["blk"], "dist": np.where(P["field"], P["dist"], np.nan), "sec": sec})
    G = D.groupby("pid").agg(events=("events", "sum"), length=("events", "size"), house=("house", "first"), bout=("bout", "first"),
                             night=("night", "first"), blk=("blk", "first"), dist=("dist", "mean"), sec=("sec", "first"))
    G["bout_len"] = P["L"][G.bout.to_numpy()]
    h = (pd.to_datetime(G.sec, unit="s").dt.hour + pd.to_datetime(G.sec, unit="s").dt.minute / 60).to_numpy()
    G["s1"], G["c1"] = np.sin(2 * np.pi * h / 24), np.cos(2 * np.pi * h / 24)
    G["lbl"] = np.log(G.bout_len)
    terms = "lbl + s1 + c1" + (" + C(night)" if G.night.nunique() > 1 else "") + (" + C(blk)" if G.blk.nunique() > 1 else "")
    out = {}
    try:
        if G.house.nunique() > 1 and G.events[G.house == 1].sum() >= 20 and G.events[G.house == 0].sum() >= 20:
            m = smf.glm(f"events ~ house + {terms}", data=G, family=sm.families.Poisson(), offset=np.log(G.length)).fit(
                cov_type="cluster", cov_kwds={"groups": G.night.to_numpy()})
            b, se = m.params["house"], m.bse["house"]
            out.update(irr_house=float(np.exp(b)), irr_house_lo=float(np.exp(b - 1.96 * se)), irr_house_hi=float(np.exp(b + 1.96 * se)))
        F = G[(G.house == 0) & G.dist.notna() & (G.dist > 0)].copy()
        if len(F) > 20 and F.events.sum() > 20:
            F["ld"] = np.log(F.dist)
            m2 = smf.glm(f"events ~ ld + {terms}", data=F, family=sm.families.Poisson(), offset=np.log(F.length)).fit(
                cov_type="cluster", cov_kwds={"groups": F.night.to_numpy()})
            b, se = m2.params["ld"], m2.bse["ld"]
            out.update(field_logdist_coef=float(b), field_logdist_lo=float(b - 1.96 * se), field_logdist_hi=float(b + 1.96 * se))
    except Exception as ex:                                             # report, do not stop the run
        out["glm_error"] = str(ex)[:200]
    out["pieces"] = int(len(G))
    return out


# ------------------------------------------------------------------ run
def load_animal(run: Path, an: str) -> pd.DataFrame:
    S = pd.read_csv(run / f"seconds_{an}.csv.gz", usecols=COLS)
    S["nonloco"] = S.nonloco.astype(bool)
    return S


SENSITIVITIES = {
    "primary": lambda S, an: S,
    "no_qc_i1": lambda S, an: S[~S.qc_i1.astype(bool)],
    "anchors_gt6": lambda S, an: S[S.anchors > 6],
    "no_ble_pass": lambda S, an: S[~S.ble_pass.astype(bool)],
    "no_rain_nights": lambda S, an: S[~S.night.astype(str).isin(RAIN_NIGHTS)],
    "sf08_settled": lambda S, an: S[pd.to_datetime(S.sec, unit="s") >= SF08_SETTLE] if an == "SF08" else S,
}


def analyse(an: str, S: pd.DataFrame, origin: np.ndarray, n_perm: int, seed: int) -> tuple[dict, dict]:
    P = prepare(S, origin)
    fe = int(P["e"][P["field"]].sum())
    occ_f = pd.Series(np.bincount(P["place"][P["field"]], minlength=len(P["pinfo"])))
    fb = int((occ_f[(P["pinfo"].kind == "field").to_numpy()] >= MIN_OCC_S).sum())
    row = dict(animal=an, field_events=fe, house_events=int(P["e"][~P["field"]].sum()),
               field_h=float(P["field"].sum() / 3600), house_h=float((~P["field"]).sum() / 3600), field_bins_60s=fb,
               bouts=len(P["start"]), swappable_share=P["swappable"], blocks=len(P["blk_u"]), nights=len(P["night_u"]),
               enters_inference=bool(fe >= SCREEN["field_events"] and fb >= SCREEN["field_bins"]), note=NOTES.get(an, ""))
    R = null_test(P, n_perm, seed)
    for k in ["T1", "T2", "T2b", "T3", "slope"]:
        row[k] = R["obs"][k]
        row[f"null_med_{k}"] = R[f"med_{k}"]
        row[f"p_{k}"] = R[f"p_{k}"]
    row["house_field_rr"] = float(np.exp(row["T3"])) if np.isfinite(row["T3"]) else np.nan
    return row, dict(P=P, R=R)


def run(a) -> None:
    from awake_ripple_map import p0_params, to_wiser
    from _common import git_commit, report_dir, write_json
    t0 = time.time()
    man = json.loads((report_dir(COHORT) / f"run_manifest_awake_ripple_map_{COHORT}.json").read_text())
    run_dir = Path(a.run or man["run_dir"])
    out = run_dir / "phase2"
    out.mkdir(exist_ok=True)
    p = p0_params()
    origin = to_wiser(np.array([[0.0, 0.0]]), p)[0]
    rows, keep, places, rings, glms = [], {}, [], [], []
    for i, an in enumerate(ANIMALS):
        S = load_animal(run_dir, an)
        row, k = analyse(an, S, origin, a.perms, 1000 + i)
        rows.append(row)
        keep[an] = k
        P, R = k["P"], k["R"]
        pi = P["pinfo"].copy()
        for b in range(len(P["blk_u"])):
            m = P["blk"] == b
            o = np.bincount(P["place"][m], minlength=len(pi))
            c = np.bincount(P["place"][m], weights=P["e"][m], minlength=len(pi))
            places.append(pi.assign(animal=an, block=int(P["blk_u"][b]), occ_s=o, events=c))
        q = R["oe_null"]
        rings.append(pd.DataFrame({"animal": an, "ring": RING_LABELS, "dist_mean_in": P["_dring"], "occ_min": P["_occ_r"].sum(0) / 60,
                                   "O": R["obs"]["O"], "E": R["obs"]["E"], "oe": R["obs"]["oe"],
                                   "null_lo": np.nanpercentile(q, 2.5, axis=0), "null_hi": np.nanpercentile(q, 97.5, axis=0)}))
        g = bout_glm(P)
        g["animal"] = an
        glms.append(g)
        np.savez_compressed(out / f"null_{an}.npz", **{k_: v for k_, v in R["null"].items()}, oe_null=q)
        print(f"{an}: field {row['field_events']} ev / {row['field_h']:.2f} h, bins {row['field_bins_60s']}, T1 {row['T1']:.3f} "
              f"(null {row['null_med_T1']:.3f}, p {row['p_T1']:.3f}), T2 {row['T2']:.2f} (p {row['p_T2']:.3f}), "
              f"T2b {row['T2b']:.2f} (p {row['p_T2b']:.3f}), RR house/field {row['house_field_rr']:.2f} (p {row['p_T3']:.3f}), "
              f"slope {row['slope']:.2f} (p {row['p_slope']:.3f})")
    A = pd.DataFrame(rows)
    inf = A.enters_inference
    for k in ["T1", "T2", "T2b", "T3", "slope"]:
        A[f"p_{k}_holm"] = np.nan
        A.loc[inf, f"p_{k}_holm"] = holm(A.loc[inf, f"p_{k}"]).to_numpy()
    PL = pd.concat(places, ignore_index=True)
    RG = pd.concat(rings, ignore_index=True)
    GL = pd.DataFrame(glms)
    sens = []
    for name, f in SENSITIVITIES.items():
        if name == "primary":
            continue
        for i, an in enumerate(ANIMALS):
            if not A.loc[A.animal == an, "enters_inference"].iloc[0]:
                continue
            S = f(load_animal(run_dir, an), an)
            r_, _ = analyse(an, S, origin, a.sens_perms, 5000 + i)
            sens.append(dict(r_, sensitivity=name))
    SE = pd.DataFrame(sens)
    rd = report_dir(COHORT)
    A.to_csv(rd / f"ephys_spikes_awake_ripple_map_stats_{COHORT}.csv", index=False)
    RG.to_csv(rd / f"ephys_spikes_awake_ripple_map_rings_{COHORT}.csv", index=False)
    GL.to_csv(rd / f"ephys_spikes_awake_ripple_map_glm_{COHORT}.csv", index=False)
    SE.to_csv(rd / f"ephys_spikes_awake_ripple_map_sensitivity_{COHORT}.csv", index=False)
    PL.to_csv(out / "places.csv.gz", index=False)
    figs = figures(keep, A, RG, origin, p)
    report(A, RG, GL, SE, figs, run_dir, out, a)
    write_json(rd / f"run_manifest_awake_ripple_map_phase2_{COHORT}.json",
               dict(name="awake_ripple_map_phase2", run_dir=str(out), seconds_run=str(run_dir), git=git_commit(),
                    perms=a.perms, sens_perms=a.sens_perms, minutes=round((time.time() - t0) / 60, 1)))
    print(f"phase 2 done in {(time.time() - t0) / 60:.1f} min")


# ------------------------------------------------------------------ figures
def figures(keep: dict, A: pd.DataFrame, RG: pd.DataFrame, origin: np.ndarray, p: dict) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm, TwoSlopeNorm
    from _common import figure_dir
    fd = figure_dir(COHORT)
    lm = json.loads((HERE / "configs/paddock_landmarks_wiser_2026c.json").read_text(encoding="utf-8"))
    cor = np.array([lm["corners_wiser"][k] for k in ("A0", "A4", "C4", "C0", "A0")])
    poles = np.array(list(lm["poles_wiser"].values()))
    out = {}

    def grid(P, val_fn):
        pi = P["pinfo"]
        fp = pi[pi.kind == "field"]
        o = np.bincount(P["place"], minlength=len(pi)).astype(float)
        c = np.bincount(P["place"], weights=P["e"], minlength=len(pi))
        return pi, o, c

    def draw(ax, P, mode, norm, cmap):
        pi, o, c = grid(P, None)
        im = None
        for j, r in pi.iterrows():
            if r.kind != "field":
                continue
            x0, y0 = origin[0] + r.gx * GRID_IN, origin[1] + r.gy * GRID_IN
            if o[j] < MIN_OCC_S:
                ax.add_patch(plt.Rectangle((x0, y0), GRID_IN, GRID_IN, color="0.9", lw=0))
                continue
            v = o[j] / 60 if mode == "occ" else c[j] / (o[j] / 60)
            if mode == "rel":
                lf = c[(pi.kind == "field").to_numpy()].sum() / (o[(pi.kind == "field").to_numpy()].sum() / 60)
                v = np.log2(max(v, 1e-3) / lf) if lf > 0 else np.nan
            im = ax.add_patch(plt.Rectangle((x0, y0), GRID_IN, GRID_IN, color=cmap(norm(v)), lw=0))
        for j, r in pi.iterrows():
            if r.kind == "field" or o[j] < MIN_OCC_S:
                continue
            hx, hy = HOUSES[1 if r.kind == "house_1" else 2]
            v = o[j] / 60 if mode == "occ" else c[j] / (o[j] / 60)
            if mode == "rel":
                fm = (pi.kind == "field").to_numpy()
                lf = c[fm].sum() / (o[fm].sum() / 60) if o[fm].sum() > 0 else np.nan
                v = np.log2(max(v, 1e-3) / lf) if lf and lf > 0 else np.nan
            col = cmap(norm(v)) if np.isfinite(v) else "white"
            ax.add_patch(plt.Circle((hx, hy), 22, facecolor=col, edgecolor="k", lw=1.2))
        ax.plot(cor[:, 0], cor[:, 1], color="k", lw=0.8)
        ax.scatter(poles[:, 0], poles[:, 1], s=6, color="k", zorder=5)
        ax.set_aspect("equal")
        ax.set_xlim(cor[:, 0].min() - 60, cor[:, 0].max() + 60)
        ax.set_ylim(cor[:, 1].min() - 60, cor[:, 1].max() + 60)
        ax.set_xticks([])
        ax.set_yticks([])

    import matplotlib.cm as cm
    for an, k in keep.items():
        P = k["P"]
        fig, axs = plt.subplots(1, 2, figsize=(13, 4.2))
        pi, o, c = grid(P, None)
        occ_vals = o[o >= MIN_OCC_S] / 60
        rate_vals = (c / np.maximum(o / 60, 1e-9))[o >= MIN_OCC_S]
        n1 = LogNorm(vmin=max(occ_vals.min(), 1), vmax=max(occ_vals.max(), 2)) if len(occ_vals) else LogNorm(1, 2)
        n2 = plt.Normalize(vmin=0, vmax=np.nanpercentile(rate_vals, 98) if len(rate_vals) else 1)
        draw(axs[0], P, "occ", n1, cm.viridis)
        draw(axs[1], P, "rate", n2, cm.magma)
        fig.colorbar(cm.ScalarMappable(norm=n1, cmap=cm.viridis), ax=axs[0], fraction=0.03, label="non-locomotor wake (min)")
        fig.colorbar(cm.ScalarMappable(norm=n2, cmap=cm.magma), ax=axs[1], fraction=0.03, label="awake ripples / min")
        r = A[A.animal == an].iloc[0]
        axs[0].set_title("occupancy (48-in bins, houses as circles; grey < 60 s)", fontsize=9)
        axs[1].set_title("awake-ripple rate", fontsize=9)
        fig.suptitle(f"{an}: field {r.field_events} events / {r.field_h:.1f} h, houses {r.house_events} / {r.house_h:.1f} h"
                     + (f"  -  NOTE: {r.note}" if r.note else ""), fontsize=10, y=1.02)
        f = fd / f"ephys_spikes_awake_ripple_map_{an}_{COHORT}.png"
        fig.savefig(f, dpi=110, bbox_inches="tight")
        plt.close(fig)
        out[an] = f
    # summary: relative rate (log2 vs the animal's field mean) + the 1-D profile
    fig = plt.figure(figsize=(15, 6.6))
    gs = fig.add_gridspec(2, 3, hspace=0.35, wspace=0.08)
    nr = TwoSlopeNorm(vmin=-2, vcenter=0, vmax=2)
    for i, an in enumerate(ANIMALS):
        ax = fig.add_subplot(gs[i // 3, i % 3])
        draw(ax, keep[an]["P"], "rel", nr, cm.RdBu_r)
        r = A[A.animal == an].iloc[0]
        ax.set_title(f"{an}: field {r.field_events} ev / {r.field_h:.1f} h" + (f"\n{r.note}" if r.note else ""), fontsize=8.5)
    fig.colorbar(cm.ScalarMappable(norm=nr, cmap=cm.RdBu_r), ax=fig.axes[:6], fraction=0.015,
                 label="log2 rate / the animal's field rate")
    f = fd / f"ephys_spikes_awake_ripple_map_summary_{COHORT}.png"
    fig.savefig(f, dpi=110, bbox_inches="tight")
    plt.close(fig)
    out["summary"] = f
    # 1-D profile: one panel per animal, categorical rings, null 95 % band
    fig, axs = plt.subplots(2, 3, figsize=(14, 6.5), sharey=True)
    xs = np.arange(len(RING_LABELS))
    for ax, an in zip(axs.ravel(), ANIMALS):
        g = RG[RG.animal == an]
        r = A[A.animal == an].iloc[0]
        floor = 0.2
        oe = np.clip(g.oe.to_numpy(), floor, 20)
        ok = np.isfinite(g.oe.to_numpy()) & (g.occ_min.to_numpy() >= MIN_OCC_S / 60)
        lo, hi = np.clip(g.null_lo.to_numpy(), floor, 20), np.clip(g.null_hi.to_numpy(), floor, 20)
        ax.fill_between(xs[ok], lo[ok], hi[ok], color="0.85", label="bout-swap null 95 %")
        ax.plot(xs[ok], oe[ok], marker="o", color="tab:red", label="observed")
        ax.axhline(1, color="k", lw=0.8, ls=":")
        ax.set_yscale("log")
        ax.set_xticks(xs)
        ax.set_xticklabels([f"{l_}\n{m_:.0f} min" for l_, m_ in zip(RING_LABELS, g.occ_min.to_numpy())], fontsize=7)
        ax.set_title(f"{an}" + (f"\n{r.note}" if r.note else ""), fontsize=8.5)
    axs[0, 0].set_ylabel("O / E (block's field rate)")
    axs[1, 0].set_ylabel("O / E (block's field rate)")
    axs[0, 0].legend(fontsize=7, loc="upper right")
    fig.suptitle("Awake ripples vs distance to the nearest house (rings in inches, with minutes of non-locomotor wake)",
                 fontsize=10)
    fig.tight_layout()
    f = fd / f"ephys_spikes_awake_ripple_map_rings_{COHORT}.png"
    fig.savefig(f, dpi=110, bbox_inches="tight")
    plt.close(fig)
    out["rings"] = f
    return out


# ------------------------------------------------------------------ report
def reading(A: pd.DataFrame, SE: pd.DataFrame) -> list[str]:
    """Plain statements from the numbers: Holm-significant tests, their robustness over the sensitivities, directions."""
    L = []
    inf = A[A.enters_inference]
    L.append(f"- Animals in inference (>= {SCREEN['field_events']} field events and >= {SCREEN['field_bins']} field bins >= 60 s): "
             + ", ".join(inf.animal) + "; the others are descriptive.")
    for r in inf.itertuples():
        se = SE[SE.animal == r.animal] if len(SE) else pd.DataFrame()
        n_s = len(se)
        t1_rob = int((se.p_T1 < 0.05).sum()) if n_s else 0
        t3_rob = int((se.p_T3 < 0.05).sum()) if n_s else 0
        t1 = (f"place dependence of the field map (T1) {'holds' if r.p_T1_holm < 0.05 else 'not shown'} "
              f"(spatial information {r.T1:.3f} vs null {r.null_med_T1:.3f} bits/event, Holm p {r.p_T1_holm:.3f}; "
              f"p < 0.05 in {t1_rob} / {n_s} sensitivities)")
        st = ("stability across nights / trial halves not estimable (too little field time per night)" if not np.isfinite(r.T2) and not np.isfinite(r.T2b)
              else f"stability: LONO r {r.T2:.2f} (p {r.p_T2:.2f}), odd / even trials r {r.T2b:.2f} (p {r.p_T2b:.2f})")
        hr = (f"house / field rate ratio {r.house_field_rr:.2f} (bout-swap null median {np.exp(r.null_med_T3):.2f}, Holm p {r.p_T3_holm:.3f}; "
              f"p < 0.05 in {t3_rob} / {n_s} sensitivities)")
        sl = f"distance slope in the field {r.slope:.2f} (Holm p {r.p_slope_holm:.2f})"
        L.append(f"- **{r.animal}**{' (' + r.note + ')' if r.note else ''}: {t1}; {st}; {hr}; {sl}.")
    lo = (A.house_field_rr < 1).sum()
    L.append(f"- House vs field, all animals with both: the rate per non-locomotor minute is lower in the houses than in the field in "
             f"{int(lo)} / {int(A.house_field_rr.notna().sum())} (food was in the houses: home + food site + huddle).")
    return L


def report(A, RG, GL, SE, figs, run_dir, out, a) -> Path:
    from _common import report_dir
    rd = report_dir(COHORT)

    def f(v, d=2):
        return "-" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{d}f}"

    L = [f"# Awake ripples at night across the paddock (cohort {COHORT}) - Phase 2: maps per animal", "",
         "## Reading (generated from the tables below)", ""] + reading(A, SE) + ["",
         "Plan: [2026-10-10-awake-ripple-map.md](../../../../implementation_plan/2026-10-10-awake-ripple-map.md), Amendment 6 "
         f"(fixed before any map). Driver `ephys/awake_ripple_map.py phase2` (`ephys/awake_ripple_phase2.py`); per-second "
         f"tables `{run_dir}`; bulk `{out}`; {a.perms} bout swaps (sensitivities {a.sens_perms}).", "",
         "Validity (Amendment 5, strict blind reading by HC + raw MUA): awake ripples pass in the houses and the field "
         "(estimated true-ripple share 1.00 / 0.94). Notes per animal below.", "",
         "## Per animal", "",
         "| animal | field events / h | house events / h | field bins >= 60 s | inference | T1 spatial info (null median) | p (Holm) | "
         "T2 LONO r (null) | p (Holm) | T2b odd / even trials r (null) | p (Holm) | house / field rate ratio (null) | p (Holm) | "
         "1-D slope (null) | p (Holm) | note |",
         "|---|---|---|---:|:---:|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in A.itertuples():
        L.append(f"| {r.animal} | {r.field_events} / {f(r.field_h)} | {r.house_events} / {f(r.house_h)} | {r.field_bins_60s} | "
                 f"{'yes' if r.enters_inference else 'no'} | {f(r.T1, 3)} ({f(r.null_med_T1, 3)}) | {f(r.p_T1, 3)} ({f(r.p_T1_holm, 3)}) | "
                 f"{f(r.T2)} ({f(r.null_med_T2)}) | {f(r.p_T2, 3)} ({f(r.p_T2_holm, 3)}) | "
                 f"{f(r.T2b)} ({f(r.null_med_T2b)}) | {f(r.p_T2b, 3)} ({f(r.p_T2b_holm, 3)}) | "
                 f"{f(r.house_field_rr)} ({f(np.exp(r.null_med_T3) if np.isfinite(r.null_med_T3) else np.nan)}) | "
                 f"{f(r.p_T3, 3)} ({f(r.p_T3_holm, 3)}) | {f(r.slope)} ({f(r.null_med_slope)}) | {f(r.p_slope, 3)} ({f(r.p_slope_holm, 3)}) | {r.note} |")
    L += ["", "## 1-D profile (observed / expected against the block's field rate; null 95 % band)", "",
          "| animal | " + " | ".join(RING_LABELS) + " |", "|---|" + "---|" * len(RING_LABELS)]
    for an, g in RG.groupby("animal", sort=False):
        L.append(f"| {an} | " + " | ".join(f"{f(o)} [{f(lo)}, {f(hi)}]" if np.isfinite(o) else "-"
                                         for o, lo, hi in zip(g.oe, g.null_lo, g.null_hi)) + " |")
    L += ["", "## Bout-level Poisson GLM (description)", "",
          "| animal | pieces | house IRR [95 % CI] | field log-distance coefficient [95 % CI] |", "|---|---:|---|---|"]
    for r in GL.itertuples():
        L.append(f"| {r.animal} | {r.pieces} | {f(getattr(r, 'irr_house', np.nan))} [{f(getattr(r, 'irr_house_lo', np.nan))}, "
                 f"{f(getattr(r, 'irr_house_hi', np.nan))}] | {f(getattr(r, 'field_logdist_coef', np.nan))} "
                 f"[{f(getattr(r, 'field_logdist_lo', np.nan))}, {f(getattr(r, 'field_logdist_hi', np.nan))}] |")
    if len(SE):
        L += ["", "## Sensitivities (animals in inference)", "",
              "| sensitivity | animal | field events | T1 (p) | T2 (p) | T2b (p) | house / field RR (p) | slope (p) |", "|---|---|---:|---|---|---|---|---|"]
        for r in SE.itertuples():
            L.append(f"| {r.sensitivity} | {r.animal} | {r.field_events} | {f(r.T1, 3)} ({f(r.p_T1, 3)}) | {f(r.T2)} ({f(r.p_T2, 3)}) | "
                     f"{f(r.T2b)} ({f(r.p_T2b, 3)}) | "
                     f"{f(r.house_field_rr)} ({f(r.p_T3, 3)}) | {f(r.slope)} ({f(r.p_slope, 3)}) |")
    L += ["", "## Figures", ""] + [f"- ![{k}](../figures/{Path(v).name})" for k, v in figs.items()]
    L += ["", "## Definitions", "",
          "Units: WISER inches (unverified offset frame; topology and distances only); time in field-PC seconds.",
          "- **Awake ripple (aSWR):** a production kept SWR (`excluded == False`) whose peak falls in a non-locomotor detectable "
          "wake second (WAKE, head IMU ok and state still / active, outside handling, SWR-covered, theta-detectable, EMG-detectable "
          "on ripple-only blocks, with a position).",
          "- **Occupancy** $o_i$: non-locomotor detectable wake seconds in place $i$; **rate** $\\lambda_i = c_i / o_i$ "
          "(events per minute in tables and maps).",
          "- **Spatial information** (Skaggs): $I = \\sum_i p_i \\frac{\\lambda_i}{\\bar\\lambda} \\log_2 \\frac{\\lambda_i}{\\bar\\lambda}$, "
          "$p_i = o_i / \\sum o$, field bins with $o_i \\ge 60$ s, within block; combined as the occupancy-weighted mean. Bits "
          "per event; 0 = uniform.",
          "- **LONO r**: for each night $n$, Pearson $r$ between $\\lambda^{(n)}_i$ and $\\lambda^{(-n)}_i$ over bins with "
          ">= 60 s in both (>= 3 bins); the mean over nights weighted by bins.",
          "- **T2b** (Amendment 1's secondary split): trials (the night split at home naps) ranked by start; odd vs even "
          "trials' field rates, Pearson $r$ over bins >= 60 s in both halves (>= 3 bins).",
          "- **House / field rate ratio** (Mantel-Haenszel over blocks $b$): "
          "$RR = \\frac{\\sum_b c_{h,b} o_{f,b} / o_b}{\\sum_b c_{f,b} o_{h,b} / o_b}$.",
          "- **Ring O / E**: $O_k = \\sum_b c_{k,b}$, $E_k = \\sum_b o_{k,b} \\, c_{f,b} / o_{f,b}$ (the block's field rate); "
          "the **slope** of $\\log((O_k + 0.5)/E_k)$ on $\\log \\bar d_k$ over field rings with >= 60 s, weighted by occupancy minutes.",
          "- **Bout swap null**: bouts = maximal runs of consecutive non-locomotor seconds in a record; strata = night x block x "
          "duration class $\\lfloor \\log L / \\log 1.25 \\rfloor$ x clock hour; within a stratum the bouts' event sequences "
          "are permuted, offsets rescaled to the recipient's length. It keeps each bout's place, duration, time of night and "
          "event count distribution, and breaks the event-place link. p = (1 + #null >= obs) / (N + 1) (T1, T2 one-sided; "
          "RR and slope two-sided).",
          "- **Screen** for inference: >= 300 field aSWR and >= 10 field bins >= 60 s. Holm over the animals in inference.", "",
          "## Caveats", "",
          "- The houses are home, food site and huddle at once (food was in the houses): a house-vs-field difference is not "
          "'home' or 'reward' alone.",
          "- WISER frame unverified: maps show topology and distances, not compass directions; landmarks are reference marks.",
          "- Awake ripples are detected on CA1 LFP after the production's flags; SF09's field events were not validated "
          "(cannot be EMG-cleaned); SF08's field reading was half doubtful; SF07 / SF11 have too little field time for inference.",
          "- Theta-quiet aSWR (the pre-registered sensitivity) is a separate pass, not in this report yet.", ""]
    p = rd / f"ephys_spikes_awake_ripple_map_2026c.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"report {p}")
    return p


# ------------------------------------------------------------------ selftest
def selftest() -> None:
    rng = np.random.default_rng(3)
    ok = True
    n = 20000
    x = rng.uniform(270, 750, n)
    y = rng.uniform(610, 840, n)
    zone = np.where(rng.random(n) < 0.2, 2, 3)
    bl = rng.integers(5, 120, 400)
    rec = np.repeat(np.arange(len(bl)), bl)[:n]
    sec = np.arange(n) * 1 + rec * 1000
    S = pd.DataFrame({"sec": sec + 1_788_000_000, "night": np.where(rec % 2 == 0, "09-01", "09-02"), "rec": rec, "zone": zone, "x": x,
                      "y": y, "anchors": 9, "qc_i1": False, "blk": 0, "ble_pass": False, "nonloco": True})
    origin = np.array([263.8, 600.4])
    S["aswr"] = rng.poisson(0.05, n)
    P = prepare(S, origin)
    e2 = permuted_events(P, np.random.default_rng(1))
    a = abs(e2.sum() - P["e"].sum()) < 1e-9
    # swaps stay inside their bout's stratum: each event moves to a bout of the same stratum
    print(f"{'PASS' if a else 'FAIL'} the swap keeps the event total ({P['e'].sum()} -> {e2.sum():.0f}); swappable {P['swappable']:.2f}")
    ok &= a
    R0 = null_test(P, 200, 0)
    b = R0["p_T1"] > 0.05
    print(f"{'PASS' if b else 'FAIL'} uniform events: T1 p {R0['p_T1']:.3f} (no structure)")
    ok &= b
    hot = (np.hypot(x - 500, y - 650) < 40) & (zone == 3)
    S2 = S.copy()
    S2["aswr"] = rng.poisson(np.where(hot, 0.4, 0.05))
    # make the hotspot a property of place, independent of bouts: events stay where they are under the swap only if
    # bouts are in one place; here each bout wanders, so the swap breaks the place link
    P2 = prepare(S2, origin)
    R2 = null_test(P2, 200, 0)
    c = R2["p_T1"] < 0.05
    print(f"{'PASS' if c else 'FAIL'} planted hotspot: T1 {R2['obs']['T1']:.3f} vs null {R2['med_T1']:.3f}, p {R2['p_T1']:.3f}")
    ok &= c
    S3 = S.copy()
    S3["aswr"] = rng.poisson(np.where(S3.zone == 2, 0.2, 0.05))
    R3 = null_test(prepare(S3, origin), 200, 0)
    d = R3["p_T3"] < 0.05 and np.exp(R3["obs"]["T3"]) > 2
    print(f"{'PASS' if d else 'FAIL'} house 4x: RR {np.exp(R3['obs']['T3']):.2f}, p {R3['p_T3']:.3f}")
    ok &= d
    h = holm(pd.Series([0.01, 0.04, 0.03, np.nan]))
    e_ = np.allclose(h.iloc[:3].to_numpy(), [0.03, 0.06, 0.06]) and np.isnan(h.iloc[3])
    print(f"{'PASS' if e_ else 'FAIL'} Holm {h.round(3).tolist()}")
    ok &= e_
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    print(__doc__)
