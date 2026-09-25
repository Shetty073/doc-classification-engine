import json
import logging
import re
from typing import Dict, Any, Optional
import httpx
from app.config import settings
from app.schemas import ClassificationResult

logger = logging.getLogger("classifier_service")

# Strict Taxonomy of Indian Financial & Banking Documents
ALLOWED_CATEGORIES = [
    "PASSPORT",
    "DRIVING_LICENCE",
    "AADHAAR_CARD",
    "VOTER_ID",
    "NREGA_JOB_CARD",
    "NPR_LETTER",
    "PAN_CARD",
    "GST_RETURN",
    "INCOME_TAX_RETURN",
    "PURCHASE_ORDER",
    "TAX_INVOICE",
    "BANK_STATEMENT",
    "AUDITED_FINANCIALS",
    "BUSINESS_REGISTRATION",
    "UNKNOWN",
]

TAXONOMY_DESCRIPTION = """
You are a Principal Document Intelligence Classifier for an Indian Bank.
Classify the given document into EXACTLY ONE category from this list:

1. PASSPORT: Republic of India Passport, Passport No, Nationality Indian.
2. DRIVING_LICENCE: Union of India Driving Licence, State Licensing Authority/RTO, DL number, Form 7.
3. AADHAAR_CARD: UIDAI, Mera Aadhaar Meri Pehchan, 12-digit Aadhaar/VID number, e-Aadhaar.
4. VOTER_ID: Election Commission of India, EPIC Number, Elector's Name.
5. NREGA_JOB_CARD: MGNREGA Job Card, State Rural Development.
6. NPR_LETTER: National Population Register official letter.
7. PAN_CARD: Income Tax Department, Permanent Account Number, 10-digit PAN (e.g. ABCDE1234F).
8. GST_RETURN: ANY Goods and Services Tax document, Form GSTR-1, GSTR-3B, GSTR-9, GSTIN details. (IMPORTANT: If GSTR or GST return, category MUST be GST_RETURN, NOT BUSINESS_REGISTRATION).
9. INCOME_TAX_RETURN: Income Tax Return Acknowledgement, ITR-V, Assessment Year, Total Income.
10. PURCHASE_ORDER: Purchase Order, Work Order, PO Number, Order Date, Vendor line items.
11. TAX_INVOICE: Tax Invoice, Commercial Invoice, Bill of Supply, e-Invoice, IRN, HSN/SAC codes.
12. BANK_STATEMENT: Bank Account Statement, IFSC, Account Number, Transaction History, Balance.
13. AUDITED_FINANCIALS: Balance Sheet, Profit & Loss Statement, Auditor's Report, Notes to Accounts.
14. BUSINESS_REGISTRATION: Udyam/MSME Registration Certificate, Certificate of Incorporation (CIN / Ministry of Corporate Affairs), Partnership Deed.
15. UNKNOWN: Non-financial, unrecognized, or illegible document.
"""

SYSTEM_PROMPT = f"""
{TAXONOMY_DESCRIPTION}

OUTPUT FORMAT RULES:
- Reply ONLY with a single JSON object.
- The "category" field MUST be one of:
  ["PASSPORT", "DRIVING_LICENCE", "AADHAAR_CARD", "VOTER_ID", "NREGA_JOB_CARD", "NPR_LETTER", "PAN_CARD", "GST_RETURN", "INCOME_TAX_RETURN", "PURCHASE_ORDER", "TAX_INVOICE", "BANK_STATEMENT", "AUDITED_FINANCIALS", "BUSINESS_REGISTRATION", "UNKNOWN"]
- Do NOT classify GST returns as BUSINESS_REGISTRATION; use GST_RETURN.
- Do NOT classify Work Orders as BUSINESS_REGISTRATION; use PURCHASE_ORDER.
- Do NOT classify Balance Sheets as BUSINESS_REGISTRATION; use AUDITED_FINANCIALS.
- CRITICAL FOR UNKNOWN: If the document does not fit any of the 14 standard categories, set "category": "UNKNOWN", and provide a specific hypothesis in "guess" (e.g., "Electricity / Utility Bill", "Salary Slip", "Vehicle Registration / RC", "Cancelled Cheque", "Academic Marksheet", "Medical Prescription / Hospital Bill", "Courier Slip", etc.).
- "confidence_score": An integer between 1 and 100.

JSON Schema:
{{
  "category": "CATEGORY_NAME",
  "confidence_score": 85,
  "guess": "Specific hypothesis if UNKNOWN, or null if categorized",
  "reasoning": "Brief explanation identifying key terms",
  "sub_category": "Specific variant name"
}}
"""


class LLMClassifierService:
    def __init__(self, endpoint_url: str = settings.LLAMA_CPP_URL, timeout: float = settings.LLM_REQUEST_TIMEOUT_SECONDS):
        self.endpoint_url = endpoint_url
        self.timeout = timeout

    def build_prompt(self, ocr_text: str) -> list[Dict[str, str]]:
        # Take key text from top and bottom to avoid losing classification headers
        cleaned_text = ocr_text.strip()
        if len(cleaned_text) > 4000:
            cleaned_text = cleaned_text[:3000] + "\n...[TRUNCATED]...\n" + cleaned_text[-1000:]

        user_content = (
            f"Analyze this Indian document OCR text and classify it into the exact category.\n"
            f"If it does not fit the banking taxonomy, categorize as UNKNOWN, assign a confidence_score between 1 and 100, and provide your best guess of what it is:\n\n"
            f"--- DOCUMENT OCR TEXT ---\n"
            f"{cleaned_text if cleaned_text else '[EMPTY DOCUMENT]'}\n"
            f"--- END DOCUMENT OCR TEXT ---\n"
        )

        return [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": user_content},
        ]

    async def classify_text(self, ocr_text: str) -> ClassificationResult:
        """
        Calls local llama.cpp server OpenAI-compatible endpoint with the prompt
        and parses the structured classification response.
        """
        if not ocr_text or len(ocr_text.strip()) < 10:
            logger.warning("OCR text is empty or too short. Defaulting to UNKNOWN.")
            return ClassificationResult(
                category="UNKNOWN",
                confidence_score=10,
                guess="Illegible / Blank Document",
                confidence=0.10,
                reasoning="Insufficient or no readable text extracted from document.",
            )

        messages = self.build_prompt(ocr_text)
        payload: Dict[str, Any] = {
            "model": settings.LLAMA_MODEL_NAME,
            "messages": messages,
            "temperature": 0.05,  # Almost greedy decoding for maximum determinism
            "max_tokens": 256,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info("Sending classification request to llama.cpp at %s", self.endpoint_url)
                response = await client.post(self.endpoint_url, json=payload)
                response.raise_for_status()
                response_data = response.json()

            raw_content = response_data["choices"][0]["message"]["content"]
            parsed_result = self._parse_llm_json(raw_content, ocr_text)
            return parsed_result

        except httpx.RequestError as exc:
            logger.error("Network or connection error communicating with llama.cpp: %s", exc)
            return self._heuristic_fallback(ocr_text, error=f"LLM server unreachable: {exc}")
        except Exception as exc:
            logger.error("Error during document classification: %s", exc, exc_info=True)
            return self._heuristic_fallback(ocr_text, error=str(exc))

    def _parse_llm_json(self, raw_content: str, source_text: str = "") -> ClassificationResult:
        """Sanitizes and parses JSON returned by llama.cpp, applying banking reconciliation."""
        try:
            clean_str = raw_content.strip()
            clean_str = re.sub(r"^```json\s*", "", clean_str)
            clean_str = re.sub(r"\s*```$", "", clean_str)
            data = json.loads(clean_str)

            category = str(data.get("category", "UNKNOWN")).strip().upper()
            
            # Confidence score scaling (1 to 100)
            raw_conf = data.get("confidence_score")
            if raw_conf is not None:
                try:
                    conf_score = int(float(raw_conf))
                except (ValueError, TypeError):
                    conf_score = 85
            else:
                conf_val = float(data.get("confidence", 0.85))
                conf_score = int(round(conf_val * 100)) if conf_val <= 1.0 else int(round(conf_val))

            confidence_score = max(1, min(100, conf_score))
            confidence_float = round(confidence_score / 100.0, 2)

            reasoning = str(data.get("reasoning", "LLM-classified"))
            sub_category = data.get("sub_category")
            guess = data.get("guess")

            sub_cat_str = str(sub_category).upper() if sub_category else ""
            raw_upper = raw_content.upper()
            src_upper = source_text.upper()

            # Rule reconciliation: Fix sub_category vs category discrepancies
            if "GSTR" in sub_cat_str or "GSTR" in raw_upper or "GSTR-3B" in src_upper or "GSTR-1" in src_upper or "FORM GSTR" in src_upper:
                category = "GST_RETURN"
            elif "BALANCE SHEET" in sub_cat_str or "AUDITED" in sub_cat_str or "BALANCE SHEET" in src_upper:
                category = "AUDITED_FINANCIALS"
            elif "WORK ORDER" in sub_cat_str or "PURCHASE ORDER" in sub_cat_str or "WORK ORDER" in src_upper:
                category = "PURCHASE_ORDER"
            elif "TAX INVOICE" in sub_cat_str or "TAX INVOICE" in src_upper:
                category = "TAX_INVOICE"
            elif "PAN" in sub_cat_str or "PERMANENT ACCOUNT NUMBER" in src_upper:
                category = "PAN_CARD"
            elif "AADHAAR" in sub_cat_str or "MERA AADHAAR" in src_upper:
                category = "AADHAAR_CARD"
            elif "INCORPORATION" in sub_cat_str or "UDYAM" in sub_cat_str:
                category = "BUSINESS_REGISTRATION"

            # If the category is not in our 14 recognized banking categories, normalize to UNKNOWN
            # and preserve the LLM's classification as the guess
            if category not in ALLOWED_CATEGORIES:
                if not guess or guess.strip() == "":
                    guess = str(data.get("category", "")).replace("_", " ").title()
                category = "UNKNOWN"

            # If UNKNOWN and no guess was given, extract a heuristic guess
            if category == "UNKNOWN" and (not guess or guess.strip() == ""):
                guess = self._guess_unknown_type(source_text)

            return ClassificationResult(
                category=category,
                confidence_score=confidence_score,
                guess=guess,
                confidence=confidence_float,
                reasoning=reasoning,
                sub_category=sub_category,
            )
        except Exception as e:
            logger.error("Failed to parse LLM JSON: %s. Raw: %s", e, raw_content)
            guess_val = self._guess_unknown_type(source_text)
            return ClassificationResult(
                category="UNKNOWN",
                confidence_score=30,
                guess=guess_val,
                confidence=0.30,
                reasoning=f"Failed to parse LLM response: {raw_content[:100]}",
            )

    def _guess_unknown_type(self, text: str) -> str:
        """Heuristically infers likely document type when outside RBI OVD or business taxonomy."""
        upper = text.upper()
        if any(w in upper for w in ["ELECTRICITY", "POWER", "DISCOM", "BESCOM", "TNEB", "KWH", "METER READING", "CONSUMER NO"]):
            return "Electricity / Utility Bill"
        if any(w in upper for w in ["PAYSLIP", "SALARY SLIP", "EARNINGS", "BASIC PAY", "HRA", "EMPLOYEE ID", "NET PAY"]):
            return "Salary / Pay Slip"
        if any(w in upper for w in ["CHASSIS", "REGISTRATION CERTIFICATE", "MOTOR VEHICLES", "INSURANCE POLICY", "POLICY NO"]):
            return "Vehicle Registration / Insurance Document"
        if any(w in upper for w in ["CHEQUE", "PAY TO", "BEARER", "MICR", "A/C PAYEE"]):
            return "Cheque / Cancelled Cheque"
        if any(w in upper for w in ["MARKSHEET", "UNIVERSITY", "DEGREE", "SEMESTER", "ROLL NO", "EXAMINATION"]):
            return "Academic Degree / Educational Certificate"
        if any(w in upper for w in ["HOSPITAL", "DIAGNOSIS", "PATIENT", "PRESCRIPTION", "CLINIC", "RX"]):
            return "Medical Prescription / Health Record"
        if any(w in upper for w in ["FIXED DEPOSIT", "TERM DEPOSIT", "FD ADVICE", "MATURITY VALUE"]):
            return "Fixed Deposit Receipt / Advice"
        return "Unclassified / Non-Banking Document"

    def _heuristic_fallback(self, text: str, error: Optional[str] = None) -> ClassificationResult:
        """
        Deterministic banking heuristics fallback in case llama.cpp is offline or busy.
        Ensures high availability for mission-critical banking pipelines.
        """
        upper_text = text.upper()

        if "AADHAAR" in upper_text or "UIDAI" in upper_text or "MERA AADHAAR" in upper_text:
            return ClassificationResult(
                category="AADHAAR_CARD",
                confidence_score=92,
                confidence=0.92,
                guess=None,
                reasoning="Heuristic match: UIDAI / Aadhaar anchor terms present.",
            )
        if "INCOME TAX DEPARTMENT" in upper_text and ("PERMANENT ACCOUNT NUMBER" in upper_text or "PAN" in upper_text):
            return ClassificationResult(
                category="PAN_CARD",
                confidence_score=92,
                confidence=0.92,
                guess=None,
                reasoning="Heuristic match: Income Tax Department / PAN anchors present.",
            )
        if "ELECTION COMMISSION OF INDIA" in upper_text or "IDENTITY CARD" in upper_text and "EPIC" in upper_text:
            return ClassificationResult(
                category="VOTER_ID",
                confidence_score=90,
                confidence=0.90,
                guess=None,
                reasoning="Heuristic match: Election Commission / EPIC anchors present.",
            )
        if "DRIVING LICENCE" in upper_text or "UNION OF INDIA DRIVING LICENCE" in upper_text or "MOTOR VEHICLES" in upper_text:
            return ClassificationResult(
                category="DRIVING_LICENCE",
                confidence_score=90,
                confidence=0.90,
                guess=None,
                reasoning="Heuristic match: Driving Licence keywords present.",
            )
        if "PASSPORT" in upper_text and ("REPUBLIC OF INDIA" in upper_text or "INDIAN PASSPORT" in upper_text):
            return ClassificationResult(
                category="PASSPORT",
                confidence_score=95,
                confidence=0.95,
                guess=None,
                reasoning="Heuristic match: Republic of India Passport anchors present.",
            )
        if "GOODS AND SERVICES TAX" in upper_text or "GSTIN" in upper_text or "GSTR-3B" in upper_text or "GSTR-1" in upper_text or "FORM GSTR" in upper_text:
            return ClassificationResult(
                category="GST_RETURN",
                confidence_score=90,
                confidence=0.90,
                guess=None,
                reasoning="Heuristic match: Goods and Services Tax / GSTIN / GSTR keywords present.",
            )
        if "ITR-V" in upper_text or "INDIAN INCOME TAX RETURN" in upper_text or "ACKNOWLEDGEMENT NUMBER" in upper_text:
            return ClassificationResult(
                category="INCOME_TAX_RETURN",
                confidence_score=90,
                confidence=0.90,
                guess=None,
                reasoning="Heuristic match: Income Tax Return / ITR-V anchors present.",
            )
        if "PURCHASE ORDER" in upper_text or "P.O. NUMBER" in upper_text or "PO NO" in upper_text or "WORK ORDER" in upper_text:
            return ClassificationResult(
                category="PURCHASE_ORDER",
                confidence_score=90,
                confidence=0.90,
                guess=None,
                reasoning="Heuristic match: Purchase Order / Work Order headers present.",
            )
        if "TAX INVOICE" in upper_text or "COMMERCIAL INVOICE" in upper_text or "INVOICE NO" in upper_text:
            return ClassificationResult(
                category="TAX_INVOICE",
                confidence_score=90,
                confidence=0.90,
                guess=None,
                reasoning="Heuristic match: Tax Invoice / Commercial Invoice headers present.",
            )
        if "ACCOUNT STATEMENT" in upper_text or "IFSC CODE" in upper_text or "CLOSING BALANCE" in upper_text or "TRANSACTION DETAILS" in upper_text:
            return ClassificationResult(
                category="BANK_STATEMENT",
                confidence_score=90,
                confidence=0.90,
                guess=None,
                reasoning="Heuristic match: Bank Account Statement anchors present.",
            )
        if "BALANCE SHEET" in upper_text or "PROFIT AND LOSS" in upper_text or "AUDITOR'S REPORT" in upper_text:
            return ClassificationResult(
                category="AUDITED_FINANCIALS",
                confidence_score=90,
                confidence=0.90,
                guess=None,
                reasoning="Heuristic match: Balance Sheet / Financial Statement headers present.",
            )
        if "UDYAM REGISTRATION" in upper_text or "MINISTRY OF MICRO, SMALL" in upper_text or "CERTIFICATE OF INCORPORATION" in upper_text:
            return ClassificationResult(
                category="BUSINESS_REGISTRATION",
                confidence_score=90,
                confidence=0.90,
                guess=None,
                reasoning="Heuristic match: Udyam / Incorporation registration anchors present.",
            )

        guess_val = self._guess_unknown_type(text)
        conf = 45 if guess_val != "Unclassified / Non-Banking Document" else 20
        return ClassificationResult(
            category="UNKNOWN",
            confidence_score=conf,
            guess=guess_val,
            confidence=round(conf / 100.0, 2),
            reasoning=f"Fallback triggered. Document could not be conclusively classified into banking taxonomy. ({error or 'No direct anchor match'})",
        )


classifier_service = LLMClassifierService()
