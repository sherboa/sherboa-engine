# This module performs the thumbnail generation for the frontend.

import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

########################################################################################################################
# CONSTANTS
########################################################################################################################
FFMPEG = "ffmpeg"
THUMBNAIL_FPS = 1  # One snapshop per second
THUMBNAIL_WIDTH = 320  # Width of the snapshots
THUMBNAIL_JPEG_QUALITY = 3
THUMBNAIL_TIMEOUT_SECONDS = 120  # Maximum time allowed for thumbnail extraction
THUMBNAIL_RETENTION_SECONDS = 60 * 60  # Remove thumbnail directories older than this retention period
THUMBNAIL_ROOT = Path(tempfile.gettempdir()) / "sherboa-thumbnails"  # Dedicated storage root; must contain thumbnails only



def cleanup_expired_thumbnails(root: Path = THUMBNAIL_ROOT, now: float | None = None) -> int:
    """
    Remove expired analysis directories; return the number removed.
    """
    if not root.exists():
        return 0

    current_time = time.time() if now is None else now
    removed = 0

    for entry in root.iterdir():
        if not entry.is_dir() or entry.is_symlink():
            continue

        try:
            generating_marker = entry / ".generating"

            if generating_marker.exists():
                marker_age = current_time - generating_marker.stat().st_mtime

                if marker_age < THUMBNAIL_RETENTION_SECONDS:
                    continue

                shutil.rmtree(entry)
                removed += 1
                continue

            age = current_time - entry.stat().st_mtime
            if age >= THUMBNAIL_RETENTION_SECONDS:
                shutil.rmtree(entry)
                removed += 1
        except FileNotFoundError:  # Another cleanup may already have removed this directory
            continue

    return removed



def generate_thumbnails(video_path: str, output_dir: Path) -> list[Path]:
    """
    Generate JPEG thumbnails at one frame per second.
    """

    video = Path(video_path)
    if not video.is_file():
        raise FileNotFoundError(f"video file not found: {video}")

    root = THUMBNAIL_ROOT.resolve()
    root.mkdir(parents=True, exist_ok=True)

    requested_dir = Path(output_dir)
    analysis_dir = requested_dir.parent

    if analysis_dir.is_symlink() or requested_dir.is_symlink():
        raise ValueError("symbolic links are not allowed")

    analysis_dir = analysis_dir.resolve()
    output_dir = analysis_dir / requested_dir.name

    if analysis_dir.parent != root:
        raise ValueError("output directory must be inside THUMBNAIL_ROOT, with an analysis directory as its parent")

    if output_dir.name not in {"reference", "distorted"}:
        raise ValueError("output directory must be 'reference' or 'distorted'")

    if not analysis_dir.is_dir():
        raise ValueError("analysis directory must already exist")

    if not (analysis_dir / ".generating").is_file():
        raise ValueError("analysis generation marker is missing")

    cleanup_expired_thumbnails(root)
    output_dir.mkdir(parents=False, exist_ok=False)

    output_pattern = output_dir / "thumbnail_%04d.jpg"
    command = [
        FFMPEG,
        "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(video),
        "-vf", f"fps={THUMBNAIL_FPS},scale={THUMBNAIL_WIDTH}:-2",
        "-q:v", str(THUMBNAIL_JPEG_QUALITY),
        str(output_pattern),
    ]

    try:
        subprocess.run(
            command,
            check=True,
            timeout=THUMBNAIL_TIMEOUT_SECONDS,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        generated = sorted(output_dir.glob("thumbnail_*.jpg"))
        if not generated:
            raise RuntimeError("FFmpeg produced no thumbnails")

        return generated

    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise RuntimeError("Thumbnail generation timed out") from exc

    except subprocess.CalledProcessError as exc:
        shutil.rmtree(output_dir, ignore_errors=True)
        error_detail = (exc.stderr or "").strip()
        raise RuntimeError(
            f"FFmpeg thumbnail generation failed: {error_detail}"
        ) from exc

    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise



def create_analysis_thumbnail_dir() -> Path:
    """
    Create a unique directory for one analysis.
    """
    THUMBNAIL_ROOT.mkdir(parents=True, exist_ok=True)
    return THUMBNAIL_ROOT / str(uuid.uuid4())
