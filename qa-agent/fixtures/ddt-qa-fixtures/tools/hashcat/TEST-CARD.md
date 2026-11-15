# Hashcat — QA fixture card

**Category:** Offline hash testing

**Fixture mode:** `offline_file_only`

## Simple test

Use `common/hashes/md5-test-only.txt` with `common/wordlists/tiny-fixture-words.txt`; MD5 mode 0.

## Fixture files

- `common/hashes/md5-test-only.txt`
- `common/wordlists/tiny-fixture-words.txt`

## Safety / limitations

Only synthetic fixture hash.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
