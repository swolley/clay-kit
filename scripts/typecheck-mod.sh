#!/usr/bin/env bash
# Type-check the progress mod against the engine's own types (development aid).
# Usage: typecheck-mod.sh <a loaded copy of the mod, with .claude-plugin/types laid by the engine>
# The engine lays those types the first time a session loads the mod, and re-lays them on every reload, so keep a copy of
# the `.claude-plugin/types` folder somewhere stable. Needs network for `npx typescript`.
set -euo pipefail
src="$(cd "$(dirname "$0")/../plugins/clay" && pwd)"
loaded="${1:?path to a loaded copy of the mod}"
tmp="$(mktemp -d)"
cp -r "$src/hooks" "$src/types" "$tmp/"
cp -r "$loaded/.claude-plugin" "$tmp/"
echo '{ "extends": "./.claude-plugin/types/tsconfig.json", "include": ["hooks/**/*", "types/**/*"] }' > "$tmp/tsconfig.json"
(cd "$tmp" && npx -y -p typescript tsc -p .)
echo "type check ok"
