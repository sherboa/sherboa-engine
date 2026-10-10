from subprocess import CalledProcessError
import tempfile
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from vmaf import (video_compare, generate_csv, generate_xml, generate_vmaf_graph, generate_psnr_graph, generate_ssim_graph)
from ffprobe import (is_valid_video, get_video_dimensions, get_video_duration, get_video_metadata, are_durations_compatible)

MAX_FILE_SIZE = 250 * 1024 * 1024  # File limit: 250 MB in bytes
FRONTEND_URL = "https://sherboa.com"



app = FastAPI()  # Initialize the FastAPI application

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.get("/")  # Define a GET endpoint for the root URL

def home():  # Define the root endpoint function
    return {"message": "VMAF API is running"}  # Return a JSON response indicating that the API is running


@app.post("/vmaf")  # Define a POST endpoint for computing VMAF


def calculate_vmaf(reference: UploadFile = File(...), distorted: UploadFile = File(...), format: str = "json") -> dict:  # Define the endpoint function to compute VMAF
    """
    This endpoint computes the VMAF score between a reference video and a distorted video uploaded by the user.
    It uses the vmaf_compare function to perform the computation.
    Parameters:
    - reference: The reference video file uploaded by the user.
    - distorted: The distorted video file uploaded by the user.
    Returns:
    - A dictionary containing the computed VMAF score.
    """


    if format not in {"json", "csv", "xml", "png", "psnr_png", "ssim_png"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid format. Supported formats: json, csv, xml, png, psnr_png, ssim_png"
        )

    print(">>> FUNCTION 'calculate_vmaf' EXECUTED <<<", flush=True)  # Print a message indicating that the VMAF calculation has started

    if not reference.filename or not distorted.filename:  # Error handling #1: check if both video files are provided
        raise HTTPException(
            status_code=400,
            detail="Invalid input: both video files must be provided"
        )

    reference.file.seek(0, 2)  # Move the file pointer to the end of the reference video file to determine its size
    reference_size = reference.file.tell()  # Get the size of the reference video file

    distorted.file.seek(0, 2)  # Move the file pointer to the end of the distorted video file to determine its size
    distorted_size = distorted.file.tell()  # Get the size of the distorted video file

    if reference_size > MAX_FILE_SIZE or distorted_size > MAX_FILE_SIZE:  # Error handling #3: check if either video file exceeds the maximum allowed size
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds the limit of {MAX_FILE_SIZE / (1024 * 1024)} MB"
        )


    print("REFERENCE SIZE:", reference_size, flush=True)  # Print the size of the reference video file for debugging purposes
    print("DISTORTED SIZE:", distorted_size, flush=True)  # Print the size of the distorted video file for debugging purposes

    reference.file.seek(0)  # Move the file pointer back to the beginning of the reference video file for reading
    distorted.file.seek(0)  # Move the file pointer back to the beginning of the distorted video file for reading

    if reference_size == 0 or distorted_size == 0:  # Error handling #2: check if both video files contain data
        raise HTTPException(
            status_code=400,
            detail="Both video files must contain data"
        )
  

    with tempfile.NamedTemporaryFile(suffix=".mp4") as ref_file:
        shutil.copyfileobj(reference.file, ref_file)
        #ref_file.write(reference.file.read())  # Write the contents of the uploaded reference video file to a temporary file
        ref_file.flush()  # Flush the temporary file to ensure all data is written before proceeding

        with tempfile.NamedTemporaryFile(suffix=".mp4") as dist_file:
            shutil.copyfileobj(distorted.file, dist_file)
            #dist_file.write(distorted.file.read())  # Write the contents of the uploaded distorted video file to a temporary file
            dist_file.flush()  # Flush the temporary file to ensure all data is written before proceeding


            if not is_valid_video(ref_file.name) or not is_valid_video(dist_file.name):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid video file"
                )


            reference_width, reference_height = get_video_dimensions(ref_file.name)
            distorted_width, distorted_height = get_video_dimensions(dist_file.name)

            if (reference_width, reference_height) != (distorted_width, distorted_height):
                raise HTTPException(
                    status_code=400,
                    detail="Video dimensions must match"
                )


            reference_duration = get_video_duration(ref_file.name)
            distorted_duration = get_video_duration(dist_file.name)

            if not are_durations_compatible(reference_duration, distorted_duration):
                raise HTTPException(
                    status_code=400,
                    detail="Video durations are not compatible"
                )

            video_metadata = get_video_metadata(ref_file.name)

            try:
                result = video_compare(ref_file.name, dist_file.name)
            except CalledProcessError:  # Error handling #4: catch CalledProcessError raised by subprocess.run() in vmaf_compare() if FFmpeg fails to execute properly
                raise HTTPException(
                    status_code=400,
                    detail="Invalid video file"
                )
            except RuntimeError as e:  # Error handling #5: catch RuntimeError raised by vmaf_compare() if VMAF computation exceeds the timeout limit
                raise HTTPException(
                    status_code=504,
                    detail=str(e)
                )



    if format == "csv":
        csv_data = generate_csv(result)

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=results.csv"
            }
        )

    if format == "xml":
        xml_data = generate_xml(result)

        return Response(
            content=xml_data,
            media_type="application/xml",
            headers={
                "Content-Disposition": "attachment; filename=results.xml"
            }
        )

    if format == "png":
        png_data = generate_vmaf_graph(result)

        return Response(
            content=png_data,
            media_type="image/png",
            headers={
                "Content-Disposition": "attachment; filename=vmaf-graph.png"
            }
        )

    if format == "psnr_png":
        png_data = generate_psnr_graph(result)

        return Response(
            content=png_data,
            media_type="image/png",
            headers={
                "Content-Disposition": "attachment; filename=psnr-graph.png"
            }
        )

    if format == "ssim_png":
        png_data = generate_ssim_graph(result)

        return Response(
            content=png_data,
            media_type="image/png",
            headers={
                "Content-Disposition": "attachment; filename=ssim-graph.png"
            }
        )


    return {
        **result,
        "video": video_metadata
    }