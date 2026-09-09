"""Offline self-test for ephys/ (no field data needed): header parser, de-glitch, XML, index, staging.

    python ephys/selftest.py            -> PASS/FAIL per check, exit 1 on any failure

Synthetic recording: 64 ch x 20 s @ 20 kHz int16 = slow LFP-like component + white noise (sigma 50 ADC)
+ biphasic 1-ms spikes (-2500 ADC) + the two field defects: (A) single-sample channel-substitution ticks at
~1000/s summed over channels with |offset| 1500-8000 ADC, (B) one-sample -21650 ADC housekeeping spikes on
all channels every 15 s. Acceptance mirrors the field validation: >= 99 % of injected glitches replaced,
< 1 % of spike-peak samples altered, ticks (>1200 ADC) removal >= 99 %.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PROJECT_ROOT, parse_session_name  # noqa: E402
from deglitch_wild import deglitch_file, tick_count  # noqa: E402
from make_session_xml import build_session_xml, load_probe, write_xml  # noqa: E402
from wild_ce_params import build_ce_params_bytes, parse_ce_params_bytes  # noqa: E402

FS, NCH, SEC = 20000, 64, 20
RESULTS: list[tuple[str, bool, str]] = []


def rec(name: str, ok: bool, msg: str = "") -> None:
    RESULTS.append((name, bool(ok), msg))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {msg}")


def synth(seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = FS * SEC
    t = np.arange(n) / FS
    lfp = 400 * np.sin(2 * np.pi * 3 * t)[:, None] * rng.uniform(0.5, 1.5, NCH)[None, :]
    x = lfp + rng.normal(0, 50, (n, NCH))
    spike = -2500 * np.exp(-((np.arange(20) - 6) ** 2) / 8.0) + 800 * np.exp(-((np.arange(20) - 13) ** 2) / 12.0)
    spike_peaks = np.zeros((n, NCH), dtype=bool)
    for c in range(NCH):
        for s in rng.integers(30, n - 30, size=60):
            x[s:s + 20, c] += spike
            spike_peaks[s + 6, c] = True
    glitch = np.zeros((n, NCH), dtype=bool)
    nA = 1000 * SEC
    ci = rng.integers(0, NCH, nA); si = rng.integers(3, n - 3, nA)
    x[si, ci] += rng.choice([-1, 1], nA) * rng.uniform(1500, 8000, nA); glitch[si, ci] = True
    for s in range(FS * 2, n, FS * 15):
        x[s, :] = -21650; glitch[s, :] = True
    return np.clip(x, -32768, 32767).astype(np.int16), glitch, spike_peaks


def test_ce_params() -> None:
    b = build_ce_params_bytes(firmware_version=64, rtc=datetime(2026, 8, 31, 19, 1, 33), mac="128C2F27E131")
    cp = parse_ce_params_bytes(b, "synthetic")
    rec("ce_params roundtrip", cp.firmware_version == 64 and cp.fs == 20000 and cp.n_channels == 64 and cp.mac == "128C2F27E131"
        and cp.rtc_start == "2026-08-31 19:01:33" and cp.misc_ratio == 16, f"fw={cp.firmware_version} rtc={cp.rtc_start} mac={cp.mac}")
    real = PROJECT_ROOT.drive and Path("E:/3rd_rat_spikes/SF8/128C2F27E131/0_20260831_190133.486/CE_params.bin")
    if real and real.exists():
        cp2 = parse_ce_params_bytes(real.read_bytes(), str(real))
        rec("ce_params real SF8 header", cp2.firmware_version == 64 and cp2.rtc_start == "2026-08-31 19:01:33" and cp2.mac == "128C2F27E131", f"fw={cp2.firmware_version}")


def test_session_name() -> None:
    m = parse_session_name("0_20260831_190133.486")
    rec("session name parse", bool(m) and m["slot"] == 0 and m["start"] == datetime(2026, 8, 31, 19, 1, 33, 486000) and parse_session_name("recovery.bin") is None)


def test_deglitch(tmp: Path) -> tuple[Path, np.ndarray]:
    x, glitch, peaks = synth()
    src = tmp / "raw" / "SF8" / "128C2F27E131" / "0_20260831_190133.486"
    src.mkdir(parents=True)
    x.tofile(src / "amplifier.dat")
    (src / "CE_params.bin").write_bytes(build_ce_params_bytes(firmware_version=64))
    np.arange(x.shape[0], dtype=np.int32).tofile(src / "time.dat")
    (src / "info.rhd").write_bytes(b"\x02\x27\x91\xc6" + bytes(60))
    out = tmp / "clean" / "amplifier.dat"
    s = deglitch_file(src / "amplifier.dat", out, nch=NCH, report=tmp / "clean" / "r.csv", manifest=tmp / "clean" / "m.json", verify=True, progress=False)
    y = np.fromfile(out, dtype=np.int16).reshape(-1, NCH)
    replaced = (y != x)
    frac_glitch_fixed = replaced[glitch].mean()
    frac_peaks_changed = replaced[peaks].mean()
    rec("deglitch removes injected glitches (>=99%)", frac_glitch_fixed >= 0.99, f"{100 * frac_glitch_fixed:.2f}% of {glitch.sum()} glitches replaced")
    rec("deglitch preserves spike peaks (<1% altered)", frac_peaks_changed < 0.01, f"{100 * frac_peaks_changed:.3f}% of {peaks.sum()} peaks altered")
    rec("deglitch tick metric (>=99% removal)", s["tick_removal_pct"] is not None and s["tick_removal_pct"] >= 99.0, f"ticks {s['ticks_before']} -> {s['ticks_after']}")
    rec("deglitch output size == input size", out.stat().st_size == (src / "amplifier.dat").stat().st_size)
    rec("deglitch report + manifest written", (tmp / "clean" / "r.csv").exists() and json.loads((tmp / "clean" / "m.json").read_text())["n_replaced_total"] == int(replaced.sum()))
    # second synthetic session on FM65 (clean) for the index/staging tests
    src2 = tmp / "raw" / "SF9" / "68BDFFFF62DB" / "0_20260902_080000.000"
    src2.mkdir(parents=True)
    rng = np.random.default_rng(1)
    clean = np.clip(rng.normal(0, 50, (FS * 5, NCH)), -32768, 32767).astype(np.int16)
    clean.tofile(src2 / "amplifier.dat")
    (src2 / "CE_params.bin").write_bytes(build_ce_params_bytes(firmware_version=65, rtc=datetime(2026, 9, 2, 8, 0, 0), mac="68BDFFFF62DB"))
    np.arange(clean.shape[0], dtype=np.int32).tofile(src2 / "time.dat")
    (tmp / "raw" / "SF8" / "recovery.bin").write_bytes(b"\0" * 1024)
    return tmp / "raw", x


def test_xml(tmp: Path) -> Path:
    import xml.etree.ElementTree as ET
    probe_cfg = PROJECT_ROOT / "ephys" / "configs" / "probes_2026c.yaml"
    p7 = load_probe(probe_cfg, "SF07")
    flat7 = sorted(c for g in p7["groups"] for c in g)
    rec("probe config SF07 = 4 x 16 exported columns from its verified XML", [len(g) for g in p7["groups"]] == [16, 16, 16, 16] and flat7 == list(range(64)) and p7["verified"] is True,
        f"groups {[len(g) for g in p7['groups']]}")
    p9 = load_probe(probe_cfg, "SF09")
    flat9 = sorted(c for g in p9["groups"] for c in g)
    rec("probe config SF09 = data-derived XML covering all 64 columns with skips", flat9 == list(range(64)) and len([g for g in p9["groups"] if not set(g) <= set(p9["reject_channels"])]) == 5 and len(p9["reject_channels"]) >= 4 and p9["verified"] is False,
        f"groups {[len(g) for g in p9['groups']]} reject {len(p9['reject_channels'])}")
    root = build_session_xml(n_channels=64, fs=20000, groups=[list(range(16 * i, 16 * (i + 1))) for i in range(4)], reject=[32], layout="staggered")
    out = write_xml(root, tmp / "t.xml")
    r = ET.parse(out).getroot()
    groups = [[int(c.text) for c in g.findall("channel")] for g in r.find("anatomicalDescription/channelGroups").findall("group")]
    skipped = [int(c.text) for g in r.find("anatomicalDescription/channelGroups").findall("group") for c in g.findall("channel") if c.get("skip") == "1"]
    spk = [[int(c.text) for c in g.find("channels").findall("channel")] for g in r.find("spikeDetection/channelGroups").findall("group")]
    rec("xml groups/skip roundtrip", len(groups) == 4 and skipped == [32] and 32 not in spk[2] and int(r.find("acquisitionSystem/nChannels").text) == 64)
    try:
        sys.path.insert(0, str(Path("C:/Users/Cornell/Documents/GitHub/PreprocessPipeline")))
        from src.preprocess.io import build_channel_map_data, derive_probe_assignments_from_xml
        pa, sk = derive_probe_assignments_from_xml(out)
        cm = build_channel_map_data(basepath=out.parent, basename="t", xml_path=out)
        ok = pa[0]["type"] == "staggered" and sk == [32] and cm is not None and int(cm["connected"].sum()) == 63 and len(set(np.asarray(cm["kcoords"]).ravel())) == 4
        rec("PreprocessPipeline reads the XML (chanMap 4 shanks, 63 connected)", ok)
    except Exception as e:  # pipeline env not active: informative, not a failure of ephys/
        print(f"[SKIP] PreprocessPipeline chanMap check ({type(e).__name__}: {e})")
    return out


def test_index_and_stage(raw: Path, tmp: Path) -> None:
    from build_session_index import build_index, write_outputs
    from stage_session import stage_one
    cfg = {"n_channels": 64, "sampling_rate_hz": 20000, "gain_to_uV": 0.195, "clean_firmware_min": 65, "deglitch": {"k_mad": 10.0, "floor_adc": 500.0},
           "firmware_history": {64: "glitch", 65: "clean"}, "_cohort_yaml": {"cohort": "selftest"}}
    rows, details, animals = build_index(raw, cfg, probe_seconds=5.0, verbose=False)
    r8 = next(r for r in rows if r["animal"] == "SF8"); r9 = next(r for r in rows if r["animal"] == "SF9")
    rec("index: FM64 flagged deglitch_required + measured glitchy", r8["deglitch_required"] is True and r8["measured_verdict"] == "glitchy" and r8["firmware"] == 64,
        f"ticks/s={r8['ticks_per_s']}")
    rec("index: FM65 flagged clean + measured clean", r9["deglitch_required"] is False and r9["measured_verdict"] == "clean", f"ticks/s={r9['ticks_per_s']}")
    rec("index: durations + recovery.bin + MAC", r8["duration_s"] == 20.0 and animals["SF8"]["recovery_bin_gb"] != "" and r8["logger_mac"] == "128C2F27E131" and r8["time_dat_ok"] is True)
    from _common import iter_raw_sessions, FOREIGN
    foreign = raw / "SF8" / "AAAAAAAAAAAA" / "9_20260902_120000.000"; foreign.mkdir(parents=True, exist_ok=True)
    seen_all = {(a, s.name) for a, _, s in iter_raw_sessions(raw)}
    seen_2026c = {(a, s.name) for a, _, s in iter_raw_sessions(raw, cohort="2026c")}
    skipped = [(a, m, s.name) for a, m, s in FOREIGN]
    rec("index: foreign logger MAC skipped when the cohort registers one",
        ("SF8", foreign.name) in seen_all and ("SF8", foreign.name) not in seen_2026c
        and skipped == [("SF8", "AAAAAAAAAAAA", foreign.name)] and len(seen_all) - len(seen_2026c) == 1, f"skipped={skipped}")
    rec("index: unknown cohort key filters nothing (no crash)",
        {(a, s.name) for a, _, s in iter_raw_sessions(raw, cohort="selftest")} == seen_all)
    import shutil; shutil.rmtree(foreign.parent)
    out = write_outputs(rows, details, animals, cohort="selftest", cfg=cfg, raw_root=raw, out_dir=tmp / "reports", mirror_dir=tmp / "mirror", probe_seconds=5.0)
    rec("index: csv/md/json + mirror written", all(Path(v).exists() for v in out.values()) and (tmp / "mirror" / "SESSION_INDEX.md").exists())
    probe_cfg = PROJECT_ROOT / "ephys" / "configs" / "probes_2026c.yaml"
    m8 = stage_one(raw_session=raw / "SF8" / "128C2F27E131" / "0_20260831_190133.486", animal="SF8", staged_dir=tmp / "stage" / "SF08" / "0_20260831_190133.486",
                   cfg=cfg, probe_config=probe_cfg, verify=True, probe_seconds=5.0)
    m9 = stage_one(raw_session=raw / "SF9" / "68BDFFFF62DB" / "0_20260902_080000.000", animal="SF9", staged_dir=tmp / "stage" / "SF09" / "0_20260902_080000.000",
                   cfg=cfg, probe_config=probe_cfg, verify=True, probe_seconds=5.0)
    s8 = tmp / "stage" / "SF08" / "0_20260831_190133.486"
    rec("stage: FM64 de-glitched, sidecars + xml + manifest", m8["deglitch_applied"] and (s8 / "amplifier.dat").exists() and (s8 / "0_20260831_190133.486.xml").exists()
        and (s8 / "deglitch_report.csv").exists() and (s8 / "info.rhd").exists() and (s8 / "time.dat").exists() and not (s8 / "analogin.dat").exists()
        and 32 in m8["probe"]["reject_channels"], f"reject={m8['probe']['reject_channels']}")
    raw9 = np.fromfile(raw / "SF9" / "68BDFFFF62DB" / "0_20260902_080000.000" / "amplifier.dat", dtype=np.int16)
    st9 = np.fromfile(tmp / "stage" / "SF09" / "0_20260902_080000.000" / "amplifier.dat", dtype=np.int16)
    rec("stage: FM65 copied verbatim", (not m9["deglitch_applied"]) and np.array_equal(raw9, st9))
    m8b = stage_one(raw_session=raw / "SF8" / "128C2F27E131" / "0_20260831_190133.486", animal="SF8", staged_dir=s8, cfg=cfg, probe_config=probe_cfg)
    rec("stage: idempotent without --overwrite", m8b["staged_dir"] == m8["staged_dir"])


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ephys_selftest_"))
    try:
        test_ce_params(); test_session_name()
        raw, _ = test_deglitch(tmp)
        test_xml(tmp)
        test_index_and_stage(raw, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    n_fail = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"\n{len(RESULTS) - n_fail}/{len(RESULTS)} checks passed")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
