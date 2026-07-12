---
name: export-analysis-result
description: >-
  Export a completed Field_2026_Social analysis output as one or more real validated and sealed
  analysis_exchange bundles. Invoke explicitly with /export-analysis-result <analysis-output-path>.
  Delegates classification and publication to the analysis-result-bridge subagent; it does not merely
  summarize files or infer biological meaning from reports.
version: 0.1.0
---

# Export analysis result

## Invocation

```text
/export-analysis-result path/to/analysis/output
```

The argument is required and must identify an existing analysis run or output directory.

## Action

Delegate the supplied path to the project subagent `analysis-result-bridge`. In Claude Code, use the
Task tool with `subagent_type: analysis-result-bridge` and include the exact user-supplied path.

The subagent must inspect machine-readable outputs and provenance, classify each scientific object,
create actual staging bundles, validate them, publish coherent bundles through the bridge CLI, verify
their seals, and report the published paths. A prose summary without a bundle is a failed invocation.

## Required result

Return:

1. each bundle ID and object type;
2. published path, or staging path plus blockers if it cannot be published;
3. allowed claim and forbidden promotions;
4. payloads included or referenced;
5. validation warnings;
6. fields or outputs deliberately not mapped.

Do not edit `analysis_exchange/published/`, combine different object types, promote computational
candidates, or convert aggregate/observation results into episodes.

