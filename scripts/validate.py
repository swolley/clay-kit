#!/usr/bin/env python3
"""Validate the structure of the swolley-kit marketplace and its plugins."""
import json
import re
import sys
from pathlib import Path

MANUAL_ONLY = {"run", "task", "status", "approve", "rework"}
AUTO_ALLOWED = {"brainstorm", "plan"}


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


def validate(root: Path) -> list[str]:
    problems: list[str] = []

    def rel(p: Path) -> str:
        return p.relative_to(root).as_posix()

    manifests = [root / ".claude-plugin/marketplace.json", *root.glob("plugins/*/.claude-plugin/plugin.json")]
    for m in manifests:
        if not m.exists():
            problems.append(f"{rel(m)}: missing")
            continue
        try:
            json.loads(m.read_text())
        except json.JSONDecodeError as e:
            problems.append(f"{rel(m)}: invalid JSON ({e.msg})")

    for plugin in root.glob("plugins/*"):
        for f in plugin.rglob("*"):
            if f.is_file() and f.suffix in {".md", ".json", ".html"} and "superpowers:" in f.read_text():
                problems.append(f"{rel(f)}: references superpowers: (no hard dependency allowed)")

        if (plugin / "NOTICE.md").exists() and not list((plugin / "licenses").glob("*.txt")):
            problems.append(f"{rel(plugin / 'NOTICE.md')}: license texts missing in licenses/")
        ref = plugin / "reference/orchestrator.md"
        if ref.exists() and "CLAUDE_PLUGIN_ROOT" in ref.read_text():
            problems.append(f"{rel(ref)}: must not use CLAUDE_PLUGIN_ROOT (not substituted in files read at runtime)")

        for f in [*plugin.glob("skills/*/SKILL.md"), *plugin.glob("agents/*.md")]:
            text = f.read_text()
            fm = frontmatter(text)
            for key in ("name", "description"):
                if not fm.get(key):
                    problems.append(f"{rel(f)}: frontmatter missing {key}")
            if "STYLE.md" not in text:
                problems.append(f"{rel(f)}: does not reference STYLE.md")
            if f.name == "SKILL.md":
                disabled = fm.get("disable-model-invocation") == "true"
                skill = f.parent.name
                if skill in MANUAL_ONLY and not disabled:
                    problems.append(f"{rel(f)}: disable-model-invocation must be true")
                if skill in AUTO_ALLOWED and disabled:
                    problems.append(f"{rel(f)}: disable-model-invocation must not be set")
                if skill in MANUAL_ONLY and "reference/orchestrator.md" not in text:
                    problems.append(f"{rel(f)}: must point to reference/orchestrator.md")
    return problems


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    problems = validate(root)
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
