# Reviewer routing

Maps changed paths to review lenses. `code` always runs and is not listed.
A repo can override this table with its own `factory/routing.md`.
Globs: `*` matches within a directory, `**` across directories, `{a,b}` alternatives.
A plain `.js` or `.ts` file is not a screen on its own (a Node project is full of them), so those extensions count only inside `components`, `views` and `pages`.
Rules for directories such as `components` or `auth` name code extensions, so a
docs-only change under `docs/components/` does not pull in extra reviewers.

| glob | reviewer |
|------|----------|
| `**/*.{vue,tsx,jsx,svelte,astro,blade.php,twig,erb,hbs,ejs,pug,html,htm}` | ui |
| `**/*.{vue,tsx,jsx,svelte,astro,blade.php,twig,erb,hbs,ejs,pug,html,htm}` | ux |
| `**/*.{css,scss,sass,less,styl}` | ui |
| `**/components/**/*.{ts,js}` | ui |
| `**/views/**/*.{php,ts,js}` | ux |
| `**/pages/**/*.{ts,js}` | ux |
| `**/{auth,Auth,middleware,Middleware,policies,Policies}/**/*.{php,py,ts,js,go,rb,java,cs}` | security |
| `**/routes/**/*.{php,py,ts,js,rb}` | security |
| `**/migrations/**/*.{php,py,sql,rb}` | security |
| `**/{composer.json,composer.lock,package.json,package-lock.json,pnpm-lock.yaml,yarn.lock}` | security |
| `**/{go.mod,go.sum,Cargo.toml,Cargo.lock,requirements.txt,pyproject.toml}` | security |
| `**/.env*` | security |
