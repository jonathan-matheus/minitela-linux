"""Sanity checks for the captured traffic fixtures."""

import pytest
from captures import FIXTURES, read_capture

HEX_FILES = sorted(FIXTURES.glob("*.hex"))


def test_fixtures_exist():
    assert HEX_FILES


@pytest.mark.parametrize("path", HEX_FILES, ids=lambda p: p.name)
def test_frames_are_well_formed(path):
    frames = read_capture(path)
    assert frames
    times = [elapsed for elapsed, _, _ in frames]
    assert times == sorted(times)
    for _, direction, frame in frames:
        assert direction in "<>"
        assert frame[:2] == b"AH"
        assert frame[-2:] == b"MI"
        length = int.from_bytes(frame[2:4]) & 0x7FFF
        assert len(frame) == length + 8
