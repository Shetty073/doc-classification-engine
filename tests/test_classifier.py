import pytest
from app.classifier import LLMClassifierService
from app.schemas import ClassificationResult


@pytest.fixture
def classifier():
    return LLMClassifierService()


def test_build_prompt(classifier):
    ocr_sample = "Unique Identification Authority of India Government of India Aadhaar No: 1234 5678 9012"
    messages = classifier.build_prompt(ocr_sample)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "PASSPORT" in messages[0]["content"]
    assert "AADHAAR_CARD" in messages[0]["content"]
    assert "GST_RETURN" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "1234 5678 9012" in messages[1]["content"]


def test_parse_llm_json_valid(classifier):
    valid_json = '{"category": "AADHAAR_CARD", "confidence": 0.98, "reasoning": "Contains UIDAI and 12-digit number", "sub_category": "e-Aadhaar"}'
    result = classifier._parse_llm_json(valid_json)

    assert isinstance(result, ClassificationResult)
    assert result.category == "AADHAAR_CARD"
    assert result.confidence == 0.98
    assert result.sub_category == "e-Aadhaar"


def test_parse_llm_json_markdown_wrapped(classifier):
    wrapped_json = """```json
    {
        "category": "GST_RETURN",
        "confidence": 0.95,
        "reasoning": "Form GSTR-3B monthly return",
        "sub_category": "GSTR-3B"
    }
    ```"""
    result = classifier._parse_llm_json(wrapped_json)

    assert result.category == "GST_RETURN"
    assert result.confidence == 0.95
    assert result.sub_category == "GSTR-3B"


def test_heuristic_fallbacks(classifier):
    # Test Aadhaar
    aadhaar_res = classifier._heuristic_fallback("Unique Identification Authority of India Mera Aadhaar Meri Pehchan 9876 5432 1098")
    assert aadhaar_res.category == "AADHAAR_CARD"

    # Test PAN Card
    pan_res = classifier._heuristic_fallback("INCOME TAX DEPARTMENT GOVT OF INDIA PERMANENT ACCOUNT NUMBER CARD ABCDE1234F")
    assert pan_res.category == "PAN_CARD"

    # Test Voter ID
    voter_res = classifier._heuristic_fallback("ELECTION COMMISSION OF INDIA IDENTITY CARD EPIC NO: WBS1234567")
    assert voter_res.category == "VOTER_ID"

    # Test Passport
    passport_res = classifier._heuristic_fallback("PASSPORT REPUBLIC OF INDIA TYPE P CODE IND")
    assert passport_res.category == "PASSPORT"

    # Test GST
    gst_res = classifier._heuristic_fallback("GOODS AND SERVICES TAX REGISTRATION CERTIFICATE GSTIN: 27AAAAA0000A1Z5")
    assert gst_res.category == "GST_RETURN"

    # Test Tax Invoice
    invoice_res = classifier._heuristic_fallback("TAX INVOICE INVOICE NO: INV-2024-001 BILL TO ABC CORP HSN 8471")
    assert invoice_res.category == "TAX_INVOICE"

    # Test Purchase Order
    po_res = classifier._heuristic_fallback("PURCHASE ORDER PO NO: PO-98765 DATE: 12-04-2024 VENDOR NAME")
    assert po_res.category == "PURCHASE_ORDER"

    # Test Bank Statement
    statement_res = classifier._heuristic_fallback("ACCOUNT STATEMENT HDFC BANK LTD IFSC CODE HDFC0000123 CLOSING BALANCE 50000.00")
    assert statement_res.category == "BANK_STATEMENT"
    assert statement_res.confidence_score >= 1 and statement_res.confidence_score <= 100


def test_unknown_with_guess_and_score(classifier):
    # Test JSON with non-standard document
    raw_json = '{"category": "UNKNOWN", "confidence_score": 90, "guess": "Electricity / Utility Bill", "reasoning": "BESCOM power bill"}'
    result = classifier._parse_llm_json(raw_json)

    assert result.category == "UNKNOWN"
    assert result.confidence_score == 90
    assert result.guess == "Electricity / Utility Bill"

    # Test heuristic fallback on unrecognized document with electricity terms
    fallback_res = classifier._heuristic_fallback("BESCOM ELECTRICITY BILL KWH CONSUMER NO 12345")
    assert fallback_res.category == "UNKNOWN"
    assert fallback_res.confidence_score >= 1 and fallback_res.confidence_score <= 100
    assert "Electricity" in fallback_res.guess
