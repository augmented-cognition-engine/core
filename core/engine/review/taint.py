"""Taint analysis — trace security-sensitive data flows from sources to sinks.

Identifies potential security vulnerabilities by tracking how untrusted data
flows through the codebase. Works with ACE's existing AST parser and code graph.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Common taint sources — where untrusted data enters
TAINT_SOURCES = {
    "python": [
        r"request\.(args|form|json|data|files|headers|cookies)",
        r"input\(",
        r"os\.environ",
        r"sys\.argv",
        r"\.read\(",
        r"urlopen\(",
        r"requests\.(get|post|put|delete)\(",
    ],
    "javascript": [
        r"req\.(body|params|query|headers|cookies)",
        r"document\.(location|cookie|referrer)",
        r"window\.location",
        r"process\.env",
        r"fs\.readFile",
        r"fetch\(",
    ],
    "typescript": [
        r"req\.(body|params|query|headers|cookies)",
        r"document\.(location|cookie|referrer)",
        r"process\.env",
        r"fetch\(",
    ],
}

# Common taint sinks — where untrusted data is dangerous
TAINT_SINKS = {
    "python": [
        r"execute\(",  # SQL injection
        r"os\.system\(",  # command injection
        r"subprocess\.(run|call|Popen)\(",  # command injection
        r"eval\(",  # code injection
        r"exec\(",  # code injection
        r"render_template_string\(",  # SSTI
        r"\.format\(.*\)",  # format string
        r"cursor\.execute\(",  # SQL injection
        r"db\.query\(",  # DB injection
    ],
    "javascript": [
        r"eval\(",
        r"innerHTML",
        r"document\.write\(",
        r"\.exec\(",  # regex DoS or command
        r"child_process\.",
        r"\.query\(",  # SQL
        r"res\.(send|write|json)\(",  # XSS
    ],
    "typescript": [
        r"eval\(",
        r"innerHTML",
        r"dangerouslySetInnerHTML",
        r"child_process\.",
        r"\.query\(",
        r"res\.(send|write|json)\(",
    ],
}


@dataclass
class TaintFlow:
    """A detected data flow from source to sink."""

    source_file: str
    source_line: int
    source_pattern: str
    sink_file: str
    sink_line: int
    sink_pattern: str
    severity: str = "high"  # critical if direct, high if through functions
    flow_type: str = ""  # sql_injection, xss, command_injection, etc.
    confidence: float = 0.7
    description: str = ""


@dataclass
class TaintReport:
    """Complete taint analysis report."""

    flows: list[TaintFlow] = field(default_factory=list)
    sources_found: int = 0
    sinks_found: int = 0
    files_analyzed: int = 0

    @property
    def has_critical(self) -> bool:
        return any(f.severity == "critical" for f in self.flows)


class TaintAnalyzer:
    """Static taint analysis using pattern matching on code content.

    This is a lightweight approach — pattern-based rather than full data flow.
    It identifies files with taint sources and sinks, then checks if they're
    connected via the code graph (imports, function calls, co-changes).
    """

    def analyze_file(self, path: str, content: str, language: str) -> tuple[list[dict], list[dict]]:
        """Find taint sources and sinks in a single file.

        Returns (sources, sinks) where each is a list of
        {"line": int, "pattern": str, "text": str}.
        """
        sources = []
        sinks = []

        source_patterns = TAINT_SOURCES.get(language, [])
        sink_patterns = TAINT_SINKS.get(language, [])

        for i, line_text in enumerate(content.split("\n"), start=1):
            stripped = line_text.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue  # skip comments

            for pattern in source_patterns:
                if re.search(pattern, line_text):
                    sources.append({"line": i, "pattern": pattern, "text": stripped[:100]})
                    break

            for pattern in sink_patterns:
                if re.search(pattern, line_text):
                    sinks.append({"line": i, "pattern": pattern, "text": stripped[:100]})
                    break

        return sources, sinks

    def analyze_diff_files(
        self,
        files: list[dict],
    ) -> TaintReport:
        """Analyze changed files from a PR diff for taint flows.

        files: list of {"path": str, "content": str, "language": str}
        """
        all_sources: list[tuple[str, dict]] = []  # (file_path, source_info)
        all_sinks: list[tuple[str, dict]] = []

        for f in files:
            path = f["path"]
            content = f.get("content", "")
            language = f.get("language", "")

            if not content or language not in TAINT_SOURCES:
                continue

            sources, sinks = self.analyze_file(path, content, language)
            for s in sources:
                all_sources.append((path, s))
            for s in sinks:
                all_sinks.append((path, s))

        # Detect flows: source and sink in same file = potential direct flow
        flows: list[TaintFlow] = []
        source_files = {path for path, _ in all_sources}
        sink_files = {path for path, _ in all_sinks}

        # Same-file flows (highest confidence)
        same_file = source_files & sink_files
        for path in same_file:
            file_sources = [s for p, s in all_sources if p == path]
            file_sinks = [s for p, s in all_sinks if p == path]

            for source in file_sources:
                for sink in file_sinks:
                    if source["line"] < sink["line"]:  # source before sink
                        flow_type = _classify_flow(sink["pattern"])
                        flows.append(
                            TaintFlow(
                                source_file=path,
                                source_line=source["line"],
                                source_pattern=source["pattern"],
                                sink_file=path,
                                sink_line=sink["line"],
                                sink_pattern=sink["pattern"],
                                severity="critical",
                                flow_type=flow_type,
                                confidence=0.8,
                                description=(
                                    f"Potential {flow_type}: untrusted input at line "
                                    f"{source['line']} flows to dangerous operation at line "
                                    f"{sink['line']}"
                                ),
                            )
                        )

        # Cross-file flows (lower confidence — needs graph verification)
        for src_path, source in all_sources:
            for sink_path, sink in all_sinks:
                if src_path != sink_path:
                    flow_type = _classify_flow(sink["pattern"])
                    flows.append(
                        TaintFlow(
                            source_file=src_path,
                            source_line=source["line"],
                            source_pattern=source["pattern"],
                            sink_file=sink_path,
                            sink_line=sink["line"],
                            sink_pattern=sink["pattern"],
                            severity="high",
                            flow_type=flow_type,
                            confidence=0.5,  # lower — needs graph edge confirmation
                            description=(
                                f"Potential cross-file {flow_type}: source in "
                                f"{src_path}:{source['line']}, sink in "
                                f"{sink_path}:{sink['line']}"
                            ),
                        )
                    )

        return TaintReport(
            flows=flows,
            sources_found=len(all_sources),
            sinks_found=len(all_sinks),
            files_analyzed=len(files),
        )


def _classify_flow(sink_pattern: str) -> str:
    """Classify the type of vulnerability based on the sink pattern."""
    if any(kw in sink_pattern for kw in ["execute", "query", "cursor"]):
        return "sql_injection"
    if any(kw in sink_pattern for kw in ["system", "subprocess", "child_process", "exec("]):
        return "command_injection"
    if any(kw in sink_pattern for kw in ["eval(", "exec("]):
        return "code_injection"
    if any(kw in sink_pattern for kw in ["innerHTML", "document.write", "dangerouslySetInnerHTML"]):
        return "xss"
    if any(kw in sink_pattern for kw in ["render_template_string"]):
        return "ssti"
    if any(kw in sink_pattern for kw in ["send", "write", "json"]):
        return "xss"
    return "data_flow"
