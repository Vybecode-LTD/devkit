"""What routes answer, typed (K4, decision 0042; SPEC.md 7 and 18).

Every API route declares the model of its answer, so the committed
`openapi.json` describes it and the web kernel's client is generated typed
from it. An `Answer` refuses keys it doesn't name, and every JSON answer goes
out through its model:

- a route that returns a dict names its model as `response_model`, and FastAPI
  checks the dict against it on the way out;
- a route that builds its own response, for a cookie, a header or a status of
  its own, builds it with `answer(Model, content)`, which checks it the same
  way and leaves out only the keys the content never set.

So an answer can't drift from what the spec says: a missing or extra key is a
500 in the tests that make the call. The JSON itself doesn't change: ids and
times are already strings when a route builds them (`Id`, `When` only say what
kind of string, for the spec).
"""

from __future__ import annotations

from functools import cache
from typing import Annotated, Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, TypeAdapter, WithJsonSchema

__all__ = ["Answer", "AuditEntry", "Id", "OwnActivityEntry", "TargetRef", "When", "answer"]


class Answer(BaseModel):
    """The base of every answer model: it names every key it holds."""

    model_config = ConfigDict(extra="forbid")


#: A UUID, as the string a route already makes of it.
Id = Annotated[str, WithJsonSchema({"type": "string", "format": "uuid"})]
#: A time in ISO 8601 with its zone, as `datetime.isoformat()` writes it.
When = Annotated[str, WithJsonSchema({"type": "string", "format": "date-time"})]


@cache
def _adapter(model: Any) -> TypeAdapter[Any]:
    return TypeAdapter(model)


def answer(
    model: Any,
    content: Any,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """`content` checked against `model` (an `Answer`, or a union of them) and
    sent as JSON. A key the content leaves out stays out: an optional field
    with no value is absent, never null, as WebAuthn's options need."""
    adapter = _adapter(model)
    checked = adapter.validate_python(content)
    body = adapter.dump_python(checked, mode="json", exclude_unset=True)
    return JSONResponse(body, status_code=status_code, headers=headers)


# --- shapes more than one router answers -------------------------------------------------


class TargetRef(Answer):
    """What an entry or a case is about: `(kind, id)`, such as `("blog.post", "<id>")`."""

    type: str
    id: str


class AuditEntry(Answer):
    """An audit entry as the staff's log answers it (`kernel.audit.item`)."""

    id: int
    at: When
    action: str
    result: str
    actor_id: Id | None
    subject_id: Id | None
    target: TargetRef | None
    ip: str | None
    user_agent: str
    details: dict[str, Any]


class OwnActivityEntry(Answer):
    """An audit entry as the person it concerns reads it (`kernel.audit.own_item`):
    whether they did it, never who else did."""

    id: int
    at: When
    action: str
    result: str
    target: TargetRef | None
    ip: str | None
    user_agent: str
    details: dict[str, Any]
    by_you: bool
