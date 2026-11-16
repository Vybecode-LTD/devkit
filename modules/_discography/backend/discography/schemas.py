"""Pydantic models for discography, strict mode (SPEC.md section 7). `Settings` is the source of truth for module.json settings."""

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(strict=True)

    default_audio_source: str = "upload"  # upload or soundcloud, the default for new tracks
    stream_bitrate_kbps: int = 256  # Bitrate of the public stream file made from an uploaded master
    show_explicit_badge: bool = True  # Mark explicit tracks in lists and players


# TODO: request and response models for each route in router.py (inputs strict, lists as {items, next_cursor}).
