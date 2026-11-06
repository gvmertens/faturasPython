import unittest
from datetime import date
from decimal import Decimal
from extraction import (
    Invoice,
    has_invalid_dates,
    has_missing_amount,
    parse_brl_amount,
    extract_supplier,
    extract_total_amount,
    extract_invoice_batch,
    needs_review,
    count_invoices_needing_review,
)
from evaluation import (
    is_amount_correct,
    count_correct_amounts,
    calculate_accuracy,
    evaluate_amount_extraction,
)


class CourseTests(unittest.TestCase):
    def test_dates(self):
        for issue, due, expected in [(1, 15, False), (15, 1, True), (1, 1, False)]:
            with self.subTest(issue=issue, due=due):
                invoice = Invoice(
                    "A", "0001", date(2026, 10, issue), date(2026, 10, due), None
                )
                self.assertIs(has_invalid_dates(invoice), expected)

    def test_absence_and_zero(self):
        for amount, expected in [
            (None, True),
            (Decimal("0.00"), False),
            (Decimal("179.90"), False),
        ]:
            with self.subTest(amount=amount):
                invoice = Invoice(
                    "A", "0001", date(2026, 10, 1), date(2026, 10, 15), amount
                )
                self.assertIs(has_missing_amount(invoice), expected)

    def test_valid_formats(self):
        for raw, expected in [
            ("R$ 249,90", "249.90"),
            ("R$ 1.249,90", "1249.90"),
            ("249,90", "249.90"),
            ("R$ 0,00", "0.00"),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(parse_brl_amount(raw), Decimal(expected))

    def test_invalid_formats(self):
        for raw in ["R$ 249.90", "R$ 12.49,90", "não informado"]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_brl_amount(raw)

    def test_should_extract_amount_with_total_due_label(self):
        cases = [
            {
                "text": "Total devido: R$ 89,90",
                "expected_amount": Decimal("89.90"),
            },
        ]
        result = evaluate_amount_extraction(cases)
        self.assertEqual(result, 100.0)

    def test_should_select_only_evaluation_cases(self):
        cases = [
            {"id": "A", "split": "development"},
            {"id": "B", "split": "evaluation"},
        ]
        selected = select_evaluation_cases(cases)
        self.assertEqual(selected, [{"id": "B", "split": "evaluation"}])
        evaluation_cases = select_evaluation_cases(cases)
        accuracy = evaluate_amount_extraction(evaluation_cases)

    def test_supplier(self):
        self.assertEqual(
            extract_supplier("Fatura nº: 000123\nFornecedor: Horizonte Telecom"),
            "Horizonte Telecom",
        )
        self.assertIsNone(extract_supplier("Fatura nº: 000123"))

    def test_labels_and_spaces(self):
        for label in [
            "TOTAL A PAGAR",
            "Total a pagar",
            "   Total a pagar",
            "Valor da fatura",
        ]:
            with self.subTest(label=label):
                self.assertEqual(
                    extract_total_amount(label + ": R$ 249,90"), Decimal("249.90")
                )

    def test_other_amounts_do_not_replace_total(self):
        text = "Valor dos serviços: R$ 120,00\nValor do desconto: R$ 30,10\nValor da fatura: R$ 89,90"
        self.assertEqual(extract_total_amount(text), Decimal("89.90"))

    def test_invalid_or_missing_total(self):
        for text in [
            "Fornecedor: A",
            "TOTAL A PAGAR: não informado",
            "TOTAL A PAGAR: R$ 249.90",
            "Valor total dos descontos: R$ 30,10",
        ]:
            with self.subTest(text=text):
                self.assertIsNone(extract_total_amount(text))

    def test_batch(self):
        results = extract_invoice_batch(
            [
                "Fornecedor: Horizonte Telecom\nTOTAL A PAGAR: R$ 179,90",
                "Fornecedor: Serra Internet",
            ]
        )
        self.assertEqual(
            results,
            [
                {"supplier": "Horizonte Telecom", "total_amount": Decimal("179.90")},
                {"supplier": "Serra Internet", "total_amount": None},
            ],
        )
        self.assertEqual(count_invoices_needing_review(results), 1)

    def test_review(self):
        for supplier, amount, expected in [
            ("A", Decimal("0.00"), False),
            ("A", None, True),
            (None, Decimal("5.00"), True),
        ]:
            with self.subTest(supplier=supplier, amount=amount):
                self.assertIs(
                    needs_review({"supplier": supplier, "total_amount": amount}),
                    expected,
                )

    def test_gold_comparison(self):
        cases = [
            (Decimal("179.90"), Decimal("179.90")),
            (Decimal("199.90"), Decimal("179.90")),
            (None, Decimal("50.00")),
        ]
        self.assertTrue(is_amount_correct(*cases[0]))
        self.assertFalse(is_amount_correct(*cases[1]))
        self.assertFalse(is_amount_correct(*cases[2]))
        self.assertEqual(count_correct_amounts(cases), 1)

    def test_accuracy(self):
        self.assertIsNone(calculate_accuracy(0, 0))
        self.assertEqual(calculate_accuracy(0, 3), 0.0)
        self.assertEqual(calculate_accuracy(3, 3), 100.0)
        self.assertAlmostEqual(calculate_accuracy(2, 3), 66.6666666667)

    def test_evaluation(self):
        cases = [
            {"text": "TOTAL A PAGAR: R$ 179,90", "expected_amount": Decimal("179.90")},
            {"text": "Total a pagar: R$ 0,00", "expected_amount": Decimal("0.00")},
            {"text": "Valor da fatura: R$ 89,90", "expected_amount": Decimal("89.90")},
        ]
        self.assertEqual(evaluate_amount_extraction(cases), 100.0)
        self.assertIsNone(evaluate_amount_extraction([]))

    def test_should_evaluate_only_reserved_cases(self):
        cases = [
            {
                "split": "development",
                "text": "TOTAL A PAGAR: R$ 100,00",
                "expected_amount": Decimal("100.00"),
            },
            {
                "split": "evaluation",
                "text": "Saldo para quitação: R$ 50,00",
                "expected_amount": Decimal("50.00"),
            },
            {
                "split": "evaluation",
                "text": "TOTAL A PAGAR: R$ 80,00",
                "expected_amount": Decimal("80.00"),
            },
        ]

        result = evaluate_reserved_cases(cases)

        self.assertEqual(result, 50.0)
        
    def test_should_return_none_when_no_reserved_cases_exist(self):
        cases = [
            {
                "split": "development",
                "text": "TOTAL A PAGAR: R$ 100,00",
                "expected_amount": Decimal("100.00"),
            },
        ]
        result = evaluate_reserved_cases(cases)
        self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main()
