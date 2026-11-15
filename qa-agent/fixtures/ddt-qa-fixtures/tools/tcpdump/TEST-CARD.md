# Tcpdump — QA fixture card

**Category:** Packet capture analysis

**Fixture mode:** `offline_file`

## Simple test

Read `common/pcap/ddt-synthetic-http.pcap` as an offline capture.

## Fixture files

- `common/pcap/ddt-synthetic-http.pcap`

## Safety / limitations

Do not start live capture by default.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
