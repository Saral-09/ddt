from __future__ import annotations

import ast
import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class RepositoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolRecord:
    id: str
    name: str
    path: str
    description: str
    category: str
    component: str
    source_file: str | None


_IMPORT_RE = re.compile(
    r"^\s*import\s+(?P<symbol>[A-Za-z_$][\w$]*)\s+from\s+['\"](?P<module>[^'\"]+)['\"]\s*;?",
    re.MULTILINE,
)
_IMPORT_NAMED_RE = re.compile(
    r"^\s*import\s*\{(?P<symbols>[^}]+)\}\s*from\s+['\"](?P<module>[^'\"]+)['\"]\s*;?",
    re.MULTILINE,
)
_STRING_RE = re.compile(r"(['\"])(?:\\.|(?!\1).)*?\1")


def _decode_js_string(value: str) -> str:
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return value.strip("'\"")


def _extract_array_body(source: str, marker: str) -> str:
    marker_pos = source.find(marker)
    if marker_pos < 0:
        raise RepositoryError(f"Could not find '{marker}' in RouteWrapper.tsx")

    # RouteWrapper declares the registry with a TypeScript array annotation:
    #   export const ROUTES: RouteProperties[] = [ ... ]
    # Searching for the first '[' after the marker would accidentally select
    # the [] in RouteProperties[] and return an empty array. Find the
    # initializer assignment first, then the array literal that follows it.
    assignment_pos = source.find("=", marker_pos + len(marker))
    if assignment_pos < 0:
        raise RepositoryError(f"Could not find the initializer for '{marker}'")

    start = source.find("[", assignment_pos + 1)
    if start < 0:
        raise RepositoryError("Could not find the ROUTES array opening bracket")

    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    i = start
    while i < len(source):
        char = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""

        if line_comment:
            if char == "\n":
                line_comment = False
            i += 1
            continue
        if block_comment:
            if char == "*" and nxt == "/":
                block_comment = False
                i += 2
            else:
                i += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            i += 1
            continue
        if char == "/" and nxt == "/":
            line_comment = True
            i += 2
            continue
        if char == "/" and nxt == "*":
            block_comment = True
            i += 2
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return source[start + 1 : i]
        i += 1
    raise RepositoryError("ROUTES array is not closed")


def _top_level_objects(array_body: str) -> list[str]:
    objects: list[str] = []
    depth = 0
    start: int | None = None
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    i = 0
    while i < len(array_body):
        char = array_body[i]
        nxt = array_body[i + 1] if i + 1 < len(array_body) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
            i += 1
            continue
        if block_comment:
            if char == "*" and nxt == "/":
                block_comment = False
                i += 2
            else:
                i += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            i += 1
            continue
        if char == "/" and nxt == "/":
            line_comment = True
            i += 2
            continue
        if char == "/" and nxt == "*":
            block_comment = True
            i += 2
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char == "{":
            if depth == 0:
                start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(array_body[start : i + 1])
                start = None
        i += 1
    return objects


def _field_string(entry: str, field: str) -> str | None:
    match = re.search(rf"\b{re.escape(field)}\s*:\s*((?:\"(?:\\.|[^\"\\])*\")|(?:'(?:\\.|[^'\\])*'))", entry, re.DOTALL)
    if not match:
        return None
    return _decode_js_string(match.group(1))


def _field_component(entry: str) -> str | None:
    match = re.search(r"\belement\s*:\s*<([A-Za-z_$][\w$]*)\s*/>", entry)
    return match.group(1) if match else None


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class DDTRepository:
    """Read-only DDT source inspector. It never edits project files."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise RepositoryError(f"DDT repository directory does not exist: {self.root}")
        self.src = self.root / "src"
        self.route_file = self.src / "components" / "RouteWrapper.tsx"
        self.command_helper = self.src / "utils" / "CommandHelper.ts"
        if not self.route_file.is_file():
            raise RepositoryError(f"Expected DDT route registry at {self.route_file}")

        self._route_source = self.route_file.read_text(encoding="utf-8", errors="replace")
        self._import_map = self._parse_imports(self._route_source)
        self._tools = self._parse_tools()

    @staticmethod
    def _parse_imports(source: str) -> dict[str, str]:
        imports = {m.group("symbol"): m.group("module") for m in _IMPORT_RE.finditer(source)}
        for match in _IMPORT_NAMED_RE.finditer(source):
            module = match.group("module")
            for symbol in match.group("symbols").split(","):
                item = symbol.strip()
                if not item:
                    continue
                parts = re.split(r"\s+as\s+", item)
                local_name = parts[-1].strip()
                if re.fullmatch(r"[A-Za-z_$][\w$]*", local_name):
                    imports[local_name] = module
        return imports

    def _resolve_component(self, component: str) -> Path | None:
        module = self._import_map.get(component)
        if not module or not module.startswith("."):
            return None
        base = (self.route_file.parent / module).resolve()
        candidates = [base, base.with_suffix(".tsx"), base.with_suffix(".ts"), base / "index.tsx", base / "index.ts"]
        for candidate in candidates:
            try:
                candidate.relative_to(self.root)
            except ValueError:
                continue
            if candidate.is_file():
                return candidate
        return None

    def _parse_tools(self) -> list[ToolRecord]:
        body = _extract_array_body(self._route_source, "export const ROUTES")
        records: list[ToolRecord] = []
        for entry in _top_level_objects(body):
            path = _field_string(entry, "path") or ""
            if not path.startswith("/tools/"):
                continue
            name = _field_string(entry, "name") or path.rsplit("/", 1)[-1]
            component = _field_component(entry) or ""
            description = _field_string(entry, "description") or ""
            category = _field_string(entry, "category") or "Uncategorised"
            source = self._resolve_component(component) if component else None
            records.append(
                ToolRecord(
                    id=_slug(name),
                    name=name,
                    path=path,
                    description=description,
                    category=category,
                    component=component,
                    source_file=str(source.relative_to(self.root)) if source else None,
                )
            )
        if not records:
            raise RepositoryError("No /tools routes were parsed from RouteWrapper.tsx")
        return records

    def list_tools(self, query: str = "", category: str = "") -> dict[str, Any]:
        q = query.strip().lower()
        c = category.strip().lower()
        items = [t for t in self._tools if (not q or q in t.name.lower() or q in t.id or q in t.description.lower()) and (not c or c in t.category.lower())]
        return {"count": len(items), "tools": [asdict(t) for t in items]}

    def find_tool(self, tool_id: str) -> ToolRecord:
        key = _slug(tool_id)
        for tool in self._tools:
            if key in (tool.id, _slug(tool.name), _slug(tool.path.rsplit("/", 1)[-1])):
                return tool
        raise RepositoryError(f"Tool '{tool_id}' was not found in DDT's /tools routes")

    def _read_tool_source(self, tool: ToolRecord) -> str:
        if not tool.source_file:
            raise RepositoryError(f"Could not resolve source component for {tool.name} ({tool.component})")
        path = (self.root / tool.source_file).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise RepositoryError("Resolved component path escaped repository root") from exc
        return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _extract_dependencies(source: str) -> list[str]:
        match = re.search(r"(?:const|let)\s+dependencies\s*=\s*\[(.*?)\]", source, re.DOTALL)
        if not match:
            return []
        values = []
        for string_match in _STRING_RE.finditer(match.group(1)):
            literal = string_match.group(0)
            value = _decode_js_string(literal)
            if re.fullmatch(r"[A-Za-z0-9_.+-]+", value):
                values.append(value)
        return sorted(set(values))

    @staticmethod
    def _extract_command_evidence(source: str, max_lines: int = 65) -> list[str]:
        lines = source.splitlines()
        patterns = re.compile(r"CommandHelper|new Command\(|dependencies\s*=|const args\s*=|\.push\(|\.execute\(|\.spawn\(|onSubmit|runCommand", re.IGNORECASE)
        selected: set[int] = set()
        for index, line in enumerate(lines):
            if patterns.search(line):
                selected.update(range(max(0, index - 2), min(len(lines), index + 3)))
        return [f"{i + 1}: {lines[i]}" for i in sorted(selected)[:max_lines]]

    def inspect_tool(self, tool_id: str) -> dict[str, Any]:
        tool = self.find_tool(tool_id)
        source = self._read_tool_source(tool)
        dependencies = self._extract_dependencies(source)

        # Include the tool's user-reviewed QA fixture card in the same inspection
        # response. The Foundry agent should not need a separate, unbounded file read.
        fixture_root = self.root / "qa-agent" / "fixtures" / "ddt-qa-fixtures"
        fixture_card_path = fixture_root / "tools" / tool.id / "TEST-CARD.md"
        fixture_json_path = fixture_root / "tools" / tool.id / "fixture.json"
        fixture_card = None
        fixture_metadata = None
        shared_fixture_guides: list[dict[str, str]] = []
        if fixture_card_path.is_file():
            fixture_card = fixture_card_path.read_text(encoding="utf-8", errors="replace")[:7000]
        if fixture_json_path.is_file():
            try:
                fixture_metadata = json.loads(fixture_json_path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError:
                fixture_metadata = {"status": "invalid_json", "path": str(fixture_json_path.relative_to(self.root))}

        # Include short guides for declared shared fixture folders so the agent
        # knows how to use a fixture service without another broad repository read.
        if isinstance(fixture_metadata, dict):
            for shared_path in fixture_metadata.get("shared_fixtures", []):
                if not isinstance(shared_path, str) or not shared_path.startswith("common/"):
                    continue
                normalized = (fixture_root / shared_path).resolve()
                try:
                    normalized.relative_to(fixture_root.resolve())
                except ValueError:
                    continue
                guide = normalized / "README.md" if shared_path.endswith("/") or normalized.is_dir() else normalized.parent / "README.md"
                if guide.is_file():
                    shared_fixture_guides.append(
                        {
                            "path": str(guide.relative_to(self.root)),
                            "content": guide.read_text(encoding="utf-8", errors="replace")[:3500],
                        }
                    )
                if len(shared_fixture_guides) >= 5:
                    break

        # Compact evidence helps the model map the visible form without consuming
        # the entire component source for every UI test request.
        ui_patterns = re.compile(
            r"\b(?:name|label|placeholder|aria-label|type|checked|value)\s*=|"
            r"<(?:TextInput|Textarea|Select|MultiSelect|Switch|Checkbox|NumberInput|Radio|FileInput)\b",
            re.IGNORECASE,
        )
        ui_field_evidence = [
            f"{line_number}: {line.strip()}"
            for line_number, line in enumerate(source.splitlines(), start=1)
            if ui_patterns.search(line)
        ][:100]

        return {
            "tool": asdict(tool),
            "dependencies": dependencies,
            "fixture_metadata": fixture_metadata,
            "fixture_card": fixture_card,
            "shared_fixture_guides": shared_fixture_guides,
            "ui_field_evidence": ui_field_evidence,
            "source_excerpt": source[:18000],
            "source_truncated": len(source) > 18000,
            "command_evidence": self._extract_command_evidence(source),
        }

    def check_dependencies(self, tool_id: str) -> dict[str, Any]:
        info = self.inspect_tool(tool_id)
        dependencies = info["dependencies"]
        if not dependencies:
            return {
                "tool_id": info["tool"]["id"],
                "status": "needs_review",
                "message": "No literal dependencies array could be extracted from this component.",
                "dependencies": [],
            }
        results = []
        for dependency in dependencies:
            results.append({"name": dependency, "available": shutil.which(dependency) is not None, "path": shutil.which(dependency)})
        return {
            "tool_id": info["tool"]["id"],
            "status": "passed" if all(item["available"] for item in results) else "failed",
            "dependencies": results,
        }

    def inspect_execution_helper(self) -> dict[str, Any]:
        if not self.command_helper.is_file():
            raise RepositoryError(f"CommandHelper.ts not found at {self.command_helper}")
        source = self.command_helper.read_text(encoding="utf-8", errors="replace")
        return {
            "file": str(self.command_helper.relative_to(self.root)),
            "source_excerpt": source[:20000],
            "source_truncated": len(source) > 20000,
        }

    def inspect_tauri_backend(self, tool_id: str, max_files: int = 8) -> dict[str, Any]:
        """Return bounded, read-only Rust/Tauri process and permission evidence."""
        tool = self.find_tool(tool_id)
        component_source = self._read_tool_source(tool)
        rust_root = self.root / "src-tauri" / "src"
        if not rust_root.is_dir():
            return {
                "tool_id": tool.id,
                "status": "not_found",
                "message": f"Tauri Rust source directory not found: {rust_root}",
                "component_command_evidence": self._extract_command_evidence(component_source),
                "files": [],
            }

        patterns = {
            "shell_plugin": re.compile(r"tauri[_-]?plugin[_-]?shell|ShellExt|\.shell\(\)", re.IGNORECASE),
            "process_creation": re.compile(r"Command::new|std::process|\bspawn\s*\(|\boutput\s*\(", re.IGNORECASE),
            "process_control": re.compile(r"\b(kill|terminate|pid|child)\b", re.IGNORECASE),
            "tauri_commands": re.compile(r"tauri::command|invoke_handler|generate_handler", re.IGNORECASE),
            "permissions": re.compile(r"permission|capabilit|scope|allow[_-]?execute|deny[_-]?execute", re.IGNORECASE),
        }
        skipped = {"target", "node_modules", "dist", "build", "generated"}
        candidates: list[tuple[int, Path, list[str], list[int]]] = []
        for path in rust_root.rglob("*.rs"):
            if any(part in skipped for part in path.parts):
                continue
            try:
                resolved = path.resolve()
                resolved.relative_to(rust_root.resolve())
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except (OSError, ValueError):
                continue
            matched_lines: set[int] = set()
            matched_patterns: set[str] = set()
            for index, line in enumerate(lines):
                for label, pattern in patterns.items():
                    if pattern.search(line):
                        matched_lines.add(index)
                        matched_patterns.add(label)
            if matched_lines:
                score = len(matched_lines) + 3 * len(matched_patterns)
                candidates.append((score, path, lines, sorted(matched_lines)))

        candidates.sort(key=lambda item: item[0], reverse=True)
        files: list[dict[str, Any]] = []
        total_chars = 0
        for _score, path, lines, matched in candidates[:max_files]:
            windows: list[tuple[int, int]] = []
            for line_index in matched:
                start, end = max(0, line_index - 2), min(len(lines), line_index + 3)
                if windows and start <= windows[-1][1]:
                    windows[-1] = (windows[-1][0], max(windows[-1][1], end))
                else:
                    windows.append((start, end))
            excerpt_lines: list[str] = []
            for start, end in windows:
                excerpt_lines.extend(
                    f"{i + 1}: {lines[i]}" for i in range(start, min(end, start + 12))
                )
                excerpt_lines.append("…")
            excerpt = "\n".join(excerpt_lines).strip()
            excerpt = re.sub(
                r"(?i)((?:password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key)\s*[:=]\s*[\"'])[^\"']+([\"'])",
                r"\1[REDACTED]\2",
                excerpt,
            )
            excerpt = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]{12,}", r"\1[REDACTED]", excerpt)
            remaining = 24000 - total_chars
            if remaining <= 0:
                break
            excerpt = excerpt[:remaining]
            total_chars += len(excerpt)
            matched_names = [
                label for label, pattern in patterns.items()
                if any(pattern.search(lines[index]) for index in matched)
            ]
            files.append(
                {
                    "file": str(path.relative_to(self.root)),
                    "matched_patterns": matched_names,
                    "excerpt": excerpt,
                }
            )

        config_evidence: list[dict[str, str]] = []
        config_candidates = [self.root / "src-tauri" / "Cargo.toml"]
        capabilities = self.root / "src-tauri" / "capabilities"
        if capabilities.is_dir():
            config_candidates.extend(sorted(capabilities.glob("*.json"))[:4])
        for path in config_candidates:
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            selected = [
                f"{number}: {line}"
                for number, line in enumerate(content.splitlines(), start=1)
                if re.search(r"tauri|shell|process|permission|capabilit|scope|execute", line, re.IGNORECASE)
            ]
            if selected:
                config_evidence.append(
                    {"file": str(path.relative_to(self.root)), "excerpt": "\n".join(selected[:60])[:5000]}
                )

        return {
            "tool_id": tool.id,
            "tool_name": tool.name,
            "status": "inspected" if files or config_evidence else "no_process_backend_matches",
            "component_file": tool.source_file,
            "component_command_evidence": self._extract_command_evidence(component_source),
            "rust_files_considered": len(candidates),
            "files": files,
            "tauri_config_evidence": config_evidence,
            "note": "Read-only code evidence only; matches are not proof of a defect. Trace the actual call path before reporting a backend bug.",
        }

    def inspect_related_tests(self, tool_id: str, max_files: int = 4) -> dict[str, Any]:
        tool = self.find_tool(tool_id)
        tokens = {tool.id, _slug(tool.name), tool.name.lower().replace(" ", "")}
        candidates: list[Path] = []
        roots = [self.src / "test", self.src]
        seen: set[Path] = set()
        test_suffixes = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", ".test.js", ".test.cjs")
        for base in roots:
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if not path.is_file() or not path.name.endswith(test_suffixes):
                    continue
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                name_match = any(token in _slug(path.stem) or token in path.stem.lower() for token in tokens)
                if name_match:
                    candidates.append(resolved)
                    continue
                # Catch shared test files whose filenames do not contain the tool name.
                try:
                    preview = path.read_text(encoding="utf-8", errors="replace")[:20000].lower()
                except OSError:
                    continue
                if any(token in preview for token in tokens):
                    candidates.append(resolved)
        items = []
        for path in candidates[:max_files]:
            content = path.read_text(encoding="utf-8", errors="replace")
            items.append({"file": str(path.relative_to(self.root)), "content": content[:10000], "truncated": len(content) > 10000})
        return {"tool_id": tool.id, "count": len(items), "tests": items}

    @property
    def root_path(self) -> Path:
        return self.root
