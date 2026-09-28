"""Do the accepted units of a sorted session have physiological spike waveforms, or one-sample-wide defect residue?

Step 2 of implementation_plan/2026-09-07-fm64-salvage-test.md. The FM64 substitution defect (defect A) puts ONE sample of a
donor channel into the victim channel; the 5-point-median de-glitch removes ~99.9 % of them, but a residue survives whenever
the donor-victim offset is below the replacement threshold. After the 500-8000 Hz band-pass such a residue is a single-sample
impulse, and a Kilosort4 template built on it is one sample wide, unlike a real extracellular spike (trough ~0.2-0.4 ms
= 4-8 samples at 20 kHz, plus a repolarisation lobe).

Metric per unit, on its Phy template (templates.npy of the *_spi folder, peak channel = largest peak-to-peak):
    fwhm_samples    width of the dominant (trough or peak) deflection at half its amplitude, in samples
    lobes           number of sign changes of the template around the dominant deflection (a real spike has >= 1:
                    trough followed by repolarisation)
    one_sample      fwhm_samples <= 1.5 AND the neighbouring samples are below 30 % of the peak -> defect residue
The session fails the plan's criterion if any ACCEPTED unit (cluster_group.tsv != noise) is one_sample.

Usage: python ephys/template_width_check.py --cohort 2026c --animal SF10 --session 1_20260901_080143.036 [--all]
Writes results/<cohort>/ephys_spikes/reports/ephys_spikes_template_width_<cohort>.csv (one row per session, appended).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import git_commit, report_dir, sort_root, utc_now_iso  # noqa: E402


def read_group(spi: Path) -> dict[int, str]:
    p = spi / "cluster_group.tsv"
    out: dict[int, str] = {}
    if not p.exists():
        return out
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            k = list(r.keys())
            try:
                out[int(r[k[0]])] = str(r[k[1]]).strip()
            except (ValueError, IndexError):
                pass
    return out


def template_stats(t: np.ndarray) -> dict:
    """t = (n_samples, n_channels) template of one unit."""
    ptp = t.max(0) - t.min(0)
    ch = int(np.argmax(ptp))
    w = t[:, ch].astype(np.float64)
    i = int(np.argmax(np.abs(w)))
    amp = w[i]
    half = abs(amp) / 2.0
    lo = i
    while lo > 0 and abs(w[lo - 1]) >= half and np.sign(w[lo - 1]) == np.sign(amp):
        lo -= 1
    hi = i
    while hi < len(w) - 1 and abs(w[hi + 1]) >= half and np.sign(w[hi + 1]) == np.sign(amp):
        hi += 1
    fwhm = hi - lo + 1
    neigh = max(abs(w[max(0, i - 1)]), abs(w[min(len(w) - 1, i + 1)])) / max(abs(amp), 1e-9)
    seg = w[max(0, i - 20):min(len(w), i + 21)]
    lobes = int(np.sum(np.diff(np.sign(seg[np.abs(seg) > 0.15 * abs(amp)])) != 0))
    return {"peak_channel": ch, "ptp": float(ptp[ch]), "fwhm_samples": int(fwhm), "neighbour_ratio": float(neigh),
            "lobes": lobes, "one_sample": bool(fwhm <= 1.5 and neigh < 0.30)}


def scan_session(sdir: Path) -> dict | None:
    rows = []
    for spi in sorted(p for p in sdir.glob("Kilosort4_*_spi") if p.is_dir() and ".preserved-" not in p.name):
        tp = spi / "templates.npy"
        if not tp.exists():
            continue
        T = np.load(tp)                                   # (n_units, n_samples, n_channels)
        ids = np.load(spi / "spike_templates.npy").ravel() if (spi / "spike_templates.npy").exists() else None
        groups = read_group(spi)
        clu = np.load(spi / "spike_clusters.npy").ravel() if (spi / "spike_clusters.npy").exists() else None
        # map template index -> the cluster it mostly belongs to (postprocess renumbers clusters)
        tmpl_cluster: dict[int, int] = {}
        if ids is not None and clu is not None and ids.size == clu.size:
            for ti in np.unique(ids):
                vals, cnts = np.unique(clu[ids == ti], return_counts=True)
                tmpl_cluster[int(ti)] = int(vals[int(np.argmax(cnts))])
        m = re.search(r"_shank(\d+)_spi$", spi.name)
        for ti in range(T.shape[0]):
            cid = tmpl_cluster.get(ti, ti)
            st = template_stats(T[ti])
            st.update({"shank": int(m.group(1)) if m else 0, "template": ti, "cluster": cid,
                       "group": groups.get(cid, "unsorted"), "accepted": groups.get(cid, "unsorted") != "noise"})
            rows.append(st)
    return {"units": rows} if rows else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--animal", default=None); ap.add_argument("--session", default=None)
    ap.add_argument("--all", action="store_true", help="every sorted session of the cohort")
    ap.add_argument("--sort-root", default=None); ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    root = sort_root(a.cohort, a.sort_root)
    if a.all:
        sessions = [(p.parent.name, p.name, p) for p in sorted(root.glob("*/*")) if p.is_dir() and (p / "sort_manifest.json").exists()]
    else:
        if not (a.animal and a.session):
            raise SystemExit("give --animal and --session, or --all")
        an = a.animal.upper(); an = f"SF{int(an[2:]):02d}" if an.startswith("SF") and an[2:].isdigit() else an
        sessions = [(an, a.session, root / an / a.session)]
    out_rows = []
    for animal, session, sdir in sessions:
        res = scan_session(sdir)
        if not res:
            print(f"{animal} {session}: no Phy templates found"); continue
        u = res["units"]; acc = [r for r in u if r["accepted"]]
        bad = [r for r in acc if r["one_sample"]]
        fw = json.loads((sdir / "sort_manifest.json").read_text(encoding="utf-8")).get("stage_manifest", {}).get("header", {}).get("firmware_version") if (sdir / "sort_manifest.json").exists() else None
        fwhm = np.array([r["fwhm_samples"] for r in acc], dtype=float)
        print(f"== {animal} {session} (FM{fw}): {len(u)} templates, {len(acc)} accepted; FWHM samples median {np.median(fwhm):.1f} "
              f"(p5 {np.percentile(fwhm, 5):.0f}, min {fwhm.min():.0f}); lobes>=1 in {100 * np.mean([r['lobes'] >= 1 for r in acc]):.0f} % "
              f"of accepted; ONE-SAMPLE accepted units: {len(bad)}")
        if bad:
            for r in bad[:10]:
                print(f"   shank {r['shank']} cluster {r['cluster']} ch {r['peak_channel']} ptp {r['ptp']:.0f} fwhm {r['fwhm_samples']} neigh {r['neighbour_ratio']:.2f}")
        out_rows.append({"written_utc": utc_now_iso(), "animal": animal, "session": session, "firmware": fw, "n_templates": len(u),
                         "n_accepted": len(acc), "fwhm_median": round(float(np.median(fwhm)), 2), "fwhm_p5": round(float(np.percentile(fwhm, 5)), 2),
                         "fwhm_min": int(fwhm.min()), "frac_with_repolarisation": round(float(np.mean([r["lobes"] >= 1 for r in acc])), 4),
                         "n_one_sample_accepted": len(bad), "repo_git": git_commit()})
    if out_rows and not a.no_write:
        p = report_dir(a.cohort) / f"ephys_spikes_template_width_{a.cohort}.csv"
        new = not p.exists()
        with open(p, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0]))
            if new:
                w.writeheader()
            w.writerows(out_rows)
        print(f"-> {p}")


if __name__ == "__main__":
    main()
