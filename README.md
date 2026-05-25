# LLM Challenges

A benchmark suite for evaluating how well LLM-driven coding agents handle
realistic software engineering tasks via the [`zrb`](https://github.com/state-alchemists/zrb)
framework and [`zrb-llm-evaluator`](https://github.com/state-alchemists/zrb-llm-evaluator)
test runner.

## What's in this repo

- `challenges/` — the test cases. Each subdirectory is a self-contained
  scenario that the runner stages into an isolated working directory before
  invoking `zrb chat`.
- `experiment/` — outputs from past runs (per-cell logs, conversation
  histories, validator results, and aggregated reports).

### Challenge layout

```
challenges/<name>/
├── instruction.txt   # prompt sent to the LLM
├── workdir/          # scaffolding files staged into the trial cwd
└── validator.py      # exposes a `validator` implementing ValidatorProtocol
```

### Current challenges

- `bug-fix` — locate and fix a defect in existing code.
- `copywriting` — produce written content against a spec.
- `feature` — implement a new capability end-to-end.
- `integration-bug` — diagnose a defect that spans multiple components.
- `refactor` — restructure code while preserving behavior.
- `research` — investigate a question and report findings.

## How evaluation works

`zrb-llm-evaluator` builds a grid of `model × test_case × trial` cells and,
for each cell:

1. Stages the challenge's `workdir/` into `experiment/<model>/<test_case>/trial-N/`.
2. Runs `zrb chat --interactive false --message <instruction>` in that
   directory.
3. Invokes the challenge's `validator.py` against the resulting files and
   conversation log.
4. Writes `experiment/results.json` atomically after each trial, plus a
   final `experiment/report.md`.

Resume support is automatic — re-running with the same `--output-dir` skips
cells whose status is already terminal.

### Running the suite

**Prerequisite:** `zrb-llm-evaluator` installed (`pipx install zrb-llm-evaluator`
or `poetry install` from its repo). `zrb` itself must be on PATH and
configured with the appropriate API keys.

Full grid across frontier-API baselines and locally-pulled Ollama Cloud
models (verify identifiers in [pydantic-ai](https://ai.pydantic.dev/models/)
and [ollama.com/search?c=cloud](https://ollama.com/search?c=cloud) — cloud
names rotate):

```bash
zrb-llm-evaluator run \
  --models openai:gpt-5.4-mini,openai:gpt-4o,google:gemini-2.5-flash,google:gemini-3-flash-preview,google:gemini-3.5-flash,deepseek:deepseek-v4-flash,ollama:gemma4:31b-cloud,ollama:qwen3.5:397b-cloud,ollama:qwen3-next:80b-cloud,ollama:qwen3-coder-next:cloud,ollama:glm-4.7:cloud,ollama:glm-5:cloud,ollama:glm-5.1:cloud,ollama:kimi-k2.5:cloud,ollama:kimi-k2.6:cloud,ollama:minimax-m2.5:cloud,ollama:minimax-m2.7:cloud,ollama:gpt-oss:120b-cloud \
  --test-cases ./challenges/bug-fix,./challenges/copywriting,./challenges/feature,./challenges/integration-bug,./challenges/refactor,./challenges/research \
  --trials 3 \
  --parallelism 8 \
  --timeout 600 \
  --output-dir ./experiment
```

Some Ollama Cloud models do not support parallel tool calls and benefit from
lower parallelism. Run them in a dedicated pass against the same
`--output-dir` so resume support fills in just those cells:

```bash
zrb-llm-evaluator run \
  --models ollama:glm-4.7:cloud,ollama:minimax-m2.7:cloud \
  --test-cases ./challenges/bug-fix,./challenges/copywriting,./challenges/feature,./challenges/integration-bug,./challenges/refactor,./challenges/research \
  --trials 3 \
  --parallelism 1 \
  --timeout 300 \
  --output-dir ./experiment
```

Quick smoke test (single model, single challenge, one trial):

```bash
zrb-llm-evaluator run \
  --models openai:gpt-4o \
  --test-cases ./challenges/bug-fix \
  --trials 1 \
  --parallelism 1 \
  --timeout 120 \
  --output-dir ./experiment
```

Regenerate the Markdown report from existing results without re-running:

```bash
zrb-llm-evaluator report --dir ./experiment
```

## Reading the results

Open `experiment/report.md` (or inspect `experiment/results.json` directly).

| Status      | Meaning                                                          |
|-------------|------------------------------------------------------------------|
| `EXCELLENT` | All checks passed, including the stricter optional ones.         |
| `PASS`      | Core criteria met; stricter bar missed.                          |
| `FAIL`      | Validator rejected the output.                                   |
| `TIMEOUT`   | Subprocess hit `--timeout`; output preserved as far as it got.   |
| `ERROR`     | Validator raised, or `zrb` exited non-zero with no marker.       |

Per-cell forensics live under `experiment/<model>/<test_case>/trial-N/`:

- `chat.log` — combined stdout/stderr
- `history/<session>.json` — `ZRB_LLM_HISTORY_DIR` recording
- Any files the model produced (validators read from this directory)

## Adding a new challenge

1. Create `challenges/<name>/`.
2. Add `instruction.txt` — the prompt for the agent.
3. Add `workdir/` — the initial files the agent will see in its cwd.
4. Add `validator.py` exposing a top-level `validator` object that
   implements `ValidatorProtocol` (see
   `zrb_llm_evaluator.protocols.ValidatorProtocol`). Return a
   `ValidationResult` with `status`, `score`, and `details`.

Minimal validator template:

```python
from pathlib import Path
from zrb_llm_evaluator.models import ValidationCheck, ValidationResult
from zrb_llm_evaluator.protocols import ValidatorProtocol


class MyValidator:
    def validate(self, output_dir: Path, log_content: str) -> ValidationResult:
        produced = (output_dir / "expected_artifact.md").is_file()
        return ValidationResult(
            status="PASS" if produced else "FAIL",
            score=1.0 if produced else 0.0,
            details=[
                ValidationCheck(
                    name="expected_artifact",
                    passed=produced,
                    message="expected_artifact.md present" if produced
                            else "expected_artifact.md not produced",
                ),
            ],
        )


validator = MyValidator()
```

The framework validates protocol conformance at load time — a `validator.py`
that doesn't implement `ValidatorProtocol` is rejected before any trial runs.

# Experiment Result

See the report [here](./experiment/report.md).
