# Hydra — QA fixture card

**Category:** Login auditing

**Fixture mode:** `manual_only`

## Simple test

UI validation only. No credential list or runnable authentication attack is provided.

## Fixture files

- `common/wordlists/synthetic-usernames.txt`

## Safety / limitations

No brute-force execution.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
