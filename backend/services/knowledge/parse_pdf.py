"""Resource-bounded PDF text extraction subprocess; prints no source to logs."""
import json
import resource
import sys
from pathlib import Path


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024, 2 * 1024 * 1024))
    # RLIMIT_AS is supported on Linux; macOS does not reliably enforce it.
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    from pypdf import PdfReader
    try:
        reader = PdfReader(sys.argv[1], strict=True)
        if reader.is_encrypted:
            result = {"error": "encrypted_pdf"}
        elif len(reader.pages) > 50:
            result = {"error": "budget_exceeded"}
        else:
            pages = []
            total = 0
            for page in reader.pages:
                text = (page.extract_text() or "").strip()
                total += len(text)
                if total > 50000 or len(text) > 12000:
                    result = {"error": "budget_exceeded"}
                    break
                pages.append(text)
            else:
                result = {"pages": pages} if pages and all(pages) else {"error": "needs_ocr"}
    except Exception:
        result = {"error": "parse_failed"}
    Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
