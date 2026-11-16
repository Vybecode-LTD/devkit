# Progress ledger

The visual progress ledger: https://claude.ai/artifact/48auLkb7Ajmyn2SNAni9rm (a Claude Data artifact, private to the owner until shared from its Share menu).

| File | What |
| --- | --- |
| `index.html` | The ledger's page, stored in the artifact as `files/index.html` |
| `rows.json` | Every step as one row, made by `python -m tools.progress` from `docs/progress.json`; never edit it by hand |

The repo's `docs/PROGRESS.md` and this ledger are made from the same `docs/progress.json`, so they can't disagree. `tests/test_progress.py` fails when either view is stale.

## Republishing (every session end, and after a status changes)

1. Update `docs/progress.json` and run `python -m tools.progress` (in the PR that changes the status).
2. Upload `rows.json` to the ledger: the `Artifact` tool, `url` the ledger, `file_path` this `rows.json`, `asset: true`. It answers with a new `/_blob/<id>`.
3. Point the ledger's `steps` dataset at it: `ArtifactData` `update` on collection `datasets`, doc `steps`, pinned to its version, with `source.url` the new `/_blob/<id>` and `updated` `{at, by}` saying when and from which `main`.
4. Read `data/users/me` `check` on the ledger: `passed` means the page drew the new rows.
5. Delete the previous asset once nothing points at it.

The page itself changes only when this `index.html` does: write it to `files/index.html` (pinned to its version), then read `check` the same way. Its milestone labels ("DevKit v1.0", "Everything") are text in the page, so renaming a milestone in `docs/progress.json` means changing them here too.
