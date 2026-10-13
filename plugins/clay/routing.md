# Reviewer routing

Maps changed paths to review lenses. `code` always runs and is not listed.
A repo can override this table with its own `factory/routing.md`.
Globs: `*` matches within a directory, `**` across directories, `{a,b}` alternatives.
Rules for directories such as `components` or `auth` name code extensions, so a
docs-only change under `docs/components/` does not pull in extra reviewers.

| glob | reviewer |
|------|----------|
| `**/*.{vue,tsx,jsx,svelte,blade.php}` | ui |
| `**/*.{vue,tsx,jsx,svelte,blade.php}` | ux |
| `**/*.{css,scss}` | ui |
| `**/components/**/*.{ts,js}` | ui |
| `**/views/**/*.{php,ts,js}` | ux |
| `**/pages/**/*.{ts,js}` | ux |
| `**/{auth,Auth,middleware,Middleware,policies,Policies}/**/*.{php,py,ts,js,go,rb,java,cs}` | security |
| `**/routes/**/*.{php,py,ts,js,rb}` | security |
| `**/migrations/**/*.{php,py,sql,rb}` | security |
| `**/{composer.json,composer.lock,package.json,package-lock.json,pnpm-lock.yaml,yarn.lock}` | security |
| `**/{go.mod,go.sum,Cargo.toml,Cargo.lock,requirements.txt,pyproject.toml}` | security |
| `**/.env*` | security |
