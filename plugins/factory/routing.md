# Reviewer routing

Maps changed paths to review lenses. `code` always runs and is not listed.
A repo can override this table with its own `factory/routing.md`.
Globs: `*` matches within a directory, `**` across directories.

| glob | reviewer |
|------|----------|
| `**/*.vue` | ui |
| `**/*.vue` | ux |
| `**/*.tsx` | ui |
| `**/*.tsx` | ux |
| `**/*.jsx` | ui |
| `**/*.jsx` | ux |
| `**/*.svelte` | ui |
| `**/*.svelte` | ux |
| `**/*.blade.php` | ui |
| `**/*.blade.php` | ux |
| `**/*.css` | ui |
| `**/*.scss` | ui |
| `**/components/**` | ui |
| `**/views/**` | ux |
| `**/pages/**` | ux |
| `**/auth/**` | security |
| `**/Auth/**` | security |
| `**/middleware/**` | security |
| `**/Middleware/**` | security |
| `**/policies/**` | security |
| `**/Policies/**` | security |
| `routes/**` | security |
| `**/migrations/**` | security |
| `composer.json` | security |
| `composer.lock` | security |
| `package.json` | security |
| `package-lock.json` | security |
| `pnpm-lock.yaml` | security |
| `go.mod` | security |
| `Cargo.toml` | security |
| `.env*` | security |
