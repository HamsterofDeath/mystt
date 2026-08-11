---
name: mobile-game-source-code-review
description: Review mobile game source code, especially Android/Kotlin game projects, for release-quality engineering standards. Use when Codex is asked to review a mobile game codebase, PR, branch, or local changes with goals including Kotlin-only source, at least 90% test coverage for game logic, focused single-purpose classes, maintainable game architecture, or regressions in rules, state, rendering, input, persistence, or build/test setup.
---

# Mobile Game Code Review

## Review Goal

Review the code as a senior mobile game engineer. Prioritize concrete defects, maintainability risks, missing tests, and architecture drift that could affect gameplay, releases, or future iteration.

Use these quality gates:

- Source code should be Kotlin. Treat new Java source in app/game code as a finding unless the project has an explicit exception.
- Logic code should have at least 90% test coverage.
- Each class should have one main purpose. Flag classes that combine unrelated responsibilities such as rendering, input, rules, persistence, audio, ads, networking, and state transitions.

## Workflow

1. Inspect repository instructions first: `AGENTS.md`, README, build files, and nearby docs that define project rules.
2. Determine the review surface: current diff, PR patch, or whole codebase. If the user did not specify, review the current working tree changes first.
3. Identify the platform and test tooling from Gradle/Xcode/build config before running commands.
4. Search source layout with `rg --files`. Exclude generated and build output.
5. Check Kotlin-only compliance:
   - Android: look under `src/main`, `src/test`, and `src/androidTest`.
   - Flag `.java` source under app/game code unless it is generated, third-party, legacy explicitly allowed by docs, or outside the requested review surface.
6. Classify logic code. Logic includes game rules, level validation, state transitions, movement/collision, scoring, serialization, generation, puzzle solvers, economy/progression decisions, and deterministic content selection.
7. Run the narrowest reliable verification command for tests and coverage. Prefer existing Gradle tasks such as `test`, `check`, `jacoco*CoverageVerification`, or project-specific gates. If no coverage gate exists, report that as a gap and inspect available reports or build config.
8. Review class cohesion. Flag files/classes with multiple main reasons to change, especially large Activity/View/Manager classes that also contain game decisions.
9. Review gameplay correctness. Look for invalid level data, unsolved/degenerate puzzles, off-by-one bounds, persistence migration problems, nondeterministic generation, and state replay bugs.
10. Review tests. Ensure changed logic has focused tests, edge cases, regression coverage, and assertions tied to game rules rather than only smoke tests.

## Findings Standard

Lead with findings. Order by severity. Include precise file and line references.

For each finding:

- State the impact first.
- Cite the exact code path or missing test/coverage gate.
- Explain why it violates one of the quality gates or creates a gameplay/release risk.
- Suggest the smallest credible fix.

Use this severity guide:

- `Critical`: crashes, data loss, invalid releases, broken core gameplay, or coverage gate disabled for logic.
- `High`: wrong game rules, progression blockers, unsolvable shipped content, Kotlin-only violations in changed production code, or large mixed-responsibility logic classes.
- `Medium`: missing logic tests, unverified edge cases, architecture drift, brittle persistence, or coverage below target for a logic class.
- `Low`: naming, minor organization, small duplication, or non-blocking cleanup.

If there are no findings, say that clearly and mention residual risk, such as coverage not runnable locally or unreviewed generated assets.

## Coverage Gate

Treat 90% logic coverage as a release gate, not a suggestion.

When coverage is available:

- Prefer per-class or per-package coverage for logic over only project-wide coverage.
- Flag aggregate coverage that hides untested logic classes.
- Check that coverage verification is wired into `check` or the normal CI path.

When coverage is unavailable:

- Report the missing coverage task or report as a finding if logic code exists.
- Recommend a concrete gate, for example JaCoCo/Kover verification scoped to logic packages.

## Kotlin-Only Gate

For Android projects, expect Kotlin files for app and test source. Gradle files may be Kotlin DSL or Groovy depending on the project; do not flag Groovy build scripts unless the project explicitly requires Kotlin DSL.

Do not flag:

- Generated files.
- External vendored code that is clearly isolated.
- Legacy files outside the requested diff when the user asked only for a PR review, but mention them under residual risk if they affect the stated goal.

## Single-Purpose Class Gate

Flag a class when it has multiple main reasons to change. Common mobile game splits:

- Rules/state: pure Kotlin classes with deterministic tests.
- Rendering: views, composables, sprites, shaders, animation.
- Input: touch/controller gesture interpretation.
- Persistence: saves, preferences, serialization adapters.
- Content: level catalog, validators, generators, importers.
- Platform glue: Activity, lifecycle, permissions, ads, store APIs.

Prefer recommending small extracted classes over broad refactors. Tie the extraction to a testable responsibility.
