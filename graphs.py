# This module contains functions to generate graphs for VMAF, PSNR, and SSIM metrics using matplotlib. The graphs are generated as PNG images and returned as byte data.

import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt



# FUNCTION TO GENERATE A VMAF GRAPH
def generate_vmaf_graph(result: dict) -> bytes:
    """
    Generate a PNG graph containing per-frame VMAF values.
    Parameters:
    - result (dict): Analysis results containing per-frame VMAF data.
    Returns:
    - bytes: PNG image data.
    """

    vmaf_frames = result["vmaf"]["per_frame"]  # Get the per-frame VMAF values from the result dictionary
    frames = range(1, len(vmaf_frames) + 1)  # Create a range of frame numbers starting from 1 to the number of frames

    figure, axis = plt.subplots(figsize=(12, 5))  # Create a new figure and axis for the plot with a specified size

    axis.plot(frames, vmaf_frames, linewidth=1.5)  # Plot the VMAF values against the frame numbers with a specified line width
    axis.set_title("VMAF per frame")
    axis.set_xlabel("Frame")
    axis.set_ylabel("VMAF score")
    axis.set_ylim(0, 100)
    axis.grid(True, alpha=0.3)

    figure.tight_layout()

    output = io.BytesIO()  # Create a BytesIO buffer to hold the PNG image data

    try:
        figure.savefig(output, format="png", dpi=150)  # Save the figure to the output buffer in PNG format with a specified DPI
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

    psnr_frames = result["psnr"]["per_frame"]  # Get the per-frame PSNR values from the result dictionary
    frames = range(1, len(psnr_frames) + 1)  # Create a range of frame numbers starting from 1 to the number of frames

    figure, axis = plt.subplots(figsize=(12, 5))  # Create a new figure and axis for the plot with a specified size

    axis.plot(frames, psnr_frames, color="red", linewidth=1.5)  # Plot the PSNR values against the frame numbers with a specified line width and color
    axis.set_title("PSNR per frame")
    axis.set_xlabel("Frame")
    axis.set_ylabel("PSNR [dB]")
    axis.grid(True, alpha=0.3)

    figure.tight_layout()

    output = io.BytesIO()  # Create a BytesIO buffer to hold the PNG image data

    try:
        figure.savefig(output, format="png", dpi=150)  # Save the figure to the output buffer in PNG format with a specified DPI
    finally:
        plt.close(figure)

    output.seek(0)
    return output.getvalue()



# FUNCTION TO GENERATE A SSIM GRAPH
def generate_ssim_graph(result: dict) -> bytes:
    """
    Generate a PNG graph containing per-frame SSIM values.
    Parameters:
    - result (dict): Analysis results containing per-frame SSIM data.
    Returns:
    - bytes: PNG image data.
    """

    ssim_frames = result["ssim"]["per_frame"]  # Get the per-frame SSIM values from the result dictionary
    frames = range(1, len(ssim_frames) + 1)  # Create a range of frame numbers starting from 1 to the number of frames
    
    figure, axis = plt.subplots(figsize=(12, 5))  # Create a new figure and axis for the plot with a specified size

    axis.plot(frames, ssim_frames, color="green", linewidth=1.5)  # Plot the SSIM values against the frame numbers with a specified line width and color
    axis.set_title("SSIM per frame")
    axis.set_xlabel("Frame")
    axis.set_ylabel("SSIM score")
    axis.set_ylim(0, 1)
    axis.grid(True, alpha=0.3)

    figure.tight_layout()

    output = io.BytesIO()  # Create a BytesIO buffer to hold the PNG image data

    try:
        figure.savefig(output, format="png", dpi=150)  # Save the figure to the output buffer in PNG format with a specified DPI
    finally:
        plt.close(figure)

    output.seek(0)
    return output.getvalue()
