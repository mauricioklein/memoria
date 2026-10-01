# Local RAG index

Memoria ships with an on-demand local retrieval index for each project.

Goals:

- local-first
- no daemon
- stdlib-only default implementation
- disposable generated state
- project isolation

## Storage

Each project keeps its generated index under:

```txt
projects/<slug>/.memoria/rag.sqlite
```

This is cache, not source of truth. Delete it any time and rebuild.

## What gets indexed

By default:

- `README.md`
- `resources/**/*.md`
- `log.jsonl`

By default, these are excluded:

- `inventory.md`
- `.memoria/**`
- binary files
- files larger than `rag.maxFileBytes`

## Commands

Build from scratch:

```bash
bin/memoria rag rebuild --project demo
```

Refresh changed files only:

```bash
bin/memoria rag update --project demo
```

Search:

```bash
bin/memoria rag search --project demo --query "what did we decide about sync sources?"
```

Agent-friendly context output:

```bash
bin/memoria rag search --project demo --query "latest blockers" --format context --limit 8
```

Related files from the local graph:

```bash
bin/memoria rag related --project demo --path resources/notes/2026-06-13-review.md
```

Health and size checks:

```bash
bin/memoria rag stats --project demo
bin/memoria rag doctor --project demo
```

## How search works

The default backend combines:

1. SQLite FTS5 lexical search
2. a tiny hashed sparse-vector reranker
3. metadata matches from titles, tags, summaries, and headings
4. a file graph for light related-file boosting

No external model download is required.

## Agent workflow

Recommended retrieval-first flow:

Important: run these commands from the Memoria repo root. `bin/memoria` is not relative to `projects/<slug>/`.

1. Run `bin/memoria rag search --project <slug> --query "..." --format context --limit 8`
2. Read only the returned files/snippets first.
3. If needed, expand with `bin/memoria rag related --project <slug> --path <file>`.
4. Fall back to broader scanning only when search is weak or empty.

## Config

`memoria.config.yml` can override the `rag` block, including:

- include/exclude globs
- chunk sizes
- candidate limits
- sparse embedding dimensions
- DB directory/file names

Defaults live in code, so older configs still work.
