"""
Structured Entity Extraction Utility for Indian Banking Documents.
Extracts high-value regulatory & financial data points:
- PAN Card: 10-char PAN, Name, DOB
- Aadhaar: Last 4 digits, Gender, Year/Date of Birth
- GST Return / Invoice: GSTIN, Total Amount, Period
- Bank Statement: IFSC Code, Account Number
- Salary Slip: Net Amount, Month/Year
- Purchase Order: PO Number, Date, Amount
"""
import re
from typing import Any, Dict, Optional


def extract_key_entities(category: str, text: str, llm_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extracts structured key-value entities tailored to the document category.
    Merges deterministic regex extraction with any structured metadata provided by the LLM.
    """
    entities: Dict[str, Any] = {}
    if llm_metadata and isinstance(llm_metadata, dict):
        entities.update(llm_metadata)

    upper_text = text.upper()

    # 1. PAN Card Extraction
    if category == "PAN_CARD" or "PERMANENT ACCOUNT NUMBER" in upper_text or "INCOME TAX DEPARTMENT" in upper_text:
        pan_match = re.search(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", upper_text)
        if pan_match:
            entities["pan_number"] = pan_match.group(1)

        # DOB extraction (DD/MM/YYYY or DD-MM-YYYY)
        dob_match = re.search(r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b", text)
        if dob_match:
            entities["date_of_birth"] = dob_match.group(1)

    # 2. Aadhaar Card Extraction
    if category == "AADHAAR_CARD" or "UIDAI" in upper_text or "MERA AADHAAR" in upper_text:
        # Search for masked or unmasked last 4
        last4_match = re.search(r"(?:XXXX[- ]?XXXX[- ]?|\b\d{4}[- ]?\d{4}[- ]?)(\d{4})\b", text)
        if last4_match:
            entities["aadhaar_last_4"] = last4_match.group(1)

        if "MALE" in upper_text and "FEMALE" not in upper_text:
            entities["gender"] = "MALE"
        elif "FEMALE" in upper_text:
            entities["gender"] = "FEMALE"

        yob_match = re.search(r"(?:DOB|YEAR OF BIRTH|YOB)\s*[:/]?\s*(\d{2}[/-]\d{2}[/-]\d{4}|\d{4})", upper_text)
        if yob_match:
            entities["dob_or_yob"] = yob_match.group(1)

    # 3. GST Return & Tax Invoice Extraction (GSTIN)
    gstin_matches = re.findall(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1})\b", upper_text)
    if gstin_matches:
        entities["gstin"] = gstin_matches[0]
        if len(gstin_matches) > 1:
            entities["additional_gstins"] = list(set(gstin_matches[1:]))

    # 4. Bank Statement Extraction (IFSC & Account No)
    if category in ["BANK_STATEMENT", "CANCELLED_CHEQUE"]:
        ifsc_match = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", upper_text)
        if ifsc_match:
            entities["ifsc_code"] = ifsc_match.group(1)

        ac_match = re.search(r"(?:ACCOUNT NO|A/C NO|ACCOUNT NUMBER)\.?\s*[:#-]?\s*([0-9]{9,18})\b", upper_text)
        if ac_match:
            entities["account_number"] = ac_match.group(1)

    # 5. Salary Slip Extraction
    if category == "SALARY_SLIP":
        net_pay_match = re.search(r"(?:NET PAY|NET SALARY|TAKE HOME)\s*[:₹\s]?\s*([0-9,]+(?:\.\d{2})?)", upper_text)
        if net_pay_match:
            entities["net_salary"] = net_pay_match.group(1).replace(",", "")

        gross_pay_match = re.search(r"(?:GROSS PAY|GROSS SALARY|TOTAL EARNINGS)\s*[:₹\s]?\s*([0-9,]+(?:\.\d{2})?)", upper_text)
        if gross_pay_match:
            entities["gross_salary"] = gross_pay_match.group(1).replace(",", "")

    # 6. Purchase Order & Tax Invoice (Amounts and Reference Numbers)
    if category in ["TAX_INVOICE", "PURCHASE_ORDER"]:
        inv_no_match = re.search(r"(?:INVOICE NO|INVOICE NUMBER|BILL NO|P\.?O\.?\s*(?:NO|NUMBER))\s*[:#-]?\s*([A-Za-z0-9/_-]+)", text, re.IGNORECASE)
        if inv_no_match:
            entities["document_number"] = inv_no_match.group(1).strip()

        total_match = re.search(r"(?:TOTAL AMOUNT|INVOICE TOTAL|GRAND TOTAL|NET AMOUNT)\s*[:₹\s]?\s*([0-9,]+(?:\.\d{2})?)", upper_text)
        if total_match:
            entities["total_amount"] = total_match.group(1).replace(",", "")

    # 7. Passport Number Extraction
    if category == "PASSPORT":
        passport_match = re.search(r"\b([A-Z][0-9]{7})\b", upper_text)
        if passport_match:
            entities["passport_number"] = passport_match.group(1)

    # 8. Voter ID (EPIC Number)
    if category == "VOTER_ID":
        epic_match = re.search(r"\b([A-Z]{3}[0-9]{7})\b", upper_text)
        if epic_match:
            entities["epic_number"] = epic_match.group(1)

    # 9. Driving Licence
    if category == "DRIVING_LICENCE":
        dl_match = re.search(r"\b([A-Z]{2}[-\s]?[0-9]{2}[-\s]?[0-9A-Z]{11,12})\b", upper_text)
        if dl_match:
            entities["dl_number"] = dl_match.group(1)

    return entities
