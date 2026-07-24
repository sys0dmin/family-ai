"""Deterministic policy evaluation for input, output, tools and permissions."""

from __future__ import annotations

import re

from gateway.app.safety.catalog import RULES_BY_ID
from gateway.app.safety.contracts import (
    PolicyAction,
    PolicyDecision,
    PolicyOutcome,
)
from gateway.app.safety.metrics import SafetyMetricsRegistry

SUPERVISED_OUTDOOR_PERMISSION = "supervised_outdoor_safety"
SAFE_INPUT_FALLBACK = (
    "Это очень важный вопрос, но он может быть опасным. "
    "Давай лучше спросим об этом у мамы или папы? Они точно помогут!"
)
SAFE_OUTPUT_FALLBACK = (
    "Ой, я задумался о чём-то не том. "
    "Давай лучше поиграем или спросим у мамы?"
)
SUPERVISION_REMINDER = "Важно: в походе делай это только вместе с родителями.\n\n"

POISON_PATTERN = r"\bяд(?:а|у|ом|ы|ов)?\b|ядовит"
POISON_CREATION_PATTERN = (
    r"(?:сделать|приготовить|добыть|извлечь|подмешать|отравить).{0,50}"
    f"(?:{POISON_PATTERN})"
    r"|"
    f"(?:{POISON_PATTERN})"
    r".{0,50}(?:сделать|приготовить|добыть|извлечь|подмешать|отравить)"
)
CYBER_ABUSE_PATTERN = (
    r"(?:как|помоги|научи|хочу).{0,60}"
    r"(?:взлом|обойт\w*.{0,15}защит|украст\w*.{0,15}парол|"
    r"сломать\w*.{0,15}(?:сайт|сервер)|ддос)"
)
SECRET_REQUEST_PATTERN = (
    r"(?:скажи|покажи|назови|дай|сообщи|пришли).{0,50}"
    r"(?:парол|токен|api.{0,5}ключ|ip.{0,5}адрес)"
)
PERSONAL_CONTACT_REQUEST_PATTERN = (
    r"(?:скажи|покажи|назови|дай|напиши|пришли|узнай).{0,60}"
    r"(?:домашн\w*.{0,12}адрес|адрес.{0,20}(?:дом|квартир|лер|мам|пап)|"
    r"номер.{0,12}телефон|телефон.{0,20}(?:лер|мам|пап))"
)
PHONE_NUMBER_PATTERN = (
    r"(?:\+7|8)[\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}\b"
)
HAZARDOUS_INSTRUCTION_PATTERN = (
    r"(?:как|помоги|научи|хочу|можно ли).{0,60}"
    r"(?:сунуть|вставить).{0,20}розетк"
    r"|(?:как|сколько|можно ли).{0,60}"
    r"(?:(?:выпить|съесть|принять).{0,25}(?:лекарств|таблет)"
    r"|(?:лекарств|таблет).{0,25}(?:выпить|съесть|принять))"
    r"|(?:как|помоги|научи|хочу).{0,50}(?:убить|ранить|порезать)"
)
OUTDOOR_PERMISSION_REQUIRED_PATTERN = (
    r"спичк|(?:развест|разжечь|зажечь).{0,30}(?:кост[её]р|огонь)|"
    r"заточит|заточк|точить.{0,20}нож|"
    r"гриб.{0,50}(?:съедоб|можно.{0,15}есть)|"
    r"(?:съедоб|можно.{0,15}есть).{0,50}гриб|"
    r"ягод.{0,50}(?:съедоб|можно.{0,15}есть)|"
    r"(?:съедоб|можно.{0,15}есть).{0,50}ягод"
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
PARENT_MARKERS = r"родител|взросл|мам|пап"
OUTPUT_SECRET_VALUE_PATTERN = (
    r"(?:парол\w*|токен\w*|api.{0,5}ключ\w*)"
    r"\s*(?::|=|—|–|равен|это)\s*\S+"
)
OUTPUT_CYBER_DIRECTIVE_PATTERN = (
    r"(?:давай|попробуй|можешь|тебе нужно|надо|сделай|запусти).{0,80}"
    r"(?:взлом|обойт\w*.{0,15}защит|украст\w*.{0,15}парол|ддос)"
)
OUTPUT_DANGEROUS_DIRECTIVE_PATTERN = (
    r"(?:давай|попробуй|можешь|тебе нужно|надо|возьми|достань|"
    r"зажги|подожги|разведи|сунь|вставь|выпей|съешь|прими|"
    r"сделай|приготовь|порежь|убей).{0,80}"
    r"(?:спичк|огонь|кост[её]р|нож|розетк|лекарств|таблетк|"
    r"яд|ядовит|гриб|ягод)"
)


class SafetyPolicyEngine:
    """Apply formal, content-ephemeral policy decisions."""

    def __init__(self, metrics: SafetyMetricsRegistry | None = None) -> None:
        self._metrics = metrics

    def evaluate_input(
        self,
        text: str,
        *,
        permissions: tuple[str, ...] = (),
    ) -> PolicyOutcome:
        lowered = text.lower()
        blockers = (
            (
                PERSONAL_CONTACT_REQUEST_PATTERN,
                "input.privacy.personal_contact.block",
                "Запрошены персональные контактные данные.",
            ),
            (
                PHONE_NUMBER_PATTERN,
                "input.privacy.personal_contact.block",
                "Обнаружен номер телефона.",
            ),
            (
                SECRET_REQUEST_PATTERN,
                "input.privacy.secret_request.block",
                "Запрошен инфраструктурный секрет.",
            ),
            (
                CYBER_ABUSE_PATTERN,
                "input.cyber.abuse.block",
                "Запрошено практическое компьютерное злоупотребление.",
            ),
            (
                POISON_CREATION_PATTERN,
                "input.physical.poison_creation.block",
                "Запрошено создание или применение яда.",
            ),
            (
                HAZARDOUS_INSTRUCTION_PATTERN,
                "input.physical.hazardous_instruction.block",
                "Запрошено опасное действие.",
            ),
        )
        for pattern, rule_id, reason in blockers:
            if re.search(pattern, lowered):
                return self._outcome(
                    PolicyAction.BLOCK,
                    text,
                    (self._decision(rule_id, reason),),
                    SAFE_INPUT_FALLBACK,
                )

        if re.search(OUTDOOR_PERMISSION_REQUIRED_PATTERN, lowered):
            permission = self.evaluate_permission(
                SUPERVISED_OUTDOOR_PERMISSION,
                permissions,
                record=False,
            )
            if permission.action is PolicyAction.BLOCK:
                return self._record(
                    PolicyOutcome(
                        action=PolicyAction.BLOCK,
                        text=text,
                        decisions=permission.decisions,
                        safe_response=SAFE_INPUT_FALLBACK,
                    )
                )
            guidance = self._outdoor_guidance(lowered)
            if guidance is not None:
                rule_id, response = guidance
                return self._outcome(
                    PolicyAction.TRANSFORM,
                    response,
                    (
                        self._decision(
                            rule_id,
                            "Использована проверенная памятка вместо генерации.",
                        ),
                    ),
                )

        return self._outcome(
            PolicyAction.ALLOW,
            text,
            (
                self._decision(
                    "input.default.allow",
                    "Опасный контекст не обнаружен.",
                ),
            ),
        )

    def evaluate_output(
        self,
        text: str,
        *,
        permissions: tuple[str, ...] = (),
    ) -> PolicyOutcome:
        transformed = text
        decisions: list[PolicyDecision] = []
        if SUPERVISED_OUTDOOR_PERMISSION in permissions:
            normalized = re.sub(
                r"\*\*|__|^#{1,6}\s*",
                "",
                transformed,
                flags=re.MULTILINE,
            )
            normalized = re.sub(
                r"\b\d{1,3}[\s‑–—−≈]*°",
                "под углом, указанным производителем точилки",
                normalized,
            )
            if normalized != transformed:
                transformed = normalized
                decisions.append(
                    self._decision(
                        "output.outdoor.presentation.transform",
                        "Убраны неподходящие детали представления.",
                    )
                )
            if not re.search(PARENT_MARKERS, transformed.lower()):
                transformed = SUPERVISION_REMINDER + transformed
                decisions.append(
                    self._decision(
                        "output.outdoor.supervision.transform",
                        "Добавлено обязательное участие родителей.",
                    )
                )

        lowered = transformed.lower()
        blockers = (
            (
                PHONE_NUMBER_PATTERN,
                "output.privacy.phone.block",
                "Ответ содержит номер телефона.",
            ),
            (
                OUTPUT_SECRET_VALUE_PATTERN,
                "output.privacy.secret.block",
                "Ответ раскрывает инфраструктурный секрет.",
            ),
            (
                OUTPUT_CYBER_DIRECTIVE_PATTERN,
                "output.cyber.directive.block",
                "Ответ содержит инструкцию по компьютерному злоупотреблению.",
            ),
        )
        for pattern, rule_id, reason in blockers:
            if re.search(pattern, lowered):
                decisions.append(self._decision(rule_id, reason))
                return self._outcome(
                    PolicyAction.BLOCK,
                    transformed,
                    tuple(decisions),
                    SAFE_OUTPUT_FALLBACK,
                )

        if re.search(OUTPUT_DANGEROUS_DIRECTIVE_PATTERN, lowered):
            supervised = (
                SUPERVISED_OUTDOOR_PERMISSION in permissions
                and re.search(PARENT_MARKERS, lowered)
            )
            if not supervised:
                decisions.append(
                    self._decision(
                        "output.physical.directive.block",
                        "Ответ адресует ребёнку опасное действие.",
                    )
                )
                return self._outcome(
                    PolicyAction.BLOCK,
                    transformed,
                    tuple(decisions),
                    SAFE_OUTPUT_FALLBACK,
                )

        if decisions:
            return self._outcome(
                PolicyAction.TRANSFORM,
                transformed,
                tuple(decisions),
            )
        return self._outcome(
            PolicyAction.ALLOW,
            transformed,
            (
                self._decision(
                    "output.default.allow",
                    "Опасная инструкция не обнаружена.",
                ),
            ),
        )

    def evaluate_tool(
        self,
        tool_name: str,
        granted_tools: tuple[str, ...],
    ) -> PolicyOutcome:
        granted = tool_name in granted_tools
        rule_id = f"tool.{tool_name}.{'allow' if granted else 'block'}"
        if rule_id not in RULES_BY_ID:
            rule_id = "tool.unknown.block"
            granted = False
        return self._outcome(
            PolicyAction.ALLOW if granted else PolicyAction.BLOCK,
            "",
            (
                self._decision(
                    rule_id,
                    "Инструмент разрешён агенту."
                    if granted
                    else "Инструмент отсутствует в разрешениях агента.",
                ),
            ),
        )

    def evaluate_permission(
        self,
        permission_name: str,
        granted_permissions: tuple[str, ...],
        *,
        record: bool = True,
    ) -> PolicyOutcome:
        granted = permission_name in granted_permissions
        rule_id = (
            "permission.outdoor_guidance.allow"
            if granted
            else "permission.outdoor_guidance.required"
        )
        outcome = PolicyOutcome(
            action=PolicyAction.ALLOW if granted else PolicyAction.BLOCK,
            text="",
            decisions=(
                self._decision(
                    rule_id,
                    "Разрешение присутствует."
                    if granted
                    else "Агенту не выдано обязательное разрешение.",
                ),
            ),
        )
        return self._record(outcome) if record else outcome

    def _outcome(
        self,
        action: PolicyAction,
        text: str,
        decisions: tuple[PolicyDecision, ...],
        safe_response: str | None = None,
    ) -> PolicyOutcome:
        return self._record(
            PolicyOutcome(
                action=action,
                text=text,
                decisions=decisions,
                safe_response=safe_response,
            )
        )

    def _record(self, outcome: PolicyOutcome) -> PolicyOutcome:
        if self._metrics is not None:
            self._metrics.record(outcome)
        return outcome

    @staticmethod
    def _decision(rule_id: str, reason: str) -> PolicyDecision:
        descriptor = RULES_BY_ID[rule_id]
        return PolicyDecision(
            rule_id=descriptor.rule_id,
            phase=descriptor.phase,
            category=descriptor.category,
            action=descriptor.action,
            reason=reason,
        )

    @staticmethod
    def _outdoor_guidance(text: str) -> tuple[str, str] | None:
        if re.search(FIRE_GUIDANCE_PATTERN, text):
            return (
                "input.outdoor.fire.safe_guidance",
                "Костёр разводит только родитель. Сначала вместе проверьте, что "
                "огонь разрешён, и найдите оборудованное костровище. Если его нет "
                "или стоит запрет, костёр не разводят. Ты можешь помочь собрать "
                "сухие палочки с земли и отойти на безопасное расстояние. Спички "
                "и огонь держит взрослый. Он держит рядом воду, не оставляет огонь "
                "и перед уходом заливает и перемешивает угли, пока они не станут "
                "холодными.",
            )
        if re.search(SHARPENING_GUIDANCE_PATTERN, text):
            return (
                "input.outdoor.sharpening.safe_guidance",
                "Заточку ножа делает только родитель. Взрослый садится на "
                "устойчивом месте вдали от людей, берёт штатную точилку и следует "
                "её инструкции, ведя лезвие от себя. Потом он очищает и убирает нож "
                "в чехол. Тебе лучше наблюдать с расстояния: нож и точилку держит "
                "только взрослый. Если подходящей точилки нет, безопаснее убрать "
                "нож и заточить его дома.",
            )
        if re.search(MUSHROOM_GUIDANCE_PATTERN, text):
            return (
                "input.outdoor.mushroom.safe_guidance",
                "По виду, фотографии, цвету или запаху нельзя надёжно понять, "
                "можно ли есть дикий гриб. Не трогай и не пробуй его, а покажи "
                "родителям или опытному местному грибнику. Народные тесты тоже не "
                "работают. Для еды безопаснее взять грибы, которые родители купили "
                "в магазине.",
            )
        if re.search(BERRY_GUIDANCE_PATTERN, text):
            return (
                "input.outdoor.berry.safe_guidance",
                "Не пробуй дикую ягоду и не трогай после неё лицо. По цвету, "
                "фотографии, запаху или вкусу нельзя надёжно понять, можно ли её "
                "есть. Покажи ягоду родителям с расстояния. Для еды безопаснее "
                "взять ягоды, которые родители принесли из магазина или дома.",
            )
        return None
