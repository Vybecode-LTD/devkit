"""Pydantic models for audio-player, strict mode (SPEC.md section 7). `Settings` is the source of truth for module.json settings."""

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(strict=True)

    autoplay_next: bool = True  # Move to the next item in a queue when one ends
    count_after_seconds: int = 30  # Seconds of listening before a play counts


# TODO: request and response models for each route in router.py (inputs strict, lists as {items, next_cursor}).
