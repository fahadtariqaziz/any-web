"""Claude prices per million tokens, and token usage -> USD (spec §10.11, M11).

Source: the claude-api reference's model table (cached 2026-10-06; Anthropic first-party API rates). Input / output /
cache-read prices are listed there; cache WRITES use the standard multipliers of the input price (5-minute TTL 1.25x,
1-hour TTL 2x). Haiku 5.5's cache-read price is not listed: 0.1x input (the usual ratio) is assumed. Haiku 5.5 costs
more for prompts over 100K tokens ($0.50 / $2.50). Update this table when prices change (and the date below); a model
missing here is reported as "unpriced" (cost 0, flagged), never guessed.
"""

from dataclasses import dataclass

PRICES_AS_OF = "2026-10-06"


@dataclass(frozen=True)
class Price:
    input: float                 # $ per 1M uncached input tokens
    output: float                # $ per 1M output tokens (thinking included)
    cache_read: float            # $ per 1M tokens read from the prompt cache
    cache_write_5m: float        # $ per 1M tokens written to the 5-minute cache
    cache_write_1h: float        # $ per 1M tokens written to the 1-hour cache
    long_prompt_tokens: int | None = None    # above this many prompt tokens, `long` applies
    long: "Price | None" = None


def _price(input: float, output: float, cache_read: float | None = None, **extra) -> Price:
    return Price(input=input, output=output, cache_read=input * 0.1 if cache_read is None else cache_read,
                 cache_write_5m=input * 1.25, cache_write_1h=input * 2, **extra)


PRICES: dict[str, Price] = {
    "claude-opus-5-5": _price(4.00, 20.00, 0.20),
    "claude-sonnet-5-5": _price(2.00, 10.00, 0.20),
    "claude-haiku-5-5": _price(0.10, 0.50, long_prompt_tokens=100_000, long=_price(0.50, 2.50)),
}


@dataclass
class Tokens:
    """One call's usage, split the way it is billed. `input` = UNCACHED input tokens only."""
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0

    @property
    def prompt(self) -> int:
        return self.input + self.cache_read + self.cache_write_5m + self.cache_write_1h

    def as_dict(self) -> dict[str, int]:
        return {"input_tokens": self.input, "output_tokens": self.output, "cache_read_tokens": self.cache_read,
                "cache_write_tokens": self.cache_write_5m + self.cache_write_1h}


def tokens_from_langchain(usage: dict | None) -> Tokens:
    """From an AIMessage's `usage_metadata`. langchain-anthropic's `input_tokens` INCLUDES the cache tokens
    (checked in its _create_usage_metadata), so they are subtracted here."""
    if not usage:
        return Tokens()
    details = usage.get("input_token_details") or {}
    read = int(details.get("cache_read") or 0)
    w5 = int(details.get("ephemeral_5m_input_tokens") or 0)
    w1 = int(details.get("ephemeral_1h_input_tokens") or 0)
    if not (w5 or w1):
        w5 = int(details.get("cache_creation") or 0)          # TTL not reported: the default 5-minute cache
    total_in = int(usage.get("input_tokens") or 0)
    return Tokens(input=max(0, total_in - read - w5 - w1), output=int(usage.get("output_tokens") or 0),
                  cache_read=read, cache_write_5m=w5, cache_write_1h=w1)


def tokens_from_anthropic(usage: dict | None) -> Tokens:
    """From the raw API usage (Agent SDK ResultMessage.usage): `input_tokens` EXCLUDES cache tokens there."""
    if not usage:
        return Tokens()
    creation = usage.get("cache_creation") or {}
    w5 = int(creation.get("ephemeral_5m_input_tokens") or 0)
    w1 = int(creation.get("ephemeral_1h_input_tokens") or 0)
    if not (w5 or w1):
        w5 = int(usage.get("cache_creation_input_tokens") or 0)
    return Tokens(input=int(usage.get("input_tokens") or 0), output=int(usage.get("output_tokens") or 0),
                  cache_read=int(usage.get("cache_read_input_tokens") or 0), cache_write_5m=w5, cache_write_1h=w1)


def is_priced(model: str) -> bool:
    return model in PRICES


def cost_usd(model: str, tokens: Tokens) -> float:
    """USD for one call; 0.0 for a model missing from PRICES (callers flag it with is_priced)."""
    price = PRICES.get(model)
    if price is None:
        return 0.0
    if price.long and price.long_prompt_tokens and tokens.prompt > price.long_prompt_tokens:
        price = price.long
    return (tokens.input * price.input + tokens.output * price.output + tokens.cache_read * price.cache_read
            + tokens.cache_write_5m * price.cache_write_5m + tokens.cache_write_1h * price.cache_write_1h) / 1_000_000
