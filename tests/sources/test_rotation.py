import pytest

from minitela.protocol import tags
from minitela.sources.rotation import RotationSource


def test_cycles_through_the_pages():
    source = RotationSource([4, 1, 5], seconds=20)
    assert source.interval == 20
    assert [source.read()[tags.PAGE] for _ in range(5)] == [4, 1, 5, 4, 1]


def test_single_page():
    source = RotationSource([3], seconds=10)
    assert [source.read()[tags.PAGE] for _ in range(2)] == [3, 3]


@pytest.mark.parametrize(("pages", "seconds"), [([], 10), ([1, 2], 0), ([1], -5)])
def test_invalid(pages, seconds):
    with pytest.raises(ValueError):
        RotationSource(pages, seconds)
