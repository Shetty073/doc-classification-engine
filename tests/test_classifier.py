import pytest
from app.classifier import LLMClassifierService
from app.schemas import ClassificationResult
from app.utils.entity_extractor import extract_key_entities
from app.utils.quality import assess_document_quality
from app.utils.redactor import mask_aadhaar_numbers


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
    assert "SALARY_SLIP" in messages[0]["content"]
    assert "CANCELLED_CHEQUE" in messages[0]["content"]
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

    # Test Salary Slip
    salary_res = classifier._heuristic_fallback("PAYSLIP FOR MONTH JULY 2025 BASIC PAY 50000 NET PAY 65000")
    assert salary_res.category == "SALARY_SLIP"

    # Test Cancelled Cheque
    cheque_res = classifier._heuristic_fallback("CANCELLED CHEQUE HDFC BANK A/C NO 5010023456789 IFSC HDFC0000123")
    assert cheque_res.category == "CANCELLED_CHEQUE"

    # Test Utility Bill
    utility_res = classifier._heuristic_fallback("BESCOM ELECTRICITY BILL KWH METER READING 12345")
    assert utility_res.category == "UTILITY_BILL"


def test_unknown_with_guess_and_score(classifier):
    raw_json = '{"category": "UNKNOWN", "confidence_score": 90, "guess": "Academic Marksheet", "reasoning": "University mark card"}'
    result = classifier._parse_llm_json(raw_json)

    assert result.category == "UNKNOWN"
    assert result.confidence_score == 90
    assert result.guess == "Academic Marksheet"

    # Fallback on non-banking document
    fallback_res = classifier._heuristic_fallback("UNIVERSITY DEGREE MARKSHEET SEMESTER EXAMINATION ROLL NO 99123")
    assert fallback_res.category == "UNKNOWN"
    assert fallback_res.confidence_score >= 1 and fallback_res.confidence_score <= 100
    assert "Academic" in fallback_res.guess


def test_aadhaar_masking():
    # 12 digits with spaces
    text1 = "Aadhaar: 1234 5678 9012 valid."
    masked1 = mask_aadhaar_numbers(text1)
    assert "1234 5678" not in masked1
    assert "XXXX-XXXX-9012" in masked1

    # 12 digits with hyphens
    text2 = "UID: 9876-5432-1111"
    masked2 = mask_aadhaar_numbers(text2)
    assert "XXXX-XXXX-1111" in masked2

    # 16-digit Virtual ID
    text3 = "VID 1111-2222-3333-4444"
    masked3 = mask_aadhaar_numbers(text3)
    assert "XXXX-XXXX-XXXX-4444" in masked3


def test_entity_extraction():
    # PAN Extraction
    pan_text = "INCOME TAX DEPARTMENT GOVT OF INDIA PAN: ABCDE1234F DOB: 15/08/1990"
    pan_entities = extract_key_entities("PAN_CARD", pan_text)
    assert pan_entities.get("pan_number") == "ABCDE1234F"
    assert pan_entities.get("date_of_birth") == "15/08/1990"

    # GSTIN Extraction
    gst_text = "TAX INVOICE SUPPLIER GSTIN: 27ABCDE1234F1Z5 INVOICE NO: INV-100 TOTAL AMOUNT: 50,000.00"
    gst_entities = extract_key_entities("TAX_INVOICE", gst_text)
    assert gst_entities.get("gstin") == "27ABCDE1234F1Z5"
    assert gst_entities.get("document_number") == "INV-100"
    assert gst_entities.get("total_amount") == "50000.00"

    # Bank IFSC & Account
    bank_text = "STATEMENT IFSC CODE: SBIN0001234 ACCOUNT NO: 123456789012"
    bank_entities = extract_key_entities("BANK_STATEMENT", bank_text)
    assert bank_entities.get("ifsc_code") == "SBIN0001234"
    assert bank_entities.get("account_number") == "123456789012"


def test_document_quality():
    score, issues = assess_document_quality("sample_dataset/pan1.png")
    assert 1 <= score <= 100
    assert isinstance(issues, list)
