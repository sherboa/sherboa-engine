# This is the main FastAPI application file for the VMAF, PSNR, and SSIM API. It defines the endpoints and handles video file uploads, validation, and quality metric computation.

from subprocess import CalledProcessError, TimeoutExpired
import tempfile
import shutil
import math
import re
from uuid import UUID
from fastapi import FastAPI, UploadFile, File, HTTPException, Response, Depends, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from quality_metrics import (video_compare, UnsupportedFrameRateError)
from graphs import (generate_vmaf_graph, generate_psnr_graph, generate_ssim_graph)
from exports import (generate_csv, generate_xml)
from ffprobe import (is_valid_video, get_video_dimensions, get_video_duration, get_video_metadata, are_durations_compatible, get_overlap_interval)
from rate_limiter import RateLimitMiddleware, limit_analysis_concurrency
from usage_limiter import UsageLimiter, UsageLimitExceeded, USAGE_LIMIT_MAX_ANALYSES
import thumbnails

########################################################################################################################
# CONSTANTS
########################################################################################################################
MAX_FILE_SIZE = 250 * 1024 * 1024  # Maximum allowed size for each uploaded video, in bytes
FRONTEND_URL = "https://sherboa.com"  # Authorized frontend origin for cross-origin browser requests


########################################################################################################################
# APPLICATION INITIALIZATION
########################################################################################################################
app = FastAPI()
app.add_middleware(RateLimitMiddleware)
usage_limiter = UsageLimiter()  # Persistent rolling-window quota shared across container recreations

########################################################################################################################
# CORS CONFIGURATION
########################################################################################################################
app.add_middleware(  # Allow browser requests only from the official sherboa frontend; CORS is a browser access policy, not a substitute for authentication or rate limiting
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

########################################################################################################################
# HEALTH / ROOT ENDPOINT
########################################################################################################################
@app.get("/")  # Define a GET endpoint for the root URL
def home():  # Define the root endpoint function
    return {"message": "VMAF API is running"}  # Return a JSON response indicating that the API is running

########################################################################################################################
# THUMBNAIL ENDPOINT
########################################################################################################################
@app.get(
    "/thumbnails/{analysis_id}/{video_type}/{filename}",
    include_in_schema=False,
)
def get_thumbnail(analysis_id: str, video_type: str, filename: str,):
    """
    Serve a generated thumbnail without exposing arbitrary filesystem paths.
    """

    not_found = HTTPException(
        status_code=404,
        detail="Thumbnail not found",
    )

    try:  # Accept only canonical UUIDs as analysis identifiers
        canonical_id = str(UUID(analysis_id))
    except (ValueError, AttributeError):
        raise not_found

    if canonical_id != analysis_id.lower():
        raise not_found

    if video_type not in {"reference", "distorted"}:  # Restrict access to the two expected video directories
        raise not_found

    if not re.fullmatch(r"thumbnail_\d{4,}\.jpg", filename):  # Only serve generated JPEG thumbnails
        raise not_found

    thumbnails.cleanup_expired_thumbnails(root=thumbnails.THUMBNAIL_ROOT,)  # Remove expired analyses before attempting to serve a file

    root = thumbnails.THUMBNAIL_ROOT.resolve()
    analysis_dir = (root / canonical_id).resolve()

    if analysis_dir.parent != root:  # Ensure the analysis directory is directly inside the thumbnail root
        raise not_found

    if (analysis_dir / ".generating").exists():  # Never serve files while an analysis is still generating thumbnails
        raise not_found

    video_dir = (analysis_dir / video_type).resolve()

    try:
        video_dir.relative_to(analysis_dir)
    except ValueError:
        raise not_found

    image_path = (video_dir / filename).resolve()

    try:  # Prevent symlinks or path manipulation from escaping the video directory
        image_path.relative_to(video_dir)
    except ValueError:
        raise not_found

    if not image_path.is_file():
        raise not_found

    return FileResponse(
        path=image_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )



########################################################################################################################
# VIDEO PREPARATION ENDPOINT
########################################################################################################################
@app.post("/prepare")
def prepare_videos(reference: UploadFile = File(...), distorted: UploadFile = File(...),) -> dict:
    """
    Validate both videos and generate thumbnails without running quality metrics or consuming the daily analysis quota.
    """

    if not reference.filename or not distorted.filename:
        raise HTTPException(
            status_code=400,
            detail="invalid input: both video files must be provided",
        )

    reference.file.seek(0, 2)
    reference_size = reference.file.tell()

    distorted.file.seek(0, 2)
    distorted_size = distorted.file.tell()

    if reference_size > MAX_FILE_SIZE or distorted_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"file size exceeds the limit of {MAX_FILE_SIZE / (1024 * 1024)} MB",
        )

    if reference_size == 0 or distorted_size == 0:
        raise HTTPException(
            status_code=400,
            detail="both video files must contain data",
        )

    reference.file.seek(0)
    distorted.file.seek(0)

    analysis_dir = None

    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4") as ref_file:
            shutil.copyfileobj(reference.file, ref_file)
            ref_file.flush()

            with tempfile.NamedTemporaryFile(suffix=".mp4") as dist_file:
                shutil.copyfileobj(distorted.file, dist_file)
                dist_file.flush()

                try:
                    if not is_valid_video(ref_file.name) or not is_valid_video(dist_file.name):
                        raise HTTPException(
                            status_code=400,
                            detail="invalid video file",
                        )

                    reference_width, reference_height = get_video_dimensions(ref_file.name)
                    distorted_width, distorted_height = get_video_dimensions(dist_file.name)

                    if (reference_width, reference_height) != (
                        distorted_width,
                        distorted_height,
                    ):
                        raise HTTPException(
                            status_code=400,
                            detail="video dimensions must match",
                        )

                    reference_duration = get_video_duration(ref_file.name)
                    distorted_duration = get_video_duration(dist_file.name)

                    if not are_durations_compatible(reference_duration, distorted_duration,):
                        raise HTTPException(
                            status_code=400,
                            detail="video durations are not compatible",
                        )

                    video_metadata = get_video_metadata(ref_file.name)
                    distorted_video_metadata = get_video_metadata(dist_file.name)

                except TimeoutExpired:
                    raise HTTPException(
                        status_code=504,
                        detail="video inspection timed out",
                    )

                analysis_dir = thumbnails.create_analysis_thumbnail_dir()
                analysis_dir.mkdir(parents=False, exist_ok=False)

                generating_marker = analysis_dir / ".generating"
                generating_marker.touch()

                thumbnails.generate_thumbnails(
                    ref_file.name,
                    analysis_dir / "reference",
                )

                thumbnails.generate_thumbnails(
                    dist_file.name,
                    analysis_dir / "distorted",
                )

                generating_marker.unlink()

                return {
                    "video": video_metadata,
                    "distorted_video": distorted_video_metadata,
                    "analysis_id": analysis_dir.name,
                    "thumbnails_available": True,
                }

    except HTTPException:
        if analysis_dir is not None:
            shutil.rmtree(analysis_dir, ignore_errors=True)
        raise

    except Exception as e:
        if analysis_dir is not None:
            shutil.rmtree(analysis_dir, ignore_errors=True)

        print(f"Video preparation failed: {e}", flush=True)

        raise HTTPException(
            status_code=500,
            detail="video preparation failed",
        )



########################################################################################################################
# VIDEO QUALITY ANALYSIS ENDPOINT
########################################################################################################################
@app.post("/vmaf")  # Define a POST endpoint for computing VMAF

def calculate_vmaf(request: Request, reference: UploadFile = File(...), distorted: UploadFile = File(...), format: str = "json", offset: float = Form(0.0), _: None = Depends(limit_analysis_concurrency)) -> dict:  # Define the endpoint function to compute VMAF
    """
    Compare a reference video against a distorted video.

    Processing stages:
    1. Validate the requested output format and uploaded files.
    2. Enforce individual file-size limits and reject empty uploads.
    3. Copy uploads into temporary files for external media tools.
    4. Inspect video validity, dimensions, duration, and metadata with ffprobe.
    5. Calculate VMAF, PSNR, and SSIM using video_compare().
    6. Return JSON results or generate a downloadable CSV, XML, or PNG graph.

    The concurrency dependency allows only one active analysis per process.
    
    Parameters:
    - reference: The reference video file uploaded by the user.
    - distorted: The distorted video file uploaded by the user.
    - format: The requested output format (json, csv, xml, png, psnr_png, or ssim_png). Defaults to "json".
    - offset: Temporal synchronization offset in seconds applied to the distorted video relative to the reference video. Defaults to 0.0 (no offset).
    - _:  A dependency that limits concurrent video analyses to one at a time, returning HTTP 429 if another analysis is already in progress.
    Returns:
    - A dictionary with quality metrics and video metadata for JSON output, or a response containing the requested downloadable file.
    Raises:
    - HTTPException: For invalid input, incompatible videos, unsupported formats, FFmpeg/ffprobe failures, or processing timeouts.
    """

    # Validate the requested output format before starting media processing
    if format not in {"json", "csv", "xml", "png", "psnr_png", "ssim_png"}:  # Error handling #6: check if the requested output format is valid
        raise HTTPException(
            status_code=400,
            detail="invalid format. Supported formats: json, csv, xml, png, psnr_png, ssim_png"
        )

    # Validate the synchronization offset before processing uploaded videos
    if not math.isfinite(offset):
        raise HTTPException(
            status_code=400,
            detail="offset must be a finite number"
        )

    print(">>> FUNCTION 'calculate_vmaf' EXECUTED <<<", flush=True)  # Print a message indicating that the VMAF calculation has started

    # Ensure both uploads include filenames
    if not reference.filename or not distorted.filename:  # Error handling #1: check if both video files are provided
        raise HTTPException(
            status_code=400,
            detail="invalid input: both video files must be provided"
        )

    # Determine the size of each upload without loading the whole file into memory
    reference.file.seek(0, 2)  # Move the file pointer to the end of the reference video file to determine its size
    reference_size = reference.file.tell()  # Get the size of the reference video file

    distorted.file.seek(0, 2)  # Move the file pointer to the end of the distorted video file to determine its size
    distorted_size = distorted.file.tell()  # Get the size of the distorted video file


    # Enforce the maximum size independently for each video
    if reference_size > MAX_FILE_SIZE or distorted_size > MAX_FILE_SIZE:  # Error handling #3: check if either video file exceeds the maximum allowed size
        raise HTTPException(
            status_code=413,
            detail=f"file size exceeds the limit of {MAX_FILE_SIZE / (1024 * 1024)} MB"
        )


    print("REFERENCE SIZE:", reference_size, flush=True)  # Print the size of the reference video file for debugging purposes
    print("DISTORTED SIZE:", distorted_size, flush=True)  # Print the size of the distorted video file for debugging purposes

    # Reject empty files and reset both file pointers before copying
    reference.file.seek(0)  # Move the file pointer back to the beginning of the reference video file for reading
    distorted.file.seek(0)  # Move the file pointer back to the beginning of the distorted video file for reading

    if reference_size == 0 or distorted_size == 0:  # Error handling #2: check if both video files contain data
        raise HTTPException(
            status_code=400,
            detail="both video files must contain data"
        )

    analysis_id = None
    thumbnails_available = False


    with tempfile.NamedTemporaryFile(suffix=".mp4") as ref_file:
        shutil.copyfileobj(reference.file, ref_file)
        ref_file.flush()  # Flush the temporary file to ensure all data is written before proceeding

        with tempfile.NamedTemporaryFile(suffix=".mp4") as dist_file:
            shutil.copyfileobj(distorted.file, dist_file)
            dist_file.flush()  # Flush the temporary file to ensure all data is written before proceeding

            ############################################################################################################
            # VIDEO INSPECTION AND VALIDATION
            ############################################################################################################
            try:
                if not is_valid_video(ref_file.name) or not is_valid_video(dist_file.name):
                    raise HTTPException(
                        status_code=400,
                        detail="invalid video file"
                    )

                reference_width, reference_height = get_video_dimensions(ref_file.name)
                distorted_width, distorted_height = get_video_dimensions(dist_file.name)

                if (reference_width, reference_height) != (distorted_width, distorted_height):
                    raise HTTPException(
                        status_code=400,
                        detail="video dimensions must match"
                    )

                reference_duration = get_video_duration(ref_file.name)
                distorted_duration = get_video_duration(dist_file.name)

                try:
                    get_overlap_interval(
                        reference_duration,
                        distorted_duration,
                        offset,
                    )
                except ValueError as e:
                    raise HTTPException(
                        status_code=400,
                        detail=str(e),
                    )

                video_metadata = get_video_metadata(ref_file.name)
                distorted_video_metadata = get_video_metadata(dist_file.name)

            except TimeoutExpired:  # ffprobe did not finish within its configured timeout
                raise HTTPException(
                    status_code=504,
                    detail="video inspection timed out"
                )

            ###########################################################################################
            # QUALITY METRIC COMPUTATION
            ###########################################################################################
            if not request.client or not request.client.host:
                raise HTTPException(
                    status_code=500,
                    detail="unable to identify client IP"
                )

            client_ip = request.client.host


            try:
                usage_limiter.register_analysis(client_ip)
            except UsageLimitExceeded as e:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"analysis limit reached: maximum "
                        f"{USAGE_LIMIT_MAX_ANALYSES} analyses per IP "
                        f"in a rolling 24-hour window; please try again later."
                    ),
                    headers={"Retry-After": str(e.retry_after)}
                )

            try:  # From this point onward, the analysis counts even if processing fails
                result = video_compare(ref_file.name, dist_file.name, offset=offset)
            except CalledProcessError as e:
                stderr = e.stderr or ""
                print(
                    f"FFmpeg failed with exit code {e.returncode}:\n"
                    + "\n".join(stderr.splitlines()[-30:])
                )
                raise HTTPException(status_code=400, detail="invalid video file")
            except UnsupportedFrameRateError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except RuntimeError as e:
                raise HTTPException(status_code=504, detail=str(e))


    ###################################################################################################
    # CSV FILE: return tabular per-frame metric data as a downloadable file
    ###################################################################################################
    if format == "csv":  # Generate a CSV file containing per-frame VMAF and PSNR values
        csv_data = generate_csv(result)  # Generate a CSV string containing per-frame VMAF and PSNR values using the generate_csv() function

        return Response(
            content=csv_data,  # Return the generated CSV data as the response content
            media_type="text/csv",  # Set the media type of the response to "text/csv" to indicate that the response contains CSV data
            headers={
                "Content-Disposition": "attachment; filename=results.csv"
            }
        )


    ###################################################################################################
    # XML FILE: return the analysis results in XML format
    ##################################################################################################
    if format == "xml":  # Generate an XML file containing the complete analysis results
        xml_data = generate_xml(result)  # Generate an XML string containing the complete analysis results using the generate_xml() function

        return Response(
            content=xml_data,  # Return the generated XML data as the response content
            media_type="application/xml",  # Set the media type of the response to "application/xml" to indicate that the response contains XML data
            headers={
                "Content-Disposition": "attachment; filename=results.xml"  # Set the Content-Disposition header to specify the filename for the downloaded XML file
            }
        )


    ##################################################################################################
    # DELIVERY OF VMAF GRAPH IN PNG FORMAT
    ##################################################################################################
    if format == "png":  # Generate a PNG graph containing per-frame VMAF values
        png_data = generate_vmaf_graph(result)

        return Response(
            content=png_data,  # Return the generated PNG graph data as the response content
            media_type="image/png",  # Set the media type of the response to "image/png" to indicate that the response contains a PNG image
            headers={
                "Content-Disposition": "attachment; filename=vmaf-graph.png"  # Set the Content-Disposition header to specify the filename for the downloaded PNG graph
            }
        )


    ##################################################################################################
    # DELIVERY OF PSNR GRAPH IN PNG FORMAT
    #################################################################################################
    if format == "psnr_png":  # Generate a PNG graph containing per-frame PSNR values
        png_data = generate_psnr_graph(result)

        return Response(
            content=png_data,  # Return the generated PNG graph data as the response content
            media_type="image/png",  # Set the media type of the response to "image/png" to indicate that the response contains a PNG image
            headers={
                "Content-Disposition": "attachment; filename=psnr-graph.png"  # Set the Content-Disposition header to specify the filename for the downloaded PNG graph
            }
        )


    ##################################################################################################
    # DELIVERY OF SSIM GRAPH IN PNG FORMAT
    #################################################################################################
    if format == "ssim_png":  # Generate a PNG graph containing per-frame SSIM values
        png_data = generate_ssim_graph(result)

        return Response(
            content=png_data,  # Return the generated PNG graph data as the response content
            media_type="image/png",  # Set the media type of the response to "image/png" to indicate that the response contains a PNG image
            headers={
                "Content-Disposition": "attachment; filename=ssim-graph.png"  # Set the Content-Disposition header to specify the filename for the downloaded PNG graph
            }
        )

    return {
        **result,  # Merge the computed VMAF, PSNR, and SSIM results with the video metadata into a single dictionary to be returned as the API response
        "video": video_metadata,  # Include the video metadata in the response under the "video" key
        "distorted_video": distorted_video_metadata,
        "analysis_id": analysis_id,
        "thumbnails_available": thumbnails_available,
    }
