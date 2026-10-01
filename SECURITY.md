# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Memoria, please report it privately rather than opening a public issue.

Use GitHub's private vulnerability reporting feature when available. Otherwise, contact the repository maintainers privately; do not post vulnerability details or credentials in a public issue.

Please include:
- A description of the vulnerability
- Steps to reproduce
- Affected versions (if known)

## Supported versions

Only the latest commit on `main` is actively supported.

## Security model

Memoria is a local-only CLI tool. It does not:

- Make outbound network requests
- Run daemons or background services
- Collect telemetry
- Store secrets

The primary security surface is the content indexed into the local RAG database (`projects/<slug>/.memoria/rag.sqlite`), which lives on your filesystem and inherits your existing file permissions.
