"""OCR engine abstraction.

Two open-source engines are supported, selected via `OCR_PROVIDER`:

- `tesseract` (default): lightweight, works out of the box via pytesseract,
  no GPU, no heavy model download — good default for local dev.
- `paddleocr`: generally higher accuracy on real-world scanned invoices,
  installed via the optional `ocr-paddle` extra (`pip install -e ".[ocr-paddle]"`).

Both return the same `OCRResult` shape so callers (the invoice pipeline,
document ingestion) never branch on which engine produced it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

from app.config import get_settings
from app.core.errors import DependencyUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class OCRWord:
    text: str
    confidence: float  # 0.0 - 1.0
    bbox: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1


@dataclass
class OCRResult:
    text: str
    confidence: float  # average word confidence, 0.0 - 1.0
    words: list[OCRWord]
    engine: str


class OCREngine(ABC):
    @abstractmethod
    def extract(self, image_bytes: bytes) -> OCRResult: ...


class TesseractOCREngine(OCREngine):
    def __init__(self, language: str = "en", tesseract_cmd: str | None = None) -> None:
        import pytesseract

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        self._pytesseract = pytesseract
        self._lang = "eng" if language == "en" else language

    def extract(self, image_bytes: bytes) -> OCRResult:
        import io

        from PIL import Image

        try:
            image = Image.open(io.BytesIO(image_bytes))
        except Exception as exc:
            raise DependencyUnavailableError(f"Could not decode image for OCR: {exc}") from exc

        try:
            data = self._pytesseract.image_to_data(
                image, lang=self._lang, output_type=self._pytesseract.Output.DICT
            )
        except self._pytesseract.TesseractNotFoundError as exc:
            raise DependencyUnavailableError(
                "Tesseract binary not found. Install Tesseract OCR and/or set TESSERACT_CMD."
            ) from exc

        words: list[OCRWord] = []
        for i, text in enumerate(data["text"]):
            text = text.strip()
            if not text:
                continue
            conf_raw = data["conf"][i]
            try:
                conf = max(float(conf_raw), 0.0) / 100.0
            except (TypeError, ValueError):
                conf = 0.0
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            words.append(OCRWord(text=text, confidence=conf, bbox=(x, y, x + w, y + h)))

        full_text = " ".join(w.text for w in words)
        avg_conf = sum(w.confidence for w in words) / len(words) if words else 0.0
        return OCRResult(text=full_text, confidence=avg_conf, words=words, engine="tesseract")


class PaddleOCREngine(OCREngine):
    def __init__(self, language: str = "en") -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise DependencyUnavailableError(
                "PaddleOCR is not installed. Install with: "
                'pip install -e ".[ocr-paddle]" (or switch OCR_PROVIDER=tesseract).'
            ) from exc

        self._ocr = PaddleOCR(use_angle_cls=True, lang=language)

    def extract(self, image_bytes: bytes) -> OCRResult:
        import io

        import numpy as np
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        result = self._ocr.ocr(np.array(image), cls=True)

        words: list[OCRWord] = []
        for line in result or []:
            for box, (text, conf) in line:
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                words.append(
                    OCRWord(
                        text=text,
                        confidence=float(conf),
                        bbox=(min(xs), min(ys), max(xs), max(ys)),
                    )
                )

        full_text = " ".join(w.text for w in words)
        avg_conf = sum(w.confidence for w in words) / len(words) if words else 0.0
        return OCRResult(text=full_text, confidence=avg_conf, words=words, engine="paddleocr")


@lru_cache
def get_ocr_engine() -> OCREngine:
    settings = get_settings()
    if settings.ocr_provider == "paddleocr":
        return PaddleOCREngine(language=settings.ocr_language)
    return TesseractOCREngine(language=settings.ocr_language, tesseract_cmd=settings.tesseract_cmd)
