"""AI tools. They depend only on the AIProvider port, so any provider (Claude, OpenAI-compatible, local) works."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.errors import ServiceUnavailable, ValidationFailed
from app.domain.ports import AIProvider
from app.tools.base import Category, Tool, ToolContext, ToolOptions, stem
from app.tools.convert_from import pdf_to_markdown
from app.tools.registry import register

MAX_CHARS = 150_000


def _provider(ctx: ToolContext) -> AIProvider:
    if ctx.ai is None or not ctx.ai.available:
        raise ServiceUnavailable("AI features are not configured yet. Add an AI provider key to enable them.")
    return ctx.ai


def _document_text(path: Path) -> str:
    text = pdf_to_markdown(path).strip()
    if not text:
        raise ValidationFailed(f"No text found in '{path.name}'. Run OCR first if it's a scan.")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n[Document truncated]"
    return text


class _AITool(Tool):
    category = Category.INTELLIGENCE
    premium = True
    produces_pdf = False
    max_files = 1


@register
class SummarizeTool(_AITool):
    id = "ai_summarize"
    name = "AI Summarizer"
    description = "Get the key points of a long document in seconds."

    class Options(ToolOptions):
        length: Literal["short", "medium", "detailed"] = "medium"
        language: str = Field("English", max_length=40, description="Language of the summary")

    LENGTHS = {"short": "3 to 5 bullet points", "medium": "a one-paragraph overview then 5 to 10 bullet points",
               "detailed": "a section-by-section summary with headings"}  # fmt: skip

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        ai = _provider(ctx)
        answer = ai.complete(
            system="You summarize documents accurately. Never invent facts that are not in the document.",
            prompt=(
                f"Summarize the document below as {self.LENGTHS[options.length]}, in {options.language}. "
                f"Use Markdown.\n\n<document>\n{_document_text(inputs[0])}\n</document>"
            ),
            max_tokens=2048,
        )
        out = ctx.output_path(f"{stem(inputs[0])}-summary.md")
        out.write_text(answer, encoding="utf-8")
        return [out]


@register
class TranslateTool(_AITool):
    id = "ai_translate"
    name = "Translate PDF"
    description = "Translate a document's text into another language, keeping its headings."

    class Options(ToolOptions):
        target_language: str = Field(..., min_length=2, max_length=40)

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        ai = _provider(ctx)
        text = _document_text(inputs[0])
        chunks = [text[i : i + 12_000] for i in range(0, len(text), 12_000)]
        translated = [
            ai.complete(
                system="You are a professional translator. Output only the translation, keeping Markdown structure.",
                prompt=f"Translate into {options.target_language}:\n\n{chunk}",
                max_tokens=8192,
            )
            for chunk in chunks
        ]
        out = ctx.output_path(f"{stem(inputs[0])}-{options.target_language.lower()}.md")
        out.write_text("\n\n".join(translated), encoding="utf-8")
        return [out]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=8000)


@register
class AskPdfTool(_AITool):
    id = "ai_chat"
    name = "Chat with PDF"
    description = "Ask questions and get answers that cite the page they came from."

    class Options(ToolOptions):
        question: str = Field(..., min_length=1, max_length=4000)
        history: list[ChatTurn] = Field(default_factory=list, max_length=20)

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        ai = _provider(ctx)
        transcript = "\n".join(f"{t.role.upper()}: {t.content}" for t in options.history)
        answer = ai.complete(
            system=(
                "Answer questions using only the document provided. If the answer is not in it, say so. "
                "Quote short passages when helpful."
            ),
            prompt=(
                f"<document>\n{_document_text(inputs[0])}\n</document>\n\n"
                f"{('Conversation so far:\n' + transcript + '\n\n') if transcript else ''}"
                f"Question: {options.question}"
            ),
            max_tokens=1500,
        )
        out = ctx.output_path("answer.md")
        out.write_text(answer, encoding="utf-8")
        return [out]
