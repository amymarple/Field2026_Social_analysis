"""Unit-yield report over every sorted session of a cohort (Kilosort4 + PreprocessPipeline postprocess -> Phy folders).

Scans <sort_root>/<SFxx>/<session>/ for sort_manifest.json and the postprocessed Phy folders
(Kilosort4_<ts>_probe1_shank<k>_spi). Per shank it reads cluster_group.tsv (good / mua / noise labels written by the
postprocess noise rules), quality_metrics.csv (firing_rate, isi_violations_ratio, presence_ratio, snr, amplitude_median)
and spike_clusters.npy for spike counts. Nothing is re-sorted.

Definitions:
    KS4 units          clusters Kilosort4 emitted for the shank (before postprocess), from sort_manifest/log when present
    final clusters     clusters in the *_spi Phy folder after duplicate removal, merge, autosplit
    good / mua / noise the cluster_group.tsv label; 'noise' = failed the postprocess metric thresholds
                       (isi_violations_ratio > 5, presence_ratio < 0.1, snr < 2, amplitude_median < 15 or > 500 uV, rate < 0.01 Hz)
    candidate units    final clusters not labelled noise (= good + mua + unsorted); the number to curate in Phy
    lt3hz              candidate units with rate < 3 Hz: the hippocampal criterion (pyramidal cells fire sparsely; the
                       user's rule 2026-09-04: "count cells below 3 Hz", do not gate on a minimum rate beyond the
                       postprocess 0.01-Hz floor); ge3hz = candidates at >= 3 Hz (putative interneurons / multi-unit)
    well-isolated      candidate units with isi_violations_ratio < 0.5 and snr >= 5 (isolation only, no rate gate)
    rate (Hz)          spikes / recording duration; amplitude in uV uses the pipeline's 0.195 uV/count (relative)
All counts depend on the placeholder channel map for SF08/10/11/12 (provisional) and SF09 (data-derived groups).

Usage: python ephys/unit_yield_report.py --cohort 2026c
Writes results/<cohort>/ephys_spikes/reports/ephys_spikes_ks4_unit_yield_<cohort>.{md,csv} + figures/..._unit_yield_<cohort>.png
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

from _common import analysis_root, figure_dir, git_commit, report_dir, sort_root, stage_root, utc_now_iso


def read_tsv(p: Path) -> list[dict]:
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def read_metrics(p: Path) -> dict[int, dict]:
    out = {}
    if not p.exists():
        return out
    with open(p, encoding="utf-8") as f:
        rd = csv.DictReader(f)
        idcol = rd.fieldnames[0]
        for r in rd:
            try:
                out[int(float(r[idcol]))] = r
            except (ValueError, TypeError):
                continue
    return out


def scan_shank(spi: Path, duration_s: float) -> dict:
    groups = {int(r["cluster_id"]): r["group"] for r in read_tsv(spi / "cluster_group.tsv")} if (spi / "cluster_group.tsv").exists() else {}
    metrics = read_metrics(spi / "quality_metrics.csv")
    n_spikes: dict[int, int] = {}
    if (spi / "spike_clusters.npy").exists():
        clu = np.load(spi / "spike_clusters.npy").ravel()
        ids, cnt = np.unique(clu, return_counts=True)
        n_spikes = {int(i): int(c) for i, c in zip(ids, cnt)}
    ids = sorted(set(groups) | set(metrics) | set(n_spikes))
    rows = []
    for cid in ids:
        g = groups.get(cid, "unsorted")
        m = metrics.get(cid, {})
        def fnum(k):
            try:
                return float(m[k])
            except (KeyError, ValueError, TypeError):
                return float("nan")
        isi = fnum("isi_violations_ratio"); snr = fnum("snr"); amp = fnum("amplitude_median"); pres = fnum("presence_ratio")
        ns = n_spikes.get(cid, 0)
        rate = ns / duration_s if duration_s else float("nan")
        rows.append({"cluster": cid, "group": g, "n_spikes": ns, "rate_hz": rate, "isi_viol": isi, "snr": snr, "amp_uV": abs(amp) if amp == amp else amp, "presence": pres,
                     "candidate": g != "noise", "lt3hz": (g != "noise") and rate < 3.0, "ge3hz": (g != "noise") and rate >= 3.0,
                     "well_isolated": (g != "noise") and (isi == isi and isi < 0.5) and (snr == snr and snr >= 5)})
    return {"clusters": rows, "n_final": len(rows), "n_good": sum(1 for r in rows if r["group"] == "good"), "n_mua": sum(1 for r in rows if r["group"] == "mua"),
            "n_noise": sum(1 for r in rows if r["group"] == "noise"), "n_unsorted": sum(1 for r in rows if r["group"] not in ("good", "mua", "noise")),
            "n_candidate": sum(1 for r in rows if r["candidate"]), "n_lt3": sum(1 for r in rows if r["lt3hz"]), "n_ge3": sum(1 for r in rows if r["ge3hz"]),
            "n_lt3_well": sum(1 for r in rows if r["lt3hz"] and r["well_isolated"]), "n_well": sum(1 for r in rows if r["well_isolated"]),
            "spikes_total": sum(r["n_spikes"] for r in rows)}


def scan_raw_shank(raw: Path, duration_s: float) -> dict:
    """Kilosort4 output BEFORE postprocess (a session whose postprocess is still running, or a --no-post run).

    group = cluster_group.tsv of the sorter folder (Kilosort's KSLabel good/mua, plus 'noise' where PreprocessPipeline's
    sorter runner applied its low-rate relabel), candidate = not noise; well_isolated = KSLabel good and Kilosort's
    ContamPct < 10 (no SNR / ISI metrics exist yet, so this is Kilosort's own contamination estimate). Amplitude is
    Kilosort's template amplitude (arbitrary scale, not µV) and is left out of the medians."""
    def two_col(p: Path) -> dict[int, str]:   # cluster_id + one label column (KS4 names it KSLabel in both files; the low-rate relabel writes 'group')
        out = {}
        for r in (read_tsv(p) if p.exists() else []):
            keys = list(r.keys())
            try:
                out[int(r[keys[0]])] = str(r[keys[1]]).strip()
            except (ValueError, IndexError, TypeError):
                continue
        return out
    ks = two_col(raw / "cluster_KSLabel.tsv")
    groups = two_col(raw / "cluster_group.tsv")
    contam: dict[int, float] = {}
    if (raw / "cluster_ContamPct.tsv").exists():
        for r in read_tsv(raw / "cluster_ContamPct.tsv"):
            try:
                contam[int(r["cluster_id"])] = float(r["ContamPct"])
            except (KeyError, ValueError, TypeError):
                pass
    n_spikes: dict[int, int] = {}
    if (raw / "spike_clusters.npy").exists():
        clu = np.load(raw / "spike_clusters.npy").ravel()
        ids, cnt = np.unique(clu, return_counts=True)
        n_spikes = {int(i): int(c) for i, c in zip(ids, cnt)}
    rows = []
    for cid in sorted(set(ks) | set(groups) | set(n_spikes)):
        g = groups.get(cid) or ks.get(cid, "unsorted")
        ns = n_spikes.get(cid, 0)
        rate = ns / duration_s if duration_s else float("nan")
        if g != "noise" and rate == rate and rate < 0.01:
            g = "noise"   # the sorter runner's own low-rate rule (mark_low_firing_rate_clusters_as_noise, 0.01 Hz), applied here when it has not run yet
        c = contam.get(cid, float("nan"))
        well = (g != "noise") and ks.get(cid) == "good" and (c == c and c < 10.0)
        rows.append({"cluster": cid, "group": g, "n_spikes": ns, "rate_hz": rate, "isi_viol": float("nan"), "snr": float("nan"), "amp_uV": float("nan"),
                     "presence": float("nan"), "contam_pct": c, "candidate": g != "noise", "lt3hz": (g != "noise") and rate < 3.0,
                     "ge3hz": (g != "noise") and rate >= 3.0, "well_isolated": well})
    return {"clusters": rows, "stage": "ks4-raw", "n_final": len(rows), "n_good": sum(1 for r in rows if r["group"] == "good"),
            "n_mua": sum(1 for r in rows if r["group"] == "mua"), "n_noise": sum(1 for r in rows if r["group"] == "noise"),
            "n_unsorted": sum(1 for r in rows if r["group"] not in ("good", "mua", "noise")),
            "n_candidate": sum(1 for r in rows if r["candidate"]), "n_lt3": sum(1 for r in rows if r["lt3hz"]), "n_ge3": sum(1 for r in rows if r["ge3hz"]),
            "n_lt3_well": sum(1 for r in rows if r["lt3hz"] and r["well_isolated"]), "n_well": sum(1 for r in rows if r["well_isolated"]),
            "spikes_total": sum(r["n_spikes"] for r in rows)}


def ks4_units_from_log(session_dir: Path, shank_folder: str) -> int | None:
    """Number of clusters Kilosort4 wrote (spike_clusters.npy of the raw sorter folder)."""
    raw = session_dir / shank_folder.replace("_spi", "")
    p = raw / "spike_clusters.npy"
    if p.exists():
        return int(np.unique(np.load(p).ravel()).size)
    return None


def session_duration_s(man: dict, sdir: Path, stage_man: dict) -> float:
    dur = float((man.get("stage_manifest") or {}).get("duration_s") or 0)
    if not dur:
        pm = sdir / "preprocessSession_manifest.json"
        if pm.exists():
            p = json.loads(pm.read_text(encoding="utf-8"))
            n = p.get("subsession_sample_counts") or []
            dur = sum(n) / float(p.get("sr") or 20000.0) if n else 0.0
    if not dur:
        dur = float(stage_man.get("duration_s") or 0)
    return dur


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--sort-root", default=None)
    a = ap.parse_args()
    root = sort_root(a.cohort, a.sort_root)
    sessions = []
    # every <animal>/<session> dir that has a sort_manifest.json OR at least one Kilosort4 sorter folder (run in progress)
    for sdir in sorted(p for p in root.glob("*/*") if p.is_dir() and not p.name.startswith((".", "_"))):
        skip = lambda n: n.startswith(".") or ".preserved-" in n or ".attempt-" in n   # pipeline backups, not sorter runs
        raw_dirs = sorted(p for p in sdir.glob("Kilosort4_*_probe*_shank*")
                          if p.is_dir() and not p.name.endswith("_spi") and not skip(p.name))
        mf = sdir / "sort_manifest.json"
        # A re-sort writes a NEW timestamped folder set and leaves the previous one in place (run_sort_session --overwrite does
        # not delete it), so a session can hold several runs. Keep only the current one: the folders the manifest lists (plus
        # anything a resort added), else the newest timestamp present. Seen on SF09 2026-09-08 (7-group + 5-shank runs = 12 rows).
        if mf.exists() and raw_dirs:
            man0 = json.loads(mf.read_text(encoding="utf-8"))
            current = {Path(d).name for d in ((man0.get("result") or {}).get("sorter_output_dirs") or [])}
            for r in man0.get("resorts") or []:
                current |= {Path(d).name for d in (r.get("kilosort4_dirs") or [])}
            keep = [d for d in raw_dirs if d.name in current] if current else []
            if not keep:                      # no manifest paths (or none survive): fall back to the newest timestamp
                stamps = sorted({re.match(r"Kilosort4_(\d{4}-\d{2}-\d{2}_\d{6})_", d.name).group(1)
                                 for d in raw_dirs if re.match(r"Kilosort4_(\d{4}-\d{2}-\d{2}_\d{6})_", d.name)})
                keep = [d for d in raw_dirs if stamps and d.name.startswith(f"Kilosort4_{stamps[-1]}_")] or raw_dirs
            elif (man0.get("resorts") or []) and len(keep) < len(raw_dirs):
                # ONLY after a partial re-sort (resort_shanks.py): the shanks it did not touch come from the earlier run.
                # A full re-run's sorter_output_dirs is complete on its own — SF09's 5-shank run must not inherit the
                # superseded 7-group run's shanks 6 and 7.
                have = {re.search(r"_shank(\d+)$", d.name).group(1) for d in keep if re.search(r"_shank(\d+)$", d.name)}
                keep += [d for d in raw_dirs if d not in keep and (m2 := re.search(r"_shank(\d+)$", d.name)) and m2.group(1) not in have]
            raw_dirs = sorted(keep, key=lambda d: d.name)
        if not raw_dirs and not mf.exists():
            continue
        man = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
        animal, session = man.get("animal") or sdir.parent.name, man.get("session") or sdir.name
        stage_man = man.get("stage_manifest") or {}
        if not stage_man:
            smf = stage_root(a.cohort, None) / animal / session / "stage_manifest.json"
            stage_man = json.loads(smf.read_text(encoding="utf-8")) if smf.exists() else {}
        dur = session_duration_s(man, sdir, stage_man)
        shanks = []
        seen = set()
        for raw in raw_dirs:
            m = re.search(r"_probe(\d+)_shank(\d+)$", raw.name)
            sh = int(m.group(2)) if m else 0
            spi = sdir / (raw.name + "_spi")
            if spi.is_dir():
                r = scan_shank(spi, dur); r["stage"] = "post"; r["folder"] = spi.name
            else:
                r = scan_raw_shank(raw, dur); r["folder"] = raw.name
            r["shank"] = sh; r["ks4_units"] = ks4_units_from_log(sdir, raw.name + "_spi")
            shanks.append(r); seen.add(raw.name + "_spi")
        for spi in sorted(sdir.glob("Kilosort4_*_spi")):   # Phy folders whose sorter folder is gone
            # not "gone" if the raw folder is still on disk: then this _spi belongs to a superseded run filtered out above
            if spi.name in seen or skip(spi.name) or (sdir / spi.name[:-4]).is_dir():
                continue
            m = re.search(r"_probe(\d+)_shank(\d+)_spi$", spi.name)
            r = scan_shank(spi, dur); r["stage"] = "post"; r["folder"] = spi.name; r["shank"] = int(m.group(2)) if m else 0; r["ks4_units"] = None
            shanks.append(r)
        shanks.sort(key=lambda r: r["shank"])
        n_post = sum(1 for r in shanks if r["stage"] == "post")
        status = f"done ({man.get('post_mode', 'full')})" if mf.exists() else f"in progress: postprocess {n_post}/{len(shanks)} shanks"
        bad = (man.get("result") or {}).get("bad_channels_0based")
        if bad is None:
            pm = sdir / "preprocessSession_manifest.json"
            bad = (json.loads(pm.read_text(encoding="utf-8")).get("bad_channels_0based") if pm.exists() else []) or []
        sessions.append({"animal": animal, "session": session, "dir": sdir, "duration_s": dur, "firmware": (stage_man.get("header") or {}).get("firmware_version"),
                         "deglitched": stage_man.get("deglitch_applied"), "bad_channels": bad, "probe_verified": man.get("probe_verified"),
                         "elapsed_min": float(man.get("elapsed_s", 0)) / 60, "shanks": shanks, "status": status, "post_mode": man.get("post_mode")})
    if not sessions:
        raise SystemExit(f"no sorted sessions under {root}")

    rd = report_dir(a.cohort); fd = figure_dir(a.cohort)
    csv_path = rd / f"ephys_spikes_ks4_unit_yield_{a.cohort}.csv"
    md_path = rd / f"ephys_spikes_ks4_unit_yield_{a.cohort}.md"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["animal", "session", "duration_h", "firmware", "status", "post_mode", "shank", "stage", "ks4_units", "final_clusters", "good", "mua", "unsorted", "noise",
                    "candidate_units", "lt3hz_units", "lt3hz_well_isolated", "ge3hz_units", "well_isolated", "spikes_total",
                    "median_rate_hz_candidates", "median_amp_uV_candidates", "median_snr_candidates"])
        for s in sessions:
            for sh in s["shanks"]:
                cand = [r for r in sh["clusters"] if r["candidate"]]
                med = lambda k: (float(np.nanmedian([r[k] for r in cand])) if cand else float("nan"))
                w.writerow([s["animal"], s["session"], round(s["duration_s"] / 3600, 2), s["firmware"], s["status"], s["post_mode"] or "", sh["shank"], sh["stage"], sh["ks4_units"],
                            sh["n_final"], sh["n_good"], sh["n_mua"], sh["n_unsorted"], sh["n_noise"], sh["n_candidate"], sh["n_lt3"], sh["n_lt3_well"], sh["n_ge3"], sh["n_well"],
                            sh["spikes_total"], round(med("rate_hz"), 3), round(med("amp_uV"), 1), round(med("snr"), 2)])

    L = [f"# Kilosort4 unit yield, cohort `{a.cohort}`\n",
         f"Generated {utc_now_iso()} by `ephys/unit_yield_report.py` (git {git_commit()}) from `{root}`. One ~8-h FM65 daytime session per logger "
         "(2026-09-02), PreprocessPipeline defaults (500–8000 Hz, local CMR 20–200 µm, per-shank high-amplitude artifact removal at 5 σ), "
         "Kilosort4 per shank, postprocess (dedupe → merge → autosplit → metrics → noise labels). Definitions in the script docstring. "
         "**Counts are pre-curation**: `candidate` = everything not auto-labelled noise; **`< 3 Hz` = the hippocampal count** (pyramidal cells fire sparsely, "
         "so cells are counted by rate < 3 Hz, no minimum-rate gate beyond the 0.01-Hz postprocess floor); `≥ 3 Hz` = fast-firing candidates (putative interneurons / multi-unit); "
         "`well-isolated` = ISI-violation ratio < 0.5 and SNR ≥ 5 (isolation only). "
         "Channel maps: SF07 verified; SF08/10/11/12 provisional (SF07's map); SF09 data-derived groups without geometry. "
         "Rows with stage `ks4-raw` are Kilosort4 output whose postprocess has not run yet: labels = Kilosort's KSLabel (+ the sorter runner's low-rate "
         "relabel), `well-isolated` there = KSLabel good & ContamPct < 10, amplitude/SNR medians unavailable. `post_mode` fast = features on ≤ 500 spikes per unit, "
         "no PCA autosplit, no Phy pc_features (see ephys/run_sort_session.py); full = the pipeline's all-spike passes.\n",
         "## Per logger\n",
         "| logger | session | h | FW | status | shanks | KS4 units | final clusters | noise | candidate units | **< 3 Hz** | < 3 Hz & well-isolated | ≥ 3 Hz | spikes | median rate Hz | median amp µV | bad ch | sort time min |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    totals = defaultdict(int)
    for s in sessions:
        cand = [r for sh in s["shanks"] for r in sh["clusters"] if r["candidate"]]
        ks4 = sum(sh["ks4_units"] or 0 for sh in s["shanks"])
        fin = sum(sh["n_final"] for sh in s["shanks"]); noi = sum(sh["n_noise"] for sh in s["shanks"]); ncand = sum(sh["n_candidate"] for sh in s["shanks"])
        nlt3 = sum(sh["n_lt3"] for sh in s["shanks"]); nlt3w = sum(sh["n_lt3_well"] for sh in s["shanks"]); nge3 = sum(sh["n_ge3"] for sh in s["shanks"])
        spk = sum(sh["spikes_total"] for sh in s["shanks"])
        totals["ks4"] += ks4; totals["final"] += fin; totals["noise"] += noi; totals["cand"] += ncand; totals["lt3"] += nlt3; totals["lt3w"] += nlt3w; totals["ge3"] += nge3
        amp_c = [r["amp_uV"] for r in cand if r["amp_uV"] == r["amp_uV"]]
        L.append(f"| {s['animal']} | `{s['session']}` | {s['duration_s'] / 3600:.1f} | FM{s['firmware']} | {s['status']} | {len(s['shanks'])} | {ks4} | {fin} | {noi} | {ncand} | **{nlt3}** | {nlt3w} | {nge3} | {spk:,} | "
                 f"{np.nanmedian([r['rate_hz'] for r in cand]) if cand else float('nan'):.2f} | {np.nanmedian(amp_c) if amp_c else float('nan'):.0f} | "
                 f"{' '.join(map(str, s['bad_channels'])) or '-'} | {s['elapsed_min']:.0f} |")
    L.append(f"| **total** | | | | | | {totals['ks4']} | {totals['final']} | {totals['noise']} | {totals['cand']} | **{totals['lt3']}** | {totals['lt3w']} | {totals['ge3']} | | | | | |\n")
    L.append("## Per shank\n")
    L.append("| logger | shank | stage | KS4 units | final | good | mua | unsorted | noise | candidate | < 3 Hz | < 3 Hz & well-isolated | ≥ 3 Hz | spikes | median rate Hz | median amp µV | median SNR |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in sessions:
        for sh in s["shanks"]:
            cand = [r for r in sh["clusters"] if r["candidate"]]
            med = lambda k: (float(np.nanmedian([r[k] for r in cand])) if cand else float("nan"))
            L.append(f"| {s['animal']} | {sh['shank']} | {sh['stage']} | {sh['ks4_units']} | {sh['n_final']} | {sh['n_good']} | {sh['n_mua']} | {sh['n_unsorted']} | {sh['n_noise']} | {sh['n_candidate']} | {sh['n_lt3']} | {sh['n_lt3_well']} | {sh['n_ge3']} | "
                     f"{sh['spikes_total']:,} | {med('rate_hz'):.2f} | {med('amp_uV'):.0f} | {med('snr'):.1f} |")
    L.append("\n## Caveats\n")
    L.append("- Pre-curation numbers from one session per logger; Phy curation (merges/splits, the 'good' label) is still to be done, so treat `candidate` as an upper bound and `well-isolated` as a conservative lower bound.")
    L.append("- SF09's channel groups are data-derived (no geometry); SF08/10/11/12 use SF07's map provisionally; a wrong map lowers yield rather than inflating it.")
    L.append("- Amplitudes assume the Intan 0.195 µV/count scale (WILD gain not verified).")
    md_path.write_text("\n".join(L) + "\n", encoding="utf-8")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        animals = [s["animal"] for s in sessions]
        x = np.arange(len(animals)); wdt = 0.8
        bottom = np.zeros(len(animals))
        for label, key, col in (("< 3 Hz (hippocampal count)", "n_lt3", "#1f77b4"), (">= 3 Hz candidates", "n_ge3", "#9ecae1"), ("noise-labelled", "n_noise", "#d9d9d9")):
            vals = np.array([sum(sh[key] for sh in s["shanks"]) for s in sessions])
            axes[0].bar(x, vals, wdt, bottom=bottom, label=label, color=col); bottom += vals
        axes[0].set_xticks(x); axes[0].set_xticklabels(animals); axes[0].set_ylabel("clusters after postprocess"); axes[0].set_title("Kilosort4 yield per logger (one ~8-h FM65 session)"); axes[0].legend()
        for s in sessions:
            cand = [r for sh in s["shanks"] for r in sh["clusters"] if r["candidate"]]
            axes[1].scatter([r["rate_hz"] for r in cand], [r["amp_uV"] for r in cand], s=12, alpha=0.6, label=s["animal"])
        axes[1].set_xscale("log"); axes[1].set_xlabel("firing rate (Hz)"); axes[1].set_ylabel("median amplitude (µV, relative)"); axes[1].set_title("candidate units"); axes[1].legend(fontsize=8)
        fig.tight_layout()
        fp = fd / f"ephys_spikes_ks4_unit_yield_{a.cohort}.png"
        fig.savefig(fp, dpi=130); plt.close(fig)
        print(f"figure -> {fp}")
    except Exception as e:
        print(f"figure skipped: {e}")
    ar = analysis_root(a.cohort)
    if ar:
        (ar / "index").mkdir(parents=True, exist_ok=True)
        for p in (md_path, csv_path):
            (ar / "index" / p.name).write_bytes(p.read_bytes())
    print(f"report -> {md_path}\ncsv -> {csv_path}")


if __name__ == "__main__":
    main()
