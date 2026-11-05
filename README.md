# Sherboa Engine

Backend API for **Sherboa**, a web-based tool for comparing video quality using objective quality metrics.

## Overview

Sherboa Engine provides the backend processing capabilities for Sherboa.

It receives reference and distorted video files, validates their compatibility, performs objective video quality analysis, and returns the results through a REST API.

The engine is built with FastAPI and uses FFmpeg and Netflix VMAF to calculate video quality metrics.

## Features

- Validate uploaded video files
- Generate video thumbnails for manual synchronization
- Apply user-defined synchronization offsets before analysis
- Calculate VMAF, PSNR, and SSIM metrics
- Provide per-frame quality measurements
- Export analysis results in JSON, CSV, and XML formats
- Generate metric visualization charts in PNG format
- Enforce request rate limits and daily usage quotas
- Docker-based deployment

## Tech Stack

- **Python 3.12** — backend application logic
- **FastAPI** — REST API framework
- **Uvicorn** — ASGI application server
- **FFmpeg 8.0** — video processing and quality metric calculations
- **Netflix libvmaf 3.2.1** — objective video quality assessment
- **Matplotlib** — metric chart generation
- **SQLite** — persistent usage quota tracking
- **Docker** — application containerization

## Project Structure

```text
sherboa-engine/
├── infra/
│   └── caddy/
│       └── Caddyfile          # Reverse proxy configuration
├── tests/                     # Automated tests
├── main.py                    # API endpoints and application entry point
├── quality_metrics.py         # VMAF, PSNR, and SSIM calculations
├── ffprobe.py                # Video metadata and validation
├── thumbnails.py             # Thumbnail generation and management
├── graphs.py                 # Metric chart generation
├── exports.py                # Analysis result exports
├── rate_limiter.py           # Request rate limiting
├── usage_limiter.py          # Persistent daily usage quotas
├── vmaf.json                 # VMAF configuration
├── requirements.txt          # Python dependencies
├── Dockerfile                # Container image definition
├── README.md
└── LICENSE
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | API health check |
| POST | `/prepare` | Validate videos and generate synchronization thumbnails |
| GET | `/thumbnails/{analysis_id}/{video_type}/{filename}` | Retrieve generated thumbnails |
| POST | `/vmaf` | Run video quality analysis |

The `/vmaf` endpoint supports the following output formats:

- `json` — Complete analysis results (default)
- `csv` — Per-frame metric data
- `xml` — Analysis results in XML
- `png` — VMAF graph
- `psnr_png` — PSNR graph
- `ssim_png` — SSIM graph

## How It Works

Sherboa Engine processes video comparisons through the following workflow:

1. Receive reference and distorted video files.
2. Validate video formats, dimensions, and duration compatibility.
3. Generate thumbnails to assist manual synchronization.
4. Apply the synchronization offset selected by the user.
5. Process the videos using FFmpeg and calculate VMAF, PSNR, and SSIM.
6. Return the analysis results to Sherboa Web.

Video preparation and quality analysis are handled through separate API endpoints. The `/prepare` endpoint generates thumbnails without running quality metrics or consuming the daily analysis quota.

The `/vmaf` endpoint performs the actual analysis, applying the user-defined temporal offset before calculating the quality metrics.

The engine handles all video processing and metric calculations. The frontend is responsible for user interaction and result visualization.

## Configuration

The production API is available at:

```text
https://api.sherboa.com
```

The API accepts browser requests from the official Sherboa Web frontend.

## Development

Clone the repository:

```bash
git clone https://github.com/sherboa/sherboa-engine.git
cd sherboa-engine
```

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

Sherboa Engine also requires FFmpeg compiled with libvmaf support.

For local development, ensure these native dependencies are available before starting the application:

```bash
uvicorn main:app --reload
```

Alternatively, build the Docker image to use the dependencies defined in the project Dockerfile:

```bash
docker build -t sherboa-engine .
```

The interactive API documentation is available at:

```text
http://localhost:8000/docs
```

## Deployment

Sherboa Engine runs as a Docker container on AWS infrastructure.

The API is exposed through **Caddy** as a reverse proxy, with **Cloudflare** providing DNS and edge protection.

The production service is available at:

[https://api.sherboa.com](https://api.sherboa.com)

## Related Repositories

- **Sherboa Web** — Frontend application for video uploads, analysis, and results visualization. [https://github.com/sherboa/sherboa-web](https://github.com/sherboa/sherboa-web)

## License

See the [LICENSE](LICENSE) file for licensing information.