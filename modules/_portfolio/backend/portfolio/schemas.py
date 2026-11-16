"""Pydantic models for portfolio, strict mode (SPEC.md section 7). `Settings` is the source of truth for module.json settings."""

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(strict=True)

    pieces_per_page: int = 24  # Pieces on each list page


# TODO: request and response models for each route in router.py (inputs strict, lists as {items, next_cursor}).
