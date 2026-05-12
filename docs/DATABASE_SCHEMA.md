# Persistence schema — Semantic Authentication System (SAS)

The SAS persistence model stores accounts, encrypted semantic artefacts, per-login challenges with six binary image slots, a per-user pre-generated gallery pool, and anonymised login outcomes. The diagram below is the **conceptual schema** implemented in the application layer.

## Entity–relationship model

```mermaid
erDiagram
  users ||--o{ secret_embeddings : "has many"
  users ||--o{ login_challenges : "has many"
  users ||--o{ user_gallery_pool_slots : "has many"
  users ||--o{ login_events : "has many"
  login_challenges ||--o{ login_challenge_gallery_slots : "has many"

  users {
    int id PK
    string username UK
    string email UK "nullable"
    string password_hash "nullable"
    blob greeting_image_bytes "nullable"
    string greeting_image_mime "nullable"
    int greeting_seed "nullable"
    string greeting_prompt_hash "nullable"
    string greeting_model_name "nullable"
    string login_mode "both or image_only"
    int semantic_failed_attempts
    int semantic_lock_step
    datetime semantic_locked_until "nullable"
    bool semantic_hard_locked
    datetime created_at
    datetime updated_at
    string greeting_image_path "nullable legacy"
  }

  secret_embeddings {
    int id PK
    int user_id FK
    string secret_type "text or voice"
    blob embedding_encrypted
    blob semantic_summary_encrypted "nullable"
    string model_name
    datetime created_at
  }

  login_challenges {
    int id PK
    int user_id FK
    string status "pending completed expired"
    int attempt_count
    datetime created_at
    datetime expires_at
    datetime image_gallery_verified_at "nullable"
    int image_pick_failures
  }

  login_challenge_gallery_slots {
    int id PK
    int challenge_id FK
    int slot "0 to 5 unique per challenge"
    blob image_bytes
    string image_mime
    bool is_target
  }

  user_gallery_pool_slots {
    int id PK
    int user_id FK
    int slot "0 to 5 unique per user"
    blob image_bytes
    string image_mime
    bool is_target
    datetime created_at
    datetime updated_at
  }

  login_events {
    int id PK
    int user_id FK "nullable"
    string result "success failure locked"
    string similarity_bucket "nullable"
    datetime created_at
  }
```

## Integrity rules

- Each **username** is unique; **email**, when present, is unique.
- Gallery tiles are uniquely keyed by **(challenge_id, slot)** and **(user_id, slot)** for challenge and pool tables respectively.

## Schema evolution

The shipped application may add columns or tables on startup when older files are opened, so that existing study databases gain new fields without a separate migration tool. The diagram represents the **intended** relational shape after a successful run.
