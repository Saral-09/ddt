# Instructions for using the fixture pack

1. Discover the selected DDT tool from the registered routes.
2. Read `tools/<tool-slug>/TEST-CARD.md` and `fixture.json`.
3. Inspect the live React component and the tool guide; those sources control actual field names, accepted input formats, file pickers, dependencies and arguments.
4. Match form fields by labels/accessibility metadata. Never guess a selector or write values into an unrelated field.
5. Use `common/` fixtures only when their type matches the component input. For native Tauri file dialogs, use the approved fixture-selection mechanism; do not assume browser `setFiles()` can control a native dialog.
6. Before a file-based test, resolve fixture paths to absolute paths and verify that files exist and are readable. Use disposable copies for tools that modify input files.
7. For network tools, prefer the loopback web/TCP/TLS fixtures. Use a lab IP only if the user explicitly names that host in the current task. Never target 10.10.1.202 (the attacker machine). Never expand to a subnet.
8. If a tool requires credentials, hardware, an API key, a capture, a vulnerable service, privileged execution or a valid binary format that is not included, do not fabricate it. Report a test gap or blocker.
9. Do not execute DoS, brute-force, credential attacks, ARP poisoning, wireless attacks, payload generation, exploitation, or destructive actions. For such tools, test form validation and safe command previews only.
10. Never treat a `TEST-CARD.md` command idea as permission to execute. The runner's allowlist and operator approval remain mandatory.
11. Do not mark UI automation passed solely because a field was populated. Verify the rendered value, validation state, generated arguments and resulting output where possible.
