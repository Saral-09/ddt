# RainbowCrack / rtgen / rtsort fixtures

There is intentionally no fake `.rt` file in this archive: Rtsort expects a valid RainbowCrack table, and a fabricated placeholder would be misleading.

To create a small disposable fixture manually (requires `rtgen` and `rtsort` installed):

```bash
cd common/rainbowcrack
chmod +x generate-disposable-table.sh
./generate-disposable-table.sh ./rtsort-fixture-output
```

The script uses the documented argument form `rtgen hash_algorithm charset plaintext_len_min plaintext_len_max table_index chain_len chain_num part_index` with a deliberately tiny 20x20 test table. It writes only inside the selected output directory. Sorting mutates generated files, so use only this disposable directory.

Source for syntax: Kali RainbowCrack tool documentation: https://www.kali.org/tools/rainbowcrack/
