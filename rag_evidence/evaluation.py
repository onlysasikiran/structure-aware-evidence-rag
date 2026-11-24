"""Paired, source-aware evaluation with inspectable per-question traces."""

from collections import defaultdict
from datetime import date
from pathlib import Path
import json
import re

from .pipeline import Corpus, run_query
from .reader import answer, answer_ollama


ROOT = Path(__file__).resolve().parents[1]


def normalize(value):
    return re.sub(r"\s+", " ", value or "").casefold().strip()


def has_complete_gold(case, items):
    """One delivered unit must include entity, labeled field, and gold value."""
    for item in items:
        if item["source"] != case["source"]:
            continue
        body = item["text"]
        if case["entity"] and normalize(case["entity"]) not in normalize(body):
            continue
        rows = [[cell.strip() for cell in line.split("|")] for line in body.splitlines() if "|" in line]
        for index, header in enumerate(rows):
            columns = [i for i, label in enumerate(header) if normalize(label) == normalize(case["field"])]
            for row in rows[index + 1:]:
                if columns and row and normalize(case["entity"]) in normalize(row[0]) and columns[0] < len(row):
                    if normalize(row[columns[0]]) == normalize(case["answer"]):
                        return True
        for line in body.splitlines():
            if ": " not in line:
                continue
            label, value = line.split(": ", 1)
            if normalize(label) == normalize(case["field"]) and normalize(value) == normalize(case["answer"]):
                return True
    return False


def summary(rows, mode):
    count = len(rows)
    return {
        "questions": count,
        "retrieval_page_recall": round(sum(r["page_retrieved"] for r in rows) / count, 4),
        "evidence_recall": round(sum(r[mode]["evidence_recall"] for r in rows) / count, 4),
        "agent_task_accuracy": round(sum(r[mode]["correct"] for r in rows) / count, 4),
        "abstentions": sum(r[mode]["answer"] is None for r in rows),
        "mean_evidence_tokens": round(sum(r[mode]["tokens"] for r in rows) / count, 2),
    }


def evaluate(data_dir=None, benchmark=None, budget=110, top_k=12, chunk_size=96, reader="rule", model="gemma3:4b"):
    corpus = Corpus(data_dir or ROOT / "data", chunk_size=chunk_size)
    cases = [json.loads(line) for line in Path(benchmark or ROOT / "data" / "benchmark.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = []
    for case in cases:
        trace = run_query(corpus, case["question"], budget=budget, top_k=top_k)
        row = {"id": case["id"], "kind": case["kind"], "question": case["question"], "gold": case["answer"], "source": case["source"],
               "page_retrieved": any(hit["source"] == case["source"] for hit in trace["retrieval"]),
               "retrieval": trace["retrieval"]}
        for mode in ("chunk", "expanded", "complete"):
            items = trace[mode]
            prediction = answer(case["question"], items) if reader == "rule" else answer_ollama(case["question"], items, model=model)
            row[mode] = {"answer": prediction, "correct": normalize(prediction) == normalize(case["answer"]),
                         "evidence_recall": has_complete_gold(case, items), "tokens": sum(item["tokens"] for item in items), "evidence": items}
        rows.append(row)
    by_kind = {}
    for kind in sorted({r["kind"] for r in rows}):
        subset = [r for r in rows if r["kind"] == kind]
        by_kind[kind] = {mode: summary(subset, mode) for mode in ("chunk", "expanded", "complete")}
    metrics = {
        "benchmark": "authored HTML fixture benchmark",
        "date": date.today().isoformat(),
        "reader": "deterministic labeled-value QA" if reader == "rule" else f"local Ollama {model}",
        "budget_proxy": "Unicode words plus punctuation; not a model tokenizer",
        "budget_tokens": budget,
        "retrieval_top_k": top_k,
        "chunk_size_characters": chunk_size,
        "dataset": {"questions": len(cases), "documents": len(corpus.units), "by_kind": {kind: len([r for r in rows if r["kind"] == kind]) for kind in by_kind}},
        "overall": {mode: summary(rows, mode) for mode in ("chunk", "expanded", "complete")},
        "by_kind": by_kind,
    }
    return metrics, rows


def write_results(output_dir, metrics, rows):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "questions.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    def save_trace(row, filename):
        lines = [f"Question: {row['question']}", f"Expected: {row['gold']}", ""]
        for mode in ("chunk", "expanded", "complete"):
            lines.extend([f"=== {mode.upper()} ({row[mode]['tokens']} estimated tokens) ===",
                          f"Answer: {row[mode]['answer'] or '[abstained]'}"])
            for item in row[mode]["evidence"]:
                lines.extend([f"[{item['unit_id']}]", item["text"], ""])
        (output / filename).write_text("\n".join(lines), encoding="utf-8")

    example = next((row for row in rows if "premium" in row["question"].casefold() and "monthly" in row["question"].casefold()), rows[0])
    save_trace(example, "example_trace.txt")
    residual = next((row for row in rows if row["expanded"]["answer"] is not None and not row["expanded"]["correct"] and row["complete"]["correct"]), None)
    if residual:
        save_trace(residual, "expansion_failure.txt")
