# AGENTS

This repository uses an agent-maintained docs system. Keep docs concise, accurate, and tied to durable project intent.

## Hard guardrails

- Never commit directly to `main`.
- Always work on a branch and open a PR.
- Treat code as source of truth for behavior; docs capture structure and tradeoffs that code cannot explain alone.

## Read routing (do not read everything by default)

- Read `context/MAP.md` before changing module boundaries, ownership, or data flow.
- Read `context/DECISIONS.md` before changing behavior that may re-open an intentional tradeoff.
- Read `context/CONVENTIONS.md` while writing or refactoring code.
- At task start, run `todo list`; claim work with `todo claim <id>` before editing shared areas.

## Write triggers (event-based updates)

- Module/file added, removed, moved, or data flow changed -> update `context/MAP.md`.
- Intentional tradeoff made or reversed -> append entry to `context/DECISIONS.md`.
- New repeatable engineering rule adopted -> update `context/CONVENTIONS.md`.
- User-facing behavior, setup, or operations changed -> update `README.md`.

## What not to document

- Do not keep changelogs/worklogs in Markdown.
- Do not keep feature status checklists that duplicate code and tests.
- Do not restate obvious code behavior.

## CONVENTIONS vs DECISIONS

- `CONVENTIONS.md` contains imperative rules only, with no rationale.
- If a rule needs a "because", record that rationale in `DECISIONS.md` and keep the convention terse.

## Todos and durable decisions

- Todos are stateful records under `.pi/todos`, not scratch notes.
- Keep working context in todo bodies while a task is active.
- Before closing a todo that involved a real tradeoff, move the durable rationale to `context/DECISIONS.md`.
- Closed/done todos are not permanent archive.

## Definition of Done

A task is complete only when code, tests, and matching durable docs are all updated. If a tradeoff changed and `DECISIONS.md` was not updated, the task is not done.
