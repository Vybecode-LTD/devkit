"""tools.themes and every theme in themes/ (K4 contract §2 and §7).

Each theme defines the kernel's required tokens, which themes/README.md
lists with their meaning; its references resolve; its text, links,
signals and focus meet their contrast on the grounds the kernel draws
them on; under reduced motion every duration is 0s; and the generated
files are current. No colour is written outside themes/: the kernel's
and the modules' CSS take theirs from tokens (the ESLint rule covers
TypeScript)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from tools import themes

ROOT = Path(__file__).resolve().parents[1]
THEMES = themes.discover()


def test_both_themes_are_built() -> None:
    # A theme added later is checked like these two (CodeRabbit on #80).
    assert {"machined-light", "vibrant-mindz"} <= {theme.name for theme in THEMES}


def test_the_readme_lists_the_required_tokens_with_their_meaning() -> None:
    readme = (ROOT / "themes" / "README.md").read_text("utf-8")
    section = readme.split("## Required tokens", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(r"^\| `([a-z][a-z0-9.-]*)` \| [^|]*\S[^|]* \|$", section, re.M)
    assert listed == list(themes.REQUIRED)


@pytest.mark.parametrize("theme", THEMES, ids=lambda theme: theme.name)
def test_each_theme_defines_every_required_token(theme: themes.Theme) -> None:
    by_path = theme.by_path
    assert [name for name in themes.REQUIRED if name not in by_path] == []
    for name in themes.REQUIRED:
        if name.startswith("type."):
            assert (
                by_path[name].type == "typography"
            ), f"{theme.name}: {name} isn't a typography token"


@pytest.mark.parametrize("theme", THEMES, ids=lambda theme: theme.name)
def test_every_reference_resolves(theme: themes.Theme) -> None:
    for token in theme.tokens:
        themes.literal(token, theme.by_path)


def luminance(hex_color: str) -> float:
    channels = [int(hex_color[at : at + 2], 16) / 255 for at in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ratio(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def opaque(theme: themes.Theme, name: str) -> str:
    value = themes.literal(theme.by_path[name], theme.by_path)
    assert re.fullmatch(
        r"#[0-9A-Fa-f]{6}", value
    ), f"{theme.name}: {name} is {value!r}, not an opaque hex"
    return value


GROUNDS = ["color.canvas", "color.surface", "color.surface-raised", "color.rail"]
TEXT = ["color.text-strong", "color.text", "color.text-muted", "color.text-subtle"]
SIGNALS = ["color.success", "color.warning", "color.danger", "color.info"]

#: (foreground, background, minimum): 4.5 for text, 3 for focus and the accent's
#: line against what it sits on (WCAG 2.2, 1.4.3 and 1.4.11).
PAIRS = (
    [(fg, bg, 4.5) for fg in TEXT for bg in GROUNDS]
    + [(fg, "color.well", 4.5) for fg in ["color.text-strong", "color.text"]]
    + [(fg, "color.field", 4.5) for fg in ["color.text-strong", "color.text", "color.text-subtle"]]
    + [
        (fg, bg, 4.5)
        for fg in ["color.link", "color.link-hover"]
        for bg in ["color.canvas", "color.surface"]
    ]
    + [("color.on-accent", bg, 4.5) for bg in ["color.accent", "color.accent-hover"]]
    + [
        (fg, bg, 4.5)
        for fg in SIGNALS
        for bg in ["color.canvas", "color.surface", "color.surface-raised"]
    ]
    + [("color.focus", bg, 3.0) for bg in [*GROUNDS, "color.well", "color.field"]]
    + [("color.border-control", bg, 3.0) for bg in GROUNDS]
    + [("color.accent", bg, 3.0) for bg in GROUNDS]
)


def test_vibrant_mindz_fills_a_field_with_its_page_colour() -> None:
    # The boards fill every field with the canvas, a shade lighter than the
    # well (VM Website Dev 05, 2026-11-21); Machined Light keeps its well.
    by_name = {theme.name: theme for theme in THEMES}
    mindz, light = by_name["vibrant-mindz"], by_name["machined-light"]
    assert opaque(mindz, "color.field") == opaque(mindz, "color.canvas")
    assert opaque(mindz, "color.field") != opaque(mindz, "color.well")
    assert opaque(light, "color.field") == opaque(light, "color.well")


#: A pill's words on its tint (K4.4): (words, tint).
PILLS = [
    ("color.success", "color.success-tint"),
    ("color.warning", "color.warning-tint"),
    ("color.danger", "color.danger-tint"),
    ("color.info", "color.info-tint"),
    ("color.text-muted", "color.neutral-tint"),
]


def laid_over(theme: themes.Theme, name: str, ground: str) -> str:
    """The token's colour laid over an opaque ground: itself if it's opaque, else blended."""
    value = themes.literal(theme.by_path[name], theme.by_path)
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        return value
    found = re.fullmatch(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", value)
    assert found, f"{theme.name}: {name} is {value!r}, neither a hex nor an rgba()"
    alpha = float(found.group(4))
    under = [int(ground[at : at + 2], 16) for at in (1, 3, 5)]
    over = [int(found.group(at)) for at in (1, 2, 3)]
    return "#" + "".join(
        f"{round(o * alpha + u * (1 - alpha)):02X}" for o, u in zip(over, under, strict=True)
    )


def test_a_tint_is_laid_over_its_ground() -> None:
    theme = next(each for each in THEMES if each.name == "vibrant-mindz")
    assert laid_over(theme, "color.success-tint", "#000000") == "#0B1912"
    assert laid_over(theme, "color.success", "#000000") == opaque(theme, "color.success")


@pytest.mark.parametrize(
    ("theme", "pill", "ground"),
    [(theme, pill, ground) for theme in THEMES for pill in PILLS for ground in GROUNDS],
    ids=[
        f"{theme.name}:{words}|{ground}"
        for theme in THEMES
        for words, _ in PILLS
        for ground in GROUNDS
    ],
)
def test_a_pill_reads_on_its_tint(theme: themes.Theme, pill: tuple[str, str], ground: str) -> None:
    words, tint = pill
    under = opaque(theme, ground)
    got = ratio(opaque(theme, words), laid_over(theme, tint, under))
    assert got >= 4.5, f"{theme.name}: {words} on {tint} over {ground} is {got:.2f}:1, needs 4.5:1"


def test_the_contrast_ratio_matches_known_values() -> None:
    assert ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert ratio("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.01)


@pytest.mark.parametrize(
    ("theme", "pair"),
    [(theme, pair) for theme in THEMES for pair in PAIRS],
    ids=[f"{theme.name}:{fg}|{bg}" for theme in THEMES for fg, bg, _ in PAIRS],
)
def test_contrast(theme: themes.Theme, pair: tuple[str, str, float]) -> None:
    fg, bg, minimum = pair
    got = ratio(opaque(theme, fg), opaque(theme, bg))
    assert got >= minimum, f"{theme.name}: {fg} on {bg} is {got:.2f}:1, needs {minimum}:1"


@pytest.mark.parametrize("theme", THEMES, ids=lambda theme: theme.name)
def test_reduced_motion_stops_every_duration(theme: themes.Theme) -> None:
    css = themes.render_css(theme)
    block = css[css.index("prefers-reduced-motion") :]
    durations = [token.var for token in theme.tokens if token.type == "duration"]
    assert durations, f"{theme.name} has no durations"
    for var in durations:
        assert f"{var}: 0s;" in block


@pytest.mark.parametrize("theme", THEMES, ids=lambda theme: theme.name)
def test_its_tokens_sit_under_its_own_name_only(theme: themes.Theme) -> None:
    css = themes.render_css(theme)
    assert f'[data-theme="{theme.name}"] {{' in css
    assert ":root" not in css  # a site names its theme on <html data-theme="...">


def test_the_generated_files_are_current() -> None:
    assert themes.main(["--check"]) == 0


@pytest.mark.parametrize("name", ["tokens.css", "tailwind.css"])
def test_git_keeps_the_generated_files_lf(name: str) -> None:
    # A Windows checkout with autocrlf otherwise writes CRLF, and --check calls every file stale.
    files = [(theme.folder / name).relative_to(ROOT).as_posix() for theme in THEMES]
    found = subprocess.run(  # noqa: S603  (git itself, our own paths)
        ["git", "check-attr", "eol", "--", *files],  # noqa: S607
        cwd=ROOT,
        env=_git_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.splitlines()
    assert found == [f"{path}: eol: lf" for path in files]


def _git_env() -> dict[str, str]:
    """The environment without the variables that point git at another repository (CodeRabbit on #81)."""
    return {key: value for key, value in os.environ.items() if key not in _GIT_LOCATION}


_GIT_LOCATION = {
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
}


def test_the_lf_check_reads_this_checkout_whatever_git_dir_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path / "other"
    subprocess.run(["git", "init", "-q", str(other)], check=True)  # noqa: S603, S607
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    test_git_keeps_the_generated_files_lf("tokens.css")


def test_a_stale_file_is_found(tmp_path: Path) -> None:
    folder = tmp_path / "solo"
    folder.mkdir()
    (folder / "tokens.json").write_text(
        '{"color": {"$type": "color", "canvas": {"$value": "#000000"}}}', "utf-8"
    )
    (folder / "tokens.css").write_text("stale", "utf-8")
    assert themes.main(["--check"], root=tmp_path) == 1
    assert themes.main([], root=tmp_path) == 0
    assert themes.main(["--check"], root=tmp_path) == 0


def test_names_are_kebab_case_under_the_prefix() -> None:
    for theme in THEMES:
        names = re.findall(r"^\s*(--[^:\s]+):", themes.render_css(theme), re.M)
        bad = [
            n
            for n in names
            if not re.fullmatch(r"--mf-[a-z0-9-]+(?:(?<=[0-9])_(?=[0-9])[a-z0-9-]*)*", n)
        ]
        assert bad == [], theme.name


def _token(path: str, value: object, kind: str | None) -> themes.Token:
    return themes.Token(tuple(path.split(".")), value, kind)


def test_an_alias_is_a_var_and_a_reference_inside_a_value_too() -> None:
    tokens = [
        _token("color.palette.fire", "#FF7A1F", "color"),
        _token("color.accent", "{color.palette.fire}", "color"),
        _token("shadow.glow", "0 0 12px {color.palette.fire}", "shadow"),
    ]
    by_path = themes.index(tokens)
    assert themes.css_value(tokens[1], by_path) == "var(--mf-color-palette-fire)"
    assert themes.css_value(tokens[2], by_path) == "0 0 12px var(--mf-color-palette-fire)"
    assert themes.literal(tokens[2], by_path) == "0 0 12px #FF7A1F"


def test_a_dangling_or_circular_reference_is_refused() -> None:
    dangling = _token("color.x", "{color.nope}", "color")
    with pytest.raises(ValueError, match="missing or circular"):
        themes.css_value(dangling, themes.index([dangling]))
    first = _token("color.a", "{color.b}", "color")
    second = _token("color.b", "{color.a}", "color")
    with pytest.raises(ValueError, match="missing or circular"):
        themes.literal(first, themes.index([first, second]))


def test_a_font_stack_keeps_generic_families_unquoted() -> None:
    stack = _token("font.code", ["ui-monospace", "JetBrains Mono", "monospace"], "fontFamily")
    assert (
        themes.css_value(stack, themes.index([stack]))
        == "ui-monospace, 'JetBrains Mono', monospace"
    )


def test_a_type_alias_brings_its_tracking_too() -> None:
    """A type role that's another's alias writes both of its variables (CodeRabbit on #80)."""
    tokens = [
        _token("font.text", ["Geist"], "fontFamily"),
        _token(
            "type.base",
            {"fontFamily": "{font.text}", "fontSize": "1rem", "fontWeight": 400, "lineHeight": 1.5},
            "typography",
        ),
        _token("type.body", "{type.base}", "typography"),
    ]
    by_path = themes.index(tokens)
    assert themes.declarations(tokens[2], by_path) == [
        ("--mf-type-body", "var(--mf-type-base)"),
        ("--mf-type-body-tracking", "var(--mf-type-base-tracking)"),
    ]


def test_a_type_role_is_a_font_shorthand_and_its_tracking() -> None:
    tokens = [
        _token("font.text", ["Geist", "sans-serif"], "fontFamily"),
        _token(
            "type.page-title",
            {
                "fontFamily": "{font.text}",
                "fontSize": "28px",
                "fontWeight": 600,
                "lineHeight": 1.2,
                "letterSpacing": "-0.01em",
            },
            "typography",
        ),
    ]
    by_path = themes.index(tokens)
    assert themes.declarations(tokens[1], by_path) == [
        ("--mf-type-page-title", "600 28px/1.2 var(--mf-font-text)"),
        ("--mf-type-page-title-tracking", "-0.01em"),
    ]


#: CSS's named colours (CSS Color 4), which a declaration may not use either.
_NAMES = (
    "aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet "
    "brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue "
    "darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange "
    "darkorchid darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise "
    "darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia "
    "gainsboro ghostwhite gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo "
    "ivory khaki lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan "
    "lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue "
    "lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon "
    "mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue "
    "mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin "
    "navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen "
    "paleturquoise palevioletred papayawhip peachpuff peru pink plum powderblue purple rebeccapurple red "
    "rosybrown royalblue saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue "
    "slategray slategrey snow springgreen steelblue tan teal thistle tomato turquoise violet wheat white "
    "whitesmoke yellow yellowgreen"
)
NAMED = _NAMES.split()

_NAMED = re.compile(r"\b(" + "|".join(NAMED) + r")\b", re.IGNORECASE)


#: A colour written as a value: a hex, a colour function, or a named colour
#: (cubic on #80). `transparent`, `currentColor` and `color-mix()` of var()s are fine.
def colour_literals(css: str) -> list[str]:
    no_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found = re.findall(r"#[0-9A-Fa-f]{3,8}(?![\w-])", no_comments)
    found += re.findall(r"\b(?:rgba?|hsla?|hwb|oklch|oklab|lab|lch|color)\(", no_comments)
    for value in re.findall(r":\s*([^;{}]*)[;}]", no_comments):
        # A token's name is never a colour: var(--mf-color-palette-gold-400).
        found += _NAMED.findall(re.sub(r"--[\w-]+", "", value))
    return found


def test_the_colour_check_finds_a_colour() -> None:
    assert colour_literals("a { color: #FF7A1F; }") == ["#FF7A1F"]
    assert colour_literals("a { box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.2); }") == ["rgba("]
    assert colour_literals("a { color: white; }") == ["white"]
    assert colour_literals("a { color: red; }") == ["red"]
    assert colour_literals("a { border: 1px solid RebeccaPurple; }") == ["RebeccaPurple"]
    assert colour_literals("a { color: var(--mf-color-palette-gold-400); }") == []
    assert colour_literals("a { color: var(--mf-color-text); } /* #FFF */") == []
    assert colour_literals("#main { color: currentColor; }") == []


def test_no_colour_is_written_outside_themes() -> None:
    roots = [ROOT / "kernel" / "web", ROOT / "harness" / "web", ROOT / "modules"]
    found = {}
    for root in roots:
        for path in root.rglob("*.css"):
            if {"node_modules", "dist"} & set(path.parts):
                continue
            if literals := colour_literals(path.read_text("utf-8")):
                found[str(path.relative_to(ROOT))] = literals
    assert found == {}


def _ci_filter(name: str) -> re.Pattern[str]:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")
    match = re.search(rf"^\s*{name}=\$\(any '([^']+)'\)", workflow, re.MULTILINE)
    assert match, f"ci.yml has no {name} filter"
    return re.compile(match.group(1))


@pytest.mark.parametrize("job", ["python", "web"])
def test_a_change_to_a_theme_runs_its_tests_and_the_build(job: str) -> None:
    # The Python job runs these tests and tools.themes --check; the Web job builds the CSS in.
    assert _ci_filter(job).search("themes/vibrant-mindz/tokens.json")
