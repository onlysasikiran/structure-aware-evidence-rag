"""Local UI with side-by-side evidence, answers, and generated charts."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json

from .pipeline import run_query
from .reader import answer, answer_ollama


ROOT = Path(__file__).resolve().parents[1]


def make_handler(corpus, budget=110, top_k=12, reader="rule", model="gemma3:4b"):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/api/ask":
                question = parse_qs(url.query).get("q", [""])[0].strip()
                if not question or len(question) > 500:
                    return self.respond(400, b'{"error":"Provide a question of at most 500 characters"}', "application/json")
                trace = run_query(corpus, question, budget, top_k)
                for mode in ("chunk", "expanded", "complete"):
                    trace[mode + "_answer"] = answer(question, trace[mode]) if reader == "rule" else answer_ollama(question, trace[mode], model)
                return self.respond(200, json.dumps(trace).encode(), "application/json; charset=utf-8")
            if url.path in {"/", "/comparison.svg", "/by_type.svg", "/sensitivity.svg"}:
                filename = "web/index.html" if url.path == "/" else "results/" + url.path[1:]
                path = ROOT / filename
                if not path.exists():
                    return self.respond(404, b"Run the evaluate command to generate charts", "text/plain")
                content_type = "text/html; charset=utf-8" if url.path == "/" else "image/svg+xml"
                return self.respond(200, path.read_bytes(), content_type)
            return self.respond(404, b"Not found", "text/plain")

        def respond(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(corpus, port=8000, budget=110, top_k=12, reader="rule", model="gemma3:4b"):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(corpus, budget, top_k, reader, model))
    print(f"Open http://127.0.0.1:{port}/ (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
