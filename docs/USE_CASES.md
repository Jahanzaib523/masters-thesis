# Use cases: Semantic Authentication System (SAS)

**Primary actor:** End user  
**Secondary actors:** SAS application, external AI services (**Groq** for default LLM / speech / TTS; **OpenAI** as an optional alternative for semantic operations when enabled), **Hugging Face** (image generation and hub access), **administrator** (lockout recovery operations)

---

## UC-01 Register with text secret

- **Goal:** Create an account with password, typed semantic secret, and greeting-image description.
- **Preconditions:** None.
- **Main success scenario:** The system validates input, stores credentials and encrypted semantic material, generates a semantic summary via the configured LLM provider, and prepares the user’s security image and six-tile gallery asynchronously; the user can proceed to sign-in.
- **Extensions:** Duplicate username or email; password policy failure; image generation unavailable.

---

## UC-02 Register with voice secret

- **Goal:** Same outcome as UC-01 with the secret supplied as audio transcribed server-side.
- **Preconditions:** Audio capture or file available.
- **Extensions:** Transcription failure; transcribed text exceeds allowed length.

---

## UC-03 Preview greeting image

- **Goal:** Visual confirmation of the image implied by the user’s description before registration is finalized.
- **Preconditions:** Non-empty image description within length limits.
- **Main success scenario:** The system returns generated image content for display.

---

## UC-04 Initialize login (password gate)

- **Goal:** Start an authenticated challenge after verifying identifier and password.
- **Preconditions:** Account exists, password valid, account not in a blocking lockout state, security image and gallery pool materialized.
- **Main success scenario:** A login challenge is created; six gallery image references and semantic-step metadata are returned.
- **Extensions:** Unknown identifier; wrong password; temporary cooldown; hard lock; image or gallery not yet ready.

---

## UC-05 Pick security image (six-tile)

- **Goal:** Demonstrate recognition of the user’s greeting image among decoys.
- **Preconditions:** Active login challenge from UC-04.
- **Main success scenario (both factors):** Correct tile confirms the gallery step; user continues to the semantic step.
- **Main success scenario (image-only):** Correct tile completes authentication and yields a session token.
- **Extensions:** Wrong tile with remaining attempts; lockout escalation after policy limits.

---

## UC-06 Complete semantic login (text)

- **Goal:** Finish authentication by expressing the secret’s meaning in natural language.
- **Preconditions:** Gallery step satisfied for “both” mode; challenge still valid.
- **Main success scenario:** Semantic similarity (LLM-based, with embedding fallback when needed) meets policy; session token issued; challenge closed; gallery pool refresh scheduled.
- **Extensions:** Near-threshold guidance; attempt limits; cooldown or hard lock.

---

## UC-07 Complete semantic login (voice)

- **Goal:** Same as UC-06 with the response supplied as transcribed speech.
- **Preconditions:** Same as UC-06.
- **Extensions:** Empty or unusable transcription.

---

## UC-08 Listen to login prompt (TTS)

- **Goal:** Access the semantic prompt as audio.
- **Preconditions:** Valid challenge identifier.
- **Main success scenario:** Spoken prompt audio is returned to the client.

---

## UC-09 View and update account profile

- **Goal:** Read profile fields and update username, email, or password.
- **Preconditions:** Valid session token.
- **Extensions:** Conflicting username or email; invalid email format.

---

## UC-10 Update semantic secret

- **Goal:** Replace the stored secret (text or voice) while authenticated.
- **Preconditions:** Valid session token.
- **Main success scenario:** Prior secret material is superseded; new embedding and semantic summary are stored under the chosen provider configuration.

---

## UC-11 Update security greeting image

- **Goal:** Regenerate the visual cue from new image description without changing the semantic secret.
- **Preconditions:** Valid session token.

---

## UC-12 Change login mode

- **Goal:** Switch between **both** (image + semantic) and **image-only** for subsequent sign-ins.
- **Preconditions:** Valid session token.

---

## UC-13 Sign out

- **Goal:** End the session on the client by discarding the token.
- **Preconditions:** None.

---

## UC-14 Request semantic unlock

- **Goal:** Begin recovery for an account in hard-lock state when email is on file.
- **Preconditions:** Matching identifier; hard lock; email present.

---

## UC-15 Confirm semantic unlock

- **Goal:** Clear hard-lock state using a valid recovery token bound to semantic unlock purpose.
- **Preconditions:** Unexpired token with correct purpose claim.

---

## UC-16 Administrative lockout reset

- **Goal:** Reset semantic failure counters for an identifier using an administrator credential known to the deployment.

---

## UC-17 System health visibility

- **Goal:** Expose liveness and dependency health for operations and study environments (application, image generation, token configuration presence without revealing secrets).
