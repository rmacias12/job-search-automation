# CLAUDE.md

@AGENTS.md

All project guidance lives in **AGENTS.md** (imported above): architecture, commands, data model,
scoring, credentials, safety rules, and current pipeline state. It is the canonical, agent-agnostic
document — when behavior changes, update **AGENTS.md**, not this file.

## Claude Code specifics

- Prefer `venv/bin/python ...` in commands; do not assume an activated shell in non-interactive sessions.
- Run the suite before committing behavior changes:
  `PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m unittest discover -s tests -v` (54 tests).
- Honor AGENTS.md § Safety Rules strictly — especially: no mock data into the real DB, back up
  before destructive DB work, never print resolved credentials or raw HTTP error text.
- Keep this file limited to Claude-specific notes; duplicate nothing from AGENTS.md.
