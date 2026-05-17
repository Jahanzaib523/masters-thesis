# UML views Semantic Authentication System (SAS)

Figures in this document are **Mermaid** diagrams embedded in Markdown.

---

## 1. High-level use cases

```mermaid
flowchart TB
  subgraph Actors
    U[End user]
    A[Administrator]
  end

  subgraph SAS["SAS system"]
    UC1[Register with text or voice]
    UC2[Sign in: password, image grid, semantic]
    UC3[Profile, secret, image, login mode]
    UC4[Listen to prompt]
    UC5[Recovery and admin lockout reset]
  end

  U --> UC1
  U --> UC2
  U --> UC3
  U --> UC4
  U --> UC5
  A --> UC5
```

---

## 2. Domain class diagram (persistence entities)

```mermaid
classDiagram
  class User {
    +int id
    +string username
    +string email
    +string password_hash
    +bytes greeting_image_bytes
    +string greeting_image_mime
    +string login_mode
    +int semantic_failed_attempts
    +datetime semantic_locked_until
    +bool semantic_hard_locked
    +datetime created_at
  }

  class SecretEmbedding {
    +int id
    +int user_id
    +string secret_type
    +bytes embedding_encrypted
    +bytes semantic_summary_encrypted
    +string model_name
    +datetime created_at
  }

  class LoginChallenge {
    +int id
    +int user_id
    +string status
    +int attempt_count
    +datetime expires_at
    +datetime image_gallery_verified_at
    +int image_pick_failures
  }

  class LoginChallengeGallerySlot {
    +int id
    +int challenge_id
    +int slot
    +bytes image_bytes
    +string image_mime
    +bool is_target
  }

  class UserGalleryPoolSlot {
    +int id
    +int user_id
    +int slot
    +bytes image_bytes
    +string image_mime
    +bool is_target
  }

  class LoginEvent {
    +int id
    +int user_id
    +string result
    +string similarity_bucket
    +datetime created_at
  }

  User "1" --> "*" SecretEmbedding
  User "1" --> "*" LoginChallenge
  User "1" --> "*" UserGalleryPoolSlot
  User "1" --> "*" LoginEvent
  LoginChallenge "1" --> "*" LoginChallengeGallerySlot
```

---

## 3. Sequence: Sign-in (both factors: password → image → semantic)

```mermaid
sequenceDiagram
  autonumber
  participant Client as Web client
  participant API as SAS REST API
  participant Store as Data store
  participant SemLLM as Semantic LLM
  participant Emb as Sentence embeddings

  Client->>API: Initialize login (identifier, password)
  API->>Store: Verify account, lockout, gallery pool
  API->>Store: Create challenge and gallery rows
  API-->>Client: Challenge id, image URLs, prompt metadata

  loop Each gallery slot
    Client->>API: Request gallery tile image
    API-->>Client: Image bytes
  end

  Client->>API: Submit selected tile
  API->>Store: Validate target tile
  API-->>Client: Proceed to semantic step

  Client->>API: Submit semantic response (text or transcribed voice)
  API->>Store: Load encrypted summary and embedding
  API->>SemLLM: Score meaning similarity when summary path applies
  API->>Emb: Cosine similarity fallback when required
  API->>Store: Record outcome, update lockout, close challenge
  API-->>Client: Session token or structured failure
```

---

## 4. Sequence: Registration with text secret (conceptual)

```mermaid
sequenceDiagram
  participant Client as Web client
  participant API as SAS REST API
  participant Store as Data store
  participant SemLLM as Semantic LLM
  participant Img as Image provider
  participant Emb as Sentence embeddings

  Client->>API: Request greeting image preview
  API->>Img: Generate image from description
  API-->>Client: Preview image

  Client->>API: Submit registration
  API->>Emb: Embed secret phrase
  API->>SemLLM: Derive semantic summary for storage
  API->>Img: Generate primary security image (synchronous)
  API->>Store: Persist user, secret material, and primary image
  API-->>Client: Account created
  Note over API,Img: Generate the 5 decoys in the background
```

---

## 5. Sequence: Profile Security Image Update

```mermaid
sequenceDiagram
  participant Client as Web client
  participant API as SAS REST API
  participant Store as Data store
  participant Img as Image provider

  Client->>API: Request greeting image preview
  API->>Img: Generate image from description
  API-->>Client: Preview image

  Client->>API: Submit new security image description
  API->>Img: Generate primary security image (synchronous)
  API->>Store: Delete old gallery, update primary image
  API-->>Client: Profile updated
  Note over API,Img: Spin up 5 new decoys in the background
```

---

## 6. Semantic LLM provider (Groq vs OpenAI)

```mermaid
flowchart LR
  subgraph Client["Web client"]
    UI[Semantic provider preference]
  end

  subgraph API["SAS backend"]
    Router[Auth and profile routes]
    Prov[Provider resolution]
    G[Groq client]
    O[OpenAI client]
  end

  UI -->|Optional header on supported calls| Router
  Router --> Prov
  Prov -->|Default| G
  Prov -->|When OpenAI selected and configured| O
```

Default semantic operations use **Groq**. When the client marks **OpenAI** for semantic scoring and summarisation and the deployment supplies OpenAI credentials, those operations use **OpenAI** instead for the same contracts.

---

## 7. State machine — Login challenge lifecycle

```mermaid
stateDiagram-v2
  [*] --> PENDING: Password verified, challenge issued
  PENDING --> PENDING: Incorrect image or semantic attempt within limits
  PENDING --> COMPLETED: Successful authentication
  PENDING --> EXPIRED: Challenge lifetime exceeded
  COMPLETED --> [*]
  EXPIRED --> [*]
```
