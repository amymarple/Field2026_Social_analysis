"""Parse the WILD CE64 neurologger session header ``CE_params.bin``.

Byte layout follows ``Neurologger/Code/WILD_ReadHeader.m`` (data_version at byte 440; both the v0 and the
v>=1 layouts place every field from ``dispCH`` (byte 140) onward at the same offsets). Fields we rely on:

    firmware_version  uint16 @328   (FM62 / FM64 / FM65 ...: the provenance gate for de-glitching)
    hw_version        uint16 @330
    date              4 bytes @332  (weekday, month, day, year-2000)          -> RTC start date
    time              @336          (hours, minutes, seconds, ...)             -> RTC start time (wallclock)
    MAC               8 bytes @356  (6 significant)                            -> logger identity
    fs                uint32 @0     amplifier sampling rate (Hz)
    Nch               v0: uint32 @8 ; v>=1: nch_each[0] uint16 @8

Usage: ``python ephys/wild_ce_params.py <session_dir_or_CE_params.bin> [--json]``
"""
from __future__ import annotations

import argparse
import json
import struct
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

HEADER_BYTES = 512
DATA_VERSION_OFFSET = 440
FIRMWARE_OFFSET = 328


@dataclass
class CeParams:
    path: str
    data_version: int
    fs: int
    n_channels: int
    aux_mode: int
    misc_ratio: int
    prev_ratio: int
    misc_interval: int
    error_code: int
    firmware_version: int
    hw_version: int
    rtc_start: str | None          # 'YYYY-MM-DD HH:MM:SS' logger wallclock (set from field-PC local time at Resync)
    rtc_raw: tuple
    mac: str                       # 12 hex chars, upper-case (= the offload folder name)
    sd_capacity: int
    system_status: int
    vbatt_threshold: int
    sampling_rates: tuple
    nch_each: tuple

    @property
    def misc_rate_hz(self) -> float:
        """analogin.dat rate = fs / misc_ratio (16 lanes @ 1250 Hz for the 64-ch 20 kHz config)."""
        return self.fs / self.misc_ratio if self.misc_ratio else float("nan")


def parse_ce_params_bytes(b: bytes, path: str = "<bytes>") -> CeParams:
    if len(b) < HEADER_BYTES:
        raise ValueError(f"{path}: CE_params.bin is {len(b)} bytes, expected >= {HEADER_BYTES}")
    dv = b[DATA_VERSION_OFFSET]
    fs = struct.unpack_from("<I", b, 0)[0]
    aux_mode = struct.unpack_from("<I", b, 4)[0]
    if dv == 0:
        nch = struct.unpack_from("<I", b, 8)[0]
        nch_each = (nch,)
        sampling_rates = (fs,)
    else:
        nch_each = struct.unpack_from("<8H", b, 8)
        nch = int(nch_each[0])
        sampling_rates = struct.unpack_from("<8I", b, 40)
    sd_capacity = struct.unpack_from("<I", b, 272)[0]
    system_status = struct.unpack_from("<I", b, 284)[0]
    misc_ratio, prev_ratio = b[320], b[321]
    misc_interval = struct.unpack_from("<H", b, 322)[0]
    error_code = struct.unpack_from("<I", b, 324)[0]
    fw = struct.unpack_from("<H", b, FIRMWARE_OFFSET)[0]
    hw = struct.unpack_from("<H", b, 330)[0]
    wd, mo, da, yr = b[332:336]
    hh, mm, ss = b[336:339]
    rtc_raw = (int(wd), int(mo), int(da), int(yr), int(hh), int(mm), int(ss))
    rtc_start: str | None
    try:
        rtc_start = datetime(2000 + yr, mo, da, hh, mm, ss).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        rtc_start = None   # uninitialised RTC (the field "2000-01-01 rule")
    mac = b[356:362].hex().upper()
    vbatt = struct.unpack_from("<H", b, 364)[0]
    return CeParams(
        path=str(path), data_version=int(dv), fs=int(fs), n_channels=int(nch), aux_mode=int(aux_mode),
        misc_ratio=int(misc_ratio), prev_ratio=int(prev_ratio), misc_interval=int(misc_interval),
        error_code=int(error_code), firmware_version=int(fw), hw_version=int(hw), rtc_start=rtc_start,
        rtc_raw=rtc_raw, mac=mac, sd_capacity=int(sd_capacity), system_status=int(system_status),
        vbatt_threshold=int(vbatt), sampling_rates=tuple(int(x) for x in sampling_rates),
        nch_each=tuple(int(x) for x in nch_each),
    )


def parse_ce_params(path: str | Path) -> CeParams:
    p = Path(path)
    if p.is_dir():
        p = p / "CE_params.bin"
    return parse_ce_params_bytes(p.read_bytes(), str(p))


def build_ce_params_bytes(*, fs: int = 20000, n_channels: int = 64, firmware_version: int = 64, hw_version: int = 12,
                          rtc: datetime | None = None, mac: str = "128C2F27E131", misc_ratio: int = 16,
                          data_version: int = 2, total_bytes: int = 1536) -> bytes:
    """Synthesise a v2-layout header (used by ephys/selftest.py; mirrors the field files where it matters)."""
    b = bytearray(total_bytes)
    struct.pack_into("<I", b, 0, fs)
    struct.pack_into("<8H", b, 8, n_channels, 1, 0, 0, 0, 0, 0, 0)
    struct.pack_into("<8H", b, 24, 64, 0, 0, 1, 0, 0, 0, 0)
    struct.pack_into("<8I", b, 40, fs, 0, 0, 0, 0, 0, 0, 0)
    struct.pack_into("<I", b, 272, 1001390080)
    b[320], b[321] = misc_ratio, 32
    struct.pack_into("<H", b, 322, 64)
    struct.pack_into("<I", b, 324, 65536)
    struct.pack_into("<H", b, FIRMWARE_OFFSET, firmware_version)
    struct.pack_into("<H", b, 330, hw_version)
    rtc = rtc or datetime(2026, 8, 31, 19, 1, 33)
    b[332:336] = bytes([rtc.isoweekday(), rtc.month, rtc.day, rtc.year - 2000])
    b[336:339] = bytes([rtc.hour, rtc.minute, rtc.second])
    b[356:362] = bytes.fromhex(mac)
    b[DATA_VERSION_OFFSET] = data_version
    return bytes(b)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="session folder or CE_params.bin")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cp = parse_ce_params(a.path)
    if a.json:
        print(json.dumps(asdict(cp), indent=2))
    else:
        for k, v in asdict(cp).items():
            print(f"{k:18s} {v}")


if __name__ == "__main__":
    main()
