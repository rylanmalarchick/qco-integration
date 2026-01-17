# AgentBible Development Notes

Feedback from AI agent development on qco-integration project.

## Overview

This document captures what worked well and what could be improved when using AgentBible principles and tooling during development. Intended to inform future AgentBible releases.

---

## Phase 1: Integration Layer Infrastructure

### Session 1: Project Scaffolding (Setup Phase)

**Date:** 2026-01-16

#### What Worked Well

1. **`bible audit` CLI** - Extremely useful for validating code structure before committing. Caught issues early.

2. **Template structure** - The `python_research` template provided a solid starting point. The pyproject.toml template with ruff/mypy/pytest configuration saved significant setup time.

3. **`.cursorrules` template** - Having project-specific rules in a file I can read at session start helps maintain consistency. The "Rule of 50" and "Test Before Code" reminders are valuable guardrails.

4. **Quantum domain validators** - `validate_unitary`, `validate_hermitian`, `validate_density_matrix` are exactly what's needed for this quantum computing project. Having these pre-built saves implementation time and ensures correctness.

5. **Structured error messages** - The `PhysicsConstraintError` hierarchy with `expected`, `got`, `reference`, and `guidance` fields produces excellent error messages that help debug issues quickly.

#### What Could Be Improved

1. **Package name discovery** - I initially tried `pip install agent-bible` (with hyphen) when the actual package is `agentbible` (no hyphen). Consider adding a PyPI redirect or mentioning this in documentation prominently.

2. **CLI entry point** - `bible` command wasn't available after pip install; had to use `python -m agentbible.cli.main`. This might be a packaging issue or intentional, but `bible audit` would be more ergonomic than the module path.

3. **Template for existing projects** - The `bible init` command creates new projects, but there's no `bible retrofit` or similar for adding AgentBible structure to existing projects. I manually copied patterns from the template.

4. **Context window management** - The `bible context` command is interesting but I didn't use it much. Would be helpful if it could generate a condensed "project summary" optimized for AI context windows.

5. **Validation level environment variable** - `AGENTBIBLE_VALIDATION_LEVEL` is great, but I had to dig through source code to find it. Could be more prominent in docs.

#### Suggestions for New Features

1. **`bible scaffold`** - Generate stub files for a module with proper docstrings, type hints, and test file. E.g., `bible scaffold src/bridge.py --class CircuitOptimizerBridge`

2. **`bible check-coverage`** - Quick command to verify test coverage meets threshold without running full pytest-cov.

3. **Integration with pre-commit** - A pre-packaged `.pre-commit-config.yaml` that runs `bible audit` alongside ruff/mypy.

4. **Metrics dataclass generator** - For research projects, we often need many `@dataclass` definitions. A helper that generates validated dataclasses from a schema would be useful.

---

## Session 2: Phase 1 Implementation

**Date:** 2026-01-16

*Notes to be added as implementation progresses...*

---

## General Observations

### The 5 Principles in Practice

| Principle | Effectiveness | Notes |
|-----------|--------------|-------|
| Correctness First | High | Physics validators enforce this automatically |
| Specification Before Code | Medium | Easy to forget; need more tooling reminders |
| Fail Fast with Clarity | High | Error hierarchy is excellent |
| Simplicity by Design | Medium | Rule of 50 helps but easy to ignore |
| Infrastructure Enables Speed | High | Pre-configured tooling is a huge time saver |

### What Would Help Most

1. **More aggressive reminders** - When I'm about to write a function, a prompt like "Have you written the test first?" would help enforce Principle 2.

2. **Automatic docstring validation** - `bible audit` checks for docstring presence but not quality. Could validate Google-style format, check for Args/Returns sections, etc.

3. **Research-specific templates** - More domain templates beyond `python-scientific` and `cpp-hpc-cuda`. E.g., `python-ml`, `python-quantum`, `python-simulation`.

