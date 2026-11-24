"""Shared retrieval with two independently selectable evidence-delivery paths."""

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import sqlite3

from .html_units import flatten_and_complete, make_chunks


STOPWORDS = {"a", "an", "are", "does", "for", "from", "how", "in", "is", "of", "on", "the", "to", "what", "which"}


def tokens(value):
    return re.findall(r"[^\W_]+", value.casefold())


def evidence_tokens(value):
    """A transparent word/punctuation proxy, not a provider-specific tokenizer."""
    return len(re.findall(r"\w+|[^\w\s]", value))


@dataclass(frozen=True)
class Hit:
    source: str
    ordinal: int
    body: str
    score: float


@dataclass(frozen=True)
class Delivered:
    source: str
    unit_id: str
    kind: str
    text: str
    tokens: int


class Corpus:
    def __init__(self, data_dir, chunk_size=96):
        self.data_dir = Path(data_dir)
        self.chunk_size = chunk_size
        self.units = {}
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.execute("CREATE VIRTUAL TABLE chunks USING fts5(source UNINDEXED, ordinal UNINDEXED, body)")
        for path in sorted(self.data_dir.glob("*.html")):
            blocks, units = flatten_and_complete(path.read_text(encoding="utf-8"), path.name)
            self.units[path.name] = units
            for ordinal, chunk in enumerate(make_chunks(blocks, chunk_size)):
                self.conn.execute("INSERT INTO chunks(source, ordinal, body) VALUES(?,?,?)", (path.name, ordinal, chunk))
        if not self.units:
            raise ValueError(f"No HTML files found in {self.data_dir}")

    def retrieve(self, query, limit=12):
        terms = list(dict.fromkeys(t for t in tokens(query) if t not in STOPWORDS))
        if not terms:
            return []
        expression = " OR ".join('"' + t.replace('"', '') + '"' for t in terms)
        rows = self.conn.execute(
            "SELECT source, ordinal, body, bm25(chunks) AS score FROM chunks "
            "WHERE chunks MATCH ? ORDER BY score ASC, source ASC, ordinal ASC LIMIT ?",
            (expression, limit),
        ).fetchall()
        return [Hit(source, ordinal, body, float(score)) for source, ordinal, body, score in rows]

    def neighbor_chunks(self, hit, radius=1):
        rows = self.conn.execute(
            "SELECT ordinal, body FROM chunks WHERE source=? AND ordinal BETWEEN ? AND ? ORDER BY ordinal",
            (hit.source, hit.ordinal - radius, hit.ordinal + radius),
        ).fetchall()
        return rows


def pack(candidates, budget):
    selected = []
    spent = 0
    for candidate in candidates:
        cost = evidence_tokens(candidate.text)
        if spent + cost <= budget:
            selected.append(Delivered(candidate.source, candidate.unit_id, candidate.kind, candidate.text, cost))
            spent += cost
    return selected


def deliver_chunks(hits, budget):
    items = [Delivered(h.source, f"{h.source}#chunk-{h.ordinal}", "chunk", h.body, evidence_tokens(h.body)) for h in hits]
    return pack(items, budget)


def deliver_expanded(hits, corpus, budget):
    """Fair context expansion comparator: the hit plus its immediate neighbors."""
    items = []
    seen = set()
    for hit in hits:
        neighbors = corpus.neighbor_chunks(hit)
        key = (hit.source, tuple(ordinal for ordinal, _ in neighbors))
        if key not in seen:
            seen.add(key)
            body = "\n".join(text for _, text in neighbors)
            items.append(Delivered(hit.source, f"{hit.source}#neighbors-{hit.ordinal}", "expanded", body, evidence_tokens(body)))
    return pack(items, budget)


def deliver_complete(query, hits, units_by_source, budget):
    """Use retrieved hits as page anchors, then rank complete units from those pages."""
    rank = {}
    for position, hit in enumerate(hits):
        rank.setdefault(hit.source, position)
    query_terms = set(tokens(query)) - STOPWORDS
    candidates = []
    for source in rank:
        for unit in units_by_source[source]:
            unit_terms = set(tokens(unit.text))
            overlap = query_terms & unit_terms
            if not overlap:
                continue
            score = len(overlap) / max(1, len(query_terms))
            score += 0.04 * len(overlap)
            score -= 0.001 * rank[source]
            candidates.append((score, unit))
    candidates.sort(key=lambda item: (-item[0], rank[item[1].source], item[1].unit_id))
    items = [Delivered(unit.source, unit.unit_id, unit.kind, unit.text, evidence_tokens(unit.text)) for _, unit in candidates]
    return pack(items, budget)


def run_query(corpus, question, budget=110, top_k=12):
    hits = corpus.retrieve(question, top_k)
    return {
        "question": question,
        "retrieval": [asdict(hit) for hit in hits],
        "chunk": [asdict(item) for item in deliver_chunks(hits, budget)],
        "expanded": [asdict(item) for item in deliver_expanded(hits, corpus, budget)],
        "complete": [asdict(item) for item in deliver_complete(question, hits, corpus.units, budget)],
        "budget": budget,
    }
