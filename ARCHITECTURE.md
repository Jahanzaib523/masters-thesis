# System Architecture — SAS (Mermaid)

## Logical deployment (production-style)

```mermaid
flowchart TB
  subgraph Internet
    Client[Browser / Mobile web]
  end

  subgraph Droplet["Server (e.g. DigitalOcean)"]
    Nginx[Nginx :80 / :443]
    subgraph AppProcess["Gunicorn + Uvicorn :127.0.0.1:8000"]
      FastAPI[FastAPI app.main]
      Routers[routers: auth, voice_auth]
      Web[Jinja /web optional]
    end
    SQLite[(SQLite sas.db)]
  end

  subgraph External["External services"]
    Groq[Groq LLM / STT / TTS]
    OAI[OpenAI optional]
    HFIMG[HF image inference]
    HFEMB[HF sentence-transformers local]
  end

  Client --> Nginx
  Nginx --> FastAPI
  FastAPI --> Routers
  FastAPI --> Web
  Routers --> SQLite
  Routers --> Groq
  Routers --> OAI
  Routers --> HFIMG
  Routers --> HFEMB
```

---

## Component responsibilities

| Layer | Responsibility |
|-------|----------------|
| **React SPA** | Routes, multi-step login UI, profile, `localStorage` JWT, optional `VITE_API_BASE`. |
| **Nginx** | TLS termination, reverse proxy, body size limits, static ACME path. |
| **FastAPI** | HTTP API, CORS, mounts `/static`, optional SPA `frontend/dist`. |
| **SQLAlchemy / SQLite** | Users, secrets, challenges, gallery blobs, events. |
| **Security module** | Fernet encryption for embeddings / summaries at rest. |
| **Semantic pipeline** | Embeddings + LLM scoring + lockout policy. |
| **Greeting image module** | HF (or configured provider) image generation + decoys. |

---

## System context (alternative view)

```mermaid
flowchart LR
  User((User))
  SPA[React SPA]
  API[SAS API]
  DB[(SQLite)]
  Groq[Groq]
  HF[Hugging Face]

  User --> SPA
  SPA --> API
  API --> DB
  API --> Groq
  API --> HF
```

For formal **C4** models (Context / Container / Component), copy containers from the diagram above into Structurizr, PlantUML C4, or draw.io.
