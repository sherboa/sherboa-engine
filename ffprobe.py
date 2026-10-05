from subprocess import CalledProcessError, run



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
            text=True
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
        text=True
    )

    width, height = result.stdout.strip().split("x")
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
        text=True
    )

    duration = float(result.stdout.strip())

    return duration



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

    difference = abs(reference_duration - distorted_duration)

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
        text=True
    )

    numerator, denominator = result.stdout.strip().split("/")
    r_frame_rate = int(numerator) / int(denominator)

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
        text=True
    )

    numerator, denominator = result.stdout.strip().split("/")
    avg_frame_rate =  int(numerator) / int(denominator)

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
        text=True
    )

    frames = int(result.stdout.strip())
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

    width, height = get_video_dimensions(file_path)
    duration = get_video_duration(file_path)
    fps = get_video_r_fps(file_path)

    return {
        "duration": round(duration, 3),
        "width": width,
        "height": height,
        "fps": round(fps, 3)
    }