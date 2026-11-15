# Shared file fixture index

| File / directory | Suitable tool examples | Purpose |
|---|---|---|
| `common/images/ddt-exif-sample.jpg` | Exif | Synthetic EXIF metadata with no personal data. |
| `common/documents/ddt-sample-report.docx` | Metagoofil, general file pickers | Synthetic DOCX with QA metadata. |
| `common/documents/ddt-sample-report.pdf` | Metagoofil, general file pickers | Synthetic PDF with QA metadata. |
| `common/forensics/ddt-sample-disk.img` | Foremost | Contains embedded JPEG and ZIP signatures for file carving. |
| `common/pcap/ddt-synthetic-http.pcap` | Tcpdump, capture input validation | Three synthetic Ethernet/TCP packets containing a harmless HTTP request/response; not a Wi-Fi handshake. |
| `common/archive/ddt-sample.zip` | Archive/file input checks | Unencrypted synthetic ZIP. |
| `common/archive/ddt-password-protected.zip` | Fcrackzip | Tiny test-only ZipCrypto archive; password is in `common/archive/PASSWORD.txt`. |
| `common/hashes/md5-test-only.txt` | Hashcat, John, Rainbowcrack | MD5 hash of the known synthetic fixture phrase. |
| `common/hashes/sha1-test-only.txt` | John / compatible hash inputs | SHA1 hash of the same synthetic phrase. |
| `common/repo/` | Gitleaks | Source files with clearly fake QA marker strings. |
| `common/wordlists/web-small.txt` | FFuf, GoBuster | Eight low-volume local paths. |
| `common/wordlists/tiny-fixture-words.txt` | Offline-only hash/archive fixtures | Four entries; contains the known synthetic phrase. |
| `common/rainbowcrack/` | Rtgen, Rtsort, Rainbowcrack | Script to generate a valid tiny disposable `.rt` table if RainbowCrack is installed. |

Fixtures are synthetic and should only be used with the relevant local component. Tool-specific acceptance must be confirmed from DDT's actual source and guide.
