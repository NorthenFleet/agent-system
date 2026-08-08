"""Local, evidence-preserving OCR for invoice ingestion batches."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
VISION_SOURCE = BACKEND_ROOT / "tools" / "finance_vision_ocr.swift"
VISION_BINARY = Path(
    os.getenv("FINANCE_VISION_BINARY", str(BACKEND_ROOT / "data" / "finance-tools" / "finance-vision-ocr"))
)
OCR_TIMEOUT_SECONDS = int(os.getenv("FINANCE_OCR_TIMEOUT_SECONDS", "90"))
_VISION_BUILD_LOCK = threading.Lock()


class InvoiceOCRError(RuntimeError):
    pass


def _command_version(command: str) -> str:
    try:
        result = subprocess.run(
            [command, "--version"], capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return (result.stdout or result.stderr).splitlines()[0][:128] if (result.stdout or result.stderr) else "unknown"


def _run(command: list[str], *, timeout: int = OCR_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "LC_ALL": "en_US.UTF-8"},
        )
    except subprocess.TimeoutExpired as exc:
        raise InvoiceOCRError(f"OCR command timed out after {timeout}s") from exc
    except OSError as exc:
        raise InvoiceOCRError(f"OCR command unavailable: {command[0]}") from exc


def _source_suffix(content_type: str) -> str:
    return {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/tiff": ".tiff",
    }.get(content_type, ".bin")


def _preprocess(content: bytes, content_type: str, root: Path) -> tuple[Path, bytes, dict[str, Any]]:
    magick = shutil.which("magick")
    if not magick:
        raise InvoiceOCRError("ImageMagick is not installed")
    source = root / f"source{_source_suffix(content_type)}"
    output = root / "preprocessed.png"
    source.write_bytes(content)
    command = [magick]
    if content_type == "application/pdf":
        command.extend(["-density", "220", f"{source}[0]"])
    else:
        command.append(str(source))
    command.extend([
        "-auto-orient",
        "-deskew", "40%",
        "-colorspace", "Gray",
        "-contrast-stretch", "0.5%x0.5%",
        "-strip",
        str(output),
    ])
    started = time.monotonic()
    result = _run(command)
    duration_ms = int((time.monotonic() - started) * 1000)
    if result.returncode != 0 or not output.is_file():
        raise InvoiceOCRError((result.stderr or "image preprocessing failed").strip()[:1000])
    derived = output.read_bytes()
    return output, derived, {
        "status": "success",
        "tool": "ImageMagick",
        "tool_version": _command_version(magick),
        "duration_ms": duration_ms,
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "derived_sha256": hashlib.sha256(derived).hexdigest(),
        "operations": ["auto_orient", "deskew", "grayscale", "contrast_stretch", "strip_metadata"],
    }


def _vision_binary() -> Path:
    configured = os.getenv("FINANCE_VISION_BINARY")
    if configured:
        binary = Path(configured)
        if not binary.is_file():
            raise InvoiceOCRError(f"configured Vision OCR binary does not exist: {binary}")
        return binary
    swiftc = shutil.which("swiftc")
    if not swiftc or not VISION_SOURCE.is_file():
        raise InvoiceOCRError("Apple Vision OCR source or Swift compiler is unavailable")
    with _VISION_BUILD_LOCK:
        needs_build = not VISION_BINARY.is_file() or VISION_BINARY.stat().st_mtime < VISION_SOURCE.stat().st_mtime
        if needs_build:
            VISION_BINARY.parent.mkdir(parents=True, exist_ok=True)
            result = _run([swiftc, str(VISION_SOURCE), "-O", "-o", str(VISION_BINARY)], timeout=120)
            if result.returncode != 0:
                raise InvoiceOCRError((result.stderr or "Apple Vision OCR compilation failed").strip()[:2000])
    return VISION_BINARY


def _field_pattern(text: str, pattern: str) -> tuple[str, str] | None:
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip(), match.group(0).strip()


def _normal_date(value: str) -> str:
    match = re.search(r"(20\d{2})\D{0,3}(\d{1,2})\D{0,3}(\d{1,2})", value)
    if not match:
        return value.strip()
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def _normal_money(value: str) -> str:
    clean = re.sub(r"[^0-9.\-]", "", value.replace(",", ""))
    try:
        return str(Decimal(clean).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return value.strip()


def _section(text: str, start_markers: tuple[str, ...], end_markers: tuple[str, ...]) -> str:
    positions = [text.find(marker) for marker in start_markers if text.find(marker) >= 0]
    if not positions:
        return ""
    start = min(positions)
    end_positions = [text.find(marker, start + 1) for marker in end_markers if text.find(marker, start + 1) >= 0]
    end = min(end_positions) if end_positions else min(len(text), start + 1000)
    return text[start:end]


def extract_invoice_fields(text: str, *, confidence: float = 0.75) -> dict[str, dict[str, Any]]:
    """Extract evidence-backed candidates; unknown fields remain absent."""
    normalized_text = text.replace("：", ":").replace("（", "(").replace("）", ")")
    normalized_text = re.sub(r"(?<=[\u3400-\u9fff])[ \t]+(?=[\u3400-\u9fff])", "", normalized_text)
    fields: dict[str, dict[str, Any]] = {}

    simple_patterns = {
        "invoice_code": r"发票代码\s*[:：]?\s*([0-9]{10,12})",
        "invoice_number": r"发票号码\s*[:：]?\s*([0-9]{8,20})",
        "invoice_date": r"开票日期\s*[:：]?\s*((?:20)?\d{2}\D{0,3}\d{1,2}\D{0,3}\d{1,2})",
        "check_code": r"校验码\s*[:：]?\s*([0-9 ]{6,30})",
    }
    for name, pattern in simple_patterns.items():
        found = _field_pattern(normalized_text, pattern)
        if not found:
            continue
        raw, evidence = found
        value = re.sub(r"\s+", "", raw)
        if name == "invoice_date":
            value = _normal_date(raw)
        fields[name] = {
            "raw_value": raw,
            "normalized_value": value,
            "confidence": confidence,
            "evidence_text": evidence,
            "bounding_box": None,
        }

    buyer = _section(normalized_text, ("购买方信息", "购买方"), ("销售方信息", "销售方", "项目名称"))
    seller = _section(normalized_text, ("销售方信息", "销售方"), ("备注", "开票人", "收款人"))
    for prefix, section in (("buyer", buyer), ("seller", seller)):
        if not section:
            continue
        name_match = _field_pattern(section, r"名称\s*[:：]?\s*([^\n]{2,80})")
        tax_match = _field_pattern(section, r"(?:统一社会信用代码|纳税人识别号)\s*[:：]?\s*([0-9A-Z]{15,20})")
        if name_match:
            raw, evidence = name_match
            fields[f"{prefix}_name"] = {
                "raw_value": raw,
                "normalized_value": re.sub(r"\s+", "", raw),
                "confidence": confidence,
                "evidence_text": evidence,
                "bounding_box": None,
            }
        if tax_match:
            raw, evidence = tax_match
            fields[f"{prefix}_tax_id"] = {
                "raw_value": raw,
                "normalized_value": re.sub(r"\s+", "", raw).upper(),
                "confidence": confidence,
                "evidence_text": evidence,
                "bounding_box": None,
            }

    total_match = _field_pattern(
        normalized_text,
        r"价税合计[^\n]{0,80}?[¥￥]?\s*([0-9][0-9,]*\.\d{2})",
    )
    if total_match:
        raw, evidence = total_match
        fields["total_amount"] = {
            "raw_value": raw,
            "normalized_value": _normal_money(raw),
            "confidence": confidence,
            "evidence_text": evidence,
            "bounding_box": None,
        }

    subtotal_tax = re.search(
        r"(?:合\s*计|金额)[^\n]{0,50}?[¥￥]?\s*([0-9][0-9,]*\.\d{2})\s+[¥￥]?\s*([0-9][0-9,]*\.\d{2})",
        normalized_text,
        re.IGNORECASE,
    )
    if subtotal_tax:
        evidence = subtotal_tax.group(0).strip()
        for name, raw in (("amount_excluding_tax", subtotal_tax.group(1)), ("tax_amount", subtotal_tax.group(2))):
            fields[name] = {
                "raw_value": raw,
                "normalized_value": _normal_money(raw),
                "confidence": confidence,
                "evidence_text": evidence,
                "bounding_box": None,
            }
    return fields


def _vision_result(image: Path) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = _run([str(_vision_binary()), str(image)])
        payload = json.loads(result.stdout or "{}")
        if result.returncode != 0 or payload.get("status") != "success":
            raise InvoiceOCRError(str(payload.get("error") or result.stderr or "Vision OCR failed"))
        observations = list(payload.get("observations") or [])
        observations.sort(
            key=lambda item: (
                -float((item.get("bounding_box") or [0, 0])[1]),
                float((item.get("bounding_box") or [0])[0]),
            )
        )
        text = "\n".join(str(item.get("text") or "") for item in observations if item.get("text"))
        confidences = [float(item.get("confidence") or 0) for item in observations]
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return {
            "engine": "apple_vision",
            "engine_version": "VNRecognizeTextRequest",
            "status": "success",
            "text": text,
            "observations": observations,
            "fields": extract_invoice_fields(text, confidence=confidence),
            "duration_ms": int((time.monotonic() - started) * 1000),
            "error": None,
        }
    except (InvoiceOCRError, json.JSONDecodeError) as exc:
        return {
            "engine": "apple_vision",
            "engine_version": "VNRecognizeTextRequest",
            "status": "failed",
            "text": "",
            "observations": [],
            "fields": {},
            "duration_ms": int((time.monotonic() - started) * 1000),
            "error": str(exc)[:2000],
        }


def _tesseract_result(image: Path) -> dict[str, Any]:
    started = time.monotonic()
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return {
            "engine": "tesseract",
            "engine_version": "unavailable",
            "status": "unavailable",
            "text": "",
            "observations": [],
            "fields": {},
            "duration_ms": 0,
            "error": "tesseract is not installed",
        }
    result = _run([tesseract, str(image), "stdout", "-l", "chi_sim+eng", "--psm", "6", "tsv"])
    if result.returncode != 0:
        return {
            "engine": "tesseract",
            "engine_version": _command_version(tesseract),
            "status": "failed",
            "text": "",
            "observations": [],
            "fields": {},
            "duration_ms": int((time.monotonic() - started) * 1000),
            "error": (result.stderr or "Tesseract OCR failed").strip()[:2000],
        }
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
        word = str(row.get("text") or "").strip()
        try:
            word_confidence = float(row.get("conf") or -1)
        except ValueError:
            word_confidence = -1
        if word and word_confidence >= 0:
            grouped[(row.get("block_num", "0"), row.get("par_num", "0"), row.get("line_num", "0"))].append(row)
    observations = []
    for words in grouped.values():
        text = " ".join(str(word.get("text") or "") for word in words).strip()
        confidences = [float(word.get("conf") or 0) / 100 for word in words]
        left = min(int(word.get("left") or 0) for word in words)
        top = min(int(word.get("top") or 0) for word in words)
        right = max(int(word.get("left") or 0) + int(word.get("width") or 0) for word in words)
        bottom = max(int(word.get("top") or 0) + int(word.get("height") or 0) for word in words)
        observations.append({
            "text": text,
            "confidence": sum(confidences) / len(confidences),
            "bounding_box_pixels": [left, top, right - left, bottom - top],
        })
    text = "\n".join(item["text"] for item in observations)
    confidences = [float(item["confidence"]) for item in observations]
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return {
        "engine": "tesseract",
        "engine_version": _command_version(tesseract),
        "status": "success",
        "text": text,
        "observations": observations,
        "fields": extract_invoice_fields(text, confidence=confidence),
        "duration_ms": int((time.monotonic() - started) * 1000),
        "error": None,
    }


def build_field_consensus(runs: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        if run.get("status") != "success":
            continue
        for field_name, candidate in (run.get("fields") or {}).items():
            grouped[field_name].append({**candidate, "engine": run.get("engine")})

    fields: dict[str, Any] = {}
    conflicts: list[str] = []
    for field_name, candidates in grouped.items():
        values: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for candidate in candidates:
            values[str(candidate.get("normalized_value") or "")].append(candidate)
        ranked = sorted(
            values.items(),
            key=lambda item: (len(item[1]), max(float(value.get("confidence") or 0) for value in item[1])),
            reverse=True,
        )
        selected_value, selected_candidates = ranked[0]
        if len(values) > 1:
            status = "conflict"
            conflicts.append(field_name)
        elif len(selected_candidates) > 1:
            status = "agreed"
        else:
            status = "single_source"
        fields[field_name] = {
            "value": selected_value,
            "status": status,
            "confidence": max(float(item.get("confidence") or 0) for item in selected_candidates),
            "sources": [item.get("engine") for item in selected_candidates],
            "candidates": candidates,
        }
    return {"fields": fields, "conflicts": conflicts, "requires_human_review": True}


def run_local_invoice_ocr(content: bytes, content_type: str) -> dict[str, Any]:
    """Preprocess one invoice and run independent local OCR engines."""
    with tempfile.TemporaryDirectory(prefix="finance-invoice-ocr-") as temporary:
        image, derived, preprocessing = _preprocess(content, content_type, Path(temporary))
        runs = [_vision_result(image), _tesseract_result(image)]
        consensus = build_field_consensus(runs)
        successful = [run for run in runs if run.get("status") == "success"]
        return {
            "status": "success" if successful else "failed",
            "preprocessed_content": derived,
            "preprocessing": preprocessing,
            "runs": runs,
            "consensus": consensus,
        }
