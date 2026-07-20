"""Pydantic models for GitHub PR data and diff parsing."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DiffHunk(BaseModel):
    """A single hunk within a file diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str = ""
    lines: list[str] = Field(default_factory=list)

    @property
    def added_lines(self) -> list[str]:
        return [line[1:] for line in self.lines if line.startswith("+")]

    @property
    def removed_lines(self) -> list[str]:
        return [line[1:] for line in self.lines if line.startswith("-")]


class FileDiff(BaseModel):
    """Parsed diff for a single file."""

    path: str
    old_path: str | None = None
    status: str = "modified"  # added | modified | deleted | renamed
    hunks: list[DiffHunk] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0

    @property
    def is_new(self) -> bool:
        return self.status == "added"

    @property
    def is_deleted(self) -> bool:
        return self.status == "deleted"

    @property
    def language(self) -> str:
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".rb": "ruby",
            ".cpp": "cpp",
            ".c": "c",
            ".cs": "csharp",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
        }
        for ext, lang in ext_map.items():
            if self.path.endswith(ext):
                return lang
        return "unknown"


class PRInfo(BaseModel):
    """Pull request metadata."""

    number: int
    title: str
    body: str = ""
    author: str = ""
    base_branch: str = "main"
    head_branch: str = ""
    head_sha: str = ""
    repo_owner: str = ""
    repo_name: str = ""
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0


class ReviewComment(BaseModel):
    """A single review comment to post on a PR."""

    path: str
    line: int
    body: str
    severity: str = "medium"
    discipline: str = ""
    side: str = "RIGHT"


class ReviewResult(BaseModel):
    """Complete review result for a PR."""

    pr: PRInfo
    comments: list[ReviewComment] = Field(default_factory=list)
    summary: str = ""
    pass_quality_gate: bool = True
    discipline_scores: dict[str, float] = Field(default_factory=dict)
    findings_by_severity: dict[str, int] = Field(default_factory=dict)
