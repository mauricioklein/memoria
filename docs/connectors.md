# Connectors

Memoria uses connectors to describe how external sources are discovered, fetched, refreshed, and normalized.

## Why connectors exist

The old model hardcoded environment-specific tools in a single harness-specific reference doc. The connector model separates:

- Memoria's workspace contract
- the deterministic CLI
- source/tool mechanics
- harness-specific UX

That makes the workspace portable across Claude, Pi, Codex, OpenCode, or a plain shell.

## Registry layout

```txt
connectors/
  google-doc.yml
  google-sheet.yml
  gmail.yml
  notion.yml
  slack.yml
  jira.yml
  github.yml
  local-file.yml
  web.yml
  example-internal-wiki.yml
```

Users can add their own files, for example `connectors/my-proprietary-system.yml`.

## Current file format

The CLI is stdlib-only, so the current implementation reads connectors as **JSON-compatible YAML** (valid YAML 1.2 written in JSON object syntax).

That means these are fine today:

- `.yml` files containing pretty-printed JSON
- fields made of strings, booleans, arrays, and nested objects

A future version can grow into a fuller YAML parser without changing the conceptual schema.

## Connector schema

Typical top-level fields:

- `id`
- `name`
- `description`
- `refs[]`
- `auth`
- `capabilities`
- `discover`
- `fetch`
- `refresh`
- `normalize`
- `tracking`
- `metadata`

### `refs[]`

Each ref matcher usually contains:

- `pattern` — regex used to recognize a pasted ref
- `source-ref` — template for the persisted `source-ref`
- `source-id` — template for a stable upstream id

Templates use `{{name}}` placeholders from the regex's named capture groups plus `{{url}}` / `{{ref}}`.

## Example

```yaml
id: google-doc
name: Google Docs
refs:
  - pattern: https://docs\.google\.com/document/d/(?P<id>[^/]+)
    source-ref: '{{url}}'
    source-id: '{{id}}'
capabilities:
  discover: true
  fetch: true
  refresh: true
fetch:
  run: gws drive files export --params '{"fileId":"{{source_id}}","mimeType":"text/markdown"}' -o '{{tmp_body}}'
normalize:
  kind: markdown
tracking:
  identity: '{{source_id}}'
  cursor: none
```

## Built-in connectors

This repo currently ships definitions for:

- `google-doc`
- `google-sheet`
- `gmail`
- `notion`
- `slack`
- `jira`
- `github`
- `local-file`
- `web`
- `example-internal-wiki`

Some built-ins still point at environment-specific tools (`gws`, `gh`, MCP-backed Notion/Slack, `acli`). That is intentional: they are examples and defaults, not hardcoded assumptions in the contract.

## Resource frontmatter and connectors

Connectors pair naturally with these optional frontmatter fields:

```yaml
source: google-doc
source-ref: https://docs.google.com/document/d/...
source-id: abc123
connector: google-doc
source-updated: 2026-06-13T10:00:00Z
source-cursor: optional
```

Minimum required fields remain `source` and `source-ref`.

## CLI support

Inspect the registry:

```bash
bin/memoria connector list
bin/memoria connector show --id google-doc
bin/memoria connector match --ref "https://docs.google.com/document/d/abc123/edit"
```

Scaffold a new connector:

```bash
bin/memoria setup connector --id internal-wiki
```

## Refresh models

Use `tracking.cursor` for tail-forward feeds. Common modes:

- `snapshot` — re-fetch whole resource and compare
- `cursor` — fetch only newer items and advance `source-cursor`
- `none` — no refresh path

## Legacy recipes

The old source-by-source command reference still lives at [`.claude/references/fetching-sources.md`](../.claude/references/fetching-sources.md). Keep it as supplemental detail until every built-in connector carries enough mechanics on its own.
