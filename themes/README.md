# Themes

A theme is a token set: color, type, spacing, radius and motion, authored once in `tokens.json` and generated as `tokens.css` (and later as Avalonia resources). Modules use only `var(--dk-*)` tokens; Tailwind v4's theme maps to the same tokens.

Planned first themes (phase K4):

| Theme | Source | Notes |
| --- | --- | --- |
| `machined-light` | `C:\DEV\machined-light-design-system` | Light, warm graphite, Ember accent; the default |
| `depth` | `C:\DEV\depth-design-system` | Dark; already generates React, Avalonia, JUCE and Rails bindings from one token source, the path to desktop later |

Copy tokens in, never whole component libraries: modules use the kernel UI kit.
