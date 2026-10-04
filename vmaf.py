import subprocess
import json

FFMPEG = "ffmpeg"


# FUNCTION TO COMPUTE VMAF BETWEEN REFERENCE AND DISTORTED VIDEOS
def vmaf_compare(reference, distorted) -> float:
    """
    Computes the VMAF score between a reference video and a distorted video using FFmpeg.
    Parameters:
    - reference: Path to the reference video file.
    - distorted: Path to the distorted video file.
    Returns:
    - score: The computed VMAF score rounded to three decimal places.
    """

    output_file = "vmaf.json"  # File to store the VMAF output in JSON format

    command = [  # Construct the FFmpeg command to compute VMAF
        str(FFMPEG),
        "-i", distorted,
        "-i", reference,
        "-lavfi", f"libvmaf=model=version=vmaf_v1.0.16_3d0h:log_fmt=json:log_path={output_file}",
        "-f", "null",
        "-"
    ]
    
    try:
        subprocess.run(command, check=True, timeout=300)  # Run the FFmpeg command to compute VMAF with a timeout and generate the JSON output
    except subprocess.TimeoutExpired:
        raise RuntimeError("VMAF computation timed out. Please try again with smaller video files.")
    # check=True -> a CalledProcessError will be raised if the command returns a non-zero exit status.
    # timeout=300 -> the command will be terminated if it takes longer than 300 seconds to complete, and TimeoutExpired will be raised.


    try:
        with open(output_file, "r") as file:
            data = json.load(file)
    except FileNotFoundError:
        raise RuntimeError("VMAF output file not found.")
    except json.JSONDecodeError:
        raise RuntimeError("Failed to parse VMAF output file; invalid VMAF output JSON.")


    try:
        mean = data["pooled_metrics"]["vmaf"]["mean"]
    except KeyError:
        raise RuntimeError("VMAF output JSON does not contain expected keys.")

    score = round(mean, 3)  # Round the VMAF score to three decimal places for better readability
    return score
