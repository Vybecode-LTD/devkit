# devkit CLI

Built in phase K5. Commands (SPEC.md sections 12 and 13):

| Command | Does |
| --- | --- |
| `devkit new <site> --recipe <name>` | Copies `templates/site/`, the kernel and the recipe's modules; writes the lock file |
| `devkit add <id>` | Checks requires and conflicts, copies the module, regenerates the registries, appends env vars, records hashes, runs its migrations and tests |
| `devkit remove <id> [--drop-data]` | Switches it off, offers an export, removes code and registry entries; keeps tables unless told |
| `devkit check` | Validates manifests, lists edited copies, modules behind their latest version and open advisories; non-zero on a high-severity advisory |
| `devkit diff <id>` | Three-way: the copy in the lock file, the site's files, the latest DevKit version |
| `devkit upgrade <id>` | Applies an upgrade when the copy is unedited; otherwise writes a patch |
| `devkit catalog` | Regenerates `catalog.json` from every manifest |
| `devkit create-owner` | Creates a site's first owner account |

Written in Python (standard library plus `jsonschema`), run as `python -m devkit`.
