#!/usr/bin/env python3
"""Download Suno tracks by song ID or /song/<id> URL as MP3 files."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


SONG_ID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def parse_song_arg(value: str) -> tuple[str | None, str]:
    name = None
    raw = value
    if "=" in value:
        name, raw = value.split("=", 1)
        name = sanitize_name(name)
    match = SONG_ID_RE.search(raw)
    if not match:
        raise ValueError(f"could not find a Suno song UUID in: {value}")
    song_id = match.group(0).lower()
    return name, song_id


def sanitize_name(value: str) -> str:
    value = value.strip().replace("\\", "_").replace("/", "_")
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value.strip("._-") or "suno_track"


def download(song_id: str, output: Path) -> int:
    url = f"https://cdn1.suno.ai/{song_id}.mp3"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "audio/mpeg,audio/*;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        content_type = response.headers.get("content-type", "")
        data = response.read()
    if not content_type.lower().startswith("audio/"):
        raise ValueError(f"{url} returned non-audio content-type: {content_type}")
    output.write_bytes(data)
    return len(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="/mnt/c/Users/dhaup/Downloads",
        help="Directory for downloaded MP3 files. Defaults to the Windows Downloads folder.",
    )
    parser.add_argument(
        "songs",
        nargs="+",
        help="Suno song UUIDs, /song/<uuid> URLs, or filename=uuid mappings.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    failed = False
    for song_arg in args.songs:
        try:
            name, song_id = parse_song_arg(song_arg)
            filename = f"{name or song_id}.mp3"
            output = output_dir / filename
            size = download(song_id, output)
            print(f"wrote {output} ({size} bytes)")
        except (OSError, ValueError, urllib.error.URLError) as exc:
            failed = True
            print(f"failed {song_arg}: {exc}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
