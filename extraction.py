from email.mime import text
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import json


@dataclass(frozen=True)
class Invoice:
    supplier: str
    document_number: str
    issue_date: date
    due_date: date
    total_amount: Decimal | None


TOTAL_FINAL_LABELS = {"TOTAL A PAGAR", "TOTAL DEVIDO"}
TOTAL_GENERIC_LABELS = {"VALOR DA FATURA"}
TOTAL_LABELS = TOTAL_FINAL_LABELS | TOTAL_GENERIC_LABELS
ADJUSTMENT_LABELS = {"CRÉDITO APLICADO"}
INVOICE_AMOUNT_FIELDS = (
    "invoice_amount",
    "discount_amount",
    "credit_amount",
    "total_amount",
)

BRL_AMOUNT_PATTERN = r"(?:[0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+),[0-9]{2}"


def has_invalid_dates(invoice: Invoice) -> bool:
    return invoice.due_date < invoice.issue_date


def has_missing_amount(invoice: Invoice) -> bool:
    return invoice.total_amount is None


def classify_amount_error(
    extracted: Decimal | None,
    expected: Decimal,
) -> str | None:
    if extracted is None:
        return "amount_not_extracted"

    if extracted != expected:
        return "amount_mismatch"

    return None


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


def collect_total_candidates(
    text: str,
    labels: set[str] = TOTAL_LABELS,
) -> set[Decimal]:
    candidates = set()

    for line in text.splitlines():
        label, separator, amount_text = line.partition(":")
        if not separator or label.strip().upper() not in labels:
            continue

        try:
            candidates.add(parse_brl_amount(amount_text))
        except (ValueError, InvalidOperation):
            continue

    return candidates


def has_financial_adjustment(text: str) -> bool:
    for line in text.splitlines():
        label, separator, _ = line.partition(":")
        if separator and label.strip().upper() in ADJUSTMENT_LABELS:
            return True

    return False


def select_local_total(text: str) -> Decimal | None:
    candidates = collect_total_candidates(text)

    if len(candidates) != 1:
        return None

    if has_financial_adjustment(text):
        final_candidates = collect_total_candidates(text, TOTAL_FINAL_LABELS)
        if not final_candidates:
            return None

    return next(iter(candidates))


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
        if get_invoice_review_reason(fields) is not None:
            count += 1

    return count


def get_invoice_review_reason(fields: dict) -> str | None:
    if needs_review(fields):
        return "missing_required_field"
    if fields.get("total_rule") == "services_minus_discount":
        return validate_invoice_total(
            fields.get("services"), fields.get("discount"), fields.get("total_amount")
        )

    return None


def validate_invoice_total(
    services: Decimal | None,
    discount: Decimal | None,
    total: Decimal | None,
) -> str | None:
    if services is None or discount is None or total is None:
        return "missing_amount"
    if services - discount != total:
        return "total_inconsistent"

    return None


def parse_llm_total(response: str) -> Decimal | None:
    payload = json.loads(response)

    if not isinstance(payload, dict) or "total_amount" not in payload:
        raise ValueError("Expected a JSON object with a total_amount key")

    amount = payload["total_amount"]

    if amount is None:
        return None

    if not isinstance(amount, str):
        raise ValueError("total_amount must be a string or null")

    if re.fullmatch(r"[0-9]+\.[0-9]{2}", amount) is None:
        raise ValueError("Invalid decimal format in total_amount")

    try:
        return Decimal(amount)
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal format in total_amount") from exc


def should_use_llm_for_total(text: str) -> bool:
    return select_local_total(text) is None


def extract_total_with_fallback(
    text: str,
    call_llm: Callable[[str], str],
) -> Decimal | None:
    local_total = select_local_total(text)

    if local_total is not None:
        return local_total

    return parse_llm_total(call_llm(text))


def parse_llm_invoice_amounts(response: str) -> dict[str, Decimal | None]:
    payload = json.loads(response)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")

    amounts = {}
    for field in INVOICE_AMOUNT_FIELDS:
        if field not in payload:
            raise ValueError(f"Missing field: {field}")

        try:
            amounts[field] = parse_llm_total(
                json.dumps({"total_amount": payload[field]})
            )
        except ValueError as exc:
            raise ValueError(f"Invalid value for {field}") from exc

    return amounts


def validate_total_evidence(
    text: str,
    total: Decimal | None,
    evidence: object,
) -> str | None:
    if total is None:
        return None if evidence is None else "unexpected_total_evidence"

    if not isinstance(evidence, str):
        return "invalid_total_evidence"

    evidence = evidence.strip()
    document_lines = {line.strip() for line in text.splitlines()}

    if not evidence or evidence not in document_lines:
        return "invalid_total_evidence"

    label, separator, amount_text = evidence.partition(":")
    evidence_labels = TOTAL_FINAL_LABELS | {"SALDO LÍQUIDO A PAGAR"}

    if not separator or label.strip().upper() not in evidence_labels:
        return "invalid_total_evidence"

    try:
        cited_amount = parse_brl_amount(amount_text)
    except (ValueError, InvalidOperation):
        return "invalid_total_evidence"

    if cited_amount != total:
        return "total_evidence_mismatch"

    return None
