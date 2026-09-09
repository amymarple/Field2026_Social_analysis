"""Channel-map test #3: the hippocampal LFP depth profile must be SMOOTH along a shank (sharp wave, ripple power, theta phase).

Physics (user, 2026-09-08): on a linear shank crossing CA1 the sharp wave (SPW) is positive in stratum oriens / pyramidale and
reverses gradually to negative in stratum radiatum; ripple power peaks in the pyramidal layer and falls off on both sides; theta
phase shifts monotonically with depth. So under the correct within-shank site order all three profiles are smooth; a scrambled
order makes them jagged. The test needs 30 min of LFP and no spike sorting.

Method
  1. Window of the pipeline's .lfp (1250 Hz, 64 exported columns) from the sort folder (daytime sessions are sleep-rich).
  2. Ripples: 130-200 Hz band-pass on every live column, |Hilbert| envelope smoothed 8 ms, z-scored; event = max_z > thr for
     >= 20 ms (merged within 50 ms); peak = argmax of the summed envelope.
  3. Profiles per column: SPW = ripple-triggered mean of the 1-50 Hz LFP over +-15 ms (uV, relative 0.195 uV/count);
     RIPPLE = mean envelope at the peak; THETA = circular-mean phase difference (6-10 Hz Hilbert) to the column with the most
     theta power, over the 2-s windows with the highest theta/delta ratio (REM / running).
  4. Adjacent-site spacing: r_adj = ripple-band (130-200 Hz) correlation of consecutive sites in a candidate order. With an
     exponential fall-off of correlation with distance, the implied distance between two consecutive sites is
     50 um * ln(r_adj) / ln(r_ref), r_ref = median r_adj of the reference shank (--ref-group, a shank whose order is trusted).
     A pair implying >= 1.5 sites is flagged as a GAP (a missing / dead site between them, or a larger pitch).
     CAVEAT (SF10, 2026-09-08): the correlation is NOT a distance when site impedances differ. High-impedance sites carry
     attenuated signal plus shared noise: on SF10 shank 4 the eight even-Intan sites (connector-B row 3) have 4x smaller SPW,
     20 % lower LFP rms and correlate with EACH OTHER at r 0.47 regardless of distance (odd-even 0.26, between shanks 0.11),
     and single degraded sites (SF10 cols 3, 17, 15, 47) correlate with nothing, so they look like gaps. Treat the gap flags as
     a prompt to look at the site's amplitude, never as evidence for placing a dead column; a dead column's position needs the
     physical wiring (user, 2026-09-08). In raw mode the correlation uses the 300-3000 Hz band at 20 kHz (first 2 min).
  5. Scores per candidate order (per shank, averaged): spw_tv, ripple_tv, theta_tv (total variation / range; 1.0 = monotonic),
     flips (SPW sign changes; correct: 0 or 1). Ranking = sum of the three tv ranks (--rank-by spw|theta|ripple|all).
  Candidates: connector_variants (16 full matings) x bank rotations, or --physical: physical_variants (per-connector 180 deg
  rotation, swap, mirror AND pin shifts -2..+2 with their predicted dead columns; a shift is only physically consistent if its
  predicted dead columns lie inside the user's broken-channel list, reported as dead_ok).
  Self-check of the tool: on SF07 its own verified map must rank first. SF07's mating differs from the other animals, so its map is
  NOT a reference for them (user, 2026-09-08) — the 'ref. v1_raw' line is the ProbeMaps standard order, printed for orientation only.

Usage: python ephys/lfp_profile_check.py --cohort 2026c --animal SF10 --session 9_20260902_083247.835 [--minutes 30]
        [--bad 2 32 34 ...] [--ref-group 4] [--physical] [--max-rot 1] [--top 12] [--profile-only]
        [--permute-tail GROUP N   brute-force the order of the last N sites of one group (N <= 7)]
        [--derive-xml OUT --keep-groups 1 4   write a DATA-DERIVED order (positive-SPW sites by ripple power asc, then
         negative-SPW sites by SPW desc); each dead column is placed as a PACE MAKER at the largest SPW-gradient gap of its
         shank, never at the end of the group (its exact site stays unknown, but the position keeps the geometry honest)]
Appends results/<cohort>/ephys_spikes/reports/ephys_spikes_lfp_profile_check_<cohort>.csv.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from scipy.signal import butter, filtfilt, hilbert

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import git_commit, report_dir, sort_root, utc_now_iso  # noqa: E402
from probe_map_check import PROBE_XML, PROBEMAPS, connector_variants, load_groups, physical_variants, rotation_permutation  # noqa: E402
from footprint_map_check import candidate_sites  # noqa: E402
from wild_ce_params import parse_ce_params  # noqa: E402
from deglitch_wild import estimate_thresholds, med5  # noqa: E402

UV = 0.195
PITCH_UM = 50.0


def bp(x: np.ndarray, fs: float, lo: float, hi: float, order: int = 3) -> np.ndarray:
    b, a = butter(order, [lo / (fs / 2), hi / (fs / 2)], btype="band")
    return filtfilt(b, a, x, axis=0)


def detect_ripples(lfp: np.ndarray, fs: float, live: np.ndarray, thr: float = 4.0, min_ms: float = 20.0, merge_ms: float = 50.0):
    rip = bp(lfp[:, live], fs, 130.0, 200.0)
    env = np.abs(hilbert(rip, axis=0))
    k = max(1, int(0.008 * fs)); ker = np.ones(k) / k
    env = np.apply_along_axis(lambda v: np.convolve(v, ker, mode="same"), 0, env)
    z = (env - env.mean(0)) / (env.std(0) + 1e-9)
    zmax = z.max(1); zsum = z.sum(1)
    above = zmax > thr
    idx = np.where(np.diff(above.astype(int)) != 0)[0] + 1
    if above[0]:
        idx = np.r_[0, idx]
    if above[-1]:
        idx = np.r_[idx, len(above)]
    segs = idx.reshape(-1, 2) if idx.size % 2 == 0 else idx[:-1].reshape(-1, 2)
    merged = []
    for s, e in segs:
        if merged and s - merged[-1][1] < merge_ms / 1000 * fs:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    peaks = [s + int(np.argmax(zsum[s:e])) for s, e in merged if (e - s) >= min_ms / 1000 * fs]
    return np.array(peaks, dtype=int), env, rip


def profiles(lfp: np.ndarray, fs: float, peaks: np.ndarray, env_live: np.ndarray, live: np.ndarray, half_ms: float = 15.0):
    slow = bp(lfp, fs, 1.0, 50.0)
    h = int(half_ms / 1000 * fs); W = int(0.15 * fs)
    ok = peaks[(peaks > W) & (peaks < lfp.shape[0] - W)]
    spw = np.zeros(lfp.shape[1]); rp = np.zeros(lfp.shape[1]); n = 0
    for t in ok:
        spw += slow[t - h:t + h + 1].mean(0); n += 1
    spw = spw / max(n, 1) * UV
    rp_live = np.zeros(len(live))
    for t in ok:
        rp_live += env_live[max(0, t - h):t + h + 1].mean(0)
    rp[live] = rp_live / max(n, 1) * UV
    return spw, rp, n


def theta_profile(lfp: np.ndarray, fs: float, live: np.ndarray, win_s: float = 2.0, top_frac: float = 0.3):
    """Circular-mean theta (6-10 Hz) phase of every live column relative to the column with the most theta power, over the
    windows with the highest theta/delta ratio. Returns (phase_deg[64], theta_power[64], ref_col, n_windows)."""
    th = bp(lfp[:, live], fs, 6.0, 10.0); de = bp(lfp[:, live], fs, 1.0, 4.0)
    w = int(win_s * fs); nwin = lfp.shape[0] // w
    ratio = np.array([(th[i * w:(i + 1) * w] ** 2).mean() / ((de[i * w:(i + 1) * w] ** 2).mean() + 1e-9) for i in range(nwin)])
    keep = np.argsort(ratio)[-max(3, int(top_frac * nwin)):]
    sel = np.concatenate([np.arange(i * w, (i + 1) * w) for i in sorted(keep)])
    an = hilbert(th[sel], axis=0)
    power = (np.abs(an) ** 2).mean(0)
    ref_i = int(np.argmax(power))
    d = np.angle(an * np.conj(an[:, [ref_i]]))
    ph = np.angle(np.exp(1j * d).mean(0))
    phase = np.full(lfp.shape[1], np.nan); tp = np.zeros(lfp.shape[1])
    phase[live] = np.degrees(ph); tp[live] = power * UV * UV
    return phase, tp, int(live[ref_i]), len(keep)


def load_raw_lfp(raw_dir: Path, minutes: float, offset_min: float, cfg: dict, target_fs: float = 1250.0) -> tuple[np.ndarray, float, int]:
    """Read `minutes` of a RAW WILD session (amplifier.dat, int16, 64 ch, 20 kHz) starting at `offset_min`, de-glitch it when the
    firmware is below the clean gate, and decimate to target_fs (anti-aliased, chunked). No staging, no preprocessing needed."""
    cp = parse_ce_params(raw_dir)
    nch, fs0 = cp.n_channels or 64, float(cp.fs or 20000.0)
    ns = (raw_dir / "amplifier.dat").stat().st_size // (2 * nch)
    q = int(round(fs0 / target_fs))
    a0 = int(offset_min * 60 * fs0) if offset_min >= 0 else max(0, ns + int(offset_min * 60 * fs0))   # negative = minutes from the END
    win = int(min(ns - a0, minutes * 60 * fs0))
    mm = np.memmap(raw_dir / "amplifier.dat", dtype=np.int16, mode="r", shape=(ns, nch))
    deglitch = int(cp.firmware_version) < int(cfg.get("clean_firmware_min", 65))
    thr = None
    chunks = []
    step = int(60 * fs0)
    S1 = np.zeros(nch); S2 = np.zeros((nch, nch)); N = 0          # spike-band correlation accumulators (300-3000 Hz at 20 kHz)
    for s0 in range(a0, a0 + win, step):
        x = np.asarray(mm[s0:min(a0 + win, s0 + step)]).astype(np.float32)
        if deglitch:
            if thr is None:
                dg = cfg.get("deglitch") or {}
                thr = estimate_thresholds(x, float(dg.get("k_mad", 10)), float(dg.get("floor_adc", 500)), block=min(100_000, len(x)), nblocks=min(8, max(1, len(x) // 100_000)))
            ref = med5(x); bad = np.abs(x - ref) > thr[None, :]; x[bad] = ref[bad]
        if N < 120 * fs0:                      # spike-band correlation from the first 2 min is enough for spacing (cost: filtfilt on 64 x 1.2M per chunk)
            hp = bp(x, fs0, 300.0, 3000.0).astype(np.float64)
            S1 += hp.sum(0); S2 += hp.T @ hp; N += hp.shape[0]
        # anti-alias with a 4th-order Butterworth low-pass at 0.4 x target Nyquist, then stride (the FIR `decimate` took minutes per window)
        b_lp, a_lp = butter(4, 0.4 * (target_fs / 2) / (fs0 / 2), btype="low")
        chunks.append(filtfilt(b_lp, a_lp, x, axis=0)[::q].astype(np.float64))
    mean = S1 / N; cov = S2 / N - np.outer(mean, mean); sd = np.sqrt(np.clip(np.diag(cov), 1e-12, None))
    C_hp = cov / np.outer(sd, sd)
    return np.concatenate(chunks, 0), fs0 / q, int(cp.firmware_version), C_hp


def tv_and_flips(p: np.ndarray) -> tuple[float, int]:
    if p.size < 3:
        return float("nan"), 0
    rng = p.max() - p.min()
    tv = float(np.abs(np.diff(p)).sum() / rng) if rng > 0 else float("nan")
    s = np.sign(p[np.abs(p) > 0.15 * np.abs(p).max()])
    flips = int(np.sum(np.diff(s) != 0)) if s.size > 1 else 0
    return tv, flips


def tv_phase(deg: np.ndarray) -> float:
    if deg.size < 3 or np.any(np.isnan(deg)):
        return float("nan")
    u = np.degrees(np.unwrap(np.radians(deg)))
    rng = u.max() - u.min()
    return float(np.abs(np.diff(u)).sum() / rng) if rng > 1e-6 else float("nan")


C_HP = None   # spike-band (300-3000 Hz, 20 kHz) correlation matrix of the analysed window; set in raw/staged mode


def adjacent_r(rip_live: np.ndarray, live: np.ndarray, order: list[int]) -> np.ndarray:
    """Correlation between consecutive sites of `order`: the 20-kHz spike band when available (falls off over ~100 um, so it
    resolves site spacing), else the 130-200 Hz ripple band (volume-conducted, r 0.9-0.99 everywhere - NOT a spacing measure)."""
    if C_HP is not None:
        return np.array([float(C_HP[a, b]) for a, b in zip(order[:-1], order[1:])])
    idx = {int(c): i for i, c in enumerate(live)}
    out = []
    for a, b in zip(order[:-1], order[1:]):
        out.append(float(np.corrcoef(rip_live[:, idx[a]], rip_live[:, idx[b]])[0, 1]) if (a in idx and b in idx) else np.nan)
    return np.array(out)


def implied_sites(r_adj: np.ndarray, r_ref: float) -> np.ndarray:
    """distance between consecutive sites in units of one pitch, from exponential decay of correlation."""
    r = np.clip(r_adj, 1e-3, 0.999)
    return np.log(r) / np.log(np.clip(r_ref, 1e-3, 0.999))


def score_order(order: list[int], spw, rp, theta, rip_live, live, r_ref) -> dict:
    tv_s, fl = tv_and_flips(spw[order]); tv_r, _ = tv_and_flips(rp[order]); tv_t = tv_phase(theta[order])
    ra = adjacent_r(rip_live, live, order)
    gaps = implied_sites(ra, r_ref) if r_ref else np.full(len(order) - 1, np.nan)
    return {"spw_tv": tv_s, "flips": fl, "ripple_tv": tv_r, "theta_tv": tv_t, "r_adj": ra, "gaps": gaps}


def fmt_profile(order, spw, rp, theta, gaps=None) -> str:
    parts = []
    for i, c in enumerate(order):
        th = "" if np.isnan(theta[c]) else f"/{theta[c]:+.0f}d"
        parts.append(f"{c}:{spw[c]:+.0f}/{rp[c]:.0f}{th}")
        if gaps is not None and i < len(gaps) and not np.isnan(gaps[i]) and gaps[i] >= 1.5:
            parts.append(f"<gap {gaps[i]:.1f}>")
    return " ".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True); ap.add_argument("--animal", required=True); ap.add_argument("--session", required=True)
    ap.add_argument("--probe", default="A4x16-Lin-5mm-50s-300", choices=list(PROBE_XML))
    ap.add_argument("--sort-root", default=None)
    ap.add_argument("--minutes", type=float, default=10.0); ap.add_argument("--offset-min", type=float, default=None, help="window start in minutes; negative = from the end (raw mode); default: middle of the session")
    ap.add_argument("--thr", type=float, default=4.0); ap.add_argument("--max-rot", type=int, default=1); ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--bad", type=int, nargs="*", default=None, help="broken columns from visual inspection (Neuroscope)")
    ap.add_argument("--ref-group", type=int, default=None, help="1-based group of the current XML whose order is trusted: sets the 50-um correlation scale")
    ap.add_argument("--physical", action="store_true", help="candidates = physical_variants (matings incl. pin shifts) instead of the 16 full matings")
    ap.add_argument("--rank-by", default="all", choices=["all", "spw", "theta", "ripple"])
    ap.add_argument("--profile-only", action="store_true"); ap.add_argument("--show-top", type=int, default=2)
    ap.add_argument("--permute-tail", type=int, nargs=2, metavar=("GROUP", "N"), default=None, help="brute-force the last N sites of one current-XML group")
    ap.add_argument("--derive-xml", default=None); ap.add_argument("--keep-groups", type=int, nargs="*", default=[])
    ap.add_argument("--raw", default=None, help="RAW session folder (…/<MAC>/<session>): read amplifier.dat directly and decimate to 1250 Hz; no sort folder needed")
    ap.add_argument("--xml", default=None, help="grouping XML when there is no sort folder (default: the animal's xml: in probes_<cohort>.yaml)")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()

    an = a.animal.upper(); an = f"SF{int(an[2:]):02d}" if an.startswith("SF") and an[2:].isdigit() else an
    sdir = sort_root(a.cohort, a.sort_root) / an / a.session
    if a.raw:
        from _common import PROJECT_ROOT, ephys_block
        import yaml
        cfg = ephys_block(a.cohort)
        off = a.offset_min if a.offset_min is not None else 0.0
        lfp, fs, fw, C_hp = load_raw_lfp(Path(a.raw), a.minutes, off, cfg)
        global C_HP; C_HP = C_hp
        nch = lfp.shape[1]; win = lfp.shape[0]; a0 = int(off * 60 * fs); bad = set()
        xml_path = Path(a.xml) if a.xml else PROJECT_ROOT / yaml.safe_load((PROJECT_ROOT / cfg.get("probe_config", f"ephys/configs/probes_{a.cohort}.yaml")).read_text(encoding="utf-8"))["animals"][an]["xml"]
        print(f"   raw mode: {a.raw} (FM{fw}), grouping XML {xml_path}")
    else:
        pm = json.loads((sdir / "preprocessSession_manifest.json").read_text(encoding="utf-8"))
        lfp_path = Path(pm["lfp_path"]); nch = int(pm["n_channels"]); fs = float(pm.get("sr_lfp") or 1250.0)
        bad = set(int(c) for c in (pm.get("bad_channels_0based") or []))
        ns = lfp_path.stat().st_size // (2 * nch)
        win = int(min(ns, a.minutes * 60 * fs))
        a0 = int(a.offset_min * 60 * fs) if a.offset_min is not None else max(0, (ns - win) // 2)
        lfp = np.asarray(np.memmap(lfp_path, dtype=np.int16, mode="r", shape=(ns, nch))[a0:a0 + win]).astype(np.float64)
        xml_path = Path(a.xml) if a.xml else sdir / f"{a.session}.xml"
    flat = set(int(c) for c in np.where(lfp.std(0) < 1.0)[0])
    xroot = ET.parse(xml_path).getroot()
    skipped = set(int(c.text) for c in xroot.iter("channel") if c.get("skip") == "1")
    dead = bad | flat | skipped | (set(int(c) for c in a.bad) if a.bad else set())
    live = np.array([c for c in range(nch) if c not in dead])
    peaks, env, rip_live = detect_ripples(lfp, fs, live, thr=a.thr)
    spw, rp, n = profiles(lfp, fs, peaks, env, live)
    theta, tpow, ref_col, nwin = theta_profile(lfp, fs, live)
    all_groups = [[int(c.text) for c in g.findall("channel")] for g in xroot.findall("anatomicalDescription/channelGroups/group")]
    xml_groups = [[c for c in g if c not in dead] for g in all_groups]
    print(f"== {an} {a.session}: {win / fs / 60:.0f} min from {a0 / fs / 60:.0f} min, {len(live)} live columns (dead {sorted(dead)}), "
          f"{n} ripples, theta ref col {ref_col} over {nwin} x 2-s windows")

    # reference correlation scale (one pitch)
    r_ref = None
    if a.ref_group and 1 <= a.ref_group <= len(xml_groups) and len(xml_groups[a.ref_group - 1]) >= 4:
        r_ref = float(np.nanmedian(adjacent_r(rip_live, live, xml_groups[a.ref_group - 1])))
        print(f"   spacing scale from group {a.ref_group}: median adjacent {'spike-band (300-3000 Hz)' if C_HP is not None else 'ripple-band'} r = {r_ref:.2f} == one pitch ({PITCH_UM:.0f} um)")

    print("   current XML per shank (top->bottom): col:SPW_uV/ripple/theta_deg  <gap n> = implied distance in sites where >= 1.5 (spike-band correlation)")
    cur = []
    for k, g in enumerate(xml_groups, 1):
        if len(g) < 4:
            continue
        sc = score_order(g, spw, rp, theta, rip_live, live, r_ref); cur.append(sc)
        print(f"     shank {k}: {fmt_profile(g, spw, rp, theta, sc['gaps'])}")
        print(f"              spw tv {sc['spw_tv']:.2f} flips {sc['flips']} | ripple tv {sc['ripple_tv']:.2f} | theta tv {sc['theta_tv']:.2f}"
              + (f" | adjacent r {np.round(sc['r_adj'], 2).tolist()}" if r_ref else ""))
    if cur:
        print(f"   current XML mean: spw tv {np.nanmean([c['spw_tv'] for c in cur]):.2f}, ripple tv {np.nanmean([c['ripple_tv'] for c in cur]):.2f}, "
              f"theta tv {np.nanmean([c['theta_tv'] for c in cur]):.2f}")

    if a.permute_tail:
        gi, nt = a.permute_tail; g = xml_groups[gi - 1]; head, tail = g[:-nt], g[-nt:]
        res = []
        for perm in itertools.permutations(tail):
            o = head + list(perm); sc = score_order(o, spw, rp, theta, rip_live, live, r_ref)
            res.append((sc["spw_tv"] + sc["ripple_tv"] + (sc["theta_tv"] if not np.isnan(sc["theta_tv"]) else 3.0), sc, o))
        res.sort(key=lambda t: t[0])
        print(f"   permutations of the last {nt} sites of group {gi} ({len(res)}): best 5 by spw+ripple+theta tv (current order marked)")
        for tot, sc, o in res[:5]:
            print(f"     {tot:.2f}  {'<== current' if o == g else '           '} {fmt_profile(o[-nt - 1:], spw, rp, theta)}  spw {sc['spw_tv']:.2f} rip {sc['ripple_tv']:.2f} th {sc['theta_tv']:.2f}")
        cur_tot = next(t for t, sc, o in res if o == g)
        print(f"     current order total {cur_tot:.2f}, rank {sorted(t for t, _, _ in res).index(cur_tot) + 1}/{len(res)}")

    if a.derive_xml:
        from make_session_xml import build_session_xml, write_xml
        new_groups = []
        print("   data-derived order (oriens -> pyramidale -> radiatum), per group; dead columns inserted at detected gaps when possible:")
        for k, g in enumerate(all_groups, 1):
            livec = [c for c in g if c not in dead]; deadc = [c for c in g if c in dead]
            if k in a.keep_groups or len(livec) < 4:
                new_groups.append(g); print(f"     group {k}: kept as is ({len(livec)} live)"); continue
            pos = sorted([c for c in livec if spw[c] >= 0], key=lambda c: rp[c])
            neg = sorted([c for c in livec if spw[c] < 0], key=lambda c: -spw[c])
            o = pos + neg
            sc = score_order(o, spw, rp, theta, rip_live, live, r_ref)
            # dead columns are PACE MAKERS: each goes where the SPW gradient of its shank shows the largest gap, never at the end
            # (user 2026-09-08: "dead channel 不能在最后, 因为这样会影响对 channel 物理位置的判断; 归属可以根据 LFP 梯度 difference 给出").
            seq = [[c, float(spw[c])] for c in o]
            for dc in deadc:
                if len(seq) < 2:
                    seq.append([dc, 0.0]); continue
                gaps = [abs(seq[i + 1][1] - seq[i][1]) for i in range(len(seq) - 1)]
                j = int(np.argmax(gaps))
                seq.insert(j + 1, [dc, (seq[j][1] + seq[j + 1][1]) / 2])
            placed = [c for c, _ in seq]
            print(f"     group {k}: {fmt_profile(o, spw, rp, theta, sc['gaps'])}  | spw tv {sc['spw_tv']:.2f} rip {sc['ripple_tv']:.2f} th {sc['theta_tv']:.2f}"
                  + (f"  | dead placed: {[c for c in placed if c in dead]} at positions {[placed.index(c) + 1 for c in placed if c in dead]}" if deadc else ""))
            new_groups.append(placed)
        desc = (f"{an} data-derived within-shank order from the ripple-triggered LFP profile of {a.session} ({n} ripples, {win / fs / 60:.0f} min): "
                f"positive-SPW sites by ripple power asc, then negative-SPW sites by SPW desc; groups {sorted(a.keep_groups)} kept from the verified map; "
                f"dead columns {sorted(dead & set(c for g in all_groups for c in g))} skip=1, placed as pace makers at the largest SPW-gradient gap of their shank; "
                f"channels = exported columns")
        out = write_xml(build_session_xml(n_channels=nch, fs=20000.0, groups=new_groups, reject=sorted(dead), layout="linear", description_extra=desc), Path(a.derive_xml))
        print(f"   -> {out}")
    if a.profile_only or a.derive_xml or a.permute_tail:
        return

    groups_v1 = load_groups(PROBEMAPS / PROBE_XML[a.probe][0])
    user_bad = set(int(c) for c in a.bad) if a.bad else set()
    fam = physical_variants(groups_v1, 2) if a.physical else {k: {"groups": v, "dead_intan": [], "desc": k} for k, v in connector_variants(groups_v1).items()}
    rows = []
    for vname, var in fam.items():
        for r0 in range(-a.max_rot, a.max_rot + 1):
            for r1 in range(-a.max_rot, a.max_rot + 1):
                P = rotation_permutation(r0, r1)
                shank, depth = candidate_sites(var["groups"], P)
                pred_dead = sorted(int(P[i]) for i in var["dead_intan"])
                dead_ok = (not pred_dead) or set(pred_dead) <= (user_bad | skipped | bad)
                scs = []
                for k in range(len(var["groups"])):
                    cols = [c for c in np.where(shank == k)[0] if c not in dead]
                    if len(cols) < 6:
                        continue
                    cols = sorted(cols, key=lambda c: depth[c])
                    scs.append(score_order(cols, spw, rp, theta, rip_live, live, r_ref))
                if not scs:
                    continue
                rows.append({"variant": vname, "desc": var["desc"], "rot_bank0": r0, "rot_bank1": r1, "n_shanks": len(scs),
                             "spw_tv": float(np.nanmean([s["spw_tv"] for s in scs])), "ripple_tv": float(np.nanmean([s["ripple_tv"] for s in scs])),
                             "theta_tv": float(np.nanmean([s["theta_tv"] for s in scs])), "flips": float(np.mean([s["flips"] for s in scs])),
                             "pred_dead": pred_dead, "dead_ok": dead_ok})
    for key in ("spw_tv", "ripple_tv", "theta_tv"):
        order = sorted(range(len(rows)), key=lambda i: (np.nan_to_num(rows[i][key], nan=9.0)))
        for rank, i in enumerate(order, 1):
            rows[i][key + "_rank"] = rank
    for r in rows:
        r["rank_sum"] = {"all": r["spw_tv_rank"] + r["ripple_tv_rank"] + r["theta_tv_rank"], "spw": r["spw_tv_rank"], "theta": r["theta_tv_rank"], "ripple": r["ripple_tv_rank"]}[a.rank_by]
    rows.sort(key=lambda r: (not r["dead_ok"], r["rank_sum"]))
    ref = next((r for r in rows if r["variant"] == "v1_raw" and r["rot_bank0"] == 1 and r["rot_bank1"] == 0), None)
    print(f"   {len(rows)} candidates ({'physical incl. pin shifts' if a.physical else '16 full matings'} x rotations); ranked by {a.rank_by}; dead_ok = predicted dead columns inside the broken list")
    for i, r in enumerate(rows[:a.top]):
        tag = "  <== SF07's map" if r is ref else ""
        print(f"   {i + 1:3d}. {r['variant']:14s} rot0 {r['rot_bank0']:+d} rot1 {r['rot_bank1']:+d}  spw {r['spw_tv']:.2f} rip {r['ripple_tv']:.2f} th {r['theta_tv']:.2f} "
              f"flips {r['flips']:.1f}  ranks {r['spw_tv_rank']}/{r['ripple_tv_rank']}/{r['theta_tv_rank']}  dead_ok {r['dead_ok']}"
              + (f" pred_dead {r['pred_dead']}" if r["pred_dead"] else "") + f"  [{r['desc']}]{tag}")
    if ref is not None and ref not in rows[:a.top]:
        print(f"   ref. v1_raw +1/+0 (ProbeMaps standard order; = SF07's own mating, not a reference for other animals): rank {rows.index(ref) + 1}, spw {ref['spw_tv']:.2f} rip {ref['ripple_tv']:.2f} th {ref['theta_tv']:.2f}")
    for r in rows[:a.show_top]:
        var = fam[r["variant"]]; P = rotation_permutation(r["rot_bank0"], r["rot_bank1"]); shank, depth = candidate_sites(var["groups"], P)
        print(f"   profiles under {r['variant']} {r['rot_bank0']:+d}/{r['rot_bank1']:+d}:")
        for k in range(len(var["groups"])):
            cols = sorted([c for c in np.where(shank == k)[0] if c not in dead], key=lambda c: depth[c])
            if len(cols) < 6:
                continue
            sc = score_order(cols, spw, rp, theta, rip_live, live, r_ref)
            print(f"     shank {k + 1}: {fmt_profile(cols, spw, rp, theta, sc['gaps'])}  | spw {sc['spw_tv']:.2f} rip {sc['ripple_tv']:.2f} th {sc['theta_tv']:.2f}")
    if not a.no_write and rows:
        out = report_dir(a.cohort) / f"ephys_spikes_lfp_profile_check_{a.cohort}.csv"
        new = not out.exists()
        with open(out, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["written_utc", "animal", "session", "minutes", "n_ripples", "n_live", "family", "rank_by", "rank", "variant", "desc", "rot_bank0", "rot_bank1",
                            "spw_tv", "ripple_tv", "theta_tv", "flips", "dead_ok", "pred_dead", "repo_git"])
            for i, r in enumerate(rows[:a.top]):
                w.writerow([utc_now_iso(), an, a.session, a.minutes, n, len(live), "physical" if a.physical else "matings", a.rank_by, i + 1, r["variant"], r["desc"],
                            r["rot_bank0"], r["rot_bank1"], round(r["spw_tv"], 3), round(r["ripple_tv"], 3), round(r["theta_tv"], 3) if not np.isnan(r["theta_tv"]) else "",
                            round(r["flips"], 2), r["dead_ok"], " ".join(map(str, r["pred_dead"])), git_commit()])
        print(f"   -> {out}")


if __name__ == "__main__":
    main()
