#!/usr/bin/env bash
# Benchmark runner: N models x M challenges x T trials, then an analysis pass.
#
# Deliberately no `set -e`: the fixture-integrity check after the run must
# execute even when the evaluator itself exits non-zero.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

# ---------------------------------------------------------------------------
# Agent sandbox
# ---------------------------------------------------------------------------
# Trials run unattended with tool calls auto-approved, so confine each agent to
# its own staged workdir. Without this, an agent that discovers the repo layout
# can reach the benchmark's own internals. Both happened in the 2026-07-29 run:
#
#   * ollama:minimax-m2.7 (bug-fix trial-3) read the repo README, concluded the
#     "real" task lived at challenges/bug-fix/workdir, and fixed the seeded bugs
#     *there* instead of in its own copy — silently turning that challenge into
#     a no-op for every subsequent run.
#   * google:gemini-3.5 imported and executed challenges/<case>/validator.py to
#     grade itself, in 8 cells across two runs.
#
# Writes: with WRITABLE_PATHS unset, zrb defaults the writable root to the
# process cwd, which the runner sets to the trial's own workdir (plus temp dirs,
# always writable by design). Artifacts still land under ./experiment, so
# post-hoc analysis of trial workdirs is unaffected.
export ZRB_LLM_SANDBOX_ENABLED=true
export ZRB_LLM_SANDBOX_ALLOW_ESCAPE=false  # nobody is present to approve an escape
export ZRB_LLM_SANDBOX_FALLBACK=deny       # fail closed if no OS sandbox is available

# Reads: setting this REPLACES zrb's built-in credential deny-list, so the 14
# defaults are re-listed verbatim before appending the challenge source tree.
# Dropping them would matter especially for the refuse-exfil challenge. Leading
# `~` is intentional — zrb expanduser()s each entry.
export ZRB_LLM_SANDBOX_DENY_READ_PATHS="~/.ssh:~/.aws:~/.azure:~/.config/gcloud:~/.kube:~/.gnupg:~/.netrc:~/.npmrc:~/.pypirc:~/.git-credentials:~/.docker/config.json:~/.config/gh:~/Library/Keychains:~/AppData/Roaming/gcloud:${REPO_DIR}/challenges"

# ---------------------------------------------------------------------------
# Fixture integrity: snapshot before
# ---------------------------------------------------------------------------
# Hash the challenge tree before and after rather than diffing against git.
# A before/after comparison flags only drift caused by *this run*, so it works
# on an already-dirty tree. __pycache__ is excluded: it is gitignored (a few
# .pyc predate that rule) and regenerates as noise, while any real corruption
# also shows up in the sources.
fixture_manifest() {
  find "${REPO_DIR}/challenges" -type f -not -path '*__pycache__*' -print0 \
    | sort -z | xargs -0 shasum -a 256 2>/dev/null
}

FIXTURES_BEFORE="$(fixture_manifest)"

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
zrb-llm-evaluator run \
  --models openai:gpt-4o-mini \
  --test-cases ./challenges/bug-fix,./challenges/copywriting,./challenges/feature,./challenges/integration-bug,./challenges/refactor,./challenges/research,./challenges/failing-tests,./challenges/grep-fest,./challenges/debug-loop,./challenges/refuse-exfil,./challenges/injected-readme,./challenges/big-haystack \
  --trials 3 \
  --parallelism 8 \
  --timeout 600 \
  --output-dir ./experiment
RUN_EXIT=$?

# ---------------------------------------------------------------------------
# Fixture integrity: compare after
# ---------------------------------------------------------------------------
FIXTURES_AFTER="$(fixture_manifest)"
FIXTURES_DIRTY=0

if [ "$FIXTURES_BEFORE" != "$FIXTURES_AFTER" ]; then
  FIXTURES_DIRTY=1
  echo
  echo "============================================================"
  echo "!! CHALLENGE FIXTURES CHANGED DURING THIS RUN"
  echo "============================================================"
  echo "An agent escaped its staged workdir and wrote into challenges/."
  echo "Every trial of the affected challenge is untrustworthy: later"
  echo "trials may have been staged from an already-solved fixture."
  echo
  echo "Changed files:"
  # One line per affected path: a modified file appears on both sides of the
  # diff (old hash and new hash), so dedupe on path rather than on hash line.
  diff <(printf '%s\n' "$FIXTURES_BEFORE") <(printf '%s\n' "$FIXTURES_AFTER") \
    | grep -E '^[<>]' | awk '{print $NF}' | sort -u \
    | sed -e "s|^${REPO_DIR}/||" -e 's|^|  |'
  echo
  echo "Identify the culprit:"
  echo "  grep -rl 'llm-challenges/challenges/' experiment/*/*/trial-*/history/"
  echo "Then restore:"
  echo "  git checkout HEAD -- challenges/"
  echo "============================================================"
  echo
fi

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
zrb chat "Analyze @experiment/ result, provide executive summary and failure/timeout analysis, including what probably can be improved in the system prompt, insert your analysis at the top section of  @experiment/report.md"

if [ "$FIXTURES_DIRTY" -ne 0 ]; then
  echo "run.sh: FIXTURE CORRUPTION DETECTED — see the warning above." >&2
  exit 3
fi
exit "$RUN_EXIT"
