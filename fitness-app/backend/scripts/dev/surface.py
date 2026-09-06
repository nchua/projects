"""Print a module's public surface: signatures + first docstring line.

Run from fitness-app/backend, one or more dotted module names or paths:

    venv/bin/python scripts/dev/surface.py app.services.purge_service app/api/admin.py

Replaces opening a 900-line module to confirm keyword arguments and return
shapes before writing against it (session-pickup cost, 2026-09-06). Private
names (leading underscore) are shown with ``--private``.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterator, List

BACKEND = Path(__file__).resolve().parents[2]


def _path(arg: str) -> Path:
    p = Path(arg)
    if p.suffix == ".py":
        return p if p.is_absolute() else BACKEND / p
    return BACKEND / (arg.replace(".", "/") + ".py")


def _first_line(node: ast.AST) -> str:
    doc = ast.get_docstring(node)
    return doc.strip().splitlines()[0] if doc else ""


def _signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = fn.args
    parts: List[str] = []
    positional = args.posonlyargs + args.args
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    for a, d in zip(positional, defaults):
        s = a.arg + (f": {ast.unparse(a.annotation)}" if a.annotation else "")
        parts.append(s + (f" = {ast.unparse(d)}" if d is not None else ""))
    if args.posonlyargs:
        parts.insert(len(args.posonlyargs), "/")
    if args.vararg:
        parts.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        parts.append("*")
    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        s = a.arg + (f": {ast.unparse(a.annotation)}" if a.annotation else "")
        parts.append(s + (f" = {ast.unparse(d)}" if d is not None else ""))
    if args.kwarg:
        parts.append("**" + args.kwarg.arg)
    ret = f" -> {ast.unparse(fn.returns)}" if fn.returns else ""
    prefix = "async def" if isinstance(fn, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {fn.name}({', '.join(parts)}){ret}"


def surface(path: Path, *, private: bool = False) -> Iterator[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    yield f"# {path.relative_to(BACKEND)} — {_first_line(tree)}"
    for node in tree.body:
        if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets):
            yield f"{', '.join(t.id for t in node.targets)} = {ast.unparse(node.value)[:80]}"
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and not private:
                continue
            yield f"{_signature(node)}\n    {_first_line(node)}"
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            yield f"class {node.name}({bases}):  {_first_line(node)}"
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    default = f" = {ast.unparse(item.value)}" if item.value is not None else ""
                    yield f"    {item.target.id}: {ast.unparse(item.annotation)}{default}"
                elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and (private or not item.name.startswith("_")):
                    yield f"    {_signature(item)}"
    yield ""


def main(argv: List[str]) -> int:
    private = "--private" in argv
    targets = [a for a in argv if not a.startswith("--")]
    if not targets:
        print(__doc__)
        return 2
    for arg in targets:
        for line in surface(_path(arg), private=private):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
