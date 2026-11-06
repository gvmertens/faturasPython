import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Invoice:
    supplier: str
    document_number: str
    issue_date: date
    due_date: date
    total_amount: Decimal | None


def has_invalid_dates(invoice: Invoice) -> bool:
    return invoice.due_date < invoice.issue_date


def has_missing_amount(invoice: Invoice) -> bool:
    return invoice.total_amount is None


TOTAL_LABELS = {"TOTAL A PAGAR", "VALOR DA FATURA"}
BRL_AMOUNT_PATTERN = r"(?:[0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+),[0-9]{2}"


def parse_brl_amount(text: str) -> Decimal:
    amount_text = text.strip().removeprefix("R$").strip()
    if re.fullmatch(BRL_AMOUNT_PATTERN, amount_text) is None:
        raise ValueError("Formato monetário brasileiro inválido")
    return Decimal(amount_text.replace(".", "").replace(",", "."))


def extract_supplier(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("Fornecedor:"):
            return line.removeprefix("Fornecedor:").strip()
    return None


def extract_total_amount(text: str) -> Decimal | None:
    for line in text.splitlines():
        label, separator, amount_text = line.partition(":")
        if separator and label.strip().upper() in TOTAL_LABELS:
            try:
                return parse_brl_amount(amount_text)
            except (ValueError, InvalidOperation):
                return None
    return None


def extract_invoice_fields(text: str) -> dict:
    return {
        "supplier": extract_supplier(text),
        "total_amount": extract_total_amount(text),
    }


def extract_invoice_batch(documents: list[str]) -> list[dict]:
    results = []
    for text in documents:
        results.append(extract_invoice_fields(text))
    return results


def needs_review(fields: dict) -> bool:
    return fields["supplier"] is None or fields["total_amount"] is None


def count_invoices_needing_review(results: list[dict]) -> int:
    count = 0
    for fields in results:
        if needs_review(fields):
            count += 1
    return count
