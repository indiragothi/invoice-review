from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

ContentType = Literal["application/pdf", "image/png", "image/jpeg"]
TextSource = Literal["pdf_text", "ocr"]
Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in page-image pixels


@dataclass(frozen=True)
class RawWord:
    """A word before numbering. Words with equal `line_key` on one page share a line."""

    text: str
    box: Box
    confidence: float
    line_key: object


class Word(BaseModel):
    """One positioned piece of text. The LLM cites these by `id` as evidence."""

    id: str
    page: int  # 1-based
    line: int  # document-wide line number, 1-based
    text: str
    box: Box
    confidence: float


class Page(BaseModel):
    number: int  # 1-based
    width: int
    height: int
    text_source: TextSource


class ReadDocument(BaseModel):
    content_type: ContentType
    pages: list[Page]
    words: list[Word]

    def page_text(self, number: int) -> str:
        lines: dict[int, list[str]] = {}
        for word in self.words:
            if word.page == number:
                lines.setdefault(word.line, []).append(word.text)
        return "\n".join(" ".join(texts) for _, texts in sorted(lines.items()))
