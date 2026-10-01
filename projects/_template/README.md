---
project: <project-slug>
title: <Project Name>
owner: <owner>
status: <status>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
---

# <Project Name>

<One-paragraph description of what this project is and why it exists.>

## Goal

<What "done" looks like for this project.>

## Status

<Current state — e.g. discovery, planning, in progress, blocked, on hold, done.>

## Key links

- <external-system>: <url>
- <external-system>: <url>

## People

- **Owner:** <name>
- **Collaborators:** <names>
- **Stakeholders:** <names>

## Glossary

- **<term>:** <definition>

## Retrieval workflow

When you need project context, start with the local RAG index instead of broad scanning:

1. `bin/memoria rag rebuild --project <slug>` after major content changes or right after setup
2. `bin/memoria rag search --project <slug> --query "..." --format context --limit 8`
3. Read the returned snippets/files first
4. Expand with `bin/memoria rag related --project <slug> --path <file>` if needed
5. Fall back to broad file scanning only when retrieval is weak

You can also scaffold harness instructions with:

- `bin/memoria setup agent --harness pi`
- `bin/memoria setup agent --harness claude`

## Resource categories

Categories live as folders under `resources/`. Common starters (none are required):

- `knowledge-base/` — durable reference material
- `notes/` — meeting notes, async write-ups, observations
- `decisions/` — decisions made, with context and tradeoffs
- `conversations/` — captured threads (Slack, email, chats)
- `tracker/` — progress, blockers, deadlines, achievements, todos
- `contacts/` — people and teams to coordinate with
- `contributions/` — per-person participation notes (`<person>.md`), report-ready for performance reviews

Add new categories as folders on demand — nothing here is hardcoded.

## See also

- [`inventory.md`](./inventory.md) — generated catalog of all resources
- [`log.jsonl`](./log.jsonl) — append-only activity log
- [`../../docs/rag.md`](../../docs/rag.md) — local retrieval commands and agent workflow
