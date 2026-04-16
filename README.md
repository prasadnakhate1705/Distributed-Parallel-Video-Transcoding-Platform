# Transcodify

A **cloud-native, distributed video transcoding system** built on Apache Spark, AWS, and FFmpeg. Users upload videos through a Streamlit UI, choose output formats, codecs, and resolutions, then watch the pipeline transcode across a Spark cluster and stream the results back via HLS.

The project demonstrates distributed systems design, event-driven architecture, IaC with Terraform, and real-time job orchestration — all wired together without managed services like EMR.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Python · Streamlit |
| Backend API | Python · Flask (app factory + Blueprints) |
| Job Queue | AWS DynamoDB (`PENDING → PROCESSING → COMPLETED`) |
| Object Storage | AWS S3 (input videos, intermediate segments, HLS output) |
| Event Trigger | AWS Lambda (S3 `ObjectCreated` → DynamoDB job record) |
| Distributed Processing | Apache Spark standalone cluster on EC2 (PySpark) |
| Transcoding Engine | FFmpeg (H.264 / H.265 / VP9 / AV1) |
| Streaming | HLS (`.m3u8` + `.ts` segments) · HTTP Range requests · HLS.js |
| Infrastructure | Terraform (EC2, S3, DynamoDB, Lambda, IAM, Security Groups) |
| Auth | API key (`X-API-Key` header) on all routes |

---

## Key Features

- **Multi-rendition ABR ladder** — one job can produce 360p / 720p / 1080p / 4K outputs simultaneously
- **Single vs. Parallel modes** — single-node sequential or distributed `(rendition × segment)` RDD tasks across Spark workers
- **Atomic job locking** — DynamoDB conditional expressions prevent duplicate processing across workers
- **Retry logic** — configurable `MAX_RETRIES`; failed jobs reset to `PENDING` and re-queue automatically
- **Real-time status** — Server-Sent Events stream job updates to the frontend; falls back to polling
- **HLS streaming** — outputs packaged as `.m3u8` playlists, played via HLS.js (Chrome/Firefox/Safari)
- **HTTP Range requests** — seek-and-play support in the streaming endpoint
- **IaC** — full Terraform module provisions the entire stack: Spark cluster, S3, DynamoDB, Lambda, IAM
- **No credentials on EC2** — Spark workers use IAM instance profiles; no keys in config files
- **30-day TTL** — completed job records auto-expire from DynamoDB via the `ExpiresAt` attribute

---

## Architecture

```
          ┌──────────────────┐
          │   Streamlit UI   │
          │  (frontend/)     │
          └────────┬─────────┘
                   │ POST /upload  (X-API-Key)
                   ▼
          ┌──────────────────┐
          │   Flask API      │
          │  (api/)          │
          │                  │
          │ 1. Write job to  │
          │    DynamoDB      │
          │ 2. Upload to S3  │
          └────────┬─────────┘
                   │
        ┌──────────┴───────────┐
        │                      │
        ▼                      ▼
┌──────────────┐     ┌──────────────────┐
│  S3 Bucket   │     │  DynamoDB Table  │
│  videos/     │     │  Status: PENDING │
└──────┬───────┘     └──────────────────┘
       │ S3 event                │
       ▼                         │ poll
┌──────────────┐                 │
│ AWS Lambda   │  (fallback)     │
│ conditional  ├─────────────────┘
│ put_item     │
└──────────────┘
                        │ poll + atomic lock
                        ▼
          ┌─────────────────────────┐
          │  Spark Cluster (EC2)    │
          │  worker/                │
          │                         │
          │  single_node.py         │
          │  Sequential per-        │
          │  rendition FFmpeg       │
          │                         │
          │  multi_node.py          │
          │  (rendition × segment)  │
          │  RDD → parallel FFmpeg  │
          └────────────┬────────────┘
                       │ upload HLS output
                       ▼
          ┌──────────────────────────┐
          │  S3 Bucket               │
          │  transcoded/             │
          │  *.m3u8  *.ts  *.mp4     │
          └────────────┬─────────────┘
                       │ presigned URL
                       ▼
          ┌──────────────────────────┐
          │ Flask /stream endpoint   │
          │ HLS.js player in UI      │
          └──────────────────────────┘
```

---

## Project Structure

```
Video_Transcoding/
│
├── api/                            # Flask REST API
│   ├── app.py                      # App factory, API-key auth, blueprint registration
│   ├── config.py                   # Env var loading + validate()
│   ├── requirements.txt
│   ├── routes/
│   │   ├── upload.py               # POST /upload — validate, create DynamoDB record, upload to S3
│   │   └── stream.py               # GET /videos, /stream, /jobs, /jobs/<id>, /jobs/<id>/events (SSE)
│   └── services/
│       ├── jobs.py                 # DynamoDB CRUD (create, get, list with pagination, TTL)
│       └── s3.py                   # S3 upload, list, presigned URL, chunked range streaming
│
├── worker/                         # Transcoding workers (run on Spark cluster or locally)
│   ├── config.py                   # Env var loading + validate()
│   ├── ffmpeg_utils.py             # segment(), transcode_segment(), merge_and_package_hls(), upload_outputs()
│   ├── job_store.py                # DynamoDB ops: list_pending (paginated), lock, complete, retry_or_fail
│   ├── single_node.py              # Sequential poller: PENDING → lock → transcode all renditions → COMPLETED
│   └── multi_node.py               # PySpark poller: (rendition × segment) RDD tasks → merge → COMPLETED
│
├── frontend/                       # Streamlit web UI
│   ├── app.py                      # Page config, sidebar navigation
│   ├── api_client.py               # requests wrapper — injects X-API-Key on every call
│   ├── config.py                   # FLASK_URL, API_KEY, option lists
│   ├── requirements.txt
│   └── views/
│       ├── home.py                 # Landing page — feature overview + codec/resolution reference
│       ├── upload.py               # Upload form, rendition selector, live job status polling
│       ├── results.py              # Job list, summary metrics, Single vs. Parallel bar chart
│       └── stream.py               # Video selector, HLS.js player, presigned URL expander
│
├── lambda/                         # AWS Lambda — S3 event → DynamoDB fallback job record
│   ├── handler.py                  # Extracts job_id from S3 key; conditional put (skips if API record exists)
│   └── requirements.txt
│
├── infra/
│   ├── terraform/                  # Full IaC for the entire AWS stack
│   │   ├── main.tf                 # Provider, AMI data source, default VPC
│   │   ├── variables.tf            # All input variables
│   │   ├── outputs.tf              # spark_master_url, public IPs, submit command
│   │   ├── ec2.tf                  # Spark master + N worker EC2 instances (bootstrap via user-data)
│   │   ├── iam.tf                  # Instance profiles (S3 + DynamoDB) and Lambda execution role
│   │   ├── s3.tf                   # S3 bucket (SSE, versioning, public block, Lambda notification)
│   │   ├── dynamodb.tf             # Jobs table (PAY_PER_REQUEST, StatusIndex GSI, TTL)
│   │   ├── lambda.tf               # Lambda function, S3 invocation permission, CloudWatch log group
│   │   ├── security_groups.tf      # Spark ports (7077, 8080, 8081, 4040-4050) + SSH
│   │   └── terraform.tfvars.example
│   └── scripts/
│       ├── bootstrap_master.sh     # Installs Java 11, FFmpeg, Spark; starts spark-master
│       ├── bootstrap_worker.sh     # Same setup; waits for master on port 7077 before registering
│       └── submit_job.sh           # spark-submit wrapper — reads SPARK_MASTER_URL from .env
│
├── assets/
│   ├── demo.png
│   ├── stream.jpg
│   └── upload.png
│
├── .env.example                    # Template for all required environment variables
└── .gitignore
```

---

## How It Works

### Upload Flow
1. User selects output format, codec, and one or more resolutions in the UI
2. Frontend calls `POST /upload` with the file and rendition settings
3. API validates inputs, writes a `PENDING` job record to DynamoDB (with the full rendition list), then uploads to S3
4. Lambda fires on the S3 event but skips creating a duplicate record — it extracts the `job_id` embedded in the S3 key and uses `attribute_not_exists(JobId)` to guard the insert

### Single Node Mode
1. Worker polls DynamoDB for `PENDING` jobs
2. Atomically locks a job: `PENDING → PROCESSING` via conditional update
3. Downloads video from S3, iterates over each rendition
4. FFmpeg transcodes to target resolution/codec, then packages HLS (`.m3u8` + `.ts` segments)
5. Uploads outputs to S3 `transcoded/` prefix
6. Marks job `COMPLETED` with per-rendition output keys, duration, and `Mode=Single`

### Multi Node Mode (PySpark)
1. Same atomic locking as single-node
2. Video split into 2-minute `.ts` segments via FFmpeg — segments uploaded to `transcoded/segments/{job_id}/`
3. Cartesian product `(rendition × segment)` → one Spark task per pair (e.g. 3 resolutions × 10 segments = 30 tasks)
4. Each task: download segment, transcode with FFmpeg, re-upload with namespaced S3 key
5. Results grouped by resolution on the driver; segments concatenated and repackaged into HLS per rendition
6. Intermediate segments deleted; job marked `COMPLETED` with `Mode=Parallel`

### Parallelism Design
```
Renditions: [720p, 1080p, 4K]
Segments:   [seg000.ts, seg001.ts, ..., seg009.ts]

Spark tasks (30 total):
  (720p,  seg000) (720p,  seg001) ... (720p,  seg009)
  (1080p, seg000) (1080p, seg001) ... (1080p, seg009)
  (4K,    seg000) (4K,    seg001) ... (4K,    seg009)
```

### Retry Logic
If a worker throws an exception, `retry_or_fail()` atomically increments `RetryCount` and sets `Status` to either `PENDING` (if `RetryCount ≤ MAX_RETRIES`) or `FAILED`. The condition is guarded on `Status = PROCESSING` so only one worker can increment the count.

---

## Setup

### Prerequisites
- Python 3.10+
- FFmpeg installed and on `PATH` (for running workers locally)
- AWS account with credentials that have S3, DynamoDB, Lambda, and IAM permissions
- Terraform 1.5+ (for infrastructure provisioning)

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd Video_Transcoding

cp .env.example .env
# Edit .env — fill in AWS credentials, S3 bucket, and generate an API key:
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Run locally (dev mode)

```bash
# Install dependencies
pip install -r api/requirements.txt
pip install -r frontend/requirements.txt

# Start Flask API (port 5000)
python -m flask --app api.app run --port 5000

# Start Streamlit UI (port 8501) — in a second terminal
streamlit run frontend/app.py
```

Open http://localhost:8501 in your browser.

> Note: With placeholder AWS credentials, the UI loads but upload/transcoding will fail until real credentials are set in `.env`.

### 3. Run the worker locally

```bash
pip install -r worker/requirements.txt

# Single-node worker (polls DynamoDB, processes jobs sequentially)
python -m worker.single_node

# OR multi-node (uses local[*] Spark by default)
python -m worker.multi_node
```

---

## Infrastructure (Terraform)

### Provision the full AWS stack

```bash
cd infra/terraform

cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars:
#   key_pair_name    = "your-ec2-keypair"
#   allowed_ssh_cidr = "$(curl -s ifconfig.me)/32"

terraform init
terraform plan
terraform apply
```

This provisions:
- **S3 bucket** — SSE-S3 encryption, versioning, public access blocked, Lambda event notification on `videos/`
- **DynamoDB table** — `PAY_PER_REQUEST`, `StatusIndex` GSI on `Status`, 30-day TTL via `ExpiresAt`
- **Lambda function** — Python 3.12, triggered by S3, writes fallback `PENDING` job records
- **Spark master EC2** — AL2023, Java 11, FFmpeg, Spark 3.5.1; starts `spark-master` on boot
- **Spark worker EC2s** — same setup; retry-loop waits for master on port 7077 before registering
- **IAM instance profiles** — workers get S3 and DynamoDB access via metadata service (no keys on EC2)
- **Security groups** — SSH (22), Spark submit (7077), master UI (8080), worker UI (8081), driver callbacks (4040–4050)

### After provisioning, update your `.env`

```bash
# Copy the Spark master URL into your local .env
terraform output spark_master_url   # → spark://10.x.x.x:7077
```

```env
SPARK_MASTER_URL=spark://10.x.x.x:7077
```

### Submit a Spark job to the cluster

```bash
# From the repo root
bash infra/scripts/submit_job.sh
```

### Tear down

```bash
terraform destroy
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | Yes | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | Yes | AWS secret key |
| `AWS_REGION` | Yes | e.g. `us-east-1` |
| `S3_BUCKET` | Yes | S3 bucket name for input and output |
| `JOBS_TABLE` | No | DynamoDB table name (default: `TranscodeJobs`) |
| `API_KEY` | Yes | Secret for `X-API-Key` header — generate with `secrets.token_hex(32)` |
| `FLASK_URL` | No | API base URL for frontend (default: `http://localhost:5000`) |
| `SPARK_MASTER_URL` | No | `local[*]` for dev, `spark://ip:7077` for cluster (default: `local[*]`) |
| `POLL_INTERVAL` | No | Seconds between worker polls (default: `30`) |
| `SEGMENT_DURATION` | No | FFmpeg segment length in seconds (default: `120`) |
| `MAX_RETRIES` | No | Max job retry attempts before marking FAILED (default: `3`) |

---

## API Reference

All endpoints (except `/health`) require the `X-API-Key` header.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check — no auth required |
| `POST` | `/upload` | Upload video file + rendition settings; returns `job_id` |
| `GET` | `/jobs` | List all jobs (optional `?status=PENDING\|PROCESSING\|COMPLETED\|FAILED`) |
| `GET` | `/jobs/<job_id>` | Get single job detail including outputs |
| `GET` | `/jobs/<job_id>/events` | Server-Sent Events stream — emits job updates until terminal state |
| `GET` | `/videos` | List all S3 keys under `transcoded/` |
| `GET` | `/stream?key=<s3_key>` | Generate a 1-hour presigned URL for an S3 object |
| `GET` | `/stream/<s3_key>` | Range-aware byte-range proxy (chunked, no full-file buffering) |

### POST /upload — form fields

| Field | Type | Description |
|---|---|---|
| `file` | file | Video file (`.mp4`, `.mov`, `.avi`) |
| `mode` | string | `single` or `parallel` |
| `format` | string | Output container: `mp4`, `mov`, `avi` |
| `codec` | string | `libx264`, `libx265`, `libvpx-vp9`, `libaom-av1` |
| `resolutions` | string (multi) | One or more of: `640x360`, `1280x720`, `1920x1080`, `3840x2160` |

---

## Screenshots

![Architecture Demo](assets/demo.png)
![Frontend Upload](assets/upload.png)
![Frontend Stream](assets/stream.jpg)
