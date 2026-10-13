#!/usr/bin/env bash
# Create a tiny git repo to exercise the factory: a backend task, a UI task and a task that must escalate.
set -euo pipefail
dir="${1:?usage: make_fixture.sh <empty-dir>}"
mkdir -p "$dir" && cd "$dir"
git init -q -b main
git config user.name fixture && git config user.email fixture@example.com

mkdir -p app/auth ui tests docs/superpowers/plans
cat > AGENTS.md <<'EOF'
# Fixture repo
- Setup for a fresh checkout: none.
- Tests: `python3 -m unittest discover -s tests -v`
- No lint, no build, no dev server.
- Chat in English. Keep changes small.
EOF
cat > app/util.py <<'EOF'
def title_case(text: str) -> str:
    return " ".join(w.capitalize() for w in text.split())
EOF
cat > app/auth/session.py <<'EOF'
SESSION_MINUTES = 30


def is_expired(age_minutes: int) -> bool:
    return age_minutes >= SESSION_MINUTES
EOF
cat > ui/Greeting.vue <<'EOF'
<template>
  <p class="greeting">Hello</p>
</template>
EOF
cat > tests/test_util.py <<'EOF'
import sys
import unittest

sys.path.insert(0, "app")
from util import title_case  # noqa: E402


class TitleCase(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(title_case("hello world"), "Hello World")
EOF
cat > tests/test_session.py <<'EOF'
import sys
import unittest

sys.path.insert(0, "app/auth")
from session import is_expired  # noqa: E402


class Session(unittest.TestCase):
    def test_expires_at_limit(self):
        self.assertTrue(is_expired(30))
EOF
cat > docs/superpowers/plans/2026-10-13-fixture-plan.md <<'EOF'
# Fixture Plan

**Goal:** exercise routing, escalation and resume.

**Spec:** none (fixture)

### Task 1: Add slugify helper

**Repo:** fixture
**Tier:** light
**Files:** `app/util.py`, `tests/test_util.py`
**Accept:** 1. `slugify("Hello World")` returns `hello-world`. 2. Existing tests still pass.
**Verify:** `python3 -m unittest discover -s tests -v`

- [ ] **Step 1: Write the failing test** `test_slugify` in `tests/test_util.py`
- [ ] **Step 2: Implement `slugify(text: str) -> str`** in `app/util.py`
- [ ] **Step 3: Run the tests; expect pass**

### Task 2: Add a subtitle to the greeting

**Repo:** fixture
**Tier:** medium
**Depends:** 1
**Files:** `ui/Greeting.vue`
**Accept:** 1. The component renders a `<small class="subtitle">` below the greeting.
**Verify:** read the file; no test runner for the UI in this fixture.

- [ ] **Step 1: Add the subtitle element** to `ui/Greeting.vue`
- [ ] **Step 2: Check the template is still valid**

### Task 3: Extend the session lifetime

**Repo:** fixture
**Tier:** careful
**Depends:** 1
**Files:** `app/auth/session.py`, `tests/test_session.py`
**Accept:** 1. `SESSION_MINUTES` is 60. 2. A session of 45 minutes is not expired.
**Verify:** `python3 -m unittest discover -s tests -v`

- [ ] **Step 1: Write the failing test** `test_not_expired_at_45` in `tests/test_session.py`
- [ ] **Step 2: Change `SESSION_MINUTES` to 60** in `app/auth/session.py`
- [ ] **Step 3: Run the tests; expect pass**
EOF
cat > docs/superpowers/plans/2026-10-13-fixture-legacy.md <<'EOF'
# Fixture Legacy Plan

## Task 1: Add a reverse helper

- [ ] **Step 1: Write the failing test** `test_reverse` in `tests/test_util.py`
- [ ] **Step 2: Implement `reverse(text: str) -> str`** in `app/util.py`
- [ ] **Step 3: Run the tests; expect pass**
EOF
printf 'factory/jobs/\n__pycache__/\n' > .gitignore
git add -A && git commit -q -m "fixture: initial state"
python3 -m unittest discover -s tests >/dev/null 2>&1 && echo "fixture ready at $dir (baseline tests pass)"
