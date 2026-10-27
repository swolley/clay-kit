# Measuring clay-kit runs (baseline)

Jev is out of scope. The benchmark helper is deliberately **read-only** with
respect to clay state and does not spawn agents or change workflow decisions.

## 1. Static instruction inventory

From the clay-kit checkout:

```sh
python3 scripts/context_budget.py
python3 scripts/context_budget.py --json
```

Counts are **words**, not tokens. They do not include the repository, runtime
prompts, repeated invocations, or cache usage.

## 2. Run benchmark (Claude Code first)

From the target repository, using the helper in your clay-kit checkout:

```sh
python3 /path/to/clay-kit/scripts/benchmark.py start --root . --name simple_01 --host claude --mode full
```

Start a fresh Claude Code session, record `/cost` if supported, and execute
a normal `/factory-task` or `/factory-run`. Keep host, model, effort,
repository revision and task difficulty comparable across runs.

**Important:** `factory-run` may clean `factory/jobs` at completion.
Capture the final snapshot **before** its cleanup, or pause the run at the
final approval boundary and capture there. Otherwise the report will not
contain completed jobs. This helper does not automatically intercept cleanup.

```sh
python3 /path/to/clay-kit/scripts/benchmark.py finish --root . --name simple_01
python3 /path/to/clay-kit/scripts/benchmark.py report --root . --name simple_01
```

If the host provides a session cost before and after the run, pass both
numbers in USD to `finish`:

```sh
python3 /path/to/clay-kit/scripts/benchmark.py finish --root . --name simple_01 --session-cost-before 0.12 --session-cost-after 0.49
```

**Do not add the agent usage fields to the session cost.** The host may
already include them. A `/cost` delta is a *session* measurement, not a
clay-only measurement if unrelated work occurred.

The result is stored in `factory/benchmarks/simple_01.json` in the target
repository, outside clay's temporary jobs folder. This file may include
job metadata, model identifiers and execution history: review before sharing
or committing. Add `factory/benchmarks/` to the target repository's
`.gitignore` if you do not want it tracked.

## 3. Send back

Share the benchmark JSON, the task text, host/model/effort, whether the run
completed, and `/cost` output if available. For each task repeat at least
three times before treating small differences as significant.

## Known limitations

- No automatic token attribution to the orchestrator.
- No measured cache reads/writes unless a host records them in job agents.
- No automatic detection of unrelated session activity.
- Snapshot is only as complete as the files still present at `finish`.
- Results across different model vendors are not directly comparable.
- No performance improvement is claimed by adding these tools.

The next implementation step, **after baseline collection**, is per-role
usage attribution with explicit missing-data reporting.
