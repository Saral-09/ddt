# Local service fixtures

- HTTP fixture: `python3 ../local-web/server.py` at `127.0.0.1:18080`.
- TCP echo fixture: `python3 echo_server.py` at `127.0.0.1:18081`; it accepts one connection and echoes one payload.

Both bind only to loopback. No FTP, SMB, SNMP, LDAP, wireless AP or vulnerable web server is created by this pack. Those require a separately configured lab service.
