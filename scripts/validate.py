#!/usr/bin/env python3
"""Validate the structure of the clay-kit marketplace and its plugins."""
import json
import re
import sys
from pathlib import Path

MANUAL_ONLY = {"factory-run", "factory-task", "factory-status", "factory-approve", "factory-rework", "factory-answer", "factory-unlock", "factory-backlog"}
AUTO_ALLOWED = {"factory-brainstorm", "factory-plan"}
# The commands that spawn an agent or ask the user: they read how to do it on each host.
SPAWNING = {"factory-run", "factory-task", "factory-approve", "factory-rework", "factory-answer", "factory-unlock"}
CURSOR_PLUGIN_KEYS = {"name", "displayName", "description", "version", "minClientVersions", "author", "publisher", "homepage", "repository", "license", "logo", "keywords", "category", "tags", "commands", "agents", "skills", "rules", "hooks", "variables", "mcpServers"}
CURSOR_MARKETPLACE_KEYS = {"name", "owner", "metadata", "plugins"}
CODEX_HOOKS = {"hooks": {}}
CURSOR_HOOKS = {"version": 1, "hooks": {}}
SHARED_KEYS = ("name", "version", "description")
POLICY_LINE = "allow_implicit_invocation: false"
POLICY_FLOW_RE = re.compile(r"^policy:[ \t]*\{[ \t]*allow_implicit_invocation:[ \t]*false[ \t]*\}$")
POLICY_RE = re.compile(r"^[ \t]+allow_implicit_invocation:[ \t]*false[ \t]*(#.*)?$")
ROOT_SENTENCE = "Your plugin root is the `Plugin root:` line of your prompt; paths below written `<plugin root>/...` start there. If your prompt has no such line, say so in your reply and stop without doing the task."
ROOT_LINE = "Plugin root: ${CLAUDE_PLUGIN_ROOT}"
ROOT_FALLBACK = "If the line above does not show an absolute path, the plugin root is the folder two levels above the folder that holds this SKILL.md (the folder that contains skills/)."
ARGS_FALLBACK = "If the Arguments line still shows a placeholder that starts with $, the arguments are the text the user typed after the command name."


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def has_policy_line(text: str) -> bool:
    """True when `allow_implicit_invocation: false` is a direct, non-comment child of a top-level `policy:` (block or flow style)."""
    in_policy = False
    child_indent: int | None = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            head = line.split("#")[0].strip()
            in_policy = head == "policy:"
            child_indent = None
            if POLICY_FLOW_RE.match(head):
                return True
        elif in_policy:
            indent = len(line) - len(line.lstrip())
            if child_indent is None:
                child_indent = indent
            if indent == child_indent and POLICY_RE.match(line):
                return True
    return False


def validate(root: Path) -> list[str]:
    problems: list[str] = []

    def rel(p: Path) -> str:
        return p.relative_to(root).as_posix()

    def load(path: Path) -> dict | None:
        if not path.exists():
            problems.append(f"{rel(path)}: missing")
            return None
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            problems.append(f"{rel(path)}: invalid JSON ({e.msg})")
            return None
        if not isinstance(data, dict):
            problems.append(f"{rel(path)}: must hold a JSON object")
            return None
        return data

    claude_market = load(root / ".claude-plugin/marketplace.json")
    cursor_market = load(root / ".cursor-plugin/marketplace.json")
    claude_entries = {}
    if claude_market:
        claude_entries = {e["name"]: e for e in claude_market.get("plugins", []) if isinstance(e, dict) and "name" in e}
    if cursor_market:
        market_file = rel(root / ".cursor-plugin/marketplace.json")
        for key in sorted(set(cursor_market) - CURSOR_MARKETPLACE_KEYS):
            problems.append(f"{market_file}: key {key!r} is not in the Cursor marketplace schema")
        cursor_entries = {e["name"]: e for e in cursor_market.get("plugins", []) if isinstance(e, dict) and "name" in e}
        if claude_market:
            for name in sorted(set(claude_entries) | set(cursor_entries)):
                if name not in cursor_entries:
                    problems.append(f"{market_file}: plugin {name!r} is in .claude-plugin/marketplace.json but not here")
                elif name not in claude_entries:
                    problems.append(f"{market_file}: plugin {name!r} is not in .claude-plugin/marketplace.json")
                elif cursor_entries[name].get("source") != claude_entries[name].get("source"):
                    problems.append(f"{market_file}: plugin {name!r} source {cursor_entries[name].get('source')!r} differs from .claude-plugin/marketplace.json ({claude_entries[name].get('source')!r})")

    for claude_file in root.glob("plugins/*/.claude-plugin/plugin.json"):
        claude = load(claude_file)
        base = claude_file.parent.parent
        codex_file = base / ".codex-plugin/plugin.json"
        cursor_file = base / ".cursor-plugin/plugin.json"
        codex = load(codex_file)
        cursor = load(cursor_file)
        for data, f in ((codex, codex_file), (cursor, cursor_file)):
            if data is None or claude is None:
                continue
            for key in SHARED_KEYS:
                if data.get(key) != claude.get(key):
                    problems.append(f"{rel(f)}: {key} {data.get(key)!r} differs from {rel(claude_file)} ({claude.get(key)!r})")
        entry = claude_entries.get(claude.get("name") if claude else None)
        if claude is not None and entry is not None and entry.get("version") != claude.get("version"):
            problems.append(f".claude-plugin/marketplace.json: plugin {claude.get('name')!r} version {entry.get('version')!r} differs from {rel(claude_file)} ({claude.get('version')!r})")
        if codex is not None:
            if codex.get("hooks") != CODEX_HOOKS:
                problems.append(f"{rel(codex_file)}: hooks must be the empty inline object {json.dumps(CODEX_HOOKS)} (keeps hooks/hooks.json, the Claude Code mod, from loading)")
            for key in ("skills", "commands", "mcpServers", "apps"):
                value = codex.get(key)
                for path in value if isinstance(value, list) else [value]:
                    if isinstance(path, str) and (not path.startswith("./") or path == "./"):
                        problems.append(f"{rel(codex_file)}: path {path!r} in {key} must start with ./ and name something after it")
            interface = codex.get("interface")
            if entry and entry.get("category") and (not isinstance(interface, dict) or interface.get("category") != entry["category"]):
                problems.append(f"{rel(codex_file)}: interface.category must equal the category of the plugin in .claude-plugin/marketplace.json ({entry['category']!r})")
        if cursor is not None:
            for key in sorted(set(cursor) - CURSOR_PLUGIN_KEYS):
                problems.append(f"{rel(cursor_file)}: key {key!r} is not in the Cursor plugin schema")
            for key in ("skills", "agents"):
                if key in cursor:
                    problems.append(f"{rel(cursor_file)}: must not declare {key!r} (Cursor finds the {key} of a plugin by default)")
            if cursor.get("hooks") != CURSOR_HOOKS:
                problems.append(f"{rel(cursor_file)}: hooks must be the empty inline object {json.dumps(CURSOR_HOOKS)} (keeps hooks/hooks.json, the Claude Code mod, from loading)")

    for plugin in root.glob("plugins/*"):
        for f in plugin.rglob("*"):
            if f.is_file() and f.suffix in {".md", ".json", ".html"} and "superpowers:" in f.read_text():
                problems.append(f"{rel(f)}: references superpowers: (no hard dependency allowed)")

        if (plugin / "NOTICE.md").exists() and not list((plugin / "licenses").glob("*.txt")):
            problems.append(f"{rel(plugin / 'NOTICE.md')}: license texts missing in licenses/")
        for ref in sorted(plugin.glob("reference/*.md")):
            if "CLAUDE_PLUGIN_ROOT" in ref.read_text():
                problems.append(f"{rel(ref)}: must not use CLAUDE_PLUGIN_ROOT (not substituted in files read at runtime)")
        if (plugin / "reference/hosts.md").exists():
            for host in ("claude", "codex", "cursor"):
                part = plugin / f"reference/hosts-{host}.md"
                if not part.exists():
                    problems.append(f"{rel(part)}: missing (hosts.md sends the {host} host to its own part)")

        for skill_dir in sorted(plugin.glob("skills/*")):
            yaml = skill_dir / "agents/openai.yaml"
            if skill_dir.name in MANUAL_ONLY:
                if not yaml.exists():
                    problems.append(f"{rel(yaml)}: missing (Codex needs it to keep a user-only skill from implicit use)")
                elif not has_policy_line(yaml.read_text()):
                    problems.append(f"{rel(yaml)}: must set {POLICY_LINE} on a line (not a comment) under policy:")
            elif skill_dir.name in AUTO_ALLOWED and yaml.exists():
                problems.append(f"{rel(yaml)}: must not exist (this skill may be used implicitly)")

        for f in [*plugin.glob("skills/*/SKILL.md"), *plugin.glob("agents/*.md")]:
            text = f.read_text()
            fm = frontmatter(text)
            for key in ("name", "description"):
                if not fm.get(key):
                    problems.append(f"{rel(f)}: frontmatter missing {key}")
            if "STYLE.md" not in text:
                problems.append(f"{rel(f)}: does not reference STYLE.md")
            if f.parent.name == "agents":
                if "CLAUDE_PLUGIN_ROOT" in text:
                    problems.append(f"{rel(f)}: must not use CLAUDE_PLUGIN_ROOT (not substituted when a host reads the agent as plain text)")
                body = re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S)
                if ROOT_SENTENCE not in body:
                    problems.append(f"{rel(f)}: must say its plugin root is the `Plugin root:` line of its prompt, and what to do without one")
                else:
                    heading = re.search(r"^## ", body, re.M)
                    if heading and body.index(ROOT_SENTENCE) > heading.start():
                        problems.append(f"{rel(f)}: the plugin root sentence must come before the first ## heading")
            if f.name == "SKILL.md":
                disabled = fm.get("disable-model-invocation") == "true"
                skill = f.parent.name
                if fm.get("name") and fm["name"] != skill:
                    problems.append(f"{rel(f)}: frontmatter name must match its folder ({skill})")
                body = re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S)
                if not body.lstrip("\n").startswith(ROOT_LINE + "\n" + ROOT_FALLBACK + "\n"):
                    problems.append(f"{rel(f)}: body must start with the `Plugin root:` line and the line after it that covers hosts without substitution")
                if text.count("CLAUDE_PLUGIN_ROOT") != 1:
                    problems.append(f"{rel(f)}: CLAUDE_PLUGIN_ROOT must appear exactly once (in the first line); write <plugin root>/... elsewhere")
                if text.count("$ARGUMENTS") > 1:
                    problems.append(f"{rel(f)}: $ARGUMENTS must appear at most once")
                lines = body.splitlines()
                at = next((i for i, line in enumerate(lines) if "$ARGUMENTS" in line), None)
                if at is not None:
                    after = next((line for line in lines[at + 1:] if line.strip()), None)
                    if after is None or after.strip() != ARGS_FALLBACK:
                        problems.append(f"{rel(f)}: the line with $ARGUMENTS must be followed by the sentence about the Arguments line")
                if any("${" in line and line != ROOT_LINE for line in text.splitlines()):
                    problems.append(f"{rel(f)}: ${{ may appear only in the Plugin root: line (no other substituted variables)")
                if re.search(r"\$[1-9]|\$ARGUMENTS\[", text):
                    problems.append(f"{rel(f)}: must not use positional argument forms ($1 to $9, $ARGUMENTS[...]): Claude Code substitutes them, so even prose such as '$5' would be replaced")
                if skill in MANUAL_ONLY and not disabled:
                    problems.append(f"{rel(f)}: disable-model-invocation must be true")
                if skill in AUTO_ALLOWED and disabled:
                    problems.append(f"{rel(f)}: disable-model-invocation must not be set")
                if skill in MANUAL_ONLY:
                    parts = re.findall(r"reference/([\w-]+\.md)", text)
                    if not parts:
                        problems.append(f"{rel(f)}: must point to the parts of reference/ it needs")
                    for part in sorted(set(parts)):
                        if not (plugin / "reference" / part).exists():
                            problems.append(f"{rel(f)}: points to reference/{part}, which does not exist")
                if skill in SPAWNING and "reference/hosts.md" not in text:
                    problems.append(f"{rel(f)}: must list reference/hosts.md (it spawns agents or asks the user)")
    return problems


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    problems = validate(root)
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
