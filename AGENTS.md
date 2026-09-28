# Codex instructions — Empirik (ATOM)

This file is a compatibility bridge. Claude remains the canonical owner of the
shared instructions and memory; do not edit Claude configuration as part of
Codex maintenance.

At the start of every Codex session in this workspace:

1. Read `CLAUDE.md` in this directory completely and follow its semantic intent
   as project instructions.
2. Read `MEMORY.md` from this project's memory directory before using project
   history or making project-specific recommendations. The directory is
   `%USERPROFILE%\.claude\projects\<slug>\memory\`, where `<slug>` is the
   current working directory path with separators and punctuation replaced by
   dashes; on this machine it is `C--dev-polistata`. In a POSIX shell the same
   path reads `~/.claude/projects/<slug>/memory/`.
   If the directory is missing or empty, say so in your first message of the
   session and continue without project history.
3. Load narrower memory files from that same `memory` directory only when their
   topic matches the current task.

Note for Claude: this file is not loaded automatically. `CLAUDE.md` in this
directory carries no `@AGENTS.md` import line, so everything here reaches Codex
only. Anything Claude must also obey belongs in `CLAUDE.md`.

Compatibility rules:

- Map Claude-specific tool names to the closest available Codex capability.
- A Claude-only command, hook, model name, plugin namespace, or UI action is not
  an instruction to invent that capability. Use the Codex equivalent when one
  exists; otherwise state the limitation and continue safely.
- Codex system, developer, sandbox, approval, and skill instructions take
  precedence over imported Claude guidance.
- Keep all Claude files and directories unchanged unless the user explicitly
  asks to modify the Claude environment itself.
