# Low-Level Architecture & Technical Specification 📐🏛️

This document describes the low-level architectural design, component interactions, sequence flows, data contracts, and security enforcement boundaries of the **Indian Financial Document Classification Engine**.

---

## 1. Low-Level Component Architecture Diagram

```mermaid
flowchart TB
    subgraph ClientLayer ["1. Client & Presentation Boundary"]
        FrontendSPA["Enterprise React Dashboard (Vite / Nginx)<br/>KPI Cards, Data Table, Inspector Drawer, Upload Zone"]
        BankingClient["Core Banking System (CBS) / Loan Origination (LOS)"]
        APIClients["cURL / Postman / Python SDK"]
    end

    subgraph SecurityShield ["2. Security Middleware Pipeline"]
        SecHeaders["SecurityHeadersMiddleware<br/>(HSTS, CSP, X-Frame: DENY, nosniff)"]
        TrustedHost["TrustedHostMiddleware<br/>(Allowed Hosts Enforcement)"]
        CORS["CORSMiddleware<br/>(Strict Origin Whitelist)"]
        RateLimiter["SlowAPI / Redis Rate Limiter<br/>(Key: Client IP / Token)"]
        OAuthGuard["OAuth2 Password Flow Guard<br/>(PyJWT HS256 Token Validation)"]
    end

    subgraph APILayer ["3. FastAPI Application Engine (Async)"]
        AuthRouter["auth.py<br/>POST /token<br/>POST /register<br/>GET /me"]
        DocRouter["documents.py<br/>POST /upload<br/>POST /upload-batch<br/>GET /documents/{ref_id}<br/>GET /documents/{ref_id}/status<br/>GET /documents/download/{id}"]
        HealthRouter["main.py<br/>GET /health"]
        StorageEngine["Disk Storage Streamer<br/>(Sanitizer, Size Cap 100MB, Path Traversal Guard)"]
        ARQDispatcher["ARQ Pool Producer<br/>(arq.create_pool -> Redis)"]
    end

    subgraph DataStorage ["4. Persistence & Queue Infrastructure"]
        RedisQueue[("Redis Server 6379<br/>Job Queue: 'arq:queue'")]
        PostgresDB[("PostgreSQL 5432<br/>Database: doc_classifier<br/>Tables: users, documents")]
        LocalStorage[("Storage Root: ./uploads<br/>doc_{uuid}_{clean_filename}")]
    end

    subgraph BackgroundWorker ["5. ARQ Distributed Worker Process"]
        WorkerConsumer["arq.worker.WorkerSettings<br/>process_document(document_id, file_path)"]
        StateUpdater1["DB State: PENDING -> PROCESSING"]
        
        subgraph QualityInspection ["Document Image Quality Diagnostics"]
            QualityAuditor["Quality Analyzer (app/utils/quality.py)<br/>- Laplacian Blur Variance<br/>- Michelson Contrast<br/>- Radon/Hough Skew Angle<br/>- DPI & Resolution Check<br/>-> Generates quality_score (1-100) & quality_issues"]
        end

        subgraph OCRSubsystem ["OCR Extraction Subsystem"]
            FormatDetector{"Is PDF or Image?"}
            PyMuPDFText["PyMuPDF Digital Text Extractor<br/>(Pages 1..5)"]
            PyMuPDFRaster["PyMuPDF Rasterizer<br/>(150 DPI Render)"]
            PaddleOCR["PaddleOCR Engine (app/ocr.py)<br/>(GPU: CUDA / CPU Fallback)"]
            UIDAIMasker["Aadhaar Privacy Masker (app/utils/masking.py)<br/>(Redacts 8 digits of UIDAI numbers)"]
        end

        subgraph ClassifierSubsystem ["LLM Inference Engine"]
            PromptBuilder["Prompt Constructor<br/>(42-Class RBI Banking Taxonomy + JSON Schema)"]
            HTTPXClient["httpx.AsyncClient (Timeout: 60s)"]
            LlamaServer["llama.cpp HTTP Server 8080<br/>Model: Llama-3.2-3B-Instruct<br/>POST /v1/chat/completions"]
            PostReconciliation["Rule Reconciliation & Fallback Engine<br/>- MCA Incorporation vs PAN<br/>- Udyam vs Board Resolution<br/>- MOA/AOA vs Business Registration"]
            EntityExtractor["Entity Extractor (app/utils/entity_extractor.py)<br/>- PAN, GSTIN, CIN, Dates, Names"]
        end

        StateUpdater2["DB State: PROCESSING -> COMPLETED / FAILED<br/>(Persists category, confidence, quality, entities, raw_text)"]
        WebhookDispatcher["Async Webhook Notifier<br/>(POST callback_url with completed payload)"]
    end

    %% Flow connections
    FrontendSPA --> SecHeaders
    BankingClient --> SecHeaders
    APIClients --> SecHeaders
    SecHeaders --> TrustedHost --> CORS --> RateLimiter --> OAuthGuard
    OAuthGuard --> AuthRouter
    OAuthGuard --> DocRouter
    OAuthGuard --> HealthRouter

    DocRouter --> StorageEngine --> LocalStorage
    DocRouter --> PostgresDB
    DocRouter --> ARQDispatcher --> RedisQueue

    RedisQueue --> WorkerConsumer
    WorkerConsumer --> StateUpdater1 --> PostgresDB
    WorkerConsumer --> QualityAuditor
    WorkerConsumer --> FormatDetector

    FormatDetector -->|".pdf (Digital)"| PyMuPDFText
    FormatDetector -->|".pdf (Scanned)"| PyMuPDFRaster --> PaddleOCR
    FormatDetector -->|"Image (.png, .jpg)"| PaddleOCR

    PyMuPDFText --> UIDAIMasker
    PaddleOCR --> UIDAIMasker
    UIDAIMasker --> PromptBuilder

    PromptBuilder --> HTTPXClient --> LlamaServer
    LlamaServer --> HTTPXClient --> PostReconciliation
    PostReconciliation --> EntityExtractor
    EntityExtractor --> StateUpdater2 --> PostgresDB
    StateUpdater2 --> WebhookDispatcher
```

---

## 2. End-to-End Ingestion & Processing Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Client as Banking Client / UI
    participant API as FastAPI Web Node
    participant DB as PostgreSQL (AsyncPG)
    participant Redis as Redis Task Queue
    participant Disk as Local Storage (./uploads)
    participant Worker as ARQ Background Worker
    participant Quality as Quality Auditor
    participant OCR as PaddleOCR / PyMuPDF
    participant LLM as local llama.cpp (8080)
    participant Webhook as Customer Webhook Server

    %% Authentication
    Client->>API: POST /token (username, password)
    API->>DB: SELECT * FROM users WHERE username = ?
    DB-->>API: User Record (Bcrypt Hash)
    API->>API: Verify Password via Passlib/Bcrypt
    API-->>Client: 200 OK (access_token, token_type: "bearer")

    %% Upload
    Client->>API: POST /upload (Header: Bearer Token, File, reference_id, optional callback_url)
    API->>API: Authenticate JWT Token & Inspect Claims
    API->>API: Validate Extension (.pdf, .png, .jpg, .tiff) & Check Size <= 100MB
    API->>Disk: Stream sanitized file: ./uploads/doc_{uuid}_{clean_name}
    API->>DB: INSERT INTO documents (document_id, ref_id, file_path, status='PENDING')
    DB-->>API: 201 Created Record
    API->>Redis: enqueue_job("process_document", document_id, file_path)
    Redis-->>API: Job Enqueued (job_id)
    API-->>Client: 202 Accepted {document_id, reference_id, status: "PENDING"}

    %% Worker Execution
    Redis->>Worker: Dispatch job payload (document_id, file_path)
    Worker->>DB: UPDATE documents SET status='PROCESSING' WHERE document_id = ?
    
    %% Quality Audit
    Worker->>Quality: assess_quality(file_path)
    Quality-->>Worker: {quality_score: 96, quality_issues: []}

    %% OCR Extraction
    Worker->>OCR: extract_text(file_path)
    alt PDF with Digital Text
        OCR->>OCR: Extract digital text via PyMuPDF (pages 1..5)
    else Scanned PDF / Image
        OCR->>OCR: Rasterize page (150 DPI) & run PaddleOCR (GPU/CPU)
    end
    OCR-->>Worker: Plain text (anchors, tables, numbers)
    Worker->>Worker: Mask Aadhaar digits (UIDAI privacy rule)

    %% LLM Classification
    Worker->>LLM: POST /v1/chat/completions (Prompt + OCR text + JSON schema)
    LLM-->>Worker: JSON {"category": "BUSINESS_REGISTRATION", "confidence_score": 100, ...}
    Worker->>Worker: Rule reconciliation (prioritizes Incorporation above secondary PAN mentions)
    Worker->>Worker: Deterministic entity extraction (PAN, GSTIN, CIN, Dates)

    Worker->>DB: UPDATE documents SET status='COMPLETED', category='BUSINESS_REGISTRATION', confidence_score=100, raw_text=..., quality_score=96
    DB-->>Worker: Success Commit

    %% Optional Webhook Dispatch
    opt If callback_url is configured
        Worker->>Webhook: POST callback_url {event: "document.completed", document_id, category, ...}
        Webhook-->>Worker: 200 OK
    end

    %% Real-time Querying
    Client->>API: GET /documents/{reference_id} (Bearer Token)
    API->>DB: SELECT * FROM documents WHERE reference_id = ? ORDER BY created_at DESC
    DB-->>API: All Dossier Records (PENDING, PROCESSING, COMPLETED, FAILED)
    API-->>Client: 200 OK [List of Document Items with Live Status, File Name & Download Links]

    Client->>API: GET /documents/download/{document_id} (Bearer Token)
    API->>Disk: Stream file
    Disk-->>Client: 200 OK (File Binary Stream)
```

---

## 3. Database Entity-Relationship (ER) Model

```mermaid
erDiagram
    users {
        int id PK "Auto-increment primary key"
        string username UK "Unique banking operator handle"
        string hashed_password "Bcrypt hash with salt"
        boolean is_active "Account status flag"
        timestamptz created_at "Account creation timestamp"
    }

    documents {
        uuid id PK "UUID primary key"
        string document_id UK "Unique external identifier (e.g. doc_194a2a4d...)"
        string reference_id "Lending dossier / KYC reference ID (Indexed)"
        string file_path "Absolute path to stored binary on disk"
        string status "PENDING, PROCESSING, COMPLETED, FAILED (Indexed)"
        string category "Classified Indian banking taxonomy code (Indexed)"
        int confidence_score "Confidence score 1 to 100"
        string guess "Hypothesis if category is UNKNOWN"
        string callback_url "Optional webhook callback URL"
        json extracted_metadata "Structured financial entities (PAN, GSTIN, etc.)"
        int quality_score "Image quality score 1 to 100"
        json quality_issues "Detected quality issues (blur, resolution)"
        string raw_text "UIDAI-masked extracted OCR plain text"
        string error_message "Diagnostic pipeline error message on failure"
        timestamptz created_at "Upload timestamp"
        timestamptz updated_at "Status change / completion timestamp"
    }

    users ||--o{ documents : "manages"
```

---

## 4. Document State Machine Transitions

```mermaid
stateDiagram-v2
    [*] --> PENDING : POST /upload or POST /upload-batch
    PENDING --> PROCESSING : Worker dequeues job from Redis
    PROCESSING --> COMPLETED : Document classified & entities extracted
    PROCESSING --> FAILED : OCR unreadable or pipeline exception
    FAILED --> PENDING : Re-enqueued for retry
    COMPLETED --> [*]
```

---

## 5. Security & Threat Modeling Matrix

| Threat Vector | Mitigation Strategy | Enforcement Module |
| :--- | :--- | :--- |
| **DDoS / GPU Exhaustion** | SlowAPI rate limiter (10 uploads/min per IP, 60 req/min for queries) backed by Redis. | [app/limiter.py](file:///f:/doc-classification-engine/app/limiter.py) |
| **Directory Traversal** | Filename sanitization (`[^a-zA-Z0-9_.-]`), path containment verification inside `UPLOAD_DIR`. | [app/routers/documents.py](file:///f:/doc-classification-engine/app/routers/documents.py) |
| **MIME Sniffing & Clickjacking** | Strict security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `HSTS`. | [app/middleware.py](file:///f:/doc-classification-engine/app/middleware.py) |
| **Host Header Poisoning** | Explicit whitelist of accepted Host headers via Starlette middleware. | [app/main.py](file:///f:/doc-classification-engine/app/main.py) |
| **CORS Infiltration** | Strict whitelist: `http://localhost:5173`, `http://localhost:3000`, `http://localhost:8000` (no wildcard `*`). | [app/main.py](file:///f:/doc-classification-engine/app/main.py) |
| **Unauthorized Data Access** | OAuth2 Password Flow with PyJWT cryptographically signed tokens (HS256). | [app/security.py](file:///f:/doc-classification-engine/app/security.py) |
| **Unbounded File Bomb** | Chunked streaming write that aborts and deletes files exceeding `MAX_FILE_SIZE_BYTES` (100MB). | [app/routers/documents.py](file:///f:/doc-classification-engine/app/routers/documents.py) |
| **PII / UIDAI Compliance** | Automated masking of Aadhaar digits (first 8 digits masked) before raw OCR text is persisted. | [app/utils/masking.py](file:///f:/doc-classification-engine/app/utils/masking.py) |
