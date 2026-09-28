"""Re-sort SELECTED shanks of an already-sorted session with a new channel-map XML, re-using the preprocessed .dat.

Use case (SF10, 2026-09-06): the connector-mating test found SF10 plugged as A180 (probe_map_check / footprint_map_check).
Under A180 the four column SETS per shank are the same as under SF07's map (only the shank labels 2<->3 swap), but the site
ORDER inside those two shanks changes, so their Kilosort4 runs (spatial templates, drift, Phy layout) must be redone while
the other shanks are untouched. A full re-run (preprocess 4 h + Kilosort4 9 h on SF10's noisy shank) does not fit between
the daily card offloads; this tool does Kilosort4 for the selected shanks only (~1-3 h) plus the postprocess.

What it does
  1. copies the new XML into the sort folder (old XML / chanMap.mat kept as *.pre-<tag>-<ts>) and rebuilds chanMap.mat;
  2. builds the shank partitions from the new chanMap (same PreprocessPipeline code as run_sort_session.py);
  3. moves the previous Kilosort4 folders (+ _spi) of the selected shank ids to <sort_root>/<animal>/_superseded/<session>/<tag>_<ts>/;
  4. runs Kilosort4 on each selected partition (execute_sorting_job with input_is_preprocessed=True on the existing .dat);
  5. re-runs the postprocess for every Kilosort4 folder of the session (fast mode by default), so all shanks share one pass;
  6. appends a `resorts` entry to sort_manifest.json and a row to the runs CSV.

CAVEAT recorded in the manifest: the .dat is NOT regenerated. Its local CMR (20-200 um) used the OLD site positions for the
re-sorted shanks, i.e. a slightly different within-shank neighbour subset for the median reference; band-pass and the
per-shank high-amplitude artifact removal are order-independent. Re-run run_sort_session.py --overwrite for a clean pass.

Usage (preprocess env):
  python ephys/resort_shanks.py --cohort 2026c --animal SF10 --session 9_20260902_083247.835 --shanks 2 3 [--tag A180]
        [--xml <path, default the staged <session>.xml>] [--dry-run] [--no-post] [--post-full] [--n-jobs N]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PROJECT_ROOT, ephys_block, git_commit, report_dir, sort_root, stage_root, tools_root, utc_now_iso, write_json  # noqa: E402
import run_sort_session as rss  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True); ap.add_argument("--animal", required=True); ap.add_argument("--session", required=True)
    ap.add_argument("--shanks", type=int, nargs="+", required=True, help="shank ids (1-based, as in the Kilosort4 folder names) to re-sort")
    ap.add_argument("--xml", default=None, help="new XML (default: the staged <session>.xml)")
    ap.add_argument("--tag", default="resort")
    ap.add_argument("--pipeline-root", default=None); ap.add_argument("--sort-root", default=None)
    ap.add_argument("--n-jobs", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="list partitions and what would be superseded, then exit")
    ap.add_argument("--post-only", action="store_true",
                    help="skip Kilosort4: only rewrite sorter_partition_manifest.json from the folders on disk and re-run the postprocess "
                         "(repairs a session whose re-sort postprocessed the wrong folders)")
    ap.add_argument("--no-post", action="store_true"); ap.add_argument("--post-full", action="store_true"); ap.add_argument("--post-max-spikes", type=int, default=500)
    a = ap.parse_args()
    if a.xml:
        a.xml = str(Path(a.xml).resolve())   # resolve before the chdir into the pipeline root

    cfg = ephys_block(a.cohort)
    proot = rss._pipeline_root(cfg, a.pipeline_root)
    sys.path.insert(0, str(proot)); os.chdir(proot)
    from src.preprocess import prepare_chanmap  # noqa: E402
    from src.preprocess.sorter_runner import build_sorter_partitions, execute_sorting_job, write_sorter_partition_manifest  # noqa: E402
    from src import PostprocessConfig, run_postprocess_session  # noqa: E402
    import yaml  # noqa: E402
    rss._install_ks4_partition_shim()

    animal = rss._norm_animal(a.animal)
    sdir = sort_root(a.cohort, a.sort_root) / animal / a.session
    staged = stage_root(a.cohort, None) / animal / a.session
    basename = a.session
    xml_src = Path(a.xml) if a.xml else staged / f"{basename}.xml"
    pm_path = sdir / "preprocessSession_manifest.json"
    if not pm_path.exists():
        raise SystemExit(f"not a sorted session (no preprocessSession_manifest.json): {sdir}")
    if not xml_src.exists():
        raise SystemExit(f"XML not found: {xml_src}")
    pm = json.loads(pm_path.read_text(encoding="utf-8"))
    dat = Path(pm["dat_path"]); n_ch = int(pm["n_channels"]); sr = float(pm["sr"]); bad = [int(c) for c in (pm.get("bad_channels_0based") or [])]
    if not dat.exists():
        raise SystemExit(f"preprocessed .dat missing: {dat}")
    probe_cfg = yaml.safe_load((PROJECT_ROOT / cfg.get("probe_config", f"ephys/configs/probes_{a.cohort}.yaml")).read_text(encoding="utf-8"))
    layout = str(probe_cfg["animals"][animal]["layout"])
    n_groups = len(ET.parse(xml_src).getroot().findall("anatomicalDescription/channelGroups/group"))
    probe_assignments = [{"type": layout, "groups": list(range(n_groups)), "x_offset": 0}]
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    t0 = time.time()

    # 1. XML + chanMap in the sort folder
    if not a.dry_run:
        for name in (f"{basename}.xml", "chanMap.mat"):
            p = sdir / name
            if p.exists():
                shutil.copy2(p, sdir / f"{name}.pre-{a.tag}-{ts}")
        shutil.copy2(xml_src, sdir / f"{basename}.xml")
        chanmap_path, bad_from_xml = prepare_chanmap(basepath=staged, basename=basename, local_output_dir=sdir, probe_assignments=probe_assignments,
                                                     reject_channels=[], xml_path=sdir / f"{basename}.xml")
    else:
        tmp = sdir / f"_dryrun_chanmap_{ts}"; tmp.mkdir(exist_ok=True)
        chanmap_path, bad_from_xml = prepare_chanmap(basepath=staged, basename=basename, local_output_dir=tmp, probe_assignments=probe_assignments,
                                                     reject_channels=[], xml_path=xml_src)
    print(f"chanMap from {xml_src.name}: {chanmap_path} (skip from XML: {bad_from_xml}); excluded (preprocess manifest): {bad}")

    # 2. partitions
    parts = build_sorter_partitions(mode="shank", chanmap_mat_path=chanmap_path, num_channels=n_ch, excluded_channels_0based=bad)
    sel = [p for p in parts if p.shank_id in set(a.shanks)]
    for p in parts:
        print(f"  partition {p.name}: {len(p.channels_0based)} ch {p.channels_0based}{'   <== re-sort' if p in sel else ''}")
    if not sel:
        raise SystemExit(f"no partition matches --shanks {a.shanks}")
    old = {p.shank_id: sorted(f for f in sdir.glob(f"Kilosort4_*_probe{p.probe_id}_shank{p.shank_id}*") if f.is_dir()) for p in sel}
    # folders of shanks that no longer exist in the new chanMap (all their channels rejected, e.g. SF10 shank 1 = dead) are superseded too
    live_ids = {p.shank_id for p in parts}
    for f in sorted(sdir.glob("Kilosort4_*_probe*_shank*")):
        m = re.search(r"_shank(\d+)(_spi)?$", f.name)
        if f.is_dir() and m and int(m.group(1)) not in live_ids:
            old.setdefault(int(m.group(1)), []).append(f)
    for sid, fs in old.items():
        print(f"  shank {sid}: superseding {[f.name for f in fs]}" + ("" if sid in live_ids else "   (no partition left for this shank: all channels rejected)"))
    if a.dry_run:
        shutil.rmtree(tmp, ignore_errors=True)
        print("dry run: nothing changed"); return

    # 3. supersede
    sup = sort_root(a.cohort, a.sort_root) / animal / "_superseded" / a.session / f"{a.tag}_{ts}"
    if not a.post_only:
        sup.mkdir(parents=True, exist_ok=True)
        for fs in old.values():
            for f in fs:
                shutil.move(str(f), str(sup / f.name))

    # 4. Kilosort4 on the selected partitions
    ks4_path, ks4_patches = rss._prepare_patched_ks4(proot / "sorter" / "Kilosort4", tools_root(a.cohort))
    sorter_config = PROJECT_ROOT / "ephys" / "configs" / "kilosort4_wild.yaml"
    cpu = os.cpu_count() or 4
    n_jobs = a.n_jobs or max(1, min(cpu - 2, 16))
    job_kwargs = {"pool_engine": "process", "n_jobs": n_jobs, "chunk_duration": "1s", "progress_bar": True, "max_threads_per_worker": 1}
    new_dirs = []
    for p in (() if a.post_only else sel):
        out = sdir / f"Kilosort4_{ts}_probe{p.probe_id}_shank{p.shank_id}"
        print(f"[resort] Kilosort4 {p.name}: {len(p.channels_0based)} channels -> {out}")
        execute_sorting_job(sorter="kilosort4", dat_path=dat, xml_path=sdir / f"{basename}.xml", output_folder=out, config_path=sorter_config,
                            kilosort4_path=ks4_path, chanmap_mat_path=chanmap_path, dtype="int16", gain_to_uV=float(cfg.get("gain_to_uV", 0.195)), offset_to_uV=0.0,
                            sampling_frequency=sr, num_channels=n_ch, active_channels_0based=p.channels_0based, exclude_channels_0based=bad,
                            job_kwargs=job_kwargs, remove_existing_folder=True, preprocess_for_sorting=False, input_is_preprocessed=True,
                            bandpass_min_hz=500.0, bandpass_max_hz=8000.0, reference="local", local_radius_um=(20.0, 200.0),
                            sorter_verbose=False, cleanup_temp_wh=True)
        new_dirs.append(str(out))
    print(f"[resort] Kilosort4 done: {new_dirs} ({(time.time() - t0) / 60:.1f} min)")

    # 4b. rewrite sorter_partition_manifest.json from the folders NOW on disk. PreprocessPipeline's postprocess prefers this
    # manifest over a directory scan (`_find_sorting_output_dirs_from_manifest`), so a stale one silently postprocesses the old
    # folders only — seen on the SF10 A180 re-sort 2026-09-08 (only shank 4, the untouched folder, was postprocessed).
    from dataclasses import replace as _dc_replace
    mf_old = sdir / "sorter_partition_manifest.json"
    if mf_old.exists():
        shutil.copy2(mf_old, sdir / f"sorter_partition_manifest.json.pre-{a.tag}-{ts}")
    manifest_parts = []
    for p in parts:
        cands = sorted((f for f in sdir.glob(f"Kilosort4_*_probe{p.probe_id}_shank{p.shank_id}")
                        if f.is_dir() and "_spi" not in f.name and ".preserved-" not in f.name),
                       key=lambda f: f.stat().st_mtime, reverse=True)
        if not cands:
            print(f"[resort] WARNING: no Kilosort4 folder for {p.name}; left out of the manifest")
            continue
        manifest_parts.append(_dc_replace(p, output_folder=str(cands[0]), status="completed"))
    write_sorter_partition_manifest(output_dir=sdir, mode="shank", sorter="kilosort4", partitions=manifest_parts)
    print("[resort] partition manifest -> " + ", ".join(Path(p.output_folder).name for p in manifest_parts))

    # 5. postprocess every Kilosort4 folder of the session (one consistent pass)
    post_dirs: list[str] = []
    post_mode = "skipped" if a.no_post else ("full" if a.post_full else "fast")
    if not a.no_post:
        if post_mode == "fast":
            rss._install_fast_postprocess_shim(a.post_max_spikes)
        post = PostprocessConfig(
            sorting_phy_folder=None, sorting_search_root=sdir, recording=None,
            dat_path=dat, sampling_frequency=sr, num_channels=n_ch, dtype="int16", gain_to_uV=float(cfg.get("gain_to_uV", 0.195)), offset_to_uV=0.0,
            chanmap_mat_path=chanmap_path, reject_channels=bad, apply_preprocess=False,
            bandpass_min_hz=500.0, bandpass_max_hz=8000.0, reference="local", local_radius_um=(20.0, 200.0),
            exclude_cluster_groups=["noise"], duplicate_censored_period_ms=0.5, duplicate_threshold=0.5, remove_strategy="max_spikes",
            analyzer_format="binary_folder", analyzer_cache_dir=None, delete_analyzer_cache=True, skip_curation=False,
            merge_min_spikes=100, merge_corr_diff_thresh=0.25, merge_template_diff_thresh=0.25, merge_sparsity_overlap=0.5, merge_censor_ms=0.5,
            split_contamination=0.05, split_threshold_mode="adaptive_chi2", split_min_clean_frac=0.9, split_relax_factor=0.5,
            split_use_waveform_gate=True, split_wf_threshold=0.2, split_wf_template_max=1000, split_wf_n_chans=10, split_wf_center="demean",
            split_amp_mad_scale=10.0, split_squeeze_all_outlier_to_new=True, split_min_spikes=10, split_verbose=True,
            metric_names=["firing_rate", "isi_violation", "presence_ratio", "snr", "amplitude_median"],
            template_metric_names=["peak_to_valley", "peak_trough_ratio", "half_width", "repolarization_slope", "recovery_slope"],
            noise_thresholds={"isi_violations_ratio_gt": 5.0, "isi_violations_count_gt": 50.0, "presence_ratio_lt": 0.1, "snr_lt": 2.0,
                              "amplitude_median_lt": 15.0, "amplitude_median_gt": 500.0, "firing_rate_lt": 0.01},
            skip_pc_metrics=True, overwrite=True, copy_binary=False, use_relative_path=True,
            job_kwargs={"n_jobs": n_jobs, "progress_bar": True},
        )
        print("[resort] postprocess (all Kilosort4 folders of the session) ...")
        post_dirs = [str(r.output_folder) for r in run_postprocess_session(post)]
        print(f"[resort] postprocess done: {post_dirs}")

    # 6. manifests
    mf = sdir / "sort_manifest.json"
    man = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {"cohort": a.cohort, "animal": animal, "session": a.session, "basename": basename}
    entry = {"tag": a.tag, "timestamp": ts, "post_only": bool(a.post_only), "xml": str(xml_src), "shanks": a.shanks, "partitions": [{"name": p.name, "channels_0based": p.channels_0based} for p in sel],
             "kilosort4_dirs": new_dirs, "superseded_dir": str(sup), "postprocess_dirs": post_dirs, "post_mode": post_mode,
             "post_max_spikes_per_unit": (a.post_max_spikes if post_mode == "fast" else None), "kilosort4_patches_applied": ks4_patches,
             "caveat": "preprocessed .dat reused: its local CMR neighbourhoods on the re-sorted shanks follow the OLD site order",
             "elapsed_s": time.time() - t0, "written_utc": utc_now_iso(), "repo_git": git_commit(), "script": "ephys/resort_shanks.py"}
    man.setdefault("resorts", []).append(entry)
    man["post_mode"] = post_mode; man["post_max_spikes_per_unit"] = entry["post_max_spikes_per_unit"]
    res = man.setdefault("result", {})
    keep = [d for d in (res.get("sorter_output_dirs") or []) if Path(d).exists()]
    res["sorter_output_dirs"] = keep + new_dirs; res["postprocess_dirs"] = post_dirs
    write_json(mf, man)
    runs_csv = report_dir(a.cohort, cfg.get("direction", "ephys_spikes")) / f"ephys_spikes_sort_runs_{a.cohort}.csv"
    with open(runs_csv, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([entry["written_utc"], animal, basename, "", "", f"shank (resort {' '.join(map(str, a.shanks))}, {a.tag})", "kilosort4",
                                len(new_dirs), len(post_dirs), " ".join(map(str, bad)), round(entry["elapsed_s"], 1), str(sdir), entry["repo_git"]])
    print(f"[resort] manifest -> {mf}\n[resort] elapsed {entry['elapsed_s'] / 60:.1f} min")


if __name__ == "__main__":
    main()
