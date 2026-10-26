# This module tests the calculation of the common temporal interval between reference and distorted videos, including positive and negative offsets, non-finite values, and cases with no overlap.
import pytest
from ffprobe import get_overlap_interval


@pytest.mark.parametrize(
    ("reference_duration", "distorted_duration", "offset", "expected"),
    [
        (10.0, 10.0, 0.0, (0.0, 0.0, 10.0)),
        (10.0, 10.0, 2.0, (0.0, 2.0, 8.0)),
        (10.0, 10.0, -2.0, (2.0, 0.0, 8.0)),
        (12.0, 8.0, 1.0, (0.0, 1.0, 7.0)),
        (8.0, 12.0, -1.0, (1.0, 0.0, 7.0)),
    ],
)
def test_get_overlap_interval(
    reference_duration,
    distorted_duration,
    offset,
    expected,
):
    assert get_overlap_interval(
        reference_duration,
        distorted_duration,
        offset,
    ) == expected


@pytest.mark.parametrize("offset", [float("nan"), float("inf"), float("-inf")])
def test_get_overlap_interval_rejects_non_finite_offset(offset):
    with pytest.raises(ValueError, match="finite"):
        get_overlap_interval(10.0, 10.0, offset)


@pytest.mark.parametrize("offset", [10.0, -10.0, 11.0, -11.0])
def test_get_overlap_interval_rejects_no_overlap(offset):
    with pytest.raises(ValueError, match="no overlapping"):
        get_overlap_interval(10.0, 10.0, offset)

@pytest.mark.parametrize(
    ("reference_duration", "distorted_duration"),
    [
        (0.0, 10.0),
        (10.0, 0.0),
        (-1.0, 10.0),
        (10.0, -1.0),
        (float("nan"), 10.0),
        (10.0, float("nan")),
        (float("inf"), 10.0),
        (10.0, float("inf")),
        (float("-inf"), 10.0),
        (10.0, float("-inf")),
    ],
)
def test_get_overlap_interval_rejects_invalid_durations(reference_duration, distorted_duration,):
    with pytest.raises(ValueError, match="durations must be finite and greater than zero"):
        get_overlap_interval(reference_duration, distorted_duration, 0.0)