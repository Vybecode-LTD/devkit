# The CLI's fixtures

Modules and a recipe that `cli/tests/` copies into a small checkout, since no real module is built yet (the K5 contract §4 item 4). They aren't MechFrame's modules: the harness and the catalog never see them.

| Fixture | What it tests |
| --- | --- |
| `modules/fixture-notes/` | Two settings (one required), a migration and a web binding |
| `modules/fixture-pins/` | `requires` (`fixture-notes ^0.1`), `conflicts` (`fixture-rival`), one setting, no migrations |
| `modules/fixture-rival/` | A backend alone: no settings, migrations or web binding |
| `recipes/fixture-notebook.json` | `new --recipe`: its modules out of order, its own theme and a setting |
