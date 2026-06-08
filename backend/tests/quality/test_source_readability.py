from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"

FORBIDDEN_MARKERS = [
    "\u4e2d\u6587\u6ce8\u91ca\uff1a",
    "\u6d93",
    "\u5a11",
    "\u951b",
    "\u6b7f",
    "\u935a",
    "\u9422",
    "\u7487",
    "\u7ee0",
    "\u9597",
    "\u93bf",
    "\u9237",
    "\u20ac",
    "???",
]


@dataclass(frozen=True)
class ReadabilityIssue:
    path: Path
    line: int
    marker: str
    text: str

    def format(self) -> str:
        relative = self.path.relative_to(PROJECT_ROOT).as_posix()
        snippet = self.text.strip().replace("\n", "\\n")
        snippet = snippet.encode("ascii", "backslashreplace").decode("ascii")
        return f"{relative}:{self.line}: found {self.marker!r} in {snippet!r}"


def _python_files() -> list[Path]:
    return sorted(APP_ROOT.rglob("*.py"))


def _comment_texts(path: Path) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8-sig")
    comments: list[tuple[int, str]] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            comments.append((token.start[0], token.string))
    return comments


def _docstring_texts(path: Path) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(path))
    docstrings: list[tuple[int, str]] = []
    nodes: list[ast.AST] = [tree, *[node for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]]
    for node in nodes:
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            docstrings.append((getattr(first, "lineno", getattr(node, "lineno", 1)), first.value.value))
    return docstrings


def _find_issues() -> list[ReadabilityIssue]:
    issues: list[ReadabilityIssue] = []
    for path in _python_files():
        for line, text in [*_comment_texts(path), *_docstring_texts(path)]:
            for marker in FORBIDDEN_MARKERS:
                if marker in text:
                    issues.append(ReadabilityIssue(path=path, line=line, marker=marker, text=text))
                    break
    return issues


def test_backend_comments_and_docstrings_are_readable() -> None:
    issues = _find_issues()
    assert not issues, "\n".join(issue.format() for issue in issues[:120])


def test_backend_python_files_do_not_start_with_blank_lines() -> None:
    offenders = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in _python_files()
        if path.read_text(encoding="utf-8-sig").startswith(("\n", "\r\n"))
    ]
    assert not offenders, "\n".join(offenders[:120])
