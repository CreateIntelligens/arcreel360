import pytest

from lib.cost_calculator import CNY_TO_USD_RATE, CostCalculator, cost_calculator


def cny(amount: float) -> float:
    return amount * CNY_TO_USD_RATE


class TestCostCalculator:
    def test_calculate_image_cost_known_and_default(self):
        calculator = CostCalculator()
        # 預設模型 (gemini-3.1-flash-image-preview)
        assert calculator.calculate_image_cost("1k") == 0.067
        assert calculator.calculate_image_cost("2K") == 0.101
        assert calculator.calculate_image_cost("4K") == 0.151
        assert calculator.calculate_image_cost("unknown") == 0.067
        # 指定舊模型 (gemini-3-pro-image-preview)
        assert calculator.calculate_image_cost("1k", model="gemini-3-pro-image-preview") == 0.134
        assert calculator.calculate_image_cost("2K", model="gemini-3-pro-image-preview") == 0.134

    def test_calculate_video_cost_known_and_default(self):
        calculator = CostCalculator()
        # 預設模型 (veo-3.1-lite-generate-preview)
        assert calculator.calculate_video_cost(8, "1080p", True) == pytest.approx(0.64)
        assert calculator.calculate_video_cost(8, "1080p", False) == pytest.approx(0.64)
        assert calculator.calculate_video_cost(8, "720p", True) == pytest.approx(0.40)
        assert calculator.calculate_video_cost(8, "720p", False) == pytest.approx(0.40)
        # Lite 不支援 4K，未知解析度回退到 1080p+audio 費率 (0.08)
        assert calculator.calculate_video_cost(5, "unknown", True) == pytest.approx(0.40)
        # Fast 模型 (veo-3.1-fast-generate-001)
        fast = "veo-3.1-fast-generate-001"
        assert calculator.calculate_video_cost(8, "1080p", True, model=fast) == pytest.approx(1.2)
        assert calculator.calculate_video_cost(8, "1080p", False, model=fast) == pytest.approx(0.8)
        assert calculator.calculate_video_cost(6, "4k", True, model=fast) == pytest.approx(2.1)
        assert calculator.calculate_video_cost(6, "4k", False, model=fast) == pytest.approx(1.8)
        # Fast 模型未知解析度應回退到自身的 1080p+audio 費率 (0.15)，而非標準模型的 0.40
        assert calculator.calculate_video_cost(5, "unknown", True, model=fast) == pytest.approx(0.75)
        # 歷史相容：preview 模型費率與 001 相同
        preview = "veo-3.1-generate-preview"
        assert calculator.calculate_video_cost(8, "1080p", True, model=preview) == pytest.approx(3.2)
        assert calculator.calculate_video_cost(8, "1080p", False, model=preview) == pytest.approx(1.6)
        fast_preview = "veo-3.1-fast-generate-preview"
        assert calculator.calculate_video_cost(8, "1080p", True, model=fast_preview) == pytest.approx(1.2)

    def test_singleton_instance(self):
        assert isinstance(cost_calculator, CostCalculator)


class TestArkCost:
    def test_default_seedance_2_with_audio(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_ark_video_cost(
            usage_tokens=246840,
            generate_audio=True,
        )
        assert currency == "USD"
        assert amount == pytest.approx(cny(11.35464), rel=1e-3)

    def test_default_seedance_2_no_audio_same_price(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_ark_video_cost(
            usage_tokens=246840,
            generate_audio=False,
        )
        assert currency == "USD"
        assert amount == pytest.approx(cny(11.35464), rel=1e-3)

    def test_zero_tokens(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_ark_video_cost(
            usage_tokens=0,
            generate_audio=True,
        )
        assert amount == pytest.approx(0.0)
        assert currency == "USD"

    def test_unknown_model_uses_default(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_ark_video_cost(
            usage_tokens=1_000_000,
            generate_audio=True,
            model="unknown-model",
        )
        assert currency == "USD"
        assert amount == pytest.approx(cny(46.0))

    def test_seedance_2_cost(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_ark_video_cost(
            usage_tokens=1_000_000,
            generate_audio=True,
            model="doubao-seedance-2-0-260128",
        )
        assert currency == "USD"
        assert amount == pytest.approx(cny(46.00))

    def test_seedance_2_cost_no_audio_same_price(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_ark_video_cost(
            usage_tokens=1_000_000,
            generate_audio=False,
            model="doubao-seedance-2-0-260128",
        )
        assert currency == "USD"
        assert amount == pytest.approx(cny(46.00))

    def test_modelark_endpoint_id_uses_seedance_2_cost(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_ark_video_cost(
            usage_tokens=1_000_000,
            generate_audio=True,
            model="ep-20260508120826-lkcjf",
        )
        assert currency == "USD"
        assert amount == pytest.approx(cny(46.00))


class TestGrokCost:
    def test_default_model_per_second(self):
        calculator = CostCalculator()
        cost, currency = calculator.calculate_grok_video_cost(
            duration_seconds=10,
            model="grok-imagine-video",
        )
        assert cost == pytest.approx(0.50)
        assert currency == "USD"

    def test_short_video(self):
        calculator = CostCalculator()
        cost, currency = calculator.calculate_grok_video_cost(
            duration_seconds=1,
            model="grok-imagine-video",
        )
        assert cost == pytest.approx(0.050)
        assert currency == "USD"

    def test_max_duration(self):
        calculator = CostCalculator()
        cost, _ = calculator.calculate_grok_video_cost(
            duration_seconds=15,
            model="grok-imagine-video",
        )
        assert cost == pytest.approx(0.75)

    def test_zero_duration(self):
        calculator = CostCalculator()
        cost, _ = calculator.calculate_grok_video_cost(
            duration_seconds=0,
            model="grok-imagine-video",
        )
        assert cost == pytest.approx(0.0)

    def test_unknown_model_uses_default(self):
        calculator = CostCalculator()
        cost, _ = calculator.calculate_grok_video_cost(
            duration_seconds=10,
            model="unknown-grok-model",
        )
        assert cost == pytest.approx(0.50)


class TestBytePlusImageCost:
    def test_byteplus_image_cost_is_zero_when_no_image_models_are_registered(self):
        cost, currency = cost_calculator.calculate_cost("byteplus", "image", model="removed-image-model")
        assert currency == "USD"
        assert cost == pytest.approx(0.0)


class TestGrokImageCost:
    def test_grok_image_cost_default(self):
        cost, currency = cost_calculator.calculate_grok_image_cost()
        assert cost == pytest.approx(0.02)
        assert currency == "USD"

    def test_grok_image_cost_pro(self):
        cost, currency = cost_calculator.calculate_grok_image_cost(model="grok-imagine-image-pro")
        assert cost == pytest.approx(0.07)
        assert currency == "USD"

    def test_grok_image_cost_n_images(self):
        cost, _ = cost_calculator.calculate_grok_image_cost(n=4)
        assert cost == pytest.approx(0.02 * 4)

    def test_grok_image_cost_unknown_model(self):
        cost, currency = cost_calculator.calculate_grok_image_cost(model="unknown-model")
        assert cost == pytest.approx(0.02)
        assert currency == "USD"


class TestOpenAICost:
    def test_openai_text_cost(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_text_cost(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            provider="openai",
            model="gpt-5.5-mini",
        )
        assert currency == "USD"
        assert amount == pytest.approx(0.75 + 4.50)

    def test_openai_text_cost_default_model(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_text_cost(
            input_tokens=1_000_000,
            output_tokens=0,
            provider="openai",
        )
        assert currency == "USD"
        assert amount == pytest.approx(0.75)

    def test_openai_image_cost_square(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_openai_image_cost(model="gpt-image-2", quality="medium")
        assert currency == "USD"
        assert amount == pytest.approx(0.053)  # 預設 1024x1024

    def test_openai_image_cost_portrait(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_openai_image_cost(
            model="gpt-image-2",
            quality="high",
            size="1024x1536",
        )
        assert currency == "USD"
        assert amount == pytest.approx(0.165)

    def test_openai_image_cost_landscape(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_openai_image_cost(
            model="gpt-image-2-2026-04-21",
            quality="low",
            size="1536x1024",
        )
        assert currency == "USD"
        assert amount == pytest.approx(0.005)

    def test_openai_video_cost(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_openai_video_cost(duration_seconds=8, model="sora-2")
        assert currency == "USD"
        assert amount == pytest.approx(0.80)

    def test_openai_video_cost_pro(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_openai_video_cost(
            duration_seconds=4, model="sora-2-pro", resolution="1080p"
        )
        assert currency == "USD"
        assert amount == pytest.approx(2.80)

    def test_unified_entry_openai(self):
        calculator = CostCalculator()
        amount, currency = calculator.calculate_cost("openai", "text", input_tokens=500_000, output_tokens=100_000)
        assert amount == pytest.approx(0.375 + 0.45)
        amount, currency = calculator.calculate_cost("openai", "image", model="gpt-image-2", quality="high")
        assert amount == pytest.approx(0.211)  # 預設 1024x1024
        amount, currency = calculator.calculate_cost(
            "openai", "image", model="gpt-image-2", quality="high", size="1024x1536"
        )
        assert amount == pytest.approx(0.165)
        amount, currency = calculator.calculate_cost("openai", "video", duration_seconds=12, model="sora-2")
        assert amount == pytest.approx(1.20)
