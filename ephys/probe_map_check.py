"""Which channel order does an exported WILD ``amplifier.dat`` actually have? Test candidates against the data.

Background. The WILD CE64 logger carries an Intan RHD2164 whose raw SPI slots are routed to the Omnetics
connector differently from the lab's Intan headstage. WILD Console re-orders the raw slots on export with its
CE64 map (``configs/wild_ce64_channel_map_v57.csv``, column WILDIntanmapped: exported column c holds raw Intan
channel map[c]) so that the lab's Neuronexus probe XMLs (ProbeMaps repo, Intan-headstage numbering) apply
directly. Some firmware (FM57 documented; FM62/64 suspected) recorded the first 32-slot bank with a +1 slot
rotation, which after the export map becomes the permutation in ``vendor/correct_intan_dat_channel_order.py``;
FM65 is said to fix it. This script does not assume any of that: it scores candidate column permutations
against the recorded signal and the known probe geometry.

Method. For a session window (default 60 s from the middle, de-glitched with the 5-point median rule), build
the inter-channel correlation of the LFP band (1-300 Hz) and the spike band (500-5000 Hz). For each candidate
permutation P (data[:, c_intan] = export[:, P[c_intan]]) and each probe XML variant, reorder the channels into
probe sites and compute:

    adj      mean r between sites that are nearest neighbours along a shank (50 um apart on A4x16-Lin; 20 um
             steps on the Buzsaki 5x12 poly2 tips)      -> should be the LARGEST r in the matrix
    within   mean r between sites on the same shank, excluding nearest neighbours
    between  mean r between sites on different shanks
    contrast = adj - between (LFP and spike band separately); a correct map maximises it, a scrambled map gives ~0

Candidates (all are permutations of the 64 exported columns):
    identity        exported column c IS Intan channel c (the console map worked as designed)
    v57fix          apply vendor/correct_intan_dat_channel_order.py (undo a +1 rotation of raw bank 0)
    v57inv          the opposite rotation (-1)
    wildmap         Intan channel i = exported column map^-1[i]  (console map NOT applied on export)
    wildmap_inv     Intan channel i = exported column map[i]
    wildmap+v57fix, wildmap_inv+v57fix   the two above followed by the bank-0 fix

Usage:
  python ephys/probe_map_check.py --cohort 2026c --animal SF07 --session 2_20260901_002100.939 --probe A4x16-Lin-5mm-50s-300
  (--probe-xml <path> for an explicit XML; --seconds 60; --all-sessions to scan every session >= 10 min of the animal)
Writes results/<cohort>/ephys_spikes/reports/ephys_spikes_probe_map_check_<cohort>.csv (appended) and prints a table.
"""
from __future__ import annotations

import argparse
import csv
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from _common import PROJECT_ROOT, ephys_block, find_session_dir, iter_raw_sessions, parse_session_name, raw_ephys_root, report_dir, utc_now_iso
from deglitch_wild import estimate_thresholds, med5
from wild_ce_params import parse_ce_params

PROBEMAPS = Path(r"C:/Users/Cornell/Documents/GitHub/ProbeMaps/Neuronexus")
MAP_CSV = PROJECT_ROOT / "ephys" / "configs" / "wild_ce64_channel_map_v57.csv"

# ProbeMaps XML group order = sites along each shank, top to bottom (A4x16-Lin: 16 linear sites, 50 um;
# A5x12_16-Buz: poly2 tips (alternating columns) + 4 linear sites on the centre shank).
PROBE_XML = {
    "A4x16-Lin-5mm-50s-300": ["A4x16-Lin-5mm-50s-300.xml", "A4x16-Lin-5mm-50s-300_reversed.xml"],
    "A5x12_16-Buz_lin-5mm-100-200-160_177": ["A5x12_16-Buz_lin-5mm-100-200-160_177_version1.xml", "A5x12_16-Buz_lin-5mm-100-200-160_177_version2.xml"],
}


def load_groups(xml_path: Path) -> list[list[int]]:
    r = ET.parse(xml_path).getroot()
    return [[int(c.text) for c in g.findall("channel")] for g in r.find("anatomicalDescription/channelGroups").findall("group")]


def wild_map() -> np.ndarray:
    rows = list(csv.DictReader(open(MAP_CSV, encoding="utf-8")))
    m = np.array([int(r["WILDIntanmapped"]) for r in rows])   # exported column c holds raw channel m[c]
    assert np.array_equal(np.sort(m), np.arange(64))
    return m


def v57_source_columns(rotation: int) -> np.ndarray:
    """Corrected output column c <- input column src[c] (vendor tool, rotation +1 = the validated FM57 fault)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("v57fix", PROJECT_ROOT / "ephys" / "vendor" / "correct_intan_dat_channel_order.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.restored_source_columns(channel_count=64, bank=0, bank_size=32, acquisition_rotation=rotation)


def candidates() -> dict[str, np.ndarray]:
    """Return {name: P} with data_intan[:, i] = export[:, P[i]]."""
    ident = np.arange(64)
    m = wild_map()
    inv = np.empty(64, dtype=int); inv[m] = np.arange(64)
    fix = v57_source_columns(+1)       # corrected[:, c] = export[:, fix[c]]
    unfix = v57_source_columns(-1)
    return {
        "identity": ident,
        "v57fix": fix,
        "v57inv": unfix,
        "wildmap": inv,                # export col c holds raw channel m[c]  ->  raw channel i sits in export col inv[i]
        "wildmap_inv": m,
        "wildmap+v57fix": inv[fix],    # first undo the rotation in export space, then take raw channels
        "wildmap_inv+v57fix": m[fix],
    }


def band(x: np.ndarray, fs: float, lo: float, hi: float, decim: int = 1) -> np.ndarray:
    from scipy import signal
    b, a = signal.butter(2, [lo / (fs / 2), hi / (fs / 2)], "band")
    return signal.filtfilt(b, a, x, axis=0)[::decim]


def adjacency_pairs(groups: list[list[int]], probe: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:
    """(adjacent pairs, same-shank non-adjacent pairs, different-shank pairs) in Intan-channel ids."""
    adj, within, between = [], [], []
    for gi, g in enumerate(groups):
        n = len(g)
        for a in range(n):
            for b in range(a + 1, n):
                is_adj = (b == a + 1) if not probe.startswith("A5x12") else (b == a + 1 or b == a + 2)   # poly2: two columns interleaved
                (adj if is_adj else within).append((g[a], g[b]))
        for gj in range(gi + 1, len(groups)):
            for a in g:
                for b in groups[gj]:
                    between.append((a, b))
    return adj, within, between


def spike_coactivation(hp: np.ndarray, fs: float, thr_sigma: float = 5.0, min_events: int = 30, max_active: int = 8) -> np.ndarray:
    """Spike-triggered co-amplitude matrix A[i, j] (sigma units, positive = j deflects together with i).

    hp is the spike-band signal; a global median reference is removed first so that shared noise does not
    count as co-activation. Events on channel i = local minima below -thr_sigma*sigma_i (1-ms refractory).
    A[i, j] = median over i's LOCAL events of (-min of channel j within +/-0.3 ms) / sigma_j, where a local event
    deflects at most max_active channels beyond 3 sigma (array-wide transients are excluded). Rows with fewer
    than min_events local events are NaN. A real spike footprint gives A ~ 3-8 on the 1-3 nearest sites of the
    same shank and ~0 elsewhere, so this matrix is sharply local under the correct channel map."""
    x = hp - np.median(hp, axis=1, keepdims=True)
    sigma = 1.4826 * np.median(np.abs(x - np.median(x, 0)), 0) + 1e-6
    n, nch = x.shape
    half = max(1, int(round(0.3e-3 * fs)))
    refr = int(round(1e-3 * fs))
    A = np.full((nch, nch), np.nan)
    for i in range(nch):
        z = x[:, i] / sigma[i]
        below = np.where(z < -thr_sigma)[0]
        if below.size < min_events:
            continue
        # keep one event per crossing run, at its minimum
        splits = np.where(np.diff(below) > refr)[0] + 1
        runs = np.split(below, splits)
        peaks = np.array([r[np.argmin(z[r])] for r in runs if r.size])
        peaks = peaks[(peaks > half + 1) & (peaks < n - half - 2)]
        if peaks.size < min_events:
            continue
        # WIDTH gate: a real spike stays below -3 sigma on the trigger channel for >= 3 consecutive samples;
        # a single substituted sample (FM62/64 defect A) or residual tick cannot, so it is not an event
        wide = (z[peaks - 1] < -3.0) & (z[peaks + 1] < -3.0)
        peaks = peaks[wide]
        if peaks.size < min_events:
            continue
        idx = peaks[:, None] + np.arange(-half, half + 1)[None, :]
        seg = x[idx]                                    # events x window x channels
        # co-amplitude on every channel = -(mean of the 3 samples around that channel's own minimum inside
        # the window) / sigma: a 1-sample tick on the partner is diluted 3x, a spike is not
        kmin = seg.argmin(axis=1)                       # events x channels
        ev = np.arange(seg.shape[0])[:, None]
        ch = np.arange(nch)[None, :]
        k0 = np.clip(kmin - 1, 0, seg.shape[1] - 1); k2 = np.clip(kmin + 1, 0, seg.shape[1] - 1)
        tri = (seg[ev, k0, ch] + seg[ev, kmin, ch] + seg[ev, k2, ch]) / 3.0
        amp = -tri / sigma[None, :]                     # events x channels (sigma units)
        # keep only LOCAL events: an array-wide transient (movement, chewing, residual glitch) deflects most
        # channels at once and would make every pair look coupled; a spike footprint spans a few sites
        local = (amp > 3.0).sum(axis=1) <= max_active
        if local.sum() < min_events:
            continue
        A[i] = np.median(amp[local], axis=0)
    return A


def score(C: np.ndarray, P: np.ndarray, groups: list[list[int]], probe: str, dead: set[int]) -> dict:
    """C is the exported-column correlation; map to Intan ids through P then evaluate the geometry pairs."""
    # Intan channel i lives in exported column P[i]
    def r(i, j):
        return C[P[i], P[j]]
    adj, within, between = adjacency_pairs(groups, probe)
    ok = lambda p: p[0] not in dead and p[1] not in dead and np.isfinite(r(*p)) and np.isfinite(r(p[1], p[0]))
    sym = lambda p: 0.5 * (r(*p) + r(p[1], p[0]))
    A = [sym(p) for p in adj if ok(p)]
    W = [sym(p) for p in within if ok(p)]
    B = [sym(p) for p in between if ok(p)]
    if not A or not B:
        return {"adj": float("nan"), "within": float("nan"), "between": float("nan"), "contrast": float("nan")}
    return {"adj": float(np.mean(A)), "within": float(np.mean(W)) if W else float("nan"), "between": float(np.mean(B)), "contrast": float(np.mean(A) - np.mean(B))}


def site_positions(groups: list[list[int]]) -> dict[int, tuple[int, int]]:
    """Intan channel -> (shank index, position along shank) from the XML group order."""
    return {ch: (gi, k) for gi, g in enumerate(groups) for k, ch in enumerate(g)}


def nn_agreement(A: np.ndarray, P: np.ndarray, groups: list[list[int]], dead: set[int], max_dist: int = 2,
                 columns: set[int] | None = None) -> tuple[float, int]:
    """Fraction of event-bearing Intan channels whose strongest co-activation partner lies on the same shank within
    max_dist sites (XML order). Returns (fraction, n_channels_evaluated). ``columns`` restricts the evaluated
    channels to those whose EXPORTED column is in the set (e.g. bank 0 = columns 0-31)."""
    pos = site_positions(groups)
    hits, n = 0, 0
    for i in range(64):
        if i in dead or i not in pos:
            continue
        if columns is not None and int(P[i]) not in columns:
            continue
        row = A[P[i]].copy() if np.isfinite(A[P[i], 0]) else None
        if row is None:
            continue
        row[P[i]] = -np.inf
        for d in dead:
            row[P[d]] = -np.inf
        j_col = int(np.argmax(row))
        # exported column j_col -> Intan id
        j = int(np.where(P == j_col)[0][0])
        if j not in pos:
            continue
        n += 1
        if pos[i][0] == pos[j][0] and abs(pos[i][1] - pos[j][1]) <= max_dist:
            hits += 1
    return (hits / n if n else float("nan")), n


def partner_table(A: np.ndarray, dead_cols: set[int], k: int = 3) -> list[str]:
    """Per exported column: its k strongest partners (exported column ids) with co-amplitude in sigma."""
    lines = []
    for i in range(A.shape[0]):
        if not np.isfinite(A[i, 0]) or i in dead_cols:
            continue
        row = A[i].copy(); row[i] = -np.inf
        for d in dead_cols:
            row[d] = -np.inf
        top = np.argsort(row)[::-1][:k]
        lines.append(f"col {i:2d}: " + "  ".join(f"{int(j):2d}({row[j]:.1f})" for j in top) + f"   self {A[i, i]:.1f}")
    return lines


def derive_partition(A: np.ndarray, dead_cols: set[int], thr: float = 2.5) -> list[list[int]]:
    """Data-driven shank partition: connected components of the graph of strong symmetric co-activation
    (mean of A[i,j], A[j,i] >= thr sigma) over exported columns. Singletons (no strong partner) are dropped."""
    n = A.shape[0]
    S = np.where(np.isfinite(A), A, 0.0)
    S = 0.5 * (S + S.T)
    adj = S >= thr
    np.fill_diagonal(adj, False)
    for d in dead_cols:
        adj[d, :] = False; adj[:, d] = False
    seen, comps = set(), []
    for i in range(n):
        if i in seen or not adj[i].any():
            continue
        stack, comp = [i], []
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u); comp.append(u)
            stack.extend(int(v) for v in np.where(adj[u])[0] if v not in seen)
        comps.append(sorted(comp))
    return sorted(comps, key=lambda c: -len(c))


def derive_groups(A: np.ndarray, dead_cols: set[int], thr: float = 2.5, min_size: int = 2) -> list[list[int]]:
    """DATA-DERIVED shank groups in exported-column numbering, for loggers whose map cannot be verified.

    Groups = connected components of strong co-activation (>= thr sigma); within each group the columns are ordered
    along the shank by the Fiedler vector of the co-activation graph (spectral 1-D embedding), which places
    mutually coupled sites next to each other. Columns without a strong partner are appended as a trailing group so
    every channel stays in the XML (they should be marked skip for sorting). The absolute geometry (which end is
    dorsal, site pitch) is NOT recoverable this way; use it only for per-shank sorting."""
    S = np.where(np.isfinite(A), A, 0.0); S = 0.5 * (S + S.T)
    comps = [c for c in derive_partition(A, dead_cols, thr) if len(c) >= min_size]
    ordered = []
    for c in comps:
        if len(c) <= 2:
            ordered.append(c); continue
        W = S[np.ix_(c, c)].copy(); np.fill_diagonal(W, 0.0); W = np.maximum(W, 0.0)
        D = np.diag(W.sum(1)); L = D - W
        try:
            vals, vecs = np.linalg.eigh(L)
            f = vecs[:, 1]
            ordered.append([c[i] for i in np.argsort(f)])
        except np.linalg.LinAlgError:
            ordered.append(c)
    used = set(x for g in ordered for x in g)
    rest = [i for i in range(A.shape[0]) if i not in used]
    if rest:
        ordered.append(rest)
    return ordered


def compute_matrices(sdir: Path, seconds: float, cfg: dict, cache: Path | None = None) -> dict:
    """Load (or compute and cache) the per-session matrices used by every candidate test."""
    if cache is not None and cache.exists():
        z = np.load(cache, allow_pickle=False)
        return {"C_lfp": z["C_lfp"], "C_hp": z["C_hp"], "A_sp": z["A_sp"], "dead_cols": set(int(c) for c in z["dead_cols"]),
                "win_s": float(z["win_s"]), "firmware": int(z["firmware"])}
    cp = parse_ce_params(sdir)
    nch, fs = cp.n_channels or 64, float(cp.fs or 20000)
    ns = os.path.getsize(sdir / "amplifier.dat") // (2 * nch)
    win = int(min(ns, round(seconds * fs))); a0 = max(0, (ns - win) // 2)
    x = np.asarray(np.memmap(sdir / "amplifier.dat", dtype=np.int16, mode="r", shape=(ns, nch))[a0:a0 + win]).astype(np.float32)
    dg = cfg.get("deglitch") or {}
    thr = estimate_thresholds(x, float(dg.get("k_mad", 10)), float(dg.get("floor_adc", 500)), block=min(100_000, win), nblocks=min(8, max(1, win // 100_000)))
    # de-glitch in 1M-sample blocks (2-sample overlap for the 5-point median): a 30-min window as one array needs
    # 5 x window x 64 float32 (43 GB for 1800 s) and raised MemoryError (2026-09-04)
    B = 1_000_000
    for s0 in range(0, win, B):
        lo, hi = max(0, s0 - 2), min(win, s0 + B + 2)
        blk = x[lo:hi]; ref = med5(blk); bad = np.abs(blk - ref) > thr[None, :]
        i0 = s0 - lo; i1 = i0 + min(B, win - s0)
        seg = x[s0:s0 + (i1 - i0)]; seg[bad[i0:i1]] = ref[i0:i1][bad[i0:i1]]
    hp = band(x, fs, 500.0, 5000.0)
    noise = 1.4826 * np.median(np.abs(hp - np.median(hp, 0)), 0)
    dead_cols = set(int(c) for c in np.where((noise < 3.0 / 0.195) | (noise > 4 * np.median(noise)))[0])
    C_lfp = np.nan_to_num(np.corrcoef(band(x, fs, 1.0, 300.0, decim=16).T))
    C_hp = np.nan_to_num(np.corrcoef(hp.T))
    A_sp = spike_coactivation(hp.astype(np.float32), fs)
    out = {"C_lfp": C_lfp, "C_hp": C_hp, "A_sp": A_sp, "dead_cols": dead_cols, "win_s": win / fs, "firmware": int(cp.firmware_version)}
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, C_lfp=C_lfp, C_hp=C_hp, A_sp=A_sp, dead_cols=np.array(sorted(dead_cols), dtype=int), win_s=win / fs, firmware=int(cp.firmware_version))
    return out


def run_session(sdir: Path, probe: str, xml_variants: list[Path], seconds: float, cfg: dict, print_partners: bool = False,
                cache: Path | None = None, derive: bool = False) -> list[dict]:
    M_ = compute_matrices(sdir, seconds, cfg, cache)
    C_lfp, C_hp, A_sp, dead_cols = M_["C_lfp"], M_["C_hp"], M_["A_sp"], M_["dead_cols"]
    cp = parse_ce_params(sdir)
    fs = float(cp.fs or 20000); win = int(round(M_["win_s"] * fs))
    n_event_rows = int(np.isfinite(A_sp[:, 0]).sum())
    if derive:
        comps = derive_partition(A_sp, dead_cols)
        print(f"   data-driven partition (strong pairs >= 2.5 sigma), exported columns; bank0 = 0-31, bank1 = 32-63:")
        for k, c in enumerate(comps):
            b0 = [i for i in c if i < 32]; b1 = [i for i in c if i >= 32]
            print(f"      cluster {k}: n={len(c):2d}  bank0 {b0}  bank1 {b1}")
    if print_partners:
        print("   strongest co-activation partners per exported column (sigma):")
        for line in partner_table(A_sp, dead_cols):
            print("      " + line)
    out = []
    for name, P in candidates().items():
        invP = np.empty(64, dtype=int); invP[P] = np.arange(64)
        dead_intan = set(int(invP[c]) for c in dead_cols)     # Intan id whose column is dead
        for xp in xml_variants:
            groups = load_groups(xp)
            s_l = score(C_lfp, P, groups, probe, dead_intan)
            s_h = score(C_hp, P, groups, probe, dead_intan)
            s_s = score(A_sp, P, groups, probe, dead_intan)
            nn, nn_n = nn_agreement(A_sp, P, groups, dead_intan)
            nn0, nn0_n = nn_agreement(A_sp, P, groups, dead_intan, columns=set(range(32)))
            nn1, nn1_n = nn_agreement(A_sp, P, groups, dead_intan, columns=set(range(32, 64)))
            out.append({"session": sdir.name, "firmware": cp.firmware_version, "window_s": win / fs, "probe": probe, "xml": xp.name, "perm": name,
                        "nn_agree": round(nn, 3), "nn_n": nn_n, "nn_bank0": round(nn0, 3), "nn_bank0_n": nn0_n, "nn_bank1": round(nn1, 3), "nn_bank1_n": nn1_n,
                        "sp_adj": round(s_s["adj"], 2), "sp_within": round(s_s["within"], 2), "sp_between": round(s_s["between"], 2), "sp_contrast": round(s_s["contrast"], 2),
                        "sp_rows": n_event_rows,
                        "lfp_adj": round(s_l["adj"], 3), "lfp_within": round(s_l["within"], 3), "lfp_between": round(s_l["between"], 3), "lfp_contrast": round(s_l["contrast"], 3),
                        "hp_adj": round(s_h["adj"], 3), "hp_within": round(s_h["within"], 3), "hp_between": round(s_h["between"], 3), "hp_contrast": round(s_h["contrast"], 3),
                        "dead_cols": " ".join(map(str, sorted(dead_cols)))})
    return out


# Intan RHD2164 headstage pin grid as ProbeMaps/src/ProbeMapper.py INTAN_LAYOUTS[64] (4 rows x 16, flattened)
INTAN64_PINS = [46, 44, 42, 40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20, 18, 16,
                47, 45, 43, 41, 39, 37, 35, 33, 31, 29, 27, 25, 23, 21, 19, 17,
                49, 51, 53, 55, 57, 59, 61, 63, 1, 3, 5, 7, 9, 11, 13, 15,
                48, 50, 52, 54, 56, 58, 60, 62, 0, 2, 4, 6, 8, 10, 12, 14]


def orientation_variants(groups_v1: list[list[int]]) -> dict[str, list[list[int]]]:
    """From a ProbeMaps 'version1' XML (site -> Intan channel with the raw pin grid), derive all four connector
    orientations. ProbeMapper builds version1 with INTAN64_PINS and version2 with the reversed list (180-degree
    rotation); the two remaining physical orientations are the row-wise mirror (fliplr) and its reverse (flipud),
    which ProbeMapper only produces with flip_intan=True. Position p of a site is recovered from version1 as the
    index of its Intan channel in INTAN64_PINS, independent of the Omnetics connector table."""
    raw = INTAN64_PINS
    rot180 = list(reversed(raw))
    fliplr = [v for i in range(0, 64, 16) for v in reversed(raw[i:i + 16])]
    flipud = list(reversed(fliplr))
    pos = {ch: raw.index(ch) for g in groups_v1 for ch in g}
    out = {}
    for name, pins in (("v1_raw", raw), ("v2_rot180", rot180), ("v3_fliplr", fliplr), ("v4_flipud", flipud)):
        out[name] = [[pins[pos[ch]] for ch in g] for g in groups_v1]
    return out


def connector_variants(groups_v1: list[list[int]]) -> dict[str, list[list[int]]]:
    """Every physically possible mating of the probe's two 2x16 Omnetics connectors on the RHD2164 pin grid (rows 0-1 =
    channels 16-47, rows 2-3 = channels 0-15 + 48-63): each connector may be rotated 180 degrees in its own socket
    (A180 / B180), the two connectors may be swapped (swap), and the whole probe may be mirrored (m+, flipped over).
    16 variants; v1_raw / v2_rot180 / v3_fliplr / v4_flipud are the whole-grid orientations of orientation_variants().
    Added 2026-09-04 after the user's note that SF07/10/11/12 carry the same probe and only the logger connection can
    differ ("接错")."""
    raw = INTAN64_PINS
    pos = {ch: raw.index(ch) for g in groups_v1 for ch in g}

    def fmap(mirror: bool, swap: bool, a180: bool, b180: bool) -> list[int]:
        f = []
        for p in range(64):
            r, c = divmod(p, 16)
            if mirror:
                c = 15 - c
            if swap:
                r = (r + 2) % 4
            if a180 and r in (0, 1):
                r, c = 1 - r, 15 - c
            if b180 and r in (2, 3):
                r, c = 5 - r, 15 - c
            f.append(r * 16 + c)
        return f

    names = {(False, False, False, False): "v1_raw", (False, True, True, True): "v2_rot180",
             (True, False, False, False): "v3_fliplr", (True, True, True, True): "v4_flipud"}
    out = {}
    for mirror in (False, True):
        for swap in (False, True):
            for a180 in (False, True):
                for b180 in (False, True):
                    key = (mirror, swap, a180, b180)
                    name = names.get(key) or "+".join([t for t, on in (("m", mirror), ("swap", swap), ("A180", a180), ("B180", b180)) if on])
                    f = fmap(*key)
                    pins = [raw[f[q]] for q in range(64)]
                    out[name] = [[pins[pos[ch]] for ch in g] for g in groups_v1]
    return out


def physical_variants(groups_v1: list[list[int]], max_shift: int = 2) -> dict[str, dict]:
    """Physically possible matings of the two 2x16 Omnetics connectors, INCLUDING partial matings (2026-09-08, user's
    reference (3): a candidate order must be a describable way of plugging the probe in).

    Connector A = pin-grid rows 0-1 (Intan 16-47), connector B = rows 2-3 (Intan 0-15 + 48-63). Per connector: rotated 180 deg
    in its socket or not, and SHIFTED by k pin columns along the long axis (k = -max_shift..+max_shift; k = 0 is a full mating).
    A shift leaves |k| probe sites per row unconnected (they fall off the socket: no data column, dropped from the group) and
    |k| logger pins per row open (their channels record nothing: predicted DEAD columns). The two connectors may be swapped
    and the whole probe mirrored, as in connector_variants(). Returns name -> {"groups": Intan ids per shank in site order
    (unconnected sites removed), "dead_intan": Intan channels of the open logger pins, "desc": human description}.
    The 16 full matings of connector_variants() are the k_A = k_B = 0 members."""
    raw = INTAN64_PINS
    pos = {ch: raw.index(ch) for g in groups_v1 for ch in g}

    def mate(mirror: bool, swap: bool, a180: bool, b180: bool, ka: int, kb: int):
        """probe site position p -> logger pin position (or None if it falls off the socket)"""
        f = {}
        for p in range(64):
            r, c = divmod(p, 16)
            if mirror:
                c = 15 - c
            if swap:
                r = (r + 2) % 4
            if a180 and r in (0, 1):
                r, c = 1 - r, 15 - c
            if b180 and r in (2, 3):
                r, c = 5 - r, 15 - c
            k = ka if r in (0, 1) else kb
            c2 = c + k
            f[p] = None if not (0 <= c2 <= 15) else r * 16 + c2
        return f

    out = {}
    for mirror in (False, True):
        for swap in (False, True):
            for a180 in (False, True):
                for b180 in (False, True):
                    for ka in range(-max_shift, max_shift + 1):
                        for kb in range(-max_shift, max_shift + 1):
                            f = mate(mirror, swap, a180, b180, ka, kb)
                            groups = [[raw[f[pos[ch]]] for ch in g if f[pos[ch]] is not None] for g in groups_v1]
                            used = {f[pos[ch]] for g in groups_v1 for ch in g if f[pos[ch]] is not None}
                            dead_intan = sorted(raw[q] for q in range(64) if q not in used)
                            parts = [t for t, on in (("m", mirror), ("swap", swap), ("A180", a180), ("B180", b180)) if on]
                            if ka:
                                parts.append(f"A{ka:+d}")
                            if kb:
                                parts.append(f"B{kb:+d}")
                            name = "+".join(parts) if parts else "v1_raw"
                            if not ka and not kb:   # the four whole-grid orientations keep their connector_variants() names
                                name = {(False, True, True, True): "v2_rot180", (True, False, False, False): "v3_fliplr",
                                        (True, True, True, True): "v4_flipud"}.get((mirror, swap, a180, b180), name)
                            desc = ("probe mirrored; " if mirror else "") + ("connectors swapped; " if swap else "") + \
                                   ("A rotated 180; " if a180 else "") + ("B rotated 180; " if b180 else "") + \
                                   (f"A shifted {ka:+d} pin(s); " if ka else "") + (f"B shifted {kb:+d} pin(s); " if kb else "")
                            out[name] = {"groups": groups, "dead_intan": dead_intan, "desc": desc.strip("; ") or "standard full mating"}
    return out


def pair_agreement(A: np.ndarray, P: np.ndarray, groups: list[list[int]], dead: set[int], thr: float = 2.5) -> tuple[float, int]:
    """Fraction of strong symmetric pairs (>= thr sigma) that land on the same shank under the candidate map."""
    S = np.where(np.isfinite(A), A, 0.0); S = 0.5 * (S + S.T)
    shank = {}
    for gi, g in enumerate(groups):
        for ch in g:
            shank[ch] = gi
    invP = np.empty(64, dtype=int); invP[P] = np.arange(64)   # exported column -> Intan id
    ii, jj = np.where(np.triu(S, 1) >= thr)
    same, n = 0, 0
    for a, b in zip(ii, jj):
        ia, ib = int(invP[a]), int(invP[b])
        if ia in dead or ib in dead or ia not in shank or ib not in shank:
            continue
        n += 1
        same += int(shank[ia] == shank[ib])
    return (same / n if n else float("nan")), n


def rotation_permutation(r0: int, r1: int) -> np.ndarray:
    """Export-space correction for raw bank-0 rotation r0 and raw bank-1 rotation r1 (vendor conjugation)."""
    p0 = v57_source_columns(r0) if r0 else np.arange(64)
    import importlib.util
    spec = importlib.util.spec_from_file_location("v57fix", PROJECT_ROOT / "ephys" / "vendor" / "correct_intan_dat_channel_order.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    p1 = mod.restored_source_columns(channel_count=64, bank=1, bank_size=32, acquisition_rotation=r1) if r1 else np.arange(64)
    P = np.arange(64)
    P[:32] = p0[:32]
    P[32:] = p1[32:]
    return P


def rotation_scan(A_sp: np.ndarray, dead_cols: set[int], xml_variants: list[Path], max_rot: int = 4, top: int = 12, connector: bool = False) -> list[dict]:
    """Score every (orientation, bank-0 rotation, bank-1 rotation) by strong-pair agreement (primary) and
    nearest-neighbour agreement; the four orientations are derived from the first XML (assumed 'version1')."""
    variants = (connector_variants if connector else orientation_variants)(load_groups(xml_variants[0]))
    rows = []
    for vname, groups in variants.items():
        for r0 in range(-max_rot, max_rot + 1):
            for r1 in range(-max_rot, max_rot + 1):
                P = rotation_permutation(r0, r1)
                invP = np.empty(64, dtype=int); invP[P] = np.arange(64)
                dead_intan = set(int(invP[c]) for c in dead_cols)
                pa, npairs = pair_agreement(A_sp, P, groups, dead_intan)
                nn, n = nn_agreement(A_sp, P, groups, dead_intan)
                nn0, n0 = nn_agreement(A_sp, P, groups, dead_intan, columns=set(range(32)))
                nn1, n1 = nn_agreement(A_sp, P, groups, dead_intan, columns=set(range(32, 64)))
                rows.append({"orientation": vname, "rot_bank0": r0, "rot_bank1": r1, "pair_agree": pa, "n_pairs": npairs,
                             "nn_agree": nn, "n": n, "nn_bank0": nn0, "n0": n0, "nn_bank1": nn1, "n1": n1, "groups": groups})
    rows.sort(key=lambda r: -((r["pair_agree"] if np.isfinite(r["pair_agree"]) else -1) + 0.5 * (r["nn_agree"] if np.isfinite(r["nn_agree"]) else 0)))
    return rows[:top]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True); ap.add_argument("--animal", required=True)
    ap.add_argument("--session", default=None); ap.add_argument("--all-sessions", action="store_true")
    ap.add_argument("--min-minutes", type=float, default=10.0)
    ap.add_argument("--probe", default=None, choices=list(PROBE_XML)); ap.add_argument("--probe-xml", nargs="*", default=None)
    ap.add_argument("--seconds", type=float, default=60.0); ap.add_argument("--raw-root", default=None)
    ap.add_argument("--print-partners", action="store_true", help="list each column's strongest co-activation partners (map-independent evidence)")
    ap.add_argument("--derive", action="store_true", help="print the data-driven shank partition (connected components of strong pairs)")
    ap.add_argument("--cache-dir", default=None, help="cache the per-session matrices as <dir>/<animal>_<session>_<seconds>s.npz (re-tests are instant)")
    ap.add_argument("--rotation-scan", action="store_true", help="scan raw-bank rotations (-4..+4 per bank, conjugated through the WILD map) x XML variants")
    ap.add_argument("--connector-scan", action="store_true", help="with --rotation-scan: 16 connector matings (per-connector 180-degree rotation, swap, mirror) instead of the 4 whole-grid orientations")
    ap.add_argument("--derive-xml", default=None, help="write a DATA-DERIVED XML (exported-column groups from co-activation) to this path")
    a = ap.parse_args()
    cfg = ephys_block(a.cohort)
    raw = raw_ephys_root(a.cohort, a.raw_root)
    animal = a.animal.upper(); animal = f"SF{int(animal[2:]):02d}" if animal[2:].isdigit() else animal
    folder = next(c for c in (a.animal, animal, f"SF{int(animal[2:])}") if (raw / c).is_dir())
    xmls = [Path(p) for p in a.probe_xml] if a.probe_xml else [PROBEMAPS / f for f in PROBE_XML[a.probe]]
    probe = a.probe or xmls[0].stem
    sessions = []
    if a.all_sessions:
        for an, mac, sdir in iter_raw_sessions(raw, cohort=a.cohort):
            if an == folder and os.path.getsize(sdir / "amplifier.dat") // 128 / 20000 >= a.min_minutes * 60:
                sessions.append(sdir)
    else:
        sessions.append(find_session_dir(raw, folder, a.session))
    rows = []
    for sdir in sessions:
        print(f"== {animal} {sdir.name}", flush=True)
        cache = (Path(a.cache_dir) / f"{animal}_{sdir.name}_{int(a.seconds)}s.npz") if a.cache_dir else None
        if a.derive_xml:
            from make_session_xml import build_session_xml, write_xml
            M_ = compute_matrices(sdir, a.seconds, cfg, cache)
            groups = derive_groups(M_["A_sp"], M_["dead_cols"])
            trailing = groups[-1] if groups and all(len(g) >= 2 for g in groups[:-1]) else []
            reject = sorted(M_["dead_cols"] | set(trailing))
            root = build_session_xml(n_channels=64, fs=20000.0, groups=groups, reject=reject, layout="linear",
                                     description_extra=f"DATA-DERIVED from {sdir.name} co-activation (exported columns; shank identity/geometry unverified)")
            out = write_xml(root, Path(a.derive_xml))
            print(f"   data-derived XML -> {out}: {len(groups)} groups {[len(g) for g in groups]}, reject={reject}")
            for gi, g in enumerate(groups):
                print(f"      group {gi}: {g}")
            continue
        if a.rotation_scan:
            M_ = compute_matrices(sdir, a.seconds, cfg, cache)
            print(f"   rotation scan: 4 connector orientations x bank0/bank1 raw rotations (conjugated through the WILD map); top by pair-agreement:")
            for r in rotation_scan(M_["A_sp"], M_["dead_cols"], xmls, connector=a.connector_scan):
                print(f"      {r['orientation']:10s} rot0 {r['rot_bank0']:+d} rot1 {r['rot_bank1']:+d}  pairs same-shank {r['pair_agree']:.2f} (n={r['n_pairs']})  "
                      f"NN {r['nn_agree']:.2f} (n={r['n']})  bank0 {r['nn_bank0']:.2f} (n={r['n0']})  bank1 {r['nn_bank1']:.2f} (n={r['n1']})")
            continue
        rs = run_session(sdir, probe, xmls, a.seconds, cfg, print_partners=a.print_partners, cache=cache, derive=a.derive)
        rows.extend(rs)
        key = lambda r: -((r["nn_agree"] if np.isfinite(r["nn_agree"]) else -1) * 10 + (r["sp_contrast"] if np.isfinite(r["sp_contrast"]) else 0))
        best = sorted(rs, key=key)[:3]
        for r in sorted(rs, key=key):
            flag = " <==" if r is best[0] else ""
            print(f"   FM{r['firmware']} {r['perm']:20s} {r['xml']:52s} NN-agree {r['nn_agree']:.2f} (n={r['nn_n']:2d}) bank0 {r['nn_bank0']:.2f} (n={r['nn_bank0_n']:2d}) "
                  f"bank1 {r['nn_bank1']:.2f} (n={r['nn_bank1_n']:2d}) | SPIKE adj/between {r['sp_adj']:5.2f}/{r['sp_between']:5.2f} contrast {r['sp_contrast']:+6.2f}{flag}")
        print(f"   channels with >= 30 spike events: {rs[0]['sp_rows']}; dead exported columns: {rs[0]['dead_cols']}")
    if not rows:
        return
    out = report_dir(a.cohort) / f"ephys_spikes_probe_map_check_{a.cohort}.csv"
    new = not out.exists()
    with open(out, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["written_utc", "animal"] + list(rows[0].keys()))
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({"written_utc": utc_now_iso(), "animal": animal, **r})
    print(f"appended {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
