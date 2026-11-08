from decimal import Decimal
from pprint import pprint

from evaluation import build_evaluation_report


def make_case(case_id: str, text: str, expected_amount: str) -> dict:
    return {
        "id": case_id,
        "split": "evaluation",
        "text": text,
        "expected_amount": Decimal(expected_amount),
    }


cases = [
    make_case("B-01", "   Total a pagar: R$ 2.350,45", "2350.45"),
    make_case("B-02", "Valor da fatura: R$ 0,00", "0.00"),
    make_case("B-03", "Montante a liquidar: R$ 187,35", "187.35"),
    make_case(
        "B-04",
        "Valor dos serviços: R$ 215,00\nTotal devido: R$ 195,00",
        "195.00",
    ),
    make_case(
        "B-05",
        "Valor da fatura: R$ 150,00\nTotal a pagar: R$ 125,00",
        "125.00",
    ),
]

if __name__ == "__main__":
    pprint(build_evaluation_report(cases))
