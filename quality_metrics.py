# This is the main FastAPI application file for the VMAF, PSNR, and SSIM API. It defines the endpoints and handles video file uploads, validation, and quality metric computation.

import subprocess
import json
import re
import os
from ffprobe import get_video_metadata, get_overlap_interval, get_video_duration, get_video_r_fps


FFMPEG = "ffmpeg"

class UnsupportedFrameRateError(ValueError):
    """Raised when videos have incompatible frame rates for comparison."""

# FUNCTION TO CONVERT NON FINITE RESULTS OF PSNR SCORE
def format_psnr(value: str) -> float | str:
    """
    Convert PSNR values to rounded numbers or the string 'inf'.
    Parameters:
    - value: A string representing a PSNR value computed by FFmpeg.
    Returns:
    - The PSNR value rounded to 3 decimal places as a float, or as a string ("inf" or "-inf") if the value is infinite.
    """
    number = float(value)

    if number == float("inf"):
        return "inf"

    if number == float("-inf"):
        return "-inf"

    return round(number, 3)



# FUNCTION TO COMPUTE VMAF, PSNR AND SSIM
def video_compare(reference, distorted, offset: float = 0.0) -> dict:
    """
    Computes VMAF, PSNR and SSIM between reference and distorted videos using FFmpeg.
    Parameters:
    - reference: Path to the reference video file.
    - distorted: Path to the distorted video file.
    - offset: Temporal offset in seconds applied to the distorted video relative to the reference. Defaults to 0.0.
    Returns:
    - A dictionary containing VMAF, PSNR and SSIM results.
    """

    vmaf_output = "/tmp/vmaf.json"  # Path to the temporary output file for VMAF results in JSON format
    psnr_output = "/tmp/psnr.log"  # Path to the temporary output file for PSNR results in log format
    ssim_output = "/tmp/ssim.log"  # Path to the temporary output file for SSIM results in log format

    try:
        reference_metadata = get_video_metadata(reference)

        reference_duration = get_video_duration(reference)
        distorted_duration = get_video_duration(distorted)

        reference_fps = get_video_r_fps(reference)
        distorted_fps = get_video_r_fps(distorted)

        if abs(reference_fps - distorted_fps) > 0.001:
            raise UnsupportedFrameRateError(
                "videos with different frame rates are not supported yet."
            )

        (
            reference_start,
            distorted_start,
            overlap_duration,
        ) = get_overlap_interval(
            reference_duration,
            distorted_duration,
            offset,
        )

        command = [
            str(FFMPEG),  # Use the FFMPEG command to invoke FFmpeg for video processing
            "-i", distorted,  # Path to the distorted video file as input
            "-i", reference,  # Path to the reference video file as input
            "-filter_complex",  # Use the filter_complex option to apply multiple filters in a single command
            (
                f"[0:v]trim=start={distorted_start}:duration={overlap_duration},"
                f"setpts=PTS-STARTPTS[dist];"
                f"[1:v]trim=start={reference_start}:duration={overlap_duration},"
                f"setpts=PTS-STARTPTS[ref];"
                f"[dist]split=3[dist_vmaf][dist_psnr][dist_ssim]"  # Use the libvmaf filter to compute VMAF scores between the distorted and reference videos
                f"[ref]split=3[ref_vmaf][ref_psnr][ref_ssim];"
                f"[dist_vmaf][ref_vmaf]libvmaf="
                f"model=version=vmaf_v1.0.16_3d0h:"  # Specify the VMAF model version to be used for computation
                f"log_fmt=json:log_path={vmaf_output}[vmaf];"  # Specify the output format for VMAF results as JSON and the path to the output file
                f"[dist_psnr][ref_psnr]psnr=stats_file={psnr_output}[psnr];"  # Use the psnr filter to compute PSNR values between the distorted and reference videos and specify the path to the output log file
                f"[dist_ssim][ref_ssim]ssim=stats_file={ssim_output}[ssim];"  # Use the ssim filter to compute SSIM values between the distorted and reference videos and specify the path to the output log file
            ),
            "-map", "[vmaf]",  # Map the output of the VMAF filter to the output stream for VMAF results
            "-map", "[psnr]",  # Map the output of the PSNR filter to the output stream for PSNR results
            "-map", "[ssim]",  # Map the output of the SSIM filter to the output stream for SSIM results
            "-f", "null",  # Specify the output format as null to discard the actual video output, as we are only interested in the computed metrics
            "-"  # Discard the actual video output, as we are only interested in the computed metrics
        ]

        try:
            result = subprocess.run(  # Execute the FFmpeg command using subprocess.run() to compute VMAF, PSNR, and SSIM between the reference and distorted videos
                command,  # The command list containing the FFmpeg command and its arguments
                check=True,  # Raise a CalledProcessError if the command returns a non-zero exit status
                timeout=300,  # Set a timeout of 300 seconds (5 minutes) for the command execution to prevent it from running indefinitely
                stdout=subprocess.PIPE,  # Capture the standard output of the command to be used later for parsing PSNR and SSIM values
                stderr=subprocess.PIPE,  # Capture the standard error of the command to be used later for parsing PSNR and SSIM values
                text=True  # Capture the output and error as text strings instead of bytes for easier parsing
            )

            ffmpeg_output = result.stderr  # Capture the standard error output of the FFmpeg command, which contains information about the processing and any errors that occurred during execution

            with open(ssim_output, "r", encoding="utf-8") as file:  # Open the SSIM log file in read mode with UTF-8 encoding to read the computed SSIM values
                ssim_log = file.readlines()  # Read all lines from the SSIM log file and store them in a list for later parsing of per-frame SSIM values

        except subprocess.TimeoutExpired:  # Error handling #5: catch the TimeoutExpired exception if the FFmpeg command takes longer than the specified timeout (300 seconds) to complete, and raise a RuntimeError with a message indicating that the video quality analysis timed out and suggesting to try again with smaller video files.
            raise RuntimeError(
                "video quality analysis timed out. "
                "please try again with smaller video files."
            )

        # ---------------------------------------------------------
        # VMAF
        # ---------------------------------------------------------

        try:
            with open(vmaf_output, "r") as file:  # Open the VMAF output JSON file in read mode to read the computed VMAF values
                vmaf_data = json.load(file)  # Load the JSON data from the VMAF output file into a Python dictionary for later parsing of mean, min, max, and per-frame VMAF values
        except FileNotFoundError:  # Error handling #4: catch the FileNotFoundError exception if the VMAF output file is not found, and raise a RuntimeError with a message indicating that the VMAF output file was not found.
            raise RuntimeError("VMAF output file not found.")  # Raise a RuntimeError with a message indicating that the VMAF output file was not found.
        except json.JSONDecodeError:  # Error handling #4: catch the JSONDecodeError exception if the VMAF output file is not a valid JSON file, and raise a RuntimeError with a message indicating that the VMAF output file is invalid.
            raise RuntimeError(  # Raise a RuntimeError with a message indicating that the VMAF output file is invalid.
                "failed to parse VMAF output file; invalid VMAF output JSON."  # Raise a RuntimeError with a message indicating that the VMAF output file is invalid.
            )

        try:
            vmaf_metrics = vmaf_data["pooled_metrics"]["vmaf"]  # Access the pooled VMAF metrics from the VMAF output JSON, which contains the mean, min, and max VMAF values for the entire video comparison

            vmaf_per_frame = [  # Create a list of per-frame VMAF values by iterating through the "frames" list in the VMAF output JSON and rounding each frame's VMAF score to 3 decimal places
                round(frame["metrics"]["vmaf"], 3)  # Round the VMAF score for each frame to 3 decimal places
                for frame in vmaf_data["frames"]  # Iterate through each frame in the "frames" list of the VMAF output JSON to extract the per-frame VMAF scores
            ]

            vmaf = {  # Create a dictionary to hold the VMAF results, including mean, min, max, and per-frame values
                "mean": round(vmaf_metrics["mean"], 3),  # Round the mean VMAF value to 3 decimal places and store it in the "mean" key of the vmaf dictionary
                "min": round(vmaf_metrics["min"], 3),  # Round the minimum VMAF value to 3 decimal places and store it in the "min" key of the vmaf dictionary
                "max": round(vmaf_metrics["max"], 3),  # Round the maximum VMAF value to 3 decimal places and store it in the "max" key of the vmaf dictionary
                "per_frame": vmaf_per_frame  # Store the list of per-frame VMAF values in the "per_frame" key of the vmaf dictionary
            }
        except KeyError:
            raise RuntimeError(
                "VMAF output JSON does not contain expected keys."
            )

        # ---------------------------------------------------------
        # PSNR
        # ---------------------------------------------------------

        psnr_match = re.search(
            r"PSNR y:(\S+) u:(\S+) v:(\S+) average:(\S+) min:(\S+) max:(\S+)",
            ffmpeg_output
        )

        if not psnr_match:
            raise RuntimeError("ffmpeg output does not contain valid PSNR values.")

        try:
            with open(psnr_output, "r") as file:  # Open the PSNR log file in read mode to read the computed PSNR values
                psnr_data = file.readlines()  # Read all lines from the PSNR log file and store them in a list for later parsing of per-frame PSNR values
        except FileNotFoundError:  # Error handling #4: catch the FileNotFoundError exception if the PSNR output file is not found, and raise a RuntimeError with a message indicating that the PSNR output file was not found.
            raise RuntimeError("PSNR output file not found.")  # Raise a RuntimeError with a message indicating that the PSNR output file was not found.


        psnr_per_frame = [  # Create a list of per-frame PSNR values by iterating through the lines in the PSNR log file and extracting the average PSNR value for each frame using a regular expression, rounding each value to 3 decimal places
            format_psnr(re.search(r"psnr_avg:(\S+)", line).group(1))
            for line in psnr_data  # Iterate through each line in the PSNR log file to extract the average PSNR values for each frame using a regular expression that matches the "psnr_avg" pattern in the log lines
            if re.search(r"psnr_avg:(\S+)", line)  # Only include lines that contain the "psnr_avg" pattern to ensure that we are extracting valid PSNR values for each frame
        ]

        psnr = {  # Create a dictionary to hold the PSNR results, including mean, min, max, and per-frame values
            "mean": format_psnr(psnr_match.group(4)),  # Check for non finite values and round the mean PSNR value to 3 decimal places and store it in the "mean" key of the psnr dictionary
            "min": format_psnr(psnr_match.group(5)),  # Check for non finite values and round the minimum PSNR value to 3 decimal places and store it in the "min" key of the psnr dictionary
            "max": format_psnr(psnr_match.group(6)),  # Check for non finite values and round the maximum PSNR value to 3 decimal places and store it in the "max" key of the psnr dictionary
            "per_frame": psnr_per_frame  # Store the list of per-frame PSNR values in the "per_frame" key of the psnr dictionary
        }

        # ---------------------------------------------------------
        # SSIM
        # ---------------------------------------------------------

        ssim_frames = []

        for line in ssim_log:
            match = re.search(r"All:(\S+)", line)

            if match:
                ssim_frames.append(float(match.group(1)))

        if not ssim_frames:
            raise RuntimeError(
                "SSIM log does not contain valid per-frame values."
            )

        ssim_match = re.search(
            r"SSIM Y:(\S+) .*?U:(\S+) .*?V:(\S+) .*?All:(\S+)",
            ffmpeg_output
        )

        if not ssim_match:
            raise RuntimeError("ffmpeg output does not contain valid SSIM values.")

        ssim = {  # Create a dictionary to hold the SSIM results, including global, Y, U, V, and per-frame values
            "global (all)": round(float(ssim_match.group(4)), 3),  # Round the global SSIM value to 3 decimal places and store it in the "global (all)" key of the ssim dictionary
            "y": round(float(ssim_match.group(1)), 3),  # Round the Y-component SSIM value to 3 decimal places and store it in the "y" key of the ssim dictionary
            "u": round(float(ssim_match.group(2)), 3),  # Round the U-component SSIM value to 3 decimal places and store it in the "u" key of the ssim dictionary
            "v": round(float(ssim_match.group(3)), 3),  # Round the V-component SSIM value to 3 decimal places and store it in the "v" key of the ssim dictionary
            "per_frame": ssim_frames  # Store the list of per-frame SSIM values in the "per_frame" key of the ssim dictionary
        }

        # ---------------------------------------------------------
        # RESULTS
        # ---------------------------------------------------------

        return {
            "sherboa-engine": {
                "version": "1.5.0"
            },
            "vmaf": vmaf,  # Create a dictionary to hold the VMAF results, including mean, min, max, and per-frame values
            "psnr": psnr,  # Create a dictionary to hold the PSNR results, including mean, min, max, and per-frame values
            "ssim": ssim,  # Create a dictionary to hold the SSIM results, including global, Y, U, V, and per-frame values
            "video": reference_metadata  # Include the video metadata of the reference video in the results dictionary under the "video" key, which contains information such as duration, resolution, codec, and other relevant metadata extracted from the reference video file
        }
    finally:  # Clean up internal files, even if an error occurs
        for path in (vmaf_output, psnr_output, ssim_output):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
