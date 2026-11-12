"""Pydantic models for every request and response, in strict mode (SPEC.md section 7).

`Settings` is the module's settings model, stored by the kernel with version
history and save-conflict checks. Every field needs a default; a field typed
`SecretStr` is a secret, sealed at rest and never shown back (decision 0009).
Read it with `await settings.for_module(db, "my-module")`. Delete the class if
the module has no settings.
"""

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(strict=True)
