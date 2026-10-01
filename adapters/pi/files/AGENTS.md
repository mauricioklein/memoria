# Memoria retrieval workflow for {{HARNESS}}

Start with retrieval before broad scanning.

Important: `{{BIN_PATH}}` is relative to the Memoria repo root, not to `projects/<slug>/`. If your working directory is inside a project folder, first `cd` to the repo root.

1. From the Memoria repo root, run `{{BIN_PATH}} rag search --project <slug> --query "..." --format context --limit 8`
2. Read the returned snippets and files first.
3. If you need more context, run `{{BIN_PATH}} rag related --project <slug> --path <file>`.
4. Only fall back to broad repo scanning when retrieval is weak or empty.

Reference docs:
- RAG workflow: `{{AGENTS_PATH}}`
- Memoria contract: `{{CONTRACT_PATH}}`
- Connectors: `{{CONNECTORS_PATH}}`
