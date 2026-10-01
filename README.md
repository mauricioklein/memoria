# Memoria

[Test workflow](.github/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![stdlib only](https://img.shields.io/badge/deps-stdlib%20only-brightgreen.svg)]()

**A local-first memory layer for projects and AI agents.**

Memoria turns scattered project knowledge — notes, decisions, meetings, links, imported files, conversations, trackers, and external sources — into a durable, searchable, project-scoped workspace.

It is designed for people who work with AI agents and want those agents to start from the project’s actual memory instead of repeatedly rediscovering context from scratch.

---

## Why Memoria?

Most projects have knowledge spread across docs, chats, tickets, meeting notes, decisions, and local files. AI agents can help, but they often lack durable context: they either miss important history or waste time scanning everything.

Memoria gives each project a **local, structured, searchable brain**:

- important context lives in versioned Markdown files
- every project has its own isolated knowledge workspace
- imported resources keep source metadata and refresh hints
- the local retrieval index can answer natural-language questions
- agents can use retrieval first, then read only the files that matter
- everything is transparent, portable, and works offline

Use Memoria when you want a project memory that is:

- **Local-first** — no hosted service required
- **Agent-friendly** — built for retrieval-first AI workflows
- **Human-readable** — Markdown, JSONL, and simple folders
- **Auditable** — append-only logs and source metadata
- **Extensible** — register connectors for your own systems
- **Disposable-cache safe** — indexes can be rebuilt from source files any time

---

## What Memoria does

### Capture project knowledge

Memoria organizes knowledge into project folders. Each project can contain:

- knowledge-base articles
- notes and meeting summaries
- decisions and tradeoffs
- conversations from chat/email threads
- tracker updates, blockers, deadlines, todos, and achievements
- contacts and stakeholder context
- per-person contribution notes
- imported files from external systems

Each resource is stored as Markdown with structured frontmatter, so it is easy to read, diff, review, and search.

### Import and track external material

Memoria can record resources from manual notes, local files, URLs, and external systems. Imported resources carry source metadata such as:

- source type
- source reference URL/path/id
- connector id
- upstream stable id
- source-side updated timestamp
- refresh cursor, when applicable
- tags and summary

This makes imported knowledge traceable and refreshable.

### Index everything locally

Each project gets its own local retrieval index. By default Memoria indexes:

- the project README
- all Markdown resources
- the append-only activity log

The index is stored under the project’s `.memoria/` folder and is disposable cache. Delete it whenever you want; Memoria can rebuild it from the project files.

### Ask natural-language questions

Once indexed, you can ask questions like:

- “What did we decide about retry behavior?”
- “Show me the latest blockers.”
- “Which docs mention the conference venue?”
- “What context should I read before changing sync sources?”
- “What files are related to this decision?”

Search results include paths, line ranges, snippets, scores, and “why” signals so both humans and agents can understand why something was returned.

### Explore related files

Memoria builds a lightweight file graph from:

- Markdown links
- path mentions
- shared source references
- shared connectors
- shared tags

That graph helps users and agents expand from one relevant file to nearby context without scanning the whole project.

### Register new connectors

Connectors describe how Memoria recognizes, fetches, refreshes, and normalizes external sources. Built-in connector definitions include examples for:

- GitHub
- Notion
- Slack
- Gmail
- Google Docs
- Google Sheets
- Jira
- local files
- web pages
- internal wiki-style systems

You can register your own connector for company-specific systems without changing Memoria’s core contract.

### Integrate with AI agents

Memoria can scaffold retrieval-first instructions for agent harnesses including:

- Pi
- Claude Code
- Codex
- OpenCode
- generic agents

The goal is simple: when an agent needs project context, it should query Memoria first, read the returned snippets/files, optionally expand through related files, and only then fall back to broad scanning.

---

## How to use Memoria

Memoria is easiest to use through an AI agent or assistant. The agent handles the mechanical details while Memoria provides a deterministic local engine underneath.

### 1. Create a project memory

Tell your agent:

> Create a Memoria project for the payments migration. Owner is Ana. Goal is to migrate retry handling safely before Q3.

Memoria will scaffold a self-contained project under `projects/<slug>/` with a README, inventory, activity log, and resource folders.

### 2. Capture notes, decisions, and updates

Tell your agent things like:

> Record that we decided to keep retries idempotent and store the reasoning as a decision.

> Add today’s architecture review notes to the project.

> Log this blocker: the sandbox provider still has inconsistent webhook payloads.

Memoria records the resource, updates frontmatter, appends the activity log, and refreshes the inventory.

### 3. Import files and external references

You can ask:

> Import this local file into the payments migration project and tag it as onboarding.

> Capture this GitHub issue as project context.

> Match this Google Doc URL against the connector registry and store it as a resource.

Imported resources keep source metadata so future refresh workflows know where the content came from.

### 4. Keep project memory searchable

When project content changes, ask:

> Refresh the Memoria index for this project.

or:

> Rebuild the project memory index from scratch.

The index remains local to the project and can be rebuilt at any time.

### 5. Ask questions

Ask your agent:

> What did we decide about sync-source refresh behavior?

> Find the most relevant context about webhook retries.

> What are the latest blockers and who owns them?

> Before making this change, search Memoria for related decisions and notes.

The agent should use Memoria retrieval first, then read the returned files/snippets before doing broader exploration.

### 6. Expand from one file to related context

After finding a relevant decision or note, ask:

> Show files related to that decision.

> Expand the context around this note.

Memoria uses the local file graph to surface related project material.

### 7. Add a new connector when your source is not built in

Tell your agent:

> Register our internal wiki as a Memoria connector. It should recognize URLs under `https://wiki.example.com/pages/...` and fetch Markdown through our existing CLI.

Memoria can scaffold a connector definition that describes reference matching, fetch behavior, refresh behavior, normalization, and tracking metadata.

---

## A quick example

User request:

> What did we decide about the conference venue?

Memoria-backed agent workflow:

1. Search the project’s local index for the question.
2. Read the returned snippets and files.
3. Expand to related files if the first results are not enough.
4. Answer with source-backed context.

Example result shape:

```txt
resources/decisions/2026-06-14-conference-venue.md:1-8
score: 0.84
why: fts, semantic, metadata: conference, venue
snippet: We decided to host the conference at Riverside Hall because the room fits the workshop format...
```

The important part is not the command itself. The important part is the behavior: **retrieval first, source-backed answers, minimal broad scanning**.

---

## For agent authors and technical users

Memoria’s user-facing workflow is agent-first, but the stable mechanical layer is a deterministic CLI. Agent adapters call this CLI behind the scenes.

### Project operations

```bash
# Create a project
bin/memoria init --project demo --title "Demo" --owner "You"

# Add a resource
bin/memoria new-resource --project demo \
  --category decisions \
  --title "Sync source strategy" \
  --type decision \
  --source manual \
  --summary "Use sqlite-backed local RAG"

# Update a resource
bin/memoria update-resource --project demo \
  --path resources/decisions/2026-06-14-sync-source-strategy.md \
  --change "Clarified refresh tradeoffs"

# Render project status
bin/memoria status --project demo

# Rebuild the generated inventory
bin/memoria rebuild-inventory --project demo
```

### Retrieval operations

Run these from the Memoria repository root:

```bash
# Build the index from scratch
bin/memoria rag rebuild --project demo

# Incrementally refresh the index
bin/memoria rag update --project demo

# Search with human-readable output
bin/memoria rag search --project demo --query "latest blockers"

# Search with agent-friendly context output
bin/memoria rag search --project demo --query "latest blockers" --format context --limit 8

# Return unique matching paths only
bin/memoria rag search --project demo --query "retry policy" --paths-only

# Expand from one file through the local graph
bin/memoria rag related --project demo --path resources/decisions/2026-06-14-sync-source-strategy.md

# Inspect index health
bin/memoria rag stats --project demo
bin/memoria rag doctor --project demo
```

### Connector operations

```bash
# List connector definitions
bin/memoria connector list

# Inspect one connector
bin/memoria connector show --id google-doc

# Match a URL/ref against the registry
bin/memoria connector match --ref "https://github.com/OWNER/REPO/issues/123"

# Scaffold a new connector
bin/memoria setup connector --id internal-wiki
```

### Agent adapter setup

```bash
bin/memoria setup agent --harness pi
bin/memoria setup agent --harness claude
bin/memoria setup agent --harness codex
bin/memoria setup agent --harness opencode
bin/memoria setup agent --harness generic
```

Adapters generate harness-native instruction files that tell the agent to use retrieval first.

---

## How it works

### Workspace model

Each project is isolated under `projects/<slug>/`:

```txt
projects/<slug>/
├── README.md          # project overview, goal, status, people, glossary
├── inventory.md       # generated catalog of resources
├── log.jsonl          # append-only activity log
├── .memoria/          # generated cache, including rag.sqlite
└── resources/
    ├── knowledge-base/
    ├── notes/
    ├── decisions/
    ├── conversations/
    ├── tracker/
    ├── contacts/
    └── contributions/
```

Categories are folders, not hardcoded enums. You can add new categories whenever a project needs them.

### Resource format

Resources are Markdown files with frontmatter:

```yaml
---
title: Sync source strategy
type: decision
source: manual
source-ref: manual
tags: [sync, rag, sqlite]
created: 2026-06-14
updated: 2026-06-14
summary: Use sqlite-backed local RAG
---
```

This keeps the knowledge base easy to inspect, diff, review, and version control.

### Retrieval engine

The default local retrieval backend combines:

1. SQLite FTS5 lexical search
2. hashed sparse-vector reranking
3. metadata matches from titles, tags, summaries, and headings
4. lightweight graph boosts from related files

No external embedding model or hosted vector database is required.

### Generated state

`projects/<slug>/.memoria/` contains generated local cache such as `rag.sqlite`. It is not source of truth and can be deleted or rebuilt safely.

### Configuration

`memoria.config.yml` controls RAG defaults such as include/exclude globs, chunk sizes, candidate limits, and sparse embedding dimensions.

---

## Repository layout

```txt
.
├── adapters/                   # agent harness templates
├── bin/memoria                 # deterministic CLI engine
├── connectors/                 # connector registry
├── docs/                       # canonical design docs
├── lib/memoria_rag.py          # local retrieval engine
├── projects/                   # project memories
├── tests/                      # unittest suite
└── memoria.config.yml          # default configuration
```

---

## Documentation

- [`docs/memoria-contract.md`](docs/memoria-contract.md) — workspace contract and resource conventions
- [`docs/connectors.md`](docs/connectors.md) — connector model, schema, and registry
- [`docs/rag.md`](docs/rag.md) — local retrieval index and agent workflow

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

Run tests with:

```bash
python -m unittest tests.test_rag
```

---

## License

MIT — see [`LICENSE`](LICENSE).
