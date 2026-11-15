# Urlsnarf — QA fixture card

**Category:** HTTP traffic capture

**Fixture mode:** `manual_capture_only`

## Simple test

Use the supplied PCAP only if the component supports offline input; otherwise generate local HTTP traffic and capture loopback manually.

## Fixture files

- `common/pcap/ddt-synthetic-http.pcap`

## Safety / limitations

Live capture requires explicit interface approval.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
