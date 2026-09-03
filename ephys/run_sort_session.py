"""Run PreprocessPipeline (preprocess + Kilosort4 + postprocess) on ONE staged WILD session.

Wraps the lab's PreprocessPipeline (imported by path from ``ephys.preprocess_pipeline_root`` in the cohort YAML
or $PREPROCESS_PIPELINE_ROOT; run inside its ``preprocess`` conda env). Mirrors Run_preprocessSession.py:

    staged session  ->  chanMap.mat (probe groups from the staged XML)
                    ->  bandpass 500-8000 Hz + local CMR + per-shank high-amplitude artifact removal
                    ->  <basename>.dat / .lfp (1250 Hz) / .session.mat / MergePoints
                    ->  Kilosort4 (per shank by default; vendored sorter/Kilosort4, GPU)
                    ->  postprocess (duplicates, merge, autosplit, quality metrics, noise labels) -> Phy folder

Everything is written under <OUT_ROOT>/<cohort>/ephys_sort/<animal>/<session>/ (PreprocessPipeline's local
working dir); a ``sort_manifest.json`` records provenance, and one summary row is appended to
results/<cohort>/ephys_spikes/reports/ephys_spikes_sort_runs_<cohort>.csv.

Usage (from the `preprocess` env):
  python ephys/run_sort_session.py --cohort 2026c --animal SF8 --session 0_20260831_070148.859
        [--partition shank|all] [--no-sort] [--no-post] [--reference local|global|none] [--highamp shank|none]
        [--state-score] [--overwrite] [--n-jobs N]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from _common import PROJECT_ROOT, ephys_block, git_commit, report_dir, sort_root, stage_root, tools_root, utc_now_iso, write_json


def _pipeline_root(cfg: dict, override: str | None) -> Path:
    root = override or os.environ.get("PREPROCESS_PIPELINE_ROOT") or cfg.get("preprocess_pipeline_root")
    if not root:
        raise SystemExit("PreprocessPipeline root unknown: set ephys.preprocess_pipeline_root in the cohort YAML or $PREPROCESS_PIPELINE_ROOT")
    root = Path(root)
    if not (root / "src" / "preprocess").is_dir():
        raise SystemExit(f"not a PreprocessPipeline checkout: {root}")
    return root


def _norm_animal(animal: str) -> str:
    a = animal.upper()
    return f"SF{int(a[2:]):02d}" if a.startswith("SF") and a[2:].isdigit() else a


def _install_ks4_partition_shim() -> None:
    """Work around a PreprocessPipeline bug (2026-09-02, commit cb89e24) for Kilosort4 + probe/shank partitions.

    ``sorter_runner.execute_sorting_job`` sets ``params["bad_channels"]`` to the ignored channels in FULL-recording
    indices even when it then reduces the recording to the partition's channel subset. spikeinterface's KS4 wrapper
    numbers that subset 0..n-1, so Kilosort4 raises ``IndexError: Channel 'k' was not in probe['chanMap']``. In the
    subset case the ignored channels are already removed, so ``bad_channels`` must simply not be passed. The shim
    wraps ``spikeinterface.sorters.run_sorter`` and drops ``bad_channels`` when any index lies outside the recording
    (only possible for a subset). The proposed upstream fix is ephys/patches/preprocesspipeline-ks4-partition-bad-channels.patch;
    the pipeline checkout itself is left untouched.
    """
    import spikeinterface.sorters as ss
    if getattr(ss.run_sorter, "_field2026_ks4_shim", False):
        return
    original = ss.run_sorter

    def _close_log_handlers_under(folder) -> int:
        """Windows: Kilosort4 leaves its kilosort4.log FileHandler open, and PreprocessPipeline's
        _flatten_sorter_output_folder() then fails with WinError 32 when it moves the file. Close them."""
        import logging
        folder = str(Path(folder).resolve()).lower() if folder else None
        n = 0
        loggers = [logging.getLogger()] + [lg for lg in logging.Logger.manager.loggerDict.values() if isinstance(lg, logging.Logger)]
        for lg in loggers:
            for h in list(lg.handlers):
                base = getattr(h, "baseFilename", None)
                if base and (folder is None or str(Path(base).resolve()).lower().startswith(folder)):
                    try:
                        h.flush(); h.close()
                    except Exception:
                        pass
                    lg.removeHandler(h)
                    n += 1
        return n

    def run_sorter_shim(*args, **kwargs):
        bad = kwargs.get("bad_channels")
        rec = kwargs.get("recording", args[1] if len(args) > 1 else None)
        if bad and rec is not None and max(int(c) for c in bad) >= int(rec.get_num_channels()):
            print(f"[shim] sorter input is a {rec.get_num_channels()}-channel subset; dropping full-width bad_channels "
                  f"({len(bad)} entries already excluded from the recording)")
            kwargs["bad_channels"] = None
        folder = kwargs.get("folder") or kwargs.get("output_folder")
        try:
            return original(*args, **kwargs)
        finally:
            n = _close_log_handlers_under(folder)
            if n:
                print(f"[shim] closed {n} open log handler(s) under the sorter folder (Windows file-lock workaround)")

    run_sorter_shim._field2026_ks4_shim = True  # type: ignore[attr-defined]
    ss.run_sorter = run_sorter_shim


# Text patches applied to an OFF-REPO copy of the vendored Kilosort4 (the lab checkout is never modified).
# Each entry: (relative file, exact old text, new text, why). Proposed upstream diffs live in ephys/patches/.
KS4_TEXT_PATCHES = [
    (
        "kilosort/clustering_qr.py",
        "    amp = np.asarray(spike_amplitudes, dtype=np.float32)\n",
        "    amp = np.atleast_1d(np.asarray(spike_amplitudes, dtype=np.float32))\n",
        "lab amplitude feature: a one-spike group yields a 0-d array -> np.maximum returns a numpy scalar -> "
        "torch.from_numpy raises 'expected np.ndarray (got numpy.float64)' (seen on SF10 5_20260901_054403.494, 100 s, per-shank)",
    ),
]


def _prepare_patched_ks4(vendored: Path, tools_root: Path, *, refresh: bool = False) -> tuple[Path, list[str]]:
    """Copy PreprocessPipeline's vendored Kilosort4 to <tools_root>/Kilosort4_field2026 and apply KS4_TEXT_PATCHES.

    Returns (patched_path, applied_descriptions). The copy is rebuilt when missing, when --refresh-ks4 is given, or
    when the vendored source is newer than the copy's stamp file."""
    import shutil
    dst = tools_root / "Kilosort4_field2026"
    stamp = dst / ".field2026_ks4_stamp.json"
    src_mtime = max(p.stat().st_mtime for p in (vendored / "kilosort").rglob("*.py"))
    if dst.exists() and not refresh and stamp.exists():
        try:
            if json.loads(stamp.read_text())["source_mtime"] >= src_mtime:
                return dst, json.loads(stamp.read_text())["applied"]
        except Exception:
            pass
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(vendored, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "docs", "tests", ".github", "*.pyc"))
    applied = []
    for rel, old, new, why in KS4_TEXT_PATCHES:
        f = dst / rel
        s = f.read_text(encoding="utf-8")
        n = s.count(old)
        if n != 1:
            raise RuntimeError(f"KS4 patch target not unique in {f} (found {n}x): {old!r} — vendored Kilosort4 changed; update KS4_TEXT_PATCHES")
        f.write_text(s.replace(old, new, 1), encoding="utf-8")
        applied.append(f"{rel}: {why}")
    stamp.write_text(json.dumps({"source": str(vendored), "source_mtime": src_mtime, "applied": applied, "written_utc": utc_now_iso()}, indent=2))
    print(f"[ks4] patched copy -> {dst} ({len(applied)} patch(es))")
    return dst, applied


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--animal", required=True)
    ap.add_argument("--session", required=True)
    ap.add_argument("--staged-dir", default=None, help="override <OUT_ROOT>/<cohort>/ephys_stage/<animal>/<session>")
    ap.add_argument("--sort-root", default=None, help="override <OUT_ROOT>/<cohort>/ephys_sort")
    ap.add_argument("--pipeline-root", default=None)
    ap.add_argument("--sorter", default="kilosort4", choices=["kilosort4", "none"])
    ap.add_argument("--sorter-config", default=None, help="default ephys/configs/kilosort4_wild.yaml")
    ap.add_argument("--ks4-path", default=None, help="Kilosort4 package root to use (default: patched off-repo copy of the vendored one)")
    ap.add_argument("--refresh-ks4", action="store_true", help="rebuild the patched Kilosort4 copy")
    ap.add_argument("--partition", default="shank", choices=["all", "probe", "shank"])
    ap.add_argument("--reference", default="local", choices=["local", "global", "none"])
    ap.add_argument("--local-radius", type=float, nargs=2, default=(20.0, 200.0))
    ap.add_argument("--highamp", default="shank", choices=["none", "all", "probe", "shank"])
    ap.add_argument("--highamp-sigma", type=float, default=5.0)
    ap.add_argument("--bandpass", type=float, nargs=2, default=(500.0, 8000.0))
    ap.add_argument("--lfp-fs", type=float, default=1250.0)
    ap.add_argument("--state-score", action="store_true")
    ap.add_argument("--no-sort", action="store_true", help="preprocess only")
    ap.add_argument("--no-post", action="store_true", help="skip postprocess")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--n-jobs", type=int, default=None, help="default min(cpu-2, 16)")
    a = ap.parse_args()

    cfg = ephys_block(a.cohort)
    proot = _pipeline_root(cfg, a.pipeline_root)
    sys.path.insert(0, str(proot))
    os.chdir(proot)   # the pipeline resolves sorter/ paths relative to its repo root
    from src.preprocess import PreprocessConfig, prepare_chanmap, run_preprocess_session  # noqa: E402
    from src import PostprocessConfig, run_postprocess_session  # noqa: E402
    import yaml  # noqa: E402
    _install_ks4_partition_shim()

    animal = _norm_animal(a.animal)
    staged = Path(a.staged_dir) if a.staged_dir else stage_root(a.cohort, None) / animal / a.session
    basename = staged.name   # == session, or session__w<start>s_<dur>s for a windowed stage
    if not (staged / "amplifier.dat").exists() or not (staged / f"{basename}.xml").exists():
        raise SystemExit(f"session is not staged (run ephys/stage_session.py first): {staged}")
    import json
    stage_manifest = json.loads((staged / "stage_manifest.json").read_text(encoding="utf-8"))
    probe_cfg_path = PROJECT_ROOT / cfg.get("probe_config", f"ephys/configs/probes_{a.cohort}.yaml")
    probe_cfg = yaml.safe_load(probe_cfg_path.read_text(encoding="utf-8"))
    probe = probe_cfg["animals"][animal]
    n_groups_xml = len(probe["groups"]) + (1 if len({c for g in probe["groups"] for c in g}) < int(probe_cfg.get("n_channels", 64)) else 0)
    probe_assignments = [{"type": str(probe["layout"]), "groups": list(range(n_groups_xml)), "x_offset": 0}]

    local_parent = sort_root(a.cohort, a.sort_root) / animal
    local_output_dir = local_parent / basename
    local_output_dir.mkdir(parents=True, exist_ok=True)
    cpu = os.cpu_count() or 4
    n_jobs = a.n_jobs or max(1, min(cpu - 2, 16))
    sorter_config = Path(a.sorter_config) if a.sorter_config else PROJECT_ROOT / "ephys" / "configs" / "kilosort4_wild.yaml"
    ks4_patches: list[str] = []
    if a.ks4_path:
        ks4_path = Path(a.ks4_path)
    else:
        ks4_path, ks4_patches = _prepare_patched_ks4(proot / "sorter" / "Kilosort4", tools_root(a.cohort), refresh=a.refresh_ks4)

    t0 = time.time()
    chanmap_path, bad_from_chanmap = prepare_chanmap(basepath=staged, basename=basename, local_output_dir=local_output_dir,
                                                     probe_assignments=probe_assignments, reject_channels=[], xml_path=staged / f"{basename}.xml")
    print(f"chanMap: {chanmap_path}  bad (from XML skip): {bad_from_chanmap}")

    pre = PreprocessConfig(
        basepath=staged, localpath=local_parent, xml_path=staged / f"{basename}.xml",
        dtype=str(cfg.get("dtype", "int16")), gain_to_uV=float(cfg.get("gain_to_uV", 0.195)), offset_to_uV=0.0, save_raw=False,
        analog_inputs=False, digital_inputs=False, export_intermediate_dat=False,
        do_preprocess=True, bandpass_min_hz=a.bandpass[0], bandpass_max_hz=a.bandpass[1],
        reference=a.reference, local_radius_um=tuple(a.local_radius),
        artifact_ttl_group_mode="none",
        artifact_highamp_group_mode=a.highamp, highamp_estimate_windows=500, highamp_estimate_window_s=1.0,
        highamp_threshold_sigma=a.highamp_sigma, highamp_seed=0, highamp_chunk_s=1.0, highamp_dead_time_ms=1.0,
        highamp_n_jobs=n_jobs, highamp_ms_before=2.0, highamp_ms_after=2.0, highamp_mode="linear",
        make_lfp=True, lfp_fs=a.lfp_fs, state_score=a.state_score,
        chanmap_mat_path=chanmap_path, reject_channels=[],
        matlab_path=None, matlab_max_workers=n_jobs,
        sorter=None if (a.no_sort or a.sorter == "none") else "kilosort4",
        sorter_path=ks4_path, sorter_config_path=sorter_config, sorter_partition_mode=a.partition,
        overwrite=a.overwrite, save_params_json=True, save_manifest_json=True, save_log_mat=True,
        job_kwargs={"pool_engine": "process", "n_jobs": n_jobs, "chunk_duration": "1s", "progress_bar": True, "max_threads_per_worker": 1},
    )
    print(f"[run] preprocess{'' if pre.sorter else ' only'} -> {local_output_dir} (n_jobs={n_jobs}, partition={a.partition})")
    result = run_preprocess_session(pre)
    print(f"[run] preprocess done: dat={result.dat_path} lfp={result.lfp_path} bad={result.bad_channels_0based} sorter_dirs={result.sorter_output_dirs}")

    post_dirs: list[str] = []
    if pre.sorter and not a.no_post:
        post = PostprocessConfig(
            sorting_phy_folder=None, sorting_search_root=result.local_output_dir, recording=None,
            dat_path=result.dat_path, sampling_frequency=result.sr, num_channels=result.n_channels,
            dtype=pre.dtype, gain_to_uV=pre.gain_to_uV, offset_to_uV=pre.offset_to_uV, chanmap_mat_path=pre.chanmap_mat_path,
            reject_channels=result.bad_channels_0based, apply_preprocess=False,
            bandpass_min_hz=pre.bandpass_min_hz, bandpass_max_hz=pre.bandpass_max_hz, reference=pre.reference, local_radius_um=pre.local_radius_um,
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
            skip_pc_metrics=True, overwrite=a.overwrite, copy_binary=False, use_relative_path=True,
            job_kwargs={"n_jobs": n_jobs, "progress_bar": True},
        )
        print("[run] postprocess ...")
        post_results = run_postprocess_session(post)
        post_dirs = [str(r.output_folder) for r in post_results]
        print(f"[run] postprocess done: {post_dirs}")

    manifest = {
        "cohort": a.cohort, "animal": animal, "session": a.session, "basename": basename, "window_s": stage_manifest.get("window_s"),
        "staged_dir": str(staged), "local_output_dir": str(result.local_output_dir),
        "stage_manifest": stage_manifest, "pipeline_root": str(proot), "pipeline_git": git_commit(proot), "repo_git": git_commit(),
        "preprocess_config": {k: (str(v) if isinstance(v, Path) else v) for k, v in asdict(pre).items()},
        "sorter_config_path": str(sorter_config), "kilosort4_path": str(ks4_path), "kilosort4_patches_applied": ks4_patches,
        "probe_assignments": probe_assignments, "probe_verified": bool(probe_cfg.get("verified", False)),
        "result": {"dat_path": str(result.dat_path), "lfp_path": str(result.lfp_path), "n_channels": result.n_channels, "sr": result.sr,
                   "bad_channels_0based": result.bad_channels_0based, "sorter": result.sorter,
                   "sorter_output_dirs": [str(p) for p in result.sorter_output_dirs], "postprocess_dirs": post_dirs,
                   "subsession_sample_counts": result.subsession_sample_counts},
        "elapsed_s": time.time() - t0, "written_utc": utc_now_iso(), "script": "ephys/run_sort_session.py",
    }
    write_json(local_output_dir / "sort_manifest.json", manifest)
    runs_csv = report_dir(a.cohort, cfg.get("direction", "ephys_spikes")) / f"ephys_spikes_sort_runs_{a.cohort}.csv"
    new = not runs_csv.exists()
    with open(runs_csv, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["written_utc", "animal", "session", "firmware", "deglitched", "partition", "sorter", "n_sorter_dirs", "n_post_dirs",
                        "bad_channels", "elapsed_s", "local_output_dir", "repo_git"])
        w.writerow([manifest["written_utc"], animal, basename, stage_manifest.get("header", {}).get("firmware_version"),
                    stage_manifest.get("deglitch_applied"), a.partition, result.sorter, len(result.sorter_output_dirs), len(post_dirs),
                    " ".join(map(str, result.bad_channels_0based)), round(manifest["elapsed_s"], 1), str(result.local_output_dir), manifest["repo_git"]])
    print(f"[run] manifest -> {local_output_dir / 'sort_manifest.json'}\n[run] runs table -> {runs_csv}\n[run] elapsed {manifest['elapsed_s'] / 60:.1f} min")


if __name__ == "__main__":
    main()
