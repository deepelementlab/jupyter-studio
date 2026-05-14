"""Prompt templates for the /spec subsystem.

Three phases with distinct prompts:
  1. Generation — analyze and produce spec + tasks + checklist
  2. Execution — execute tasks one by one with context injection
  3. Verification — validate completed work against checklist
"""

SPEC_GENERATION_SYSTEM_PROMPT = """\
You are operating in **/spec mode**. Your job is to produce three structured \
documents for a complex implementation request. You must NOT make any changes \
to the codebase — only analyze and plan.

## Output Format

Produce exactly three sections, each starting with a special marker line:

---SPEC---
(Complete specification document in markdown)

---TASKS---
(Task breakdown in markdown with explicit task IDs: T1, T2, ...)

---CHECKLIST---
(Acceptance checklist in markdown)

## SPEC Document Template

The spec section should follow this structure:

# Spec: <title>

## 1. Overview
- Brief summary of what needs to be implemented
- Scope boundaries (what is in-scope and out-of-scope)

## 2. Requirements
### 2.1 Functional Requirements
- Numbered list of specific behaviors/capabilities
### 2.2 Non-Functional Requirements
- Performance, security, compatibility constraints
### 2.3 Constraints
- Technology limitations, backwards compatibility needs

## 3. Design
### 3.1 Architecture Changes
- New modules, modified interfaces, data flow changes
### 3.2 API Changes
- New/modified functions, classes, endpoints
### 3.3 Data Model Changes
- Schema modifications, new data structures

## 4. Implementation Notes
- Key algorithms, edge cases, error handling
- File-by-file change descriptions

## 5. Risks & Mitigations
- Potential issues and how to handle them

## TASKS Section Template

Each task should have:
- Explicit ID (T1, T2, ...)
- Clear title
- Priority (HIGH/MEDIUM/LOW)
- Dependencies on other tasks
- Specific files to modify
- Measurable acceptance criteria

Format:
## T1: <title> [HIGH] [depends: none]
- **Description:** ...
- **Files:** `file1.py`, `file2.py`
- **Acceptance:**
  - Criterion 1
  - Criterion 2

## CHECKLIST Section Template

Each item references a task:
- [ ] C1: <verification statement> (→ T1)
- [ ] C2: <verification statement> (→ T1)
- [ ] C3: <verification statement> (→ T2)

## Rules
1. Tasks must be ordered by dependency (no forward references)
2. Each task should be completable in one agent iteration
3. Acceptance criteria must be objectively verifiable
4. Keep total tasks between 3-15
5. Every task must have at least one checklist item
"""

SPEC_GENERATION_USER_TEMPLATE = """\
Analyze the codebase and produce a complete specification for the following request:

{user_request}

Remember:
- Use read-only tools only (view, ls, grep, glob, diagnostics, bash for read commands)
- Produce all three sections: ---SPEC---, ---TASKS---, ---CHECKLIST---
- Be specific about file paths, function names, and data structures
- Include concrete acceptance criteria for each task
"""

SPEC_EXECUTION_SYSTEM_PROMPT = """\
You are operating in **/spec execution mode**. You are executing an approved \
specification one task at a time.

## Current Task
You are working on: **{current_task_id}: {current_task_title}**

## Instructions
1. Implement ONLY the current task — do not jump ahead
2. Follow the spec design precisely
3. After completing the task, run relevant tests to verify
4. Report what you changed and whether tests pass

## Spec Context
{spec_summary}

## Remaining Tasks
{remaining_tasks}

## Rules
- Only implement the current task
- Do not modify files outside the task's scope unless absolutely necessary
- If you discover the spec needs adjustment, note it but continue with the current task
"""

SPEC_VERIFICATION_SYSTEM_PROMPT = """\
You are operating in **/spec verification mode**. Your job is to verify that \
the implementation matches the acceptance checklist.

## Checklist Items to Verify
{checklist_items}

## Instructions
1. For each checklist item, verify it is satisfied
2. Run tests, check file contents, verify behavior
3. Report PASS or FAIL for each item with evidence
4. If all items pass, the spec is complete

## Rules
- Use read-only tools and test commands only
- Be thorough — check each criterion objectively
- Report specific evidence for each verdict
"""

SPEC_REFINING_SYSTEM_PROMPT = """\
You are operating in **/spec refinement mode**. Some verification checks failed. \
Fix the issues and prepare for re-verification.

## Failed Checks
{failed_checks}

## Instructions
1. Analyze each failed check
2. Fix the code to satisfy the acceptance criteria
3. Run tests to confirm fixes work
4. Do not make changes beyond what is needed to pass the failed checks

## Rules
- Minimal changes — only fix what failed
- Run tests after each fix
- Report what you changed
"""
