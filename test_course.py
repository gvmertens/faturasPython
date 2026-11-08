import unittest
from unittest.mock import Mock
from datetime import date
from decimal import Decimal
from run_hybrid import evaluate_hybrid_batch
from extraction import (
    Invoice,
    classify_amount_error,
    collect_total_candidates,
    extract_total_with_fallback,
    get_invoice_review_reason,
    has_invalid_dates,
    has_missing_amount,
    parse_brl_amount,
    extract_supplier,
    extract_total_amount,
    extract_invoice_batch,
    needs_review,
    count_invoices_needing_review,
    parse_llm_total,
    should_use_llm_for_total,
    validate_invoice_total,
)
from evaluation import (
    build_evaluation_report,
    count_failures_by_reason,
    is_amount_correct,
    count_correct_amounts,
    calculate_accuracy,
    evaluate_amount_extraction,
    select_evaluation_cases,
    evaluate_reserved_cases,
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

    def test_should_report_reserved_cases_results(self):
        cases = [
            {
                "id": "D-01",
                "split": "development",
                "text": "TOTAL A PAGAR: R$ 100,00",
                "expected_amount": Decimal("100.00"),
            },
            {
                "id": "E-01",
                "split": "evaluation",
                "text": "Saldo para quitação: R$ 50,00",
                "expected_amount": Decimal("50.00"),
            },
            {
                "id": "E-02",
                "split": "evaluation",
                "text": "TOTAL A PAGAR: R$ 80,00",
                "expected_amount": Decimal("80.00"),
            },
        ]

        result = build_evaluation_report(cases)

        self.assertEqual(
            result,
            {
                "evaluated_count": 2,
                "correct_count": 1,
                "accuracy": 50.0,
                "failures": [
                    {
                        "id": "E-01",
                        "reason": "amount_not_extracted",
                        "expected_amount": Decimal("50.00"),
                        "extracted_amount": None,
                    },
                ],
                "failure_counts": {"amount_not_extracted": 1},
            },
        )

    def test_should_return_amount_mismatch(self):
        result = classify_amount_error(Decimal("60.00"), Decimal("70.00"))
        self.assertEqual(result, "amount_mismatch")

    def test_should_classify_missing_amount(self):
        result = classify_amount_error(None, Decimal("70.00"))
        self.assertEqual(result, "amount_not_extracted")

    def test_should_return_no_error_when_amount_matches(self):
        result = classify_amount_error(Decimal("60.00"), Decimal("60.00"))
        self.assertIsNone(result)

    def test_should_return_empty_counts_when_no_failures_exist(self):
        result = count_failures_by_reason([])
        self.assertEqual(result, {})

    def test_should_count_failures_by_reason(self):
        failures = [
            {
                "id": "E-01",
                "reason": "amount_not_extracted",
                "expected_amount": Decimal("50.00"),
                "extracted_amount": None,
            },
            {
                "id": "E-03",
                "reason": "amount_not_extracted",
                "expected_amount": Decimal("70.00"),
                "extracted_amount": None,
            },
            {
                "id": "E-02",
                "reason": "amount_mismatch",
                "expected_amount": Decimal("80.00"),
                "extracted_amount": Decimal("60.00"),
            },
        ]
        result = count_failures_by_reason(failures)
        self.assertEqual(result, {"amount_not_extracted": 2, "amount_mismatch": 1})

    def test_should_return_total_inconsistent_when_total_is_inconsistent(self):
        result = validate_invoice_total(
            Decimal("100.00"), Decimal("20.00"), Decimal("70.00")
        )
        self.assertEqual(result, "total_inconsistent")

    def test_should_return_none_when_total_is_consistent(self):
        result = validate_invoice_total(
            Decimal("100.00"), Decimal("20.00"), Decimal("80.00")
        )
        self.assertIsNone(result)

    def test_should_accept_zero_discount(self):
        result = validate_invoice_total(
            Decimal("100.00"), Decimal("0.00"), Decimal("100.00")
        )
        self.assertIsNone(result)

    def test_invoice_review_reason_should_total_inconsistent_when_total_is_inconsistent(
        self,
    ):
        fields = {
            "supplier": "Teste 1",
            "total_amount": 70.00,
            "services": 100.00,
            "discount": 20.00,
            "total_rule": "services_minus_discount",
        }
        result = get_invoice_review_reason(fields)
        self.assertEqual(result, "total_inconsistent")

    def test_invoice_review_reason_should_none_when_no_rules_apply(self):
        fields = {
            "supplier": "Teste 1",
            "total_amount": 70.00,
            "services": 100.00,
            "discount": 20.00,
        }
        result = get_invoice_review_reason(fields)
        self.assertIsNone(result)

    def test_count_invoices_needing_review_counts_correctly(self):
        invoices = [
            {
                "supplier": "Teste 1",
                "total_amount": Decimal("70.00"),
                "services": Decimal("100.00"),
                "discount": Decimal("20.00"),
            },
            {
                "supplier": "Teste 1",
                "total_amount": Decimal("70.00"),
                "services": Decimal("100.00"),
                "discount": Decimal("20.00"),
                "total_rule": "services_minus_discount",
            },
        ]
        result = count_invoices_needing_review(invoices)
        self.assertEqual(result, 1)

    def test_should_prioritize_missing_required_field_over_inconsistent_total(self):
        fields = {
            "supplier": None,
            "total_amount": Decimal("70.00"),
            "services": Decimal("100.00"),
            "discount": Decimal("20.00"),
            "total_rule": "services_minus_discount",
        }
        self.assertEqual(get_invoice_review_reason(fields), "missing_required_field")

    def test_should_return_none_when_total_amount_is_none(self):
        response = '{"total_amount": null}'
        result = parse_llm_total(response)
        self.assertIsNone(result)

    def test_should_return_decimal_when_total_amount_is_present(self):
        response = '{"total_amount": "125.00"}'
        result = parse_llm_total(response)
        self.assertEqual(result, Decimal("125.00"))

    def test_should_reject_numeric_llm_total(self):
        with self.assertRaises(ValueError):
            parse_llm_total('{"total_amount": 125.00}')

    def test_should_reject_invalid_monetary_format(self):
        with self.assertRaises(ValueError):
            parse_llm_total('{"total_amount": "NaN"}')

    def test_should_reject_json_array(self):
        with self.assertRaises(ValueError):
            parse_llm_total('[]')

    def test_should_reject_json_object_without_total_amount(self):
            with self.assertRaises(ValueError):
                parse_llm_total('{}')

    def extract_response_and_print_total_value(response: str, expected: Decimal) -> dict:
        total = parse_llm_total(response)
        reason = classify_amount_error(total, expected)

        print(f"Extracted total value: {total}")
        print(f"Evaluation reason: {reason}")

        return {"total_amount": total, "reason": reason}

    def test_should_classify_correct_llm_total(self):
        expected = Decimal("125.00")
        total = parse_llm_total('{"total_amount":"125.00"}')

        self.assertEqual(total, expected)
        self.assertIsNone(classify_amount_error(total, expected))


    def test_should_classify_null_llm_total_as_not_extracted(self):
        expected = Decimal("125.00")
        total = parse_llm_total('{"total_amount":null}')

        self.assertIsNone(total)
        self.assertEqual(
            classify_amount_error(total, expected),
            "amount_not_extracted",
        )

    def test_should_deduplicate_equal_total_candidates(self):
        text = "Valor da fatura: R$ 125,00\nTotal a pagar: R$ 125,00"
        total = collect_total_candidates(text)
        self.assertEqual(total, {Decimal("125.00")})

    def test_should_keep_distinct_total_candidates(self):
            text = "Valor da fatura: R$ 125,00\nTotal a pagar: R$ 150,00"
            total = collect_total_candidates(text)
            self.assertEqual(total, {Decimal("125.00"), Decimal("150.00")})

    def test_should_use_llm_for_total_when_multiple_candidates_exist(self):
        text = "Valor da fatura: R$ 125,00\nTotal a pagar: R$ 150,00"
        self.assertTrue(should_use_llm_for_total(text))

    def test_should_not_use_llm_for_total_when_single_candidate_exists(self):
        text = "Valor da fatura: R$ 125,00\nTotal a pagar: R$ 125,00"
        self.assertFalse(should_use_llm_for_total(text))

    def test_should_use_llm_for_total_when_no_candidates_exist(self):
        text = "Pagar: R$ 125,00\nDesconto: R$ 25,00"
        self.assertTrue(should_use_llm_for_total(text))

    def test_should_use_zero_total_without_calling_llm(self):
        text = "Total a pagar: R$ 0,00"
        llm = Mock(return_value='{"total_amount":"125.00"}')

        result = extract_total_with_fallback(text, llm)

        self.assertEqual(result, Decimal("0.00"))
        llm.assert_not_called()


    def test_should_call_llm_once_when_total_is_ambiguous(self):
        text = "Valor da fatura: R$ 150,00\nTotal a pagar: R$ 125,00"
        llm = Mock(return_value='{"total_amount":"125.00"}')

        result = extract_total_with_fallback(text, llm)

        self.assertEqual(result, Decimal("125.00"))
        llm.assert_called_once_with(text)

    def test_should_call_llm_once_when_no_total_candidate_exists(self):
        text = "Montante a liquidar: R$ 187,35"
        llm = Mock(return_value='{"total_amount":"187.35"}')

        result = extract_total_with_fallback(text, llm)

        self.assertEqual(result, Decimal("187.35"))
        llm.assert_called_once_with(text)

    def test_should_propagate_llm_timeout_to_batch_caller(self):
        text = "Valor da fatura: R$ 150,00\nTotal a pagar: R$ 125,00"
        llm = Mock(side_effect=TimeoutError("LLM call timed out"))

        with self.assertRaises(TimeoutError):
            extract_total_with_fallback(text, llm)

        llm.assert_called_once_with(text)

    def test_should_continue_batch_after_llm_timeout(self):
        b05 = {
            "id": "B-05",
            "text": "Valor da fatura: R$ 150,00\nTotal a pagar: R$ 125,00",
            "expected_amount": Decimal("125.00"),
        }
        b01 = {
            "id": "B-01",
            "text": "Total a pagar: R$ 2.350,45",
            "expected_amount": Decimal("2350.45"),
        }
        llm = Mock(side_effect=TimeoutError("LLM call timed out"))

        report = evaluate_hybrid_batch([b05, b01], llm)

        self.assertEqual(report["correct_count"], 1)
        self.assertEqual(
            report["reviews"],
            [{"id": "B-05", "reason": "llm_timeout"}],
        )
        llm.assert_called_once_with(b05["text"])

if __name__ == "__main__":
    unittest.main()
