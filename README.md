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

## 📋 Comprehensive Taxonomy of Indian Banking & NBFC Documents

Built in strict compliance with the **RBI Master Direction on KYC (Updated 2024)**, **PMLA Guidelines**, and Indian commercial banking operations:

| Category Code | Classification Group | Identifying Anchors & Key Characteristics |
| :--- | :--- | :--- |
| `PASSPORT` | RBI KYC (OVD) | "Republic of India", "Passport No", Machine Readable Zone (MRZ), Nationality: Indian. |
| `DRIVING_LICENCE` | RBI KYC (OVD) | State RTO / Licensing Authority, "Union of India Driving Licence", Form 7, DL number. |
| `AADHAAR_CARD` | RBI KYC (OVD) | UIDAI, "Mera Aadhaar, Meri Pehchan", 12-digit UID/VID, e-Aadhaar, Masked Aadhaar. |
| `VOTER_ID` | RBI KYC (OVD) | Election Commission of India, EPIC Number, Elector's Name, Father's/Husband's name. |
| `NREGA_JOB_CARD` | RBI KYC (OVD) | Mahatma Gandhi NREGA, Job Card Number, State Rural Development, Officer signature. |
| `NPR_LETTER` | RBI KYC (OVD) | Letter issued by the National Population Register containing name and address details. |
| `PAN_CARD` | Mandatory Tax KYC | Income Tax Department, Govt of India, 10-digit alphanumeric PAN (`[A-Z]{5}[0-9]{4}[A-Z]`). |
| `UTILITY_BILL` | RBI Deemed OVD | Electricity, Piped Gas, Water, Postpaid Landline bill (Discoms: BESCOM, Tata Power, etc.). |
| `PROPERTY_TAX_RECEIPT` | RBI Deemed OVD | Municipal Corporation property tax receipt or assessment order in applicant's name. |
| `PENSION_PAYMENT_ORDER`| RBI Deemed OVD | Pension or Family Pension Payment Order (PPO) issued to retired employees by Govt/PSUs. |
| `EMPLOYER_ACCOMMODATION_LETTER` | RBI Deemed OVD | Official allotment letter issued by State/Central Govt, statutory body, PSU, or SCB. |
| `SALARY_SLIP` | Retail Underwriting | Monthly Payslip, Salary Slip, Basic Pay, HRA, Deductions, Net Salary, Employee ID. |
| `FORM_16` | Income Appraisal | TDS Certificate under Section 203 of IT Act (Part A TRACES or Part B computation). |
| `EPFO_PASSBOOK` | Income Verification | Employees' Provident Fund Organisation statement / UAN passbook contribution history. |
| `BANK_STATEMENT` | Loan Underwriting | Bank Account Statement, Account Number, IFSC, Opening & Closing Balances, Transactions. |
| `CANCELLED_CHEQUE` | Disbursal / Mandate | Cheque leaf with "CANCELLED" written across, Account Name, Number, IFSC / MICR code. |
| `NACH_MANDATE` | Loan Servicing | National Automated Clearing House / e-Mandate form signed for recurring EMI debit. |
| `FD_RECEIPT` | Lien Lending | Fixed Deposit Receipt, Term Deposit Advice, Tenure, Maturity Value, Interest Rate. |
| `SANCTION_LETTER` | Bank Servicing | Credit Facility Sanction Letter, In-principle Approval, Limit, Rate, EMI, Covenants. |
| `LOAN_ACCOUNT_STATEMENT` | Servicing / Takeover | Statement of Loan Account, Amortization Schedule, Repayment Ledger from bank/NBFC. |
| `NO_DUE_CERTIFICATE` | Pre-closure / NOC | No Objection Certificate (NOC) / No Dues Certificate issued on full loan settlement. |
| `DEMAND_PROMISSORY_NOTE` | Legal Security | DPN executed by borrower promising unconditional repayment of loan on demand. |
| `GST_RETURN` | Lending & Trade | Form GSTR-1, GSTR-3B, GSTR-9, or GST Registration Certificate (GST REG-06). |
| `INCOME_TAX_RETURN` | Credit Appraisal | ITR-V, ITR Acknowledgement Number, Assessment Year, Total Income, Computation sheet. |
| `PURCHASE_ORDER` | Supply Chain Finance | "Purchase Order", "Work Order", PO Number, Line Items, Quantity, Rate, Delivery Terms. |
| `TAX_INVOICE` | Supply Chain Finance | Commercial / Tax Invoice, Bill of Supply, Supplier & Buyer GSTIN, HSN/SAC, IRN/QR code. |
| `AUDITED_FINANCIALS` | Corporate Credit | Balance Sheet, Profit & Loss (P&L) Statement, Notes to Accounts, Auditor's Report. |
| `BILL_OF_LADING` | Trade Finance | Ocean Bill of Lading, Air Waybill (AWB), Lorry Receipt (LR) for consignment transport. |
| `LETTER_OF_CREDIT` | Trade Credit | Irrevocable Letter of Credit (LC), Bank Guarantee (BG), SWIFT MT700/MT760. |
| `STOCK_STATEMENT` | Working Capital | Monthly DP (Drawing Power) Stock & Book Debt statement submitted to banks. |
| `BUSINESS_REGISTRATION` | Legal Constitution | Udyam / MSME Registration Certificate, Certificate of Incorporation (CIN / MCA). |
| `MOA_AOA` | Corporate Legal | Memorandum of Association and Articles of Association registered with ROC. |
| `BOARD_RESOLUTION` | Corporate Authority | Certified true copy of Board Resolution authorizing credit facilities and signers. |
| `PARTNERSHIP_DEED` | Firm Constitution | Registered or Notarized Partnership Deed or LLP Agreement. |
| `TRUST_DEED` | Institutional KYC | Trust Deed, Society Registration Certificate, or Bye-laws for non-profits. |
| `SHAREHOLDING_PATTERN` | UBO Compliance | Beneficial ownership declaration, list of shareholders holding $\ge 10\%$ equity. |
| `TITLE_DEED` | Mortgage / Collateral| Registered Sale Deed, Conveyance Deed, Gift Deed, Lease Deed with Sub-Registrar stamp. |
| `ENCUMBRANCE_CERTIFICATE` | Title Vetting | Form 15/16 Encumbrance Certificate (EC) issued by Sub-Registrar of Assurances. |
| `PROPERTY_VALUATION_REPORT` | Collateral Sizing | Valuation certificate from Empanelled Valuer / Chartered Engineer. |
| `LEGAL_AUDIT_REPORT` | Legal Vetting | Title Search Report or Legal Opinion prepared by empanelled advocate. |
| `FORM_60` | Statutory Tax | Form 60 declaration under Rule 114B of IT Rules (filed when customer has no PAN). |
| `UNKNOWN` | Fallback | Unclassified non-banking documents (returns confidence 1-100 and best guess). |

---

## 🔒 Enterprise Features & Regulatory Safeguards

1. **Aadhaar Masking (UIDAI & RBI Section 16 Compliance):**
   * Automatically scans extracted OCR text and masks the first 8 digits of any 12-digit Aadhaar number (`XXXX-XXXX-1234`) or 16-digit Virtual ID before persistent storage.
2. **Document Quality & Tampering Assessment:**
   * Vision analysis computing Laplacian variance (blur score), resolution dimensions, and contrast distribution to detect washed-out, blurry, or low-resolution scans.
3. **Structured Financial Entity Extraction:**
   * Automatically extracts key fields (PAN number, DOB, GSTINs, IFSC codes, Account Numbers, Invoice Totals, Net Salaries) into `extracted_metadata` JSON.
4. **Batch Document Upload (`POST /upload-batch`):**
   * Enables sending up to 20 documents in a single atomic HTTP request under a shared `reference_id`, returning distinct tracking IDs.
5. **Signed Webhook Callbacks:**
   * Optional `callback_url` parameter receives an authenticated HTTP POST event containing document status, category, score, and entities, signed with HMAC-SHA256 (`X-Signature-SHA256`).
6. **Dual PDF & Image Support:**
   * Whitelisted extensions: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.tiff`, `.tif`, `.bmp` up to **100MB**.
7. **Rate Limiting & Security Headers:**
   * SlowAPI Redis rate limiting (`10 uploads/min`), HSTS, CSP, X-Frame-Options: DENY, X-Content-Type-Options: nosniff.
8. **Host & Origin Isolation:**
   * `CORSMiddleware` restricts traffic to banking origins (`localhost:3000`, `localhost:8000`).
   * `TrustedHostMiddleware` restricts accepted Host headers (`localhost`, `127.0.0.1`, `testserver`).
9. **Authentication & RBAC Readiness:**
   * OAuth2 Password Bearer flow with cryptographically signed JWT tokens (HS256) and active account checks.

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

#### Terminal 3: Start React (Vite) Demo Frontend
```bash
cd frontend
npm install
npm run dev
```
*Accessible in browser:* **`http://localhost:5173`**
* Features: 1-click demo login, drag & drop document upload, batch uploads, real-time polling, confidence badges, AI guess pills, and authenticated document download.

---

### 5. Running via Docker Compose

Two Docker Compose configurations are provided:

#### Option A: Default Stack (`docker-compose.yml`) — Backend Services Only
Runs the **FastAPI backend**, **ARQ worker**, **PostgreSQL**, and **Redis** in containers while keeping `llama.cpp` and the `frontend` running standalone on the host:

```bash
# 1. Start backend stack with default replicas (1 backend, 2 workers)
docker compose up --build -d

# 2. Scale worker instances on demand (e.g. 4 parallel OCR/classification workers)
docker compose up --scale worker=4 -d

# 3. View real-time logs
docker compose logs -f backend worker

# 4. Stop stack
docker compose down
```
* **Host LLM Bridge:** Communicates with your host-running `llama.cpp` server via `http://host.docker.internal:8080/v1/chat/completions`.

---

#### Option B: Full Stack (`docker-compose.full.yml`) — All 6 Services Containerized
Runs **PostgreSQL**, **Redis**, **llama.cpp server**, **FastAPI backend**, **ARQ worker**, and **React frontend (Nginx)** fully containerized:

```bash
# 1. Place your GGUF model into the ./models directory:
#    ./models/Llama-3.2-3B-Instruct-Q4_K_M.gguf

# 2. Build and launch all 6 services:
docker compose -f docker-compose.full.yml up --build -d

# 3. Scale workers to 4 instances:
docker compose -f docker-compose.full.yml up --scale worker=4 -d

# 4. Access points:
#    - Frontend Dashboard: http://localhost:5173
#    - Backend REST API:   http://localhost:8000/docs
#    - llama.cpp Server:   http://localhost:8080/health

# 5. Stop full stack:
docker compose -f docker-compose.full.yml down
```

#### Configuring Model Attributes & Service Replicas
You can configure model attributes and service instance counts by creating a `.env` file (or copying [`.env.docker.example`](file:///f:/doc-classification-engine/.env.docker.example)):

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `WORKER_REPLICAS` | `2` | Number of parallel background ARQ OCR/classification workers. |
| `BACKEND_REPLICAS` | `1` | Number of FastAPI REST API server instances. |
| `FRONTEND_REPLICAS`| `1` | Number of Nginx React frontend instances. |
| `LLAMA_MODEL_PATH` | `/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf` | Path to GGUF weights inside `/models`. |
| `LLAMA_CTX_SIZE` | `4096` | Context window size for document analysis. |
| `LLAMA_N_GPU_LAYERS` | `0` | Number of model layers offloaded to GPU (`-ngl`). |
| `LLAMA_THREADS` | `4` | Number of CPU threads for inference. |
| `LLAMA_BATCH_SIZE` | `512` | Evaluation batch size for prompt processing. |
| `LLAMA_TEMPERATURE` | `0.05` | Determinism temperature for JSON classification. |

---

### 6. Running Automated Tests

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

# 1. Single Document Upload (with optional callback_url)
curl -X POST "http://localhost:8000/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "reference_id=LOAN_APP_2026_001" \
  -F "file=@sample_dataset/pan1.png" \
  -F "callback_url=https://bank.internal/webhooks/kyc"

# 2. Batch Upload (Atomic multi-document ingestion up to 20 files)
curl -X POST "http://localhost:8000/upload-batch" \
  -H "Authorization: Bearer $TOKEN" \
  -F "reference_id=LOAN_APP_2026_001" \
  -F "files=@sample_dataset/Set_4_GSTR3B_July_2025.pdf" \
  -F "files=@sample_dataset/pan1.png"
```
**Response (202 Accepted):**
```json
{
  "reference_id": "LOAN_APP_2026_001",
  "total_enqueued": 2,
  "documents": [
    {
      "document_id": "doc_180fb4c2312348079a87f4f64a6d1919",
      "filename": "Set_4_GSTR3B_July_2025.pdf",
      "status": "PENDING"
    },
    {
      "document_id": "doc_def48de110ae4153b9a30d2c4ecd3e14",
      "filename": "pan1.png",
      "status": "PENDING"
    }
  ]
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
      "document_id": "doc_180fb4c2312348079a87f4f64a6d1919",
      "status": "COMPLETED",
      "category": "GST_RETURN",
      "confidence_score": 100,
      "guess": null,
      "extracted_metadata": {
        "gstin": "27AAACR5055K1Z7"
      },
      "quality_score": 85,
      "quality_issues": ["POOR_CONTRAST_OR_GLARE"],
      "error_message": null,
      "created_at": "2026-09-25T18:02:00Z",
      "updated_at": "2026-09-25T18:02:07Z"
    },
    {
      "document_id": "doc_def48de110ae4153b9a30d2c4ecd3e14",
      "status": "COMPLETED",
      "category": "PAN_CARD",
      "confidence_score": 100,
      "guess": null,
      "extracted_metadata": {
        "pan_number": "ELWPM8089J",
        "date_of_birth": "30/01/1997"
      },
      "quality_score": 90,
      "quality_issues": ["MODERATE_RESOLUTION"],
      "error_message": null,
      "created_at": "2026-09-25T18:02:00Z",
      "updated_at": "2026-09-25T18:02:08Z"
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
    "document_id": "doc_58eb4990f4284049b2024da2cb0aecb3",
    "reference_id": "LOAN_APP_2026_001",
    "category": "GST_RETURN",
    "confidence_score": 100,
    "guess": null,
    "document_url": "http://127.0.0.1:8000/documents/download/doc_58eb4990f4284049b2024da2cb0aecb3",
    "created_at": "2026-09-25T17:48:30Z",
    "updated_at": "2026-09-25T17:48:33Z"
  },
  {
    "document_id": "doc_39911831a6e9403dac781f5cb4c6094a",
    "reference_id": "LOAN_APP_2026_001",
    "category": "UNKNOWN",
    "confidence_score": 95,
    "guess": "Electricity / Utility Bill",
    "document_url": "http://127.0.0.1:8000/documents/download/doc_39911831a6e9403dac781f5cb4c6094a",
    "created_at": "2026-09-25T17:48:32Z",
    "updated_at": "2026-09-25T17:48:38Z"
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
