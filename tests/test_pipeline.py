import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen

from rag_evidence.evaluation import ROOT, evaluate, has_complete_gold, write_results
from rag_evidence.html_units import flatten_and_complete
from rag_evidence.pipeline import Corpus, deliver_complete, run_query
from rag_evidence.reader import answer
from rag_evidence.server import make_handler
from rag_evidence.visualize import render


class EvidencePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = Corpus(ROOT / "data")

    def test_same_retrieval_and_budget(self):
        trace = run_query(self.corpus, "What is the Monthly refund limit for Premium?")
        self.assertIn("refunds.html", [hit["source"] for hit in trace["retrieval"]])
        for mode in ("chunk", "expanded", "complete"):
            self.assertLessEqual(sum(item["tokens"] for item in trace[mode]), trace["budget"])
        self.assertIsNone(answer(trace["question"], trace["chunk"]))
        self.assertEqual(answer(trace["question"], trace["complete"]), "INR 1,000")

    def test_structure_restores_nested_section_and_header_spans(self):
        html = """<h1>Policy</h1><h2>International</h2><table><thead>
        <tr><th rowspan=\"2\">Plan</th><th colspan=\"2\">Limits</th></tr>
        <tr><th>Monthly</th><th>Annual</th></tr></thead><tbody>
        <tr><td>Premium</td><td>INR 1,000</td><td>INR 10,000</td></tr></tbody></table>"""
        _, units = flatten_and_complete(html, "test.html")
        self.assertEqual(len(units), 1)
        self.assertIn("Section: International", units[0].text)
        self.assertIn("Limits / Monthly: INR 1,000", units[0].text)
        self.assertIn("Limits / Annual: INR 10,000", units[0].text)

    def test_no_facts_from_unretrieved_pages(self):
        hits = self.corpus.retrieve("What is the Monthly refund limit for Premium?")
        only_one_source = {"operations.html": self.corpus.units["operations.html"]}
        self.assertEqual(deliver_complete("Monthly refund limit for Premium", [], only_one_source, 110), [])
        self.assertTrue(hits)
        self.assertIsNone(answer("What is the Monthly refund limit for Imaginary?", run_query(self.corpus, "What is the Monthly refund limit for Imaginary?")["complete"]))

    def test_recorded_benchmark_is_consistent_and_charts_are_valid(self):
        cases = [json.loads(line) for line in (ROOT / "data" / "benchmark.jsonl").read_text().splitlines()]
        metrics, rows = evaluate()
        self.assertEqual(len(rows), 56)
        self.assertEqual(len(cases), 56)
        self.assertTrue(all(row["page_retrieved"] for row in rows))
        for case, row in zip(cases, rows):
            self.assertEqual(case["id"], row["id"])
            self.assertTrue(has_complete_gold(case, row["complete"]["evidence"]))
        self.assertGreater(metrics["overall"]["complete"]["agent_task_accuracy"], metrics["overall"]["expanded"]["agent_task_accuracy"])
        with tempfile.TemporaryDirectory() as directory:
            write_results(directory, metrics, rows)
            render(metrics, directory)
            self.assertEqual(json.loads((Path(directory) / "metrics.json").read_text()), metrics)
            self.assertIn("Premium", (Path(directory) / "example_trace.txt").read_text())
            for name in ("comparison.svg", "by_type.svg"):
                self.assertEqual(ElementTree.parse(Path(directory) / name).getroot().tag, "{http://www.w3.org/2000/svg}svg")

    def test_web_api_and_chart_routes(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.corpus))
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/api/ask?q=What%20is%20the%20Monthly%20refund%20limit%20for%20Premium%3F") as response:
                payload = json.load(response)
                self.assertEqual(payload["complete_answer"], "INR 1,000")
                self.assertIsNone(payload["chunk_answer"])
            with urlopen(base + "/") as response:
                self.assertIn(b"Evidence Delivery Lab", response.read())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
