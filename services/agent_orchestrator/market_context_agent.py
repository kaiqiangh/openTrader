from __future__ import annotations

from typing import Any, Mapping

from services.agent_orchestrator.contracts import MarketContextOutput, StrategyConfig


class MarketContextAgent:
    def enrich(
        self,
        *,
        payload: Mapping[str, Any],
        strategy: StrategyConfig,
    ) -> MarketContextOutput:
        best_bid, best_bid_size = self._extract_level(payload.get("bids"), side="bid")
        best_ask, best_ask_size = self._extract_level(payload.get("asks"), side="ask")

        if best_bid is not None and best_ask is not None:
            mid_price = (best_bid + best_ask) / 2.0
            spread_bps = ((best_ask - best_bid) / mid_price * 10_000.0) if mid_price > 0 else 0.0
        else:
            mid_price = self._to_float(payload.get("mid_price"), default=0.0)
            spread_bps = 0.0

        depth_total = best_bid_size + best_ask_size
        orderbook_imbalance = 0.0
        if depth_total > 0:
            orderbook_imbalance = (best_bid_size - best_ask_size) / depth_total

        has_orderbook = best_bid is not None and best_ask is not None
        microstructure_regime = self._microstructure_regime(
            has_orderbook=has_orderbook,
            orderbook_imbalance=orderbook_imbalance,
        )

        news_summary, news_sentiment, news_source_count, news_fallback = self._extract_news(payload)
        notes: list[str] = []
        if not has_orderbook:
            notes.append("orderbook_unavailable")
        if news_fallback:
            notes.append("news_unavailable")

        quality = {
            "has_orderbook": has_orderbook,
            "has_news": not news_fallback,
            "context_score": self._context_score(
                has_orderbook=has_orderbook, has_news=not news_fallback
            ),
        }
        news = {
            "summary": news_summary,
            "sentiment": news_sentiment,
            "source_count": news_source_count,
            "is_fallback": news_fallback,
        }
        microstructure = {
            "spread_bps": spread_bps,
            "orderbook_imbalance": orderbook_imbalance,
            "regime": microstructure_regime,
        }

        context = {
            "exchange": payload.get("exchange", "unknown"),
            "symbol": payload.get("symbol", strategy.symbol),
            "timestamp_ms": payload.get("timestamp_ms"),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "best_bid_size": best_bid_size,
            "best_ask_size": best_ask_size,
            "mid_price": mid_price,
            "spread_bps": spread_bps,
            "orderbook_imbalance": orderbook_imbalance,
            "microstructure_regime": microstructure_regime,
            "current_position": self._to_float(payload.get("current_position"), default=0.0),
            "drawdown_pct": self._to_float(payload.get("drawdown_pct"), default=0.0),
            "news_summary": news_summary,
            "news_sentiment": news_sentiment,
            "news_source_count": news_source_count,
        }

        return MarketContextOutput(
            context=context,
            microstructure=microstructure,
            news=news,
            quality=quality,
            notes=tuple(notes),
        )

    @staticmethod
    def _extract_level(levels: Any, *, side: str) -> tuple[float | None, float]:
        if not isinstance(levels, list) or len(levels) == 0:
            return None, 0.0

        parsed: list[tuple[float, float]] = []
        for level in levels:
            if not isinstance(level, Mapping):
                continue
            try:
                price = float(level["price"])
                size = float(level["amount"])
            except (KeyError, TypeError, ValueError):
                continue
            parsed.append((price, max(0.0, size)))

        if not parsed:
            return None, 0.0

        if side == "bid":
            price, size = max(parsed, key=lambda item: item[0])
            return price, size

        price, size = min(parsed, key=lambda item: item[0])
        return price, size

    @staticmethod
    def _microstructure_regime(*, has_orderbook: bool, orderbook_imbalance: float) -> str:
        if not has_orderbook:
            return "unknown"
        if orderbook_imbalance >= 0.2:
            return "bid_dominant"
        if orderbook_imbalance <= -0.2:
            return "ask_dominant"
        return "balanced"

    def _extract_news(self, payload: Mapping[str, Any]) -> tuple[str, float, int, bool]:
        news_payload = payload.get("news")
        if not isinstance(news_payload, Mapping):
            return "news_unavailable", 0.0, 0, True

        summary = str(news_payload.get("summary", "news_unavailable")).strip() or "news_unavailable"
        sentiment = self._to_float(news_payload.get("sentiment"), default=0.0)
        source_count = self._to_int(news_payload.get("source_count"), default=0)
        fallback = summary == "news_unavailable"
        return summary, sentiment, source_count, fallback

    @staticmethod
    def _context_score(*, has_orderbook: bool, has_news: bool) -> float:
        score = 0.0
        if has_orderbook:
            score += 0.8
        if has_news:
            score += 0.2
        return min(1.0, score)

    @staticmethod
    def _to_float(value: Any, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_int(value: Any, *, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
