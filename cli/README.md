# mechframe CLI

Built in phase K5 (the contract: `dev plans/contracts/k5-cli-and-site-template.md`; decision 0047). The CLI is written in Python, using the standard library plus `jsonschema`. It copies from, and checks against, **the MechFrame checkout its own code sits in**, and fetches nothing.

From the repo root:

```powershell
python -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt   # the pinned, audited tools
python -m pip install --no-deps --no-build-isolation -e .   # once: the CLI as mechframe and mf, from this checkout; fetches nothing
mechframe check --site C:\path\to\site
```

Without installing it, `python -m mechframe` works with `cli` on the path: `$env:PYTHONPATH = "cli"`. Where TeX's Metafont `mf` comes first on the PATH, `mechframe` always works (decision 0034).

| Command | Does | Built |
| --- | --- | --- |
| `mechframe catalog [--check]` | Writes `catalog.json` from every built module's manifest. `--check` only says whether it's current | #91 |
| `mechframe check [--site <dir>] [--json]` | Validates the lock and the copied manifests. Lists edited, missing and added files in copied folders, copies behind this checkout, and open advisories. Exits 2 on an invalid lock or manifest, 1 on an open high or critical advisory, 0 otherwise | #91 |
| `mechframe new <dir> [--name <site name>] [--theme <name>]` | Makes a kernel-only site in an empty folder: copies `templates/site/` (without its build output) and this checkout's pinned requirements, writes the name and theme in, copies the theme's `tokens.css` and the kernel, and writes the lock. Refuses a folder that isn't empty, an unknown theme and a name that isn't one line, before writing anything; a failure half-way leaves nothing behind. Prints the next commands | #92 |
| `mechframe new --recipe <id>` | The recipe's modules too, with `add` | K5, #94 |
| `mechframe add <id>` | Checks requires and conflicts, copies the module, regenerates the registries, appends env vars, records hashes; prints its migration and test commands | K5, #94 |
| `mechframe remove <id>` | Refuses while another module requires it; removes its code, registry and lock entries; keeps its tables | K5, #94 |
| `mechframe create-owner <email>` | Runs the site's `python -m app.owner <email>`, which prints a one-time link to set a password | K5, #95 |
| `mechframe diff <id>`, `upgrade <id>` | Three-way against the copy in the lock, the site's files and this checkout | When a module ships its second version |

The site's layout, the lock's hashes and the advisories' entries: SPEC.md sections 4 and 13. The template itself: `templates/README.md`. The code is in `cli/mechframe/`, and its tests are in `cli/tests/`.
