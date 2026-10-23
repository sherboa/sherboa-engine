# This module tests the accumulated analysis quota through the FastAPI endpoint.

import pytest
from fastapi.testclient import TestClient
import os
import tempfile

os.environ["SHERBOA_USAGE_DB_PATH"] = os.path.join(
    tempfile.gettempdir(),
    "sherboa-usage-test.db",
)

import main
import rate_limiter


@pytest.fixture
def client(tmp_path):
    """
    Provide an isolated API client and temporary usage database.
    """

    # Save the original limiter so it can be restored after the test
    original_limiter = main.usage_limiter

    # Use a dedicated SQLite database for this test
    main.usage_limiter = main.UsageLimiter(tmp_path / "usage.db")

    # Reset the in-memory short-window limiter state.
    with rate_limiter.rate_limit_lock:
        rate_limiter.request_timestamps.clear()
        rate_limiter.analysis_timestamps.clear()
        rate_limiter.last_rate_limit_cleanup = 0.0

    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        main.usage_limiter = original_limiter

        with rate_limiter.rate_limit_lock:
            rate_limiter.request_timestamps.clear()
            rate_limiter.analysis_timestamps.clear()
            rate_limiter.last_rate_limit_cleanup = 0.0


def test_invalid_video_does_not_consume_daily_quota(client, monkeypatch):
    """
    Invalid video uploads must not consume the accumulated quota.
    """

    # Make the first video fail validation before quality processing
    monkeypatch.setattr(main, "is_valid_video", lambda path: False)

    response = client.post(
        "/vmaf",
        files={
            "reference": ("reference.mp4", b"not a valid video", "video/mp4"),
            "distorted": ("distorted.mp4", b"not a valid video", "video/mp4"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid video file"

    # The rejected upload must not have been recorded in the daily quota.
    with main.usage_limiter._connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM analysis_usage"
        ).fetchone()[0]

    assert count == 0


def test_valid_analysis_consumes_one_daily_quota(client, monkeypatch):
    """
    A validated analysis consumes quota when quality processing starts.
    """

    monkeypatch.setattr(main, "is_valid_video", lambda path: True)
    monkeypatch.setattr(main, "get_video_dimensions", lambda path: (1280, 720))
    monkeypatch.setattr(main, "get_video_duration", lambda path: 10.0)
    monkeypatch.setattr(main, "are_durations_compatible", lambda ref, dist: True)
    monkeypatch.setattr(main, "get_video_metadata", lambda path: {"duration": 10.0})

    # Simulate successful quality processing without running FFmpeg
    monkeypatch.setattr(
        main,
        "video_compare",
        lambda reference, distorted: {
            "vmaf": {"mean": 95.0},
            "psnr": {"mean": 40.0},
            "ssim": {"mean": 0.98},
        },
    )

    response = client.post(
        "/vmaf",
        files={
            "reference": ("reference.mp4", b"fake reference data", "video/mp4"),
            "distorted": ("distorted.mp4", b"fake distorted data", "video/mp4"),
        },
    )

    assert response.status_code == 200

    with main.usage_limiter._connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM analysis_usage"
        ).fetchone()[0]

    assert count == 1


def test_exhausted_daily_quota_returns_429_and_retry_after(client, monkeypatch):
    """
    An exhausted daily quota must reject analysis and report retry time.
    """

    monkeypatch.setattr(main, "is_valid_video", lambda path: True)
    monkeypatch.setattr(main, "get_video_dimensions", lambda path: (1280, 720))
    monkeypatch.setattr(main, "get_video_duration", lambda path: 10.0)
    monkeypatch.setattr(main, "are_durations_compatible", lambda ref, dist: True)
    monkeypatch.setattr(main, "get_video_metadata", lambda path: {"duration": 10.0})
    monkeypatch.setattr(
        main,
        "video_compare",
        lambda reference, distorted: {
            "vmaf": {"mean": 95.0},
            "psnr": {"mean": 40.0},
            "ssim": {"mean": 0.98},
        },
    )

    client_ip = "testclient"

    # Fill the daily quota directly without sending 20 HTTP requests
    for _ in range(main.USAGE_LIMIT_MAX_ANALYSES):
        main.usage_limiter.register_analysis(client_ip)

    response = client.post(
        "/vmaf",
        files={
            "reference": ("reference.mp4", b"fake reference data", "video/mp4"),
            "distorted": ("distorted.mp4", b"fake distorted data", "video/mp4"),
        },
    )

    assert response.status_code == 429
    assert "analysis limit reached" in response.json()["detail"].lower()
    assert int(response.headers["Retry-After"]) > 0

    # Rejected requests must not add another daily usage record
    with main.usage_limiter._connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM analysis_usage WHERE client_ip = ?",
            (client_ip,),
        ).fetchone()[0]

    assert count == main.USAGE_LIMIT_MAX_ANALYSES


def test_processing_failure_still_consumes_daily_quota(client, monkeypatch):
    """
    A processing failure still consumes quota once quality processing starts.
    """

    monkeypatch.setattr(main, "is_valid_video", lambda path: True)
    monkeypatch.setattr(main, "get_video_dimensions", lambda path: (1280, 720))
    monkeypatch.setattr(main, "get_video_duration", lambda path: 10.0)
    monkeypatch.setattr(main, "are_durations_compatible", lambda ref, dist: True)
    monkeypatch.setattr(main, "get_video_metadata", lambda path: {"duration": 10.0})

    def fail_video_compare(reference, distorted):
        raise RuntimeError("Simulated processing failure")

    monkeypatch.setattr(main, "video_compare", fail_video_compare)

    response = client.post(
        "/vmaf",
        files={
            "reference": ("reference.mp4", b"fake reference data", "video/mp4"),
            "distorted": ("distorted.mp4", b"fake distorted data", "video/mp4"),
        },
    )

    assert response.status_code == 504

    with main.usage_limiter._connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM analysis_usage WHERE client_ip = ?",
            ("testclient",),
        ).fetchone()[0]

    assert count == 1



def test_valid_analysis_generates_thumbnails_and_returns_analysis_id(client, monkeypatch, tmp_path):
    """
    A successful analysis generates thumbnails for both videos and returns
    an analysis ID while preserving the existing quality metrics.
    """
    import thumbnails

    monkeypatch.setattr(main, "is_valid_video", lambda path: True)
    monkeypatch.setattr(main, "get_video_dimensions", lambda path: (1280, 720))
    monkeypatch.setattr(main, "get_video_duration", lambda path: 10.0)
    monkeypatch.setattr(main, "are_durations_compatible", lambda ref, dist: True)
    monkeypatch.setattr(main, "get_video_metadata", lambda path: {"duration": 10.0})

    monkeypatch.setattr(
        main,
        "video_compare",
        lambda reference, distorted: {
            "vmaf": {"mean": 95.0},
            "psnr": {"mean": 40.0},
            "ssim": {"mean": 0.98},
        },
    )

    thumbnail_calls = []

    def fake_generate_thumbnails(video_path, output_dir):
        thumbnail_calls.append((video_path, output_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        thumbnail = output_dir / "thumbnail_0001.jpg"
        thumbnail.write_bytes(b"fake thumbnail")
        return [thumbnail]

    monkeypatch.setattr(
        thumbnails,
        "generate_thumbnails",
        fake_generate_thumbnails,
    )

    response = client.post(
        "/vmaf",
        files={
            "reference": ("reference.mp4", b"fake reference data", "video/mp4"),
            "distorted": ("distorted.mp4", b"fake distorted data", "video/mp4"),
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["vmaf"] == {"mean": 95.0}
    assert data["psnr"] == {"mean": 40.0}
    assert data["ssim"] == {"mean": 0.98}
    assert data["video"] == {"duration": 10.0}
    assert data["distorted_video"] == {"duration": 10.0}
    assert data["thumbnails_available"] is True
    assert isinstance(data["analysis_id"], str)
    assert data["analysis_id"]

    assert len(thumbnail_calls) == 2



def test_thumbnail_failure_does_not_fail_analysis_or_leave_partial_files(client, monkeypatch, tmp_path):
    """
    Thumbnail failures must not invalidate quality metrics or leave partial files.
    """
    import thumbnails

    monkeypatch.setattr(main, "is_valid_video", lambda path: True)
    monkeypatch.setattr(main, "get_video_dimensions", lambda path: (1280, 720))
    monkeypatch.setattr(main, "get_video_duration", lambda path: 10.0)
    monkeypatch.setattr(main, "are_durations_compatible", lambda ref, dist: True)
    monkeypatch.setattr(main, "get_video_metadata", lambda path: {"duration": 10.0})
    monkeypatch.setattr(
        main,
        "video_compare",
        lambda reference, distorted: {
            "vmaf": {"mean": 95.0},
            "psnr": {"mean": 40.0},
            "ssim": {"mean": 0.98},
        },
    )

    analysis_dir = tmp_path / "analysis-failure"
    monkeypatch.setattr(
        thumbnails,
        "create_analysis_thumbnail_dir",
        lambda: analysis_dir,
    )

    thumbnail_calls = []

    def fail_second_thumbnail_generation(video_path, output_dir):
        thumbnail_calls.append(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if len(thumbnail_calls) == 1:
            (output_dir / "partial.jpg").write_bytes(b"partial thumbnail")
            return [output_dir / "partial.jpg"]

        raise RuntimeError("Simulated thumbnail generation failure")

    monkeypatch.setattr(
        thumbnails,
        "generate_thumbnails",
        fail_second_thumbnail_generation,
    )

    response = client.post(
        "/vmaf",
        files={
            "reference": ("reference.mp4", b"fake reference data", "video/mp4"),
            "distorted": ("distorted.mp4", b"fake distorted data", "video/mp4"),
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["vmaf"] == {"mean": 95.0}
    assert data["psnr"] == {"mean": 40.0}
    assert data["ssim"] == {"mean": 0.98}
    assert data["thumbnails_available"] is False
    assert data["analysis_id"] is None

    assert len(thumbnail_calls) == 2
    assert not analysis_dir.exists()



@pytest.mark.parametrize("rejection_reason", ["invalid_video", "daily_quota"])
def test_rejected_analysis_does_not_generate_thumbnails(client, monkeypatch, rejection_reason):
    """
    Invalid videos and exhausted daily quotas must not generate thumbnails.
    """
    import thumbnails

    thumbnail_calls = []

    def track_thumbnail_generation(video_path, output_dir):
        thumbnail_calls.append(output_dir)
        return []

    monkeypatch.setattr(
        thumbnails,
        "generate_thumbnails",
        track_thumbnail_generation,
    )

    if rejection_reason == "invalid_video":
        monkeypatch.setattr(main, "is_valid_video", lambda path: False)
    else:
        monkeypatch.setattr(main, "is_valid_video", lambda path: True)
        monkeypatch.setattr(main, "get_video_dimensions", lambda path: (1280, 720))
        monkeypatch.setattr(main, "get_video_duration", lambda path: 10.0)
        monkeypatch.setattr(main, "are_durations_compatible", lambda ref, dist: True)
        monkeypatch.setattr(main, "get_video_metadata", lambda path: {"duration": 10.0})

        for _ in range(main.USAGE_LIMIT_MAX_ANALYSES):
            main.usage_limiter.register_analysis("testclient")

    response = client.post(
        "/vmaf",
        files={
            "reference": ("reference.mp4", b"fake reference data", "video/mp4"),
            "distorted": ("distorted.mp4", b"fake distorted data", "video/mp4"),
        },
    )

    expected_status = 400 if rejection_reason == "invalid_video" else 429
    assert response.status_code == expected_status
    assert thumbnail_calls == []
