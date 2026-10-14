# Codex Task: Repair Enriched CLO Semantics, Validate, Then Compact Production JSON

## Goal

SkillBridge currently has 49 course directories under `data/stage3/`, with 346 original CLOs. Existing `enriched_clos.json` files pass structural checks but have serious semantic errors. **Repair the current enrichment using the original CLO and mapped topics, preserving already-good outputs. Only after robust QA passes, compact the production JSON to exactly `clo` and `description`.**

You must **perform actual semantic reasoning**. A script that joins, extracts, or paraphrases topic titles without evaluating their relationship to each CLO does not meet this task.

## Context

- Course inputs: `data/stage3/<course_code>/clos.json`, `topics_by_clo.json`.
- Existing result: `data/stage3/<course_code>/enriched_clos.json`.
- Supporting context (only if needed): `metadata.json`.
- QA materials supplied by me: `clo_enrichment_audit.md`, `clo_enrichment_review_queue.json` (read them if attached/copied into the repository).
- Current counts: 49 course directories; 48 have CLOs, 1 is `AI17_GRA_ELE` with zero CLOs; 346 CLOs total.
- Current structural verification: passed. Semantic correctness: **not approved**.

Examples you must independently recheck against sources:

1. **SEG301 CLO3/CLO4**: Topic mapping includes indexing, crawling, BM25/classification under CLOs about keyword research or web analytics. Do not blindly import mismatched topics. Flag the mapping conflict; preserve the original objective when supported additions are absent.
2. **MAD101 CLO1/CLO7/CLO8; MAE101 CLO1/CLO4**: Original CLOs contain detailed sub-LOs; the current enrichment drops important named methods (propositional/predicate logic, Dijkstra, Huffman, DFS/BFS, Prim/Kruskal, Squeeze/Intermediate Value theorems, numerical integration methods). Source details must not be lost.
3. **CPV301 CLO6/CLO7**: Fix `D and 3D` (correct is 2D/3D); remove `Lab 4 assistant and interview`; include image-stitching `Global alignment` if source-supported.
4. **NLP301m CLO7**: Responsible AI-assisted development tools must not be replaced with a laundry list of research-report tasks.
5. **GAP301 CLO1**: Do not use course-introduction and group-formation logistics as skill evidence.
6. **TMG301 CLO1**: Review excessive cross-CLO expansion from introductory text-mining principles to advanced methods and end-user applications.

Positive references: `DBI202/CLO5`, `CSD203/CLO5`, `PFP191/CLO5`, and `AIM301m/CLO5` generally demonstrate useful technical specificity, though still verify them against their actual sources.

## Execution Plan

### Phase 1: Inspect, protect, and plan

1. Read applicable `AGENTS.md` instructions and inspect repository/working tree. Preserve unrelated edits.
2. Inspect the full input schema and all CLO/source-topic mappings. Verify 49/346 counts rather than trusting the old report.
3. Determine whether repository code reads `enriched_clos.json` and would break after a schema change. Plan any necessary backward-compatible change before writing.
4. Create a safe and clearly separated backup of existing full enriched JSON files (in a review/audit location, not overwriting `clos.json` or `topics_by_clo.json`).
5. Explain the batch plan in Vietnamese; use small course batches, and begin with the problem cases listed above plus DBI202.

### Phase 2: Repair semantic enrichment at the course level

For each course, read **all** original CLOs, their topic arrays, and the previous enriched results together. Compare CLO scope across outcomes.

- Preserve the learning objective and cognitive level from the original CLO. `Understand` must not silently become `Develop`, `Implement`, `Optimize`, or production-level competence.
- Treat **all content in the original CLO, including embedded sub-LOs**, as authoritative. Preserve technical methods and named algorithms even if no individual topic title repeats them.
- Add detailed course content only when directly supported by relevant teaching topics.
- Validate whether a topic genuinely belongs to the stated CLO; a topic mapped in JSON can still be semantically misassigned.
- When mapping appears contradictory or irrelevant, do not force it into the outcome. Keep the original CLO or a faithful clear rewrite, and log a specific `mapping_conflict` for human review.
- Remove course logistics (`Welcome`, `Guest speaker`, `Review report`, `Lab assistance`, group formation, tests), teaching schedules, and chapter section numbers from the final learning outcome.
- Do not copy source typos or malformed enumerations into prose.
- Do not include meta commentary such as `The CLO itself names...`, `The outcome remains...` or references to the enrichment process.
- Prefer 1-3 coherent sentences. A short faithful CLO is better than a long topic dump; do not mechanically append `The scope includes...`.
- A CLO that cannot legitimately be enriched should remain close to the original, not be padded.
- Existing high-quality enrichment may be retained as-is after checking it against sources.

### Phase 3: QA gate (before schema changes)

Keep a temporary internal audit representation with fields for original description, corrected description, supporting topic indices, review requirement, and explicit notes. It does not need to live inside the final production JSON.

Run structural checks across all CLOs:
- Exact same original CLO ID set, order, and counts in each course.
- No malformed JSON, duplicate IDs, missing/empty descriptions, or invalid supporting topic references.
- No input file changes.

Run semantic checks on all CLOs; check manually all high-risk audit cases and an appropriate sample across the remaining courses:
- No explicit technical methods from the original CLO have been inadvertently dropped.
- New detailed claims are supported by relevant source topics.
- No unresolved cognitive-level inflation, technology confusion, topic leakage, or administrative labels.
- No malformed phrases or irrelevant lists.
- Clearly label `requires_review` for unresolved source/mapping contradictions rather than marking all records false.

Prepare a review report with passes/failures, changed examples, remaining blockers, and limitations. **Do not claim semantic accuracy percentage without human-validated gold labels.**

If serious semantic issues persist, stop before compacting, report exact blockers, and ask for input only where truly necessary.

### Phase 4: Compact JSON ONLY after QA is acceptable

The desired final file for each course is:

`data/stage3/<course_code>/enriched_clos.json`

with the exact root schema:

```json
[
  {
    "clo": "CLO1",
    "description": "A single coherent enriched academic CLO in English."
  },
  {
    "clo": "CLO2",
    "description": "Another enriched academic CLO."
  }
]
```

Rules:
- **Only** two fields per record: `clo`, `description`. No `course_id`, `clos`, `original_description`, `source_topic_indices`, flags, or other fields in production.
- Do not duplicate a course ID already in the directory name.
- Preserve CLO order. Preserve the empty array for `AI17_GRA_ELE` if this directory still has no CLOs.
- Keep the richer audit record/report in a separate backup/audit location for reproducibility. No need to feed audit detail to the JD matching LLM.
- Identify and adjust dependent code/tests that parse the previous wrapper schema, or state which integrations require migration. Do not silently break consumers.
- Run a final validation of the new two-field schema against all `clos.json` files.

## Done When

1. Every eligible course is semantically reviewed, not just JSON-validated.
2. All severe documented semantic errors are repaired or clearly logged as unresolved blockers; no silent false positives remain in the intended production data.
3. Important original sub-LO contents are preserved, and newly added contents are directly supported by corresponding source topics.
4. No original Stage 3 input is modified.
5. Final compact `enriched_clos.json` exists for each course **only after** the quality gate passes; schema is exactly `[ {"clo": "...", "description": "..."} ]`.
6. The old detailed outputs are backed up, and repository consumer compatibility is checked.
7. You give me a clear Vietnamese final report including changed courses, validation evidence, unresolved mapping conflicts, and any downstream migration work.

Work systematically and prefer correctness to speed. Ask for clarification only if a real source conflict blocks a safe, faithful decision.
