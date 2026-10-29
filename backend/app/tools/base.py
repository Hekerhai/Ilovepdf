"""The Tool contract every PDF operation implements.

A tool takes input files plus a validated options model and writes output files into its work directory.
Tools never touch storage, the database, quotas or HTTP: the job service handles those, which is what lets
workflows chain any tool after any other.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from app.domain.ports import AIProvider, DocumentConverter
    from app.engines.ghostscript import Ghostscript


class Category(StrEnum):
    ORGANIZE = "organize"
    OPTIMIZE = "optimize"
    CONVERT_TO = "convert_to_pdf"
    CONVERT_FROM = "convert_from_pdf"
    EDIT = "edit"
    SECURITY = "security"
    INTELLIGENCE = "intelligence"


CATEGORY_LABELS = {
    Category.ORGANIZE: "Organize",
    Category.OPTIMIZE: "Optimize",
    Category.CONVERT_TO: "Convert to PDF",
    Category.CONVERT_FROM: "Convert from PDF",
    Category.EDIT: "Edit",
    Category.SECURITY: "Security",
    Category.INTELLIGENCE: "Intelligence",
}

PDF = (".pdf",)
IMAGES = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif")


class ToolOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoOptions(ToolOptions):
    pass


@dataclass
class ToolContext:
    """Everything a tool may use besides its inputs. Injected by the job service."""

    work_dir: Path
    converter: DocumentConverter | None = None
    ai: AIProvider | None = None
    ghostscript: Ghostscript | None = None
    ocr_languages: str = "eng"
    timeout_seconds: int = 600
    _counter: int = field(default=0, repr=False)

    def gs(self) -> Ghostscript:
        if self.ghostscript is None:
            from app.engines.ghostscript import Ghostscript

            self.ghostscript = Ghostscript(timeout=self.timeout_seconds)
        return self.ghostscript

    def require_converter(self) -> DocumentConverter:
        if self.converter is None:
            from app.domain.errors import ServiceUnavailable

            raise ServiceUnavailable("Document conversion is not configured on this server.")
        return self.converter

    def output_path(self, name: str) -> Path:
        """A unique path inside the work dir for an output file."""
        self._counter += 1
        out_dir = self.work_dir / "out" / f"{self._counter:03d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / name


class Tool(ABC):
    id: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    category: ClassVar[Category]
    accepts: ClassVar[tuple[str, ...]] = PDF
    min_files: ClassVar[int] = 1
    max_files: ClassVar[int | None] = None  # None = limited only by plan
    premium: ClassVar[bool] = False
    # True when the web app has an in-browser implementation; the server one stays as fallback and for the API.
    browser_capable: ClassVar[bool] = False
    # True when outputs are PDFs, so the tool can feed the next step of a workflow.
    produces_pdf: ClassVar[bool] = True
    Options: ClassVar[type[ToolOptions]] = NoOptions

    @abstractmethod
    def run(self, inputs: list[Path], options: Any, ctx: ToolContext) -> list[Path]:
        """Process ``inputs`` and return output file paths inside ``ctx.work_dir``."""

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "id": cls.id,
            "name": cls.name,
            "description": cls.description,
            "category": cls.category.value,
            "accepts": list(cls.accepts),
            "min_files": cls.min_files,
            "max_files": cls.max_files,
            "premium": cls.premium,
            "browser_capable": cls.browser_capable,
            "produces_pdf": cls.produces_pdf,
            "options_schema": cls.Options.model_json_schema(),
        }


def stem(path: Path) -> str:
    """The original file name without our storage prefix or extension."""
    return path.stem
