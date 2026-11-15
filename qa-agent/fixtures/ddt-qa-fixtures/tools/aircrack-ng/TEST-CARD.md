# Aircrack NG — QA fixture card

**Category:** Wireless capture analysis

**Fixture mode:** `offline_capture_only`

## Simple test

Use the supplied synthetic PCAP only to verify file selection/error handling; it is not a WPA handshake. A separate captured lab handshake is required for meaningful analysis.

## Fixture files

- `common/pcap/ddt-synthetic-http.pcap`

## Safety / limitations

No cracking or capture collection included.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
