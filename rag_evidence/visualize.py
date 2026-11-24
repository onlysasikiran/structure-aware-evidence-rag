"""Generate committed SVG charts without a plotting dependency."""

from html import escape
from pathlib import Path
import json


NAVY = "#16324b"
BLUE = "#418bc9"
GOLD = "#e5a446"
TEAL = "#1d9f86"
MUTED = "#577184"


def chart(title, labels, baseline, expanded, complete, ylabel, path):
    width = max(720, 200 + 140 * len(labels))
    height = 420
    left, top, bottom = 75, 76, 100
    plot_height = height - top - bottom
    group_width = (width - left - 55) / len(labels)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
           f'<rect width="{width}" height="{height}" fill="#f7fafc"/>',
           f'<text x="{left}" y="36" fill="{NAVY}" font-size="22" font-weight="700" font-family="sans-serif">{escape(title)}</text>',
           f'<text x="{left}" y="56" fill="{MUTED}" font-size="12" font-family="sans-serif">{escape(ylabel)}</text>']
    for tick in range(0, 101, 20):
        y = top + plot_height * (1 - tick / 100)
        out.extend([f'<line x1="{left}" y1="{y:.1f}" x2="{width - 40}" y2="{y:.1f}" stroke="#dfebf0"/>',
                    f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" fill="{MUTED}" font-size="12" font-family="sans-serif">{tick}</text>'])
    for index, label in enumerate(labels):
        middle = left + group_width * (index + .5)
        for shift, value, color in ((-34, baseline[index], BLUE), (-10, expanded[index], GOLD), (14, complete[index], TEAL)):
            bar_height = plot_height * value / 100
            x = middle + shift
            y = top + plot_height - bar_height
            out.extend([f'<rect x="{x:.1f}" y="{y:.1f}" width="22" height="{bar_height:.1f}" rx="3" fill="{color}"/>',
                        f'<text x="{x + 11:.1f}" y="{max(top + 12, y - 7):.1f}" text-anchor="middle" fill="{NAVY}" font-size="11" font-family="sans-serif">{value:.1f}</text>'])
        out.append(f'<text x="{middle:.1f}" y="{height - 69}" text-anchor="middle" fill="{NAVY}" font-size="12" font-family="sans-serif">{escape(label)}</text>')
    out.extend([f'<rect x="{left}" y="{height - 38}" width="13" height="13" fill="{BLUE}"/>',
                f'<text x="{left + 20}" y="{height - 27}" fill="{NAVY}" font-family="sans-serif" font-size="12">Chunk delivery</text>',
                f'<rect x="{left + 150}" y="{height - 38}" width="13" height="13" fill="{GOLD}"/>',
                f'<text x="{left + 170}" y="{height - 27}" fill="{NAVY}" font-family="sans-serif" font-size="12">Neighbor expansion</text>',
                f'<rect x="{left + 330}" y="{height - 38}" width="13" height="13" fill="{TEAL}"/>',
                f'<text x="{left + 350}" y="{height - 27}" fill="{NAVY}" font-family="sans-serif" font-size="12">Complete units</text>', "</svg>"])
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")


def render(metrics, output_dir):
    output = Path(output_dir)
    overall = metrics["overall"]
    keys = ["retrieval_page_recall", "evidence_recall", "agent_task_accuracy"]
    chart("Same retrieval, different delivery", ["Page retrieved", "Evidence recall", "Task accuracy"],
          [100 * overall["chunk"][key] for key in keys], [100 * overall["expanded"][key] for key in keys],
          [100 * overall["complete"][key] for key in keys],
          "Percent of all benchmark questions · matched evidence budget", output / "comparison.svg")
    labels = ["Tables", "Lists", "Prose"]
    kinds = ["table", "list", "prose"]
    chart("Answer accuracy by content type", labels,
          [100 * metrics["by_kind"][kind]["chunk"]["agent_task_accuracy"] for kind in kinds],
          [100 * metrics["by_kind"][kind]["expanded"]["agent_task_accuracy"] for kind in kinds],
          [100 * metrics["by_kind"][kind]["complete"]["agent_task_accuracy"] for kind in kinds],
          "Percent correct · identical retrieval hits and reader", output / "by_type.svg")


def render_sensitivity(rows, output_dir, budget):
    output = Path(output_dir)
    (output / "sensitivity.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    chart("Accuracy vs retrieval chunk size", [str(row["chunk_size"]) + " chars" for row in rows],
          [100 * row["overall"]["chunk"]["agent_task_accuracy"] for row in rows],
          [100 * row["overall"]["expanded"]["agent_task_accuracy"] for row in rows],
          [100 * row["overall"]["complete"]["agent_task_accuracy"] for row in rows],
          f"Percent correct · shared {budget}-unit evidence budget", output / "sensitivity.svg")
