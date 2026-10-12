"""Offline PDF authoring and publication checks. Never uploads or assigns a DOI.

Run from the repository root:
  python -m tools.research_publications validate
  python -m tools.research_publications build path/to/reviewed-record.json
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import re
import unicodedata

from grid_monitor.services.research import (
    DEFAULT_DIRECTORY, MAX_PDF_BYTES, ResearchValidationError,
    pdf_path, read_records, validate_record,
)


def _normalized(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def validate_pdf(record, directory, *, path_override=None):
    from pypdf import PdfReader

    path = path_override or pdf_path(record, directory)
    if path is None:
        return
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_PDF_BYTES:
        raise ResearchValidationError("PDF must exist and be no larger than 5 MB")
    reader = PdfReader(path)
    if reader.is_encrypted or not reader.pages:
        raise ResearchValidationError("PDF must be unencrypted and have pages")
    texts = [page.extract_text() or "" for page in reader.pages]
    if any(len(text.strip()) < 30 for text in texts):
        raise ResearchValidationError("Every PDF page must have searchable text; review scanned or blank pages")
    first = _normalized(texts[0])
    full = _normalized(" ".join(texts))
    for value in [record["title"], *(author["name"] for author in record["authors"])]:
        if _normalized(value) not in first:
            raise ResearchValidationError("PDF first page must match the registered title and all authors")
    if _normalized(record["abstract"]) not in full:
        raise ResearchValidationError("PDF abstract does not match the research record")
    for field in ("methodology", "findings", "limitations", "assumptions"):
        if any(_normalized(paragraph) not in full for paragraph in record[field]):
            raise ResearchValidationError(f"PDF {field} differs from the public record")
    if "references" not in full:
        raise ResearchValidationError("PDF must include a References section")


def build_pdf(raw, directory, *, overwrite=False, font=None, bold_font=None):
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    record = validate_record(raw, directory, check_pdf=False)
    target = pdf_path(record, directory)
    if target is None:
        raise ResearchValidationError("Set pdf_file before building")
    if target.exists() and not overwrite:
        raise ResearchValidationError("PDF exists; use --overwrite only after reviewing version policy")
    fonts = Path(reportlab.__file__).resolve().parent / "fonts"
    pdfmetrics.registerFont(TTFont("ResearchBody", str(font or fonts / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("ResearchHeading", str(bold_font or fonts / "VeraBd.ttf")))
    # Missing glyphs corrupt author attribution and searchability; fail explicitly.
    all_text = json.dumps(raw, ensure_ascii=False)
    for name in ("ResearchBody", "ResearchHeading"):
        glyphs = pdfmetrics.getFont(name).face.charToGlyph
        unsupported = {char for char in all_text if not char.isspace() and ord(char) not in glyphs}
        if unsupported:
            raise ResearchValidationError("Font lacks required characters; supply --font and --bold-font covering the author's text")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("ResearchTitle", fontName="ResearchHeading", fontSize=24, leading=29, spaceAfter=16))
    styles.add(ParagraphStyle("ResearchAuthor", fontName="ResearchBody", fontSize=16, leading=21, spaceAfter=10))
    styles.add(ParagraphStyle("ResearchText", fontName="ResearchBody", fontSize=10.5, leading=16, spaceAfter=10))
    styles.add(ParagraphStyle("ResearchSection", fontName="ResearchHeading", fontSize=13, leading=18, spaceBefore=16, spaceAfter=9, keepWithNext=True))
    story = []

    def paragraph(text, style="ResearchText"):
        story.append(Paragraph(escape(text).replace("\n", "<br/>"), styles[style]))

    paragraph(record["title"], "ResearchTitle")
    paragraph("; ".join(author["name"] for author in record["authors"]), "ResearchAuthor")
    for author in record["authors"]:
        details = [author["name"], *author["affiliations"]]
        if author.get("orcid"):
            details.append(author["orcid"])
        paragraph(" | ".join(details))
    paragraph(f'Published {record["published_at"]} | Updated {record["updated_at"]} | Version {record["version"]} | {record["type_label"]}')
    paragraph("Nigeria Power Data | " + ("Not peer reviewed" if record["peer_review_status"] == "not_peer_reviewed" else "External peer review: " + record["peer_review_url"]))
    if record.get("doi"):
        paragraph("Registered DOI: https://doi.org/" + record["doi"])
    paragraph("License: " + record["license"])
    for field, title in (("abstract", "Abstract"), ("methodology", "Methodology"),
                         ("findings", "Findings"), ("limitations", "Limitations"),
                         ("assumptions", "Methodological assumptions")):
        paragraph(title, "ResearchSection")
        for text in ([record[field]] if isinstance(record[field], str) else record[field]):
            paragraph(text)
    paragraph("Data provenance", "ResearchSection")
    for source in record["data_provenance"]:
        paragraph(f'{source["citation"]} | {source["data_kind"]} | {source["url"]}')
        paragraph(f'Coverage: {source["coverage"]}. Accessed: {source["accessed_on"]}. Processing: {source["processing"]}. Source rights: {source["license"]}.')
    paragraph("References", "ResearchSection")
    for index, reference in enumerate(record["references"], 1):
        paragraph(f'{index}. {reference["citation"]}' + (f' {reference["url"]}' if reference.get("url") else ""))
    story.append(Spacer(1, 8))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("ResearchBody", 8)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(48, 28, f'Version {record["version"]} | {record["published_at"]}')
        canvas.drawRightString(A4[0] - 48, 28, f"Page {document.page}")
        canvas.restoreState()

    target.parent.mkdir(parents=True, exist_ok=True)
    # Build and check a temporary file so failed output never replaces an approved PDF.
    import tempfile
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        output = Path(temporary) / target.name
        document = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=48, leftMargin=48,
                                     topMargin=44, bottomMargin=48, title=record["title"],
                                     author="; ".join(author["name"] for author in record["authors"]),
                                     pageCompression=1)
        document.build(story, onFirstPage=footer, onLaterPages=footer)
        from pypdf import PdfReader
        text = " ".join(page.extract_text() or "" for page in PdfReader(output).pages)
        if _normalized(record["abstract"]) not in _normalized(text):
            raise ResearchValidationError("Generated PDF text extraction failed")
        if output.stat().st_size > MAX_PDF_BYTES:
            raise ResearchValidationError("Generated PDF exceeds the 5 MB scholarly limit")
        validate_pdf(record, directory, path_override=output)
        output.replace(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    check.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    build = sub.add_parser("build")
    build.add_argument("record", type=Path)
    build.add_argument("--overwrite", action="store_true")
    build.add_argument("--font", type=Path)
    build.add_argument("--bold-font", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        raw = json.loads(args.record.read_text(encoding="utf-8"))
        target = build_pdf(raw, args.record.resolve().parent, overwrite=args.overwrite,
                           font=args.font, bold_font=args.bold_font)
        print(f"Built {target}. Review before setting pdf_publication_approved=true.")
    else:
        records = read_records(args.directory, strict=True)
        for record in records:
            validate_pdf(record, args.directory)
        print(f"Validated {len(records)} research records and their linked PDFs.")


if __name__ == "__main__":
    main()
