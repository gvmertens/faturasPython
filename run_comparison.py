from decimal import Decimal
from time import perf_counter
from unittest.mock import Mock

from extraction import extract_total_amount, extract_total_with_fallback

CASES = [
    ("V-01", "Total a pagar: R$ 83,20", "83.20"),
    ("V-02", "Valor da fatura: R$ 0,00", "0.00"),
    (
        "V-03",
        "Valor da fatura: R$ 180,00\n"
        "Crédito aplicado: R$ 20,00\n"
        "Saldo líquido a pagar: R$ 160,00",
        "160.00",
    ),
    (
        "V-04",
        "Valor da fatura: R$ 200,00\n"
        "Desconto aplicado: R$ 25,00\n"
        "Saldo líquido a pagar: R$ 175,00",
        "175.00",
    ),
    (
        "V-05",
        "Crédito aplicado: R$ 30,00\n" "Total a pagar: pendente de fechamento",
        None,
    ),
    (
        "V-06",
        "Desconto promocional: R$ 15,00\n"
        "Documento preliminar. O valor final será informado no fechamento.",
        None,
    ),
]


def evaluate(name, extract):
    started_at = perf_counter()
    counts = {
        "correct": 0,
        "wrong_value": 0,
        "expected_review": 0,
        "unexpected_review": 0,
        "unexpected_value": 0,
        "technical_error": 0,
    }

    print(f"\n{name}")

    for case_id, text, expected_text in CASES:
        expected = Decimal(expected_text) if expected_text is not None else None

        try:
            extracted = extract(text)
        except TimeoutError:
            counts["technical_error"] += 1
            print(f"{case_id}: review (llm_timeout)")
            continue
        except ValueError:
            counts["technical_error"] += 1
            print(f"{case_id}: review (invalid_response)")
            continue

        if expected is None:
            status = "expected_review" if extracted is None else "unexpected_value"
        elif extracted is None:
            status = "unexpected_review"
        elif extracted == expected:
            status = "correct"
        else:
            status = "wrong_value"

        counts[status] += 1
        print(f"{case_id}: {status}, extraído={extracted}, esperado={expected}")

    elapsed = perf_counter() - started_at
    print(
        f"Totais corretos: {counts['correct']} | "
        f"Valores incorretos: {counts['wrong_value']} | "
        f"Revisões esperadas: {counts['expected_review']} | "
        f"Revisões inesperadas: {counts['unexpected_review']} | "
        f"Valores sem evidência: {counts['unexpected_value']} | "
        f"Erros técnicos: {counts['technical_error']} | "
        f"Tempo: {elapsed:.2f} s"
    )


if __name__ == "__main__":
    from openai_client import call_llm

    evaluate("Determinístico", extract_total_amount)

    llm = Mock(wraps=call_llm)
    evaluate("Híbrido", lambda text: extract_total_with_fallback(text, llm))

    print(f"Chamadas ao modelo no híbrido: {llm.call_count}")
