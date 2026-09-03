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


def score(C: np.ndarray, P: np.ndarray, groups: list[list[int]], probe: str, dead: set[int]) -> dict:
    """C is the exported-column correlation; map to Intan ids through P then evaluate the geometry pairs."""
    # Intan channel i lives in exported column P[i]
    def r(i, j):
        return C[P[i], P[j]]
    adj, within, between = adjacency_pairs(groups, probe)
    ok = lambda p: p[0] not in dead and p[1] not in dead
    A = [r(*p) for p in adj if ok(p)]
    W = [r(*p) for p in within if ok(p)]
    B = [r(*p) for p in between if ok(p)]
    return {"adj": float(np.mean(A)), "within": float(np.mean(W)), "between": float(np.mean(B)), "contrast": float(np.mean(A) - np.mean(B))}


def run_session(sdir: Path, probe: str, xml_variants: list[Path], seconds: float, cfg: dict) -> list[dict]:
    cp = parse_ce_params(sdir)
    nch, fs = cp.n_channels or 64, float(cp.fs or 20000)
    ns = os.path.getsize(sdir / "amplifier.dat") // (2 * nch)
    win = int(min(ns, round(seconds * fs))); a0 = max(0, (ns - win) // 2)
    x = np.asarray(np.memmap(sdir / "amplifier.dat", dtype=np.int16, mode="r", shape=(ns, nch))[a0:a0 + win]).astype(np.float32)
    dg = cfg.get("deglitch") or {}
    thr = estimate_thresholds(x, float(dg.get("k_mad", 10)), float(dg.get("floor_adc", 500)), block=min(100_000, win), nblocks=min(8, max(1, win // 100_000)))
    ref = med5(x); bad = np.abs(x - ref) > thr[None, :]; x[bad] = ref[bad]
    # dead channels (exported-column ids): flat spike band
    hp = band(x, fs, 500.0, 5000.0)
    noise = 1.4826 * np.median(np.abs(hp - np.median(hp, 0)), 0)
    dead_cols = set(int(c) for c in np.where((noise < 3.0 / 0.195) | (noise > 4 * np.median(noise)))[0])
    C_lfp = np.nan_to_num(np.corrcoef(band(x, fs, 1.0, 300.0, decim=16).T))
    C_hp = np.nan_to_num(np.corrcoef(hp.T))
    out = []
    for name, P in candidates().items():
        invP = np.empty(64, dtype=int); invP[P] = np.arange(64)
        dead_intan = set(int(invP[c]) for c in dead_cols)     # Intan id whose column is dead
        for xp in xml_variants:
            groups = load_groups(xp)
            s_l = score(C_lfp, P, groups, probe, dead_intan)
            s_h = score(C_hp, P, groups, probe, dead_intan)
            out.append({"session": sdir.name, "firmware": cp.firmware_version, "window_s": win / fs, "probe": probe, "xml": xp.name, "perm": name,
                        "lfp_adj": round(s_l["adj"], 3), "lfp_within": round(s_l["within"], 3), "lfp_between": round(s_l["between"], 3), "lfp_contrast": round(s_l["contrast"], 3),
                        "hp_adj": round(s_h["adj"], 3), "hp_within": round(s_h["within"], 3), "hp_between": round(s_h["between"], 3), "hp_contrast": round(s_h["contrast"], 3),
                        "dead_cols": " ".join(map(str, sorted(dead_cols)))})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True); ap.add_argument("--animal", required=True)
    ap.add_argument("--session", default=None); ap.add_argument("--all-sessions", action="store_true")
    ap.add_argument("--min-minutes", type=float, default=10.0)
    ap.add_argument("--probe", default=None, choices=list(PROBE_XML)); ap.add_argument("--probe-xml", nargs="*", default=None)
    ap.add_argument("--seconds", type=float, default=60.0); ap.add_argument("--raw-root", default=None)
    a = ap.parse_args()
    cfg = ephys_block(a.cohort)
    raw = raw_ephys_root(a.cohort, a.raw_root)
    animal = a.animal.upper(); animal = f"SF{int(animal[2:]):02d}" if animal[2:].isdigit() else animal
    folder = next(c for c in (a.animal, animal, f"SF{int(animal[2:])}") if (raw / c).is_dir())
    xmls = [Path(p) for p in a.probe_xml] if a.probe_xml else [PROBEMAPS / f for f in PROBE_XML[a.probe]]
    probe = a.probe or xmls[0].stem
    sessions = []
    if a.all_sessions:
        for an, mac, sdir in iter_raw_sessions(raw):
            if an == folder and os.path.getsize(sdir / "amplifier.dat") // 128 / 20000 >= a.min_minutes * 60:
                sessions.append(sdir)
    else:
        sessions.append(find_session_dir(raw, folder, a.session))
    rows = []
    for sdir in sessions:
        print(f"== {animal} {sdir.name}", flush=True)
        rs = run_session(sdir, probe, xmls, a.seconds, cfg)
        rows.extend(rs)
        best = sorted(rs, key=lambda r: -(r["lfp_contrast"] + r["hp_contrast"]))[:3]
        for r in rs:
            flag = " <==" if r is best[0] else ""
            print(f"   FM{r['firmware']} {r['perm']:22s} {r['xml']:52s} LFP adj/within/between {r['lfp_adj']:.2f}/{r['lfp_within']:.2f}/{r['lfp_between']:.2f} "
                  f"contrast {r['lfp_contrast']:+.3f} | HP {r['hp_adj']:.2f}/{r['hp_within']:.2f}/{r['hp_between']:.2f} contrast {r['hp_contrast']:+.3f}{flag}")
        print(f"   dead exported columns: {rs[0]['dead_cols']}")
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
