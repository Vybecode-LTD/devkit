"""tools/event_schemas.py: every declared event payload as JSON Schema in
schema/events/ (SPEC.md section 11, decision 0036)."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from tools import event_schemas

KERNEL_FILES = {
    "auth.user.created.v1.schema.json",
    "auth.user.verified.v1.schema.json",
    "auth.user.deleted.v1.schema.json",
    "kernel.settings.changed.v1.schema.json",
}


def test_the_schemas_in_the_repo_are_current() -> None:
    assert event_schemas.main(["--check"]) == 0


def test_each_kernel_event_has_a_schema_of_its_own() -> None:
    assert set(event_schemas.schemas()) >= KERNEL_FILES


def test_a_schema_describes_its_payload_and_refuses_more() -> None:
    schema = event_schemas.schemas()["auth.user.deleted.v1.schema.json"]
    Draft202012Validator.check_schema(schema)
    assert schema["title"] == "auth.user.deleted (v1)"
    assert schema["required"] == ["user_id"]
    assert schema["properties"]["user_id"]["format"] == "uuid"
    assert schema["additionalProperties"] is False
    validator = Draft202012Validator(schema)
    assert validator.is_valid({"user_id": "6f1c2b9e-0a43-4c55-9d0c-6a7e2f1b3c4d"})
    assert not validator.is_valid({"user_id": "6f1c2b9e-0a43-4c55-9d0c-6a7e2f1b3c4d", "email": "x"})


def test_writing_makes_missing_files_and_removes_left_over_ones(tmp_path: Path) -> None:
    (tmp_path / "gone.post.published.v1.schema.json").write_text("{}", encoding="utf-8")
    (tmp_path / "README.md").write_text("kept", encoding="utf-8")
    assert event_schemas.main(["--check"], folder=tmp_path) == 1

    assert event_schemas.main([], folder=tmp_path) == 0
    assert {path.name for path in tmp_path.iterdir()} == KERNEL_FILES | {"README.md"}
    written = json.loads((tmp_path / "kernel.settings.changed.v1.schema.json").read_text("utf-8"))
    assert sorted(written["required"]) == ["module", "version"]
    assert event_schemas.main(["--check"], folder=tmp_path) == 0


def test_check_finds_a_stale_file(tmp_path: Path) -> None:
    event_schemas.main([], folder=tmp_path)
    (tmp_path / "auth.user.created.v1.schema.json").write_text("{}\n", encoding="utf-8")
    assert event_schemas.main(["--check"], folder=tmp_path) == 1
