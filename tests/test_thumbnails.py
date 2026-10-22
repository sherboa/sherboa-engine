# This is the module for testing the thumbnail generation: it covers JPEG extraction, output dimensions, expired-directory cleanup, invalid input handling, and cleanup after FFmpeg failures.

import shutil
import subprocess
import time
from pathlib import Path
import pytest
import thumbnails


@pytest.fixture
def thumbnail_root(tmp_path, monkeypatch):
    """
    Use an isolated thumbnail root for each test.
    """
    root = tmp_path / "thumbnails"
    monkeypatch.setattr(thumbnails, "THUMBNAIL_ROOT", root)
    return root



@pytest.fixture
def sample_video(tmp_path):
    """
    Generate a short test video using FFmpeg.
    """
    if shutil.which(thumbnails.FFMPEG) is None:
        pytest.skip("FFmpeg is not installed.")

    video = tmp_path / "sample.mp4"
    command = [
        thumbnails.FFMPEG,
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-y",
        "-f", "lavfi",
        "-i", "testsrc=size=640x360:rate=10:duration=3",
        "-c:v", "mpeg4",
        "-pix_fmt", "yuv420p",
        str(video),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return video



def test_generate_thumbnails(thumbnail_root, sample_video):
    analysis_dir = thumbnails.create_analysis_thumbnail_dir()
    analysis_dir.mkdir()
    (analysis_dir / ".generating").touch()

    output_dir = analysis_dir / "reference"
    generated = thumbnails.generate_thumbnails(
        str(sample_video),
        output_dir,
    )

    assert len(generated) == 3
    assert all(path.is_file() for path in generated)
    assert all(path.suffix == ".jpg" for path in generated)
    assert all(path.parent == output_dir for path in generated)
    assert (analysis_dir / ".generating").exists()

    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(generated[0]),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert probe.stdout.strip() == "320x180"



def test_cleanup_removes_expired_directories(thumbnail_root):
    expired = thumbnail_root / "expired"
    current = thumbnail_root / "current"
    expired.mkdir(parents=True)
    current.mkdir()

    now = time.time()
    old_timestamp = now - thumbnails.THUMBNAIL_RETENTION_SECONDS - 10
    current_timestamp = now - 60

    import os

    os.utime(expired, (old_timestamp, old_timestamp))
    os.utime(current, (current_timestamp, current_timestamp))

    removed = thumbnails.cleanup_expired_thumbnails(thumbnail_root, now=now)

    assert removed == 1
    assert not expired.exists()
    assert current.exists()



def test_cleanup_skips_directories_being_generated(thumbnail_root):
    generating = thumbnail_root / "generating"
    generating.mkdir(parents=True)
    (generating / ".generating").touch()

    now = time.time()
    old_timestamp = now - thumbnails.THUMBNAIL_RETENTION_SECONDS - 10

    import os
    os.utime(generating, (old_timestamp, old_timestamp))

    removed = thumbnails.cleanup_expired_thumbnails(thumbnail_root, now=now)

    assert removed == 0
    assert generating.exists()
    assert (generating / ".generating").exists()



def test_cleanup_removes_stale_generation_marker(thumbnail_root):
    abandoned = thumbnail_root / "abandoned"
    abandoned.mkdir(parents=True)

    marker = abandoned / ".generating"
    marker.touch()

    now = time.time()
    old_timestamp = now - thumbnails.THUMBNAIL_RETENTION_SECONDS - 10

    import os
    os.utime(marker, (old_timestamp, old_timestamp))

    removed = thumbnails.cleanup_expired_thumbnails(
        thumbnail_root,
        now=now,
    )

    assert removed == 1
    assert not abandoned.exists()



def test_missing_video_raises_file_not_found(thumbnail_root, tmp_path):
    output_dir = thumbnail_root / "analysis-1"
    missing_video = tmp_path / "missing.mp4"

    with pytest.raises(FileNotFoundError):
        thumbnails.generate_thumbnails(str(missing_video), output_dir)



def test_output_directory_must_be_inside_thumbnail_root(sample_video, thumbnail_root, tmp_path):
    output_dir = tmp_path / "outside"

    with pytest.raises(ValueError, match="output directory must be"):
        thumbnails.generate_thumbnails(str(sample_video), output_dir)



def test_ffmpeg_failure_cleans_partial_output(
    thumbnail_root, sample_video, monkeypatch
):
    analysis_dir = thumbnails.create_analysis_thumbnail_dir()
    analysis_dir.mkdir()
    (analysis_dir / ".generating").touch()
    output_dir = analysis_dir / "reference"

    def fake_run(command, **kwargs):
        output_pattern = Path(command[-1])
        output_pattern.parent.mkdir(parents=True, exist_ok=True)
        (output_pattern.parent / "thumbnail_0001.jpg").write_bytes(b"partial")
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=command,
            stderr="simulated ffmpeg failure",
        )

    monkeypatch.setattr(thumbnails.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="FFmpeg thumbnail generation failed"):
        thumbnails.generate_thumbnails(str(sample_video), output_dir)

    assert not output_dir.exists()
    assert (analysis_dir / ".generating").exists()

