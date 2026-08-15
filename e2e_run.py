import tempfile, sys
from pathlib import Path
sys.path.insert(0, ".")
from rst_to_md.converters.sphinx import convert_sphinx_project

src = Path("tests/fixtures/sphinx_md_autosummary")
out = Path(tempfile.mkdtemp(prefix="e2e_out_"))
ok = convert_sphinx_project(src, out, lightweight=True, builder="markdown", show_progress=False)
print("RESULT:", ok)
print("=== OUTPUT TREE ===")
for p in sorted(out.rglob("*.md")):
    print(" ", p.relative_to(out))
print("=== index.md ===")
print((out / "index.md").read_text(encoding="utf-8"))
