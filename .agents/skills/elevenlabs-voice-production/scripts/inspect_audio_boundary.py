#!/usr/bin/env python3
"""Measure common cutoff and leading-transient signatures at a clip boundary."""

from __future__ import annotations

import argparse
import array
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any


FULL_SCALE = 32768.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", required=True, type=Path)
    parser.add_argument("--right", required=True, type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--sample-rate", type=int, default=48_000)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def decode(path: Path, ffmpeg: str, sample_rate: int) -> array.array[int]:
    result = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    samples = array.array("h")
    samples.frombytes(result.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def dbfs(samples: array.array[int]) -> float:
    if not samples:
        return float("-inf")
    mean_square = sum(float(value) * value for value in samples) / len(samples)
    if mean_square <= 0:
        return float("-inf")
    return 20 * math.log10(math.sqrt(mean_square) / FULL_SCALE)


def window(
    samples: array.array[int],
    start_ms: float,
    end_ms: float,
    sample_rate: int,
) -> array.array[int]:
    duration_ms = len(samples) * 1000 / sample_rate
    start_ms = start_ms if start_ms >= 0 else duration_ms + start_ms
    end_ms = end_ms if end_ms > 0 else duration_ms + end_ms
    start = max(0, min(len(samples), round(start_ms * sample_rate / 1000)))
    end = max(start, min(len(samples), round(end_ms * sample_rate / 1000)))
    return samples[start:end]


def finite_db(value: float) -> float | None:
    return round(value, 1) if math.isfinite(value) else None


def inspect(
    left: array.array[int],
    right: array.array[int],
    sample_rate: int,
) -> dict[str, Any]:
    left_windows = {
        "tail160To80Db": finite_db(
            dbfs(window(left, -160, -80, sample_rate))
        ),
        "tail80To40Db": finite_db(
            dbfs(window(left, -80, -40, sample_rate))
        ),
        "tail40To20Db": finite_db(
            dbfs(window(left, -40, -20, sample_rate))
        ),
        "final20Db": finite_db(dbfs(window(left, -20, 0, sample_rate))),
    }
    right_windows = {
        "head0To40Db": finite_db(dbfs(window(right, 0, 40, sample_rate))),
        "head40To80Db": finite_db(
            dbfs(window(right, 40, 80, sample_rate))
        ),
        "head80To200Db": finite_db(
            dbfs(window(right, 80, 200, sample_rate))
        ),
    }
    final_db = left_windows["final20Db"]
    head_db = right_windows["head0To40Db"]
    gap_db = right_windows["head40To80Db"]
    speech_db = right_windows["head80To200Db"]
    return {
        "sampleRate": sample_rate,
        "leftDuration": round(len(left) / sample_rate, 6),
        "rightDuration": round(len(right) / sample_rate, 6),
        "left": left_windows,
        "right": right_windows,
        "cutoffRisk": final_db is not None and final_db > -48,
        "isolatedHeadTransientRisk": (
            head_db is not None
            and gap_db is not None
            and speech_db is not None
            and head_db > -48
            and gap_db <= -50
            and speech_db > -35
        ),
    }


def main() -> None:
    args = parse_args()
    if args.sample_rate <= 0:
        raise SystemExit("--sample-rate must be positive")
    report = inspect(
        decode(args.left, args.ffmpeg, args.sample_rate),
        decode(args.right, args.ffmpeg, args.sample_rate),
        args.sample_rate,
    )
    if args.json:
        print(json.dumps(report, indent=2))
        return
    print(f"left={args.left}")
    print(f"right={args.right}")
    for side in ("left", "right"):
        print(side)
        for name, value in report[side].items():
            label = "-inf" if value is None else f"{value:.1f}"
            print(f"  {name}={label} dBFS")
    print(f"cutoff_risk={str(report['cutoffRisk']).lower()}")
    print(
        "isolated_head_transient_risk="
        f"{str(report['isolatedHeadTransientRisk']).lower()}"
    )


if __name__ == "__main__":
    main()
