"""Pydantic models for comments, strict mode (SPEC.md section 7). `Settings` is the source of truth for module.json settings."""

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(strict=True)

    guest_comments: bool = (
        True  # Guests may comment; every guest comment waits for approval (owner answer Q4)
    )
    edit_window_minutes: int = 15  # Minutes a comment stays editable
    max_links: int = 2  # Links allowed in one comment


# TODO: request and response models for each route in router.py (inputs strict, lists as {items, next_cursor}).
