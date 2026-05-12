# User stories — Semantic Authentication System (SAS)

SAS supports **password + semantic secret + visual greeting challenge**, with **text and voice** paths and **inclusive** access (e.g. spoken prompts). Stories below describe value from the **end user’s** perspective.

## Registration and onboarding

| ID | Story |
|----|--------|
| US-01 | **As a** new user, **I want to** register with username, password, and a semantic secret I can express in my own words later, **so that** I can sign in without memorizing exact wording. |
| US-02 | **As a** user who prefers not to type the secret phrase, **I want to** register my secret **by voice** (record or upload), **so that** the system captures the same idea in a way that works for me. |
| US-03 | **As a** user, **I want to** describe a **personal security image** in text and **see a preview** before finishing registration, **so that** I can recognize that image among decoys when I sign in. |
| US-04 | **As a** user, **I want** optional email on registration, **so that** the service can support account recovery when my account is locked after repeated failures. |

## Sign-in (multi-step)

| ID | Story |
|----|--------|
| US-05 | **As a** returning user, **I want to** enter username (or email) and password first, **so that** only after that I face the image and semantic challenges. |
| US-06 | **As a** user, **I want to** choose my real **security image** among **six** tiles, **so that** a fake login page cannot rely on password alone to impersonate the real flow. |
| US-07 | **As a** user, **I want to** answer the semantic challenge by **typing** or **speaking** (record or upload), **so that** I can use the modality that matches my abilities and context. |
| US-08 | **As a** blind or low-vision user, **I want to** **hear** the login prompt (text-to-speech), **so that** I know how to respond without reading the screen. |
| US-09 | **As a** user who enabled **image-only** sign-in, **I want** a correct image choice to finish authentication without a second semantic step, **so that** I can trade some assurance for less friction when I choose to. |

## Session and profile

| ID | Story |
|----|--------|
| US-10 | **As a** signed-in user, **I want to** view and update username, email, and password, **so that** I can keep my account details current. |
| US-11 | **As a** signed-in user, **I want to** replace my semantic secret (text or voice), **so that** I can recover from worry about disclosure or from forgetting how I phrased the old idea. |
| US-12 | **As a** signed-in user, **I want to** change only the **security greeting image** (new description) **without** changing my semantic secret, **so that** I can refresh the picture I recognize at login. |
| US-13 | **As a** signed-in user, **I want to** switch between **both factors** (image + semantic) and **image-only** sign-in, **so that** I can align the service with how much assurance I want each time. |
| US-14 | **As a** signed-in user, **I want to** sign out on this device, **so that** my session token is cleared here. |

## Help, evaluation, and administration

| ID | Story |
|----|--------|
| US-15 | **As a** user, **I want** in-product help that explains password, semantic secret, and security image, **so that** I understand how the three pieces work together. |
| US-16 | **As a** researcher or evaluator, **I want** structured feedback when verification fails (e.g. similarity bands), **so that** usability and security trade-offs can be analysed without storing raw secrets in logs. |
| US-17 | **As an** administrator, **I want** a controlled way to clear repeated-failure lockout for a given account identifier, **so that** study participants or support cases can continue evaluation after policy blocks them. |

## Quality attributes reflected in the stories

- **Accessibility:** Voice registration and login, optional TTS for the semantic prompt (US-02, US-07, US-08).
- **Security:** Six-tile image challenge, progressive lockout, encrypted semantic material at rest (US-06, US-09, US-16).
- **Responsiveness:** Web client usable on desktop and mobile browsers (cross-cutting).
