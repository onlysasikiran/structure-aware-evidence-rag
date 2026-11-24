"""A deliberately conservative, model-free QA agent shared by both delivery paths."""

import re
import json
from urllib.request import Request, urlopen


def parse_question(question):
    match = re.fullmatch(r"What is the (.+?)(?: for (.+?))?\?", question.strip(), flags=re.I)
    if not match:
        return "", ""
    return match.group(1).casefold().strip(), (match.group(2) or "").casefold().strip()


def answer(question, items):
    """Only extract an explicitly labeled value whose evidence identifies the entity."""
    field, entity = parse_question(question)
    if not field:
        return None
    for item in items:
        content = item["text"] if isinstance(item, dict) else item.text
        if entity and entity not in content.casefold():
            continue
        rows = [[cell.strip() for cell in line.split("|")] for line in content.splitlines() if "|" in line]
        for index, header in enumerate(rows):
            columns = [i for i, label in enumerate(header) if label.casefold() == field]
            if not columns:
                continue
            for row in rows[index + 1:]:
                if entity and entity in row[0].casefold() and columns[0] < len(row):
                    return row[columns[0]]
        for line in content.splitlines():
            if ": " not in line:
                continue
            label, value = line.split(": ", 1)
            if label.casefold().strip() == field and value.strip():
                return value.strip()
    return None


def answer_ollama(question, items, model="gemma3:4b", url="http://127.0.0.1:11434/api/generate"):
    """Optional local LLM reader; uses exactly the evidence selected by the pipeline."""
    evidence = "\n\n".join(item["text"] if isinstance(item, dict) else item.text for item in items)
    prompt = (
        "Answer the question using only the evidence below. If the entity, field, or their "
        "relationship is missing or ambiguous, return null. Reply ONLY as JSON of the form "
        '{"answer": "value or null"}. Do not guess.\n\n'
        f"Question: {question}\nEvidence:\n{evidence}"
    )
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json", "options": {"temperature": 0}}).encode()
    request = Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=120) as response:
        generated = json.load(response)["response"]
    value = json.loads(generated).get("answer")
    return str(value).strip() if value is not None and str(value).strip().casefold() not in {"", "null", "none", "unknown"} else None
