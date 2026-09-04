"""Write a Neuroscope/CellExplorer-style session XML with per-shank channel groups from a probe config.

PreprocessPipeline reads ``<basename>.xml`` for: sampling rate, channel count, ``anatomicalDescription``
channel groups (= shanks; drives the per-shank Kilosort partition and the chanMap geometry), ``skip="1"``
channels (excluded), the optional ``generalInfo/description`` (selects the geometry layout, e.g. "staggered"
or "Buzsaki 5x12"), and ``spikeDetection`` groups (channels absent there are marked not-connected).

Usage:
  python ephys/make_session_xml.py --probe-config ephys/configs/probes_2026c.yaml --animal SF08 \
         --out <stage_dir>/<basename>.xml [--reject 32 40] [--fs 20000] [--lfp-fs 1250]
"""
from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

import yaml


def _groups_from_xml(xml_path: Path) -> tuple[list[list[int]], list[int]]:
    r = ET.parse(xml_path).getroot()
    cg = r.find("anatomicalDescription/channelGroups")
    groups = [[int(c.text) for c in g.findall("channel")] for g in cg.findall("group")]
    skipped = [int(c.text) for g in cg.findall("group") for c in g.findall("channel") if c.get("skip") == "1"]
    return groups, skipped


def load_probe(probe_config: Path, animal: str) -> dict:
    cfg = yaml.safe_load(Path(probe_config).read_text(encoding="utf-8"))
    animals = cfg.get("animals") or {}
    if animal not in animals:
        raise KeyError(f"{probe_config}: no probe entry for animal {animal!r} (have {sorted(animals)})")
    probe = dict(animals[animal])
    # A per-animal XML (exported-column numbering, e.g. from make_probe_xml.py or a data-derived one) overrides
    # inline groups; its skip="1" channels are merged into reject_channels.
    if probe.get("xml"):
        xml_path = Path(probe["xml"])
        if not xml_path.is_absolute():
            xml_path = Path(probe_config).resolve().parent.parent.parent / xml_path   # repo-relative
        groups, skipped = _groups_from_xml(xml_path)
        probe["groups"] = groups
        probe["reject_channels"] = sorted(set(int(c) for c in (probe.get("reject_channels") or [])) | set(skipped))
        probe["xml_resolved"] = str(xml_path)
    probe["n_channels"] = int(probe.get("n_channels", cfg.get("n_channels", 64)))
    probe["sampling_rate_hz"] = float(probe.get("sampling_rate_hz", cfg.get("sampling_rate_hz", 20000)))
    probe["verified"] = bool(probe.get("verified", cfg.get("verified", False)))
    probe["mapping_source"] = probe.get("mapping_source", cfg.get("mapping_source", ""))
    probe["reject_channels"] = [int(c) for c in (probe.get("reject_channels") or [])]
    probe["groups"] = [[int(c) for c in g] for g in probe["groups"]]
    flat = [c for g in probe["groups"] for c in g]
    if len(flat) != len(set(flat)):
        raise ValueError(f"probe {animal}: duplicate channels across groups")
    if any(c < 0 or c >= probe["n_channels"] for c in flat):
        raise ValueError(f"probe {animal}: channel outside 0..{probe['n_channels'] - 1}")
    return probe


def build_session_xml(*, n_channels: int, fs: float, groups: list[list[int]], reject: list[int], layout: str,
                      lfp_fs: float = 1250.0, description_extra: str = "") -> ET.Element:
    reject_set = set(int(c) for c in reject)
    root = ET.Element("parameters", version="1.0", creator="Field2026_Social_analysis/ephys/make_session_xml.py")
    gi = ET.SubElement(root, "generalInfo")
    ET.SubElement(gi, "date").text = ""
    ET.SubElement(gi, "experimenters").text = ""
    desc = layout if not description_extra else f"{layout} — {description_extra}"
    ET.SubElement(gi, "description").text = desc
    ET.SubElement(gi, "notes").text = ""
    acq = ET.SubElement(root, "acquisitionSystem")
    ET.SubElement(acq, "nBits").text = "16"
    ET.SubElement(acq, "nChannels").text = str(int(n_channels))
    ET.SubElement(acq, "samplingRate").text = f"{fs:g}"
    ET.SubElement(acq, "voltageRange").text = "20"
    ET.SubElement(acq, "amplification").text = "1000"
    ET.SubElement(acq, "offset").text = "0"
    fp = ET.SubElement(root, "fieldPotentials")
    ET.SubElement(fp, "lfpSamplingRate").text = f"{lfp_fs:g}"
    anat = ET.SubElement(root, "anatomicalDescription")
    cg = ET.SubElement(anat, "channelGroups")
    covered = set()
    for g in groups:
        ge = ET.SubElement(cg, "group")
        for c in g:
            ET.SubElement(ge, "channel", skip="1" if c in reject_set else "0").text = str(int(c))
            covered.add(int(c))
    # channels not assigned to any shank go into a trailing "unassigned" group, skipped, so nChannels stays
    # consistent with the binary and they never enter the sort
    leftover = [c for c in range(int(n_channels)) if c not in covered]
    if leftover:
        ge = ET.SubElement(cg, "group")
        for c in leftover:
            ET.SubElement(ge, "channel", skip="1").text = str(c)
    spk = ET.SubElement(root, "spikeDetection")
    scg = ET.SubElement(spk, "channelGroups")
    for g in groups:
        keep = [c for c in g if c not in reject_set]
        if not keep:
            continue
        ge = ET.SubElement(scg, "group")
        chs = ET.SubElement(ge, "channels")
        for c in keep:
            ET.SubElement(chs, "channel").text = str(int(c))
        ET.SubElement(ge, "nSamples").text = "32"
        ET.SubElement(ge, "peakSampleIndex").text = "16"
        ET.SubElement(ge, "nFeatures").text = "3"
    ns = ET.SubElement(root, "neuroscope", version="2.0.0")
    misc = ET.SubElement(ns, "miscellaneous")
    ET.SubElement(misc, "screenGain").text = "0.2"
    ET.SubElement(misc, "traceBackgroundImage").text = ""
    sp = ET.SubElement(ns, "spikes")
    ET.SubElement(sp, "nSamples").text = "32"
    ET.SubElement(sp, "peakSampleIndex").text = "16"
    chans = ET.SubElement(ns, "channels")
    palette = ["#0080ff", "#ff8000", "#00c000", "#c000c0", "#00c0c0", "#c0c000", "#ff0000", "#8080ff"]
    for gi_, g in enumerate(groups + ([leftover] if leftover else [])):
        col = palette[gi_ % len(palette)]
        for c in g:
            cc = ET.SubElement(chans, "channelColors")
            ET.SubElement(cc, "channel").text = str(int(c))
            ET.SubElement(cc, "color").text = col
            ET.SubElement(cc, "anatomyColor").text = col
            ET.SubElement(cc, "spikeColor").text = col
            co = ET.SubElement(chans, "channelOffset")
            ET.SubElement(co, "channel").text = str(int(c))
            ET.SubElement(co, "defaultOffset").text = "0"
    return root


def write_xml(root: ET.Element, out: Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pretty = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent=" ")
    out.write_text(pretty, encoding="utf-8")
    return out


def write_session_xml_for_animal(*, probe_config: Path, animal: str, out: Path, extra_reject: list[int] | None = None,
                                 fs: float | None = None, n_channels: int | None = None, lfp_fs: float = 1250.0) -> tuple[Path, dict]:
    probe = load_probe(probe_config, animal)
    reject = sorted(set(probe["reject_channels"]) | set(int(c) for c in (extra_reject or [])))
    n = int(n_channels or probe["n_channels"])
    rate = float(fs or probe["sampling_rate_hz"])
    extra = "" if probe["verified"] else "UNVERIFIED channel->shank mapping (placeholder)"
    root = build_session_xml(n_channels=n, fs=rate, groups=probe["groups"], reject=reject, layout=str(probe["layout"]),
                             lfp_fs=lfp_fs, description_extra=extra)
    write_xml(root, out)
    info = {"animal": animal, "layout": probe["layout"], "groups": probe["groups"], "reject_channels": reject,
            "n_channels": n, "sampling_rate_hz": rate, "verified": probe["verified"], "mapping_source": probe["mapping_source"],
            "probe_config": str(probe_config)}
    return Path(out), info


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe-config", required=True)
    ap.add_argument("--animal", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--reject", type=int, nargs="*", default=[], help="extra 0-based channels to skip")
    ap.add_argument("--fs", type=float, default=None)
    ap.add_argument("--n-channels", type=int, default=None)
    ap.add_argument("--lfp-fs", type=float, default=1250.0)
    a = ap.parse_args()
    out, info = write_session_xml_for_animal(probe_config=Path(a.probe_config), animal=a.animal, out=Path(a.out),
                                             extra_reject=a.reject, fs=a.fs, n_channels=a.n_channels, lfp_fs=a.lfp_fs)
    print(f"wrote {out}: {len(info['groups'])} groups, reject={info['reject_channels']}, layout={info['layout']}, verified={info['verified']}")


if __name__ == "__main__":
    main()
