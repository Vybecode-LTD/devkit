# 0017: Retire the claude.ai Spec doc

- **Date:** 2026-11-13
- **Status:** Applied
- **Context:** Since K0, `SPEC.md` has been the source of truth, and the claude.ai doc "AI DevKit Spec v0.1" was the owner's reading copy, synced by hand after every spec change. The audit changed sections 4 to 7, 12, 14, 15 and 16 and left the doc behind. The sync needs a claude.ai connection that a coding agent on the owner's machine may not have, and the owner is moving the build to Claude Code, which reads `SPEC.md` directly.
- **Decision:** The doc is retired. On 2026-11-13 it was titled "AI DevKit Spec v0.1 (retired)" and given a notice under the title: frozen as of 2026-11-12, the current spec is `SPEC.md` on GitHub. Nothing syncs into it any more. A spec change still needs a decision record and a change-log line in the same PR, and the owner is still told which sections changed, so he knows what to read.
- **Alternatives:** Keep syncing the doc by hand, from a claude.ai chat when the connection works. Rejected: a second copy that drifts whenever a sync is missed, with nothing to catch it. GitHub renders `SPEC.md` well enough to read, phones included.
- **Consequences:** CLAUDE.md, AGENTS.md, KICKOFF.md and the `devkit-module-extractor` skill stop asking for doc syncs. Decisions 0013, 0014 and 0016 still say what the doc needed at the time; this record supersedes those lines. The claude.ai docs for the auth contract and the Vibrant Mindz module plan are untouched by this decision.
- **See:** SPEC.md (header and change log); decision 0016
