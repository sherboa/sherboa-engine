# This module tests the synchronization offset contract of the /vmaf endpoint; including default values, accepted offsets, and rejection of non-finite values.
import os
import tempfile

os.environ["SHERBOA_USAGE_DB_PATH"] = os.path.join(
    tempfile.gettempdir(),
    "sherboa-offset-test.db",
)

import main


def test_vmaf_accepts_offset_values(client, monkeypatch):
    """
    The endpoint accepts positive, negative, and zero offsets.
    """

    captured_offsets = []

    monkeypatch.setattr(main, "is_valid_video", lambda path: True)
    monkeypatch.setattr(main, "get_video_dimensions", lambda path: (1280, 720))
    monkeypatch.setattr(main, "get_video_duration", lambda path: 10.0)
    monkeypatch.setattr(main, "are_durations_compatible", lambda ref, dist: True)
    monkeypatch.setattr(main, "get_video_metadata", lambda path: {"duration": 10.0})
 
    def fake_video_compare(reference, distorted, offset=0.0):
        captured_offsets.append(offset)
        return {
            "vmaf": {"mean": 95.0},
            "psnr": {"mean": 40.0},
            "ssim": {"mean": 0.98},
        }

    monkeypatch.setattr(main, "video_compare", fake_video_compare)

    for offset in ("0", "1.25", "-1.25"):
        response = client.post(
            "/vmaf",
            data={"offset": offset},
            files={
                "reference": ("reference.mp4", b"reference data", "video/mp4"),
                "distorted": ("distorted.mp4", b"distorted data", "video/mp4"),
            },
        )

        assert response.status_code == 200
    assert captured_offsets == [0.0, 1.25, -1.25]


def test_vmaf_rejects_non_finite_offset(client, monkeypatch):
    """
    Non-finite offsets are rejected before video validation or quota use.
    """

    def unexpected_validation(path):
        raise AssertionError("video validation must not run")

    monkeypatch.setattr(main, "is_valid_video", unexpected_validation)

    for offset in ("nan", "inf", "-inf"):
        response = client.post(
            "/vmaf",
            data={"offset": offset},
            files={
                "reference": ("reference.mp4", b"reference data", "video/mp4"),
                "distorted": ("distorted.mp4", b"distorted data", "video/mp4"),
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "offset must be a finite number"

    with main.usage_limiter._connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM analysis_usage"
        ).fetchone()[0]

    assert count == 0


def test_vmaf_offset_defaults_to_zero(client, monkeypatch):
    """
    The endpoint accepts requests that omit the offset.
    """

    monkeypatch.setattr(main, "is_valid_video", lambda path: True)
    monkeypatch.setattr(main, "get_video_dimensions", lambda path: (1280, 720))
    monkeypatch.setattr(main, "get_video_duration", lambda path: 10.0)
    monkeypatch.setattr(main, "are_durations_compatible", lambda ref, dist: True)
    monkeypatch.setattr(main, "get_video_metadata", lambda path: {"duration": 10.0})
    monkeypatch.setattr(
        main,
        "video_compare",
        lambda reference, distorted, offset=0.0: {
            "vmaf": {"mean": 95.0},
            "psnr": {"mean": 40.0},
            "ssim": {"mean": 0.98},
        },
    )

    response = client.post(
        "/vmaf",
        files={
            "reference": ("reference.mp4", b"reference data", "video/mp4"),
            "distorted": ("distorted.mp4", b"distorted data", "video/mp4"),
        },
    )

    assert response.status_code == 200


def test_vmaf_rejects_unsupported_frame_rates(client, monkeypatch):
    monkeypatch.setattr(main, "is_valid_video", lambda path: True)
    monkeypatch.setattr(main, "get_video_dimensions", lambda path: (1280, 720))
    monkeypatch.setattr(main, "get_video_duration", lambda path: 10.0)
    monkeypatch.setattr(main, "are_durations_compatible", lambda ref, dist: True)
    monkeypatch.setattr(main, "get_video_metadata", lambda path: {"duration": 10.0})

    def unsupported_frame_rate(*args, **kwargs):
        raise main.UnsupportedFrameRateError(
            "videos with different frame rates are not supported yet."
        )

    monkeypatch.setattr(main, "video_compare", unsupported_frame_rate)

    response = client.post(
        "/vmaf",
        data={"offset": "0"},
        files={
            "reference": ("reference.mp4", b"reference", "video/mp4"),
            "distorted": ("distorted.mp4", b"distorted", "video/mp4"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "videos with different frame rates are not supported yet."
    )