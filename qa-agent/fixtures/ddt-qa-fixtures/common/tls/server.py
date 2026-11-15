#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body=b'DDT local TLS fixture\n'
        self.send_response(200); self.send_header('Content-Type','text/plain'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, fmt, *args): print('[tls-fixture] '+(fmt % args))
s=HTTPServer(('127.0.0.1',18443),H)
ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain('localhost-cert.pem','localhost-key.pem')
s.socket=ctx.wrap_socket(s.socket,server_side=True)
print('Serving local TLS fixture at https://127.0.0.1:18443')
s.serve_forever()
