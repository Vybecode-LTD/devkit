# Vibrant Mindz

The Vibrant Mindz site's dark theme. It holds every value the working canvas's boards draw, exactly as drawn: the owner's rule (2026-11-17) is that the built site, admin included, looks exactly like the canvas.

Copied on 2026-11-18, at K4, from VM Website `design/theme/vibrant-mindz/tokens.json`, where the census (`census.py`) and the admin shell's part list (`shell_slots.py`, `shell-slots.md`) still live, since they read that project's boards. The kernel's colour roles already had the kernel's names there. The kernel's other names were added here as aliases of the theme's own values, so no value changed:
- `font.display`, `font.text` and `font.mono`, where `font.mono` is the code face (`typography.fontFamily.code`), not Doto (contract change 5).
- `type.page-title` (28px 600), `type.section-title` (16px 600), `type.body` (15px), `type.small` (14px) and `type.meta` (13px 500), as the admin boards draw them.
- `radius.control` (10px), `radius.card` (16px) and `radius.pill` (full).
- `motion.fast` and `motion.base`.

K4.4 (the UI kit) added three things, so VM Website's copy is now behind this one (contract change 15):
- **One new value**, `color.palette.line-3` `#5C6584`: `line-2` taken 41% of the way to `muted`, the darkest step of that blend at 3:1 on the canvas, panels and rail. It's `color.border-control`, the edge of a field, a select and a switch's track, which the boards draw in `line-2` at 1.5:1 (WCAG 1.4.11 asks 3:1).
- **Aliases of existing values:** `color.success-tint`, `warning-tint`, `danger-tint` and `neutral-tint` are the boards' 12% pill tints (`color.alpha.mint.12` and the rest).
- **The admin's focus shadows** (`shadow.focus-ring` and its forms) were already here; they're now required of every theme.

The generator moved to `tools/themes.py`. Its prefix is now `--mf-` (it was `--dk-`), and the tokens sit on `[data-theme="vibrant-mindz"]` alone. The theme's own checks moved to `tests/test_theme_vibrant_mindz.py`: its 65 contrast pairs, aliases, alphas and shadows.

| File | What |
| --- | --- |
| `tokens.json` | The source. Edit only this file, here, and carry a change back to VM Website's copy (or the reverse) |
| `tokens.css`, `tailwind.css` | Made by `python -m tools.themes` |

**Still to do in VM Website** (that project's session, not this repo's): point `census.py` and `shell_slots.py --check` at this copy and keep them green. Its `GROUPS` gains `font` and `type`, both of which are aliases only. Then retire the copy there, or keep the two in step.
