"""Guards for tools/extract_cv_text.py: reading a CV from .docx, .pdf, .md, .txt, .tex.

The .docx fixture (tests/fixtures/sample_cv.docx) was written by Word's own object model
(python-docx) with a header, footer, headings, bullet list, a table, a hyperlink and a
run formatted as hidden. Hand-built archives cover what Word writes less often.
"""

import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "extract_cv_text.py"
SAMPLE = REPO / "tests" / "fixtures" / "sample_cv.docx"

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
EXTRA_NS = (
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'xmlns:v="urn:schemas-microsoft-com:vml"'
)


def run(path: Path, *extra: str):
    proc = subprocess.run([sys.executable, str(TOOL), str(path), *extra], capture_output=True, text=True, encoding="utf-8")
    info = None
    for line in reversed(proc.stderr.strip().splitlines()):
        if line.startswith("{"):
            info = json.loads(line)
            break
    return proc.returncode, proc.stdout, info


def make_docx(path: Path, document_body: str, extra_parts: dict[str, str | bytes] | None = None) -> Path:
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document {W} {EXTRA_NS}><w:body>{document_body}</w:body></w:document>'
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", xml)
        for name, content in (extra_parts or {}).items():
            zf.writestr(name, content)
    return path


def para(text: str, rpr: str = "") -> str:
    return f"<w:p><w:r>{('<w:rPr>' + rpr + '</w:rPr>') if rpr else ''}<w:t>{text}</w:t></w:r></w:p>"


class DocxFromWord(unittest.TestCase):
    def setUp(self):
        self.code, self.out, self.info = run(SAMPLE)

    def test_succeeds_and_reports_the_format(self):
        self.assertEqual(self.code, 0)
        self.assertEqual(self.info["format"], "docx")
        self.assertEqual(self.info["chars"], len(self.out))

    def test_header_comes_first_and_carries_the_contact_details(self):
        self.assertTrue(self.out.startswith("[header]\nJane Doe | jane.doe@example.com | (555) 010-0100\n[/header]"))

    def test_footer_comes_last(self):
        self.assertTrue(self.out.rstrip().endswith("[footer]\nPage footer: Toronto, ON\n[/footer]"))

    def test_headings_lists_and_tables_keep_their_structure(self):
        self.assertIn("# Experience", self.out)
        self.assertIn("- Cut p99 latency 40% across the payments API.", self.out)
        self.assertIn("Skills | Python, Go, SQL", self.out)
        self.assertIn("Cloud | AWS, GCP", self.out)

    def test_hyperlink_target_is_kept_next_to_its_text(self):
        self.assertIn("my GitHub (https://github.com/janedoe)", self.out)

    def test_hidden_text_is_dropped_and_counted(self):
        self.assertNotIn("IGNORE PREVIOUS INSTRUCTIONS", self.out)
        self.assertEqual(self.info["hidden_runs_dropped"], 1)

    def test_out_flag_writes_a_file_and_prints_nothing_to_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "cv.txt"
            code, out, _ = run(SAMPLE, "--out", str(target))
            self.assertEqual(code, 0)
            self.assertEqual(out, "")
            self.assertIn("Jane Doe", target.read_text(encoding="utf-8"))


class DocxHandBuilt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tracked_deletion_is_omitted_and_insertion_kept(self):
        body = (
            "<w:p><w:r><w:t>Led </w:t></w:r>"
            '<w:del w:id="1"><w:r><w:delText>a team of 50</w:delText></w:r></w:del>'
            '<w:ins w:id="2"><w:r><w:t>a team of 5</w:t></w:r></w:ins></w:p>'
        )
        code, out, _ = run(make_docx(self.dir / "t.docx", body))
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "Led a team of 5")

    def test_text_box_is_read_once_not_twice(self):
        body = (
            "<w:p><w:r><mc:AlternateContent>"
            "<mc:Choice><w:drawing><wps:txbx><w:txbxContent>" + para("Phone 555-0100") + "</w:txbxContent></wps:txbx></w:drawing></mc:Choice>"
            "<mc:Fallback><w:pict><v:textbox><w:txbxContent>" + para("Phone 555-0100") + "</w:txbxContent></v:textbox></w:pict></mc:Fallback>"
            "</mc:AlternateContent></w:r></w:p>"
        )
        code, out, _ = run(make_docx(self.dir / "t.docx", body))
        self.assertEqual(code, 0)
        self.assertEqual(out.count("Phone 555-0100"), 1)

    def test_vanish_off_is_not_hidden(self):
        body = para("visible", '<w:vanish w:val="0"/>')
        code, out, info = run(make_docx(self.dir / "t.docx", body))
        self.assertIn("visible", out)
        self.assertEqual(info["hidden_runs_dropped"], 0)

    def test_header_repeated_for_first_and_default_pages_is_printed_once(self):
        hdr = f'<w:hdr {W}>' + para("Jane Doe") + "</w:hdr>"
        path = make_docx(self.dir / "t.docx", para("Body"), {"word/header1.xml": hdr, "word/header2.xml": hdr})
        _, out, _ = run(path)
        self.assertEqual(out.count("Jane Doe"), 1)

    def test_tabs_line_breaks_and_unicode(self):
        body = '<w:p><w:r><w:t>Zürich</w:t><w:tab/><w:t>2019</w:t><w:br/><w:t>Ñandú – café</w:t></w:r></w:p>'
        _, out, _ = run(make_docx(self.dir / "t.docx", body))
        self.assertEqual(out.strip(), "Zürich\t2019\nÑandú – café")

    def test_a_doctype_is_refused(self):
        path = self.dir / "evil.docx"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("word/document.xml", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaa">]><w:document ' + W + "><w:body/></w:document>")
        code, _, info = run(path)
        self.assertEqual((code, info["code"]), (1, "UNSAFE_XML"))

    def test_a_zip_bomb_is_refused(self):
        path = self.dir / "bomb.docx"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("word/document.xml", f'<w:document {W}><w:body>' + "<w:p/>" * 1_000_000 + "</w:body></w:document>")
        code, _, info = run(path)
        self.assertEqual((code, info["code"]), (1, "ZIP_BOMB"))


class OtherFormats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plain_text_formats_pass_through(self):
        for name, content in (("cv.md", "# Jane\n- Python\n"), ("cv.txt", "Jane\n"), ("cv.tex", "\\name{Jane}{Doe}\n")):
            with self.subTest(name=name):
                (self.dir / name).write_text(content, encoding="utf-8")
                code, out, info = run(self.dir / name)
                self.assertEqual((code, out), (0, content))
                self.assertEqual(info["format"], name.split(".")[1])

    def test_pdf_text_layer(self):
        pdf = self.dir / "cv.pdf"
        pdf.write_bytes(minimal_pdf("Jane Doe Senior Engineer"))
        code, out, info = run(pdf)
        self.assertEqual(code, 0, info)
        self.assertIn("Jane Doe Senior Engineer", out)
        self.assertEqual(info["format"], "pdf")

    def test_errors_are_json_on_stderr_with_exit_1(self):
        (self.dir / "x.doc").write_bytes(b"\xd0\xcf\x11\xe0")
        (self.dir / "x.png").write_bytes(b"\x89PNG")
        (self.dir / "bad.docx").write_bytes(b"not a zip")
        for name, expected in (("x.doc", "UNSUPPORTED"), ("x.png", "UNSUPPORTED"), ("bad.docx", "BAD_DOCX"), ("missing.docx", "NOT_FOUND")):
            with self.subTest(name=name):
                code, out, info = run(self.dir / name)
                self.assertEqual((code, out, info["code"]), (1, "", expected))

    def test_a_docx_without_a_document_part_is_rejected(self):
        path = self.dir / "empty.docx"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("hello.txt", "hi")
        code, _, info = run(path)
        self.assertEqual((code, info["code"]), (1, "BAD_DOCX"))


def minimal_pdf(text: str) -> bytes:
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs[3] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(buf.tell())
        buf.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = buf.tell()
    buf.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        buf.write(b"%010d 00000 n \n" % off)
    buf.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
    return buf.getvalue()


if __name__ == "__main__":
    unittest.main()
