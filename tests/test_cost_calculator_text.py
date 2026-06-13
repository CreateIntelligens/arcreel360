from lib.cost_calculator import CNY_TO_USD_RATE, CostCalculator


def cny(amount: float) -> float:
    return amount * CNY_TO_USD_RATE


class TestTextCost:
    def setup_method(self):
        self.calc = CostCalculator()

    def test_gemini_cost(self):
        amount, currency = self.calc.calculate_text_cost(1000, 500, "gemini")
        assert currency == "USD"
        assert amount == (1000 * 0.10 + 500 * 0.40) / 1_000_000

    def test_byteplus_cost(self):
        amount, currency = self.calc.calculate_text_cost(1000, 500, "byteplus")
        assert currency == "USD"
        assert amount == cny((1000 * 0.30 + 500 * 0.60) / 1_000_000)

    def test_legacy_ark_cost_normalizes_to_byteplus(self):
        amount, currency = self.calc.calculate_text_cost(1000, 500, "ark")
        assert currency == "USD"
        assert amount == cny((1000 * 0.30 + 500 * 0.60) / 1_000_000)

    def test_grok_cost(self):
        amount, currency = self.calc.calculate_text_cost(1000, 500, "grok")
        assert currency == "USD"
        assert amount == (1000 * 2.00 + 500 * 10.00) / 1_000_000

    def test_unknown_provider_defaults_to_gemini(self):
        amount, currency = self.calc.calculate_text_cost(1000, 500, "unknown")
        assert currency == "USD"
