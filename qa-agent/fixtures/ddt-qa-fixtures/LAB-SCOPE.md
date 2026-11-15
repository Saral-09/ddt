# DDT.com lab scope (user-provided topology)

- PC1 attacker / DDT machine: `10.10.1.202` — **never target this address**.
- PC2 external-side address: `192.168.1.201`.
- PC2 internal-side address: `10.10.1.201`.
- DDT.com Active Directory server: `10.10.1.200`.

Treat the two PC2 addresses as distinct addresses. Only test an individual address explicitly named in the current request. Do not infer routing, DNS, service availability, or that one address is interchangeable with another. Do not scan `192.168.1.0/24` or `10.10.1.0/24`.

The loopback fixtures (`127.0.0.1`) run on the DDT/Kali machine and are preferred for generic UI and web-tool tests.
