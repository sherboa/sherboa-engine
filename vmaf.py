import subprocess
import json
import re

FFMPEG = "ffmpeg"


# FUNCTION TO COMPUTE VMAF, PSNR AND SSIM
def video_compare(reference, distorted) -> dict:
    """
    Computes VMAF, PSNR and SSIM between reference and distorted videos using FFmpeg.
    Parameters:
    - reference: Path to the reference video file.
    - distorted: Path to the distorted video file.
    Returns:
    - A dictionary containing VMAF, PSNR and SSIM results.
    """

    vmaf_output = "/tmp/vmaf.json"
    psnr_output = "/tmp/psnr.log"
    ssim_output = "/tmp/ssim.log"

    command = [
        str(FFMPEG),
        "-i", distorted,
        "-i", reference,
        "-filter_complex",
        (
            f"[0:v][1:v]libvmaf="
            f"model=version=vmaf_v1.0.16_3d0h:"
            f"log_fmt=json:log_path={vmaf_output}[vmaf];"
            f"[0:v][1:v]psnr=stats_file={psnr_output}[psnr];"
            f"[0:v][1:v]ssim=stats_file={ssim_output}[ssim]"
        ),
        "-map", "[vmaf]",
        "-map", "[psnr]",
        "-map", "[ssim]",
        "-f", "null",
        "-"
    ]

    try:
        result = subprocess.run(
            command,
            check=True,
            timeout=300,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        ffmpeg_output = result.stderr
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "Video quality analysis timed out. "
            "Please try again with smaller video files."
        )

    # ---------------------------------------------------------
    # VMAF
    # ---------------------------------------------------------

    try:
        with open(vmaf_output, "r") as file:
            vmaf_data = json.load(file)
    except FileNotFoundError:
        raise RuntimeError("VMAF output file not found.")
    except json.JSONDecodeError:
        raise RuntimeError(
            "Failed to parse VMAF output file; invalid VMAF output JSON."
        )

    try:
        vmaf_metrics = vmaf_data["pooled_metrics"]["vmaf"]

        vmaf = {
            "mean": round(vmaf_metrics["mean"], 3),
            "min": round(vmaf_metrics["min"], 3),
            "max": round(vmaf_metrics["max"], 3)
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
        raise RuntimeError("FFmpeg output does not contain valid PSNR values.")

    psnr = {
        "mean": round(float(psnr_match.group(4)), 3),
        "min": round(float(psnr_match.group(5)), 3),
        "max": round(float(psnr_match.group(6)), 3)
    }

    # ---------------------------------------------------------
    # SSIM
    # ---------------------------------------------------------

    ssim_match = re.search(
        r"SSIM Y:(\S+) .*?U:(\S+) .*?V:(\S+) .*?All:(\S+)",
        ffmpeg_output
    )

    if not ssim_match:
        raise RuntimeError("FFmpeg output does not contain valid SSIM values.")

    ssim = {
        "global (all)": round(float(ssim_match.group(4)), 3),
        "y": round(float(ssim_match.group(1)), 3),
        "u": round(float(ssim_match.group(2)), 3),
        "v": round(float(ssim_match.group(3)), 3)
    }

    return {
        "vmaf": vmaf,
        "psnr": psnr,
        "ssim": ssim
    }