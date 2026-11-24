"""Create a fixed, inspectable 56-question benchmark from the authored fixtures."""

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
cases = []


def add(source, kind, field, entity, value):
    cases.append({
        "id": f"q{len(cases) + 1:02d}",
        "kind": kind,
        "question": f"What is the {field}" + (f" for {entity}?" if entity else "?"),
        "source": source,
        "field": field,
        "entity": entity,
        "answer": value,
    })


tables = {
    "refunds.html": ("Subscription Refund Policy", ("Monthly refund limit", "Annual refund limit"), [
        ("Basic", "INR 500", "INR 5,000"),
        ("Plus", "INR 750", "INR 7,500"),
        ("Premium", "INR 1,000", "INR 10,000"),
        ("Enterprise", "INR 2,500", "INR 25,000"),
    ]),
    "shipping.html": ("Shipping Service Levels", ("Standard delivery", "Express delivery"), [
        ("North", "5 business days", "2 business days"),
        ("South", "4 business days", "1 business day"),
        ("East", "6 business days", "3 business days"),
        ("West", "3 business days", "1 business day"),
    ]),
    "incidents.html": ("Incident Response Standards", ("Acknowledgement deadline", "Status update interval"), [
        ("SEV1", "10 minutes", "20 minutes"),
        ("SEV2", "30 minutes", "60 minutes"),
        ("SEV3", "2 hours", "4 hours"),
        ("SEV4", "1 business day", "2 business days"),
    ]),
    "retention.html": ("Records Retention Schedule", ("Active storage", "Archive storage"), [
        ("Billing logs", "90 days", "7 years"),
        ("Access logs", "30 days", "1 year"),
        ("Support chats", "60 days", "2 years"),
        ("Audit events", "180 days", "5 years"),
    ]),
}

for source, (_, fields, rows) in tables.items():
    for entity, first, second in rows:
        add(source, "table", fields[0], entity, first)
        add(source, "table", fields[1], entity, second)

lists = {
    "travel.html": ("Daily meal allowance", "Hotel nightly cap", "Taxi reimbursement cap", "Approval lead time"),
    "access.html": ("Credential rotation interval", "Access review interval", "Account closure deadline", "Recovery verification window"),
}
list_rows = {
    "travel.html": {
        "Domestic": ("INR 1,200", "INR 5,000", "INR 800", "2 business days"),
        "International": ("USD 70", "USD 180", "USD 45", "10 business days"),
    },
    "access.html": {
        "Employees": ("180 days", "90 days", "24 hours", "30 minutes"),
        "Contractors": ("30 days", "14 days", "4 hours", "15 minutes"),
    },
}

for source, fields in lists.items():
    for entity, values in list_rows[source].items():
        for field, value in zip(fields, values):
            add(source, "list", field, entity, value)

for field, value in [
    ("SSO session timeout", "30 minutes"),
    ("API request timeout", "45 seconds"),
    ("Backup verification cadence", "1 week"),
    ("Certificate renewal notice", "60 days"),
    ("Deployment freeze window", "12 hours"),
    ("Support escalation deadline", "2 hours"),
    ("Health check interval", "5 minutes"),
    ("Audit report cadence", "1 month"),
]:
    add("operations.html", "prose", field, "", value)

output = ROOT / "data" / "benchmark.jsonl"
output.write_text("".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases), encoding="utf-8")
print(f"Wrote {len(cases)} questions to {output}")
