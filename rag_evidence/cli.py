"""Command line interface for evaluation, inspection, and the local web demo."""

import argparse
import json
from pathlib import Path

from .evaluation import ROOT, evaluate, write_results
from .pipeline import Corpus, run_query
from .reader import answer, answer_ollama
from .visualize import render, render_sensitivity


def main():
    parser = argparse.ArgumentParser(description="Compare raw chunk delivery with complete evidence units")
    commands = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data", type=Path, default=ROOT / "data", help="Directory of source HTML files")
    common.add_argument("--budget", type=int, default=110, help="Shared estimated evidence token budget")
    common.add_argument("--top-k", type=int, default=12, help="Number of shared retrieved hits")
    common.add_argument("--chunk-size", type=int, default=96, help="Baseline chunk size in characters")
    common.add_argument("--reader", choices=("rule", "ollama"), default="rule")
    common.add_argument("--model", default="gemma3:4b", help="Local Ollama model when reader=ollama")
    assess = commands.add_parser("evaluate", parents=[common], help="Run paired benchmark and write metrics/charts")
    assess.add_argument("--benchmark", type=Path, default=ROOT / "data" / "benchmark.jsonl")
    assess.add_argument("--output", type=Path, default=ROOT / "results")
    ask = commands.add_parser("ask", parents=[common], help="Inspect a single query in both modes")
    ask.add_argument("question")
    server = commands.add_parser("serve", parents=[common], help="Launch local comparison UI and JSON API")
    server.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.budget <= 0 or args.top_k <= 0 or args.chunk_size <= 0:
        parser.error("budget, top-k, and chunk-size must all be positive")
    if args.command == "evaluate":
        metrics, rows = evaluate(args.data, args.benchmark, args.budget, args.top_k, args.chunk_size, args.reader, args.model)
        write_results(args.output, metrics, rows)
        render(metrics, args.output)
        if args.reader == "rule":
            sizes = sorted({96, 160, 256, 384, args.chunk_size})
            sensitivity = [{"chunk_size": size, "overall": evaluate(args.data, args.benchmark, args.budget, args.top_k, size)[0]["overall"]} for size in sizes]
            render_sensitivity(sensitivity, args.output, args.budget)
        print(json.dumps(metrics, indent=2))
        print(f"Wrote metrics, individual traces, examples, and SVG charts to {args.output}")
    elif args.command == "ask":
        trace = run_query(Corpus(args.data, args.chunk_size), args.question, args.budget, args.top_k)
        for mode in ("chunk", "expanded", "complete"):
            items = trace[mode]
            prediction = answer(args.question, items) if args.reader == "rule" else answer_ollama(args.question, items, args.model)
            print(f"\n=== {mode.upper()} | {sum(item['tokens'] for item in items)}/{args.budget} estimated tokens ===")
            print("Answer:", prediction or "[abstained]")
            for item in items:
                print(f"\n[{item['unit_id']}]\n{item['text']}")
    else:
        from .server import serve
        serve(Corpus(args.data, args.chunk_size), args.port, args.budget, args.top_k, args.reader, args.model)


if __name__ == "__main__":
    main()
