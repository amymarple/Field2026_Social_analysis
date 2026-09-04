"""Generate a per-animal Neuroscope XML in EXPORTED-COLUMN numbering from a ProbeMaps probe XML plus the verified
connector orientation and the per-bank raw rotations of that logger's firmware fault.

Chain (see ephys/probe_map_check.py for the evidence):
    probe site -> Intan channel        ProbeMaps XML (version1 = raw Intan pin grid) + connector orientation
                                        (v1_raw | v2_rot180 | v3_fliplr | v4_flipud)
    Intan channel i -> exported column P[i]   P = rotation_permutation(rot_bank0, rot_bank1): the WILD Console CE64
                                        export map already applied on download, with the firmware's raw-bank slot
                                        rotation conjugated through it (vendor/correct_intan_dat_channel_order.py)
So the XML written here lists, for every shank in site order, the exported amplifier.dat columns. Use it directly on
the exported/staged amplifier.dat; do NOT also run the v57 repair on the data (that would rotate twice).

Usage:
  python ephys/make_probe_xml.py --probe A4x16-Lin-5mm-50s-300 --orientation v1_raw --rot0 1 --rot1 0 \
         --out ephys/configs/xml/SF07_A4x16-Lin_v1raw_rot+1_0.xml [--reject 32 ...] [--fs 20000]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from make_session_xml import build_session_xml, write_xml
from probe_map_check import PROBEMAPS, PROBE_XML, load_groups, orientation_variants, rotation_permutation

LAYOUT_FOR_PROBE = {"A4x16-Lin-5mm-50s-300": "linear", "A5x12_16-Buz_lin-5mm-100-200-160_177": "Buzsaki 5x12"}


def exported_groups(probe: str, orientation: str, rot0: int, rot1: int) -> tuple[list[list[int]], list[list[int]]]:
    """Return (groups in exported-column numbering, groups in Intan numbering) for the probe/orientation/rotations."""
    v1 = load_groups(PROBEMAPS / PROBE_XML[probe][0])
    intan_groups = orientation_variants(v1)[orientation]
    P = rotation_permutation(rot0, rot1)           # Intan channel i lives in exported column P[i]
    return [[int(P[ch]) for ch in g] for g in intan_groups], intan_groups


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", required=True, choices=list(PROBE_XML))
    ap.add_argument("--orientation", default="v1_raw", choices=["v1_raw", "v2_rot180", "v3_fliplr", "v4_flipud"])
    ap.add_argument("--rot0", type=int, default=0, help="raw bank-0 slot rotation of the logger (SF07 FM64/FM65: +1)")
    ap.add_argument("--rot1", type=int, default=0, help="raw bank-1 slot rotation of the logger")
    ap.add_argument("--reject", type=int, nargs="*", default=[], help="exported columns to mark skip=1")
    ap.add_argument("--fs", type=float, default=20000.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    groups, intan_groups = exported_groups(a.probe, a.orientation, a.rot0, a.rot1)
    layout = LAYOUT_FOR_PROBE[a.probe]
    root = build_session_xml(n_channels=64, fs=a.fs, groups=groups, reject=a.reject, layout=layout,
                             description_extra=f"{a.probe} {a.orientation} rot_bank0={a.rot0:+d} rot_bank1={a.rot1:+d}; channels = exported amplifier.dat columns")
    out = write_xml(root, Path(a.out))
    print(f"wrote {out}")
    for gi, (g, ig) in enumerate(zip(groups, intan_groups)):
        print(f"  shank {gi + 1}: exported columns {g}\n           (Intan ids {ig})")


if __name__ == "__main__":
    main()
