#!/usr/bin/env python3
"""Report 6-word sequences a plugin shares with another checkout (development aid).

Usage: check_overlap.py <other-checkout-dir> [plugin-dir]
The other checkout is read only to compare; nothing from it is copied or stored.
"""
import re
import sys
from pathlib import Path

N = 6
SKIP = {".git", "node_modules", ".venv"}


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def grams(text: str) -> set[tuple[str, ...]]:
    w = words(text)
    return {tuple(w[i : i + N]) for i in range(len(w) - N + 1)}


def files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in {".md", ".html", ".json"} and not SKIP & set(p.parts):
            yield p


def main(argv: list[str]) -> int:
    other = Path(argv[0])
    mine = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "plugins/factory"
    theirs: set[tuple[str, ...]] = set()
    for p in files(other):
        theirs |= grams(p.read_text(errors="ignore"))
    total = 0
    for p in sorted(files(mine)):
        shared = grams(p.read_text(errors="ignore")) & theirs
        total += len(shared)
        if shared:
            print(f"{len(shared):4d}  {p.relative_to(mine)}")
    print(f"total shared {N}-grams: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
