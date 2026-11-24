"""Parse source HTML into flat retrieval blocks and self-contained evidence units."""

from dataclasses import dataclass, field
from html.parser import HTMLParser
import re


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    parent: "Node | None" = None


@dataclass(frozen=True)
class Evidence:
    source: str
    unit_id: str
    kind: str
    section: str
    text: str


class TreeParser(HTMLParser):
    VOID = {"br", "hr", "img", "input", "meta", "link", "source", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                return

    def handle_data(self, data):
        if self.stack[-1].tag not in {"script", "style"}:
            self.stack[-1].children.append(data)


def parse(html):
    parser = TreeParser()
    parser.feed(html)
    return parser.root


def descendants(node, tag):
    for child in node.children:
        if isinstance(child, Node):
            if child.tag == tag:
                yield child
            yield from descendants(child, tag)


def text_of(node):
    fragments = []

    def walk(current):
        if isinstance(current, str):
            fragments.append(current)
        elif current.tag not in {"script", "style"}:
            for child in current.children:
                walk(child)

    walk(node)
    return re.sub(r"\s+", " ", " ".join(fragments)).strip()


def direct_cells(row):
    return [child for child in row.children if isinstance(child, Node) and child.tag in {"td", "th"}]


def table_rows(table):
    for child in table.children:
        if not isinstance(child, Node):
            continue
        if child.tag == "tr":
            yield child
        elif child.tag in {"thead", "tbody", "tfoot"}:
            for row in child.children:
                if isinstance(row, Node) and row.tag == "tr":
                    yield row


def expand_table(table):
    """Expand ordinary rowspan/colspan cells into a rectangular logical grid."""
    occupied = {}
    rows = []
    for row_index, row in enumerate(table_rows(table)):
        cells = {col: value for (r, col), value in occupied.items() if r == row_index}
        col = 0
        for cell in direct_cells(row):
            while col in cells:
                col += 1
            value = text_of(cell)
            colspan = max(1, min(64, int(cell.attrs.get("colspan", 1))))
            rowspan = max(1, min(64, int(cell.attrs.get("rowspan", 1))))
            for x in range(col, col + colspan):
                cells[x] = value
                for r in range(row_index + 1, row_index + rowspan):
                    occupied[r, x] = value
            col += colspan
        has_data = any(c.tag == "td" for c in direct_cells(row))
        rows.append(([cells.get(i, "") for i in range(max(cells, default=-1) + 1)], has_data))
    return rows


def header_names(header_rows, width):
    names = []
    for col in range(width):
        levels = []
        for row in header_rows:
            label = row[col] if col < len(row) else ""
            if label and label not in levels:
                levels.append(label)
        names.append(" / ".join(levels) or f"Column {col + 1}")
    return names


def flatten_and_complete(html, source):
    root = parse(html)
    title_node = next(descendants(root, "h1"), None)
    title = text_of(title_node) if title_node else source
    blocks = []
    units = []
    headings = []
    counter = 0

    def add(kind, content):
        nonlocal counter
        counter += 1
        section = " / ".join(headings)
        prefix = f"Document: {title}\n"
        if section:
            prefix += f"Section: {section}\n"
        units.append(Evidence(source, f"{source}#u{counter}", kind, section, prefix + content))

    def walk(node):
        if isinstance(node, str) or node.tag in {"script", "style", "head"}:
            return
        if node.tag in {"h1", "h2", "h3", "h4"}:
            heading = text_of(node)
            blocks.append(heading)
            if node.tag != "h1":
                depth = int(node.tag[1]) - 2
                del headings[depth:]
                headings.append(heading)
            return
        if node.tag == "table":
            rows = expand_table(node)
            caption = next((text_of(c) for c in node.children if isinstance(c, Node) and c.tag == "caption"), "")
            if caption:
                blocks.append(caption)
            headers = []
            for row, has_data in rows:
                blocks.append(" | ".join(row))
                if not has_data:
                    headers.append(row)
                    continue
                names = header_names(headers, len(row))
                fields = [f"{names[i]}: {value}" for i, value in enumerate(row) if value]
                add("table", (f"Table: {caption}\n" if caption else "") + "\n".join(fields))
            return
        if node.tag in {"p", "li"}:
            value = text_of(node)
            if value:
                blocks.append(value)
                add("list" if node.tag == "li" else "prose", value)
            return
        for child in node.children:
            walk(child)

    walk(root)
    return blocks, units


def make_chunks(blocks, max_chars=96):
    """A simple conventional extractor with fixed-size text chunks."""
    result = []
    current = ""
    for block in blocks:
        if len(block) > max_chars:
            if current:
                result.append(current)
                current = ""
            result.extend(block[i:i + max_chars] for i in range(0, len(block), max_chars))
        elif current and len(current) + len(block) + 1 > max_chars:
            result.append(current)
            current = block
        else:
            current = current + "\n" + block if current else block
    if current:
        result.append(current)
    return result
