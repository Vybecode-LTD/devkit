# Themes

A theme is a token set: colour, type, spacing, radius, shadow and motion. It's written once in its folder's `tokens.json` (W3C design-tokens format). `python -m tools.themes` makes its `tokens.css` and `tailwind.css` from it, and `--check` reports them stale (`tests/test_themes.py` runs it).

Every token is `--mf-<path>` in kebab case: `color.text-strong` becomes `--mf-color-text-strong`, `typography.fontFamily.display` becomes `--mf-typography-font-family-display`. A type role is a `font` shorthand plus its tracking: `font: var(--mf-type-body); letter-spacing: var(--mf-type-body-tracking)`.

The tokens sit on `[data-theme="<name>"]` alone, so a site names its theme on `<html data-theme="...">` in its `index.html`. Under `prefers-reduced-motion` every duration is 0s.

The kernel and the modules style themselves only with these tokens. A colour written as a hex, a colour function or one of CSS's named colours fails two checks. `tests/test_themes.py` reads the CSS in `kernel/web`, `harness/web` and `modules/`, and ESLint reads the TypeScript, tests aside.

| Theme | Source | Notes |
| --- | --- | --- |
| `machined-light` | `C:\DEV\machined-light-design-system` | Light, warm graphite, Ember accent; the kernel's default. Its README says where a role takes another shade than the system's own |
| `vibrant-mindz` | VM Website `design/theme/vibrant-mindz` | The Vibrant Mindz site's dark theme: every value its boards draw, plus the kernel's names as aliases |

Depth waits until a site wants it (the owner, 2026-11-18).

## Required tokens

Every theme defines these; the kit styles itself with them. `tools/themes.py`'s `REQUIRED` is the same list, and a test holds the two equal.

| Token | What it's for |
| --- | --- |
| `color.canvas` | The page behind everything |
| `color.rail` | The admin's sidebar |
| `color.surface` | Cards, panels, the save bar |
| `color.surface-raised` | Pop-overs, menus, a nav item's hover and current state |
| `color.well` | Recessed inputs and tracks |
| `color.text` | Secondary text: an accordion's body, a stat's line, the current breadcrumb |
| `color.text-strong` | The highest contrast: titles and the admin's body text |
| `color.text-muted` | Labels, hints, table heads, inactive nav |
| `color.text-subtle` | Placeholders, the quietest text that's still text (AA on every ground) |
| `color.border` | The edges of cards, dividers, table rows, the sidebar and the top bar |
| `color.border-strong` | The edges of controls: buttons, inputs, badges, chips, the save bar |
| `color.accent` | The primary action and the admin's focus ring |
| `color.accent-hover` | The primary action, hovered |
| `color.on-accent` | Text and icons on the accent |
| `color.focus` | The focus outline on the site and the sign-in and account screens |
| `color.link` | A link |
| `color.link-hover` | A link, hovered |
| `color.success` | A success, as text or a tone |
| `color.warning` | A warning, as text or a tone |
| `color.danger` | A danger or an error, as text or a tone |
| `font.display` | The display face: big headings, the wordmark |
| `font.text` | The text face: everything else |
| `font.mono` | The code face (contract change 5) |
| `type.page-title` | A page's title |
| `type.section-title` | A card's or a section's heading |
| `type.body` | Body text |
| `type.small` | Table cells and secondary lines |
| `type.meta` | Labels, hints and counts |
| `radius.control` | Buttons and inputs |
| `radius.card` | Cards |
| `radius.pill` | Pills and chips |
| `layout.sidebar` | The admin sidebar's width |
| `motion.fast` | A quick change: colour, border, background |
| `motion.base` | An ordinary change: a transform, a panel |

**Contrast**, which `tests/test_themes.py` checks token against token:
- Every text role is at least 4.5:1 on the canvas, surface, raised surface and rail, and the two strongest are 4.5:1 on a well.
- Links are 4.5:1 on the canvas and surface, and so is the on-accent colour on the accent and its hover.
- The signals are 4.5:1 on the canvas, surface and raised surface.
- The focus colour and the accent are at least 3:1 on what they sit on.

Rendered contrast is checked by axe, in Playwright, on each page's default rendering in both themes. Text over photos or glows, and the hover and focus states, are checked by eye beside the boards as each screen is built (contract §7).

`color.border-strong` isn't held to 3:1: in both themes a control also takes its edge from a fill or a shadow. A control's boundary as a whole must reach 3:1 (WCAG 1.4.11), which the UI kit's controls are checked for when they're built (K4.4).

## Adding a theme

1. Make `themes/<name>/tokens.json`, with every required token.
2. Run `python -m tools.themes`.
3. Run `python -m pytest tests/test_themes.py`.

Copy tokens in, never whole component libraries: modules use the kernel's UI kit.
