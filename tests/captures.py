"""Helpers to read the captured traffic fixtures in tests/fixtures/."""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def read_capture(path: Path) -> list[tuple[float, str, bytes]]:
    """Parse a fixture file into (seconds, direction, frame bytes) tuples."""
    frames = []
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        elapsed, direction, data = line.split()
        frames.append((float(elapsed), direction, bytes.fromhex(data)))
    return frames


def official_app_frames() -> list[bytes]:
    """Every frame sent by the official app, from all fixtures except our own sessions."""
    paths = sorted(p for p in FIXTURES.glob("*.hex") if not p.name.startswith("device-"))
    return [frame for path in paths for _, _, frame in read_capture(path)]
