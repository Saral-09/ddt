# SearchSploit — QA fixture card

**Category:** Exploit database search

**Fixture mode:** `offline_search_only`

## Simple test

Search a harmless product string such as `OpenSSH` in the local Exploit-DB index. Do not execute exploit code.

## Fixture files

- `common/text/sample.txt`

## Safety / limitations

Search only; no exploit execution.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
