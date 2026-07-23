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

    SUPERVISED_OUTDOOR_PERMISSION = "supervised_outdoor_safety"
    POISON_PATTERN = r"\bяд(?:а|у|ом|ы|ов)?\b|ядовит"
    NATURE_HAZARD_CONTEXT_PATTERN = (
        r"гриб|ягод|растен|трав|куст|дерев|цвет|зме|клещ|насеком|паук|"
        r"живот|хищн|волк|медвед|борщевик|багульник"
    )
    HARMFUL_POISON_INTENT_PATTERN = (
        r"(?:сделать|приготовить|добыть|извлечь|отравить).{0,40}"
        + f"(?:{POISON_PATTERN})"
        + r"|"
        + f"(?:{POISON_PATTERN})"
        + r".{0,40}(?:сделать|приготовить|добыть|извлечь|отравить)"
    )
    CYBER_ABUSE_PATTERN = (
        r"(?:как|помоги|научи|хочу).{0,50}"
        r"(?:взлом|обойт\w*.{0,15}защит|украст\w*.{0,15}парол|"
        r"сломать\w*.{0,15}(?:сайт|сервер)|ддос)"
    )
    SECRET_REQUEST_PATTERN = (
        r"(?:скажи|покажи|назови|дай|сообщи|пришли).{0,40}"
        r"(?:парол|токен|api.{0,5}ключ|ip.{0,5}адрес)"
    )
    PERSONAL_CONTACT_REQUEST_PATTERN = (
        r"(?:скажи|покажи|назови|дай|напиши|пришли|узнай).{0,50}"
        r"(?:домашн\w*.{0,12}адрес|адрес.{0,20}(?:дом|квартир|лер|мам|пап)|"
        r"номер.{0,12}телефон|телефон.{0,20}(?:лер|мам|пап))"
    )
    PHONE_NUMBER_PATTERN = (
        r"(?:\+7|8)[\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}\b"
    )
    OUTPUT_SECRET_VALUE_PATTERN = (
        r"(?:парол|токен|api.{0,5}ключ)\s*(?::|=|—|–|равен|это)\s*\S+"
    )
    OUTPUT_DANGEROUS_DIRECTIVE_PATTERN = (
        r"(?:давай|попробуй|можешь|тебе нужно|надо|возьми|достань|"
        r"зажги|подожги|разведи|сунь|вставь|выпей|съешь|прими|"
        r"сделай|приготовь|порежь|убей).{0,80}"
        r"(?:спичк|огонь|кост[её]р|нож|розетк|лекарств|таблетк|"
        r"яд|ядовит|гриб|ягод)"
    )
    OUTPUT_CYBER_DIRECTIVE_PATTERN = (
        r"(?:давай|попробуй|можешь|тебе нужно|надо|сделай|запусти).{0,80}"
        r"(?:взлом|обойт\w*.{0,15}защит|украст\w*.{0,15}парол|ддос)"
    )
    SUPERVISED_OUTDOOR_KEYWORDS = [
        r"спичк",
        r"огонь",
        r"кост[её]р",
        r"нож",
        r"заточит",
        r"точил",
    ]
    DANGEROUS_KEYWORDS = [
        CYBER_ABUSE_PATTERN,
        SECRET_REQUEST_PATTERN,
        PERSONAL_CONTACT_REQUEST_PATTERN,
        PHONE_NUMBER_PATTERN,
        r"розетк",
        r"лекарств",
        r"таблетк",
        POISON_PATTERN,
        r"убей",
        r"смерт",
        r"кров",
    ]
    PARENT_MARKERS = (r"родител", r"взросл", r"мам", r"пап")
    SUPERVISION_REMINDER = (
        "Важно: в походе делай это только вместе с родителями.\n\n"
    )
    FIRE_GUIDANCE_PATTERN = r"(?:развест|разжечь|зажечь).{0,30}(?:кост[её]р|огонь)"
    SHARPENING_GUIDANCE_PATTERN = r"заточит|заточк|точить.{0,20}нож"
    MUSHROOM_GUIDANCE_PATTERN = (
        r"гриб.{0,50}(?:съедоб|можно.{0,15}есть)"
        r"|(?:съедоб|можно.{0,15}есть).{0,50}гриб"
    )
    BERRY_GUIDANCE_PATTERN = (
        r"ягод.{0,50}(?:съедоб|можно.{0,15}есть)"
        r"|(?:съедоб|можно.{0,15}есть).{0,50}ягод"
    )

    def check_text(
        self,
        text: str,
        permissions: tuple[str, ...] = (),
    ) -> SafetyResult:
        """Check text against safety rules."""
        text_lower = text.lower()
        outdoor_supervision_allowed = self.SUPERVISED_OUTDOOR_PERMISSION in permissions

        for pattern in self.SUPERVISED_OUTDOOR_KEYWORDS:
            if re.search(pattern, text_lower) and not outdoor_supervision_allowed:
                return self._unsafe_result(pattern)

        for pattern in self.DANGEROUS_KEYWORDS:
            if re.search(pattern, text_lower):
                if outdoor_supervision_allowed and pattern == self.POISON_PATTERN:
                    is_nature_hazard_guidance = re.search(
                        self.NATURE_HAZARD_CONTEXT_PATTERN,
                        text_lower,
                    ) and not re.search(self.HARMFUL_POISON_INTENT_PATTERN, text_lower)
                    if is_nature_hazard_guidance:
                        continue
                return self._unsafe_result(pattern)

        return SafetyResult(is_safe=True)

    def check_response(
        self,
        text: str,
        permissions: tuple[str, ...] = (),
    ) -> SafetyResult:
        """Block actionable unsafe output without rejecting educational facts."""

        text_lower = text.lower()
        always_blocked_patterns = (
            self.PHONE_NUMBER_PATTERN,
            self.OUTPUT_SECRET_VALUE_PATTERN,
            self.OUTPUT_CYBER_DIRECTIVE_PATTERN,
        )
        for pattern in always_blocked_patterns:
            if re.search(pattern, text_lower):
                return self._unsafe_result(pattern)

        if re.search(self.OUTPUT_DANGEROUS_DIRECTIVE_PATTERN, text_lower):
            supervised_outdoor_answer = (
                self.SUPERVISED_OUTDOOR_PERMISSION in permissions
                and any(re.search(pattern, text_lower) for pattern in self.PARENT_MARKERS)
            )
            if not supervised_outdoor_answer:
                return self._unsafe_result(self.OUTPUT_DANGEROUS_DIRECTIVE_PATTERN)

        return SafetyResult(is_safe=True)

    def apply_required_guardrails(
        self,
        text: str,
        permissions: tuple[str, ...],
    ) -> str:
        """Deterministically retain parental supervision for outdoor guidance."""

        if self.SUPERVISED_OUTDOOR_PERMISSION not in permissions:
            return text
        if any(re.search(pattern, text.lower()) for pattern in self.PARENT_MARKERS):
            return text
        return self.SUPERVISION_REMINDER + text

    def get_supervised_outdoor_guidance(
        self,
        text: str,
        permissions: tuple[str, ...],
    ) -> str | None:
        """Return audited guidance for high-risk outdoor questions."""

        if self.SUPERVISED_OUTDOOR_PERMISSION not in permissions:
            return None

        text_lower = text.lower()
        if re.search(self.FIRE_GUIDANCE_PATTERN, text_lower):
            return (
                "Костёр разводит только родитель. Сначала вместе проверьте, что огонь "
                "разрешён, и найдите оборудованное костровище. Если его нет или стоит запрет, "
                "костёр не разводят. Ты можешь помочь собрать сухие палочки с земли и отойти на "
                "безопасное расстояние. Спички и огонь держит взрослый. Он держит рядом воду, не "
                "оставляет огонь и перед уходом заливает и перемешивает угли, "
                "пока они не станут холодными."
            )
        if re.search(self.SHARPENING_GUIDANCE_PATTERN, text_lower):
            return (
                "Заточку ножа делает только родитель. Взрослый садится на устойчивом месте вдали "
                "от людей, берёт штатную точилку и следует её инструкции, "
                "ведя лезвие от себя. Потом он очищает и убирает нож в чехол. "
                "Тебе лучше наблюдать с расстояния: нож и точилку держит только взрослый. "
                "Если подходящей точилки нет, не надо заменять её случайным камнем: "
                "безопаснее "
                "убрать нож и заточить его дома."
            )
        if re.search(self.MUSHROOM_GUIDANCE_PATTERN, text_lower):
            return (
                "По виду, фотографии, цвету или запаху нельзя надёжно понять, "
                "можно ли есть дикий гриб. Не трогай и не пробуй его, а покажи родителям "
                "или опытному местному грибнику. Народные тесты тоже не работают. Для еды "
                "безопаснее взять грибы, которые родители купили в магазине."
            )
        if re.search(self.BERRY_GUIDANCE_PATTERN, text_lower):
            return (
                "Не пробуй дикую ягоду и не трогай после неё лицо. По цвету, фотографии, "
                "запаху или вкусу нельзя надёжно понять, можно ли её есть. Покажи ягоду родителям "
                "с расстояния. Для еды безопаснее взять ягоды, которые родители принесли "
                "из магазина или дома."
            )
        return None

    def normalize_outdoor_response(
        self,
        text: str,
        permissions: tuple[str, ...],
    ) -> str:
        """Remove presentation and knife details unsuitable for a six-year-old."""

        if self.SUPERVISED_OUTDOOR_PERMISSION not in permissions:
            return text

        normalized = re.sub(r"\*\*|__|^#{1,6}\s*", "", text, flags=re.MULTILINE)
        normalized = re.sub(
            r"\b\d{1,3}[\s‑–—−≈]*°",
            "под углом, указанным производителем точилки",
            normalized,
        )
        return normalized

    @staticmethod
    def _unsafe_result(pattern: str) -> SafetyResult:
        return SafetyResult(
            is_safe=False,
            reason=f"Matched dangerous pattern: {pattern}",
            suggested_response=(
                "Это очень важный вопрос, но он может быть опасным. "
                "Давай лучше спросим об этом у мамы или папы? Они точно помогут!"
            ),
        )
