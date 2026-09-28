"""Stage one raw WILD session into a clean, sortable working copy (raw data is never touched).

    <OUT_ROOT>/<cohort>/ephys_stage/<animal>/<session>/
        amplifier.dat          de-glitched copy (firmware < clean_firmware_min) or verbatim copy (FM65+)
        info.rhd, CE_params.bin, time.dat   copied (time.dat regenerated as int32 0..N-1 when missing)
        <session>.xml          Neuroscope XML with shank groups from ephys/configs/probes_<cohort>.yaml
        deglitch_report.csv / deglitch_manifest.json   (when de-glitched)
        stage_manifest.json    full provenance: source paths + fingerprints, firmware, params, probe info,
                               auto-reject channels, git commit, timestamp

Deliberately NOT staged: analogin.dat / digitalin.dat / supply.dat / adc.dat / misc.dat. PreprocessPipeline's
Intan sidecar check infers ADC width from the 20 kHz amplifier sample count and would reject the 1250 Hz WILD
lanes; BLE PC-time anchors are derived from the RAW folder with Neurologger's WILD_generate_pc_time.py.

Firmware gate: de-glitch iff CE_params.firmware_version < ephys.clean_firmware_min (cohort YAML), unless
--force-deglitch / --skip-deglitch. --auto-reject (default on) adds per-session dead/broken channel candidates
from a 30-s probe (ephys/signal_probe.py rules) to the probe-config reject list, as skip="1" in the XML.

Usage:
  python ephys/stage_session.py --cohort 2026c --animal SF8 --session 0_20260831_190133.486 [--overwrite]
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

import numpy as np

from _common import (PROJECT_ROOT, ephys_block, find_session_dir, git_commit, raw_ephys_root, sha256_head_tail, stage_root,
                     utc_now_iso, write_json)
from deglitch_wild import deglitch_file
from make_session_xml import write_session_xml_for_animal
from signal_probe import probe_window_stats
from wild_ce_params import parse_ce_params

COPY_SIDECARS = ("info.rhd", "CE_params.bin", "time.dat")


def _norm_animal(animal: str) -> str:
    """'SF8' and 'SF08' name the same animal (raw folders use SF8, the Notion/probe config use SF08)."""
    a = animal.upper()
    if a.startswith("SF") and a[2:].isdigit():
        return f"SF{int(a[2:]):02d}"
    return a


def _raw_animal_folder(raw_root: Path, animal: str) -> str:
    """Resolve the on-disk animal folder name for either spelling."""
    for cand in (animal, _norm_animal(animal), f"SF{int(animal[2:])}" if animal[2:].isdigit() else animal):
        if (raw_root / cand).is_dir():
            return cand
    raise FileNotFoundError(f"no folder for {animal} under {raw_root}")


def window_suffix(window_s: tuple[float, float] | None) -> str:
    """Folder suffix for a windowed stage so it can never be mistaken for the full session."""
    return "" if window_s is None else f"__w{int(window_s[0])}s_{int(window_s[1])}s"


def stage_one(*, raw_session: Path, animal: str, staged_dir: Path, cfg: dict, probe_config: Path, force_deglitch: bool | None = None,
              auto_reject: bool = True, overwrite: bool = False, verify: bool = True, probe_seconds: float = 30.0,
              window_s: tuple[float, float] | None = None) -> dict:
    """Stage one session. ``window_s=(start_s, duration_s)`` stages only that slice (quick tests of long sessions):
    the staged folder is named ``<session>__w<start>s_<dur>s`` and every manifest records the slice."""
    raw_session = Path(raw_session)
    staged_dir = Path(staged_dir)
    manifest_path = staged_dir / "stage_manifest.json"
    if manifest_path.exists() and not overwrite:
        print(f"already staged (use --overwrite to redo): {staged_dir}")
        import json
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    staged_dir.mkdir(parents=True, exist_ok=True)

    cp = parse_ce_params(raw_session)
    nch = cp.n_channels or int(cfg.get("n_channels", 64))
    fs = float(cp.fs or cfg.get("sampling_rate_hz", 20000))
    clean_min = int(cfg.get("clean_firmware_min", 65))
    need = cp.firmware_version < clean_min if force_deglitch is None else bool(force_deglitch)
    dg = cfg.get("deglitch") or {}
    amp_src = raw_session / "amplifier.dat"
    amp_dst = staged_dir / "amplifier.dat"
    n_samples_file = os.path.getsize(amp_src) // (2 * nch)
    sample_range = None
    if window_s is not None:
        s0 = int(round(window_s[0] * fs))
        s1 = min(n_samples_file, s0 + int(round(window_s[1] * fs)))
        if s1 <= s0:
            raise ValueError(f"window {window_s} s lies outside the {n_samples_file / fs:.1f}-s session")
        sample_range = (s0, s1)
    n_samples = (sample_range[1] - sample_range[0]) if sample_range else n_samples_file
    basename = staged_dir.name

    print(f"[stage] {animal} {raw_session.name}{window_suffix(window_s)}: FM{cp.firmware_version} (clean >= FM{clean_min}) -> "
          f"{'DE-GLITCH' if need else 'verbatim copy'}{'' if sample_range is None else ' of samples %d..%d' % sample_range}")
    probe = probe_window_stats(amp_src, nch=nch, fs=fs, seconds=probe_seconds, k=float(dg.get("k_mad", 10.0)),
                               floor=float(dg.get("floor_adc", 500.0)), gain_uV=float(cfg.get("gain_to_uV", 0.195))) if probe_seconds > 0 else {}
    auto_rej = list(probe.get("bad_channel_candidates", [])) if auto_reject else []

    deglitch = None
    if need:
        deglitch = deglitch_file(amp_src, amp_dst, nch=nch, k=float(dg.get("k_mad", 10.0)), floor=float(dg.get("floor_adc", 500.0)),
                                 report=staged_dir / "deglitch_report.csv", manifest=staged_dir / "deglitch_manifest.json",
                                 verify=verify, fs=fs, sample_range=sample_range)
    elif sample_range is None:
        print(f"[stage] copying {amp_src} ({os.path.getsize(amp_src) / 1e9:.2f} GB)")
        shutil.copyfile(amp_src, amp_dst)
    else:
        print(f"[stage] copying samples {sample_range[0]}..{sample_range[1]} of {amp_src}")
        d = np.memmap(amp_src, dtype=np.int16, mode="r", shape=(n_samples_file, nch))
        np.ascontiguousarray(d[sample_range[0]:sample_range[1]]).tofile(amp_dst)

    for name in COPY_SIDECARS:
        src = raw_session / name
        if name == "time.dat" and (sample_range is not None or not src.exists()):
            if not src.exists():
                print("[stage] time.dat missing in raw -> regenerating int32 0..N-1 (as WILD_PreProcess.m does)")
            np.arange(n_samples, dtype=np.int32).tofile(staged_dir / name)
        elif src.exists():
            shutil.copyfile(src, staged_dir / name)

    animal_key = _norm_animal(animal)
    xml_path, probe_info = write_session_xml_for_animal(probe_config=probe_config, animal=animal_key, out=staged_dir / f"{basename}.xml",
                                                        extra_reject=auto_rej, fs=fs, n_channels=nch)
    manifest = {
        "cohort": cfg.get("_cohort_yaml", {}).get("cohort"), "animal": animal_key, "animal_raw_folder": animal, "session": raw_session.name,
        "basename": basename, "window_s": list(window_s) if window_s else None, "sample_range": list(sample_range) if sample_range else None,
        "source_n_samples": n_samples_file,
        "raw_session": str(raw_session), "staged_dir": str(staged_dir),
        "raw_amplifier": {"path": str(amp_src), "bytes": os.path.getsize(amp_src), "sha256_head_tail_64MiB": sha256_head_tail(amp_src)},
        "staged_amplifier": {"path": str(amp_dst), "bytes": os.path.getsize(amp_dst), "sha256_head_tail_64MiB": sha256_head_tail(amp_dst)},
        "n_channels": nch, "sampling_rate_hz": fs, "n_samples": n_samples, "duration_s": n_samples / fs,
        "header": {"firmware_version": cp.firmware_version, "hw_version": cp.hw_version, "rtc_start": cp.rtc_start, "mac": cp.mac,
                   "sd_capacity": cp.sd_capacity, "error_code": cp.error_code},
        "clean_firmware_min": clean_min, "deglitch_applied": need,
        "deglitch_decision": "forced" if force_deglitch is not None else "firmware gate",
        "deglitch": {k: v for k, v in (deglitch or {}).items() if k not in ("threshold_adc_per_channel", "n_replaced_per_channel")},
        "probe_window": {k: v for k, v in probe.items() if not isinstance(v, list)} | {"bad_channel_candidates": probe.get("bad_channel_candidates", [])},
        "auto_reject_channels": auto_rej, "probe": probe_info, "xml": str(xml_path),
        "sidecars_copied": [n for n in COPY_SIDECARS if (staged_dir / n).exists()],
        "sidecars_left_in_raw": ["analogin.dat", "digitalin.dat", "supply.dat", "adc.dat", "misc.dat"],
        "gain_to_uV": cfg.get("gain_to_uV", 0.195), "gain_note": "Intan default; WILD header carries no scale (relative, unverified)",
        "git_commit": git_commit(), "written_utc": utc_now_iso(), "script": "ephys/stage_session.py",
    }
    write_json(manifest_path, manifest)
    print(f"[stage] done -> {staged_dir}\n        xml={xml_path.name} reject={probe_info['reject_channels']} "
          f"{'glitch/s=%.1f ticks %s->%s' % (deglitch['glitch_rate_per_s'], deglitch['ticks_before'], deglitch['ticks_after']) if deglitch else ''}")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--animal", required=True, help="e.g. SF8 or SF08")
    ap.add_argument("--session", required=True, nargs="+", help="session folder name(s), e.g. 0_20260831_190133.486")
    ap.add_argument("--raw-root", default=None)
    ap.add_argument("--stage-root", default=None, help="override <OUT_ROOT>/<cohort>/ephys_stage")
    ap.add_argument("--probe-config", default=None, help="override ephys.probe_config from the cohort YAML")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--force-deglitch", action="store_true")
    g.add_argument("--skip-deglitch", action="store_true")
    ap.add_argument("--no-auto-reject", action="store_true")
    ap.add_argument("--no-verify", action="store_true", help="skip the before/after tick count (faster)")
    ap.add_argument("--window-s", type=float, nargs=2, metavar=("START_S", "DURATION_S"), default=None,
                    help="stage only this slice (quick tests of long sessions); folder gets a __w<start>s_<dur>s suffix")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    window = tuple(a.window_s) if a.window_s else None
    cfg = ephys_block(a.cohort)
    raw = raw_ephys_root(a.cohort, a.raw_root)
    animal_folder = _raw_animal_folder(raw, a.animal)
    probe_cfg = Path(a.probe_config) if a.probe_config else PROJECT_ROOT / cfg.get("probe_config", f"ephys/configs/probes_{a.cohort}.yaml")
    force = True if a.force_deglitch else (False if a.skip_deglitch else None)
    for sess in a.session:
        raw_session = find_session_dir(raw, animal_folder, sess)
        staged = stage_root(a.cohort, a.stage_root) / _norm_animal(a.animal) / (sess + window_suffix(window))
        stage_one(raw_session=raw_session, animal=animal_folder, staged_dir=staged, cfg=cfg, probe_config=probe_cfg, force_deglitch=force,
                  auto_reject=not a.no_auto_reject, overwrite=a.overwrite, verify=not a.no_verify, window_s=window)


if __name__ == "__main__":
    main()
