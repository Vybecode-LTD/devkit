# Event payload schemas

Each module exports its event payloads (the Pydantic models in its `events.py`) as JSON Schema here, one file per event and version: `<event-name>.v<N>.schema.json`, for example `blog.post.published.v1.schema.json` (SPEC.md section 11). They are generated, never edited by hand, and they keep the event contract language-neutral (decision 0004).
