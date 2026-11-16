"""Pydantic models for licensing, strict mode (SPEC.md section 7). `Settings` is the source of truth for module.json settings."""

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(strict=True)

    free_download_for_email: bool = False  # Offer a tagged free download in exchange for an email
    credit_line: str = "prod. by Vibrant Mindz"  # Credit printed on every agreement


# TODO: request and response models for each route in router.py (inputs strict, lists as {items, next_cursor}).
