# Crunch — QA fixture card

**Category:** Wordlist generation

**Fixture mode:** `offline_small_output`

## Simple test

Generate a tiny two-character sample from a two-character charset; compare with `common/wordlists/crunch-expected.txt`.

## Fixture files

- `common/wordlists/crunch-expected.txt`

## Safety / limitations

Keep output small and local.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
