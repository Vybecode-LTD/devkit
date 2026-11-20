"""The two registries `add` and `remove` write (`mechframe.registries`): whole,
in id order, and as the site's Black and ESLint would leave them."""

from __future__ import annotations

from pathlib import Path

import black

from mechframe import registries

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "site"
MANY = [f"module-number-{each}" for each in range(1, 9)]


def _black(text: str) -> str:
    return black.format_str(text, mode=black.Mode(line_length=registries.WIDTH))


def test_no_modules_is_the_template_as_it_is() -> None:
    assert registries.python([]) == (TEMPLATE / registries.PYTHON).read_text("utf-8")
    assert registries.web([]) == (TEMPLATE / registries.WEB).read_text("utf-8")


def test_the_backends_registry_is_as_black_leaves_it() -> None:
    for ids in ([], ["blog"], ["media-gallery", "blog"], MANY):
        text = registries.python(ids)
        assert _black(text) == text, ids
    assert 'MODULE_IDS: tuple[str, ...] = ("blog", "media-gallery")' in registries.python(
        ["media-gallery", "blog"]
    )
    assert 'MODULE_IDS: tuple[str, ...] = ("blog",)' in registries.python(["blog"])


def test_the_webs_registry_imports_each_binding_by_a_name_of_its_own() -> None:
    text = registries.web(["media-gallery", "blog"])
    assert 'import blogModule from "./modules/blog/module.web";' in text
    assert 'import mediaGalleryModule from "./modules/media-gallery/module.web";' in text
    assert "export const modules: ModuleDefinition[] = [blogModule, mediaGalleryModule];" in text
    long = registries.web(MANY)
    assert "  moduleNumber1Module," in long
    assert all(len(line) <= registries.WIDTH for line in long.splitlines())


def test_a_name_is_never_a_reserved_word() -> None:
    assert registries.identifier("new") == "newModule"
    assert registries.identifier("a-b-c") == "aBCModule"
