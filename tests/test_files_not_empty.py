import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Files that are legitimately empty (none today). Add a path here only on purpose.
ALLOWED_EMPTY: set[str] = set()


def test_no_tracked_text_file_is_empty():
    names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    empty = [n for n in names if n and (ROOT / n).is_file() and (ROOT / n).stat().st_size == 0 and n not in ALLOWED_EMPTY]
    assert empty == [], f"empty files (a rewrite that truncated them?): {empty}"
