#!/usr/bin/env python3
"""Repair the FM57 Intan bank rotation in an exported ``amplifier.dat``.

Problem
-------
Some affected CE64 firmware recorded the first 32-word Intan SPI bank with a
fixed one-slot phase rotation. Sample count and sample time stayed continuous,
but each raw SPI slot contained the next channel in that bank. This is a
deterministic channel-label permutation, not missing data and not a
signal-processing glitch.

WILD Console then exported the raw slots through its normal CE64-to-Intan
channel map. Therefore an exported ``amplifier.dat`` must *not* be repaired by
rotating columns 0..31 directly. The raw inverse rotation has to be conjugated
through the already-applied WILD map:

    exported correction = inverse(WILD map) * raw inverse rotation * WILD map

Solution
--------
CE64 DAT files store each frame as 64 consecutive little-endian signed 16-bit
samples. This program streams the file frame by frame and applies the correct
post-export permutation. With the validated FM57 ``+1`` fault and WILD's CE64
map, corrected output column ``c`` is copied from these existing input columns:

    30,0,28,31,26,29,24,27,22,25,20,23,18,21,16,19,
    17,15,14,13,12,11,10,9,8,7,6,5,4,3,2,1,
    32,33,...,63

The default input layout is ``wild-export``, which is correct for a file
downloaded by WILD Console. ``--input-layout raw`` retains support for an
unmapped raw 64-column stream. Use ``--acquisition-rotation`` only when a
register-pattern diagnostic proves a different fixed rotation.

This tool must not be used for isolated corrupt
samples, dropped samples, or recordings whose rotation changes over time.
Correct either the DAT samples or the accompanying XML channel references, not
both; applying both compensations would rotate the channel labels twice.

Processing is sequential and chunked, so files much larger than RAM are
supported. The input is never overwritten. By default the new file is written
as ``v57_channel_repaired/amplifier.dat`` beside the input.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - exercised only without NumPy
    raise SystemExit("NumPy is required: install it with 'python -m pip install numpy'.") from exc


DTYPE = np.dtype("<i2")

# WILD Console CE32_channelMapper.CE64. Entry c is the raw Intan source column
# copied into exported amplifier.dat column c. This mapping predates FM57 and is
# already present in affected exported files; the repair must operate after it.
CE64_WILD_SOURCE_COLUMNS = np.asarray(
    [
        31, 0, 29, 2, 27, 4, 25, 6, 23, 8, 21, 10, 19, 12, 17, 14,
        16, 15, 18, 13, 20, 11, 22, 9, 24, 7, 26, 5, 28, 3, 30, 1,
        32, 60, 33, 58, 35, 56, 37, 54, 39, 52, 41, 50, 43, 48,
        45, 47, 49, 51, 46, 53, 44, 55, 42, 57, 40, 59, 38, 61,
        36, 63, 34, 62,
    ],
    dtype=np.int64,
)


def restored_source_columns(
    *,
    channel_count: int,
    bank: int,
    bank_size: int,
    acquisition_rotation: int,
    input_layout: str = "wild-export",
) -> np.ndarray:
    """Return the input column used for each corrected output column.

    ``acquisition_rotation=+1`` means raw stored slot ``r`` contains the value
    belonging to raw logical channel ``r+1`` within the selected bank.
    """
    if channel_count <= 0:
        raise ValueError("channel count must be positive")
    if bank < 0:
        raise ValueError("bank must be non-negative")
    if bank_size <= 0:
        raise ValueError("bank size must be positive")

    bank_start = bank * bank_size
    bank_end = bank_start + bank_size
    if bank_end > channel_count:
        raise ValueError(
            f"bank {bank} spans channels {bank_start}..{bank_end - 1}, "
            f"outside a {channel_count}-channel frame"
        )

    if input_layout == "raw":
        columns = np.arange(channel_count, dtype=np.int64)
        logical = np.arange(bank_size, dtype=np.int64)
        columns[bank_start:bank_end] = (
            bank_start + (logical - acquisition_rotation) % bank_size
        )
        return columns

    if input_layout != "wild-export":
        raise ValueError("input layout must be 'wild-export' or 'raw'")
    if channel_count != len(CE64_WILD_SOURCE_COLUMNS):
        raise ValueError(
            "wild-export repair requires exactly 64 channels because it uses "
            "WILD Console's CE64 channel map"
        )

    wild_map = CE64_WILD_SOURCE_COLUMNS
    if not np.array_equal(np.sort(wild_map), np.arange(channel_count)):
        raise RuntimeError("embedded WILD CE64 channel map is not a permutation")
    inverse_wild_map = np.empty(channel_count, dtype=np.int64)
    inverse_wild_map[wild_map] = np.arange(channel_count, dtype=np.int64)

    # Exported input column j contains the rotated raw value from wild_map[j].
    # For corrected output c, find j whose rotated value is the unrotated value
    # expected at wild_map[c]. Channels outside the selected raw bank are left
    # byte-for-byte in their existing exported columns.
    columns = np.arange(channel_count, dtype=np.int64)
    for output_column, raw_channel in enumerate(wild_map):
        if bank_start <= raw_channel < bank_end:
            source_raw_slot = bank_start + (
                (raw_channel - bank_start - acquisition_rotation) % bank_size
            )
            columns[output_column] = inverse_wild_map[source_raw_slot]
    return columns


def _default_output(input_path: Path) -> Path:
    return input_path.parent / "v57_channel_repaired" / "amplifier.dat"


def restore_dat(
    input_path: Path,
    output_path: Path,
    *,
    channel_count: int = 64,
    bank: int = 0,
    bank_size: int = 32,
    acquisition_rotation: int = 1,
    input_layout: str = "wild-export",
    chunk_mib: int = 128,
    force: bool = False,
    quiet: bool = False,
) -> dict[str, float | int | str]:
    """Stream a corrected copy of ``input_path`` to ``output_path``."""
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    if input_path == output_path:
        raise ValueError("input and output must differ; the source is never overwritten")
    if not input_path.is_file():
        raise FileNotFoundError(f"input DAT file does not exist: {input_path}")
    if output_path.exists() and not force:
        raise FileExistsError(f"output already exists: {output_path} (use --force)")
    if chunk_mib <= 0:
        raise ValueError("chunk size must be positive")

    source_columns = restored_source_columns(
        channel_count=channel_count,
        bank=bank,
        bank_size=bank_size,
        acquisition_rotation=acquisition_rotation,
        input_layout=input_layout,
    )
    bank_start = bank * bank_size
    bank_end = bank_start + bank_size
    bank_source_columns = source_columns[bank_start:bank_end]
    frame_bytes = channel_count * DTYPE.itemsize
    input_bytes = input_path.stat().st_size
    if input_bytes == 0:
        raise ValueError("input DAT file is empty")
    if input_bytes % frame_bytes:
        raise ValueError(
            f"file size {input_bytes:,} is not divisible by the "
            f"{frame_bytes}-byte frame size ({channel_count} int16 channels)"
        )

    frame_count = input_bytes // frame_bytes
    chunk_bytes = chunk_mib * 1024 * 1024
    frames_per_chunk = max(1, chunk_bytes // frame_bytes)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not quiet:
        preview = ",".join(str(int(v)) for v in source_columns[bank_start : bank_start + min(8, bank_size)])
        print(f"Input:  {input_path}")
        print(f"Output: {output_path}")
        print(
            f"Frames: {frame_count:,}; channels: {channel_count}; "
            f"format: little-endian int16; size: {input_bytes / (1024 ** 3):.3f} GiB"
        )
        print(
            f"Bank {bank} restoration after {input_layout}: measured raw rotation "
            f"{acquisition_rotation:+d}; first source columns "
            f"[{preview}{',...' if bank_size > 8 else ''}]"
        )

    started = time.perf_counter()
    last_report = started
    source = np.memmap(input_path, dtype=DTYPE, mode="r", shape=(frame_count, channel_count))
    destination: np.memmap | None = None

    try:
        destination = np.memmap(
            output_path,
            dtype=DTYPE,
            mode="w+",
            shape=(frame_count, channel_count),
        )
        for start in range(0, frame_count, frames_per_chunk):
            end = min(start + frames_per_chunk, frame_count)
            # Read every source byte once, then reorder the selected bank in RAM.
            # NumPy materializes the advanced-index RHS before assigning it, so
            # wrapping 31->0 cannot overwrite a value that is still needed.
            corrected = np.array(source[start:end, :], dtype=DTYPE, copy=True, order="C")
            corrected[:, bank_start:bank_end] = corrected[:, bank_source_columns]
            destination[start:end, :] = corrected

            now = time.perf_counter()
            if not quiet and (now - last_report >= 2.0 or end == frame_count):
                processed_bytes = end * frame_bytes
                speed = processed_bytes / max(now - started, 1e-9) / (1024 ** 2)
                remaining = (input_bytes - processed_bytes) / max(speed * 1024 ** 2, 1.0)
                print(
                    f"{100.0 * end / frame_count:6.2f}%  "
                    f"{speed:8.1f} MiB/s  ETA {remaining:6.1f} s",
                    flush=True,
                )
                last_report = now
        destination.flush()
    except BaseException:
        if destination is not None:
            del destination
        del source
        try:
            output_path.unlink()
        except OSError:
            pass
        raise
    finally:
        if destination is not None:
            del destination
        if "source" in locals():
            del source

    output_bytes = output_path.stat().st_size
    if output_bytes != input_bytes:
        raise RuntimeError(
            f"output size mismatch: expected {input_bytes:,}, got {output_bytes:,} bytes"
        )

    # Cheap deterministic verification without rereading the whole file: check
    # the first, middle and final frames against the exact source permutation.
    source_check = np.memmap(input_path, dtype=DTYPE, mode="r", shape=(frame_count, channel_count))
    output_check = np.memmap(output_path, dtype=DTYPE, mode="r", shape=(frame_count, channel_count))
    probe_frames = sorted({0, frame_count // 2, frame_count - 1})
    for frame in probe_frames:
        if not np.array_equal(output_check[frame], source_check[frame, source_columns]):
            del output_check
            del source_check
            raise RuntimeError(f"post-write verification failed at frame {frame}")
    del output_check
    del source_check

    elapsed = time.perf_counter() - started
    speed_mib_s = input_bytes / max(elapsed, 1e-9) / (1024 ** 2)
    result: dict[str, float | int | str] = {
        "input": str(input_path),
        "output": str(output_path),
        "frames": frame_count,
        "channels": channel_count,
        "input_layout": input_layout,
        "bytes": input_bytes,
        "elapsed_seconds": elapsed,
        "speed_mib_s": speed_mib_s,
    }
    if not quiet:
        print(
            f"PASS: wrote {output_bytes:,} bytes in {elapsed:.2f} s "
            f"({speed_mib_s:.1f} MiB/s); original left unchanged."
        )
    return result


def self_test() -> int:
    frames = 257
    channels = 64
    logical_raw = (
        np.arange(frames, dtype=np.int32)[:, None] * 100
        + np.arange(channels, dtype=np.int32)[None, :]
    ).astype(DTYPE)

    # Model the full real pipeline: FM57 rotates the first raw Intan bank, then
    # WILD Console applies its normal CE64 channel reordering during export.
    fm57_raw = logical_raw.copy()
    fm57_raw[:, :32] = logical_raw[:, np.r_[np.arange(1, 32), 0]]
    expected_export = logical_raw[:, CE64_WILD_SOURCE_COLUMNS]
    affected_export = fm57_raw[:, CE64_WILD_SOURCE_COLUMNS]

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source_path = root / "affected.dat"
        output_path = root / "repaired" / "amplifier.dat"
        affected_export.tofile(source_path)
        restore_dat(source_path, output_path, chunk_mib=1, quiet=True)
        restored = np.fromfile(output_path, dtype=DTYPE).reshape(frames, channels)

        np.testing.assert_array_equal(restored, expected_export)
        np.testing.assert_array_equal(restored[:, 32:], affected_export[:, 32:])
        np.testing.assert_array_equal(
            np.fromfile(source_path, dtype=DTYPE), affected_export.ravel()
        )

        expected_columns = np.asarray(
            [
                30, 0, 28, 31, 26, 29, 24, 27, 22, 25, 20, 23, 18, 21,
                16, 19, 17, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4,
                3, 2, 1,
                *range(32, 64),
            ],
            dtype=np.int64,
        )
        np.testing.assert_array_equal(
            restored_source_columns(
                channel_count=64,
                bank=0,
                bank_size=32,
                acquisition_rotation=1,
                input_layout="wild-export",
            ),
            expected_columns,
        )

        # Applying the inverse measured rotation reconstructs the affected
        # export, which also proves the post-map transform is bijective.
        round_trip_path = root / "round-trip.dat"
        restore_dat(
            output_path,
            round_trip_path,
            acquisition_rotation=-1,
            chunk_mib=1,
            quiet=True,
        )
        round_trip = np.fromfile(round_trip_path, dtype=DTYPE).reshape(frames, channels)
        np.testing.assert_array_equal(round_trip, affected_export)

        # Preserve explicit raw-stream support and its simple adjacent inverse.
        raw_path = root / "raw.dat"
        raw_fixed_path = root / "raw-fixed.dat"
        fm57_raw.tofile(raw_path)
        restore_dat(
            raw_path,
            raw_fixed_path,
            input_layout="raw",
            chunk_mib=1,
            quiet=True,
        )
        raw_fixed = np.fromfile(raw_fixed_path, dtype=DTYPE).reshape(frames, channels)
        np.testing.assert_array_equal(raw_fixed, logical_raw)

    print(
        "SELF-TEST PASS: FM57 raw fault -> WILD export -> repaired amplifier.dat; "
        "mapping direction, unaffected channels, raw mode, size, and source preservation"
    )
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Repair the FM57 Intan bank rotation in a channel-interleaved "
            "little-endian int16 DAT file after WILD Console export."
        )
    )
    parser.add_argument("input", nargs="?", type=Path, help="input .dat file")
    parser.add_argument(
        "--output",
        type=Path,
        help="output path (default: v57_channel_repaired/amplifier.dat beside input)",
    )
    parser.add_argument("--channels", type=int, default=64, help="channels per frame (default: 64)")
    parser.add_argument("--bank", type=int, default=0, help="zero-based bank to correct (default: 0)")
    parser.add_argument("--bank-size", type=int, default=32, help="channels in the bank (default: 32)")
    parser.add_argument(
        "--acquisition-rotation",
        type=int,
        default=1,
        help="measured stored-data rotation; correction applies its inverse (default: +1)",
    )
    parser.add_argument(
        "--input-layout",
        choices=("wild-export", "raw"),
        default="wild-export",
        help=(
            "input column layout: WILD-exported amplifier data (default), or "
            "unmapped raw Intan columns"
        ),
    )
    parser.add_argument("--chunk-mib", type=int, default=128, help="working chunk size in MiB (default: 128)")
    parser.add_argument("--force", action="store_true", help="replace an existing output file")
    parser.add_argument("--quiet", action="store_true", help="suppress progress output")
    parser.add_argument("--self-test", action="store_true", help="run deterministic built-in tests")
    args = parser.parse_args(argv)
    if not args.self_test and args.input is None:
        parser.error("input is required unless --self-test is used")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.self_test:
        return self_test()

    output_path = args.output or _default_output(args.input)
    try:
        restore_dat(
            args.input,
            output_path,
            channel_count=args.channels,
            bank=args.bank,
            bank_size=args.bank_size,
            acquisition_rotation=args.acquisition_rotation,
            input_layout=args.input_layout,
            chunk_mib=args.chunk_mib,
            force=args.force,
            quiet=args.quiet,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
