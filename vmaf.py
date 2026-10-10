import subprocess
import json
import re
import csv
import io
import xml.etree.ElementTree as ET
from ffprobe import get_video_metadata
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


FFMPEG = "ffmpeg"



# FUNCTION TO GENERATE A CSV FILE
def generate_csv(result: dict) -> str:
    """
    Generate a CSV string containing per-frame VMAF and PSNR values.
    Parameters:
    - result (dict): Analysis results containing per-frame VMAF and PSNR data.
    Returns:
    - str: CSV-formatted string with frame, VMAF, and PSNR values.
    """
    
    output = io.StringIO()

    writer = csv.writer(output)
    writer.writerow(["frame", "vmaf", "psnr"])

    vmaf_frames = result["vmaf"]["per_frame"]
    psnr_frames = result["psnr"]["per_frame"]

    for frame, (vmaf, psnr) in enumerate(zip(vmaf_frames, psnr_frames), start=1):
        writer.writerow([frame, vmaf, psnr])

    return output.getvalue()



# FUNCTION TO GENERATE A XML FILE
def generate_xml(result: dict) -> str:
    """
    Generate an XML string containing the complete analysis results.
    Parameters:
    - result (dict): Analysis results containing VMAF, PSNR, SSIM,
      and video metadata.
    Returns:
    - str: XML-formatted analysis results.
    """

    root = ET.Element("sherboa-analysis")

    engine = ET.SubElement(root, "sherboa-engine")
    engine.set("version", result["sherboa-engine"]["version"])

    vmaf = ET.SubElement(root, "vmaf")
    ET.SubElement(vmaf, "mean").text = str(result["vmaf"]["mean"])
    ET.SubElement(vmaf, "min").text = str(result["vmaf"]["min"])
    ET.SubElement(vmaf, "max").text = str(result["vmaf"]["max"])

    vmaf_frames = ET.SubElement(vmaf, "per-frame")

    for frame, value in enumerate(result["vmaf"]["per_frame"], start=1):
        ET.SubElement(
            vmaf_frames,
            "frame",
            number=str(frame)
        ).text = str(value)

    psnr = ET.SubElement(root, "psnr")
    ET.SubElement(psnr, "mean").text = str(result["psnr"]["mean"])
    ET.SubElement(psnr, "min").text = str(result["psnr"]["min"])
    ET.SubElement(psnr, "max").text = str(result["psnr"]["max"])

    psnr_frames = ET.SubElement(psnr, "per-frame")

    for frame, value in enumerate(result["psnr"]["per_frame"], start=1):
        ET.SubElement(
            psnr_frames,
            "frame",
            number=str(frame)
        ).text = str(value)

    ssim = ET.SubElement(root, "ssim")
    ET.SubElement(ssim, "global").text = str(result["ssim"]["global (all)"])
    ET.SubElement(ssim, "y").text = str(result["ssim"]["y"])
    ET.SubElement(ssim, "u").text = str(result["ssim"]["u"])
    ET.SubElement(ssim, "v").text = str(result["ssim"]["v"])

    video = ET.SubElement(root, "video")
    ET.SubElement(video, "duration").text = str(result["video"]["duration"])
    ET.SubElement(video, "width").text = str(result["video"]["width"])
    ET.SubElement(video, "height").text = str(result["video"]["height"])
    ET.SubElement(video, "fps").text = str(result["video"]["fps"])

    return ET.tostring(root, encoding="unicode")



# FUNCTION TO GENERATE A VMAF GRAPH
def generate_vmaf_graph(result: dict) -> bytes:
    """
    Generate a PNG graph containing per-frame VMAF values.
    Parameters:
    - result (dict): Analysis results containing per-frame VMAF data.
    Returns:
    - bytes: PNG image data.
    """

    vmaf_frames = result["vmaf"]["per_frame"]
    frames = range(1, len(vmaf_frames) + 1)

    figure, axis = plt.subplots(figsize=(12, 5))

    axis.plot(frames, vmaf_frames, linewidth=1.5)
    axis.set_title("VMAF per frame")
    axis.set_xlabel("Frame")
    axis.set_ylabel("VMAF score")
    axis.set_ylim(0, 100)
    axis.grid(True, alpha=0.3)

    figure.tight_layout()

    output = io.BytesIO()

    try:
        figure.savefig(output, format="png", dpi=150)
    finally:
        plt.close(figure)

    output.seek(0)
    return output.getvalue()



# FUNCTION TO GENERATE A PSNR GRAPH
def generate_psnr_graph(result: dict) -> bytes:
    """
    Generate a PNG graph containing per-frame PSNR values.
    Parameters:
    - result (dict): Analysis results containing per-frame PSNR data.
    Returns:
    - bytes: PNG image data.
    """

    psnr_frames = result["psnr"]["per_frame"]
    frames = range(1, len(psnr_frames) + 1)

    figure, axis = plt.subplots(figsize=(12, 5))

    axis.plot(frames, psnr_frames, color="red", linewidth=1.5)
    axis.set_title("PSNR per frame")
    axis.set_xlabel("Frame")
    axis.set_ylabel("PSNR (dB)")
    axis.grid(True, alpha=0.3)

    figure.tight_layout()

    output = io.BytesIO()

    try:
        figure.savefig(output, format="png", dpi=150)
    finally:
        plt.close(figure)

    output.seek(0)
    return output.getvalue()



# FUNCTION TO GENERATE AN SSIM GRAPH
def generate_ssim_graph(result: dict) -> bytes:
    """
    Generate a PNG graph containing per-frame SSIM values.
    Parameters:
    - result (dict): Analysis results containing per-frame SSIM data.
    Returns:
    - bytes: PNG image data.
    """

    ssim_frames = result["ssim"]["per_frame"]
    frames = range(1, len(ssim_frames) + 1)

    figure, axis = plt.subplots(figsize=(12, 5))

    axis.plot(frames, ssim_frames, color="green", linewidth=1.5)
    axis.set_title("SSIM per frame")
    axis.set_xlabel("Frame")
    axis.set_ylabel("SSIM score")
    axis.set_ylim(0, 1)
    axis.grid(True, alpha=0.3)

    figure.tight_layout()

    output = io.BytesIO()

    try:
        figure.savefig(output, format="png", dpi=150)
    finally:
        plt.close(figure)

    output.seek(0)
    return output.getvalue()



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

    reference_metadata = get_video_metadata(reference)

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

        with open(ssim_output, "r", encoding="utf-8") as file:
            ssim_log = file.readlines()

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

        vmaf_per_frame = [
            round(frame["metrics"]["vmaf"], 3)
            for frame in vmaf_data["frames"]
        ]

        vmaf = {
            "mean": round(vmaf_metrics["mean"], 3),
            "min": round(vmaf_metrics["min"], 3),
            "max": round(vmaf_metrics["max"], 3),
            "per_frame": vmaf_per_frame
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

    try:
        with open(psnr_output, "r") as file:
            psnr_data = file.readlines()
    except FileNotFoundError:
        raise RuntimeError("PSNR output file not found.")

    psnr_per_frame = [
        round(float(re.search(r"psnr_avg:(\S+)", line).group(1)), 3)
        for line in psnr_data
        if re.search(r"psnr_avg:(\S+)", line)
    ]

    psnr = {
        "mean": round(float(psnr_match.group(4)), 3),
        "min": round(float(psnr_match.group(5)), 3),
        "max": round(float(psnr_match.group(6)), 3),
        "per_frame": psnr_per_frame
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
        raise RuntimeError("FFmpeg output does not contain valid SSIM values.")

    ssim = {
        "global (all)": round(float(ssim_match.group(4)), 3),
        "y": round(float(ssim_match.group(1)), 3),
        "u": round(float(ssim_match.group(2)), 3),
        "v": round(float(ssim_match.group(3)), 3),
        "per_frame": ssim_frames
    }

    # ---------------------------------------------------------
    # RESULTS
    # ---------------------------------------------------------

    return {
        "sherboa-engine": {
            "version": "1.3.0"
        },
        "vmaf": vmaf,
        "psnr": psnr,
        "ssim": ssim,
        "video": reference_metadata
    }