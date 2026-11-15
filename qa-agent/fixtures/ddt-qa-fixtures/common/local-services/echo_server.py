#!/usr/bin/env python3
"""Single-connection loopback TCP echo fixture; never binds to a LAN interface."""
import socket
HOST, PORT = '127.0.0.1', 18081
with socket.socket() as s:
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT)); s.listen(1)
    print(f'Listening on {HOST}:{PORT}; send one line, Ctrl-C to stop')
    conn, addr=s.accept()
    with conn:
        data=conn.recv(1024)
        conn.sendall(b'DDT-ECHO: '+data)
