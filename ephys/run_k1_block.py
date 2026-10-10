"""Run Kilosort1 (PreprocessPipeline's KiloSort1) with the LAB settings on one block .dat, locally or on BioHPC.

Lab settings = neurocode spikeSorting/KilosortWrapper/KilosortConfiguration.m:
- the whole probe (all channels) in one K1 run;
- criterionNoiseChannels 1e-5 (every template confined to the shank of its peak channel, mainLoop/zeroOutKcoords.m);
- whiteningRange 64;
- Nfilt 8 x channels; Th [6 10 10]; lam [12 40 40]; ForceMaxRAMforDat 15e9 (the pipeline config has all of these).

PreprocessPipeline leaves criterionNoiseChannels unset, and its runner then writes 0.2 (20 % of templates may span
shanks). Since 09-30 it uses whiteningRange 32. Both are overridden here.

Full width: whole-probe runs read all channels of the .dat, as the lab wrapper does, and K1 drops dead channels
through chanMap `connected`. The pipeline would otherwise write a channel-subset copy whenever a channel is dead
(--subset-copy restores that).

Our deviations from the lab, none of which changes the algorithm:
- NT = 32*1024+ntbuff: the lab's 32*1028 leaves 128 samples of every batch unscanned, because the CUDA kernels launch
  NT/1024 blocks.
- parfor off and no MATLAB process pool. K1 uses parfor only in decompose_dWU.m, and 2 local runs hung while the
  pool started.
- delete_recording_dat, which removes spikeinterface's channel-subset copy after the sort.
- A patched copy of K1 in <tools-root>/KiloSort1_field2026: fullMPMU.m preallocates the spike table and doubles
  cProj/cProjPC instead of growing them every batch (the original is quadratic in the spike count). The output is
  meant to be identical; check it with --compare.

Output: <out>/chanMap.mat, k1_config_used.yaml, kilosort1/ (Phy folder) and k1_run.json.

Usage, in PreprocessPipeline's environment (local: <pipeline>/.venv; server: /home/hc997/src/PreprocessPipeline/.venv):
  python ephys/run_k1_block.py --cohort 2026c --animal SF10 --dat <block>.dat --out <dir>
         [--xml <xml>] [--disconnect CH ...] [--whitening-range 64|32] [--partition all|shank]
         [--crit 1e-5] [--unpatched] [--keep-matlab-files] [--pipeline-root P] [--tools-root T] [--matlab M]
  python ephys/run_k1_block.py --compare <phy folder A> <phy folder B>   # byte comparison of two K1 outputs
  python ephys/run_k1_block.py --selftest                                 # patches apply, config builds (no MATLAB)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PROJECT_ROOT, ephys_block, git_commit, tools_root, utc_now_iso, write_json  # noqa: E402
from make_session_xml import load_probe, write_session_xml_for_animal  # noqa: E402

LAB_CRIT = 1e-5
KS1_DIRNAME = "KiloSort1_field2026"
# (file, old text, new text, why); each old text must occur exactly once in the pipeline's copy.
KS1_TEXT_PATCHES = [
    ("fullMPMU.m", "\nst3 = [];",
     "\nst3 = zeros(5e6, 4);  % field2026 patch: preallocated (was [] grown by cat every batch)",
     "preallocate st3"),
    ("fullMPMU.m", "    if ~isempty(st)",
     "    if ~isempty(st)\n        [st3, rez] = field2026_grow(st3, rez, irun, numel(st), ops);  % field2026 patch",
     "grow st3 / cProj / cProjPC by doubling"),
    ("fullMPMU.m", "        st3             = cat(1, st3, STT);",
     "        st3(irun - numel(st) + (1:numel(st)), :) = STT;  % field2026 patch (irun already counts these spikes)",
     "fill st3 in place"),
    ("fullMPMU.m", "toc, ibatch,Nbatch, size(st3,1));",
     "toc, ibatch,Nbatch, irun);  % field2026 patch: spike count, not the preallocated size",
     "progress line counts spikes"),
    ("fullMPMU.m", "[~, isort]      = sort(st3(:,1), 'ascend');",
     "st3 = st3(1:irun, :);  % field2026 patch: trim the preallocation\n[~, isort]      = sort(st3(:,1), 'ascend');",
     "trim st3 before sorting"),
    # zeroOutKcoords.m averages each template's amplitude per channel group 1..max(kcoords). A group with no connected
    # channel (a dead shank, e.g. SF10 shank 1, or SF12 shanks switched off per block) gives mean([]) = NaN, which
    # makes every template's nEffective NaN, so no template is confined to its shank whatever criterionNoiseChannels
    # is. An empty group now contributes 0.
    ("mainLoop/zeroOutKcoords.m", "    aUgroups(j, :) = mean(aU(kcoords==j,:), 1);",
     "    if any(kcoords==j), aUgroups(j, :) = mean(aU(kcoords==j,:), 1); end  % field2026 patch: empty (all-dead) "
     "group gave NaN and disabled the shank confinement",
     "zeroOutKcoords: empty channel groups contribute 0, not NaN"),
]
GROW_HELPER = """function [st3, rez] = field2026_grow(st3, rez, irun, nNew, ops)
% field2026 patch for fullMPMU.m (Field2026_Social_analysis, ephys/run_k1_block.py): make room for nNew more spikes
% by doubling the spike table st3 and the projection arrays rez.cProj / rez.cProjPC, instead of reallocating them
% every batch. Values and their order are unchanged.
need = irun + nNew;
if need > size(st3, 1)
    st3(max(2 * size(st3, 1), need), size(st3, 2)) = 0;
end
if ~isempty(ops.nNeigh) && isfield(rez, 'cProj') && need > size(rez.cProj, 1)
    rez.cProj(max(2 * size(rez.cProj, 1), need), size(rez.cProj, 2)) = 0;
end
if ~isempty(ops.nNeighPC) && isfield(rez, 'cProjPC') && need > size(rez.cProjPC, 1)
    rez.cProjPC(max(2 * size(rez.cProjPC, 1), need), size(rez.cProjPC, 2)) = 0;
end
end
"""


def default_pipeline_root() -> Path:
    env = os.environ.get("PREPROCESS_PIPELINE_ROOT")
    if env:
        return Path(env)
    for cand in (ephys_block("2026c").get("preprocess_pipeline_root"), "D:/Documents/ayalab/PreprocessPipeline"):
        if cand and Path(cand).exists():
            return Path(cand)
    raise SystemExit("PreprocessPipeline not found: pass --pipeline-root or set PREPROCESS_PIPELINE_ROOT")


def default_matlab() -> str:
    if os.environ.get("MATLAB_CMD"):
        return os.environ["MATLAB_CMD"]
    if platform.system() == "Windows":
        return "D:/Program/Matlab/R2021b/bin/matlab.exe"
    return "/local/workdir/hc997/MATLAB/bin/matlab"   # wrapper adding -licmode onlinelicensing (Cornell TAH)


# Test only (--test-small-prealloc): start the preallocations at 1,000 rows, so that a short window exercises the
# doubling in field2026_grow.m many times. Its output must equal the unpatched run's.
SMALL_PREALLOC_PATCHES = [
    ("fullMPMU.m", "st3 = zeros(5e6, 4);", "st3 = zeros(1000, 4);", "TEST: st3 starts at 1000 rows"),
    ("fullMPMU.m", "rez.cProj = zeros(5e6, nNeigh, 'single');", "rez.cProj = zeros(1000, nNeigh, 'single');",
     "TEST: cProj starts at 1000 rows"),
    ("fullMPMU.m", "rez.cProjPC = zeros(5e6, 3*nNeighPC, 'single');", "rez.cProjPC = zeros(1000, 3*nNeighPC, 'single');",
     "TEST: cProjPC starts at 1000 rows"),
]


def prepare_patched_ks1(pipeline_root: Path, tools: Path, *, refresh: bool = False,
                        small_prealloc_test: bool = False) -> tuple[Path, list[str]]:
    """Copy <pipeline>/sorter/KiloSort1 (incl. its compiled mex) to <tools>/KiloSort1_field2026 and apply the patches."""
    src = pipeline_root / "sorter" / "KiloSort1"
    dst = tools / (KS1_DIRNAME + ("_smallprealloc_TEST" if small_prealloc_test else ""))
    stamp = dst / ".field2026_ks1_stamp.json"
    src_sig = hashlib.sha256((src / "fullMPMU.m").read_bytes() + (src / "mainLoop" / "zeroOutKcoords.m").read_bytes()).hexdigest()
    patches = KS1_TEXT_PATCHES + (SMALL_PREALLOC_PATCHES if small_prealloc_test else [])
    patch_sig = hashlib.sha256((repr(patches) + GROW_HELPER).encode("utf-8")).hexdigest()
    mex = sorted(p.name for p in (src / "CUDA").glob("*.mex*"))
    if dst.exists() and stamp.exists() and not refresh:
        st = json.loads(stamp.read_text())
        if st.get("source_sha256") == src_sig and st.get("patch_sha256") == patch_sig and st.get("mex") == mex:
            return dst, st["applied"]
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "*.asv"))
    applied = []
    for rel, old, new, why in patches:
        f = dst / rel
        s = f.read_bytes().decode("utf-8")
        n = s.count(old)
        if n != 1:
            raise RuntimeError(f"KS1 patch target not unique in {f} (found {n}x): {old!r}")
        f.write_bytes(s.replace(old, new, 1).encode("utf-8"))
        applied.append(f"{rel}: {why}")
    (dst / "mainLoop" / "field2026_grow.m").write_text(GROW_HELPER, encoding="utf-8")
    applied.append("mainLoop/field2026_grow.m: helper")
    stamp.write_text(json.dumps({"source": str(src), "source_sha256": src_sig, "patch_sha256": patch_sig, "mex": mex,
                                 "applied": applied, "written_utc": utc_now_iso()}, indent=2))
    print(f"[k1] patched copy -> {dst} ({len(applied)} change(s); mex: {', '.join(mex) or 'NONE - compile first'})")
    return dst, applied


def k1_config(pipeline_root: Path, *, whitening_range: int, keep_matlab_files: bool) -> dict:
    cfg = yaml.safe_load((pipeline_root / "sorter" / "Kilosort1_config.yaml").read_text(encoding="utf-8"))
    cfg.update({"NT": "32*1024+ntbuff", "whiteningRange": int(whitening_range), "parfor": False,
                "delete_recording_dat": True})
    if keep_matlab_files:
        cfg["delete_tmp_files"] = []
    return cfg


def compare_outputs(a: Path, b: Path) -> bool:
    ok = True
    for name in ("spike_times.npy", "spike_clusters.npy", "spike_templates.npy", "amplitudes.npy",
                 "templates.npy", "pc_features.npy", "template_features.npy"):
        fa, fb = a / name, b / name
        if not (fa.exists() and fb.exists()):
            print(f"  {name}: missing in {'A' if not fa.exists() else 'B'}")
            ok = False
            continue
        x, y = np.load(fa), np.load(fb)
        same = x.shape == y.shape and np.array_equal(x, y)
        print(f"  {name}: {'IDENTICAL' if same else 'DIFFERENT'} {x.shape} vs {y.shape}")
        ok &= same
    return ok


def selftest() -> None:
    import tempfile
    proot = default_pipeline_root()
    with tempfile.TemporaryDirectory() as td:
        dst, applied = prepare_patched_ks1(proot, Path(td), refresh=True)
        s = (dst / "fullMPMU.m").read_text(encoding="utf-8")
        assert s.count("field2026 patch") == 5 and "cat(1, st3, STT)" not in s, "fullMPMU.m patch incomplete"
        assert "field2026 patch" in (dst / "mainLoop" / "zeroOutKcoords.m").read_text(encoding="utf-8"), "zeroOutKcoords patch missing"
        assert (dst / "mainLoop" / "field2026_grow.m").exists()
        print(f"selftest: {len(applied)} patch items applied to a copy of {proot / 'sorter' / 'KiloSort1'}")
    cfg = k1_config(proot, whitening_range=64, keep_matlab_files=False)
    assert cfg["NT"] == "32*1024+ntbuff" and cfg["parfor"] is False and cfg["whiteningRange"] == 64
    print("selftest: config OK (NT 32*1024+ntbuff, parfor off, whiteningRange 64); crit override = %g" % LAB_CRIT)
    print("SELFTEST PASS")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--animal")
    ap.add_argument("--dat", help="block .dat (int16, all channels)")
    ap.add_argument("--xml", default=None, help="session/block XML; default: written from the cohort probe config")
    ap.add_argument("--out", help="output folder for this block")
    ap.add_argument("--disconnect", type=int, nargs="*", default=[], help="extra 0-based channels to leave out (failing shanks)")
    ap.add_argument("--whitening-range", type=int, default=64)
    ap.add_argument("--partition", choices=["all", "shank"], default="all")
    ap.add_argument("--crit", type=float, default=LAB_CRIT, help="criterionNoiseChannels (lab 1e-5; pipeline 0.2)")
    ap.add_argument("--unpatched", action="store_true", help="use the pipeline's K1 unchanged (for the --compare check)")
    ap.add_argument("--test-small-prealloc", action="store_true", help="TEST: patched K1 starting at 1,000 rows (exercises the doubling)")
    ap.add_argument("--subset-copy", action="store_true",
                    help="pipeline default: write the channel-subset recording.dat (default: full width, no copy)")
    ap.add_argument("--keep-matlab-files", action="store_true")
    ap.add_argument("--pipeline-root", default=None)
    ap.add_argument("--tools-root", default=None)
    ap.add_argument("--matlab", default=None)
    ap.add_argument("--refresh-ks1", action="store_true")
    ap.add_argument("--compare", nargs=2, metavar=("PHY_A", "PHY_B"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    if a.compare:
        ok = compare_outputs(Path(a.compare[0]), Path(a.compare[1]))
        print("COMPARE:", "IDENTICAL" if ok else "DIFFERENT"); sys.exit(0 if ok else 1)
    if not (a.animal and a.dat and a.out):
        ap.error("--animal, --dat and --out are required")

    animal = a.animal if len(a.animal) == 4 else f"SF{int(a.animal[2:]):02d}"
    proot = Path(a.pipeline_root) if a.pipeline_root else default_pipeline_root()
    tools = Path(a.tools_root) if a.tools_root else tools_root(a.cohort)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    dat = Path(a.dat)
    os.environ.setdefault("MW_CUDA_FORWARD_COMPATIBILITY", "1")
    os.environ.setdefault("CUDA_CACHE_MAXSIZE", "4294967296")
    os.environ.setdefault("PREPROCESS_RUNTIME_DIR", str(tools / "preprocess_runtime"))
    Path(os.environ["PREPROCESS_RUNTIME_DIR"]).mkdir(parents=True, exist_ok=True)

    probe_config = PROJECT_ROOT / ephys_block(a.cohort)["probe_config"]
    probe = load_probe(probe_config, animal)
    xml = Path(a.xml) if a.xml else out / f"{dat.stem}.xml"
    if not a.xml:
        write_session_xml_for_animal(probe_config=probe_config, animal=animal, out=xml)

    sys.path.insert(0, str(proot))
    os.chdir(proot)
    from src.preprocess import prepare_chanmap  # noqa: E402
    import src.preprocess.sorter_runner as sr  # noqa: E402

    layout = str(probe.get("layout", "linear"))
    n_groups = len(ET.parse(xml).getroot().findall("anatomicalDescription/channelGroups/group"))
    chanmap, bad = prepare_chanmap(basepath=xml.parent, basename=xml.stem, local_output_dir=out,
                                   probe_assignments=[{"type": layout, "groups": list(range(n_groups)), "x_offset": 0}],
                                   reject_channels=list(a.disconnect), xml_path=xml)
    cfg = k1_config(proot, whitening_range=a.whitening_range, keep_matlab_files=a.keep_matlab_files)
    cfg_path = out / "k1_config_used.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    if a.unpatched:
        ks1_path, applied = proot / "sorter" / "KiloSort1", []
    else:
        ks1_path, applied = prepare_patched_ks1(proot, tools, refresh=a.refresh_ks1,
                                                small_prealloc_test=a.test_small_prealloc)

    # criterionNoiseChannels: the runner writes its default only when ops lacks the key (sorter_runner.py
    # _rewrite_kilosort_ops_nchan_from_chanmap); record what actually lands in ops.mat.
    seen_ops: dict = {}
    orig_rewrite = sr._rewrite_kilosort_ops_nchan_from_chanmap

    def rewrite_with_lab_crit(*, sorter_output_folder, n_channels_total=None, criterion_noise_channels_default=0.2):
        orig_rewrite(sorter_output_folder=sorter_output_folder, n_channels_total=n_channels_total,
                     criterion_noise_channels_default=a.crit)
        from scipy.io import loadmat
        ops = loadmat(str(Path(sorter_output_folder) / "ops.mat"), simplify_cells=True)["ops"]
        for k in ("criterionNoiseChannels", "whiteningRange", "Nfilt", "NT", "Nchan", "NchanTOT", "parfor",
                  "ForceMaxRAMforDat", "Th", "lam"):
            v = ops.get(k)
            seen_ops[k] = v.tolist() if hasattr(v, "tolist") else v
        print(f"[k1] ops.mat: {seen_ops}")

    sr._rewrite_kilosort_ops_nchan_from_chanmap = rewrite_with_lab_crit

    # Full width (lab KilosortWrapper behaviour). K1 reads all channels of the .dat and drops dead ones through
    # chanMap `connected`. The pipeline instead intersects the active set with `connected`, and any dead channel then
    # makes spikeinterface write a 50-90 GB channel-subset copy (recording.dat) before K1 starts. Whole-probe runs
    # tell the runner that every channel is active; `connected` (kept by _copy_chanmap_for_kilosort) still excludes
    # the dead ones inside K1.
    if a.partition == "all" and not a.subset_copy:
        n_all = int(probe.get("n_channels", 64))
        sr._resolve_active_channels_0based = lambda **kw: list(range(int(kw.get("num_channels", n_all))))

    partitions = [None]
    if a.partition == "shank":
        parts = sr.build_sorter_partitions(mode="shank", chanmap_mat_path=chanmap,
                                           num_channels=int(probe.get("n_channels", 64)), excluded_channels_0based=bad)
        partitions = [p for p in parts if p.status != "skipped"]
    t0 = time.time()
    results = []
    for p in partitions:
        folder = out / ("kilosort1" if p is None else f"kilosort1_{p.name}")
        t1 = time.time()
        part_cfg = cfg_path
        if p is not None:
            # lab KilosortConfiguration: nNeigh = nNeighPC = min(16, Nchan); with a fixed 16 the K1 final pass indexes
            # past the channel count of a 12-15-channel shank ("Index ... must not exceed 15")
            n_act = len(p.channels_0based)
            pc = dict(cfg, nNeigh=min(int(cfg.get("nNeigh", 16)), n_act), nNeighPC=min(int(cfg.get("nNeighPC", 16)), n_act))
            part_cfg = out / f"k1_config_used_{p.name}.yaml"
            part_cfg.write_text(yaml.safe_dump(pc, sort_keys=False), encoding="utf-8")
        sr.execute_sorting_job(
            sorter="kilosort", dat_path=dat, xml_path=xml, output_folder=folder, config_path=part_cfg,
            kilosort1_path=ks1_path, matlab_path=Path(a.matlab or default_matlab()), matlab_max_workers=None,
            chanmap_mat_path=chanmap, active_channels_0based=None if p is None else p.channels_0based,
            exclude_channels_0based=bad if p is not None else None, remove_existing_folder=True)
        st = np.load(folder / "spike_times.npy").ravel()
        cl = np.load(folder / "spike_clusters.npy").ravel()
        results.append({"folder": str(folder), "elapsed_s": round(time.time() - t1, 1), "spikes": int(st.size),
                        "clusters": int(np.unique(cl).size)})
        print(f"[k1] {folder.name}: {st.size} spikes, {np.unique(cl).size} clusters, {time.time() - t1:.0f} s")
    n_samples = dat.stat().st_size // 2 // int(probe.get("n_channels", 64))
    write_json(out / "k1_run.json", {
        "written_utc": utc_now_iso(), "animal": animal, "dat": str(dat), "hours": n_samples / 20000 / 3600,
        "xml": str(xml), "layout": layout, "disconnected_0based": bad, "partition": a.partition,
        "full_width": a.partition == "all" and not a.subset_copy,
        "criterionNoiseChannels_requested": a.crit, "ops_seen": seen_ops, "config": cfg,
        "kilosort1_path": str(ks1_path), "ks1_patches": applied, "pipeline_root": str(proot),
        "pipeline_commit": git_commit(proot), "repo_commit": git_commit(PROJECT_ROOT), "host": platform.node(),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"), "elapsed_s": round(time.time() - t0, 1),
        "results": results})
    print(f"[k1] done in {time.time() - t0:.0f} s -> {out / 'k1_run.json'}")


if __name__ == "__main__":
    main()
