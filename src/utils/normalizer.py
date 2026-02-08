"""Text normalization utilities for product names and descriptions."""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class NormalizedProduct:
    """Represents a normalized product name."""

    normalized: str
    brand: Optional[str] = None
    model: Optional[str] = None
    category_hints: List[str] = field(default_factory=list)
    original: str = ""


@dataclass
class ProductSpecs:
    """Extracted product specifications."""

    memory: Optional[str] = None
    storage: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    display: Optional[str] = None
    processor: Optional[str] = None
    raw_specs: List[str] = field(default_factory=list)


class TextNormalizer:
    """Normalizer for product names and text."""

    # Common stopwords (English and Hebrew)
    STOPWORDS: Set[str] = {
        # English
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "been",
        "be",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "dare",
        "ought",
        "used",
        "new",
        "brand",
        "original",
        "authentic",
        "genuine",
        "official",
        "sealed",
        # Hebrew
        "את",
        "של",
        "על",
        "עם",
        "או",
        "אבל",
        "גם",
        "רק",
        "כל",
        "זה",
        "זו",
        "אלה",
        "הזה",
        "הזו",
        "חדש",
        "מקורי",
    }

    # Known brands (tech, electronics, fashion)
    KNOWN_BRANDS: Dict[str, List[str]] = {
        "apple": ["iphone", "ipad", "macbook", "airpods", "apple watch", "imac"],
        "samsung": ["galaxy", "note", "tab", "buds"],
        "google": ["pixel", "nest", "chromecast"],
        "microsoft": ["surface", "xbox"],
        "sony": ["playstation", "ps5", "ps4", "xperia", "bravia"],
        "lg": ["gram", "oled", "stylo"],
        "dell": ["xps", "inspiron", "latitude", "alienware"],
        "hp": ["pavilion", "spectre", "envy", "omen"],
        "lenovo": ["thinkpad", "ideapad", "yoga", "legion"],
        "asus": ["zenbook", "rog", "vivobook", "tuf"],
        "acer": ["predator", "aspire", "nitro", "swift"],
        "xiaomi": ["mi", "redmi", "poco"],
        "huawei": ["mate", "p30", "p40", "nova"],
        "oneplus": ["nord"],
        "oppo": ["find", "reno"],
        "nike": ["air", "jordan", "dunk"],
        "adidas": ["ultraboost", "yeezy", "stan smith"],
        "dyson": ["v15", "v12", "v11", "airwrap"],
        "bose": ["quietcomfort", "soundlink"],
        "jbl": ["flip", "charge", "pulse"],
    }

    # Category detection patterns
    CATEGORY_PATTERNS: Dict[str, List[str]] = {
        "smartphone": [
            r"iphone",
            r"galaxy\s*s\d+",
            r"pixel\s*\d+",
            r"smartphone",
            r"phone",
            r"טלפון",
        ],
        "laptop": [
            r"macbook",
            r"laptop",
            r"notebook",
            r"לפטופ",
            r"מחשב נייד",
        ],
        "tablet": [
            r"ipad",
            r"galaxy\s*tab",
            r"tablet",
            r"טאבלט",
        ],
        "headphones": [
            r"airpods",
            r"buds",
            r"headphones",
            r"earbuds",
            r"אוזניות",
        ],
        "smartwatch": [
            r"apple\s*watch",
            r"galaxy\s*watch",
            r"smartwatch",
            r"שעון חכם",
        ],
        "gaming": [
            r"playstation",
            r"ps[45]",
            r"xbox",
            r"nintendo",
            r"switch",
        ],
        "tv": [
            r"tv",
            r"television",
            r"oled",
            r"qled",
            r'"\s*inch',
            r"טלוויזיה",
        ],
    }

    # Spec patterns
    SPEC_PATTERNS: Dict[str, List[str]] = {
        "memory": [
            r"(\d+)\s*GB\s*RAM",
            r"(\d+)GB\s+RAM",
            r"RAM[:\s]*(\d+)\s*GB",
            r"(\d+)\s*GB\s+memory",
        ],
        "storage": [
            r"(\d+)\s*(GB|TB)\s*(SSD|HDD|storage|rom)",
            r"(SSD|HDD)[:\s]*(\d+)\s*(GB|TB)",
            r"(\d+)\s*(GB|TB)\s+internal",
        ],
        "display": [
            r'(\d+(?:\.\d+)?)\s*["\']?\s*inch',
            r'(\d+(?:\.\d+)?)\s*["\']?\s*display',
            r"(\d+)\s*אינץ",
        ],
        "processor": [
            r"(i[357]-\d{4,5}[A-Z]*)",
            r"(Ryzen\s*[357959]\s*\d{4}[A-Z]*)",
            r"(M[123]\s*(Pro|Max|Ultra)?)",
            r"(Snapdragon\s*\d+)",
            r"(A\d{2}\s*Bionic)",
        ],
        "color": [
            r"(black|white|silver|gold|gray|grey|blue|red|green|pink|purple|rose\s*gold|space\s*gray|midnight|starlight)",
            r"(שחור|לבן|כסוף|זהב|אפור|כחול|אדום|ירוק|ורוד|סגול)",
        ],
        "size": [
            r"(XS|S|M|L|XL|XXL|XXXL)",
            r"size[:\s]*([\d.]+)",
            r"(\d+)\s*mm",
            r"(\d+)\s*cm",
        ],
    }

    def __init__(self, remove_stopwords: bool = True):
        """Initialize normalizer.

        Args:
            remove_stopwords: Whether to remove stopwords during normalization.
        """
        self.remove_stopwords = remove_stopwords
        self._build_brand_lookup()

    def _build_brand_lookup(self) -> None:
        """Build reverse lookup for product patterns to brands."""
        self.product_to_brand: Dict[str, str] = {}
        for brand, products in self.KNOWN_BRANDS.items():
            for product in products:
                self.product_to_brand[product.lower()] = brand

    def normalize(self, product_name: str) -> NormalizedProduct:
        """Normalize a product name.

        Args:
            product_name: Original product name.

        Returns:
            NormalizedProduct with normalized name and extracted info.
        """
        original = product_name
        text = product_name.lower().strip()

        # Detect brand
        brand = self._detect_brand(text)

        # Detect model
        model = self._detect_model(text, brand)

        # Detect categories
        categories = self._detect_categories(text)

        # Clean and normalize text
        normalized = self._clean_text(text)

        return NormalizedProduct(
            normalized=normalized,
            brand=brand,
            model=model,
            category_hints=categories,
            original=original,
        )

    def _detect_brand(self, text: str) -> Optional[str]:
        """Detect brand from text.

        Args:
            text: Lowercase text.

        Returns:
            Brand name or None.
        """
        # Direct brand match
        for brand in self.KNOWN_BRANDS.keys():
            if brand in text:
                return brand.title()

        # Product pattern match
        for product, brand in self.product_to_brand.items():
            if product in text:
                return brand.title()

        return None

    def _detect_model(self, text: str, brand: Optional[str]) -> Optional[str]:
        """Detect model number/name from text.

        Args:
            text: Lowercase text.
            brand: Detected brand if any.

        Returns:
            Model name or None.
        """
        model_patterns = [
            # iPhone models
            r"iphone\s*(\d{1,2}(?:\s*(?:pro|plus|max|mini))*)",
            # Samsung Galaxy models
            r"galaxy\s*(s\d{1,2}(?:\s*(?:plus|ultra|fe))?|note\s*\d{1,2}|a\d{1,2}|z\s*(?:fold|flip)\s*\d?)",
            # MacBook models
            r"macbook\s*(air|pro)?\s*(\d{1,2}(?:\.\d)?)?",
            # iPad models
            r"ipad\s*(air|pro|mini)?\s*(\d{1,2})?",
            # Generic model numbers
            r"model[:\s#]*([A-Z0-9-]+)",
            r"([A-Z]{2,}\d{3,}[A-Z]*)",
        ]

        for pattern in model_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                model = " ".join(g for g in match.groups() if g)
                return model.strip().title() if model else None

        return None

    def _detect_categories(self, text: str) -> List[str]:
        """Detect product categories from text.

        Args:
            text: Lowercase text.

        Returns:
            List of category hints.
        """
        categories = []

        for category, patterns in self.CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    if category not in categories:
                        categories.append(category)
                    break

        return categories

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text.

        Args:
            text: Text to clean.

        Returns:
            Cleaned text.
        """
        # Remove URLs
        text = re.sub(r"https?://\S+", "", text)

        # Remove special characters but keep Hebrew and alphanumeric
        text = re.sub(r"[^\w\s\u0590-\u05FF-]", " ", text)

        # Normalize whitespace
        text = " ".join(text.split())

        # Remove stopwords if enabled
        if self.remove_stopwords:
            words = text.split()
            words = [w for w in words if w.lower() not in self.STOPWORDS]
            text = " ".join(words)

        return text.strip()

    def extract_specs(self, text: str) -> ProductSpecs:
        """Extract technical specifications from text.

        Args:
            text: Text containing specifications.

        Returns:
            ProductSpecs with extracted specifications.
        """
        specs = ProductSpecs()
        raw_specs = []

        for spec_type, patterns in self.SPEC_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value = " ".join(g for g in match.groups() if g)
                    value = value.strip()

                    if value:
                        setattr(specs, spec_type, value)
                        raw_specs.append(f"{spec_type}: {value}")
                        break

        specs.raw_specs = raw_specs
        return specs

    def similarity_score(self, name1: str, name2: str) -> float:
        """Calculate similarity between two product names.

        Args:
            name1: First product name.
            name2: Second product name.

        Returns:
            Similarity score between 0 and 1.
        """
        # Normalize both names
        norm1 = self.normalize(name1)
        norm2 = self.normalize(name2)

        # Convert to word sets
        words1 = set(norm1.normalized.lower().split())
        words2 = set(norm2.normalized.lower().split())

        if not words1 or not words2:
            return 0.0

        # Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)

        jaccard = intersection / union if union > 0 else 0

        # Bonus for matching brand/model
        bonus = 0
        if norm1.brand and norm1.brand == norm2.brand:
            bonus += 0.2
        if norm1.model and norm1.model == norm2.model:
            bonus += 0.3

        return min(1.0, jaccard + bonus)
