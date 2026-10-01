# Contributing to Memoria

Thanks for taking the time to contribute.

## Getting started

```bash
git clone <repository-url> memoria
cd memoria
```

Memoria is stdlib-only — no dependencies beyond Python 3.

## Running tests

```bash
python -m unittest tests.test_rag
```

## Code style

- Follow existing conventions in `bin/memoria` and `lib/`
- stdlib-only — no third-party imports
- Keep the CLI deterministic and judgment-free

## Submitting changes

1. Create a branch from `main`
2. Make your changes
3. Run the tests
4. Open a pull request

Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.
