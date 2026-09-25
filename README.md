# Indian Financial Document Classification Engine 🇮🇳🏛️

An enterprise-grade, asynchronous AI document classification backend engineered for Indian Scheduled Commercial Banks and Non-Banking Financial Companies (NBFCs).

The platform automates the ingestion, text extraction, and strict taxonomy classification for:
1. **Officially Valid Documents (OVDs)** accepted by the Reserve Bank of India (RBI) under the Master Direction on KYC (Passport, Driving Licence, Aadhaar Card, Voter Identity Card, NREGA Job Card, NPR Letter, and PAN Card / Form 60).
2. **Business, MSME & Supply Chain Lending Documents** (GST Returns, Income Tax Returns, Purchase Orders / Work Orders, Tax Invoices, Bank Statements, Audited Financials, and Business Registrations).

---

## 🏗️ System Architecture

```
                   ┌──────────────────────────────────────────────┐
                   │               Banking Client / UI            │
                   └──────────────────────┬───────────────────────┘
                                          │ HTTPS (Bearer JWT)
                                          ▼
                   ┌──────────────────────────────────────────────┐
                   │             FastAPI Web Engine               │
                   │  - SecurityHeaders (HSTS, CSP, X-Frame: DENY)│
                   │  - TrustedHost & CORS Allowed Origins        │
                   │  - SlowAPI Rate Limiter (IP/Redis)           │
                   │  - OAuth2 Password Auth with JWT (HS256)     │
                   └──────────────┬────────────────┬──────────────┘
                                  │                │
            Enqueues Task Payload │                │ Persists Metadata
                                  ▼                ▼
     ┌──────────────────────────────┐            ┌──────────────────────────────┐
     │       Redis Task Queue       │            │      PostgreSQL Database     │
     │      (localhost:6379)        │            │       (localhost:5432)       │
     └──────────────┬───────────────┘            └──────────────┬───────────────┘
                    │                                           │
                    ▼                                           │
     ┌──────────────────────────────┐                           │
     │       ARQ Worker Node        │                           │
     │  - PyMuPDF / pypdf Hybrid    ├───────────────────────────┘
     │  - GPU PaddleOCR Engine      │ Updates status: PROCESSING -> COMPLETED / FAILED
     │  - LLM Classification Client │
     └──────────────┬───────────────┘
                    │ HTTP POST /v1/chat/completions
                    ▼
     ┌──────────────────────────────┐
     │   Local llama.cpp Server     │
     │      (localhost:8080)        │
     │  Model: Llama-3.2-3B-Instruct│
     └──────────────────────────────┘
```

> 📖 **Deep Dive:** For the comprehensive low-level component diagrams, sequence diagrams, and entity-relationship models, see [ARCHITECTURE.md](file:///f:/doc-classification-engine/ARCHITECTURE.md).

---

## 🚀 Tech Stack & Core Dependencies

* **Web Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+) with async event loop.
* **Database & ORM:** PostgreSQL (`localhost:5432`), [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (Async engine via `asyncpg`), and [Alembic](https://alembic.sqlalchemy.org/) for migrations.
* **Task Queue:** [Redis](https://redis.io/) (`localhost:6379`) with [`arq`](https://arq-docs.helpmanual.io/) (Async Redis Queue) for distributed, asynchronous worker execution.
* **OCR & Extraction Engine:** 
  * `paddlepaddle-gpu` (CUDA-accelerated on NVIDIA RTX 3080) with automatic runtime fallback to CPU.
  * `paddleocr` (v2.10) with textline orientation detection.
  * `PyMuPDF` (`pymupdf`) and `pypdf` hybrid digital text extraction + page rasterization (capped at first 5 pages for enterprise latency).
* **LLM Inference:** `Llama-3.2-3B-Instruct` served locally via [`llama.cpp`](https://github.com/ggerganov/llama.cpp)'s built-in HTTP server (`http://localhost:8080/v1/chat/completions`).
* **Security & Auth:** OAuth2 Password Bearer flow, PyJWT (HS256), Passlib (Bcrypt), SlowAPI rate limiting (IP/Redis), TrustedHostMiddleware, Strict-Transport-Security, and Content Security Policy.

---

## 📋 Strict Taxonomy of Indian Banking Documents

| Category Code | Classification Group | Identifying Anchors & Key Characteristics |
| :--- | :--- | :--- |
| `PASSPORT` | RBI KYC (OVD) | "Republic of India", "Passport No", Machine Readable Zone (MRZ), Nationality: Indian. |
| `DRIVING_LICENCE` | RBI KYC (OVD) | State RTO / Licensing Authority, "Union of India Driving Licence", Form 7, DL number. |
| `AADHAAR_CARD` | RBI KYC (OVD) | UIDAI, "Mera Aadhaar, Meri Pehchan", 12-digit UID/VID, e-Aadhaar, Masked Aadhaar. |
| `VOTER_ID` | RBI KYC (OVD) | Election Commission of India, EPIC Number, Elector's Name, Father's/Husband's name. |
| `NREGA_JOB_CARD` | RBI KYC (OVD) | Mahatma Gandhi NREGA, Job Card Number, State Rural Development, Officer signature. |
| `NPR_LETTER` | RBI KYC (OVD) | Letter issued by the National Population Register containing name and address details. |
| `PAN_CARD` | Mandatory Tax KYC | Income Tax Department, Govt of India, 10-digit alphanumeric PAN (`[A-Z]{5}[0-9]{4}[A-Z]`). |
| `GST_RETURN` | Lending & Trade | Form GSTR-1, GSTR-3B, GSTR-9, or GST Registration Certificate (GST REG-06). |
| `INCOME_TAX_RETURN` | Credit Appraisal | ITR-V, ITR Acknowledgement Number, Assessment Year, Total Income, Computation sheet. |
| `PURCHASE_ORDER` | Supply Chain Finance | "Purchase Order", "Work Order", PO Number, Line Items, Quantity, Rate, Delivery Terms. |
| `TAX_INVOICE` | Supply Chain Finance | Commercial / Tax Invoice, Bill of Supply, Supplier & Buyer GSTIN, HSN/SAC, IRN/QR code. |
| `BANK_STATEMENT` | Loan Underwriting | Bank Account Statement, Account Number, IFSC, Opening & Closing Balances, Transactions. |
| `AUDITED_FINANCIALS` | Corporate Credit | Balance Sheet, Profit & Loss (P&L) Statement, Notes to Accounts, Auditor's Report. |
| `BUSINESS_REGISTRATION` | Legal Constitution | Udyam / MSME Registration Certificate, Certificate of Incorporation (CIN / MCA), Partnership Deed. |
| `UNKNOWN` | Fallback | Illegible, corrupted, non-financial, or unrecognized documents. |

---

## 🔒 Enterprise Security & Storage Controls

1. **Dual PDF & Image Support:**
   * Whitelisted extensions: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.tiff`, `.tif`, `.bmp`.
   * Enforced file size limit: **100MB** (`104,857,600` bytes).
   * Stream-to-disk write with path containment verification to eliminate directory traversal risks (`../../`).
2. **Authentication Mechanism:**
   * OAuth2 Password Bearer flow with cryptographically signed JWT tokens (HS256).
   * Active account verification on all protected endpoints.
3. **Rate Limiting (SlowAPI + Redis):**
   * Default API: `60 requests/minute`.
   * Upload Endpoint: `10 uploads/minute` per IP to safeguard GPU memory and LLM capacity against DDoS.
4. **Host & Origin Isolation:**
   * `CORSMiddleware`: Restricts incoming traffic to enterprise origins (`localhost:3000`, `localhost:8000`).
   * `TrustedHostMiddleware`: Restricts accepted Host headers (`localhost`, `127.0.0.1`, `testserver`).
5. **Security Headers Middleware:**
   * `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
   * `X-Content-Type-Options: nosniff`
   * `X-Frame-Options: DENY`
   * `Content-Security-Policy: default-src 'none'; frame-ancestors 'none';`
   * `Permissions-Policy: camera=(), microphone=(), payment=()`

---

## 🛠️ Step-by-Step Setup & Execution Guide

### 1. Prerequisites
Ensure the following services are running:
* **Python 3.10+**
* **PostgreSQL** running on `localhost:5432` with database `doc_classifier` (user: `postgres`, password: `postgres`).
* **Redis** running on `localhost:6379`.
* **llama.cpp server** running with `Llama-3.2-3B-Instruct` on `http://localhost:8080`.

#### Quickstart PostgreSQL & Redis via Docker (Optional)
```bash
# Start PostgreSQL
docker run --name pg-doc -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=doc_classifier -p 5432:5432 -d postgres:15

# Start Redis
docker run --name redis-doc -p 6379:6379 -d redis:7-alpine
```

#### Launch Local `llama.cpp` Server
```bash
./llama-server \
  -m models/Llama-3.2-3B-Instruct-Q4_K_M.gguf \
  --port 8080 \
  --host 127.0.0.1 \
  -c 4096 \
  -ngl 33
```

---

### 2. Environment Setup & Dependency Installation

```bash
# Navigate to project directory
cd f:\doc-classification-engine

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux/macOS:
source venv/bin/activate

# Install all dependencies (includes paddlepaddle-gpu and PyMuPDF)
pip install -r requirements.txt
```

---

### 3. Database Migrations & Initial Seeding

```bash
# Run Alembic migrations to create tables and enums
alembic upgrade head

# Seed initial default banking operator account
python -m app.seed
```
*Default Operator Credentials:*
* **Username:** `admin`
* **Password:** `admin_secure_pass123`

---

### 4. Running the Application Services

Open two separate terminals with the virtual environment activated:

#### Terminal 1: Start FastAPI REST Server
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### Terminal 2: Start ARQ Background Worker Node
```bash
arq app.worker.WorkerSettings
```

---

### 5. Running Automated Tests

#### Run Unit & Endpoint Test Suite
```bash
pytest -v
```

#### Run Live End-to-End Test (against PostgreSQL, Redis, PaddleOCR & llama.cpp)
```bash
python tests/test_live_api.py
```

---

## 📬 Postman Collection

A complete, pre-configured Postman v2.1 collection is provided at:
👉 **[postman_collection.json](file:///f:/doc-classification-engine/postman_collection.json)**

### Highlights:
* **Auto JWT Token Capture:** Logging in via `POST /token` runs a test script that automatically saves `access_token` into the `{{token}}` collection variable.
* **Pre-configured Endpoints:** `/token`, `/register`, `/me`, `/upload` (multipart form), `/documents/{reference_id}/status`, `/documents/{reference_id}`, `/documents/download/{document_id}`, and `/health`.

---

## 📡 API Reference & cURL Commands

### 1. Authenticate & Obtain Access Token
```bash
curl -X POST "http://localhost:8000/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin_secure_pass123"
```
**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 28800
}
```

---

### 2. Upload Document (PDF or Image)
```bash
export TOKEN="YOUR_JWT_ACCESS_TOKEN"

# Uploading a PDF (e.g., GSTR-3B Return)
curl -X POST "http://localhost:8000/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "reference_id=LOAN_APP_2026_001" \
  -F "file=@sample_dataset/Set_4_GSTR3B_July_2025.pdf"

# Uploading an Image (e.g., PAN Card)
curl -X POST "http://localhost:8000/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "reference_id=LOAN_APP_2026_001" \
  -F "file=@sample_dataset/pan1.png"
```
**Response (202 Accepted):**
```json
{
  "document_id": "doc_5669777e34034cf59d92d4cf504164e4",
  "reference_id": "LOAN_APP_2026_001",
  "status": "PENDING"
}
```

---

### 3. Check Overall Processing Status for an Application
```bash
curl -X GET "http://localhost:8000/documents/LOAN_APP_2026_001/status" \
  -H "Authorization: Bearer $TOKEN"
```
**Response (200 OK):**
```json
{
  "reference_id": "LOAN_APP_2026_001",
  "total_count": 2,
  "counts_by_status": {
    "PENDING": 0,
    "PROCESSING": 0,
    "COMPLETED": 2,
    "FAILED": 0
  },
  "documents": [
    {
      "document_id": "doc_5669777e34034cf59d92d4cf504164e4",
      "status": "COMPLETED",
      "category": "GST_RETURN",
      "error_message": null,
      "created_at": "2026-09-25T17:30:47Z",
      "updated_at": "2026-09-25T17:30:50Z"
    },
    {
      "document_id": "doc_35a90136d72248bb945f72ecf5baf045",
      "status": "COMPLETED",
      "category": "PAN_CARD",
      "error_message": null,
      "created_at": "2026-09-25T17:30:48Z",
      "updated_at": "2026-09-25T17:30:52Z"
    }
  ]
}
```

---

### 4. Fetch Completed Documents & Download URLs
```bash
curl -X GET "http://localhost:8000/documents/LOAN_APP_2026_001" \
  -H "Authorization: Bearer $TOKEN"
```
**Response (200 OK):**
```json
[
  {
    "document_id": "doc_5669777e34034cf59d92d4cf504164e4",
    "reference_id": "LOAN_APP_2026_001",
    "category": "GST_RETURN",
    "document_url": "http://127.0.0.1:8000/documents/download/doc_5669777e34034cf59d92d4cf504164e4",
    "created_at": "2026-09-25T17:30:47Z",
    "updated_at": "2026-09-25T17:30:50Z"
  },
  {
    "document_id": "doc_35a90136d72248bb945f72ecf5baf045",
    "reference_id": "LOAN_APP_2026_001",
    "category": "PAN_CARD",
    "document_url": "http://127.0.0.1:8000/documents/download/doc_35a90136d72248bb945f72ecf5baf045",
    "created_at": "2026-09-25T17:30:48Z",
    "updated_at": "2026-09-25T17:30:52Z"
  }
]
```

---

### 5. Secure Document Download
```bash
curl -X GET "http://127.0.0.1:8000/documents/download/doc_5669777e34034cf59d92d4cf504164e4" \
  -H "Authorization: Bearer $TOKEN" \
  -O -J
```

---

## 🏛️ Enterprise Production Deployment Checklist for Banks

1. **Hardware Acceleration:** Configure `PADDLE_OCR_USE_GPU=true` on GPU-enabled nodes; the service automatically fails over to CPU if VRAM is exhausted.
2. **Horizontal Worker Scaling:** Scale ARQ workers across multiple processing instances connected to the shared Redis queue (`arq app.worker.WorkerSettings --burst`).
3. **Cloud Storage Adapter:** Replace local `./uploads` storage with AWS S3 / Azure Blob Storage using pre-signed temporary download URLs.
4. **UIDAI Aadhaar Redaction Compliance:** Mask the first 8 digits of Aadhaar numbers (`XXXX-XXXX-1234`) before permanent raw text persistence.
