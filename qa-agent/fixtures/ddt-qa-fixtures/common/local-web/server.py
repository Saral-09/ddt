#!/usr/bin/env python3
"""Loopback-only inert HTTP fixture server for DDT QA."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import os
ROOT = Path(__file__).resolve().parent
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(ROOT), **kwargs)
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path == '/health':
            body=b'{"status":"ok","fixture":"ddt-qa"}'
            self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == '/search':
            q=parse_qs(parsed.query).get('q',[''])[0]
            body=(f'<html><title>Search fixture</title><body><h1>Search</h1><p>Query: {q}</p></body></html>').encode()
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == '/api/health':
            body=b'{"ok":true,"service":"ddt-fixture-api"}'
            self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == '/private-fixture/':
            self.send_error(403, 'Fixture path intentionally restricted'); return
        if parsed.path == '/': self.path='/index.html'
        if parsed.path == '/about': self.path='/about.html'
        if parsed.path == '/contact': self.path='/contact.html'
        return super().do_GET()
    def log_message(self, fmt, *args): print('[local-web-fixture] '+(fmt % args))
if __name__=='__main__':
    print('Serving DDT fixtures at http://127.0.0.1:18080 (loopback only)')
    ThreadingHTTPServer(('127.0.0.1',18080),Handler).serve_forever()
