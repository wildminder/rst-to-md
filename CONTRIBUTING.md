# Contributing

Thanks for your interest in improving `rst-to-md`!

## Development setup

```bash
# Create and activate a virtual environment (uv-managed venv used here)
call C:\_Dev\Python\.venv\Scripts\activate
uv pip install -e ".[dev]"
```

## Running the checks

```bash
make lint      # ruff check + ruff format --check
make type      # mypy rst_to_md
make test      # pytest with coverage
```

Or directly:

```bash
ruff check .
mypy rst_to_md
pytest -q
```

## Guidelines

- Keep functions small and pure where possible (post-processing, link rewriting).
- Add a test for every behavior change; unit tests should not require Sphinx.
- Integration tests may run `sphinx-build` on the tiny fixtures under `tests/fixtures/`.
- Run `pre-commit install` to enable the hooks locally.

## Pull requests

- Describe the motivation and the change.
- Ensure `make lint type test` passes.
- Update `CHANGELOG.md` under the Unreleased section.
