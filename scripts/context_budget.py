#!/usr/bin/env python3
"""Static context inventory for clay skills; counts words, not model tokens.

Usage: python3 scripts/context_budget.py [--plugin DIR] [--json]
Does not execute a host, load user files, or change a run.
"""
import argparse
import json
import re
from pathlib import Path

DEFAULT_PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "clay"
HOSTS = ("claude", "codex")
REFERENCE_RE = re.compile(r"reference/([\w-]+\.md)")
QUOTED_MD_RE = re.compile(r"`([\w-]+\.md)`")


def inventory(plugin: Path) -> dict:
    result = {}
    for skill in sorted((plugin / "skills").glob("*/SKILL.md")):
        body = skill.read_text(encoding="utf-8")
        # The SKILL references conditional parts as well; count them separately.
        names = sorted(set(REFERENCE_RE.findall(body)) | {n for n in QUOTED_MD_RE.findall(body) if (plugin / "reference" / n).is_file()})
        always = sorted(set(re.findall(r"<plugin root>/reference/([\w-]+\.md)", body.split("Read `questions.md` only")[0].split("Read these parts")[1].split("Read `")[0]))) if "Read these parts" in body else []
        # Simpler, conservative default for other skills: all mentioned parts.
        if not always:
            always = names
        conditional = sorted(set(names) - set(always))
        def words(path):
            return len(path.read_text(encoding="utf-8").split())
        own = words(skill)
        required = {n: words(plugin / "reference" / n) for n in always}
        optional = {n: words(plugin / "reference" / n) for n in conditional}
        result[skill.parent.name] = {
            "skill_words": own,
            "required": required,
            "conditional": optional,
            "startup_words": own + sum(required.values()),
            "host_startup_words": {
                host: own + sum(required.values()) + (
                    words(plugin / "reference" / f"hosts-{host}.md")
                    if "hosts.md" in required else 0
                )
                for host in HOSTS
            },
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin", type=Path, default=DEFAULT_PLUGIN)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    data = inventory(args.plugin)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return
    print("Static word counts (not tokens; excludes task payloads, agent prompts and runtime diffs)")
    for name, entry in data.items():
        host = " ".join(f"{h}={n}" for h, n in entry["host_startup_words"].items())
        print(f"{name:22} base={entry['startup_words']:5} optional={sum(entry['conditional'].values()):5} {host}")


if __name__ == "__main__":
    main()
