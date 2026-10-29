"""Optimize tools: compress, repair, grayscale, OCR and deskew."""

import shutil
import sys
from pathlib import Path
from typing import Literal

import pikepdf
from pydantic import Field

from app.domain.errors import ToolFailed
from app.engines.process import run
from app.tools.base import Category, Tool, ToolContext, ToolOptions, stem
from app.tools.pdfio import open_pdf, save_pdf
from app.tools.registry import register


@register
class CompressTool(Tool):
    id = "compress"
    name = "Compress PDF"
    description = "Shrink file size while keeping the best quality for the level you choose."
    category = Category.OPTIMIZE

    class Options(ToolOptions):
        level: Literal["low", "recommended", "extreme"] = Field(
            "recommended", description="Low keeps the most quality, extreme gives the smallest file"
        )

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            out = ctx.output_path(f"{stem(path)}-compressed.pdf")
            ctx.gs().compress(path, out, options.level)
            # Already-optimized files can grow under Ghostscript; never hand back a bigger file.
            if out.stat().st_size >= path.stat().st_size:
                with open_pdf(path) as pdf:
                    save_pdf(pdf, out)
                if out.stat().st_size >= path.stat().st_size:
                    shutil.copyfile(path, out)
            outputs.append(out)
        return outputs


@register
class RepairTool(Tool):
    id = "repair"
    name = "Repair PDF"
    description = "Recover damaged or corrupt PDFs."
    category = Category.OPTIMIZE

    def run(self, inputs: list[Path], options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            out = ctx.output_path(f"{stem(path)}-repaired.pdf")
            try:
                # qpdf reconstructs broken xref tables and streams on open.
                with pikepdf.open(path, attempt_recovery=True) as pdf:
                    save_pdf(pdf, out)
            except pikepdf.PdfError:
                # Last resort: let Ghostscript re-interpret and rewrite the file.
                try:
                    ctx.gs().compress(path, out, "low")
                except ToolFailed:
                    raise ToolFailed(f"'{path.name}' is too damaged to repair.") from None
            outputs.append(out)
        return outputs


@register
class GrayscaleTool(Tool):
    id = "grayscale"
    name = "Grayscale PDF"
    description = "Convert colours to shades of gray to save ink."
    category = Category.OPTIMIZE

    def run(self, inputs: list[Path], options, ctx: ToolContext) -> list[Path]:
        return [ctx.gs().grayscale(p, ctx.output_path(f"{stem(p)}-grayscale.pdf")) for p in inputs]


@register
class OcrTool(Tool):
    id = "ocr"
    name = "OCR PDF"
    description = "Make scanned PDFs searchable and selectable."
    category = Category.OPTIMIZE
    premium = True

    class Options(ToolOptions):
        languages: list[str] = Field(["eng"], min_length=1, description="Document languages (Tesseract codes)")
        deskew: bool = Field(True, description="Straighten crooked scans")
        rotate_pages: bool = Field(True, description="Fix sideways pages automatically")
        mode: Literal["skip_text", "force", "redo"] = Field(
            "skip_text", description="skip_text leaves pages that already have text alone"
        )
        output: Literal["pdf", "pdfa"] = "pdf"

    MODE_FLAGS = {"skip_text": "--skip-text", "force": "--force-ocr", "redo": "--redo-ocr"}

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        langs = "+".join(sorted({lang.strip() for lang in options.languages if lang.strip().isalnum()}))
        outputs = []
        for path in inputs:
            out = ctx.output_path(f"{stem(path)}-ocr.pdf")
            cmd = [
                sys.executable,
                "-m",
                "ocrmypdf",
                "--language",
                langs or ctx.ocr_languages,
                self.MODE_FLAGS[options.mode],
                "--output-type",
                options.output,
                "--optimize",
                "1",
                "--jobs",
                "2",
                "--quiet",
            ]
            if options.deskew and options.mode != "redo":
                cmd.append("--deskew")
            if options.rotate_pages:
                cmd.append("--rotate-pages")
            run([*cmd, str(path), str(out)], timeout=ctx.timeout_seconds, error=f"OCR failed for '{path.name}'.")
            outputs.append(out)
        return outputs


@register
class DeskewTool(Tool):
    id = "deskew"
    name = "Deskew PDF"
    description = "Straighten scanned pages that were fed in at an angle."
    category = Category.OPTIMIZE
    premium = True

    def run(self, inputs: list[Path], options, ctx: ToolContext) -> list[Path]:
        outputs = []
        for path in inputs:
            out = ctx.output_path(f"{stem(path)}-deskewed.pdf")
            cmd = [sys.executable, "-m", "ocrmypdf", "--deskew", "--force-ocr", "--quiet", "--optimize", "1"]
            run([*cmd, str(path), str(out)], timeout=ctx.timeout_seconds, error=f"Deskew failed for '{path.name}'.")
            outputs.append(out)
        return outputs
