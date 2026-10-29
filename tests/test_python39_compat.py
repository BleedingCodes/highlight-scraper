"""
Regression test for reviewer finding N1: `str | None` unions are
evaluated at def-time on Python < 3.10, which used to make highlight-scraper
unimportable on the README-declared Python 3.9 (reproduced on CPython 3.9.25:
TypeError: unsupported operand type(s) for |). The remediation is
`from __future__ import annotations`; this guard enforces the invariant on
any interpreter: a module may only use PEP 604 unions in positions that get
evaluated if it carries the future import.
"""

import ast
from pathlib import Path

SRC = Path(__file__).parents[1] / "src" / "highlight_scraper"


def _has_future_annotations(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__" and node.col_offset == 0
        and any(a.name == "annotations" for a in node.names)
        for node in tree.body
    )


def _binops_in(node):
    return [n for n in ast.walk(node) if isinstance(n, ast.BinOp)]


def _def_time_union_offenders(tree):
    """PEP 604 unions in *evaluated* annotation positions. Without
    `from __future__ import annotations` these raise TypeError on import
    on Python < 3.10:
    - function arg / return annotations (evaluated at def time), anywhere
    - annotated assignments at module or class scope (evaluated there;
      annotated assignments inside function bodies are NOT evaluated)"""
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None and _binops_in(node.returns):
                offenders.append(node.returns.lineno)
            for arg in (*node.args.posonlyargs, *node.args.args,
                        *node.args.kwonlyargs,
                        node.args.vararg, node.args.kwarg):
                if arg is None:
                    continue
                if arg.annotation is not None and _binops_in(arg.annotation):
                    offenders.append(arg.annotation.lineno)
    scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    for scope in scopes:
        for stmt in scope.body:
            if isinstance(stmt, ast.AnnAssign) and _binops_in(stmt.annotation):
                offenders.append(stmt.annotation.lineno)
    return offenders


def test_no_future_annotation_modules_free_of_def_time_pep604_unions():
    offenders = []
    for py in sorted(SRC.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        if _has_future_annotations(tree):
            continue
        for line in _def_time_union_offenders(tree):
            offenders.append(f"{py.name}: line {line}")

    assert not offenders, (
        "modules without `from __future__ import annotations` must not use "
        "PEP 604 unions (X | Y) in evaluated annotations (breaks Python 3.9): "
        + "; ".join(offenders)
    )


def test_source_info_carries_the_future_import():
    """N1's validated fix keeps the declared Python 3.9 support; the other
    front ends import source_info transitively, so this is the critical one."""
    tree = ast.parse((SRC / "source_info.py").read_text(encoding="utf-8"))
    assert _has_future_annotations(tree), \
        "source_info.py must keep `from __future__ import annotations` (N1)"
