"""Sanity checks for the captured traffic fixtures."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
HEX_FILES = sorted(FIXTURES.glob("*.hex"))


def read_frames(path: Path) -> list[tuple[float, str, bytes]]:
    frames = []
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        elapsed, direction, data = line.split()
        frames.append((float(elapsed), direction, bytes.fromhex(data)))
    return frames


def test_fixtures_exist():
    assert HEX_FILES


@pytest.mark.parametrize("path", HEX_FILES, ids=lambda p: p.name)
def test_frames_are_well_formed(path):
    frames = read_frames(path)
    assert frames
    times = [elapsed for elapsed, _, _ in frames]
    assert times == sorted(times)
    for _, direction, frame in frames:
        assert direction in "<>"
        assert frame[:2] == b"AH"
        assert frame[-2:] == b"MI"
        length = int.from_bytes(frame[2:4]) & 0x7FFF
        assert len(frame) == length + 8
