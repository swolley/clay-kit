#!/usr/bin/env python3
"""Report 6-word sequences a plugin shares with another project (development aid).

Run it before publishing, to see how much text the plugin has in common with a project whose license
does not allow copying it. The other project is read only to compare; nothing from it is copied or stored.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

N = 6
ZAZENCODES = "https://github.com/zazencodes/zazencodes-season-3.git"
ZAZENCODES_DIR = "src/software-factory-claude-code"

USAGE = """Usage:
  check_overlap.py --zazencodes [plugin-dir]       download only the zazencodes software factory folder and compare
  check_overlap.py <other-folder> [plugin-dir]     compare with a folder you already have
The plugin folder defaults to plugins/clay. Needs git and network for --zazencodes."""
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


def fetch_zazencodes(into: Path) -> Path | None:
    """Sparse clone of the one folder we compare against, into `into`."""
    steps = [
        ["git", "clone", "--quiet", "--depth", "1", "--filter=blob:none", "--sparse", ZAZENCODES, str(into)],
        ["git", "-C", str(into), "sparse-checkout", "set", ZAZENCODES_DIR],
    ]
    for cmd in steps:
        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode != 0:
            print(f"could not download the zazencodes folder: {done.stderr.strip()[:200]}")
            return None
    return into / ZAZENCODES_DIR


def main(argv: list[str]) -> int:
    if not argv:
        print(USAGE)
        return 2
    if argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    tmp = None
    if argv[0] == "--zazencodes":
        tmp = tempfile.TemporaryDirectory()
        other = fetch_zazencodes(Path(tmp.name) / "zz")
        if other is None:
            tmp.cleanup()
            return 2
    else:
        other = Path(argv[0])
    rest = argv[1:]
    if not other.is_dir():
        print(f"{other}: not a folder")
        return 2
    mine = Path(rest[0]) if rest else Path(__file__).resolve().parent.parent / "plugins/clay"
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
    if tmp:
        tmp.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
