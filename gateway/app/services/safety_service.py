"""Safety pipeline for content filtering."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyResult:
    """Result of a safety check."""
    is_safe: bool
    reason: str | None = None
    suggested_response: str | None = None


class SafetyService:
    """Validates incoming and outgoing messages for age-appropriateness."""

    # Simple keyword-based filters for MVP
    DANGEROUS_KEYWORDS = [
        r"спички", r"огонь", r"розетк", r"нож", r"лекарств", r"таблетк",
        r"яд", r"убей", r"смерт", r"кров", r"адрес", r"телефон", r"номер"
    ]

    def check_text(self, text: str) -> SafetyResult:
        """Check text against safety rules."""
        text_lower = text.lower()

        # 1. Check for dangerous keywords
        for pattern in self.DANGEROUS_KEYWORDS:
            if re.search(pattern, text_lower):
                return SafetyResult(
                    is_safe=False,
                    reason=f"Matched dangerous pattern: {pattern}",
                    suggested_response=(
                        "Это очень важный вопрос, но он может быть опасным. "
                        "Давай лучше спросим об этом у мамы или папы? Они точно помогут!"
                    )
                )

        return SafetyResult(is_safe=True)
