# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.3] - 2026-08-15

### Fixed
- **`TypeError: '<' not supported between instances of 'int' and '_DummyModule'`
  when converting projects whose `conf.py` registers local directives**
  (e.g. the Torchaudio docs). The lightweight stubbing machinery AST-scans
  `conf.py` imports and stubbed every non-importable name — including
  project-local modules like `custom_directives` that are only importable
  inside the Sphinx subprocess. The stub shadowed the real file, so
  `rst.directives.register_directive()` received `_DummyModule` objects and
  docutils crashed on `directive.required_arguments`. Local modules (files or
  packages in the source dir, or in dirs `conf.py` adds to `sys.path`) are now
  detected by the new pure helpers `extract_sys_path_dirs()` /
  `find_local_modules()` and excluded from both the sitecustomize stub set and
  `autodoc_mock_imports`. As defense in depth, the generated `sitecustomize.py`
  now also wraps `docutils.parsers.rst.states.Body.run_directive` so any single
  broken/stubbed directive degrades to an ERROR system message instead of
  aborting the whole build. Verified end-to-end: the Torchaudio docs
  (`docs/source`) now convert 18 pages with exit code 0. See
  `docs/plans/2026-08-15-fix-local-module-stubbing-directive-crash-plan.md`.

### Changed
- **Single-sourced the package version** (CRIT-002). `pyproject.toml` now
  declares `dynamic = ["version"]` and hatchling reads `__version__` from
  `rst_to_md/__init__.py` at build time — the two sources can no longer
  drift. Packaging tests now also assert the top CHANGELOG release matches
  `__version__`.
- **Declared Python 3.10 as the minimum** (IMP-006): `requires-python`
  bumped to `>=3.10`, CI matrix drops 3.8/3.9, ruff/mypy targets aligned
  to 3.10, README badge updated. A `test_ci.py` guard keeps
  `requires-python`, classifiers, the CI matrix, and the tooling targets
  in sync.

## [1.4.2] - 2026-08-12

### Fixed
- **Empty autosummary tables for non-installed packages.** When the documented
  package (e.g. `librosa`) is not installed, `autosummary_generate` is now left
  `False` (instead of being forced `False` unconditionally) so the build cannot
  crash importing the package and its missing transitive deps. The resulting
  stub autosummary rows (empty description/signature cells) are now backfilled
  **from the package source tree via AST** — no import required — using the new
  `rst_to_md.core.source_extract` (`build_source_map`/`find_source_roots`) and
  `rst_to_md.core.autosummary_enrich` (`enrich_autosummary_table` /
  `write_generated_stubs`) modules. Each empty row is rewritten to a link
  `[`name`](generated/<fqn>.md#<fqn>)<signature>` with the docstring summary in
  the second cell, and matching `generated/<fqn>.md` stub pages are emitted so
  the links resolve. The policy is configurable via `--autosummary-generate
  {auto,true,false}` (default `auto`).
- **Leftover empty named anchors.** The vendored markdown builder emits
  `<a id="..."></a>` anchors for `.. _label:` targets; these carry no navigation
  value in plain Markdown and are now stripped by `strip_empty_anchors` in the
  shared `post_process_markdown` pipeline (anchors that wrap content or carry an
  `href` are left untouched). Fixes the raw `<a id="beat"></a>` leakage in
  `api/beat.md`.

## [1.4.1] - 2026-07-17

### Fixed
- **Vendored `sphinx-markdown-builder` with clean autodoc formatting.** The
  direct Markdown builder (`-b markdown`, the default) previously rendered
  autodoc blocks (`autoclass`/`automethod`/`autofunction`) with three defects
  versus the legacy `html` builder: (D1) field lists (`Parameters:`/`Raises:`)
  became nested bullet lists (`* **Parameters:**` → `* **token**`); (D2)
  `property`/`class` annotations were wrapped in `*italic*`; (D3) member
  signatures became `####` headings. The builder is now **vendored** into
  `rst_to_md/_vendor/sphinx_markdown_builder` (no longer a PyPI dependency) and
  its `MarkdownTranslator` is patched so field lists render as bold labels with
  an indented body, annotations are plain text, and nested member signatures are
  bold paragraphs — matching the `html` builder's output. The vendored copy is
  loaded via `PYTHONPATH` shadowing in `build_sphinx_html` so it overrides any
  PyPI install.
- **Flatten ambiguous cross-reference links inside autodoc signatures (XREF).**
  When a signature parameter or return type is documented on another page, the
  `markdown` builder previously emitted broken links like
  `[BaseSession](session/base.md#aiogram.client.session.base.BaseSession)` — the
  anchor is a fully-qualified Python identifier that does not resolve in Markdown
  viewers. Type cross-references inside any `desc_signature` subtree
  (`ContextStatus.desc_depth > 0`) are now rendered as **plain text** (the type
  name only), matching the legacy `html` builder. Prose cross-references keep
  their normal link / code-span form. Covered by the `sphinx_md_xref` fixture
  and three new tests in `tests/test_sphinx_converter.py`.
- **Proper section header for autodoc blocks.** The top-level autodoc object
  (class/function at `desc_depth == 1`) is now a `##` (h2) **section header**,
  and nested members (methods) are `###` (h3), giving a proper
  `#` (page) → `##` (autodoc section) → `###` (members) heading hierarchy
  instead of jumping straight from h1 to h3/h4. Member *properties/attributes*
  remain bold paragraphs (not headings). Covered by the updated D3 assertions in
  `tests/test_sphinx_converter.py`.

## [1.4.0] - 2026-07-13

### Added
- **Direct Markdown builder (new default Sphinx pipeline).** Sphinx mode now
  renders the doctree straight to Markdown via the `sphinx-markdown-builder`
  extension (`-b markdown`) instead of round-tripping through HTML. This removes
  the HTML→Markdown conversion step entirely — there is no chrome stripping and
  no HTML-specific post-processing, only the shared deterministic cleanup
  (footer/media/link/blank-line normalization). Internal cross-references are
  emitted as `.md#anchor` by the builder itself.
- **Legacy HTML fallback preserved.** `--builder html` restores the original
  `rst → HTML → Markdown` pipeline (used when a project's extensions are
  incompatible with the Markdown builder). Both builders share the same
  `(success, errors, skipped)` contract and the same skip/cache/parallel/report
  features.
- **Parallel Sphinx builds (performance).** The build itself now runs with
  `-j N` (N = CPU count by default) instead of a single core, removing the
  main CPU bottleneck for large doc sets. Controlled by `--build-workers`
  (0 = auto/CPU count, 1 = serial); the IMP-001 mock-all fallback retries
  serially so parallel-incompatible extensions still complete. Note:
  `--workers` only parallelizes the *post-build* conversion, not the build.

## [1.3.0] - 2026-07-13

### Added
- **Live progress tracker.** Both converters now render a single in-place status
  line to stderr when attached to a terminal, showing `N/total | elapsed | ok/err/skip
  | rate`. It is auto-enabled on a TTY and auto-disabled otherwise (CI/pipes), and
  can be forced off with `--no-progress`. The implementation is dependency-free
  ([`rst_to_md/core/progress.py`](rst_to_md/core/progress.py:18)); while the bar is
  active the per-file `[OK]`/`[ERR]` logs are suppressed to avoid clashing with the
  redraw, but errors are still surfaced live and recorded in the `--report` JSON.
- **Incremental caching (NTH-001).** A `.md` is skipped when its source is not
  newer than the existing output; `--no-cache` forces a full reconvert.
- **Parallel conversion (NTH-002).** `--workers N` converts files concurrently via
  a `ThreadPoolExecutor` (default `1`, serial); output is identical to serial.
- **JSON report (NTH-003).** `--report report.json` writes a machine-readable
  summary with per-file status/errors for CI consumption.
- **Dry-run (NTH-004).** `--dry-run` lists the planned `src -> dst` work and
  converts nothing.
- **Sphinx builder override (NTH-006).** `--builder NAME` (default `html`) is
  forwarded to Sphinx via `-b NAME` for both the primary build and the IMP-001
  mock-all fallback.
- **Tooling alignment (NTH-005).** `ruff` `target-version` and `mypy`
  `python_version` now both target `3.10`.

## [1.2.1] - 2026-07-12

### Fixed
- **Sphinx build no longer aborts on third-party objects that raise during
  autodoc member gathering.** Some libraries (e.g. pydantic models) raise when
  their attributes are accessed while Sphinx's `napoleon` extension decides
  whether to skip a member (`getattr(obj, "__qualname__")`). The default handler
  is not exception-safe, so a single problematic member aborted the entire build
  and produced no output. The lightweight build now always installs a
  `sitecustomize.py` that wraps `sphinx.ext.napoleon._skip_member` to skip such
  members instead of crashing. This is essential now that importable packages
  are no longer mocked (1.2.0), which is what exposes their real members.

## [1.2.0] - 2026-07-12

### Added
- **Autodoc content preservation.** Sphinx mode now extracts the page's content
  container (`<main>` / `<article>` / `[role="main"]`) *before* HTML→Markdown
  conversion, so `autoclass` / `autofunction` output is kept intact: class
  signatures, the `Bases:` inheritance list, members (`:members:`,
  `:special-members:`, `:undoc-members:`), and the `Parameters:` / `Raises:` /
  `Returns:` field lists.
- **Signature repair.** `<em class="sig-param">` is rewritten to `<code>` so
  signature parameters such as `` **kwargs `` are emitted as code spans instead
  of being mangled by Markdown emphasis (the previous `***kwargs*` artifact).
- **Permalink cleanup at the source.** `¶` headerlink anchors are removed from
  the HTML before conversion.
- **No mocking of importable packages.** In lightweight mode a package that is
  actually installed is no longer added to `autodoc_mock_imports`, so autodoc
  can resolve the real `Bases:` inheritance list and member signatures.

### Fixed
- Empty `Bases:` inheritance lines caused by mocking the documented package in
  lightweight mode (the converter now keeps importable packages un-mocked).
- Signature parameters rendered as italic emphasis (`**kwargs` → `***kwargs*`).

## [1.1.1] - 2026-07-12

### Added
- Sphinx mode now strips theme-generated navigation chrome from the generated
  Markdown by default: YAML front matter, the global sidebar table of contents,
  theme icons/logo, "Back to top"/"View this page" links, the footer navigation
  (Previous/Next), the copyright line, the local "On this page" table of
  contents, and the `¶` heading permalinks.
- `--keep-chrome` CLI flag to preserve the navigation chrome when desired.

### Fixed
- Heading permalinks emitted by furo/alabaster as `[¶](#anchor "Link to this
  heading")` were left as dangling `[](#anchor...)` links. The pilcrow is now
  removed before empty-link cleanup, so the permalinks are fully stripped.
- The copyright-line regex only matched `© Copyright`; it now also matches
  `Copyright © <year>, <owner>` (copyright symbol after the word).

## [1.1.0] - 2026-07-12

### Fixed
- `html_to_markdown.convert()` may return a `ConversionResult` (v3.8+) rather than a
  `str`/`dict`; `_html_to_markdown` now normalizes all known return shapes.
- Lightweight Sphinx mode no longer overrides `datetime` (which broke `conf.py`
  imports); missing top-level packages are stubbed via a generated `sitecustomize.py`
  injected through `PYTHONPATH`.
- `conf.py` metadata dunders (`__version__`, `__api_version__`, etc.) now resolve to
  `"0.0.0"` strings instead of raising `AttributeError`, and class-protocol dunders
  (`__mro__`, `__dict__`, `__bases__`, ...) correctly raise `AttributeError` so
  autodoc introspection is skipped instead of crashing.
- Eliminated a `RecursionError` in the dummy module `__repr__` by setting real module
  dunders (`__file__`, `__name__`, `__package__`, ...) in `__init__`.
- `rewrite_links` no longer double-prefixes `#` for current-page anchors
  (`.html#frag` -> `#frag`) and handles bare `.html` links (`.html` -> `#`).
- Stub `sitecustomize` template now emits a real `set` literal for `_ALLOWED` (previously
  a string), so only genuinely-missing modules are stubbed.

## [1.0.0] - 2024-01-01

### Added
- Sphinx-aware conversion mode (`--sphinx`) that builds HTML then converts to Markdown.
- Lightweight mode that avoids requiring the documented package or heavy extensions
  (plot/gallery/ipython) by stubbing missing imports and mocking autodoc.
- Simple RST-to-Markdown mode using pypandoc.
- Deterministic, idempotent Markdown post-processing (link rewriting, media stripping,
  blank-line collapsing, footer/timestamp removal).
- Structured package layout (`converters/`, `core/`), `py.typed`, logging, and custom
  exceptions.
- Test suite (unit + integration) with fixtures, plus `ruff`/`mypy` config and CI.
