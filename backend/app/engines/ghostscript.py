"""Ghostscript adapter: compression, grayscale and PDF/A. Called as a CLI, never linked."""

from pathlib import Path
from typing import Literal

from app.engines.process import run

CompressionLevel = Literal["low", "recommended", "extreme"]

# Resolution in DPI for colour/gray images and the matching Ghostscript preset.
_LEVELS: dict[str, tuple[str, int]] = {
    "low": ("/printer", 220),
    "recommended": ("/ebook", 144),
    "extreme": ("/screen", 72),
}


class Ghostscript:
    def __init__(self, binary: str = "gs", timeout: int = 600):
        self.binary = binary
        self.timeout = timeout

    def _base(self, output: Path) -> list[str]:
        return [
            self.binary,
            "-sDEVICE=pdfwrite",
            "-dNOPAUSE",
            "-dBATCH",
            "-dQUIET",
            "-dSAFER",
            f"-sOutputFile={output}",
        ]

    def compress(self, source: Path, output: Path, level: CompressionLevel) -> Path:
        preset, dpi = _LEVELS[level]
        cmd = self._base(output) + [
            "-dCompatibilityLevel=1.6",
            f"-dPDFSETTINGS={preset}",
            "-dDetectDuplicateImages=true",
            "-dCompressFonts=true",
            "-dSubsetFonts=true",
            "-dDownsampleColorImages=true",
            "-dDownsampleGrayImages=true",
            "-dDownsampleMonoImages=true",
            f"-dColorImageResolution={dpi}",
            f"-dGrayImageResolution={dpi}",
            f"-dMonoImageResolution={dpi * 2}",
            "-dColorImageDownsampleThreshold=1.0",
            "-dGrayImageDownsampleThreshold=1.0",
            str(source),
        ]
        run(cmd, timeout=self.timeout, error="Compression failed.")
        return output

    def grayscale(self, source: Path, output: Path) -> Path:
        cmd = self._base(output) + [
            "-sColorConversionStrategy=Gray",
            "-dProcessColorModel=/DeviceGray",
            "-dOverrideICC",
            str(source),
        ]
        run(cmd, timeout=self.timeout, error="Grayscale conversion failed.")
        return output

    def pdfa(self, source: Path, output: Path, part: Literal[1, 2, 3] = 2) -> Path:
        cmd = self._base(output) + [
            f"-dPDFA={part}",
            "-dPDFACompatibilityPolicy=1",
            "-sColorConversionStrategy=RGB",
            str(source),
        ]
        run(cmd, timeout=self.timeout, error="PDF/A conversion failed.")
        return output
