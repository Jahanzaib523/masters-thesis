# Database Schema

Here's the data model we use to store accounts, encrypted semantic data, login challenges (with their 6 image tiles), pre-generated galleries, and login event logs. The diagram below shows the core structure.

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

- **usernames** are always unique. If an **email** is provided, it must also be unique.
- Image tiles have unique combinations of **(challenge_id, slot)** or **(user_id, slot)** so we don't accidentally double-book a slot.

## Schema evolution

We handle migrations automatically on startup. If you spin up an older database, the app just adds whatever new columns it needs behind the scenes so you don't have to worry about running separate migration scripts. The diagram above shows the final expected structure.
