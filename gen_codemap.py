"""Regenerate the auto layer (B) of docs/CODEMAP.md from src/features/*.

Run before every build (rule #15):  .venv\\Scripts\\python.exe gen_codemap.py
Layer A (the hand-written table) is never touched — only the block between
the CODEMAP:AUTO markers is rewritten.
"""
import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
FEATURES_DIR = PROJECT_ROOT / "src" / "features"
CODEMAP = PROJECT_ROOT / "docs" / "CODEMAP.md"
START, END = "<!-- CODEMAP:AUTO:START -->", "<!-- CODEMAP:AUTO:END -->"


def first_doc_line(node) -> str:
    doc = ast.get_docstring(node) or ""
    return doc.splitlines()[0] if doc else ""


def describe_file(py_path: Path) -> list[str]:
    """One bullet per top-level function/class, with method names for classes."""
    tree = ast.parse(py_path.read_text(encoding="utf-8"))
    lines = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            args = ", ".join(a.arg for a in node.args.args)
            lines.append(f"    • `{node.name}({args})` — {first_doc_line(node)}")
        elif isinstance(node, ast.ClassDef):
            lines.append(f"    • `class {node.name}` — {first_doc_line(node)}")
            methods = [n.name for n in node.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and not n.name.startswith("_")]
            if methods:
                lines.append(f"        ↳ {', '.join(methods)}")
    return lines


def build_auto_block() -> str:
    out = [START]
    for feature in sorted(p for p in FEATURES_DIR.iterdir() if p.is_dir()):
        if feature.name == "__pycache__":
            continue
        out.append(f"### {feature.name}")
        files = sorted(feature.glob("*.py"))
        body = []
        for f in files:
            bullets = describe_file(f)
            if bullets:
                body.append(f"- `src/features/{feature.name}/{f.name}`")
                body.extend(bullets)
        out.extend(body if body else ["_(empty)_"])
        out.append("")
    out[-1:] = [END]  # replace trailing blank with the end marker
    return "\n".join(out)


def main() -> None:
    text = CODEMAP.read_text(encoding="utf-8")
    if START not in text or END not in text:
        sys.exit("CODEMAP markers missing — fix docs/CODEMAP.md first.")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    CODEMAP.write_text(head + build_auto_block() + tail, encoding="utf-8")
    print("CODEMAP layer B regenerated.")


if __name__ == "__main__":
    main()
