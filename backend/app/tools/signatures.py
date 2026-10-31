"""Digital (certificate) signatures with pyHanko: sign with your own certificate, and check existing signatures.

A digital signature is different from the Sign tool's drawn signature: it seals the file cryptographically, so any
later change shows up in every PDF reader.
"""

import base64
import datetime as dt
import io
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from app.domain.errors import ValidationFailed
from app.tools.base import Category, Tool, ToolContext, ToolOptions, stem
from app.tools.overlay import anchor_xy, user_rect, visual_size
from app.tools.pdfio import open_pdf
from app.tools.registry import register

Position = Literal["top-left", "top-right", "bottom-left", "bottom-center", "bottom-right"]
STAMP_W, STAMP_H = 200.0, 56.0


def self_signed_pkcs12(name: str, email: str | None, days: int = 365) -> bytes:
    """A fresh key and self-signed certificate for someone without one. Readers show it as 'identity not verified'."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import NoEncryption, pkcs12
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, name)]
    if email:
        attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))
    subject = x509.Name(attrs)
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )  # fmt: skip
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(name.encode(), key, cert, None, NoEncryption())


def _decode_file(data_url: str) -> bytes:
    payload = data_url.split(",", 1)[1] if data_url.startswith("data:") else data_url
    try:
        return base64.b64decode(payload)
    except ValueError:
        raise ValidationFailed("The certificate file could not be read.") from None


@register
class DigitalSignTool(Tool):
    id = "digital_sign"
    name = "Digital signature"
    description = "Seal a PDF with a certificate-based digital signature that reveals any later change."
    category = Category.SECURITY
    max_files = 1
    premium = True

    class Options(ToolOptions):
        certificate: str | None = Field(
            None, description="Your certificate (.p12 or .pfx) as a data URL. Leave empty to create one for you"
        )
        certificate_password: str | None = Field(None, description="Password of the certificate file")
        signer_name: str | None = Field(None, max_length=120, description="Name on a newly created certificate")
        signer_email: str | None = Field(None, max_length=200)
        reason: str | None = Field(None, max_length=200, description="Why you are signing, e.g. 'I approve'")
        location: str | None = Field(None, max_length=120)
        visible: bool = Field(True, description="Show a signature stamp on the page")
        page: int = Field(1, ge=1, description="Page for the stamp (counts from 1; use a large number for the last)")
        position: Position = "bottom-right"
        field_name: str | None = Field(None, description="Sign an existing empty signature field instead")
        certify: bool = Field(False, description="Certify: allow only form filling after signing")
        timestamp_url: str | None = Field(None, description="RFC 3161 timestamp server, e.g. https://freetsa.org/tsr")

        @model_validator(mode="after")
        def _need_identity(self):
            if not self.certificate and not (self.signer_name or "").strip():
                raise ValueError("Upload your certificate, or enter your name to create one.")
            return self

    def run(self, inputs: list[Path], options: Options, ctx: ToolContext) -> list[Path]:
        from pyhanko import stamp
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import fields, signers, timestamps

        if options.certificate:
            p12, password = _decode_file(options.certificate), (options.certificate_password or "").encode() or None
        else:
            p12, password = self_signed_pkcs12(options.signer_name.strip(), options.signer_email), None
        try:
            signer = signers.SimpleSigner.load_pkcs12_data(p12, other_certs=[], passphrase=password)
        except Exception:
            signer = None
        if signer is None:
            raise ValidationFailed("Couldn't open the certificate. Check the file and its password.")

        # Work out the stamp box in user space up front (pyHanko wants page index + box).
        with open_pdf(inputs[0]) as pdf:
            if pdf.is_encrypted:
                raise ValidationFailed("Unlock this PDF before signing it.")
            page_index = min(options.page, len(pdf.pages)) - 1
            page = pdf.pages[page_index]
            vw, vh = visual_size(page)
            bx, by = anchor_xy(options.position, STAMP_W, STAMP_H, vw, vh, 28)
            box = user_rect(page, bx / vw, 1 - (by + STAMP_H) / vh, STAMP_W / vw, STAMP_H / vh)

        field_name = options.field_name or f"Signature{dt.datetime.now(dt.UTC):%Y%m%d%H%M%S}"
        meta = signers.PdfSignatureMetadata(
            field_name=field_name,
            reason=options.reason or None,
            location=options.location or None,
            certify=options.certify,
            md_algorithm="sha256",
        )
        spec = None
        if not options.field_name:
            spec = fields.SigFieldSpec(
                field_name, on_page=page_index, box=tuple(round(v) for v in box) if options.visible else None
            )
        stamp_style = stamp.TextStampStyle(
            stamp_text="Digitally signed by\n%(signer)s\n%(ts)s", timestamp_format="%d %b %Y %H:%M UTC", border_width=1
        )
        timestamper = timestamps.HTTPTimeStamper(options.timestamp_url) if options.timestamp_url else None
        out = ctx.output_path(f"{stem(inputs[0])}-signed.pdf")
        with inputs[0].open("rb") as source:
            writer = IncrementalPdfFileWriter(source, strict=False)
            pdf_signer = signers.PdfSigner(
                meta, signer=signer, timestamper=timestamper, stamp_style=stamp_style, new_field_spec=spec
            )
            try:
                buf = pdf_signer.sign_pdf(writer, existing_fields_only=bool(options.field_name), output=io.BytesIO())
            except Exception as exc:
                raise ValidationFailed(f"Signing failed: {exc}") from exc
            out.write_bytes(buf.getvalue())
        return [out]


@register
class VerifySignaturesTool(Tool):
    id = "verify_signatures"
    name = "Check signatures"
    description = "See who digitally signed a PDF, when, and whether it has changed since."
    category = Category.SECURITY
    max_files = 1
    produces_pdf = False

    def run(self, inputs: list[Path], options, ctx: ToolContext) -> list[Path]:
        report = signature_report(inputs[0])
        out = ctx.output_path(f"{stem(inputs[0])}-signatures.md")
        out.write_text(report, encoding="utf-8")
        return [out]


def signature_report(path: Path) -> str:
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    lines = [f"# Signatures in {path.name}", ""]
    with path.open("rb") as f:
        try:
            reader = PdfFileReader(f, strict=False)
        except Exception:
            raise ValidationFailed(f"'{path.name}' is not a readable PDF.") from None
        signatures = reader.embedded_signatures
        if not signatures:
            return "\n".join([*lines, "This PDF has no digital signatures.", ""])
        context = ValidationContext(allow_fetching=False)
        for n, sig in enumerate(signatures, start=1):
            try:
                status = validate_pdf_signature(sig, context)
            except Exception as exc:
                lines += [f"## {n}. {sig.field_name}", "", f"Could not be checked: {exc}", ""]
                continue
            cert = status.signing_cert
            who = cert.subject.human_friendly if cert else "unknown"
            when = (
                status.signer_reported_dt.strftime("%d %b %Y %H:%M UTC") if status.signer_reported_dt else "not stated"
            )
            intact = status.intact and status.valid
            coverage = status.coverage.name.replace("_", " ").lower() if status.coverage else "unknown"
            level = status.modification_level
            changes = level.name.replace("_", " ").lower() if level and level.name != "NONE" else "none"
            verdict = "valid, document unchanged since signing" if intact else "INVALID: the file was altered"
            trust = "trusted" if status.trusted else "not from a trusted authority (for example self-signed)"
            lines += [
                f"## {n}. {sig.field_name}",
                "",
                f"- **Signed by:** {who}",
                f"- **Signed at:** {when}",
                f"- **Signature:** {verdict}",
                f"- **Certificate:** {trust}",
                f"- **Covers:** {coverage}",
                f"- **Later changes:** {changes}",
                f"- **Timestamped:** {'yes' if status.timestamp_validity else 'no'}",
                "",
            ]
    return "\n".join(lines)
