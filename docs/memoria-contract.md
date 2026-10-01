# Memoria contract

Memoria is a multi-project knowledge workspace. Each project is a self-contained "brain": knowledge base, notes, decisions, conversations, contacts, progress tracker, and an append-only activity log.

## Repository layout

```txt
.
├── docs/                        # canonical docs
├── bin/memoria                  # deterministic CLI
├── connectors/                  # connector registry
├── projects/
│   ├── _template/               # scaffold for new projects
│   └── <project-slug>/          # one folder per project — fully self-contained
│       ├── README.md            # name, owner, status, goal, links, glossary
│       ├── inventory.md         # generated resource catalog
│       ├── log.jsonl            # append-only activity log
│       ├── .memoria/            # generated local cache (for example rag.sqlite)
│       └── resources/           # all content lives here; categories are folders
│           ├── knowledge-base/
│           ├── notes/
│           ├── decisions/
│           ├── conversations/
│           ├── tracker/
│           ├── contacts/
│           └── <any-category>/
└── memoria.config.yml
```

Categories are folders, not enums.

## Projects are isolated

Each project lives under `projects/<slug>/` and owns its own resources, inventory, log, and generated local cache. Projects do not share state.

Generated files under `projects/<slug>/.memoria/` are disposable cache, not canonical data. Deleting them must never lose project knowledge; the CLI can rebuild them.

## Resource frontmatter

Every file under `resources/` carries YAML frontmatter:

```yaml
---
title: ...
type: knowledge-base | note | decision | conversation | meeting | tracker | ...
source: google-doc | notion | slack | email | manual | local-file | web | ...
source-ref: <url, path, id, or "manual">
source-id: <optional stable upstream id>
connector: <optional connector id>
source-created: <optional original creation date or timestamp>
source-updated: <optional source-side updated timestamp>
source-cursor: <optional tail-forward cursor>
tags: [tag1, tag2, ...]
created: YYYY-MM-DD
updated: YYYY-MM-DD
summary: One-line summary used by the inventory.
---
```

Notes:

- `type`, `source`, `connector`, and `tags` are free-form strings.
- `created` and `updated` are ISO dates.
- `source-ref` is required for any non-manual resource.
- `source-id` and `connector` are optional but recommended for refreshable resources.
- `source-updated` captures the upstream freshness signal.
- `source-cursor` is only for tail-forward feeds.

## Inventory (`inventory.md`)

A generated markdown table listing every resource in a project.

Columns:

| path | type | source | tags | summary | updated |

Frontmatter is the source of truth. `inventory.md` is rebuilt by `bin/memoria rebuild-inventory`.

## Log (`log.jsonl`)

Append-only. One JSON object per line.

Example:

```json
{"ts":"2026-05-23T14:02:00Z","kind":"resource.added","resource":"resources/notes/2026-05-23-design-review.md","summary":"Captured design review notes from Notion page","tags":["design-review","v2"]}
```

Common `kind` values:

- `resource.added`
- `resource.updated`
- `resource.removed`
- `status.changed`
- `decision.logged`
- `meeting.recorded`
- `fetch.completed`
- `tracker.updated`
- `note`

### Logging rule

Always record meaningful changes automatically and without asking.

Never edit past log entries. If you need to correct one, append a new entry with `corrects`.

## Deterministic engine

The stable mechanical layer is `bin/memoria`.

Primary commands:

- `bin/memoria init`
- `bin/memoria new-resource`
- `bin/memoria update-resource`
- `bin/memoria log`
- `bin/memoria rebuild-inventory`
- `bin/memoria status`
- `bin/memoria rag ...`
- `bin/memoria connector ...`
- `bin/memoria setup connector ...`

## Connectors

Source/tool mechanics live in `connectors/`.

A connector defines things like:

- source id
- supported reference patterns
- auth check and setup notes
- discover command
- fetch command
- refresh metadata check
- normalization strategy
- identity / cursor tracking
- metadata mapping

See [`docs/connectors.md`](./connectors.md).

## Conventions

- Dates are ISO `YYYY-MM-DD`.
- Filenames are kebab-case.
- Dated files use `YYYY-MM-DD-<slug>.md`.
- Project slugs are kebab-case, lowercase, no spaces.
- Frontmatter is mandatory on every file under `resources/`.
- One project per concern.
