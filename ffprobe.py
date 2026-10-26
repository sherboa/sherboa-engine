# This module provides utility functions to extract video metadata and validate video files using ffprobe.

from subprocess import CalledProcessError, run

FFPROBE_TIMEOUT = 15  # Maximum time in seconds allowed for each ffprobe command

# FUNCTION TO VALIDATE INPUT FILE
def is_valid_video(file_path: str) -> bool:
    """
    Checks whether a file contains a valid video stream.
    Parameters:
    - file_path: Path to the video file to be checked.
    Returns:
    - True if the file contains a video stream, False otherwise.
    """

    try:
        result = run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0", file_path
             ],
            check=True,
            capture_output=True,
            text=True,
            timeout=FFPROBE_TIMEOUT
        )
        text_output = result.stdout.strip()  # Clean spaces and newlines

        if text_output == "video":  # Check if stream type is video
            return True
        else:
            return False
    except CalledProcessError:
        return False



# FUNCTION TO VALIDATE VIDEO RESOLUTION
def get_video_dimensions(file_path: str) -> tuple[int, int]:
    """
    Returns the width and height of the first video stream.
    Parameters:
    - file_path: Path to the video file.
    Returns:
    - A tuple containing the video width and height.
    """

    result = run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0:s=x", file_path
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=FFPROBE_TIMEOUT
    )

    width, height = result.stdout.strip().split("x")  # Split the output of the ffprobe command to get the width and height of the first video stream
    return int(width), int(height)



# FUNCTION TO CHECK DURATION OF A VIDEO STREAM
def get_video_duration(file_path: str) -> float:
    """
    Returns the duration of the video in seconds.
    Parameters:
    - file_path: Path to the video file.
    Returns:
    - The video duration in seconds.
    """

    result = run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=FFPROBE_TIMEOUT
    )

    duration = float(result.stdout.strip())  # Get the duration of the video in seconds by converting the output of the ffprobe command to a float

    return duration



# FUNCTION TO CALCULATE VIDEO START TIMES AND OVERLAP DURATION
def get_overlap_interval(reference_duration: float, distorted_duration: float, offset: float = 0.0,) -> tuple[float, float, float]:
    """
    Calculate the common temporal interval for synchronized video comparison.
    The offset convention is: distorted_time = reference_time + offset.
    Returns:
        A tuple containing the reference start time, distorted start time,
        and common interval duration, in seconds.
    Raises:
        ValueError: If the offset is non-finite or no overlap exists.
    """
    import math

    if not math.isfinite(offset):
        raise ValueError("offset must be a finite number")

    if (
        not math.isfinite(reference_duration)
        or not math.isfinite(distorted_duration)
        or reference_duration <= 0
        or distorted_duration <= 0
    ):
        raise ValueError("video durations must be finite and greater than zero")


    reference_start = max(0.0, -offset)
    distorted_start = max(0.0, offset)

    overlap_end = min(
        reference_duration - reference_start,
        distorted_duration - distorted_start,
    )

    if overlap_end <= 0:
        raise ValueError("offset leaves no overlapping video interval")

    return reference_start, distorted_start, overlap_end



# FUNCTION TO CALCULATE THE DIFFERENCE IN SECONDS BETWEEN THE TWO INPUT STREAMS
def are_durations_compatible(reference_duration: float, distorted_duration: float) -> bool:
    """
    Checks whether two video durations are compatible.
    Parameters:
    - reference_duration: Duration of the reference video in seconds.
    - distorted_duration: Duration of the distorted video in seconds.
    Returns:
    - True if the duration difference is within one second, False otherwise.
    """

    difference = abs(reference_duration - distorted_duration)  # Calculate the absolute difference between the two video durations in seconds

    if difference <= 1.0:  # The tolerance to consider both streams compatible in terms of duration is: 1 sec
        return True
    else:
        return False



# FUNCTION TO CALCULATE NOMINAL FPS RATE OF A VIDEO STREAM
def get_video_r_fps(file_path: str) -> float:
    """
    Returns the nominal frame rate of the first video stream.
    Parameters:
    - file_path: Path to the video file.
    Returns:
    - r_frame_rate: The nominal video frame rate in frames per second.
    """

    result = run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=FFPROBE_TIMEOUT
    )

    numerator, denominator = result.stdout.strip().split("/")  # Split the output of the ffprobe command to get the numerator and denominator of the nominal frame rate
    r_frame_rate = int(numerator) / int(denominator)  # Calculate the nominal frame rate by dividing the numerator by the denominator to get the nominal frame rate in frames per second

    return r_frame_rate



# FUNCTION TO CALCULATE AVERAGE FPS RATE OF A VIDEO STREAM
def get_video_avg_fps(file_path: str) -> float:
    """
    Returns the average frame rate of the first video stream.
    Parameters:
    - file_path: Path to the video file.
    Returns:
    - avg_frame_rate: The average frame rate in frames per second.
    """

    result = run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=avg_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=FFPROBE_TIMEOUT
    )

    numerator, denominator = result.stdout.strip().split("/")  # Split the output of the ffprobe command to get the numerator and denominator of the average frame rate
    avg_frame_rate =  int(numerator) / int(denominator)  # Calculate the average frame rate by dividing the numerator by the denominator to get the average frame rate in frames per second

    return avg_frame_rate



# FUNCTION TO COUNT FRAMES
def get_video_frame_count(file_path: str) -> int:
    """
    Returns the number of frames in the first video stream.
    Parameters:
    - file_path: Path to the video file.
    Returns:
    - frames: The number of video frames.
    """

    result = run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-count_frames",
            "-show_entries", "stream=nb_read_frames",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=FFPROBE_TIMEOUT
    )

    frames = int(result.stdout.strip())  # Get the number of frames in the first video stream by converting the output of the ffprobe command to an integer
    return frames



# FUNCTION TO GET VIDEO METADATA
def get_video_metadata(file_path: str) -> dict:
    """
    Returns basic metadata from the first video stream.
    Parameters:
    - file_path: Path to the video file.
    Returns:
    - A dictionary containing duration, width, height and fps.
    """

    width, height = get_video_dimensions(file_path)  # Get the width and height of the first video stream using the get_video_dimensions function
    duration = get_video_duration(file_path)  # Get the duration of the first video stream using the get_video_duration function
    fps = get_video_r_fps(file_path)  # Get the nominal frame rate of the first video stream using the get_video_r_fps function

    return {
        "duration": round(duration, 3),  # Round the duration to 3 decimal places and store it in the "duration" key of the metadata dictionary
        "width": width,  # Store the width of the video in the "width" key of the metadata dictionary
        "height": height,  # Store the height of the video in the "height" key of the metadata dictionary
        "fps": round(fps, 3)  # Round the nominal frame rate to 3 decimal places and store it in the "fps" key of the metadata dictionary
    }