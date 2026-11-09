import json
import os
import subprocess
from tempfile import TemporaryDirectory

import pymupdf

from pathlib import Path

from pypdf import PdfReader

from extraction import (
    parse_llm_invoice_amounts,
    validate_invoice_total,
    validate_total_evidence,
)
from openai_client import client
from decimal import Decimal


def extract_text_with_ocr(pdf_path: Path) -> str:
    tessdata_dir = Path(__file__).resolve().parent / "tessdata"
    page_texts = []

    with pymupdf.open(pdf_path) as document, TemporaryDirectory() as temp_dir:
        for index, page in enumerate(document, start=1):
            image_path = Path(temp_dir) / f"page-{index}.png"
            page.get_pixmap(dpi=300).save(str(image_path))

            try:
                result = subprocess.run(
                    [
                        "tesseract",
                        str(image_path),
                        "stdout",
                        "--tessdata-dir",
                        str(tessdata_dir),
                        "-l",
                        "por",
                    ],
                    capture_output=True,
                    encoding="utf-8",
                    check=True,
                    timeout=30,
                )
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(
                    f"OCR falhou na página {index}: {exc.stderr.strip()}"
                ) from exc

            page_texts.append(result.stdout)

    return "\n".join(page_texts)


instructions = """
Extraia os campos da fatura e responda apenas com um objeto JSON
contendo estas cinco chaves:

- invoice_amount: valor bruto informado como valor da fatura.
- discount_amount: desconto explicitamente informado.
- credit_amount: crédito explicitamente informado.
- total_amount: valor final a pagar explicitamente informado.
- total_evidence: copie literalmente a linha do documento que informa
  o valor final a pagar, incluindo o rótulo e o valor.
  Se total_amount for null, use null também para total_evidence.

Para os quatro campos monetários, use uma string com ponto decimal
e duas casas, sem símbolo de moeda. Use null se o campo não estiver
informado. Para total_evidence, siga a regra de cópia literal acima.
""".strip()

fields = ("invoice_amount", "discount_amount", "credit_amount", "total_amount")

base_dir = Path(__file__).resolve().parent
expected_amounts = ("250.00", "10.00", "5.00", "230.00")

cases = [
    ("M-02-PDF", base_dir / "M-02.pdf", expected_amounts, "total_inconsistent"),
    ("M-02-SCAN", base_dir / "M-02-scan.pdf", expected_amounts, "total_inconsistent"),
]

correct_cases = 0

for case_id, pdf_path, expected_values, expected_reason in cases:
    reader = PdfReader(pdf_path)
    invoice_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    source = "camada do PDF"

    if not invoice_text.strip():
        invoice_text = extract_text_with_ocr(pdf_path)
        source = "OCR"

    print(f"{case_id}: {pdf_path.name} | origem={source}")

    if not invoice_text.strip():
        print(f"{case_id}: no_extractable_text")
        continue

    response = client.responses.create(
        model=os.environ["OPENAI_MODEL"],
        instructions=instructions,
        input=invoice_text,
    )

    try:
        payload = json.loads(response.output_text)
        amounts = parse_llm_invoice_amounts(response.output_text)
        evidence = payload["total_evidence"]
    except (ValueError, KeyError) as exc:
        print(f"{case_id}: resposta fora do contrato ({exc})")
        print(response.output_text)
        continue

    review_reason = validate_total_evidence(
        invoice_text, amounts["total_amount"], evidence
    )

    if review_reason is None:
        discount = amounts["discount_amount"]
        credit = amounts["credit_amount"]
        adjustments = (discount if discount is not None else Decimal("0.00")) + (
            credit if credit is not None else Decimal("0.00")
        )
        review_reason = validate_invoice_total(
            amounts["invoice_amount"], adjustments, amounts["total_amount"]
        )

    mismatches = []
    for field, expected_value in zip(fields, expected_values):
        expected = Decimal(expected_value) if expected_value is not None else None
        if amounts[field] != expected:
            mismatches.append(field)

    if not mismatches and review_reason == expected_reason:
        correct_cases += 1

    print(f"{case_id}: campos divergentes={mismatches}")
    print(f"  Revisão obtida={review_reason}, esperada={expected_reason}")
    print(f"  Evidência={evidence!r}")

print(f"\nCasos com extração e revisão corretas: {correct_cases}/{len(cases)}")

print("API evidence:", ascii(evidence))
print("PDF lines:", [ascii(line.strip()) for line in invoice_text.splitlines()])
