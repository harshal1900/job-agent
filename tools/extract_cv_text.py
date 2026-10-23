#!/usr/bin/env python3
"""Print the text of a CV or other career document, whatever its format.

    python3 tools/extract_cv_text.py documents/cv/my_cv.docx
    python3 tools/extract_cv_text.py documents/cv/my_cv.pdf --out /tmp/cv.txt

Supported: .docx, .pdf, .md, .txt, .tex. A .docx is read straight from its XML (it is
a ZIP archive), so no Word and no extra Python package is needed. Reading a Word file
this way keeps what a parser cares about and a PDF export loses:

  * headers and footers (contact details very often sit there),
  * table cells (two-column CV layouts), joined with " | " per row,
  * list items ("- ") and headings ("# "), so the structure survives,
  * hyperlink targets, written "text (https://...)" when they differ from the text.

It deliberately leaves out text Word does not show: runs formatted as hidden
(`w:vanish`) and tracked deletions. Both are common in templates that were edited
and are a known way to smuggle instructions into a document an agent will read, so
the number of hidden runs dropped is reported on stderr as one JSON line.

Exit 0 on success; exit 1 with {"error", "code"} on stderr otherwise.
"""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"

MAX_MEMBER_BYTES = 25 * 1024 * 1024      # one XML part, uncompressed
MAX_TOTAL_BYTES = 60 * 1024 * 1024       # all parts read, uncompressed
MAX_RATIO = 200                          # uncompressed / compressed, per member

TEXT_SUFFIXES = {".md", ".txt", ".tex", ".markdown"}


class ExtractError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def q(tag: str, ns: str = W) -> str:
    return f"{{{ns}}}{tag}"


def _read_member(zf: zipfile.ZipFile, name: str, budget: list[int]) -> bytes | None:
    try:
        info = zf.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_MEMBER_BYTES:
        raise ExtractError(f"{name} is {info.file_size} bytes uncompressed; refusing to read it", "TOO_LARGE")
    if info.compress_size and info.file_size / info.compress_size > MAX_RATIO and info.file_size > 1_000_000:
        raise ExtractError(f"{name} has a suspicious compression ratio; refusing to read it", "ZIP_BOMB")
    budget[0] += info.file_size
    if budget[0] > MAX_TOTAL_BYTES:
        raise ExtractError("document is too large to read safely", "TOO_LARGE")
    return zf.read(info)


def _parse(data: bytes, name: str) -> ET.Element:
    # Expat does not fetch external entities; the size limits above bound entity expansion.
    if re.search(rb"<!DOCTYPE|<!ENTITY", data[:4096], re.I):
        raise ExtractError(f"{name} declares a DOCTYPE/ENTITY, which Word never writes; refusing to parse it", "UNSAFE_XML")
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        raise ExtractError(f"{name} is not valid XML ({e})", "BAD_DOCX") from e


def _relationships(zf: zipfile.ZipFile, part: str, budget: list[int]) -> dict[str, str]:
    """rId -> external target for the hyperlinks of one part."""
    folder, _, base = part.rpartition("/")
    data = _read_member(zf, f"{folder}/_rels/{base}.rels", budget)
    if data is None:
        return {}
    out: dict[str, str] = {}
    for rel in _parse(data, "relationships").findall(q("Relationship", REL)):
        if rel.get("TargetMode") == "External" and rel.get("Id") and rel.get("Target"):
            out[rel.get("Id")] = rel.get("Target")
    return out


class _Walker:
    def __init__(self, links: dict[str, str]):
        self.links = links
        self.hidden = 0

    def run_text(self, run: ET.Element) -> str:
        props = run.find(q("rPr"))
        if props is not None:
            vanish = props.find(q("vanish"))
            if vanish is not None and vanish.get(q("val")) not in ("0", "false", "off"):
                self.hidden += 1
                return ""
        parts = []
        for child in run:
            if child.tag == q("t"):
                parts.append(child.text or "")
            elif child.tag == q("tab"):
                parts.append("\t")
            elif child.tag in (q("br"), q("cr")):
                parts.append("\n")
            elif child.tag == q("noBreakHyphen"):
                parts.append("-")
            elif child.tag == q("AlternateContent", MC):
                # A text box is stored twice (modern Choice + legacy Fallback); read one.
                choice = child.find(q("Choice", MC))
                parts.append(self.nested(choice if choice is not None else child))
            elif child.tag in (q("drawing"), q("pict")):
                parts.append(self.nested(child))
        return "".join(parts)

    def inline(self, node: ET.Element) -> str:
        """Text of a paragraph-level element, in document order."""
        out = []
        for child in node:
            if child.tag == q("r"):
                out.append(self.run_text(child))
            elif child.tag == q("hyperlink"):
                text = self.inline(child)
                target = self.links.get(child.get(q("id", R), ""))
                if target and text.strip() and target.rstrip("/") not in text and target.replace("mailto:", "") not in text:
                    text = f"{text} ({target})"
                out.append(text)
            elif child.tag in (q("ins"), q("smartTag"), q("sdt"), q("sdtContent"), q("fldSimple")):
                out.append(self.inline(child))
            elif child.tag == q("del"):
                continue  # tracked deletion: Word shows it struck through, not as text
            elif child.tag == q("pPr") or child.tag == q("rPr"):
                continue
            elif child.tag == q("AlternateContent", MC):
                # A text box is stored twice (modern Choice + legacy Fallback); read one.
                choice = child.find(q("Choice", MC))
                out.append(self.nested(choice if choice is not None else child))
            else:
                # drawing/textbox wrappers (mc:AlternateContent, w:pict, ...) hold nested paragraphs
                out.append(self.nested(child))
        return "".join(out)

    def nested(self, node: ET.Element) -> str:
        texts = [self.paragraph(p) for p in node.iter(q("p"))]
        return " ".join(t for t in texts if t)

    def paragraph(self, p: ET.Element) -> str:
        text = self.inline(p).strip()
        if not text:
            return ""
        ppr = p.find(q("pPr"))
        if ppr is not None:
            style = ppr.find(q("pStyle"))
            sval = style.get(q("val")) if style is not None else ""
            m = re.match(r"(?:Heading|heading)\s*(\d)$", sval or "")
            if m:
                return f"{'#' * min(int(m.group(1)), 4)} {text}"
            if sval and sval.lower() == "title":
                return f"# {text}"
            if ppr.find(q("numPr")) is not None or (sval and "list" in sval.lower()):
                return f"- {text}"
        return text

    def block(self, node: ET.Element) -> list[str]:
        lines: list[str] = []
        for child in node:
            if child.tag == q("p"):
                t = self.paragraph(child)
                if t:
                    lines.append(t)
            elif child.tag == q("tbl"):
                lines.extend(self.table(child))
            elif child.tag in (q("sdt"), q("sdtContent"), q("ins")):
                lines.extend(self.block(child))
        return lines

    def table(self, tbl: ET.Element) -> list[str]:
        rows = []
        for tr in tbl.findall(q("tr")):
            cells = []
            for tc in tr.findall(q("tc")):
                cell = " ".join(self.block(tc)).strip()
                if cell:
                    cells.append(cell)
            if cells:
                rows.append(" | ".join(cells))
        return rows


def extract_docx(path: Path) -> tuple[str, dict]:
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise ExtractError(f"{path.name} is not a .docx (not a ZIP archive); a legacy .doc must be saved as .docx or PDF first", "BAD_DOCX") from e
    with zf:
        budget = [0]
        names = zf.namelist()
        if "word/document.xml" not in names:
            raise ExtractError(f"{path.name} has no word/document.xml; is it a Word document?", "BAD_DOCX")
        hidden = 0
        sections: list[tuple[str, list[str]]] = []
        parts = ["word/document.xml"] + sorted(n for n in names if re.fullmatch(r"word/(header|footer)\d*\.xml", n))
        for part in parts:
            data = _read_member(zf, part, budget)
            root = _parse(data, part)
            walker = _Walker(_relationships(zf, part, budget))
            body = root.find(q("body")) if part == "word/document.xml" else root
            lines = walker.block(body if body is not None else root)
            hidden += walker.hidden
            label = "body" if part == "word/document.xml" else ("header" if "header" in part else "footer")
            if lines:
                sections.append((label, lines))
    ordered = [s for s in sections if s[0] == "header"] + [s for s in sections if s[0] == "body"] + [s for s in sections if s[0] == "footer"]
    seen: set[str] = set()
    out: list[str] = []
    for label, lines in ordered:
        if label != "body":
            # Word repeats the same header/footer text for first/even/odd pages.
            lines = [ln for ln in lines if ln not in seen]
            seen.update(lines)
            if not lines:
                continue
            out.append(f"[{label}]")
        out.extend(lines)
        if label != "body":
            out.append(f"[/{label}]")
    return "\n".join(out).strip() + "\n", {"format": "docx", "hidden_runs_dropped": hidden}


def extract_pdf(path: Path) -> tuple[str, dict]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import verify_pdf  # noqa: E402  (same folder; shares the pypdf/pdftotext fallback)

    try:
        text, pages, extractor = verify_pdf.extract_text_layer(path)
    except (verify_pdf.VerificationError, FileNotFoundError) as e:
        raise ExtractError(
            f"could not extract text from {path.name} ({e}); install pypdf (pip install pypdf) or Poppler's pdftotext",
            "NO_EXTRACTOR",
        ) from e
    if not text.strip():
        raise ExtractError(f"{path.name} has no text layer (a scan?); export a text PDF or use .docx", "NO_TEXT")
    return text, {"format": "pdf", "extractor": extractor, "pages": pages}


def extract(path: Path) -> tuple[str, dict]:
    if not path.is_file():
        raise ExtractError(f"{path} does not exist", "NOT_FOUND")
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace"), {"format": suffix.lstrip(".")}
    if suffix == ".doc":
        raise ExtractError("legacy .doc is not supported; open it in Word or Google Docs and save as .docx or PDF", "UNSUPPORTED")
    raise ExtractError(f"unsupported file type '{suffix}' (use .docx, .pdf, .md, .txt or .tex)", "UNSUPPORTED")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("file")
    parser.add_argument("--out", help="write the text to this file instead of stdout")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        text, info = extract(Path(args.file))
    except ExtractError as e:
        print(json.dumps({"error": str(e), "code": e.code}), file=sys.stderr)
        return 1
    info.update(file=Path(args.file).name, chars=len(text))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    print(json.dumps(info), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
