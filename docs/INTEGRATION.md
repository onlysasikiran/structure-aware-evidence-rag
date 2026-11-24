# Connecting an existing retriever

`Corpus.retrieve(question)` currently supplies ranked `Hit(source, ordinal, body, score)` objects. Both versions are intentionally separate from this retrieval step. To connect an embedding or vector search system:

1. At ingestion, retain a stable source ID for each indexed chunk and store the full original HTML page under that ID. The ID must resolve to the same document version the retriever indexed.
2. Adapt the vector search output to `Hit` objects. Keep the retrieved order and capture the score or rank.
3. Supply those hits and the parsed units to `deliver_complete(question, hits, units_by_source, budget)`. The raw control uses the same hits with `deliver_chunks(hits, budget)`.
4. Give either delivered list to the *same* answerer or agent. Log the selected unit IDs, source versions, exact evidence text, and consumed budget.

Example adapter:

```python
from rag_evidence.pipeline import Hit, deliver_chunks, deliver_complete

hits = [Hit(source=row["source_id"], ordinal=row["chunk_id"],
            body=row["chunk_text"], score=row["score"]) for row in vector_results]
baseline = deliver_chunks(hits, budget=110)
improved = deliver_complete(question, hits, units_by_source, budget=110)
```

The HTML units must be produced by `flatten_and_complete(html, source_id)` and stored or regenerated when a source version changes. Never combine facts from an older parsed page with hits from a newer index. The implementation requires a readable source page after retrieval; when original HTML is unavailable, this delivery method cannot restore missing table headers reliably.
