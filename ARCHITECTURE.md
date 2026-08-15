# Clingwrap Architecture

## Overview

Clingwrap is a debugging information collection tool that processes a YAML
configuration file to gather system state into a compressed ZIP archive.

User-facing documentation lives in `docs/`; this document covers internal
structure.

| Question | Document |
|----------|----------|
| Where do I start reading? | [docs/index.md](docs/index.md) |
| How do I install it, and what does it depend on? | [docs/installation.md](docs/installation.md) |
| How do I configure it? | [docs/configuration.md](docs/configuration.md) |
| What command types exist? | [docs/command-types.md](docs/command-types.md) |
| What does a real config look like? | [docs/examples.md](docs/examples.md) |

## High-Level Architecture

```
+-------------------+     +------------------+     +------------------+
|                   |     |                  |     |                  |
|  Configuration    |---->|  Job Processing  |---->|  ZIP Archive     |
|  (YAML file)      |     |  Engine          |     |  Output          |
|                   |     |                  |     |                  |
+-------------------+     +------------------+     +------------------+
                                 |
                                 v
                    +------------------------+
                    |                        |
                    |  Job Classes           |
                    |  - FileJob             |
                    |  - DirectoryJob        |
                    |  - ShellJob            |
                    |  - ShellEmitterJob     |
                    |                        |
                    +------------------------+
```

## Components

### CLI Layer (`clingwrap/main.py`)

The CLI uses Click framework with a single command group:

- `clingwrap gather` - Main command to collect debugging information

Options:
- `--target` - Configuration file or built-in example name
- `--output` - Output ZIP file path

### Configuration Loading

Configuration can be loaded from three sources:

1. **File path** - Full path to a `.cwd` file
2. **Built-in example** - Name of a shipped example (loaded via
   `importlib.resources`)
3. **Standard input** - YAML piped via stdin

### Job System

All jobs inherit from the `Job` base class:

```
Job (base class)
├── FileJob          - Copy single file
├── DirectoryJob     - Recursively copy directory (yields FileJobs)
├── ShellJob         - Execute shell command
└── ShellEmitterJob  - Generate jobs dynamically
```

#### Job Base Class

Provides common functionality:

- Random job ID for tracking
- Logging (dual output: console and log file)
- Reference to ZIP archive for writing
- Basic `execute()` method that calls `_execute_inner()`

#### FileJob

Copies a single file to the ZIP archive:

- Uses streaming (`zipfile.write()`) for memory efficiency
- Handles missing files gracefully
- Captures exceptions with error details

#### DirectoryJob

Recursively processes a directory:

- Walks directory tree with `os.walk()`
- Yields FileJob dictionaries for each file
- Supports exclusion patterns via regex
- Processing is depth-first for memory efficiency

#### ShellJob

Executes shell commands:

- Uses `oslo_concurrency.processutils.execute()`
- 30-second timeout per command
- Captures stdout, stderr, and exceptions
- Formats output with command header

#### ShellEmitterJob

Generates jobs dynamically:

- Runs shell script with 60-second timeout
- Parses stdout as YAML to get job definitions
- Yields jobs for immediate processing
- Useful for iterating over discovered objects

### Processing Engine

Jobs are processed depth-first:

```python
def process_job(kwargs):
    job = JOB_MAP.get(kwargs['type'])(**kwargs)
    for newjob in job.execute():
        process_job(newjob)  # Recursive, depth-first
```

This approach:

- Minimizes memory usage (no job queue accumulation)
- Processes generated jobs immediately
- Handles arbitrarily deep job hierarchies

### Output Format

The ZIP archive contains:

```
output.zip
├── _commands/          # Shell command outputs
│   ├── uname
│   ├── ip-link
│   └── ...
├── etc/                # Collected config files
│   ├── hosts
│   ├── os-release
│   └── apache2/
├── var/                # Collected log files
│   └── log/
│       └── syslog
├── srv/                # Application data
│   └── ...
└── clingwrap.log       # Execution log
```

## Performance Considerations

### Memory Efficiency

- FileJob uses `zipfile.write()` for streaming (not `writestr()`)
- DirectoryJob yields jobs instead of accumulating
- Depth-first processing prevents queue growth

### Timeouts

- Shell commands: 30 seconds
- Shell emitters: 60 seconds

### Large Collections

For large log collections (e.g., Docker logs), configurations should use
`--tail` or similar limiting options to avoid excessive data.

## Error Handling

- Missing files: Logged and placeholder written
- File read errors: Exception captured in output
- Shell command failures: Exception captured with stdout/stderr
- Shell emitter failures: Exception logged, processing continues

All errors are non-fatal - clingwrap continues collecting other data.

## Configuration Format

YAML with list of command dictionaries:

```yaml
---
- name: Human-readable description
  type: file|directory|shell|shell_emitter
  source: /path/to/source        # for file/directory
  command: shell command         # for shell/shell_emitter
  destination: path/in/zip       # where to store output
  exclude: regex-pattern         # optional, for directory
```

## Dependencies

See [docs/installation.md](docs/installation.md#dependencies) for the runtime
dependency list and licences. `pyproject.toml` is the source of truth for
versions.

## Release Process

Releases are automated via GitHub Actions:

1. Push a version tag (e.g., `v2.2`)
2. The `release.yml` workflow builds the package
3. A required reviewer approves the release
4. The package is signed with Sigstore and published to PyPI

See [RELEASE-SETUP.md](RELEASE-SETUP.md) for one-time setup steps.

## Future Considerations

Potential enhancements:

- Parallel job execution (currently sequential)
- Progress reporting for large collections
- Compression level configuration
- Remote collection (SSH)
- Incremental/differential collection
