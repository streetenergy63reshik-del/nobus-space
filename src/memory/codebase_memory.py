"""In-memory codebase memory inspired by repo-base patterns.

Indexes local source files and retrieves relevant snippets on demand,
so that agents do not need to pass the entire codebase into an LLM context.
"""

from __future__ import annotations

import ast
import difflib
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class CodeSnippet(BaseModel):
    """A single chunk of code with metadata."""

    file_path: str
    name: str
    node_type: str  # module, class, function, method
    content: str
    start_line: int
    end_line: int
    relevance_score: float = 0.0


class CodebaseMemory:
    """Lightweight keyword-based memory over a Python codebase.

    Future versions may replace keyword matching with vector embeddings
    (Chroma / FAISS) for semantic retrieval.
    """

    def __init__(self) -> None:
        self._snippets: list[CodeSnippet] = []

    def index(self, root_path: str | Path) -> None:
        """Scan Python files under root_path and break them into snippets."""
        root = Path(root_path).resolve()
        self._snippets.clear()

        for file_path in root.rglob("*.py"):
            if ".venv" in file_path.parts or "__pycache__" in file_path.parts:
                continue
            self._index_file(file_path, root)

    def _index_file(self, file_path: Path, root: Path) -> None:
        """Parse a single file and extract top-level classes and functions."""
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return

        lines = source.splitlines()
        relative_path = str(file_path.relative_to(root))

        # Always index the module header (docstring + imports).
        module_content = "\n".join(lines[: min(20, len(lines))])
        self._snippets.append(
            CodeSnippet(
                file_path=relative_path,
                name=file_path.stem,
                node_type="module",
                content=module_content,
                start_line=1,
                end_line=min(20, len(lines)),
            )
        )

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                snippet = CodeSnippet(
                    file_path=relative_path,
                    name=node.name,
                    node_type="class" if isinstance(node, ast.ClassDef) else "function",
                    content=ast.unparse(node),
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                )
                self._snippets.append(snippet)

    def query(self, question: str, top_k: int = 5) -> list[CodeSnippet]:
        """Return the most relevant snippets for a natural-language question.

        Uses keyword matching combined with fuzzy name matching. No LLM is
        involved, so it is fast and token-cheap.
        """
        keywords = self._extract_keywords(question)
        scored: list[tuple[CodeSnippet, float]] = []

        for snippet in self._snippets:
            score = 0.0
            text = f"{snippet.name} {snippet.content}".lower()

            # Keyword matches.
            for keyword in keywords:
                if keyword in text:
                    score += 1.0

            # Fuzzy match against snippet name.
            name_matches = difflib.get_close_matches(
                question.lower(),
                [snippet.name.lower()],
                n=1,
                cutoff=0.6,
            )
            if name_matches:
                score += 2.0

            if score > 0:
                snippet.relevance_score = score
                scored.append((snippet, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return [snippet for snippet, _ in scored[:top_k]]

    @staticmethod
    def _extract_keywords(text: str) -> set[str]:
        """Extract simple lowercase keywords from a question."""
        words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text)  # type: ignore[name-defined]
        return {word.lower() for word in words if len(word) > 2}

    def stats(self) -> dict[str, Any]:
        """Return basic statistics about the indexed codebase."""
        return {
            "total_snippets": len(self._snippets),
            "functions": sum(1 for s in self._snippets if s.node_type == "function"),
            "classes": sum(1 for s in self._snippets if s.node_type == "class"),
            "modules": sum(1 for s in self._snippets if s.node_type == "module"),
        }
