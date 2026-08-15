# AI Agent Instructions for Clingwrap

This document provides guidance for AI agents working on the clingwrap codebase.

## Project Overview

Clingwrap is a debugging information collection tool that bundles system state
data into a zip file for later analysis. It is a relatively simple project with
a single main module.

## Where the documentation lives

| Question | Document |
|----------|----------|
| Where do I start reading? | [docs/index.md](docs/index.md) |
| How is it put together? | [ARCHITECTURE.md](ARCHITECTURE.md) |
| How do I install it, and what does it depend on? | [docs/installation.md](docs/installation.md) |
| How do I configure it? | [docs/configuration.md](docs/configuration.md) |
| What command types exist? | [docs/command-types.md](docs/command-types.md) |
| What does a real config look like? | [docs/examples.md](docs/examples.md) |

New user-visible documentation belongs in `docs/`; this file and
`ARCHITECTURE.md` are a summary and an index into it.

## Key Files

| File | Purpose |
|------|---------|
| `clingwrap/main.py` | Core implementation - all job classes and CLI |
| `pyproject.toml` | Project metadata, dependencies, and build configuration |
| `clingwrap/examples/*.cwd` | Example configuration files |
| `docs/` | Documentation directory |

## Architecture

The codebase uses a job-based architecture:

1. **Job base class** - Common functionality for all job types
2. **FileJob** - Copies individual files to the ZIP archive
3. **DirectoryJob** - Recursively processes directories, yielding FileJobs
4. **ShellJob** - Executes shell commands with timeout
5. **ShellEmitterJob** - Runs scripts that generate additional job definitions

Jobs are processed depth-first to minimize memory usage.

## Code Style

- Python 3.7+ compatible
- Line length: 120 characters (flake8 configuration)
- Single quotes for strings except docstrings
- Use oslo.concurrency for process execution

## Testing

Run tests with:

```bash
tox -e py38
```

Run linting with:

```bash
tox -e flake8
```

## Common Tasks

### Adding a New Command Type

1. Create a new class inheriting from `Job` in `clingwrap/main.py`
2. Implement `__init__` calling `super().__init__(**kwargs)`
3. Override `execute()` or `_execute_inner()` as appropriate
4. Add the class to `JOB_MAP` dictionary
5. Document the new type in `docs/command-types.md`

### Adding a New Built-in Example

1. Create a new `.cwd` file in `clingwrap/examples/`
2. Document it in `docs/examples.md`
3. Update `docs/index.md` to list the new example

## CI Infrastructure

The project uses GitHub Actions for CI:

- `functional-tests.yml` - Main CI: flake8 linting, requirements validation,
  and automated Claude Code review
- `pr-re-review.yml` - Re-trigger automated review via bot comment
- `pr-address-comments.yml` - Address review comments via bot comment
- `pr-retest.yml` - Re-run functional tests via bot comment
- `release.yml` - Automated PyPI releases with Sigstore signing
- `renovate.yml` - Dependency updates via Renovate
- `export-repo-config.yml` - Daily repo configuration export
- `codeql-analysis.yml` - GitHub CodeQL security scanning

### Bot Commands

In PR comments, authorized users can use:

- `@shakenfist-bot please re-review` - Trigger another automated review
- `@shakenfist-bot please address comments` - Have Claude Code fix review items
- `@shakenfist-bot please retest` - Re-run functional tests

### Pre-commit Hooks

Run `pre-commit run --all-files` before committing. Hooks include:

- `actionlint` - GitHub Actions workflow linting
- `shellcheck` - Shell script linting
