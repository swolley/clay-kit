#!/usr/bin/env python3
"""Choose review lenses from the paths a change touched, using routing.md."""
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ORDER = ["code", "security", "ux", "ui"]


@dataclass(frozen=True)
class Rule:
    glob: str
    reviewer: str


def _regex(glob: str) -> re.Pattern[str]:
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif glob.startswith("**", i):
            out += ".*"
            i += 2
        elif glob[i] == "*":
            out += "[^/]*"
            i += 1
        elif glob[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(glob[i])
            i += 1
    return re.compile(out + r"\Z")


def load_rules(path: Path) -> list[Rule]:
    rules = []
    for line in path.read_text().splitlines():
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if line.strip().startswith("|") and len(cells) == 2 and cells[1] in ORDER[1:]:
            rules.append(Rule(cells[0], cells[1]))
    return rules


def route(paths: list[str], rules: list[Rule]) -> list[str]:
    chosen = {"code"}
    compiled = [(_regex(r.glob), r.reviewer) for r in rules]
    for p in paths:
        p = p.replace("\\", "/")
        if p.startswith("./"):
            p = p[2:]
        for rx, reviewer in compiled:
            if rx.match(p):
                chosen.add(reviewer)
    return [r for r in ORDER if r in chosen]


def main(argv: list[str]) -> int:
    table = Path(argv[argv.index("--table") + 1]) if "--table" in argv else Path(__file__).resolve().parent.parent / "plugins/factory/routing.md"
    paths = [ln.strip() for ln in sys.stdin if ln.strip()]
    print(json.dumps(route(paths, load_rules(table))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
