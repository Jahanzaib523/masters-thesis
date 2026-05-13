# Software architecture: Semantic Authentication System (SAS)

SAS is a **web-centric** semantic authentication prototype: a browser client talks to a **Python** service that combines **classical credentials**, **meaning-based verification**, and a **visual recognition** step. **Groq** is the default provider for conversational LLM tasks, speech-to-text, text-to-speech, and related semantic scoring; **OpenAI** can serve the same semantic summarisation and similarity role when selected and configured. **Hugging Face** backs image generation and model hub access; **sentence-transformers** runs locally for dense embeddings and as a **fallback** when the primary semantic score is unavailable.

---

## 1. Logical system context

```mermaid
flowchart TB
  subgraph Users
    U[People using browsers on desktop or mobile]
  end

  subgraph SAS["SAS product boundary"]
    SPA[Single-page application]
    Svc[Authentication and profile service]
    DB[(Relational store: SQLite)]
  end

  subgraph AI["External and local AI"]
    Groq[Groq — default LLM, STT, TTS]
    OAI[OpenAI — optional semantic LLM]
    HFIMG[Hugging Face — image generation]
    LOC[Local sentence-transformers — embeddings]
  end

  U <--> SPA
  SPA <--> Svc
  Svc <--> DB
  Svc <--> Groq
  Svc <--> OAI
  Svc <--> HFIMG
  Svc <--> LOC
```

---

## 2. Layered application structure

```mermaid
flowchart TB
  subgraph Presentation["Presentation"]
    UI[React UI: registration, multi-step login, profile, help]
  end

  subgraph Application["Application / HTTP"]
    HTTP[FastAPI application and routers]
    SEC[JWT issuance and bearer verification]
    CORS[Cross-origin policy for trusted web origins]
  end

  subgraph Domain["Domain services"]
    AUTH[Registration and login orchestration]
    SEM[Semantic comparison: LLM score with embedding fallback]
    IMG[Greeting image and decoy gallery lifecycle]
    VOICE[Voice ingest: transcription pipeline]
    LOCK[Progressive lockout and audit events]
  end

  subgraph Infrastructure["Infrastructure"]
    ORM[SQLAlchemy models and sessions]
    CRYPT[Fernet encryption for embeddings and summaries]
    CFG[Settings and environment-backed configuration]
  end

  UI --> HTTP
  HTTP --> SEC
  HTTP --> CORS
  HTTP --> AUTH
  AUTH --> SEM
  AUTH --> IMG
  AUTH --> VOICE
  AUTH --> LOCK
  SEM --> ORM
  IMG --> ORM
  LOCK --> ORM
  AUTH --> CRYPT
  ORM --> CFG
```

---

## 3. Sign-in assurance pipeline (conceptual dataflow)

```mermaid
flowchart LR
  A[Identifier + password] --> B{Password valid?}
  B -->|No| X[Reject]
  B -->|Yes| C[Six-tile image choice]
  C --> D{Correct image?}
  D -->|No| L[Failure / lockout policy]
  D -->|Yes| E{Login mode}
  E -->|image only| T[Issue session]
  E -->|both| F[Semantic response]
  F --> G{Meaning match policy}
  G -->|Yes| T
  G -->|No| L
```

---

## 4. Semantic verification stack

```mermaid
flowchart TB
  subgraph Inputs
    R[User paraphrase at login]
    S[Stored encrypted semantic summary]
    E[Stored encrypted embedding of secret]
  end

  subgraph Primary["Primary path"]
    LLM[LLM similarity under selected provider]
  end

  subgraph Fallback["Fallback path"]
    RV[Embed response locally]
    COS[Cosine similarity vs stored vector]
  end

  R --> LLM
  S --> LLM
  LLM -->|Score available| Out[Decision vs threshold]
  LLM -->|Unavailable| RV
  E --> COS
  RV --> COS
  COS --> Out
```

The **selected provider** is **Groq** unless the client requests **OpenAI** for semantic routes and the deployment exposes OpenAI credentials.

---

## 5. Component responsibilities

| Part | Responsibility |
|------|------------------|
| **Web client** | Guided flows, optional OpenAI/Groq preference for semantic calls, secure token storage in the browser, accessibility affordances (voice, TTS). |
| **HTTP surface** | REST JSON and multipart for voice; optional legacy HTML flows under a separate path prefix. |
| **Authentication core** | Password hashing, challenge lifecycle, JWT contents, profile updates. |
| **Semantic core** | Summary generation at enrolment; similarity at verification; similarity bands for logging. |
| **Visual security** | User-level gallery pool; per-challenge copies; regeneration after successful login where applicable. |
| **Persistence** | Users, embeddings, challenges, binary image slots, anonymised login events. |
| **Cryptography** | Encryption of material that must not appear as plaintext at rest. |

---

## 6. Trust boundaries

- **Browser:** holds short-lived session token; never receives server-side API keys for Groq, OpenAI, or Hugging Face.
- **SAS service:** holds credentials to AI providers and encryption keys; must run in a controlled host environment.
- **Data store:** holds encrypted semantic artefacts and binary images; not raw user secrets in clear text for the summary field.
