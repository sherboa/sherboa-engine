# This is the module for generating export files (CSV, XML) for the VMAF, PSNR, and SSIM API. It defines functions to create formatted output from analysis results.

import csv
import io
import xml.etree.ElementTree as ET


# FUNCTION TO GENERATE A CSV FILE
def generate_csv(result: dict) -> str:
    """
    Generate a CSV string containing per-frame VMAF and PSNR values.
    Parameters:
    - result (dict): Analysis results containing per-frame VMAF and PSNR data.
    Returns:
    - str: CSV-formatted string with frame, VMAF, and PSNR values.
    """
    
    output = io.StringIO()  # Create a StringIO buffer to hold the CSV data

    writer = csv.writer(output)  # Create a CSV writer object to write data to the output buffer
    writer.writerow(["frame", "vmaf", "psnr"])  # Write the header row to the CSV file with column names: "frame", "vmaf", and "psnr"

    vmaf_frames = result["vmaf"]["per_frame"]  # Get the per-frame VMAF values from the result dictionary
    psnr_frames = result["psnr"]["per_frame"]  # Get the per-frame PSNR values from the result dictionary

    for frame, (vmaf, psnr) in enumerate(zip(vmaf_frames, psnr_frames), start=1):  # Loop through the per-frame VMAF and PSNR values using the enumerate function to get both the frame number and the corresponding VMAF and PSNR values. The loop starts counting frames from 1.
        writer.writerow([frame, vmaf, psnr])

    return output.getvalue()  # Convert the entire CSV data in the output buffer to a string and return it as the output of the function



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

    root = ET.Element("sherboa-analysis")  # Create the root element of the XML tree with the tag "sherboa-analysis"

    engine = ET.SubElement(root, "sherboa-engine")  # Create a sub-element under the root element with the tag "sherboa-engine" to hold information about the analysis engine
    engine.set("version", result["sherboa-engine"]["version"])  # Set the "version" attribute of the "sherboa-engine" element to the version value from the result dictionary

    vmaf = ET.SubElement(root, "vmaf")  # Create a sub-element under the root element with the tag "vmaf" to hold VMAF analysis results
    ET.SubElement(vmaf, "mean").text = str(result["vmaf"]["mean"])  # Create a sub-element under the "vmaf" element with the tag "mean" and set its text content to the mean VMAF value from the result dictionary
    ET.SubElement(vmaf, "min").text = str(result["vmaf"]["min"])  # Create a sub-element under the "vmaf" element with the tag "min" and set its text content to the minimum VMAF value from the result dictionary
    ET.SubElement(vmaf, "max").text = str(result["vmaf"]["max"])  # Create a sub-element under the "vmaf" element with the tag "max" and set its text content to the maximum VMAF value from the result dictionary

    vmaf_frames = ET.SubElement(vmaf, "per-frame")  # Create a sub-element under the "vmaf" element with the tag "per-frame" to hold per-frame VMAF values

    for frame, value in enumerate(result["vmaf"]["per_frame"], start=1):  # Loop through the per-frame VMAF values using the enumerate function to get both the frame number and the corresponding VMAF value. The loop starts counting frames from 1.
        ET.SubElement(  # Create a sub-element under the "per-frame" element with the tag "frame" and set its "number" attribute to the current frame number and its text content to the corresponding VMAF value.
            vmaf_frames,
            "frame",
            number=str(frame)
        ).text = str(value)

    psnr = ET.SubElement(root, "psnr")  # Create a sub-element under the root element with the tag "psnr" to hold PSNR analysis results
    ET.SubElement(psnr, "mean").text = str(result["psnr"]["mean"])  # Create a sub-element under the "psnr" element with the tag "mean" and set its text content to the mean PSNR value from the result dictionary
    ET.SubElement(psnr, "min").text = str(result["psnr"]["min"])  # Create a sub-element under the "psnr" element with the tag "min" and set its text content to the minimum PSNR value from the result dictionary
    ET.SubElement(psnr, "max").text = str(result["psnr"]["max"])  # Create a sub-element under the "psnr" element with the tag "max" and set its text content to the maximum PSNR value from the result dictionary

    psnr_frames = ET.SubElement(psnr, "per-frame")  # Create a sub-element under the "psnr" element with the tag "per-frame" to hold per-frame PSNR values

    for frame, value in enumerate(result["psnr"]["per_frame"], start=1):  # Loop through the per-frame PSNR values using the enumerate function to get both the frame number and the corresponding PSNR value. The loop starts counting frames from 1.
        ET.SubElement(  # Create a sub-element under the "per-frame" element with the tag "frame" and set its "number" attribute to the current frame number and its text content to the corresponding PSNR value.
            psnr_frames,
            "frame",
            number=str(frame)
        ).text = str(value)

    ssim = ET.SubElement(root, "ssim")  # Create a sub-element under the root element with the tag "ssim" to hold SSIM analysis results
    ET.SubElement(ssim, "global").text = str(result["ssim"]["global (all)"])  # Create a sub-element under the "ssim" element with the tag "global" and set its text content to the global SSIM value from the result dictionary
    ET.SubElement(ssim, "y").text = str(result["ssim"]["y"])  # Create a sub-element under the "ssim" element with the tag "y" and set its text content to the Y-channel SSIM value from the result dictionary
    ET.SubElement(ssim, "u").text = str(result["ssim"]["u"])  # Create a sub-element under the "ssim" element with the tag "u" and set its text content to the U-channel SSIM value from the result dictionary
    ET.SubElement(ssim, "v").text = str(result["ssim"]["v"])  # Create a sub-element under the "ssim" element with the tag "v" and set its text content to the V-channel SSIM value from the result dictionary

    video = ET.SubElement(root, "video")  # Create a sub-element under the root element with the tag "video" to hold video metadata
    ET.SubElement(video, "duration").text = str(result["video"]["duration"])  # Create a sub-element under the "video" element with the tag "duration" and set its text content to the video duration value from the result dictionary
    ET.SubElement(video, "width").text = str(result["video"]["width"])  # Create a sub-element under the "video" element with the tag "width" and set its text content to the video width value from the result dictionary
    ET.SubElement(video, "height").text = str(result["video"]["height"])  # Create a sub-element under the "video" element with the tag "height" and set its text content to the video height value from the result dictionary
    ET.SubElement(video, "fps").text = str(result["video"]["fps"])  # Create a sub-element under the "video" element with the tag "fps" and set its text content to the video FPS value from the result dictionary

    return ET.tostring(root, encoding="unicode")  # Convert the entire XML tree to a string representation in Unicode format and return it as the output of the function