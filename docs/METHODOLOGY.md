# Methodology and limits

## Corpus and questions

Seven small HTML pages in `data/` cover four tables (32 questions), two sectioned lists (16 questions), and one page of labeled prose (8 questions). `tools/build_benchmark.py` writes the fixed 56-question `data/benchmark.jsonl`. Every gold answer is visible in its corresponding source page. The benchmark, sources, and QA rules were authored for this demo; there is no held-out real-world evaluation.

## Paired comparison

- The extractor turns HTML headings, table rows, list items and paragraphs into text blocks. The baseline packs blocks into chunks of up to 96 characters.
- A single SQLite FTS5 index ranks those chunks with `bm25`, using the non-stopword query terms joined by `OR`. Ties use source name and chunk ordinal. The first 12 hits are saved with every question.
- Raw delivery packs these hits without changing them. Neighbor expansion joins each hit with the previous and following chunk from its source. Complete delivery uses only source pages present among those hits, parses their HTML, adds heading paths and table headers to each fact, scores units by query token overlap, and packs full units greedily.
- Every path uses the same maximum evidence budget of 110 estimated tokens. An estimated token is a Unicode word or a punctuation character. Because this is a proxy, provider-specific token counts will differ.
- The same reader then receives each delivered evidence list. The default reader recognizes `What is the ... [for ...]?`, extracts explicitly labeled values, and can associate a pipe-delimited table header and row when they coexist in one delivered unit. It abstains when it cannot establish the relation. Optional local Ollama calls use the same selected evidence but require separate evaluation.

## Metric definitions

**Source-page retrieval recall** = questions with the gold source page represented in the retrieved hit list / total questions. Its equality across paths is expected because retrieval is shared.

**Evidence recall** = questions where at least one delivered unit from the gold source contains the correct entity, the requested field label, and its correct value together / total questions. For flat tables, a co-located header and row also counts. This does not mean the reader will always pick the correct value when multiple sections are mixed together.

**Agent task accuracy** = questions where the shared reader's normalized answer exactly equals the gold answer / total questions. Abstentions count as incorrect. Every per-question prediction, source, selected text and budget usage is in `results/questions.jsonl`.

## Sensitivity and interpretation

`results/sensitivity.json` reruns the same questions at 96, 160, 256, and 384 baseline chunk characters with the same retrieval limit and evidence budget. Larger chunks can fix some table fragmentation, while longer mixed sections can still confuse a simple reader. The control demonstrates residual errors under these particular settings; it does not prove that all large-context readers or LLMs would fail.

The 100% complete-evidence result is specific to this deliberately inspectable fixture corpus and exact-label questions. It is not an expected deployment number. This project does not evaluate PDFs, OCR, arbitrary HTML, conflicting versions, prompt injection, LLM hallucination, numeric reasoning, or genuinely independent enterprise tasks. Table handling covers ordinary row/column spans; malformed HTML and complex nested tables require additional validation. Before production use, test on real authorized documents, evaluate a fixed LLM under a true tokenizer budget, measure latency/cost, and inspect incorrect or ambiguous business actions with human review.
