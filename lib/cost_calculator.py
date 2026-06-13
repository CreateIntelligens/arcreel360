"""
費用計算器

基於 docs/影片&圖片生成費用表.md 中的費用規則，計算圖片和影片生成的費用。
支援按模型區分費用，以便不同模型的歷史資料能正確計費。
"""

from __future__ import annotations

from lib.custom_provider import is_custom_provider
from lib.providers import PROVIDER_BYTEPLUS, PROVIDER_GROK, PROVIDER_OPENAI, CallType, normalize_provider_id

# CNY → USD 換算匯率（寫死；如需可調日後移至設定）
CNY_TO_USD_RATE = 1 / 7.2  # 約當 USD/CNY = 7.2


def _to_usd(amount: float, currency: str) -> tuple[float, str]:
    """將金額統一換算為 USD。未知幣別原樣回傳。"""
    if currency == "USD":
        return amount, "USD"
    if currency == "CNY":
        return amount * CNY_TO_USD_RATE, "USD"
    return amount, currency


class CostCalculator:
    """費用計算器"""

    # 圖片費用（美元/張），按模型和解析度區分
    IMAGE_COST = {
        "gemini-3-pro-image-preview": {
            "1K": 0.134,
            "2K": 0.134,
            "4K": 0.24,
        },
        "gemini-3.1-flash-image-preview": {
            "512PX": 0.045,
            "1K": 0.067,
            "2K": 0.101,
            "4K": 0.151,
        },
    }

    DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image-preview"

    # 影片費用（美元/秒），按模型區分
    # 格式：model -> {(resolution, generate_audio): cost_per_second}
    VIDEO_COST = {
        "veo-3.1-generate-001": {
            ("720p", True): 0.40,
            ("720p", False): 0.20,
            ("1080p", True): 0.40,
            ("1080p", False): 0.20,
            ("4k", True): 0.60,
            ("4k", False): 0.40,
        },
        "veo-3.1-fast-generate-001": {
            ("720p", True): 0.15,
            ("720p", False): 0.10,
            ("1080p", True): 0.15,
            ("1080p", False): 0.10,
            ("4k", True): 0.35,
            ("4k", False): 0.30,
        },
        # 歷史相容：preview 模型已下線，保留費率供歷史計費使用
        "veo-3.1-generate-preview": {
            ("720p", True): 0.40,
            ("720p", False): 0.20,
            ("1080p", True): 0.40,
            ("1080p", False): 0.20,
            ("4k", True): 0.60,
            ("4k", False): 0.40,
        },
        "veo-3.1-fast-generate-preview": {
            ("720p", True): 0.15,
            ("720p", False): 0.10,
            ("1080p", True): 0.15,
            ("1080p", False): 0.10,
            ("4k", True): 0.35,
            ("4k", False): 0.30,
        },
        "veo-3.1-lite-generate-preview": {
            ("720p", True): 0.05,
            ("720p", False): 0.05,
            ("1080p", True): 0.08,
            ("1080p", False): 0.08,
        },
    }

    SELECTABLE_VIDEO_MODELS = [
        "veo-3.1-generate-preview",
        "veo-3.1-fast-generate-preview",
        "veo-3.1-lite-generate-preview",
    ]

    DEFAULT_VIDEO_MODEL = "veo-3.1-lite-generate-preview"

    # BytePlus ModelArk 影片費用（元/百萬 token），按 generate_audio 查表
    ARK_VIDEO_COST = {
        "doubao-seedance-2-0-260128": {
            ("default", True): 46.00,
            ("default", False): 46.00,
        },
    }

    DEFAULT_ARK_VIDEO_MODEL = "doubao-seedance-2-0-260128"
    DEFAULT_ARK_ENDPOINT_VIDEO_MODEL = "doubao-seedance-2-0-260128"
    # 預估用：每秒 tokens（按解析度）。實際以 API 回傳的 completion_tokens 計費。
    # 抓上限值，讓預估反映「最壞情況」費用。
    ARK_EST_TOKENS_PER_SECOND: dict[str, int] = {
        "480p": 6_000,
        "720p": 12_000,
        "1080p": 24_000,
    }

    # Grok 影片費用（美元/秒），不區分解析度
    # 來源：docs/grok-docs/models.md — $0.050/sec
    GROK_VIDEO_COST = {
        "grok-imagine-video": 0.050,
    }

    DEFAULT_GROK_MODEL = "grok-imagine-video"

    # Grok 圖片費用（美元/張）
    GROK_IMAGE_COST = {
        "grok-imagine-image": 0.02,
        "grok-imagine-image-pro": 0.07,
    }
    DEFAULT_GROK_IMAGE_MODEL = "grok-imagine-image"

    # Gemini 文字 token 費率（美元/百萬 token）
    GEMINI_TEXT_COST = {
        "gemini-3.1-flash-lite": {"input": 0.10, "output": 0.40},
    }

    # BytePlus ModelArk 文字 token 費率（元/百萬 token）
    ARK_TEXT_COST = {
        "doubao-seed-2-0-lite-260215": {"input": 0.30, "output": 0.60},
    }

    # Grok 文字 token 費率（美元/百萬 token）
    GROK_TEXT_COST = {
        "grok-4-1-fast-reasoning": {"input": 2.00, "output": 10.00},
    }

    # OpenAI 文字 token 費率（美元/百萬 token）
    OPENAI_TEXT_COST = {
        "gpt-5.5": {"input": 2.50, "output": 15.00},
        "gpt-5.5-mini": {"input": 0.75, "output": 4.50},
        "gpt-5.5-nano": {"input": 0.20, "output": 1.25},
    }
    # OpenAI 圖片費用（美元/張），按 (quality, size) 二維查表
    # 來源：https://platform.openai.com/docs/pricing — GPT Image
    OPENAI_IMAGE_COST: dict[str, dict[tuple[str, str], float]] = {
        "gpt-image-2": {
            ("low", "1024x1024"): 0.006,
            ("low", "1024x1536"): 0.005,
            ("low", "1536x1024"): 0.005,
            ("medium", "1024x1024"): 0.053,
            ("medium", "1024x1536"): 0.041,
            ("medium", "1536x1024"): 0.041,
            ("high", "1024x1024"): 0.211,
            ("high", "1024x1536"): 0.165,
            ("high", "1536x1024"): 0.165,
        },
    }
    OPENAI_IMAGE_COST["gpt-image-2-2026-04-21"] = OPENAI_IMAGE_COST["gpt-image-2"]
    DEFAULT_OPENAI_IMAGE_MODEL = "gpt-image-2"
    OPENAI_VIDEO_COST = {
        "sora-2": {"720p": 0.10},
        "sora-2-pro": {"720p": 0.30, "1024p": 0.50, "1080p": 0.70},
    }
    DEFAULT_OPENAI_VIDEO_MODEL = "sora-2"

    def calculate_ark_video_cost(
        self,
        usage_tokens: int,
        generate_audio: bool = True,
        model: str | None = None,
    ) -> tuple[float, str]:
        """
        計算 Ark 影片生成費用。

        Returns:
            (amount, currency) — 金額和幣種 (USD)
        """
        model = self._resolve_ark_video_cost_model(model)
        model_costs = self.ARK_VIDEO_COST.get(model, self.ARK_VIDEO_COST[self.DEFAULT_ARK_VIDEO_MODEL])
        key = ("default", generate_audio)
        price_per_million = model_costs.get(
            key,
            model_costs.get(("default", True), 16.00),
        )
        amount = usage_tokens / 1_000_000 * price_per_million
        return _to_usd(amount, "CNY")

    def _resolve_ark_video_cost_model(self, model: str | None) -> str:
        if model and model.startswith("ep-"):
            return self.DEFAULT_ARK_ENDPOINT_VIDEO_MODEL
        return model or self.DEFAULT_ARK_VIDEO_MODEL

    def _resolve_ark_video_usage_tokens(
        self,
        usage_tokens: int | None,
        *,
        duration_seconds: int | None,
        resolution: str | None,
    ) -> int:
        if usage_tokens is not None:
            return usage_tokens
        return self.estimate_ark_video_tokens(
            duration_seconds=duration_seconds or 8,
            resolution=resolution or "720p",
        )

    def estimate_ark_video_tokens(self, duration_seconds: int, resolution: str = "720p") -> int:
        """預估 Ark 影片的 completion_tokens（上限值）。

        實際以 API 回傳為準；此值僅供 UI 預估顯示。
        """
        per_sec = self.ARK_EST_TOKENS_PER_SECOND.get(resolution, self.ARK_EST_TOKENS_PER_SECOND["720p"])
        return duration_seconds * per_sec

    def calculate_image_cost(self, resolution: str = "1K", model: str = None) -> float:
        """
        計算圖片生成費用

        Args:
            resolution: 圖片解析度 ('512PX', '1K', '2K', '4K')
            model: 模型名稱，預設使用當前預設模型

        Returns:
            費用（美元）
        """
        model = model or self.DEFAULT_IMAGE_MODEL
        model_costs = self.IMAGE_COST.get(model, self.IMAGE_COST[self.DEFAULT_IMAGE_MODEL])
        default_cost = model_costs.get("1K") or self.IMAGE_COST[self.DEFAULT_IMAGE_MODEL]["1K"]
        return model_costs.get(resolution.upper(), default_cost)

    def calculate_video_cost(
        self,
        duration_seconds: int,
        resolution: str = "1080p",
        generate_audio: bool = True,
        model: str = None,
    ) -> float:
        """
        計算影片生成費用

        Args:
            duration_seconds: 影片時長（秒）
            resolution: 解析度 ('720p', '1080p', '4k')
            generate_audio: 是否生成音訊
            model: 模型名稱，預設使用當前預設模型

        Returns:
            費用（美元）
        """
        model = model or self.DEFAULT_VIDEO_MODEL
        model_costs = self.VIDEO_COST.get(model, self.VIDEO_COST[self.DEFAULT_VIDEO_MODEL])
        resolution = resolution.lower()
        cost_per_second = model_costs.get(
            (resolution, generate_audio),
            model_costs.get(("1080p", True)) or self.VIDEO_COST[self.DEFAULT_VIDEO_MODEL][("1080p", True)],
        )
        return duration_seconds * cost_per_second

    def calculate_ark_image_cost(
        self,
        model: str | None = None,
        n: int = 1,
    ) -> tuple[float, str]:
        """
        BytePlus 圖片模型未註冊；保留入口給舊呼叫路徑，固定回 0。

        Returns:
            (amount, currency) — 金額和幣種 (USD)
        """
        return _to_usd(0.0, "USD")

    def calculate_grok_image_cost(
        self,
        model: str | None = None,
        n: int = 1,
    ) -> tuple[float, str]:
        """
        Grok 圖片按張計費。

        Returns:
            (amount, currency) — 金額和幣種 (USD)
        """
        model = model or self.DEFAULT_GROK_IMAGE_MODEL
        per_image = self.GROK_IMAGE_COST.get(model, self.GROK_IMAGE_COST[self.DEFAULT_GROK_IMAGE_MODEL])
        return _to_usd(per_image * n, "USD")

    def calculate_grok_video_cost(
        self,
        duration_seconds: int,
        model: str | None = None,
    ) -> tuple[float, str]:
        """
        計算 Grok 影片生成費用。

        Args:
            duration_seconds: 影片時長（秒）
            model: 模型名稱

        Returns:
            (amount, currency) — 金額和幣種 (USD)
        """
        model = model or self.DEFAULT_GROK_MODEL
        per_second = self.GROK_VIDEO_COST.get(model, self.GROK_VIDEO_COST[self.DEFAULT_GROK_MODEL])
        return _to_usd(duration_seconds * per_second, "USD")

    def calculate_openai_image_cost(
        self,
        model: str | None = None,
        quality: str | None = None,
        size: str | None = None,
    ) -> tuple[float, str]:
        """
        OpenAI 圖片按 (quality, size) 計費。

        Returns:
            (amount, currency) — 金額和幣種 (USD)
        """
        model = model or self.DEFAULT_OPENAI_IMAGE_MODEL
        quality = quality or "medium"
        size = size or "1024x1024"
        model_costs = self.OPENAI_IMAGE_COST.get(model, self.OPENAI_IMAGE_COST[self.DEFAULT_OPENAI_IMAGE_MODEL])
        per_image = model_costs.get(
            (quality, size), model_costs.get((quality, "1024x1024"), model_costs.get(("medium", "1024x1024"), 0.034))
        )
        return _to_usd(per_image, "USD")

    def calculate_openai_video_cost(
        self,
        duration_seconds: int,
        model: str | None = None,
        resolution: str | None = None,
    ) -> tuple[float, str]:
        """
        計算 OpenAI 影片生成費用（按秒計費）。

        Returns:
            (amount, currency) — 金額和幣種 (USD)
        """
        model = model or self.DEFAULT_OPENAI_VIDEO_MODEL
        resolution = resolution or "720p"
        model_costs = self.OPENAI_VIDEO_COST.get(model, self.OPENAI_VIDEO_COST[self.DEFAULT_OPENAI_VIDEO_MODEL])
        per_second = model_costs.get(resolution, model_costs.get("720p"))
        return _to_usd(duration_seconds * per_second, "USD")

    _TEXT_COST_TABLES: dict[str, tuple[dict, str, str]] = {
        # provider -> (cost_table_attr, default_model, currency)
        PROVIDER_BYTEPLUS: ("ARK_TEXT_COST", "doubao-seed-2-0-lite-260215", "CNY"),
        PROVIDER_GROK: ("GROK_TEXT_COST", "grok-4-1-fast-reasoning", "USD"),
        PROVIDER_OPENAI: ("OPENAI_TEXT_COST", "gpt-5.5-mini", "USD"),
    }
    _TEXT_COST_DEFAULT = ("GEMINI_TEXT_COST", "gemini-3.1-flash-lite", "USD")

    def calculate_text_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        provider: str,
        model: str | None = None,
    ) -> tuple[float, str]:
        """計算文字生成費用。返回 (amount, currency)。"""
        provider = normalize_provider_id(provider)
        table_attr, default_model, currency = self._TEXT_COST_TABLES.get(provider, self._TEXT_COST_DEFAULT)
        cost_table = getattr(self, table_attr)
        model = model or default_model
        rates = cost_table.get(model, cost_table.get(default_model, {"input": 0.0, "output": 0.0}))
        amount = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
        return _to_usd(amount, currency)

    def calculate_cost(
        self,
        provider: str,
        call_type: CallType,
        *,
        model: str | None = None,
        resolution: str | None = None,
        duration_seconds: int | None = None,
        generate_audio: bool = True,
        usage_tokens: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        quality: str | None = None,
        size: str | None = None,
        custom_price_input: float | None = None,
        custom_price_output: float | None = None,
        custom_currency: str | None = None,
    ) -> tuple[float, str]:
        """統一費用計算入口。按 (call_type, provider) 顯式路由。返回 (amount, currency)。

        自定義供應商的價格資訊透過 custom_price_* 引數傳入（呼叫方需預先查詢 DB）。
        """
        provider = normalize_provider_id(provider)
        if is_custom_provider(provider):
            return self._calculate_custom_cost(
                call_type,
                price_input=custom_price_input,
                price_output=custom_price_output,
                currency=custom_currency,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_seconds=duration_seconds,
            )

        if call_type == "text":
            if input_tokens is None:
                return 0.0, "USD"
            return self.calculate_text_cost(
                input_tokens=input_tokens,
                output_tokens=output_tokens or 0,
                provider=provider,
                model=model,
            )

        if call_type == "image":
            if provider == PROVIDER_BYTEPLUS:
                return self.calculate_ark_image_cost(model=model)
            if provider == PROVIDER_GROK:
                return self.calculate_grok_image_cost(model=model)
            if provider == PROVIDER_OPENAI:
                return self.calculate_openai_image_cost(model=model, quality=quality, size=size)
            return self.calculate_image_cost(resolution or "1K", model=model), "USD"

        if call_type == "video":
            if provider == PROVIDER_BYTEPLUS:
                # 無實際 tokens（預估場景）時，按解析度×時長估上限
                return self.calculate_ark_video_cost(
                    usage_tokens=self._resolve_ark_video_usage_tokens(
                        usage_tokens,
                        duration_seconds=duration_seconds,
                        resolution=resolution,
                    ),
                    generate_audio=generate_audio,
                    model=model,
                )
            if provider == PROVIDER_GROK:
                return self.calculate_grok_video_cost(
                    duration_seconds=duration_seconds or 8,
                    model=model,
                )
            if provider == PROVIDER_OPENAI:
                return self.calculate_openai_video_cost(
                    duration_seconds=duration_seconds or 8,
                    model=model,
                    resolution=resolution or "720p",
                )
            return self.calculate_video_cost(
                duration_seconds=duration_seconds or 8,
                resolution=resolution or "1080p",
                generate_audio=generate_audio,
                model=model,
            ), "USD"

        return 0.0, "USD"

    @staticmethod
    def _calculate_custom_cost(
        call_type: str,
        *,
        price_input: float | None = None,
        price_output: float | None = None,
        currency: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        duration_seconds: int | None = None,
    ) -> tuple[float, str]:
        """根據呼叫方預查的價格資訊計算自定義供應商費用。"""
        if price_input is None:
            return _to_usd(0.0, "USD")

        cur = currency or "USD"

        if call_type == "text":
            inp = (input_tokens or 0) * price_input
            out = (output_tokens or 0) * (price_output or 0)
            return _to_usd((inp + out) / 1_000_000, cur)
        if call_type == "image":
            return _to_usd(price_input, cur)
        if call_type == "video":
            return _to_usd((duration_seconds or 8) * price_input, cur)
        return _to_usd(0.0, cur)


# 單例例項，方便使用
cost_calculator = CostCalculator()
