# Vibrant Mindz

The Vibrant Mindz site's dark theme. It holds every value the working canvas's boards draw, exactly as drawn: the owner's rule (2026-11-17) is that the built site, admin included, looks exactly like the canvas.

Copied on 2026-11-18, at K4, from VM Website `design/theme/vibrant-mindz/tokens.json`, where the census (`census.py`) and the admin shell's part list (`shell_slots.py`, `shell-slots.md`) still live, since they read that project's boards. The kernel's colour roles already had the kernel's names there. The kernel's other names were added here as aliases of the theme's own values, so no value changed:
- `font.display`, `font.text` and `font.mono`, where `font.mono` is the code face (`typography.fontFamily.code`), not Doto (contract change 5).
- `type.page-title` (28px 600), `type.section-title` (16px 600), `type.body` (15px), `type.small` (14px) and `type.meta` (13px 500), as the admin boards draw them.
- `radius.control` (10px), `radius.card` (16px) and `radius.pill` (full).
- `motion.fast` and `motion.base`.

The generator moved to `tools/themes.py`. Its prefix is now `--mf-` (it was `--dk-`), and the tokens sit on `[data-theme="vibrant-mindz"]` alone. The theme's own checks moved to `tests/test_theme_vibrant_mindz.py`: its 65 contrast pairs, aliases, alphas and shadows.

| File | What |
| --- | --- |
| `tokens.json` | The source. Edit only this file, here, and carry a change back to VM Website's copy (or the reverse) |
| `tokens.css`, `tailwind.css` | Made by `python -m tools.themes` |

**Still to do in VM Website** (that project's session, not this repo's): point `census.py` and `shell_slots.py --check` at this copy and keep them green. Its `GROUPS` gains `font` and `type`, both of which are aliases only. Then retire the copy there, or keep the two in step.
