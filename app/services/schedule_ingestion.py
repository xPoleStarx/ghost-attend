from __future__ import annotations

import asyncio
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.config import Settings
from app.domain.schemas import ScheduleCandidate
from app.services.schedule_parser import ScheduleParser


class ScheduleImageExtractor(Protocol):
    async def extract(self, image_path: Path) -> str: ...


class StubScheduleImageExtractor:
    async def extract(self, image_path: Path) -> str:
        _ = image_path
        return ""


@dataclass(slots=True)
class LLMScheduleImageExtractor:
    settings: Settings

    async def extract(self, image_path: Path) -> str:
        provider = self.settings.llm_provider.lower()
        if provider == "gemini" and self.settings.google_api_key is not None:
            return await asyncio.to_thread(self._extract_with_gemini, image_path)
        return ""

    def _extract_with_gemini(self, image_path: Path) -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return ""

        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        image_bytes = image_path.read_bytes()
        client = genai.Client(api_key=self.settings.google_api_key.get_secret_value())
        prompt = (
            "You are extracting a Turkish university class schedule from an image. "
            "Return plain text only. "
            "Output one class per line using exactly this format:\n"
            "Course Name | english_weekday | HH:MM | HH:MM | optional teams link\n"
            "Rules:\n"
            "- Keep only real class rows.\n"
            "- Prefer online / virtual / Teams classes when the schedule distinguishes modality.\n"
            "- If modality is unclear, include the row anyway.\n"
            "- Normalize weekday to one of monday, tuesday, wednesday, thursday, friday, saturday, sunday.\n"
            "- Normalize times to 24-hour HH:MM.\n"
            "- If no Teams link is visible, omit the fifth column.\n"
            "- Do not add explanations, JSON, markdown, bullets, or comments."
        )
        try:
            response = client.models.generate_content(
                model=self.settings.llm_model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
            )
        except Exception:
            return ""
        text = getattr(response, "text", None)
        if not isinstance(text, str):
            return ""
        return text.strip()


@dataclass(slots=True)
class ScheduleIngestionService:
    parser: ScheduleParser
    image_extractor: ScheduleImageExtractor

    def parse_text(self, raw_text: str) -> ScheduleCandidate:
        return self.parser.parse_text(raw_text)

    async def parse_image(self, image_path: Path) -> ScheduleCandidate:
        extracted_text = await self.image_extractor.extract(image_path)
        candidate = self.parser.parse_text(extracted_text)
        if not candidate.courses:
            candidate.warnings.append(
                "Image schedule extraction could not produce a confirmed course list. Manual correction is required."
            )
        return candidate
