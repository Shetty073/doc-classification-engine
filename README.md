# Indian Financial Document Classification Engine 🇮🇳🏛️

An enterprise-grade, asynchronous AI document classification backend engineered for Indian Scheduled Commercial Banks and Non-Banking Financial Companies (NBFCs).

The platform automates the ingestion, text extraction, image quality auditing, and strict taxonomy classification for:
1. **Officially Valid Documents (OVDs)** accepted by the Reserve Bank of India (RBI) under the Master Direction on KYC (Passport, Driving Licence, Aadhaar Card, Voter Identity Card, NREGA Job Card, NPR Letter, and PAN Card / Form 60).
2. **Business, Corporate Constitution & Supply Chain Lending Documents** (Certificates of Incorporation, Udyam MSME Certificates, MOA & AOA, Board Resolutions, GST Returns, Income Tax Returns, Purchase Orders, Tax Invoices, Bank Statements, and Audited Financial Statements).

---

## 🏗️ System Architecture

```
                   ┌──────────────────────────────────────────────┐
                   │    Enterprise Banking UI / Client Systems    │
                   │ (React Dashboard, Core Banking Systems, SDK) │
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
     │  - Quality Diagnostic Engine ├───────────────────────────┘
     │  - PyMuPDF / PaddleOCR Engine│ Updates status: PENDING -> PROCESSING -> COMPLETED / FAILED
     │  - LLM Classification Client │ Dispatches Webhook callbacks
     └──────────────┬───────────────┘
                    │ HTTP POST /v1/chat/completions
                    ▼
     ┌──────────────────────────────┐
     │   Local llama.cpp Server     │
     │      (localhost:8080)        │
     │  Model: Llama-3.2-3B-Instruct│
     └──────────────────────────────┘
```

> 📖 **Deep Dive:** For the complete component interactions, sequence diagrams, and ER models, see [ARCHITECTURE.md](file:///f:/doc-classification-engine/ARCHITECTURE.md).

---

## 💻 Enterprise Web Dashboard (React + Vite)

The engine includes a modern, high-density **Enterprise Banking Dashboard** designed in the aesthetic style of Stripe, Plaid, and AWS Management Console.

* **Zero "AI Slop":** Clean slate palette (`#090d16`, `#0f172a`), crisp typography, high-contrast badges, and zero gimmicky neon gradients or emojis.
* **Real-time Pipeline Tracking:** Shows all dossier documents, displaying in-flight progress (`PENDING` queue, animated `PROCESSING` spinners) and auto-updating to `COMPLETED` via polling.
* **Document Inspector Drawer:** Slide-out right-side panel providing tabs for Classification Summary, Structured Extracted Entities (PAN, GSTIN, CIN, dates), Document Image Quality Diagnostics, and Raw Monospace OCR Text with one-click copy.
* **Dual View Modes:** Seamless toggle between an Enterprise Data Table view and a Grid Card view.
* **Ingestion Gateway:** Drag-and-drop dropzone supporting single-file and multi-file batch uploads (PDF, PNG, JPG, TIFF) with optional Webhook Callback URL configuration.

```bash
# To run the frontend locally:
cd frontend
npm install
npm run dev
# Dashboard opens at http://localhost:5173/
```

---

## 🚀 Tech Stack & Core Dependencies

* **Web Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+) with async event loop.
* **Frontend:** React 19, Vite, Lucide Icons, Vanilla Enterprise Design System, Nginx reverse proxy.
* **Database & ORM:** PostgreSQL (`localhost:5432`), [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (Async engine via `asyncpg`), and [Alembic](https://alembic.sqlalchemy.org/) for migrations.
* **Task Queue:** [Redis](https://redis.io/) (`localhost:6379`) with [`arq`](https://arq-docs.helpmanual.io/) for asynchronous worker execution.
* **OCR & Extraction Engine:** 
  * `paddlepaddle-gpu` (CUDA-accelerated on NVIDIA RTX GPUs) with automated runtime fallback to CPU.
  * `paddleocr` (v2.10) with textline orientation detection.
  * `PyMuPDF` (`pymupdf`) digital text extraction + page rasterization (150 DPI).
* **LLM Inference:** `Llama-3.2-3B-Instruct` served locally via [`llama.cpp`](https://github.com/ggerganov/llama.cpp)'s OpenAI-compatible HTTP server (`http://localhost:8080/v1/chat/completions`).
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
| `PAN_CARD` | Mandatory Tax KYC | Physical or electronic PAN Card issued by Income Tax Department (`[A-Z]{5}[0-9]{4}[A-Z]`). |
| `UTILITY_BILL` | RBI Deemed OVD | Electricity, Piped Gas, Water, Postpaid Landline bill (Discoms: BESCOM, Tata Power, MSEDCL). |
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
| `AUDITED_FINANCIALS` | Corporate Credit | Balance Sheet, Profit & Loss (P&L) Statement, Notes to Accounts, Form 3CA/3CB Audit Report. |
| `BUSINESS_REGISTRATION` | Entity Constitution | Certificate of Incorporation (MCA / CIN / Companies House), Udyam Registration, Shop Act. |
| `MOA_AOA` | Entity Constitution | Memorandum of Association and Articles of Association of a corporate entity. |
| `BOARD_RESOLUTION` | Corporate Borrowing | Certified copy of Board Resolution ("RESOLVED THAT...") authorizing credit facilities. |
| `PARTNERSHIP_DEED` | Entity Constitution | Registered Partnership Deed or LLP Agreement defining partners and profit sharing. |
| `TRUST_DEED` | Entity Constitution | Trust Deed, Society Registration Certificate, or Bye-laws for non-profits. |
| `SHAREHOLDING_PATTERN` | Entity KYC | Beneficial ownership declaration, list of shareholders holding equity. |
| `TITLE_DEED` | Collateral Security | Registered Sale Deed, Conveyance Deed, Gift Deed, Lease Deed with Sub-Registrar stamp. |
| `ENCUMBRANCE_CERTIFICATE` | Collateral Security | Form 15/16 Encumbrance Certificate (EC) issued by Sub-Registrar confirming lien freedom. |
| `PROPERTY_VALUATION_REPORT`| Collateral Security | Valuation certificate from Empanelled Valuer / Chartered Engineer estimating market value. |
| `LEGAL_AUDIT_REPORT` | Collateral Security | Title Search Report or Legal Opinion prepared by empanelled advocate. |
| `BILL_OF_LADING` | Trade Finance | Ocean Bill of Lading, Air Waybill (AWB), Lorry Receipt (LR) for goods transport. |
| `LETTER_OF_CREDIT` | Trade Finance | Irrevocable Letter of Credit (LC), Bank Guarantee (BG), SWIFT MT700. |
| `STOCK_STATEMENT` | Working Capital | Monthly DP (Drawing Power) Stock & Book Debt statement submitted to banks. |
| `FORM_60` | Statutory Declaration | Form 60 declaration under Rule 114B of IT Rules (filed when customer has no PAN). |
| `UNKNOWN` | Fallback Category | Non-financial or unrecognized document. Includes deterministic hypothesis `guess`. |

---

## 🐳 Docker Deployment Options

The project provides dual Docker Compose configurations:

### Option A: Standard Deployment (Backend, Worker, DB, Redis)
Runs PostgreSQL, Redis, FastAPI Backend, and ARQ Workers. Connects to your local/external `llama.cpp` instance running on the host machine.
```bash
# 1. Copy environment variables
cp .env.docker.example .env

# 2. Launch stack (with 2 scalable worker instances by default)
docker compose up -d --build

# Scale worker instances dynamically
docker compose up -d --scale worker=4
```

### Option B: Full-Stack Deployment (All 6 Services Containerized)
Runs the entire ecosystem in isolated containers, including `llama.cpp` and the React Vite production build served via Nginx.
```bash
docker compose -f docker-compose.full.yml up -d --build
```

---

## 📡 Canonical API Endpoints

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/token` | OAuth2 Password Login (returns JWT) | No |
| `POST` | `/register` | Register New Operator User | Admin |
| `GET` | `/me` | Get Current Authenticated User Profile | Yes |
| `POST` | `/upload` | Upload Single Document (PDF/Image) | Yes |
| `POST` | `/upload-batch` | Upload Batch Documents (up to 20 files) | Yes |
| `GET` | `/documents/{reference_id}` | List All Documents (in-flight & completed) | Yes |
| `GET` | `/documents/{reference_id}/status`| Application Processing Status Summary | Yes |
| `GET` | `/documents/download/{document_id}`| Secure Document File Download | Yes |
| `GET` | `/health` | Service Liveness & Health Check | No |

---

## 📬 Postman Collection

A complete, pre-configured Postman v2.1 collection is available:
👉 **[postman_collection.json](file:///f:/doc-classification-engine/postman_collection.json)**

* **Auto JWT Token Capture:** Tests automatically persist JWT tokens into `{{token}}` collection variable.
* **Pre-configured Endpoints:** Complete parameter lists, file upload payloads, and response validation scripts.

---

## 🧪 Testing & Verification

```bash
# Run pytest test suite
.\venv\Scripts\python.exe -m pytest tests/
```
