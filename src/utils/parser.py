"""Price parsing utilities for extracting and normalizing price data."""

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ParsedPrice:
    """Represents a parsed price."""

    value: float
    currency: str
    original: str
    locale: Optional[str] = None


class PriceParser:
    """Parser for extracting and normalizing price values from various formats."""

    # Currency symbol to code mapping
    CURRENCY_SYMBOLS: Dict[str, str] = {
        "₪": "ILS",
        "ש״ח": "ILS",
        "שח": "ILS",
        "shekel": "ILS",
        "shekels": "ILS",
        "$": "USD",
        "€": "EUR",
        "£": "GBP",
        "¥": "JPY",
        "₹": "INR",
        "₽": "RUB",
        "kr": "SEK",
        "CHF": "CHF",
        "A$": "AUD",
        "C$": "CAD",
        "NZ$": "NZD",
    }

    # Currency code patterns
    CURRENCY_CODES: List[str] = [
        "ILS",
        "USD",
        "EUR",
        "GBP",
        "JPY",
        "INR",
        "RUB",
        "SEK",
        "CHF",
        "AUD",
        "CAD",
        "NZD",
    ]

    # Locale-based decimal/thousand separator detection
    LOCALE_PATTERNS: Dict[str, Tuple[str, str]] = {
        "us": (".", ","),  # 1,234.56
        "eu": (",", "."),  # 1.234,56
        "il": (".", ","),  # Israeli uses US format
    }

    def __init__(self, default_currency: str = "ILS"):
        """Initialize parser with default currency.

        Args:
            default_currency: Default currency code when none detected.
        """
        self.default_currency = default_currency

    def parse(
        self,
        price_string: str,
        currency_hint: Optional[str] = None,
    ) -> Optional[ParsedPrice]:
        """Parse a price string into structured format.

        Args:
            price_string: The price string to parse (e.g., "₪1,234.56").
            currency_hint: Optional currency hint if not in string.

        Returns:
            ParsedPrice object or None if parsing fails.
        """
        if not price_string:
            return None

        original = price_string.strip()
        currency = currency_hint or self._detect_currency(original)
        locale = self._detect_locale(original)
        value = self._extract_numeric_value(original, locale)

        if value is None:
            return None

        return ParsedPrice(
            value=value,
            currency=currency or self.default_currency,
            original=original,
            locale=locale,
        )

    def _detect_currency(self, text: str) -> Optional[str]:
        """Detect currency from text.

        Args:
            text: Text containing currency symbol or code.

        Returns:
            Currency code or None.
        """
        text_lower = text.lower()

        # Check for currency symbols
        for symbol, code in self.CURRENCY_SYMBOLS.items():
            if symbol in text or symbol.lower() in text_lower:
                return code

        # Check for currency codes
        text_upper = text.upper()
        for code in self.CURRENCY_CODES:
            if code in text_upper:
                return code

        return None

    def _detect_locale(self, text: str) -> str:
        """Detect locale from number format.

        Args:
            text: Text containing the number.

        Returns:
            Locale identifier.
        """
        # Remove currency symbols and letters
        cleaned = re.sub(r"[^\d.,\s]", "", text)

        # Count separators
        comma_count = cleaned.count(",")
        dot_count = cleaned.count(".")

        if comma_count == 0 and dot_count <= 1:
            return "us"  # 1234.56 or 1234

        if dot_count == 0 and comma_count == 1:
            # Could be "1,234" (US thousand) or "1,50" (EU decimal)
            parts = cleaned.split(",")
            if len(parts) == 2 and len(parts[1]) == 2:
                return "eu"  # Decimal with 2 places
            return "us"

        # Multiple commas = US thousands, single dot = decimal
        if comma_count >= 1 and dot_count == 1:
            # Check position: "1,234.56" vs "1.234,56"
            last_comma = cleaned.rfind(",")
            last_dot = cleaned.rfind(".")
            if last_dot > last_comma:
                return "us"
            return "eu"

        # Multiple dots = EU thousands, single comma = decimal
        if dot_count >= 1 and comma_count == 1:
            last_comma = cleaned.rfind(",")
            last_dot = cleaned.rfind(".")
            if last_comma > last_dot:
                return "eu"
            return "us"

        return "us"  # Default to US format

    def _extract_numeric_value(
        self,
        text: str,
        locale: str,
    ) -> Optional[float]:
        """Extract numeric value from text.

        Args:
            text: Text containing the number.
            locale: Locale identifier for separator interpretation.

        Returns:
            Float value or None if extraction fails.
        """
        # Remove all non-numeric characters except separators
        cleaned = re.sub(r"[^\d.,]", "", text)

        if not cleaned:
            return None

        decimal_sep, thousand_sep = self.LOCALE_PATTERNS.get(locale, (".", ","))

        # Remove thousand separators
        if thousand_sep in cleaned:
            cleaned = cleaned.replace(thousand_sep, "")

        # Normalize decimal separator
        if decimal_sep != ".":
            cleaned = cleaned.replace(decimal_sep, ".")

        try:
            return float(cleaned)
        except ValueError:
            logger.warning(f"Failed to parse price value: {text}")
            return None

    def extract_all_prices(
        self,
        text: str,
        currency_hints: Optional[List[str]] = None,
    ) -> List[ParsedPrice]:
        """Extract all prices from a text.

        Args:
            text: Text potentially containing multiple prices.
            currency_hints: List of currency symbols/codes to look for.

        Returns:
            List of parsed prices.
        """
        prices = []
        hints = currency_hints or ["₪", "$", "€", "ILS", "USD", "EUR"]

        # Build pattern for price matching
        # Matches: $1,234.56, 1234.56$, ₪ 1,234, 1.234,56€, etc.
        patterns = [
            # Currency symbol before number
            r"([₪$€£¥₹₽])\s*([\d.,]+)",
            # Number followed by currency symbol
            r"([\d.,]+)\s*([₪$€£¥₹₽])",
            # Number followed by currency code
            r"([\d.,]+)\s*(ILS|USD|EUR|GBP|JPY|CHF)",
            # Currency code before number
            r"(ILS|USD|EUR|GBP|JPY|CHF)\s*([\d.,]+)",
            # Hebrew shekel variations
            r"([\d.,]+)\s*(ש״ח|שח|שקל|שקלים)",
        ]

        seen_values = set()

        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                groups = match.groups()

                # Determine which group is the number
                if re.match(r"[\d.,]+", groups[0]):
                    num_str, curr_str = groups
                else:
                    curr_str, num_str = groups

                # Parse the price
                full_match = match.group(0)
                parsed = self.parse(full_match)

                if parsed and parsed.value not in seen_values:
                    seen_values.add(parsed.value)
                    prices.append(parsed)

        return prices

    def normalize_to_ils(
        self,
        value: float,
        from_currency: str,
        exchange_rates: Optional[Dict[str, float]] = None,
    ) -> float:
        """Convert a price to ILS using exchange rates.

        Args:
            value: Price value.
            from_currency: Source currency code.
            exchange_rates: Optional exchange rates dict (currency -> ILS rate).

        Returns:
            Value in ILS.
        """
        # Default exchange rates (approximate)
        default_rates = {
            "ILS": 1.0,
            "USD": 3.7,
            "EUR": 4.0,
            "GBP": 4.6,
            "JPY": 0.025,
            "CHF": 4.2,
        }

        rates = exchange_rates or default_rates
        rate = rates.get(from_currency.upper(), 1.0)

        return round(value * rate, 2)
