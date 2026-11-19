# Machined Light

The kernel's default theme: light, warm graphite with an Ember accent, from `C:\DEV\machined-light-design-system` (`tokens/tokens.json` and `src/styles/tokens.css`). Its palette, type scale, spacing, radii, shadows and motion are carried over as they are. Its roles are put on the kernel's names. Where one of the system's own roles fails AA as text, the kernel's role takes the next shade in the palette that passes.

| File | What |
| --- | --- |
| `tokens.json` | The source. Edit only this file |
| `tokens.css`, `tailwind.css` | Made by `python -m tools.themes` |

## Where the kernel's role differs from Machined Light's

| Kernel token | Here | Machined Light's own | Why |
| --- | --- | --- | --- |
| `color.text-strong` | neutral-900 `#191817` | `--color-text` | The kernel's highest contrast is Machined Light's body text |
| `color.text` | neutral-800 `#2C2B28` | `--color-text-strong` | The kernel's secondary text |
| `color.text-muted` | neutral-700 `#454440`, 8.2:1 | `--color-text-muted` is neutral-500 | neutral-500 is 3.4:1 on the canvas |
| `color.text-subtle` | neutral-600 `#5F5E58`, 5.5:1 | `--color-text-subtle` is neutral-400 | neutral-400 is under 3:1 |
| `color.border` | neutral-200 `#D8D8D4` | (none) | Its cards take their edge from a shadow; this is for dividers and rows |
| `color.border-strong` | neutral-300 `#C4C4BF` | `--color-border` | The control border (contract change 5) |
| `color.accent` | ember-600 `#C93A0C` | `--accent` is ember-500 | White on ember-500 is 4.0:1, under 4.5:1; on ember-600 it's 5.1:1 |
| `color.accent-hover` | ember-700 `#A2320F` | ember-600 | One step darker, as before |
| `color.link`, `color.link-hover` | ember-700, ember-900 | ember-700 is "accent on light text" | |
| `color.success`, `warning`, `danger` | success-700 `#007948`, warning-700 `#9A5900`, danger-700 `#BF3536` | the 500s, under 4.5:1 as text (2.9, 2.9 and 4.0:1) | Derived on each signal's own hue in OKLCH (L 0.500, 0.525, 0.540), the lightest that's 4.5:1 on the canvas |
| `color.rail` | neutral-50, the card surface | (none) | Machined Light has no sidebar |
| `font.display` | the sans | (none) | It has one sans face |
| `type.page-title` … `type.meta` | h3, h4, base, sm, xs | | Its own scale |
| `radius.control`, `card`, `pill` | md 12px, lg 16px, full | | |
| `layout.sidebar` | 256px | (none) | The kernel's width |

`color.focus` is its own ember-500 (3.4:1 on the canvas, past the 3:1 a focus ring needs), and its focus shadow is its own.

`color.border-strong` is a control's edge as Machined Light draws it, far under 3:1 on its grounds, since its controls also take their edge from a well and a shadow. A control's boundary as a whole must reach 3:1 (WCAG 1.4.11): the UI kit's controls are checked for that when they're built (K4.4), not this token alone. Vibrant Mindz's boards draw theirs the same way.

The owner may want other shades for these (the handoff asks). The contrast tests in `tests/test_themes.py` hold whatever is chosen to AA.
