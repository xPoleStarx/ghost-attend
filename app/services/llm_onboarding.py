from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.config import Settings
from app.domain.schemas import ScheduleCandidate


FIELD_NAMES = ["university_url", "email", "password", "timezone", "schedule"]


class OnboardingAnalysis(BaseModel):
    university_url: str | None = None
    email: str | None = None
    password: str | None = None
    timezone: str | None = None
    schedule_text: str | None = None
    confirmation: bool = False
    schedule_action: str | None = None
    courses_to_remove: list[str] = Field(default_factory=list)
    assistant_message: str | None = None


class OnboardingPromptPayload(BaseModel):
    message: str
    missing_fields: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class LLMOnboardingAssistant:
    settings: Settings

    async def analyze_message(
        self,
        *,
        message: str,
        current_state: dict[str, Any],
        has_schedule_candidate: bool,
    ) -> OnboardingAnalysis:
        heuristic = self._heuristic_analysis(
            message=message,
            current_state=current_state,
            has_schedule_candidate=has_schedule_candidate,
        )
        llm_result = await self._llm_analysis(
            message=message,
            current_state=current_state,
            has_schedule_candidate=has_schedule_candidate,
        )
        if llm_result is None:
            return heuristic
        return self._merge_analysis(heuristic, llm_result)

    async def compose_opening_prompt(self) -> OnboardingPromptPayload:
        llm_prompt = await self._llm_opening_prompt()
        if llm_prompt is not None:
            return llm_prompt
        return OnboardingPromptPayload(
            message=(
                "Merhaba, ben Ghost Attend. En bastan birlikte kurabiliriz. Bana tek mesajda ya da parca parca "
                "DYS adresini, okul e-postani, sifreni, saat dilimini ve ders programini yazabilirsin. "
                "Istersen DYS adresinle baslayalim."
            ),
            missing_fields=FIELD_NAMES,
        )

    async def compose_followup_prompt(
        self,
        *,
        current_state: dict[str, Any],
        has_schedule_candidate: bool,
        schedule_candidate: ScheduleCandidate | None,
    ) -> OnboardingPromptPayload:
        return self._fallback_followup_prompt(
            current_state=current_state,
            has_schedule_candidate=has_schedule_candidate,
            schedule_candidate=schedule_candidate,
        )

    def _merge_analysis(
        self,
        heuristic: OnboardingAnalysis,
        llm_result: OnboardingAnalysis,
    ) -> OnboardingAnalysis:
        merged = heuristic.model_copy()
        for field_name in (
            "university_url",
            "email",
            "password",
            "timezone",
            "schedule_text",
            "schedule_action",
        ):
            llm_value = getattr(llm_result, field_name)
            heuristic_value = getattr(heuristic, field_name)
            setattr(merged, field_name, llm_value or heuristic_value)
        merged.confirmation = heuristic.confirmation or llm_result.confirmation
        merged.courses_to_remove = llm_result.courses_to_remove or heuristic.courses_to_remove
        merged.assistant_message = llm_result.assistant_message or heuristic.assistant_message
        return merged

    def _heuristic_analysis(
        self,
        *,
        message: str,
        current_state: dict[str, Any],
        has_schedule_candidate: bool,
    ) -> OnboardingAnalysis:
        cleaned = message.strip()
        lower = cleaned.lower()
        normalized_lower = self._normalize_text(cleaned)
        url_match = re.search(
            r"(https?://[^\s,]+|(?:dys\.)?[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s,]*)?)",
            cleaned,
            re.I,
        )
        email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", cleaned)
        timezone = self._normalize_timezone(cleaned)
        schedule_text = cleaned if self._looks_like_schedule(cleaned) else None
        confirmation = normalized_lower in {"yes", "evet", "tamam", "ok"}
        schedule_action = "confirm" if confirmation else None
        courses_to_remove = self._extract_courses_to_remove(cleaned)
        if courses_to_remove:
            schedule_action = "edit"
        password = self._extract_password(cleaned, current_state)
        university_url = self._normalize_university_url(url_match.group(1)) if url_match else None
        email = email_match.group(0) if email_match else None

        if has_schedule_candidate and confirmation:
            schedule_text = None

        return OnboardingAnalysis(
            university_url=university_url,
            email=email,
            password=password,
            timezone=timezone,
            schedule_text=schedule_text,
            confirmation=confirmation,
            schedule_action=schedule_action,
            courses_to_remove=courses_to_remove,
        )

    async def _llm_opening_prompt(self) -> OnboardingPromptPayload | None:
        prompt = (
            "You are the onboarding voice of a Telegram bot for Turkish students. "
            "Return only JSON with keys message and missing_fields. "
            "Write a short, warm Turkish message that explains the user can send DYS URL, school email, "
            "password, timezone and schedule in one message or step by step. missing_fields should include "
            "all of: university_url, email, password, timezone, schedule."
        )
        response = await self._call_provider(prompt)
        if response is None:
            return None
        try:
            data = json.loads(response)
            return OnboardingPromptPayload.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            return None

    async def _llm_analysis(
        self,
        *,
        message: str,
        current_state: dict[str, Any],
        has_schedule_candidate: bool,
    ) -> OnboardingAnalysis | None:
        prompt = (
            "You extract onboarding intent and fields for a Telegram bot. Return only JSON with keys "
            "university_url, email, password, timezone, schedule_text, confirmation, schedule_action, "
            "courses_to_remove, assistant_message. "
            "assistant_message should be a short Turkish response that feels natural. "
            "Never invent data; use null when unknown. "
            "schedule_action must be one of confirm, edit, provide_info, unclear. "
            "If the user semantically approves the already parsed schedule with phrases like aynen, olur, "
            "uygun, tamamdir, dogru, onayliyorum, set confirmation=true and schedule_action=confirm. "
            "If the user wants to remove or exclude some courses, set schedule_action=edit and fill "
            "courses_to_remove with the course names as the user referred to them. "
            "Current state:\n"
            f"{json.dumps(current_state, ensure_ascii=False)}\n"
            f"has_schedule_candidate={has_schedule_candidate}\n"
            f"user_message={json.dumps(message, ensure_ascii=False)}"
        )
        response = await self._call_provider(prompt)
        if response is None:
            return None
        try:
            data = json.loads(response)
            return OnboardingAnalysis.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            return None

    async def _call_provider(self, prompt: str) -> str | None:
        provider = self.settings.llm_provider.lower()
        if provider == "gemini" and self.settings.google_api_key is not None:
            return await asyncio.to_thread(self._call_gemini, prompt)
        if provider == "openai" and self.settings.openai_api_key is not None:
            return await asyncio.to_thread(self._call_openai, prompt)
        if provider == "anthropic" and self.settings.anthropic_api_key is not None:
            return await asyncio.to_thread(self._call_anthropic, prompt)
        return None

    def _call_gemini(self, prompt: str) -> str | None:
        try:
            from google import genai
        except ImportError:
            return None
        client = genai.Client(api_key=self.settings.google_api_key.get_secret_value())
        response = client.models.generate_content(
            model=self.settings.llm_model,
            contents=prompt,
        )
        return getattr(response, "text", None)

    def _call_openai(self, prompt: str) -> str | None:
        try:
            from openai import OpenAI
        except ImportError:
            return None
        client = OpenAI(api_key=self.settings.openai_api_key.get_secret_value())
        response = client.chat.completions.create(
            model=self.settings.llm_model,
            messages=[
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content
        if isinstance(content, str):
            return content
        return None

    def _call_anthropic(self, prompt: str) -> str | None:
        try:
            import anthropic
        except ImportError:
            return None
        client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key.get_secret_value())
        response = client.messages.create(
            model=self.settings.llm_model,
            max_tokens=400,
            system="Return only valid JSON.",
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                return text
        return None

    def _fallback_followup_prompt(
        self,
        *,
        current_state: dict[str, Any],
        has_schedule_candidate: bool,
        schedule_candidate: ScheduleCandidate | None,
    ) -> OnboardingPromptPayload:
        missing = self._missing_fields(current_state, has_schedule_candidate)
        if has_schedule_candidate and schedule_candidate is not None:
            warnings = ""
            if schedule_candidate.warnings:
                warnings = " Ayrica bazi satirlari netlestiremedim; istersen duzelterek yeniden yazabilirsin."
            return OnboardingPromptPayload(
                message=(
                    "Programini buyuk olcude cikardim. Uygunsa onaylayabilirsin; degilse dogal cumleyle ya da "
                    f"satir satir duzeltebilirsin.{warnings}"
                ),
                missing_fields=[],
            )
        field_text = {
            "university_url": "DYS adresin",
            "email": "okul e-posta adresin",
            "password": "DYS sifren",
            "timezone": "saat dilimin",
            "schedule": "ders programin",
        }
        if not missing:
            return OnboardingPromptPayload(message="Devam edebiliriz.", missing_fields=[])
        wanted = ", ".join(field_text[item] for item in missing)
        return OnboardingPromptPayload(
            message=f"Iyi gidiyoruz. Simdi sadece su eksikleri tamamlayalim: {wanted}.",
            missing_fields=missing,
        )

    def _missing_fields(self, current_state: dict[str, Any], has_schedule_candidate: bool) -> list[str]:
        missing: list[str] = []
        for field_name in ("university_url", "email", "password", "timezone"):
            if not current_state.get(field_name):
                missing.append(field_name)
        if not has_schedule_candidate:
            missing.append("schedule")
        return missing

    def _normalize_timezone(self, text: str) -> str | None:
        lowered = text.strip().lower()
        aliases = {
            "istanbul": "Europe/Istanbul",
            "turkiye": "Europe/Istanbul",
            "turkiyedeyim": "Europe/Istanbul",
            "turkiye saati": "Europe/Istanbul",
            "turkiye saatine gore": "Europe/Istanbul",
            "turkey": "Europe/Istanbul",
            "mugla": "Europe/Istanbul",
            "muğla": "Europe/Istanbul",
            "gmt+3": "Europe/Istanbul",
            "utc+3": "Europe/Istanbul",
        }
        for alias, normalized in aliases.items():
            if alias in lowered:
                return normalized
        timezone_token = re.search(r"\b[A-Za-z_]+/[A-Za-z_]+\b", text)
        if timezone_token:
            return timezone_token.group(0)
        timezone_match = re.search(r"\b(?:UTC|GMT)\s*([+-]\d{1,2})\b", text, re.I)
        if timezone_match and timezone_match.group(1) == "+3":
            return "Europe/Istanbul"
        return None

    def _looks_like_schedule(self, text: str) -> bool:
        lowered = text.lower()
        day_tokens = [
            "pazartesi",
            "sali",
            "salı",
            "carsamba",
            "çarşamba",
            "persembe",
            "perşembe",
            "cuma",
            "cumartesi",
            "pazar",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        has_day = any(token in lowered for token in day_tokens)
        has_time = re.search(r"\b\d{1,2}[:.]\d{2}\b", text) is not None
        return "|" in text or (has_day and has_time)

    def _extract_password(self, text: str, current_state: dict[str, Any]) -> str | None:
        if current_state.get("password"):
            return None
        labeled_match = re.search(r"(?:sifre|şifre|password)\s*[:=]?\s*(\S+)", text, re.I)
        if labeled_match:
            return labeled_match.group(1).strip().rstrip(",")
        if (
            " " not in text.strip()
            and "@" not in text
            and "/" not in text
            and not self._looks_like_schedule(text)
            and self._normalize_timezone(text) is None
            and len(text.strip()) >= 4
        ):
            return text.strip().rstrip(",")
        return None

    def _normalize_university_url(self, value: str) -> str:
        normalized = value.strip().rstrip(",")
        if not normalized.startswith(("http://", "https://")):
            normalized = f"https://{normalized}"
        return normalized

    def _normalize_text(self, value: str) -> str:
        ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()

    def _extract_courses_to_remove(self, text: str) -> list[str]:
        normalized = self._normalize_text(text)
        if not any(keyword in normalized for keyword in ("kaldir", "sil", "cikar", "remove", "delete")):
            return []
        cleaned = text.replace("bunlar online değil", "").replace("bunlar online degil", "")
        parts = re.split(r"\b(?:ve|,)\b", cleaned, flags=re.I)
        candidates: list[str] = []
        for part in parts:
            segment = part.strip(" ,.")
            if not segment:
                continue
            if re.search(r"\b(kaldir|sil|cikar|remove|delete|online)\b", self._normalize_text(segment)):
                segment = re.split(r"\b(?:kaldir|sil|cikar|remove|delete)\b", segment, flags=re.I)[0].strip(" ,.")
            if segment:
                candidates.append(segment)
        return candidates
