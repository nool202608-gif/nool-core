# Colearner Service

Turn-based voice Bloom's Taxonomy oral co-learner, ported from the
`nool-research` prototype (`nool-research/app`) into nool-core's service
shape. Firebase-authenticated, same as `auth`/`core`.

```
nool-app -> NGINX -> Colearner Service -> OpenAI / Gemini / Edge-TTS
```

## Two pipelines, each with fixed (non-configurable) models

| Pipeline | STT | LLM | TTS |
| --- | --- | --- | --- |
| **Chained** (`/api/v1/colearner/chained*`) | OpenAI Whisper (`whisper-1`) | OpenAI `gpt-4o-mini` | Edge-TTS |
| **Multimodal** (`/api/v1/colearner/multimodal*`) | — (direct audio-in) | Gemini `gemini-3.5-flash-lite` | Edge-TTS |

Model/provider/voice selection is intentionally **not** part of the request
schema (`src/domain/schemas.py`'s `SessionConfig`) - each pipeline's
service module (`src/services/chained_service.py`,
`src/services/multimodal_service.py`) fixes its own `LLM_MODEL`/`TTS_VOICE`
constants. Only pedagogical config (grade, subject, chapter, num_questions,
Bloom's levels, textbook context, reference questions, session time limit)
is client-supplied.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Process health. |
| GET | `/ready` | Ready when Firebase is configured and at least one model API key is set. |
| POST | `/api/v1/colearner/chained` | Chained pipeline turn (init + subsequent turns). Requires `Authorization: Bearer <firebase-id-token>`. |
| WS | `/api/v1/colearner/chained/stream?token=<firebase-id-token>` | Chained pipeline, live streaming. |
| POST | `/api/v1/colearner/multimodal` | Multimodal pipeline turn. Requires `Authorization: Bearer <firebase-id-token>`. |
| WS | `/api/v1/colearner/multimodal/stream?token=<firebase-id-token>` | Multimodal pipeline, live streaming. |

WebSocket auth uses a `?token=` query param rather than an `Authorization`
header, since browsers cannot set custom headers on the WS handshake - same
pattern as `services/core/src/api/routes/ai_assessor.py`'s
`stream_session`.

## Known v1 limitations

- **Sessions are in-memory only** (`src/services/session_store.py`) - lost
  on container restart, not shared across replicas. No Redis/DB added for
  this; revisit only if the service needs to scale horizontally or survive
  restarts mid-session (see nool-core/claude.md: don't add infra without an
  actual requirement).
- **Reports are written to a container-local `reports/` directory**, not a
  durable store - same reasoning as above.

## Environment variables

See the repo root `.env.example`'s "Voice Co-Learner service" section:
`FIREBASE_PROJECT_ID`, `FIREBASE_CREDENTIALS_HOST_PATH` (shared with
`auth`/`core`), `OPENAI_API_KEY` (shared with `kg`), `GEMINI_API_KEY`.
