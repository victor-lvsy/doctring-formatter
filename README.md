# docstring-formatter

Conservative docstring formatter for Python code. It normalizes existing docstrings to [NumPy style](https://numpydoc.readthedocs.io/en/latest/format.html) and fills in missing sections (`Parameters`, `Returns`, `Raises`, `Attributes`) from type annotations and AST analysis — without rewriting prose you already wrote.

The CLI command is `docfmt`.

## What it does

- **Functions and methods** — adds or completes `Parameters`, `Returns`, and `Raises` sections; infers types from annotations; marks missing descriptions with `DOC_MISSING:` placeholders.
- **Classes** — adds an `Attributes` section for annotated class fields when one is not already present.
- **Skips trivial code** — ignores dunder methods, logger helpers, one-liner stubs, and docstrings whose first line starts with `TRIVIAL`.
- **Preserves intent** — leaves existing section content in place; only normalizes underline lengths and collapses extra blank lines.

By default, `tests/` and `alembic/` directories are excluded.

## Requirements

- Python 3.10+

## Installation

This tool is not published on PyPI. Install it from source with [pipx](https://pipx.pypa.io/), which creates an isolated environment and puts the `docfmt` executable on your `PATH`.

### From a local checkout

```bash
git clone <repository-url>
cd docstring-formatter
pipx install .
```

### From a Git URL

```bash
pipx install git+https://github.com/<org>/docstring-formatter.git
```

### Upgrade or reinstall

After pulling new changes in a local checkout:

```bash
cd docstring-formatter
pipx reinstall .
```

Or reinstall directly from Git:

```bash
pipx reinstall git+https://github.com/<org>/docstring-formatter.git
```

### One-off run without installing

From a Git repository:

```bash
pipx run --spec git+https://github.com/<org>/docstring-formatter.git docfmt --diff src/
```

## Usage

Process the current directory (writes changes in place):

```bash
docfmt
```

Process a specific file or directory:

```bash
docfmt src/my_module.py
docfmt src/
```

Preview changes without writing files:

```bash
docfmt --diff src/
```

Exclude additional path segments (repeatable; `tests` and `alembic` are excluded by default):

```bash
docfmt --exclude migrations --exclude .venv src/
```

After each run, `docfmt` prints a summary:

```
changed_files=3
changed_docstrings=12
```

## Examples

**Dry run on a package:**

```bash
docfmt --diff src/mypackage/
```

**Format only production code:**

```bash
docfmt --exclude tests --exclude scripts src/
```

**Format a single file:**

```bash
docfmt path/to/file.py
```

## Development

This project uses [Poetry](https://python-poetry.org/) for local development:

```bash
poetry install
poetry run docfmt --diff src/
```
