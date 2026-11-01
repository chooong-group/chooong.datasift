"""Create a small synthetic XLSX for the documented quickstart; never overwrite."""

import argparse
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


@dataclass(frozen=True, slots=True)
class SampleRow:
    country: str
    amount: int


def create_sample(path: Path, *, dirty: bool = False) -> None:
    rows = (SampleRow("DE", 1500), SampleRow("AT", 2000), SampleRow("DE", 900))
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relationships = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with ZipFile(path, "x", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/data.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="book" Type="{relationships}/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{namespace}" xmlns:r="{relationships}">'
            '<sheets><sheet name="Data" sheetId="1" r:id="data"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="data" Type="{relationships}/worksheet" '
            'Target="worksheets/data.xml"/>'
            "</Relationships>",
        )
        data = "".join(
            f'<row r="{number}"><c r="A{number}" t="inlineStr"><is><t>{row.country}</t></is></c>'
            f'<c r="B{number}"><v>{row.amount}</v></c></row>'
            for number, row in enumerate(rows, start=2)
        )
        header = (
            '<row r="1"><c r="A1" t="inlineStr"><is><t>Country</t></is></c>'
            '<c r="B1" t="inlineStr"><is><t>Amount</t></is></c></row>'
        )
        if dirty:
            header = ""
            data = """
<row r="1"><c r="A1" t="inlineStr"><is><t>Quarterly sales — draft</t></is></c></row>
<row r="4">
<c r="C4" t="inlineStr"><is><t>Country</t></is></c>
<c r="D4" t="inlineStr"><is><t>Amount</t></is></c>
<c r="E4" t="inlineStr"><is><t>Note</t></is></c>
<c r="H4" t="inlineStr"><is><t>Country</t></is></c>
<c r="I4" t="inlineStr"><is><t>Amount</t></is></c>
<c r="J4" t="inlineStr"><is><t>Note</t></is></c>
</row>
<row r="5"><c r="C5" t="inlineStr"><is><t>Amounts pending review</t></is></c>
<c r="H5" t="inlineStr"><is><t>Includes estimates</t></is></c></row>
<row r="6">
<c r="C6" t="inlineStr"><is><t>DE</t></is></c>
<c r="D6"><v>1500</v></c>
<c r="E6" t="inlineStr"><is><t>Provisional</t></is></c>
<c r="H6" t="inlineStr"><is><t>DE</t></is></c>
<c r="I6"><v>2400</v></c>
<c r="J6" t="inlineStr"><is><t>Approved</t></is></c>
</row>
<row r="7">
<c r="C7" t="inlineStr"><is><t>AT</t></is></c>
<c r="D7"><v>2000</v></c>
<c r="H7" t="inlineStr"><is><t>DE</t></is></c>
<c r="I7"><v>900</v></c>
</row>
"""
        archive.writestr(
            "xl/worksheets/data.xml",
            f'<worksheet xmlns="{namespace}"><sheetData>'
            + header
            + data
            + "</sheetData></worksheet>",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--dirty", action="store_true", help="Include adjacent offset tables and comments"
    )
    args = parser.parse_args()
    create_sample(args.output, dirty=args.dirty)


if __name__ == "__main__":
    main()
