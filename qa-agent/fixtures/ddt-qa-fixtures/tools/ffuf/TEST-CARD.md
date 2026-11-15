# FFuf — QA fixture card

**Category:** Web content discovery

**Fixture mode:** `local_web_only`

## Simple test

Use local web fixture and `common/wordlists/web-small.txt`; set a low request rate if supported.

## Fixture files

- `common/wordlists/web-small.txt`
- `common/targets/localhost-url.txt`

## Safety / limitations

Loopback only; small wordlist.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
