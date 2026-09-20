#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json
import re
ROOT=Path(__file__).resolve().parents[1]
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(ROOT),**kwargs)
    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy','same-origin')
        self.send_header('Cross-Origin-Embedder-Policy','require-corp')
        self.send_header('Cache-Control','no-store')
        super().end_headers()
    def log_message(self,*args): pass
    def do_POST(self):
        match=re.fullmatch(r'/results/([a-z0-9-]+)',self.path)
        if not match: self.send_error(404);return
        data=self.rfile.read(int(self.headers['Content-Length']));json.loads(data)
        destination=ROOT/'results'/f'{match[1]}.json'
        destination.write_bytes(data)
        self.send_response(200);self.end_headers();self.wfile.write(b'ok')
        print('Saved',destination.name,flush=True)
print('Listening on http://127.0.0.1:8765/harness/benchmark.html',flush=True)
ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
