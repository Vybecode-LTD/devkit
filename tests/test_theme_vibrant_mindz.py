"""The Vibrant Mindz theme's own checks, moved here with its generator at K4
(from VM Website design/theme/vibrant-mindz/test_tokens.py): its contrast
pairs, as drawn on the site and in the admin; every alias sound and every
role pointing at the palette; shadows and filters holding no hex; each alpha
its palette colour at its named percentage; and reduced motion. The kernel's
own checks, for every theme, are in test_themes.py. Rendered contrast (text
over the glows and photos, hover and focus) is checked on real pages."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools import themes

THEME = themes.load(Path(__file__).resolve().parents[1] / "themes" / "vibrant-mindz")
TOKENS = THEME.tokens
BY_PATH = THEME.by_path


def hex_of(path: str) -> str:
    value = themes.literal(BY_PATH[path], BY_PATH)
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", value), f"{path} is {value!r}, not an opaque hex"
    return value


def luminance(h: str) -> float:
    c = [int(h[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# (foreground, background, minimum). 4.5 for text, 3 for the focus ring against what it sits on.
GROUNDS = ["color.canvas", "color.surface", "color.surface-2"]
ADMIN_GROUNDS = ["color.canvas", "color.surface", "color.surface-raised", "color.rail"]
PAIRS = (
    [
        (fg, bg, 4.5)
        for fg in [
            "color.text",
            "color.text-strong",
            "color.text-muted",
            "color.link",
            "color.link-hover",
            "color.accent",
            "color.accent-2",
        ]
        for bg in GROUNDS
    ]
    + [
        (fg, "color.well", 4.5)
        for fg in [
            "color.text",
            "color.text-strong",
            "color.text-muted",
            "color.accent-2",
            "color.palette.lcd-dim",
        ]
    ]
    + [("color.text-subtle", bg, 4.5) for bg in ["color.canvas", "color.surface"]]
    + [
        ("color.on-accent", "color.accent", 4.5),
        ("color.on-accent", "color.accent-hover", 4.5),
        ("color.on-accent-2", "color.accent-2", 4.5),
    ]
    + [(f"ext.deck.{d}.key-text", f"ext.deck.{d}.key", 4.5) for d in ("space-grey", "aluminum")]
    + [
        (f"ext.deck.{d}.silk", f"ext.deck.{d}.{part}", 4.5)
        for d in ("space-grey", "aluminum")
        for part in ("top", "bottom")
    ]
    + [("color.focus", bg, 3.0) for bg in [*GROUNDS, "color.well"]]
    # The admin: its text and status colours on each of its grounds, and the site's focus outline there.
    + [
        (fg, bg, 4.5)
        for fg in [
            "color.text",
            "color.text-strong",
            "color.text-muted",
            "color.success",
            "color.warning",
            "color.danger",
        ]
        for bg in ["color.surface-raised", "color.rail"]
    ]
    + [
        (fg, bg, 4.5)
        for fg in ["color.success", "color.warning", "color.danger"]
        for bg in ["color.canvas", "color.surface"]
    ]
    + [("color.focus", bg, 3.0) for bg in ["color.surface-raised", "color.rail"]]
    # The admin's own focus ring is a 1px line of the accent (shadow.focus-ring; owner, 2026-11-18).
    + [("color.accent", bg, 3.0) for bg in ADMIN_GROUNDS]
)


def test_the_contrast_gate_can_fail() -> None:
    # Positive control: the strong border on the page is decorative and far under 3:1.
    assert ratio(hex_of("color.border-strong"), hex_of("color.canvas")) < 3.0


@pytest.mark.parametrize(("fg", "bg", "minimum"), PAIRS, ids=[f"{f}|{b}" for f, b, _ in PAIRS])
def test_contrast(fg: str, bg: str, minimum: float) -> None:
    got = ratio(hex_of(fg), hex_of(bg))
    assert got >= minimum, f"{fg} on {bg}: {got:.2f}:1, needs {minimum}:1"


def test_every_pair_was_checked() -> None:
    assert len(PAIRS) == 65
    assert set(ADMIN_GROUNDS) <= {bg for _, bg, _ in PAIRS}


def test_every_alias_resolves_and_roles_hold_no_hex() -> None:
    aliases = [t for t in TOKENS if isinstance(t.value, str) and themes.ALIAS.match(t.value)]
    # 62, plus the kernel's font, radius and motion names (K4), plus the control edge and the
    # four pill tints (K4.4), plus info and its tint (K4.6), plus a field's fill (#101)
    assert len(aliases) == 78
    for t in aliases:
        themes.literal(t, BY_PATH)
    # Every colour role points at the palette or an alpha, so a colour is changed in one place.
    roles = [t for t in TOKENS if len(t.path) == 2 and t.path[0] == "color"]
    assert len(roles) == 34  # info and its tint joined at K4.6, the field's fill at #101
    assert [t.dotted for t in roles if not themes.ALIAS.match(str(t.value))] == []


def test_shadows_and_filters_point_at_colours_not_hex() -> None:
    composite = [t for t in TOKENS if t.path[0] in ("shadow", "effect")]
    assert len(composite) == 35
    for t in composite:
        assert not re.search(
            r"#[0-9A-Fa-f]{3,8}\b|rgba?\(", str(t.value)
        ), f"{t.dotted} holds a colour literal"
        themes.literal(t, BY_PATH)
    assert (
        themes.css_value(BY_PATH["shadow.glow-accent"], BY_PATH)
        == "0 0 12px var(--mf-color-palette-fire)"
    )
    assert themes.literal(BY_PATH["shadow.glow-accent"], BY_PATH) == "0 0 12px #FF7A1F"


def test_each_alpha_colour_is_its_palette_colour() -> None:
    alphas = [t for t in TOKENS if t.path[:2] == ("color", "alpha")]
    assert len(alphas) == 81
    for t in alphas:
        base = hex_of(f"color.palette.{t.path[2]}")
        rgb = tuple(int(base[i : i + 2], 16) for i in (1, 3, 5))
        m = re.fullmatch(r"rgba\((\d+), (\d+), (\d+), ([\d.]+)\)", t.value)
        assert m, f"{t.dotted} is {t.value!r}, not rgba(r, g, b, a)"
        assert (
            tuple(int(m.group(i)) for i in (1, 2, 3)) == rgb
        ), f"{t.dotted} isn't color.palette.{t.path[2]}"
        assert 0 <= float(m.group(4)) <= 1, f"{t.dotted}'s alpha is out of range"  # cubic on #80
        assert (
            t.path[3].replace("_", ".") == f"{float(m.group(4)) * 100:g}"
        ), f"{t.dotted}'s name doesn't match its alpha"


def test_reduced_motion_stops_every_duration_and_pauses_the_ambient_loops() -> None:
    css = themes.render_css(THEME)
    block = css[css.index("prefers-reduced-motion") :]
    durations = [t.var for t in TOKENS if t.type == "duration"]
    assert len(durations) == 11  # 9, plus the kernel's motion.fast and motion.base
    for var in durations:
        assert f"{var}: 0s;" in block
    assert "--mf-motion-ambient-state: paused;" in block


def test_every_token_is_written_once_and_again_only_under_reduced_motion() -> None:
    main, reduced = themes.render_css(THEME).split("@media (prefers-reduced-motion: reduce)", 1)
    written = re.findall(r"^\s*(--mf-[^:\s]+):", main, re.M)
    expected = [name for token in TOKENS for name, _value in themes.declarations(token, BY_PATH)]
    # Each token once, a type role's tracking too, and no name twice (cubic on #80).
    assert written == expected
    assert len(set(written)) == len(written)
    again = re.findall(r"^\s*(--mf-[^:\s]+):", reduced, re.M)
    assert len(again) == 12  # 11 durations and the ambient state
    assert set(again) <= set(written)


def test_generic_font_keywords_stay_unquoted() -> None:
    css = themes.css_value(BY_PATH["typography.fontFamily.code"], BY_PATH)
    assert css == "ui-monospace, 'Consolas', monospace"


def test_the_kernel_names_are_its_own_values() -> None:
    """The aliases change no value: what the boards draw is what the kit gets."""
    pairs = {
        "font.mono": "typography.fontFamily.code",
        "radius.control": "radius.10",
        "radius.card": "radius.16",
        "radius.pill": "radius.full",
        "motion.fast": "motion.duration.fast",
    }
    for kernel, own in pairs.items():
        assert themes.literal(BY_PATH[kernel], BY_PATH) == themes.literal(BY_PATH[own], BY_PATH)
    assert (
        themes.literal(BY_PATH["type.page-title"], BY_PATH)
        == "600 1.75rem/1.3 Geist, system-ui, sans-serif"
    )
