from services.finance_invoice_ocr import build_field_consensus, extract_invoice_fields


def _candidate(value: str, confidence: float = 0.9):
    return {
        "raw_value": value,
        "normalized_value": value,
        "confidence": confidence,
        "evidence_text": value,
        "bounding_box": None,
    }


def test_extracts_core_invoice_fields_without_guessing_missing_values():
    fields = extract_invoice_fields(
        """
        电子发票
        发票代码：011001900111
        发票号码：12345678
        开票日期：2026年08月08日
        购买方信息
        名称：测试购买单位
        纳税人识别号：91110000123456789X
        销售方信息
        名称：测试销售公司
        统一社会信用代码：91310000123456789Y
        合计 ¥80.00 ¥8.00
        价税合计（小写）¥88.00
        """
    )

    assert fields["invoice_code"]["normalized_value"] == "011001900111"
    assert fields["invoice_number"]["normalized_value"] == "12345678"
    assert fields["invoice_date"]["normalized_value"] == "2026-08-08"
    assert fields["buyer_name"]["normalized_value"] == "测试购买单位"
    assert fields["seller_name"]["normalized_value"] == "测试销售公司"
    assert fields["amount_excluding_tax"]["normalized_value"] == "80.00"
    assert fields["tax_amount"]["normalized_value"] == "8.00"
    assert fields["total_amount"]["normalized_value"] == "88.00"
    assert "bank_account" not in fields


def test_dual_engine_agreement_and_conflict_are_explicit():
    agreed = build_field_consensus([
        {"engine": "apple_vision", "status": "success", "fields": {"total_amount": _candidate("88.00")}},
        {"engine": "tesseract", "status": "success", "fields": {"total_amount": _candidate("88.00", 0.8)}},
    ])
    assert agreed["fields"]["total_amount"]["status"] == "agreed"
    assert agreed["conflicts"] == []

    conflicted = build_field_consensus([
        {"engine": "apple_vision", "status": "success", "fields": {"total_amount": _candidate("88.00")}},
        {"engine": "tesseract", "status": "success", "fields": {"total_amount": _candidate("38.00", 0.8)}},
    ])
    assert conflicted["fields"]["total_amount"]["status"] == "conflict"
    assert conflicted["conflicts"] == ["total_amount"]
    assert conflicted["requires_human_review"] is True


def test_tesseract_spacing_noise_is_normalized_before_field_extraction():
    fields = extract_invoice_fields(
        "发 票 代码 : 011001900111\n"
        "发 票 号 码 : 12345678\n"
        "开票 日 期 : 2026 年 08 月 08 日\n"
        "购买 方 信息\n名 称 : 测试 购买 单位\n"
        "销售 方 信息\n名 称 : 测试 销售 公司\n"
        "价 税 合计 (小 写 ) ¥88.00"
    )

    assert fields["invoice_code"]["normalized_value"] == "011001900111"
    assert fields["invoice_number"]["normalized_value"] == "12345678"
    assert fields["invoice_date"]["normalized_value"] == "2026-08-08"
    assert fields["buyer_name"]["normalized_value"] == "测试购买单位"
    assert fields["seller_name"]["normalized_value"] == "测试销售公司"
    assert fields["total_amount"]["normalized_value"] == "88.00"
