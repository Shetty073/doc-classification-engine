# Low-Level Architecture & Technical Specification 📐🏛️

This document describes the low-level architectural design, component interactions, sequence flows, data contracts, and security enforcement boundaries of the **Indian Financial Document Classification Engine**.

---

## 1. Low-Level Component Architecture Diagram

```mermaid
flowchart TB
    subgraph ClientLayer ["1. Client & API Gateway Boundary"]
        Client["Banking Portal / Core Banking System (CBS)"]
        Curl["cURL / Postman / SDK"]
    end

    subgraph SecurityShield ["2. Security Middleware Pipeline"]
        SecHeaders["SecurityHeadersMiddleware<br/>(HSTS, CSP, X-Frame: DENY, nosniff)"]
        TrustedHost["TrustedHostMiddleware<br/>(Allowed Hosts Enforcement)"]
        CORS["CORSMiddleware<br/>(Origin Whitelist)"]
        RateLimiter["SlowAPI / Redis Rate Limiter<br/>(Key: Client IP / Token)"]
        OAuthGuard["OAuth2 Password Flow Guard<br/>(PyJWT HS256 Token Validation)"]
    end

    subgraph APILayer ["3. FastAPI Application Engine (Async)"]
        AuthRouter["auth.py<br/>POST /token<br/>POST /register<br/>GET /me"]
        DocRouter["documents.py<br/>POST /upload<br/>GET /documents/{ref_id}<br/>GET /documents/{ref_id}/status<br/>GET /documents/download/{id}"]
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
        
        subgraph OCRSubsystem ["OCR Extraction Pipeline"]
            FormatDetector{"Is PDF or Image?"}
            PyMuPDFText["PyMuPDF Digital Text Extractor<br/>(First 5 Pages)"]
            PyMuPDFRaster["PyMuPDF Rasterizer<br/>(150 DPI Temp Render)"]
            PaddleOCR["PaddleOCR Engine<br/>(GPU: CUDA / CPU Fallback)"]
            TextNormalizer["Spatial Text Normalizer<br/>(Max 4,000 Chars Head+Tail Window)"]
        end

        subgraph ClassifierSubsystem ["LLM Inference Engine"]
            PromptBuilder["Prompt Constructor<br/>(Strict Banking Taxonomy + JSON Schema)"]
            HTTPXClient["httpx.AsyncClient (Timeout: 60s)"]
            LlamaServer["llama.cpp HTTP Server 8080<br/>Model: Llama-3.2-3B-Instruct<br/>POST /v1/chat/completions"]
            PostReconciliation["Banking Rule Reconciliation & JSON Parser"]
        end

        StateUpdater2["DB State: PROCESSING -> COMPLETED / FAILED<br/>(Persists category, raw_text, updated_at)"]
    end

    %% Flow connections
    Client --> SecHeaders
    Curl --> SecHeaders
    SecHeaders --> TrustedHost --> CORS --> RateLimiter --> OAuthGuard
    OAuthGuard --> AuthRouter
    OAuthGuard --> DocRouter

    DocRouter --> StorageEngine --> LocalStorage
    DocRouter --> PostgresDB
    DocRouter --> ARQDispatcher --> RedisQueue

    RedisQueue --> WorkerConsumer
    WorkerConsumer --> StateUpdater1 --> PostgresDB
    WorkerConsumer --> FormatDetector

    FormatDetector -->|".pdf (Digital)"| PyMuPDFText
    PyMuPDFText --> TextNormalizer
    FormatDetector -->|".pdf (Scanned)"| PyMuPDFRaster
    PyMuPDFRaster --> PaddleOCR
    PaddleOCR --> TextNormalizer
    FormatDetector -->|"Image (.png, .jpg)"| PaddleOCR

    TextNormalizer --> PromptBuilder --> HTTPXClient --> LlamaServer
    LlamaServer --> HTTPXClient --> PostReconciliation --> StateUpdater2 --> PostgresDB
```

---

## 2. End-to-End Ingestion & Processing Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Client as Banking Client
    participant API as FastAPI Web Node
    participant DB as PostgreSQL (AsyncPG)
    participant Redis as Redis Task Queue
    participant Disk as Local Storage (./uploads)
    participant Worker as ARQ Background Worker
    participant OCR as PaddleOCR / PyMuPDF
    participant LLM as local llama.cpp (8080)

    %% Authentication
    Client->>API: POST /token (username, password)
    API->>DB: SELECT * FROM users WHERE username = ?
    DB-->>API: User Record (Bcrypt Hash)
    API->>API: Verify Password via Passlib/Bcrypt
    API-->>Client: 200 OK (access_token, token_type: "bearer")

    %% Upload
    Client->>API: POST /upload (Header: Bearer Token, File, reference_id)
    API->>API: Authenticate JWT Token & Inspect Claims
    API->>API: Validate Extension (.pdf, .png, .jpg) & Check Size <= 100MB
    API->>Disk: Stream sanitized file: ./uploads/doc_{uuid}_{clean_name}
    API->>DB: INSERT INTO documents (document_id, ref_id, file_path, status='PENDING')
    DB-->>API: 201 Created Record
    API->>Redis: enqueue_job("process_document", document_id, file_path)
    Redis-->>API: Job Enqueued (job_id)
    API-->>Client: 202 Accepted {document_id, reference_id, status: "PENDING"}

    %% Worker Execution
    Redis->>Worker: Dispatch job payload (document_id, file_path)
    Worker->>DB: UPDATE documents SET status='PROCESSING' WHERE document_id = ?
    Worker->>OCR: extract_text(file_path)
    alt PDF with Digital Text
        OCR->>OCR: Extract digital text via PyMuPDF (pages 1..5)
    else Scanned PDF / Image
        OCR->>OCR: Rasterize page (150 DPI) & run PaddleOCR (GPU/CPU)
    end
    OCR-->>Worker: Plain text (anchors, tables, numbers)

    Worker->>LLM: POST /v1/chat/completions (Prompt + OCR text + JSON schema)
    LLM-->>Worker: JSON {"category": "GST_RETURN", "confidence": 0.99, ...}
    Worker->>Worker: Rule reconciliation (sanitize category against Taxonomy)
    Worker->>DB: UPDATE documents SET status='COMPLETED', category='GST_RETURN', raw_text=...
    DB-->>Worker: Success Commit

    %% Status Query
    Client->>API: GET /documents/{reference_id}/status (Bearer Token)
    API->>DB: SELECT count by status, items WHERE reference_id = ?
    DB-->>API: Status Breakdown
    API-->>Client: 200 OK {"total_count": 1, "counts_by_status": {"COMPLETED": 1}}

    %% Document Fetch & Download
    Client->>API: GET /documents/{reference_id} (Bearer Token)
    API->>DB: SELECT * FROM documents WHERE reference_id = ? AND status='COMPLETED'
    DB-->>API: Completed records
    API-->>Client: 200 OK [{document_id, category, document_url: ".../download/{id}"}]

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
        string document_id UK "Unique external identifier"
        string reference_id "Lending dossier / KYC reference ID (Indexed)"
        string file_path "Absolute path to stored binary on disk"
        string status "PENDING, PROCESSING, COMPLETED, FAILED (Indexed)"
        string category "Classified Indian banking taxonomy code (Indexed)"
        int confidence_score "Confidence score 1 to 100"
        string guess "Hypothesis if category is UNKNOWN"
        string raw_text "Full extracted OCR plain text"
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
    [*] --> PENDING : POST /upload
    PENDING --> PROCESSING : Worker picks job and starts OCR
    PROCESSING --> COMPLETED : Document classified
    PROCESSING --> FAILED : OCR error or timeout
    FAILED --> PENDING : Trigger retry
    COMPLETED --> [*]
```

---

## 5. Security & Threat Modeling Matrices

| Threat Vector | Mitigation Strategy | Enforcement Module |
| :--- | :--- | :--- |
| **DDoS / GPU Exhaustion** | 10 uploads/min per IP rate limiter backed by Redis. | [app/limiter.py](file:///f:/doc-classification-engine/app/limiter.py) |
| **Directory Traversal** | Filename regex sanitization (`[^a-zA-Z0-9_.-]`), path containment verification inside `UPLOAD_DIR`. | [app/routers/documents.py](file:///f:/doc-classification-engine/app/routers/documents.py#L22-L28) |
| **MIME Sniffing & Clickjacking** | Strict headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `HSTS`. | [app/middleware.py](file:///f:/doc-classification-engine/app/middleware.py#L21-L45) |
| **Host Header Poisoning** | Explicit whitelist of accepted Host headers via Starlette middleware. | [app/main.py](file:///f:/doc-classification-engine/app/main.py#L75-L79) |
| **CORS Infiltration** | Strict whitelist: `http://localhost:3000`, `http://localhost:8000` (No `*` wildcards allowed). | [app/main.py](file:///f:/doc-classification-engine/app/main.py#L82-L90) |
| **Unauthorized Data Access** | OAuth2 Password Flow with PyJWT cryptographically signed tokens (HS256). | [app/security.py](file:///f:/doc-classification-engine/app/security.py) |
| **Unbounded File Bomb** | Chunked streaming write that aborts and deletes files exceeding `MAX_FILE_SIZE_BYTES` (100MB). | [app/routers/documents.py](file:///f:/doc-classification-engine/app/routers/documents.py#L72-L89) |
