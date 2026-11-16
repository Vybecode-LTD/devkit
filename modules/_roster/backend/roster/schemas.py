"""Pydantic models for roster, strict mode (SPEC.md section 7). `Settings` is the source of truth for module.json settings."""

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(strict=True)

    pass


# TODO: request and response models for each route in router.py (inputs strict, lists as {items, next_cursor}).
