"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";

const h = React.createElement;
const requestCache = new Map();
const TOKEN_STORAGE_KEY = "openTraderJWT";
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/+$/, "");
const KLINE_INTERVAL_OPTIONS = ["1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"];
const KLINE_INTERVAL_MINUTES = {
  "1m": 1,
  "5m": 5,
  "15m": 15,
  "1h": 60,
  "4h": 240,
  "1d": 1440,
  "1w": 10080,
  "1M": 43200,
};
const MIN_KLINE_BARS = 20;
const EQUITY_ANIMATION_DURATION_MS = 220;
const EQUITY_ANIMATION_EASING_POWER = 2.4;

function intervalSizeMinutes(interval) {
  return KLINE_INTERVAL_MINUTES[interval] || 1;
}

function baseKlineLimitForInterval(interval) {
  const factor = intervalSizeMinutes(interval);
  const desiredBars = 100;
  return Math.min(10000, Math.max(240, factor * desiredBars));
}

function safeReadToken() {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function saveToken(token) {
  try {
    if (!token) {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    // Ignore local storage failures in restricted environments.
  }
}

function buildQuery(params) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      query.set(key, String(value));
    }
  });
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

function buildApiUrl(path) {
  if (typeof path !== "string") {
    return API_BASE_URL;
  }
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  if (path.startsWith("/")) {
    return `${API_BASE_URL}${path}`;
  }
  return `${API_BASE_URL}/${path}`;
}

async function apiFetchJson(path, { token, method = "GET", body, dedupe = method === "GET" } = {}) {
  const cacheKey = `${method}:${path}:${body ? JSON.stringify(body) : ""}`;
  if (dedupe && requestCache.has(cacheKey)) {
    return requestCache.get(cacheKey);
  }

  const headers = { Accept: "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const task = fetch(buildApiUrl(path), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  }).then(async (response) => {
    const raw = await response.text();
    let payload = null;
    if (raw) {
      try {
        payload = JSON.parse(raw);
      } catch {
        payload = { detail: raw };
      }
    }

    if (!response.ok) {
      const detail = payload && payload.detail ? payload.detail : `${response.status} ${response.statusText}`;
      throw new Error(String(detail));
    }
    return payload || {};
  });

  if (dedupe) {
    requestCache.set(cacheKey, task);
  }

  try {
    return await task;
  } finally {
    if (dedupe) {
      requestCache.delete(cacheKey);
    }
  }
}

function settledValue(result, fallback) {
  if (result && result.status === "fulfilled") {
    return result.value;
  }
  return fallback;
}

function updateIfChanged(setter, newValue) {
  setter((prev) => {
    if (JSON.stringify(prev) === JSON.stringify(newValue)) {
      return prev;  // Same data, skip re-render
    }
    return newValue;
  });
}

function intervalBucketStart(timeMs, interval) {
  const date = new Date(timeMs);
  if (interval === "1w") {
    const weekday = date.getUTCDay();
    const diff = (weekday + 6) % 7;
    date.setUTCDate(date.getUTCDate() - diff);
    date.setUTCHours(0, 0, 0, 0);
    return date.getTime();
  }
  if (interval === "1M") {
    date.setUTCDate(1);
    date.setUTCHours(0, 0, 0, 0);
    return date.getTime();
  }
  const minutes = intervalSizeMinutes(interval);
  const minute = date.getUTCMinutes();
  const flooredMinute = minute - (minute % minutes);
  date.setUTCMinutes(flooredMinute, 0, 0);
  if (minutes >= 60) {
    const hourSpan = Math.max(1, Math.floor(minutes / 60));
    const flooredHour = date.getUTCHours() - (date.getUTCHours() % hourSpan);
    date.setUTCHours(flooredHour, 0, 0, 0);
  }
  if (minutes >= 1440) {
    date.setUTCHours(0, 0, 0, 0);
  }
  return date.getTime();
}

function normalizeBaseKline(item) {
  const rawTime = item && item.time ? item.time : "";
  const timeMs = Date.parse(String(rawTime));
  return {
    time: Number.isFinite(timeMs) ? new Date(timeMs).toISOString() : "",
    open: Number(item && item.open) || 0,
    high: Number(item && item.high) || 0,
    low: Number(item && item.low) || 0,
    close: Number(item && item.close) || 0,
    volume: Number(item && item.volume) || 0,
    quote_volume: Number(item && item.quote_volume) || 0,
    trades: Number(item && item.trades) || 0,
  };
}

function aggregateKlines(baseBars, interval) {
  const items = Array.isArray(baseBars) ? baseBars : [];
  if (interval === "1m") {
    return items.map(normalizeBaseKline);
  }
  const sorted = items
    .map((item) => {
      const rawTime = item && item.time ? item.time : "";
      const timeMs = Date.parse(String(rawTime));
      return {
        ...normalizeBaseKline(item),
        _timeMs: Number.isFinite(timeMs) ? timeMs : null,
      };
    })
    .filter((item) => item._timeMs != null)
    .sort((a, b) => a._timeMs - b._timeMs);
  if (sorted.length === 0) {
    return [];
  }
  const buckets = new Map();
  sorted.forEach((item) => {
    const bucketStart = intervalBucketStart(item._timeMs, interval);
    const key = String(bucketStart);
    const existing = buckets.get(key);
    if (!existing) {
      buckets.set(key, {
        time: new Date(bucketStart).toISOString(),
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
        volume: item.volume,
        quote_volume: item.quote_volume,
        trades: item.trades,
      });
      return;
    }
    existing.high = Math.max(existing.high, item.high);
    existing.low = Math.min(existing.low, item.low);
    existing.close = item.close;
    existing.volume += item.volume;
    existing.quote_volume += item.quote_volume;
    existing.trades += item.trades;
  });
  return Array.from(buckets.values()).sort((a, b) => Date.parse(a.time) - Date.parse(b.time));
}

function klineDataNotice(interval, baseCount, aggregatedCount) {
  const factor = intervalSizeMinutes(interval);
  if (aggregatedCount === 0) {
    return `No ${interval} bars available. Need at least ${factor} one-minute candles.`;
  }
  if (aggregatedCount < MIN_KLINE_BARS) {
    return `Only ${aggregatedCount} ${interval} bars available from ${baseCount} one-minute candles. More history is needed for a stable chart.`;
  }
  return "";
}

async function copyText(value) {
  const text = String(value || "").trim();
  if (!text) {
    return false;
  }
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const node = document.createElement("textarea");
      node.value = text;
      node.setAttribute("readonly", "");
      node.style.position = "absolute";
      node.style.left = "-9999px";
      document.body.appendChild(node);
      node.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(node);
      return Boolean(ok);
    } catch {
      return false;
    }
  }
}

function SectionCard({ title, subtitle, children }) {
  return h(
    "section",
    { className: "panel-card" },
    h("header", { className: "panel-header" }, h("h2", null, title), subtitle ? h("p", null, subtitle) : null),
    h("div", { className: "panel-body" }, children)
  );
}

function KeyStat({ label, value }) {
  return h("div", { className: "key-stat" }, h("span", { className: "stat-label" }, label), h("strong", null, value));
}

function JsonBlock({ value }) {
  const formatted = useMemo(() => JSON.stringify(value, null, 2), [value]);
  return h("pre", { className: "json-block" }, formatted);
}

function ChartLoadingPlaceholder({ label }) {
  return h(
    "div",
    { className: "chart-skeleton", "aria-live": "polite" },
    h("div", { className: "chart-skeleton-wave" }),
    h("p", { className: "muted" }, label || "Loading chart...")
  );
}

function linePath(points, width, height) {
  if (!Array.isArray(points) || points.length === 0) {
    return "";
  }
  const numeric = points.map((value) => Number(value) || 0);
  const min = Math.min(...numeric);
  const max = Math.max(...numeric);
  const span = max - min || 1;
  return numeric
    .map((value, index) => {
      const x = numeric.length === 1 ? width / 2 : (index / (numeric.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function pointerIndex(event, count) {
  if (!event || !event.currentTarget || count <= 0) {
    return null;
  }
  const rect = event.currentTarget.getBoundingClientRect();
  if (!rect || rect.width <= 0) {
    return null;
  }
  const ratio = (event.clientX - rect.left) / rect.width;
  const clamped = Math.max(0, Math.min(1, ratio));
  return Math.min(count - 1, Math.max(0, Math.round(clamped * (count - 1))));
}

function seriesSignature(items, timeKeys) {
  if (!Array.isArray(items) || items.length === 0) {
    return "empty";
  }
  const keys = Array.isArray(timeKeys) && timeKeys.length > 0 ? timeKeys : ["time"];
  const resolveTime = (item) => {
    if (!item || typeof item !== "object") {
      return "";
    }
    for (const key of keys) {
      if (item[key]) {
        return String(item[key]);
      }
    }
    return "";
  };
  const first = items[0];
  const last = items[items.length - 1];
  return `${items.length}:${resolveTime(first)}:${resolveTime(last)}`;
}

function EquityLineChart({ snapshots }) {
  const width = 760;
  const height = 180;
  const gridLines = 5;
  const [hoverIndex, setHoverIndex] = useState(null);
  const [pinnedIndex, setPinnedIndex] = useState(null);
  const [isReady, setIsReady] = useState(false);
  const items = Array.isArray(snapshots) ? snapshots : [];
  const values = useMemo(() => items.map((item) => Number(item.total_balance_usd) || 0), [items]);
  const [animatedValues, setAnimatedValues] = useState(values);
  const animatedValuesRef = useRef(animatedValues);
  const seriesKey = useMemo(() => seriesSignature(items, ["snapshot_time"]), [items]);

  useEffect(() => {
    animatedValuesRef.current = animatedValues;
  }, [animatedValues]);

  useEffect(() => {
    const target = values;
    const source = Array.isArray(animatedValuesRef.current) ? animatedValuesRef.current : [];
    if (target.length === 0) {
      setAnimatedValues([]);
      return;
    }
    if (source.length !== target.length) {
      setAnimatedValues(target);
      return;
    }
    let frameId = 0;
    const startedAt = performance.now();
    const durationMs = EQUITY_ANIMATION_DURATION_MS;
    const from = source.slice();
    const to = target.slice();
    const step = (now) => {
      const ratio = Math.max(0, Math.min(1, (now - startedAt) / durationMs));
      const eased = 1 - (1 - ratio) ** EQUITY_ANIMATION_EASING_POWER;
      const next = to.map((targetValue, index) => from[index] + (targetValue - from[index]) * eased);
      setAnimatedValues(next);
      if (ratio < 1) {
        frameId = window.requestAnimationFrame(step);
      }
    };
    frameId = window.requestAnimationFrame(step);
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [values]);

  useEffect(() => {
    setHoverIndex(null);
    setPinnedIndex(null);
  }, [seriesKey]);

  useEffect(() => {
    setIsReady(false);
    const frameId = window.requestAnimationFrame(() => setIsReady(true));
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [seriesKey]);

  const path = useMemo(() => linePath(animatedValues, width, height), [animatedValues]);
  const areaPath = useMemo(() => {
    if (!path) {
      return "";
    }
    return `${path} L ${width} ${height} L 0 ${height} Z`;
  }, [path, width, height]);
  const min = animatedValues.length > 0 ? Math.min(...animatedValues) : 0;
  const max = animatedValues.length > 0 ? Math.max(...animatedValues) : 1;
  const span = max - min || 1;
  const delta = values.length > 1 ? values[values.length - 1] - values[0] : 0;
  const deltaPct = values.length > 1 && values[0] !== 0 ? (delta / values[0]) * 100.0 : 0;

  const activeIndex = pinnedIndex != null ? pinnedIndex : hoverIndex;
  const activePoint = activeIndex != null && activeIndex >= 0 && activeIndex < items.length ? items[activeIndex] : null;
  const activeValue = activeIndex != null && activeIndex >= 0 && activeIndex < animatedValues.length ? animatedValues[activeIndex] : null;
  const activeX = activeIndex != null && animatedValues.length > 1 ? (activeIndex / (animatedValues.length - 1)) * width : width / 2;
  const activeY = activeValue == null ? null : height - ((activeValue - min) / span) * height;

  const handleMove = (event) => {
    const index = pointerIndex(event, items.length);
    if (index == null || pinnedIndex != null) {
      return;
    }
    setHoverIndex(index);
  };

  const handleClick = (event) => {
    const index = pointerIndex(event, items.length);
    if (index == null) {
      return;
    }
    setPinnedIndex((prev) => (prev === index ? null : index));
  };

  return h(
    "div",
    { className: isReady ? "chart-shell chart-ready" : "chart-shell chart-loading" },
    h(
      "svg",
      {
        viewBox: `0 0 ${width} ${height}`,
        className: "chart-svg chart-svg-interactive",
        role: "img",
        "aria-label": "Portfolio equity curve",
        onMouseMove: handleMove,
        onMouseLeave: () => {
          if (pinnedIndex == null) {
            setHoverIndex(null);
          }
        },
        onClick: handleClick,
      },
      h(
        "defs",
        null,
        h(
          "linearGradient",
          { id: "equityAreaGradient", x1: "0", x2: "0", y1: "0", y2: "1" },
          h("stop", { offset: "0%", stopColor: "rgba(32, 226, 181, 0.4)" }),
          h("stop", { offset: "100%", stopColor: "rgba(32, 226, 181, 0.04)" })
        )
      ),
      Array.from({ length: gridLines }, (_, index) => {
        const ratio = index / Math.max(1, gridLines - 1);
        const y = ratio * height;
        const value = max - ratio * span;
        return h(
          "g",
          { key: `equity-grid-${index}` },
          h("line", { x1: 0, x2: width, y1: y, y2: y, className: "chart-grid-line" }),
          h("text", { x: width - 4, y: Math.max(10, y - 2), className: "chart-grid-label", textAnchor: "end" }, value.toFixed(0))
        );
      }),
      areaPath ? h("path", { d: areaPath, className: "line-chart-area" }) : null,
      h("path", { d: path, className: "line-chart-path" }),
      activePoint && activeY != null
        ? h(
            "g",
            null,
            h("line", { x1: activeX, x2: activeX, y1: 0, y2: height, className: "chart-crosshair" }),
            h("line", { x1: 0, x2: width, y1: activeY, y2: activeY, className: "chart-crosshair" }),
            h("circle", { cx: activeX, cy: activeY, r: 3.4, className: "line-chart-point" })
          )
        : null
    ),
    h(
      "div",
      { className: "chart-metrics" },
      h("span", null, `Min $${min.toFixed(2)}`),
      h("span", null, `Max $${max.toFixed(2)}`),
      h("span", { className: delta >= 0 ? "metric-positive" : "metric-negative" }, `Δ ${delta >= 0 ? "+" : ""}${delta.toFixed(2)} (${deltaPct.toFixed(2)}%)`)
    ),
    activePoint
      ? h(
          "div",
          { className: "chart-tooltip" },
          h("strong", null, `$${(Number(activePoint.total_balance_usd) || 0).toFixed(2)}`),
          h("span", null, String(activePoint.snapshot_time || "")),
          h("span", null, `mode=${String(activePoint.mode || "")}`)
        )
      : h("div", { className: "chart-tooltip chart-tooltip-muted" }, "Hover or click to inspect values")
  );
}

function CandleChart({ bars }) {
  const width = 760;
  const height = 260;
  const volumeZone = 54;
  const plotHeight = height - volumeZone;
  const rightAxisWidth = 56;
  const chartWidth = width - rightAxisWidth;
  const gridLines = 6;
  const [hoverIndex, setHoverIndex] = useState(null);
  const [pinnedIndex, setPinnedIndex] = useState(null);
  const [isReady, setIsReady] = useState(false);
  const items = Array.isArray(bars) ? bars : [];
  const seriesKey = useMemo(() => seriesSignature(items, ["time"]), [items]);
  const prices = items.flatMap((bar) => [Number(bar.low) || 0, Number(bar.high) || 0]);
  const minPrice = prices.length > 0 ? Math.min(...prices) : 0;
  const maxPrice = prices.length > 0 ? Math.max(...prices) : 1;
  const span = maxPrice - minPrice || 1;
  const slot = items.length > 0 ? chartWidth / items.length : chartWidth;
  const candleWidth = Math.max(3, Math.min(8, slot * 0.55));
  const maxVolume = Math.max(
    1,
    ...items.map((bar) => Number(bar.volume) || 0),
  );

  const toY = (value) => {
    const numeric = Number(value) || 0;
    return plotHeight - ((numeric - minPrice) / span) * plotHeight;
  };
  const activeIndex = pinnedIndex != null ? pinnedIndex : hoverIndex;
  const activeBar = activeIndex != null && activeIndex >= 0 && activeIndex < items.length ? items[activeIndex] : null;
  const activeX = activeIndex != null ? activeIndex * slot + slot * 0.5 : null;

  useEffect(() => {
    setHoverIndex(null);
    setPinnedIndex(null);
  }, [seriesKey]);

  useEffect(() => {
    setIsReady(false);
    const frameId = window.requestAnimationFrame(() => setIsReady(true));
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [seriesKey]);

  const handleMove = (event) => {
    const index = pointerIndex(event, items.length);
    if (index == null || pinnedIndex != null) {
      return;
    }
    setHoverIndex(index);
  };

  const handleClick = (event) => {
    const index = pointerIndex(event, items.length);
    if (index == null) {
      return;
    }
    setPinnedIndex((prev) => (prev === index ? null : index));
  };

  return h(
    "div",
    { className: isReady ? "chart-shell chart-ready" : "chart-shell chart-loading" },
    h(
      "svg",
      {
        viewBox: `0 0 ${width} ${height}`,
        className: "chart-svg chart-svg-interactive",
        role: "img",
        "aria-label": "Candlestick chart",
        onMouseMove: handleMove,
        onMouseLeave: () => {
          if (pinnedIndex == null) {
            setHoverIndex(null);
          }
        },
        onClick: handleClick,
      },
      Array.from({ length: gridLines }, (_, index) => {
        const ratio = index / Math.max(1, gridLines - 1);
        const y = ratio * plotHeight;
        const price = maxPrice - ratio * span;
        return h(
          "g",
          { key: `k-grid-${index}` },
          h("line", { x1: 0, x2: chartWidth, y1: y, y2: y, className: "chart-grid-line" }),
          h("text", { x: width - 4, y: Math.max(10, y - 2), className: "chart-grid-label", textAnchor: "end" }, price.toFixed(2))
        );
      }),
      h("line", { x1: chartWidth, x2: chartWidth, y1: 0, y2: height, className: "chart-axis-separator" }),
      items.map((bar, index) => {
          const open = Number(bar.open) || 0;
          const close = Number(bar.close) || 0;
          const high = Number(bar.high) || 0;
          const low = Number(bar.low) || 0;
          const x = index * slot + slot * 0.5;
          const yOpen = toY(open);
          const yClose = toY(close);
          const yHigh = toY(high);
          const yLow = toY(low);
          const top = Math.min(yOpen, yClose);
          const bodyHeight = Math.max(1, Math.abs(yOpen - yClose));
          const bullish = close >= open;
          const volume = Number(bar.volume) || 0;
          const volHeight = Math.max(1, (volume / maxVolume) * (volumeZone - 8));
          const volY = height - volHeight;
          return h(
            "g",
            { key: `${bar.time || index}` },
            h("line", { x1: x, x2: x, y1: yHigh, y2: yLow, className: "candle-wick" }),
            h("rect", {
              x: x - candleWidth / 2,
              y: top,
              width: candleWidth,
              height: bodyHeight,
              className: bullish ? "candle-body up" : "candle-body down",
            }),
            h("rect", {
              x: x - candleWidth / 2,
              y: volY,
              width: candleWidth,
              height: volHeight,
              className: bullish ? "volume-bar up" : "volume-bar down",
            })
          );
        }),
      activeBar && activeX != null
        ? h(
            "g",
            null,
            h("line", { x1: activeX, x2: activeX, y1: 0, y2: height, className: "chart-crosshair" }),
            h("line", { x1: 0, x2: chartWidth, y1: toY(activeBar.close), y2: toY(activeBar.close), className: "chart-crosshair" })
          )
        : null
    ),
    h(
      "div",
      { className: "chart-metrics" },
      h("span", null, `High ${maxPrice.toFixed(2)}`),
      h("span", null, `Low ${minPrice.toFixed(2)}`),
      h("span", null, `Bars ${items.length}`)
    ),
    activeBar
      ? h(
          "div",
          { className: "chart-tooltip" },
          h("strong", null, String(activeBar.time || "")),
          h("span", null, `O ${Number(activeBar.open || 0).toFixed(2)} | H ${Number(activeBar.high || 0).toFixed(2)}`),
          h("span", null, `L ${Number(activeBar.low || 0).toFixed(2)} | C ${Number(activeBar.close || 0).toFixed(2)}`),
          h("span", null, `Volume ${Number(activeBar.volume || 0).toFixed(4)}`)
        )
      : h("div", { className: "chart-tooltip chart-tooltip-muted" }, "Hover or click to inspect OHLC")
  );
}

function HomeView({
  token,
  tokenInput,
  setTokenInput,
  tokenMessage,
  tokenPanelOpen,
  setTokenPanelOpen,
  setStoredToken,
  clearStoredToken,
}) {
  return h(
    "div",
    { className: "view-grid" },
    h(
      SectionCard,
      {
        title: "Session Token Tool",
        subtitle: "Token configuration is available only on Home via the tool icon.",
      },
      h(
        "div",
        { className: "button-row" },
        h(
          "button",
          {
            type: "button",
            className: tokenPanelOpen ? "button-secondary" : "",
            onClick: () => setTokenPanelOpen((current) => !current),
          },
          tokenPanelOpen ? "Hide Token Tool" : "Open Token Tool"
        )
      ),
      tokenPanelOpen
        ? h(
            "div",
            { className: "panel-body" },
            h(
              "div",
              { className: "filter-row" },
              h("input", {
                type: "password",
                placeholder: "JWT token",
                value: tokenInput,
                onChange: (event) => setTokenInput(event.target.value),
              }),
              h("button", { type: "button", onClick: setStoredToken }, "Save Token"),
              h("button", { type: "button", onClick: clearStoredToken }, "Clear")
            ),
            h("p", { className: "muted" }, token ? "Token is configured." : "No token configured."),
            h("p", { className: "muted" }, `API base: ${API_BASE_URL}`),
            tokenMessage ? h("p", { className: "muted" }, tokenMessage) : null
          )
        : h("p", { className: "muted" }, "Click the tool icon to manage session token.")
    ),
    h(
      SectionCard,
      {
        title: "Operator Workspace",
        subtitle: "Use these focused panels for governance, replay, mode controls, and news impact monitoring.",
      },
      h(
        "ul",
        { className: "link-list" },
        h("li", null, h("a", { href: "/notifications" }, "P7-016 Notification Observability")),
        h("li", null, h("a", { href: "/news" }, "P7-010 News Intelligence Panel")),
        h("li", null, h("a", { href: "/governance" }, "P7-007 Token Usage Dashboard")),
        h("li", null, h("a", { href: "/replay" }, "P7-008 Prompt/Response Inspector")),
        h("li", null, h("a", { href: "/mode" }, "P7-009 Trading Mode Panel"))
      )
    )
  );
}

function StatusView({ token }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [klineInterval, setKlineInterval] = useState("1m");
  const [readiness, setReadiness] = useState(null);
  const [riskStatus, setRiskStatus] = useState(null);
  const [klineSourceItems, setKlineSourceItems] = useState([]);
  const [equityHistory, setEquityHistory] = useState([]);
  const [latestSignal, setLatestSignal] = useState(null);
  const [orderbookSnapshot, setOrderbookSnapshot] = useState(null);
  const [recentTrades, setRecentTrades] = useState([]);
  const [pipelineHealth, setPipelineHealth] = useState(null);
  const [llmRuntime, setLlmRuntime] = useState(null);
  const [klineNotice, setKlineNotice] = useState("");
  const [klineLoading, setKlineLoading] = useState(false);
  const reloadSequenceRef = useRef(0);

  const reload = useCallback(async () => {
    const sequence = reloadSequenceRef.current + 1;
    reloadSequenceRef.current = sequence;
    setLoading(true);
    setError("");
    try {
      const ready = await apiFetchJson("/health/readiness", { token });
      if (reloadSequenceRef.current !== sequence) {
        return;
      }
      setReadiness(ready);
      if (token) {
        const baseLimit = baseKlineLimitForInterval(klineInterval);
        const [riskResult, klineResult, portfolioResult, signalResult, orderbookResult, tradesResult, pipelineResult, llmResult] = await Promise.allSettled([
          apiFetchJson("/ops/risk/status", { token }),
          apiFetchJson(`/ops/market/klines?symbol=BTC/USDT&interval=1m&limit=${baseLimit}`, { token }),
          apiFetchJson("/ops/portfolio/history?mode=MOCK&limit=80", { token }),
          apiFetchJson("/ops/signals/latest?limit=1", { token }),
          apiFetchJson("/ops/market/orderbook/latest?symbol=BTC/USDT", { token }),
          apiFetchJson("/ops/trades/latest?mode=MOCK&symbol=BTC/USDT&limit=20", { token }),
          apiFetchJson("/ops/pipeline/health?mode=MOCK", { token }),
          apiFetchJson("/ops/llm/runtime", { token }),
        ]);
        if (reloadSequenceRef.current !== sequence) {
          return;
        }
        const risk = settledValue(riskResult, null);
        const klines = settledValue(klineResult, { items: [] });
        const portfolio = settledValue(portfolioResult, { items: [] });
        const signals = settledValue(signalResult, { items: [] });
        const orderbook = settledValue(orderbookResult, null);
        const trades = settledValue(tradesResult, { items: [] });
        const pipeline = settledValue(pipelineResult, null);
        const llm = settledValue(llmResult, null);

        updateIfChanged(setRiskStatus, risk || null);
        updateIfChanged(setKlineSourceItems, Array.isArray(klines && klines.items) ? klines.items : []);
        setKlineLoading(false);
        updateIfChanged(setEquityHistory, Array.isArray(portfolio && portfolio.items) ? portfolio.items : []);
        updateIfChanged(setLatestSignal, Array.isArray(signals && signals.items) && signals.items.length > 0 ? signals.items[0] : null);
        updateIfChanged(setOrderbookSnapshot, orderbook && orderbook.symbol ? orderbook : null);
        updateIfChanged(setRecentTrades, Array.isArray(trades && trades.items) ? trades.items : []);
        updateIfChanged(setPipelineHealth, pipeline && Array.isArray(pipeline.stages) ? pipeline : null);
        updateIfChanged(setLlmRuntime, llm && typeof llm === "object" ? llm : null);
      } else {
        setRiskStatus(null);
        setKlineSourceItems([]);
        setEquityHistory([]);
        setLatestSignal(null);
        setOrderbookSnapshot(null);
        setRecentTrades([]);
        setPipelineHealth(null);
        setLlmRuntime(null);
        setKlineLoading(false);
      }
    } catch (exc) {
      if (reloadSequenceRef.current !== sequence) {
        return;
      }
      setError(String(exc.message || exc));
      setOrderbookSnapshot(null);
      setRecentTrades([]);
      setPipelineHealth(null);
      setLlmRuntime(null);
      setKlineNotice("");
      setKlineLoading(false);
    } finally {
      if (reloadSequenceRef.current === sequence) {
        setLoading(false);
      }
    }
  }, [token, klineInterval]);

  useEffect(() => {
    void reload();
    const poll = window.setInterval(() => {
      void reload();
    }, 5000);
    return () => window.clearInterval(poll);
  }, [reload]);

  const topBids = useMemo(
    () => (orderbookSnapshot && Array.isArray(orderbookSnapshot.bids) ? orderbookSnapshot.bids.slice(0, 5) : []),
    [orderbookSnapshot]
  );
  const topAsks = useMemo(
    () => (orderbookSnapshot && Array.isArray(orderbookSnapshot.asks) ? orderbookSnapshot.asks.slice(0, 5) : []),
    [orderbookSnapshot]
  );
  const pipelineStages = useMemo(
    () => (pipelineHealth && Array.isArray(pipelineHealth.stages) ? pipelineHealth.stages : []),
    [pipelineHealth]
  );
  const klineItems = useMemo(() => aggregateKlines(klineSourceItems, klineInterval), [klineSourceItems, klineInterval]);
  const candleChartKey = useMemo(() => `${klineInterval}:${seriesSignature(klineItems, ["time"])}`, [klineInterval, klineItems]);

  useEffect(() => {
    setKlineNotice(klineDataNotice(klineInterval, klineSourceItems.length, klineItems.length));
  }, [klineInterval, klineSourceItems.length, klineItems.length]);

  const handleKlineIntervalChange = useCallback(
    (interval) => {
      if (interval === klineInterval) {
        return;
      }
      setKlineLoading(true);
      setKlineSourceItems([]);
      setKlineNotice(`Loading ${interval} candles...`);
      setKlineInterval(interval);
    },
    [klineInterval]
  );

  return h(
    "div",
    { className: "view-grid" },
    h(
      SectionCard,
      { title: "System Status", subtitle: "FastAPI readiness and risk-control summary." },
      loading
        ? h("p", { className: "muted" }, "Loading status...")
        : h(
            "div",
            { className: "stats-grid" },
            h(KeyStat, { label: "Readiness", value: readiness ? readiness.status : "unknown" }),
            h(KeyStat, { label: "Mode", value: readiness ? readiness.mode : "unknown" }),
            h(KeyStat, {
              label: "Kill Switch",
              value: riskStatus ? String(riskStatus.kill_switch_enabled) : "n/a",
            }),
            h(KeyStat, {
              label: "Circuit Breaker",
              value: riskStatus ? String(riskStatus.circuit_breaker_open) : "n/a",
            })
          ),
      h("div", { className: "button-row" }, h("button", { type: "button", onClick: () => void reload() }, "Refresh")),
      error ? h("p", { className: "error" }, error) : null
    ),
    h(
      SectionCard,
      { title: "Pipeline Health", subtitle: "DB-backed dataflow checks for ingestion, decisions, and portfolio updates." },
      pipelineStages.length === 0
        ? h("p", { className: "muted" }, "No pipeline health snapshot available.")
        : h(
            "div",
            { className: "table-wrap" },
            h(
              "table",
              null,
              h(
                "thead",
                null,
                h("tr", null, h("th", null, "Stage"), h("th", null, "Status"), h("th", null, "Records"), h("th", null, "Age(s)"), h("th", null, "Latest"))
              ),
              h(
                "tbody",
                null,
                pipelineStages.map((item) =>
                  h(
                    "tr",
                    { key: String(item.stage || "") },
                    h("td", null, String(item.stage || "")),
                    h("td", null, String(item.status || "")),
                    h("td", null, String(item.records_total || 0)),
                    h("td", null, item.age_seconds == null ? "-" : Number(item.age_seconds).toFixed(1)),
                    h("td", null, String(item.latest_at || "-"))
                  )
                )
              )
            )
          )
    ),
    h(
      SectionCard,
      { title: "BTC/USDT Candles", subtitle: `Derived ${klineInterval} bars from 1m stream (auto-refresh every 2 seconds).` },
      h(
        "div",
        { className: "timeframe-switch" },
        KLINE_INTERVAL_OPTIONS.map((interval) =>
          h(
            "button",
            {
              key: interval,
              type: "button",
              className: interval === klineInterval ? "timeframe-pill active" : "timeframe-pill",
              onClick: () => handleKlineIntervalChange(interval),
            },
            interval
          )
        )
      ),
      klineLoading
        ? h(ChartLoadingPlaceholder, { label: `Loading ${klineInterval} candles...` })
        : klineItems.length === 0
          ? h("p", { className: "muted" }, "No one-minute kline data available.")
          : h(CandleChart, { key: candleChartKey, bars: klineItems }),
      klineNotice ? h("p", { className: "warning" }, klineNotice) : null,
      h(
        "div",
        { className: "button-row link-row" },
        h("a", { href: "/governance" }, "LLM Governance"),
        h("a", { href: "/replay" }, "Replay Inspector")
      )
    ),
    h(
      SectionCard,
      { title: "LLM Runtime", subtitle: "Runtime switch, provider order, and recent call persistence status." },
      llmRuntime
        ? h(
            "div",
            { className: "stats-grid" },
            h(KeyStat, { label: "Enabled", value: String(Boolean(llmRuntime.runtime_enabled)) }),
            h(KeyStat, { label: "LiteLLM URL", value: llmRuntime.litellm_base_url_configured ? "configured" : "missing" }),
            h(KeyStat, { label: "Calls", value: String(llmRuntime.total_calls || 0) }),
            h(KeyStat, { label: "Succeeded", value: String(llmRuntime.succeeded_calls || 0) }),
            h(KeyStat, { label: "Failed", value: String(llmRuntime.failed_calls || 0) }),
            h(KeyStat, { label: "Latest Call", value: String(llmRuntime.latest_call_at || "n/a") })
          )
        : h("p", { className: "muted" }, "No LLM runtime snapshot available."),
      llmRuntime && !llmRuntime.runtime_enabled
        ? h("p", { className: "muted" }, "Set LLM_RUNTIME_ENABLED=true and restart runtime_worker_orchestrator to activate LLM calls.")
        : null,
      llmRuntime && llmRuntime.runtime_enabled && !llmRuntime.litellm_base_url_configured
        ? h("p", { className: "error" }, "LITELLM_BASE_URL is missing. Configure it and restart runtime_worker_orchestrator.")
        : null,
      llmRuntime
        ? h(
            "p",
            { className: "muted" },
            `quick=${Array.isArray(llmRuntime.quick_provider_order) ? llmRuntime.quick_provider_order.join(" -> ") : "n/a"} | deep=${Array.isArray(llmRuntime.deep_provider_order) ? llmRuntime.deep_provider_order.join(" -> ") : "n/a"}`
          )
        : null
    ),
    h(
      SectionCard,
      { title: "Portfolio Equity", subtitle: "Mode=MOCK equity curve from /ops/portfolio/history." },
      equityHistory.length === 0 ? h("p", { className: "muted" }, "No portfolio history available.") : h(EquityLineChart, { snapshots: equityHistory }),
      latestSignal
        ? h(
            "div",
            { className: "signal-pill" },
            h("strong", null, `Latest Signal: ${latestSignal.action}`),
            h("span", null, `confidence=${Number(latestSignal.confidence || 0).toFixed(2)}`),
            h("span", null, `strategy=${latestSignal.strategy_id}`)
          )
        : h("p", { className: "muted" }, "No latest signal available.")
    ),
    h(
      SectionCard,
      { title: "Order Book (Top 5)", subtitle: "Latest snapshot from /ops/market/orderbook/latest." },
      orderbookSnapshot
        ? h(
            "div",
            { className: "stats-grid" },
            h(KeyStat, { label: "Best Bid", value: Number(orderbookSnapshot.best_bid || 0).toFixed(2) }),
            h(KeyStat, { label: "Best Ask", value: Number(orderbookSnapshot.best_ask || 0).toFixed(2) }),
            h(KeyStat, { label: "Spread (bps)", value: Number(orderbookSnapshot.spread_bps || 0).toFixed(3) })
          )
        : h("p", { className: "muted" }, "No orderbook snapshot available."),
      orderbookSnapshot
        ? h(
            "div",
            { className: "json-columns" },
            h(
              "div",
              { className: "mini-card" },
              h("h3", null, "Bids"),
              topBids.length === 0
                ? h("p", { className: "muted" }, "No bid levels.")
                : h(
                    "table",
                    null,
                    h("thead", null, h("tr", null, h("th", null, "Price"), h("th", null, "Amount"))),
                    h(
                      "tbody",
                      null,
                      topBids.map((level, index) =>
                        h(
                          "tr",
                          { key: `bid-${index}` },
                          h("td", null, Number(level.price || 0).toFixed(2)),
                          h("td", null, Number(level.amount || 0).toFixed(6))
                        )
                      )
                    )
                  )
            ),
            h(
              "div",
              { className: "mini-card" },
              h("h3", null, "Asks"),
              topAsks.length === 0
                ? h("p", { className: "muted" }, "No ask levels.")
                : h(
                    "table",
                    null,
                    h("thead", null, h("tr", null, h("th", null, "Price"), h("th", null, "Amount"))),
                    h(
                      "tbody",
                      null,
                      topAsks.map((level, index) =>
                        h(
                          "tr",
                          { key: `ask-${index}` },
                          h("td", null, Number(level.price || 0).toFixed(2)),
                          h("td", null, Number(level.amount || 0).toFixed(6))
                        )
                      )
                    )
                  )
            )
          )
        : null
    ),
    h(
      SectionCard,
      { title: "Recent Trades", subtitle: "Latest fills from /ops/trades/latest." },
      recentTrades.length === 0
        ? h("p", { className: "muted" }, "No recent trade records available.")
        : h(
            "div",
            { className: "table-wrap" },
            h(
              "table",
              null,
              h(
                "thead",
                null,
                h(
                  "tr",
                  null,
                  h("th", null, "Time"),
                  h("th", null, "Exchange"),
                  h("th", null, "Symbol"),
                  h("th", null, "Side"),
                  h("th", null, "Quantity"),
                  h("th", null, "Price"),
                  h("th", null, "Fee")
                )
              ),
              h(
                "tbody",
                null,
                recentTrades.map((item) =>
                  h(
                    "tr",
                    { key: `${item.fill_id}` },
                    h("td", null, String(item.filled_at || "")),
                    h("td", null, String(item.exchange || "")),
                    h("td", null, String(item.symbol || "")),
                    h("td", null, String(item.side || "")),
                    h("td", null, Number(item.quantity || 0).toFixed(6)),
                    h("td", null, Number(item.price || 0).toFixed(2)),
                    h("td", null, `${Number(item.fee || 0).toFixed(6)} ${item.fee_currency || ""}`.trim())
                  )
                )
              )
            )
          )
    )
  );
}

function GovernanceView({ token }) {
  const [strategyInput, setStrategyInput] = useState("");
  const [agentInput, setAgentInput] = useState("");
  const [callFilters, setCallFilters] = useState({ strategy_id: "", agent_name: "" });
  const [usageItems, setUsageItems] = useState([]);
  const [breachItems, setBreachItems] = useState([]);
  const [callItems, setCallItems] = useState([]);
  const [runtimeStatus, setRuntimeStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copyMessage, setCopyMessage] = useState("");
  const [refreshSeed, setRefreshSeed] = useState(0);
  const [isPending, startTransition] = useTransition();

  const load = useCallback(async () => {
    if (!token) {
      setError("Set JWT token to load governance data.");
      setUsageItems([]);
      setBreachItems([]);
      setCallItems([]);
      setRuntimeStatus(null);
      return;
    }

    setLoading(true);
    setError("");
    try {
      const [usagePayload, breachPayload, callPayload, runtimePayload] = await Promise.all([
        apiFetchJson("/governance/llm/usage", { token }),
        apiFetchJson("/governance/llm/breaches?include_failures=true&limit=300", { token }),
        apiFetchJson(`/governance/llm/calls${buildQuery({ ...callFilters, limit: 300 })}`, { token }),
        apiFetchJson("/ops/llm/runtime", { token }),
      ]);
      setUsageItems(Array.isArray(usagePayload.items) ? usagePayload.items : []);
      setBreachItems(Array.isArray(breachPayload.items) ? breachPayload.items : []);
      setCallItems(Array.isArray(callPayload.items) ? callPayload.items : []);
      setRuntimeStatus(runtimePayload && typeof runtimePayload === "object" ? runtimePayload : null);
    } catch (exc) {
      setError(String(exc.message || exc));
      setUsageItems([]);
      setBreachItems([]);
      setCallItems([]);
      setRuntimeStatus(null);
    } finally {
      setLoading(false);
    }
  }, [token, callFilters]);

  useEffect(() => {
    void load();
  }, [load, refreshSeed]);

  const applyFilters = () => {
    startTransition(() => {
      setCallFilters({ strategy_id: strategyInput.trim(), agent_name: agentInput.trim() });
      setRefreshSeed((value) => value + 1);
    });
  };

  const copyId = useCallback(async (value, label) => {
    const ok = await copyText(value);
    setCopyMessage(ok ? `${label} copied.` : `Failed to copy ${label}.`);
  }, []);

  return h(
    "div",
    { className: "view-grid" },
    h(
      SectionCard,
      {
        title: "Token Usage Dashboard",
        subtitle: "Global token/cost utilization across all strategies and agents.",
      },
      h(
        "div",
        { className: "filter-row" },
        h("input", {
          type: "text",
          placeholder: "Filter logs: strategy_id (optional)",
          value: strategyInput,
          onChange: (event) => setStrategyInput(event.target.value),
        }),
        h("input", {
          type: "text",
          placeholder: "Filter logs: agent_name (optional)",
          value: agentInput,
          onChange: (event) => setAgentInput(event.target.value),
        }),
        h("button", { type: "button", onClick: applyFilters, disabled: loading || isPending }, "Filter Logs"),
        h(
          "button",
          {
            type: "button",
            onClick: () => startTransition(() => setRefreshSeed((value) => value + 1)),
            disabled: loading || isPending,
          },
          "Refresh"
        )
      ),
      loading
        ? h("p", { className: "muted" }, "Loading governance data...")
        : null,
      runtimeStatus
        ? h(
            "div",
            { className: "stats-grid" },
            h(KeyStat, { label: "Runtime Enabled", value: String(Boolean(runtimeStatus.runtime_enabled)) }),
            h(KeyStat, { label: "LiteLLM URL", value: runtimeStatus.litellm_base_url_configured ? "configured" : "missing" }),
            h(KeyStat, { label: "Total Calls", value: String(runtimeStatus.total_calls || 0) }),
            h(KeyStat, { label: "Succeeded", value: String(runtimeStatus.succeeded_calls || 0) }),
            h(KeyStat, { label: "Failed", value: String(runtimeStatus.failed_calls || 0) }),
            h(KeyStat, { label: "Latest", value: String(runtimeStatus.latest_call_at || "n/a") })
          )
        : null,
      runtimeStatus && runtimeStatus.runtime_enabled && Number(runtimeStatus.total_calls || 0) === 0
        ? h(
            "p",
            { className: "warning" },
            "LLM runtime is enabled but no calls are persisted yet. Ensure both market and orchestrator workers are running and producing decisions."
          )
        : null,
      h("h3", null, "Usage by Strategy / Agent"),
      usageItems.length === 0
        ? h("p", { className: "muted" }, "No token usage rows found.")
        : h(
            "div",
            { className: "table-wrap" },
            h(
              "table",
              null,
              h(
                "thead",
                null,
                h(
                  "tr",
                  null,
                  h("th", null, "Strategy"),
                  h("th", null, "Agent"),
                  h("th", null, "Daily Tokens"),
                  h("th", null, "Daily Limit"),
                  h("th", null, "Monthly Cost"),
                  h("th", null, "Monthly Limit"),
                  h("th", null, "Breaches")
                )
              ),
              h(
                "tbody",
                null,
                usageItems.map((item) =>
                  h(
                    "tr",
                    { key: `${item.strategy_id}-${item.agent_name}`, className: "virtual-row" },
                    h("td", null, item.strategy_id),
                    h("td", null, item.agent_name),
                    h("td", null, String(item.daily_tokens)),
                    h("td", null, String(item.daily_token_limit ?? "-")),
                    h("td", null, Number(item.monthly_cost).toFixed(6)),
                    h("td", null, String(item.monthly_cost_limit ?? "-")),
                    h("td", null, String(item.breach_count))
                  )
                )
              )
            )
          ),
      h("h3", null, "Recent Breaches"),
      h(
        "div",
        { className: "table-wrap" },
        breachItems.length === 0
          ? h("p", { className: "muted" }, "No recent breaches or failed LLM calls.")
          : h(
              "table",
              null,
              h(
                "thead",
                null,
                h(
                  "tr",
                  null,
                  h("th", null, "Created At"),
                  h("th", null, "Strategy"),
                  h("th", null, "Agent"),
                  h("th", null, "Reason"),
                  h("th", null, "Decision"),
                  h("th", null, "Copy")
                )
              ),
              h(
                "tbody",
                null,
                breachItems.map((item) =>
                  h(
                    "tr",
                    { key: item.llm_call_id, className: "virtual-row" },
                    h("td", null, item.created_at),
                    h("td", null, item.strategy_id),
                    h("td", null, item.agent_name),
                    h("td", null, item.reason),
                    h("td", null, h("code", { className: "copy-id" }, item.decision_id)),
                    h(
                      "td",
                      null,
                      h(
                        "button",
                        { type: "button", className: "button-secondary", onClick: () => void copyId(item.decision_id, "decision_id") },
                        "Copy"
                      )
                    )
                  )
                )
              )
            )
      ),
      h("h3", null, "LLM Invocation Logs"),
      callItems.length === 0
        ? h("p", { className: "muted" }, "No LLM invocation logs found.")
        : h(
            "div",
            { className: "table-wrap" },
            h(
              "table",
              null,
              h(
                "thead",
                null,
                h(
                  "tr",
                  null,
                  h("th", null, "Created At"),
                  h("th", null, "Status"),
                  h("th", null, "Mode/Tier"),
                  h("th", null, "Provider/Model"),
                  h("th", null, "Strategy/Agent"),
                  h("th", null, "Tokens"),
                  h("th", null, "decision_id"),
                  h("th", null, "llm_call_id"),
                  h("th", null, "Prompt Preview"),
                  h("th", null, "Response Preview")
                )
              ),
              h(
                "tbody",
                null,
                callItems.map((item) =>
                  h(
                    "tr",
                    { key: item.llm_call_id, className: "virtual-row" },
                    h("td", null, String(item.created_at || "")),
                    h("td", null, String(item.status || "")),
                    h("td", null, `${item.mode || "-"} / ${item.tier || "-"}`),
                    h("td", null, `${item.provider || "-"} / ${item.model || "-"}`),
                    h("td", null, `${item.strategy_id || "-"} / ${item.agent_name || "-"}`),
                    h("td", null, String(item.total_tokens || 0)),
                    h(
                      "td",
                      null,
                      h("code", { className: "copy-id" }, String(item.decision_id || "")),
                      h(
                        "button",
                        { type: "button", className: "button-secondary", onClick: () => void copyId(item.decision_id, "decision_id") },
                        "Copy"
                      )
                    ),
                    h(
                      "td",
                      null,
                      h("code", { className: "copy-id" }, String(item.llm_call_id || "")),
                      h(
                        "button",
                        { type: "button", className: "button-secondary", onClick: () => void copyId(item.llm_call_id, "llm_call_id") },
                        "Copy"
                      )
                    ),
                    h("td", null, String(item.prompt_preview || "-")),
                    h("td", null, String(item.response_preview || "-"))
                  )
                )
              )
            )
          ),
      copyMessage ? h("p", { className: "muted" }, copyMessage) : null,
      error ? h("p", { className: "error" }, error) : null
    )
  );
}

function ReplayView({ token }) {
  const [decisionIdInput, setDecisionIdInput] = useState("");
  const [requestIdInput, setRequestIdInput] = useState("");
  const [decisionPayload, setDecisionPayload] = useState(null);
  const [requestPayload, setRequestPayload] = useState(null);
  const [catalog, setCatalog] = useState({ decisions: [], requests: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copyMessage, setCopyMessage] = useState("");

  const loadCatalog = useCallback(async () => {
    if (!token) {
      setCatalog({ decisions: [], requests: [] });
      return;
    }
    try {
      const payload = await apiFetchJson("/replay/catalog?decision_limit=400&request_limit=400", { token });
      setCatalog({
        decisions: Array.isArray(payload.decisions) ? payload.decisions : [],
        requests: Array.isArray(payload.requests) ? payload.requests : [],
      });
    } catch (exc) {
      setError(String(exc.message || exc));
      setCatalog({ decisions: [], requests: [] });
    }
  }, [token]);

  const loadDecision = useCallback(async () => {
    if (!token || !decisionIdInput.trim()) {
      setError("Provide JWT token and decision_id.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const payload = await apiFetchJson(`/replay/decisions/${encodeURIComponent(decisionIdInput.trim())}`, { token });
      setDecisionPayload(payload);
    } catch (exc) {
      setError(String(exc.message || exc));
      setDecisionPayload(null);
    } finally {
      setLoading(false);
    }
  }, [token, decisionIdInput]);

  const loadRequest = useCallback(async () => {
    if (!token || !requestIdInput.trim()) {
      setError("Provide JWT token and request_id.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const payload = await apiFetchJson(`/replay/requests/${encodeURIComponent(requestIdInput.trim())}`, { token });
      setRequestPayload(payload);
      setDecisionPayload(payload.result || null);
    } catch (exc) {
      setError(String(exc.message || exc));
    } finally {
      setLoading(false);
    }
  }, [token, requestIdInput]);

  const submitReplayRequest = useCallback(async () => {
    if (!token || !decisionIdInput.trim()) {
      setError("Provide JWT token and decision_id.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const payload = await apiFetchJson("/replay/requests", {
        token,
        method: "POST",
        body: { decision_id: decisionIdInput.trim() },
        dedupe: false,
      });
      setRequestPayload(payload);
      setDecisionPayload(payload.result || null);
      setRequestIdInput(payload.request_id || "");
      await loadCatalog();
    } catch (exc) {
      setError(String(exc.message || exc));
    } finally {
      setLoading(false);
    }
  }, [token, decisionIdInput, loadCatalog]);

  const llmCalls = useMemo(() => {
    if (!decisionPayload || !Array.isArray(decisionPayload.llm_calls)) {
      return [];
    }
    return decisionPayload.llm_calls;
  }, [decisionPayload]);

  const copyId = useCallback(async (value, label) => {
    const ok = await copyText(value);
    setCopyMessage(ok ? `${label} copied.` : `Failed to copy ${label}.`);
  }, []);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  return h(
    "div",
    { className: "view-grid" },
    h(
      SectionCard,
      {
        title: "Replay Inspector",
        subtitle: "Inspect replay results and raw prompt/response payloads by decision.",
      },
      h(
        "div",
        { className: "filter-row" },
        h("input", {
          type: "text",
          placeholder: "decision_id",
          value: decisionIdInput,
          onChange: (event) => setDecisionIdInput(event.target.value),
        }),
        h("button", { type: "button", onClick: () => void loadDecision(), disabled: loading }, "Fetch Decision"),
        h(
          "button",
          { type: "button", onClick: () => void submitReplayRequest(), disabled: loading },
          "Submit Replay Request"
        ),
        h("button", { type: "button", onClick: () => void loadCatalog(), disabled: loading }, "Refresh ID Catalog")
      ),
      h(
        "div",
        { className: "filter-row" },
        h("input", {
          type: "text",
          placeholder: "request_id",
          value: requestIdInput,
          onChange: (event) => setRequestIdInput(event.target.value),
        }),
        h("button", { type: "button", onClick: () => void loadRequest(), disabled: loading }, "Fetch Request")
      ),
      loading ? h("p", { className: "muted" }, "Loading replay data...") : null,
      h("h3", null, "Available decision_id values"),
      catalog.decisions.length === 0
        ? h("p", { className: "muted" }, "No decision traces found.")
        : h(
            "div",
            { className: "table-wrap" },
            h(
              "table",
              null,
              h(
                "thead",
                null,
                h(
                  "tr",
                  null,
                  h("th", null, "decision_id"),
                  h("th", null, "trace_id"),
                  h("th", null, "status"),
                  h("th", null, "started_at"),
                  h("th", null, "Actions")
                )
              ),
              h(
                "tbody",
                null,
                catalog.decisions.map((item) =>
                  h(
                    "tr",
                    { key: item.decision_id, className: "virtual-row" },
                    h("td", null, h("code", { className: "copy-id" }, String(item.decision_id || ""))),
                    h("td", null, h("code", { className: "copy-id" }, String(item.trace_id || ""))),
                    h("td", null, String(item.status || "")),
                    h("td", null, String(item.started_at || "")),
                    h(
                      "td",
                      null,
                      h(
                        "button",
                        {
                          type: "button",
                          className: "button-secondary",
                          onClick: () => {
                            setDecisionIdInput(String(item.decision_id || ""));
                          },
                        },
                        "Use"
                      ),
                      h(
                        "button",
                        { type: "button", className: "button-secondary", onClick: () => void copyId(item.decision_id, "decision_id") },
                        "Copy"
                      )
                    )
                  )
                )
              )
            )
          ),
      h("h3", null, "Available request_id values"),
      catalog.requests.length === 0
        ? h("p", { className: "muted" }, "No replay requests found.")
        : h(
            "div",
            { className: "table-wrap" },
            h(
              "table",
              null,
              h(
                "thead",
                null,
                h(
                  "tr",
                  null,
                  h("th", null, "request_id"),
                  h("th", null, "decision_id"),
                  h("th", null, "status"),
                  h("th", null, "requested_at"),
                  h("th", null, "Actions")
                )
              ),
              h(
                "tbody",
                null,
                catalog.requests.map((item) =>
                  h(
                    "tr",
                    { key: item.request_id, className: "virtual-row" },
                    h("td", null, h("code", { className: "copy-id" }, String(item.request_id || ""))),
                    h("td", null, h("code", { className: "copy-id" }, String(item.decision_id || ""))),
                    h("td", null, String(item.status || "")),
                    h("td", null, String(item.requested_at || "")),
                    h(
                      "td",
                      null,
                      h(
                        "button",
                        {
                          type: "button",
                          className: "button-secondary",
                          onClick: () => {
                            setRequestIdInput(String(item.request_id || ""));
                          },
                        },
                        "Use"
                      ),
                      h(
                        "button",
                        { type: "button", className: "button-secondary", onClick: () => void copyId(item.request_id, "request_id") },
                        "Copy"
                      )
                    )
                  )
                )
              )
            )
          ),
      requestPayload
        ? h(
            "div",
            null,
            h("h3", null, "Replay Request"),
            h(JsonBlock, { value: requestPayload })
          )
        : null,
      decisionPayload
        ? h(
            "div",
            null,
            h("h3", null, "Decision Replay"),
            h(JsonBlock, { value: decisionPayload })
          )
        : null,
      llmCalls.length > 0
        ? h(
            "div",
            null,
            h("h3", null, "Prompt / Response Calls"),
            llmCalls.map((call, index) =>
              h(
                "div",
                { key: `${call.llm_call_id || index}`, className: "llm-call" },
                h("h4", null, `${call.agent_name || "agent"} :: ${call.model || "model"}`),
                h("p", { className: "muted" }, `trace_id=${call.trace_id || "n/a"}`),
                h("div", { className: "json-columns" }, h(JsonBlock, { value: call.prompt_payload }), h(JsonBlock, { value: call.response_payload }))
              )
            )
          )
        : null,
      copyMessage ? h("p", { className: "muted" }, copyMessage) : null,
      error ? h("p", { className: "error" }, error) : null
    )
  );
}

function ModeView({ token }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState("MOCK");
  const [reason, setReason] = useState("");
  const [modePayload, setModePayload] = useState(null);
  const [historyItems, setHistoryItems] = useState([]);
  const [strategies, setStrategies] = useState([]);
  const [refreshSeed, setRefreshSeed] = useState(0);

  const loadModeData = useCallback(async () => {
    if (!token) {
      setError("Set JWT token to load mode panel data.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const [currentMode, modeHistory, strategyList] = await Promise.all([
        apiFetchJson("/control/mode", { token }),
        apiFetchJson("/control/mode/history?limit=30", { token }),
        apiFetchJson("/control/strategies", { token }),
      ]);
      setModePayload(currentMode);
      setMode(currentMode.mode || "MOCK");
      setHistoryItems(Array.isArray(modeHistory.items) ? modeHistory.items : []);
      setStrategies(Array.isArray(strategyList.items) ? strategyList.items : []);
    } catch (exc) {
      setError(String(exc.message || exc));
      setModePayload(null);
      setHistoryItems([]);
      setStrategies([]);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadModeData();
  }, [loadModeData, refreshSeed]);

  const submitModeChange = useCallback(async () => {
    if (!token) {
      setError("Set JWT token before sending mode updates.");
      return;
    }
    if (!reason.trim()) {
      setError("Reason is required for mode updates.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      await apiFetchJson("/control/mode", {
        token,
        method: "PUT",
        body: { mode, reason: reason.trim() },
        dedupe: false,
      });
      setReason("");
      setRefreshSeed((value) => value + 1);
    } catch (exc) {
      setError(String(exc.message || exc));
    } finally {
      setLoading(false);
    }
  }, [mode, reason, token]);

  return h(
    "div",
    { className: "view-grid" },
    h(
      SectionCard,
      { title: "Trading Mode Control", subtitle: "Display current mode and submit controlled updates." },
      h(
        "div",
        { className: "stats-grid" },
        h(KeyStat, { label: "Current Mode", value: modePayload ? modePayload.mode : "unknown" }),
        h(KeyStat, { label: "Last Updated", value: modePayload ? modePayload.updated_at : "unknown" }),
        h(KeyStat, { label: "Strategies", value: String(strategies.length) })
      ),
      h(
        "div",
        { className: "filter-row" },
        h(
          "select",
          { value: mode, onChange: (event) => setMode(event.target.value) },
          h("option", { value: "MOCK" }, "MOCK"),
          h("option", { value: "REAL" }, "REAL")
        ),
        h("input", {
          type: "text",
          placeholder: "reason",
          value: reason,
          onChange: (event) => setReason(event.target.value),
        }),
        h("button", { type: "button", onClick: () => void submitModeChange(), disabled: loading }, "Update Mode"),
        h("button", { type: "button", onClick: () => setRefreshSeed((value) => value + 1), disabled: loading }, "Refresh")
      ),
      loading ? h("p", { className: "muted" }, "Loading mode panel...") : null,
      h("h3", null, "Mode Audit History"),
      h(
        "div",
        { className: "table-wrap" },
        h(
          "table",
          null,
          h(
            "thead",
            null,
            h(
              "tr",
              null,
              h("th", null, "Changed At"),
              h("th", null, "Mode"),
              h("th", null, "Changed By"),
              h("th", null, "Reason")
            )
          ),
          h(
            "tbody",
            null,
            historyItems.map((item) =>
              h(
                "tr",
                { key: item.event_id, className: "virtual-row" },
                h("td", null, item.changed_at),
                h("td", null, item.mode),
                h("td", null, item.changed_by),
                h("td", null, item.reason)
              )
            )
          )
        )
      ),
      error ? h("p", { className: "error" }, error) : null
    )
  );
}

function NewsView({ token }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [symbolInput, setSymbolInput] = useState("");
  const [symbolFilter, setSymbolFilter] = useState("");
  const [newsItems, setNewsItems] = useState([]);
  const [summaryItems, setSummaryItems] = useState([]);
  const [impactItems, setImpactItems] = useState([]);
  const [refreshSeed, setRefreshSeed] = useState(0);

  const load = useCallback(async () => {
    if (!token) {
      setError("Set JWT token to load news panel data.");
      setNewsItems([]);
      setSummaryItems([]);
      setImpactItems([]);
      return;
    }

    const itemsQuery = buildQuery({ symbol: symbolFilter, limit: 50 });
    const summariesQuery = buildQuery({ symbol_scope: symbolFilter, limit: 20 });
    const impactQuery = buildQuery({ limit: 12 });

    setLoading(true);
    setError("");
    try {
      const [itemsPayload, summaryPayload, impactPayload] = await Promise.all([
        apiFetchJson(`/ops/news/items${itemsQuery}`, { token }),
        apiFetchJson(`/ops/news/summaries${summariesQuery}`, { token }),
        apiFetchJson(`/ops/news/impact${impactQuery}`, { token }),
      ]);
      setNewsItems(Array.isArray(itemsPayload.items) ? itemsPayload.items : []);
      setSummaryItems(Array.isArray(summaryPayload.items) ? summaryPayload.items : []);
      setImpactItems(Array.isArray(impactPayload.items) ? impactPayload.items : []);
    } catch (exc) {
      setError(String(exc.message || exc));
      setNewsItems([]);
      setSummaryItems([]);
      setImpactItems([]);
    } finally {
      setLoading(false);
    }
  }, [token, symbolFilter]);

  useEffect(() => {
    void load();
  }, [load, refreshSeed]);

  const applyFilter = () => {
    setSymbolFilter(symbolInput.trim().toUpperCase());
    setRefreshSeed((value) => value + 1);
  };

  return h(
    "div",
    { className: "view-grid" },
    h(
      SectionCard,
      {
        title: "News Intelligence",
        subtitle: "News stream, rolling summaries, and symbol impact snapshots.",
      },
      h(
        "div",
        { className: "filter-row" },
        h("input", {
          type: "text",
          placeholder: "symbol (BTC/ETH/SOL) optional",
          value: symbolInput,
          onChange: (event) => setSymbolInput(event.target.value),
        }),
        h("button", { type: "button", onClick: applyFilter, disabled: loading }, "Apply"),
        h("button", { type: "button", onClick: () => setRefreshSeed((value) => value + 1), disabled: loading }, "Refresh")
      ),
      loading ? h("p", { className: "muted" }, "Loading news panel data...") : null,
      h(
        "div",
        { className: "impact-grid" },
        impactItems.map((item) =>
          h(
            "article",
            { key: item.symbol, className: "impact-card" },
            h("h3", null, item.symbol),
            h("p", { className: "muted" }, `headlines=${item.headline_count}`),
            h("p", null, `avg_sentiment=${Number(item.avg_sentiment).toFixed(2)}`),
            h("p", null, `max_relevance=${Number(item.max_relevance).toFixed(2)}`)
          )
        )
      ),
      h("h3", null, "Latest News Stream"),
      h(
        "div",
        { className: "table-wrap" },
        h(
          "table",
          null,
          h(
            "thead",
            null,
            h(
              "tr",
              null,
              h("th", null, "Published"),
              h("th", null, "Source"),
              h("th", null, "Symbol"),
              h("th", null, "Topic"),
              h("th", null, "Headline"),
              h("th", null, "Sentiment")
            )
          ),
          h(
            "tbody",
            null,
            newsItems.map((item) =>
              h(
                "tr",
                { key: item.news_id, className: "virtual-row" },
                h("td", null, item.published_at),
                h("td", null, item.source),
                h("td", null, item.symbol || "GLOBAL"),
                h("td", null, item.topic),
                h("td", null, h("a", { href: item.url, target: "_blank", rel: "noreferrer" }, item.title)),
                h("td", null, Number(item.sentiment_score).toFixed(2))
              )
            )
          )
        )
      ),
      h("h3", null, "Rolling Summaries"),
      h(
        "div",
        { className: "summary-stack" },
        summaryItems.map((item) =>
          h(
            "article",
            { key: item.summary_id, className: "summary-card virtual-row" },
            h("h4", null, `${item.symbol_scope} :: ${item.window_start} -> ${item.window_end}`),
            h("p", null, item.summary_text),
            h(
              "p",
              { className: "muted" },
              `source_count=${item.source_count} avg_sentiment=${Number(item.avg_sentiment).toFixed(2)}`
            )
          )
        )
      ),
      error ? h("p", { className: "error" }, error) : null
    )
  );
}

function NotificationsView({ token }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [metrics, setMetrics] = useState(null);
  const [deliveries, setDeliveries] = useState([]);
  const [traces, setTraces] = useState([]);
  const [refreshSeed, setRefreshSeed] = useState(0);

  const load = useCallback(async () => {
    if (!token) {
      setError("Set JWT token to load notification telemetry.");
      setMetrics(null);
      setDeliveries([]);
      setTraces([]);
      return;
    }

    setLoading(true);
    setError("");
    try {
      const [metricsPayload, deliveriesPayload, tracesPayload] = await Promise.all([
        apiFetchJson("/ops/notifications/metrics", { token }),
        apiFetchJson("/ops/notifications/deliveries?limit=60", { token }),
        apiFetchJson("/ops/notifications/traces?limit=60", { token }),
      ]);
      setMetrics(metricsPayload);
      setDeliveries(Array.isArray(deliveriesPayload.items) ? deliveriesPayload.items : []);
      setTraces(Array.isArray(tracesPayload.items) ? tracesPayload.items : []);
    } catch (exc) {
      setError(String(exc.message || exc));
      setMetrics(null);
      setDeliveries([]);
      setTraces([]);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load, refreshSeed]);

  const totals = metrics && metrics.totals ? metrics.totals : null;
  const suppression = metrics && metrics.suppression ? metrics.suppression : {};
  const gatewayStatus = metrics && metrics.gateway_status ? metrics.gateway_status : {};
  const retryHistogram = metrics && metrics.retry_attempt_histogram ? metrics.retry_attempt_histogram : {};

  return h(
    "div",
    { className: "view-grid" },
    h(
      SectionCard,
      {
        title: "Notification Observability",
        subtitle: "Metrics, delivery logs, and trace spans for notification runtime.",
      },
      h(
        "div",
        { className: "button-row" },
        h("button", { type: "button", onClick: () => setRefreshSeed((value) => value + 1), disabled: loading }, "Refresh")
      ),
      loading ? h("p", { className: "muted" }, "Loading notification telemetry...") : null,
      totals
        ? h(
            "div",
            { className: "stats-grid" },
            h(KeyStat, { label: "Received", value: String(totals.received_total) }),
            h(KeyStat, { label: "Filtered", value: String(totals.filtered_total) }),
            h(KeyStat, { label: "Dispatched", value: String(totals.dispatched_total) }),
            h(KeyStat, { label: "Delivered", value: String(totals.delivered_total) }),
            h(KeyStat, { label: "Failed", value: String(totals.failed_total) }),
            h(KeyStat, { label: "DLQ", value: String(totals.dlq_total) })
          )
        : null,
      h(
        "div",
        { className: "json-columns" },
        h(
          "div",
          { className: "mini-card" },
          h("h3", null, "Suppression"),
          h(JsonBlock, { value: suppression })
        ),
        h(
          "div",
          { className: "mini-card" },
          h("h3", null, "Gateway Status"),
          h(JsonBlock, { value: gatewayStatus })
        ),
        h(
          "div",
          { className: "mini-card" },
          h("h3", null, "Retry Attempts"),
          h(JsonBlock, { value: retryHistogram })
        )
      ),
      h("h3", null, "Recent Deliveries"),
      h(
        "div",
        { className: "table-wrap" },
        h(
          "table",
          null,
          h(
            "thead",
            null,
            h(
              "tr",
              null,
              h("th", null, "Logged At"),
              h("th", null, "Event Type"),
              h("th", null, "Severity"),
              h("th", null, "Gateway"),
              h("th", null, "Status"),
              h("th", null, "Attempt"),
              h("th", null, "Trace ID")
            )
          ),
          h(
            "tbody",
            null,
            deliveries.map((item, index) =>
              h(
                "tr",
                { key: `${item.notification_event_id}-${item.gateway}-${index}`, className: "virtual-row" },
                h("td", null, item.logged_at),
                h("td", null, item.event_type),
                h("td", null, item.severity),
                h("td", null, item.gateway),
                h("td", null, item.delivery_status),
                h("td", null, String(item.attempt)),
                h("td", null, item.trace_id)
              )
            )
          )
        )
      ),
      h("h3", null, "Recent Trace Spans"),
      h(
        "div",
        { className: "table-wrap" },
        h(
          "table",
          null,
          h(
            "thead",
            null,
            h(
              "tr",
              null,
              h("th", null, "Completed At"),
              h("th", null, "Stage"),
              h("th", null, "Status"),
              h("th", null, "Latency (ms)"),
              h("th", null, "Trace ID"),
              h("th", null, "Decision ID")
            )
          ),
          h(
            "tbody",
            null,
            traces.map((item, index) =>
              h(
                "tr",
                { key: `${item.notification_event_id}-${item.stage}-${index}`, className: "virtual-row" },
                h("td", null, item.completed_at),
                h("td", null, item.stage),
                h("td", null, item.status),
                h("td", null, Number(item.latency_ms).toFixed(2)),
                h("td", null, item.trace_id),
                h("td", null, item.decision_id)
              )
            )
          )
        )
      ),
      error ? h("p", { className: "error" }, error) : null
    )
  );
}

function App({ initialView }) {
  const [token, setToken] = useState(() => safeReadToken());
  const [tokenInput, setTokenInput] = useState(() => safeReadToken());
  const [tokenMessage, setTokenMessage] = useState("");
  const [tokenPanelOpen, setTokenPanelOpen] = useState(false);
  const isHomeView = initialView === "home";

  const setStoredToken = () => {
    const value = tokenInput.trim();
    saveToken(value);
    setToken(value);
    setTokenMessage(value ? "Token updated." : "Token cleared.");
  };

  const clearStoredToken = () => {
    saveToken("");
    setToken("");
    setTokenInput("");
    setTokenMessage("Token cleared.");
  };

  useEffect(() => {
    if (!isHomeView) {
      setTokenPanelOpen(false);
    }
  }, [isHomeView]);

  const body = useMemo(() => {
    if (initialView === "notifications") {
      return h(NotificationsView, { token });
    }
    if (initialView === "news") {
      return h(NewsView, { token });
    }
    if (initialView === "governance") {
      return h(GovernanceView, { token });
    }
    if (initialView === "replay") {
      return h(ReplayView, { token });
    }
    if (initialView === "mode") {
      return h(ModeView, { token });
    }
    if (initialView === "status") {
      return h(StatusView, { token });
    }
    return h(HomeView, {
      token,
      tokenInput,
      setTokenInput,
      tokenMessage,
      tokenPanelOpen,
      setTokenPanelOpen,
      setStoredToken,
      clearStoredToken,
    });
  }, [initialView, token, tokenInput, tokenMessage, tokenPanelOpen]);

  const viewMeta = useMemo(() => {
    if (initialView === "notifications") {
      return {
        title: "Notification Observability",
        description: "Delivery metrics, failure logs, and trace spans across notification gateways.",
      };
    }
    if (initialView === "news") {
      return {
        title: "News Intelligence Panel",
        description: "News stream, rolling summaries, and symbol impact insights.",
      };
    }
    if (initialView === "governance") {
      return {
        title: "LLM Governance",
        description: "Token usage, cost utilization, and breach history by strategy and agent.",
      };
    }
    if (initialView === "replay") {
      return {
        title: "Replay Inspector",
        description: "Replay requests and prompt/response inspection by decision.",
      };
    }
    if (initialView === "mode") {
      return {
        title: "Trading Mode Panel",
        description: "Current mode, controlled mode switch, and audit-facing change history.",
      };
    }
    if (initialView === "status") {
      return {
        title: "Live Status",
        description: "Runtime readiness, market snapshots, and risk control status.",
      };
    }
    return {
      title: "Operations Dashboard",
      description: "Operator control plane with governance, replay, and mode controls.",
    };
  }, [initialView]);

  const navCards = [
    ["Dashboard Home", "/"],
    ["Live Status", "/status"],
    ["LLM Governance", "/governance"],
    ["Replay Inspector", "/replay"],
    ["Mode Panel", "/mode"],
    ["News Panel", "/news"],
    ["Notifications", "/notifications"],
  ];

  return h(
    "div",
    null,
    h(
      "header",
      { className: "dashboard-header" },
      h(
        "div",
        { className: "header-top-row" },
        h("div", null, h("h1", null, viewMeta.title), h("p", null, viewMeta.description)),
        isHomeView
          ? h(
              "button",
              {
                type: "button",
                className: "tool-toggle",
                title: "Session Token Tool",
                "aria-label": "Session Token Tool",
                onClick: () => setTokenPanelOpen((current) => !current),
              },
              "🛠"
            )
          : null
      ),
      h(
        "nav",
        { "aria-label": "dashboard-navigation" },
        h(
          "ul",
          { className: "dashboard-nav" },
          navCards.map((card) =>
            h(
              "li",
              { key: card[1] },
              h("a", { href: card[1], "aria-current": card[1] === (initialView === "home" ? "/" : `/${initialView}`) ? "page" : undefined }, card[0])
            )
          )
        )
      )
    ),
    h(
      "main",
      { className: "dashboard-root" },
      h(
        "div",
        { className: "app-shell" },
        body
      )
    )
  );
}

export default function DashboardClient({ initialView = "home" }) {
  return h(App, { initialView });
}
