"""The harness's probe modules, mounted by its test support only
(docs/contracts/auth-api.md, "The harness's test support"; K4 contract
change 19).

The repo's real modules wait as `modules/_<id>/` scaffolds, so without these
the contract suite would have nothing to switch off and no job that fails.
`probe` has a route, a settings section with a secret, and two jobs: one
that fails on its one try and one that does nothing. `probe-addon` requires
`probe`, so switching `probe` off turns it off too.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from kernel import jobs
from kernel.access import public
from kernel.answers import Answer
from kernel.modules import InstalledModule, Manifest


class ProbeFailure(Exception):
    """What `probe.fail` raises: its name is the job's last error."""


@jobs.handler("probe.fail", tries=1)
async def _fail(ctx: jobs.Context, payload: dict[str, Any]) -> None:
    raise ProbeFailure


@jobs.handler("probe.ok", tries=1)
async def _ok(ctx: jobs.Context, payload: dict[str, Any]) -> None:
    return None


@jobs.handler("probe-addon.ok", tries=1)
async def _addon_ok(ctx: jobs.Context, payload: dict[str, Any]) -> None:
    return None


class ProbeSettings(BaseModel):
    """The settings section `probe`: a word, a number and a secret."""

    model_config = ConfigDict(extra="forbid")

    greeting: str = Field(default="hello", max_length=200)
    count: int = Field(default=1, ge=0, le=100)
    token: SecretStr | None = None


class Pong(Answer):
    """The probe's answer while it's on."""


router = APIRouter()


@router.get("/ping", dependencies=[Depends(public)], response_model=Pong)
async def ping() -> dict[str, Any]:
    return {}


def _manifest(module_id: str, name: str, summary: str, requires: dict[str, str]) -> Manifest:
    return Manifest.from_dict(
        {
            "id": module_id,
            "name": name,
            "version": "0.1.0",
            "summary": summary,
            "category": "admin",
            "requires": {"modules": requires},
        }
    )


MODULES = (
    InstalledModule(
        _manifest("probe", "Probe", "The test support's module: a route, settings and jobs", {}),
        router=router,
        settings=ProbeSettings,
        jobs=(_fail, _ok),
    ),
    InstalledModule(
        _manifest(
            "probe-addon",
            "Probe add-on",
            "Needs the probe, to show a switch-off spreading",
            {"probe": "^0.1"},
        ),
        jobs=(_addon_ok,),
    ),
)
