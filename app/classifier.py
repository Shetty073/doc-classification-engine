import json
import logging
import re
from typing import Dict, Any, Optional
import httpx
from app.config import settings
from app.schemas import ClassificationResult
from app.utils.entity_extractor import extract_key_entities

logger = logging.getLogger("classifier_service")

# Comprehensive Taxonomy of Indian Financial & Banking Documents (RBI & PMLA Compliant)
ALLOWED_CATEGORIES = [
    # 1. RBI KYC Officially Valid Documents (OVD)
    "PASSPORT",
    "DRIVING_LICENCE",
    "AADHAAR_CARD",
    "VOTER_ID",
    "NREGA_JOB_CARD",
    "NPR_LETTER",
    "PAN_CARD",
    # 2. RBI Deemed OVDs (Proof of Address under Rule 9 / Section 3(a)(vi))
    "UTILITY_BILL",
    "PROPERTY_TAX_RECEIPT",
    "PENSION_PAYMENT_ORDER",
    "EMPLOYER_ACCOMMODATION_LETTER",
    # 3. Retail Underwriting, Income & Employment Proofs
    "SALARY_SLIP",
    "FORM_16",
    "EPFO_PASSBOOK",
    # 4. Payment, Banking & Repayment Instruments
    "BANK_STATEMENT",
    "CANCELLED_CHEQUE",
    "NACH_MANDATE",
    "FD_RECEIPT",
    # 5. Bank / NBFC Issued Servicing Documents
    "SANCTION_LETTER",
    "LOAN_ACCOUNT_STATEMENT",
    "NO_DUE_CERTIFICATE",
    "DEMAND_PROMISSORY_NOTE",
    # 6. Trade, Commercial & Supply Chain Documents
    "GST_RETURN",
    "INCOME_TAX_RETURN",
    "PURCHASE_ORDER",
    "TAX_INVOICE",
    "AUDITED_FINANCIALS",
    "BILL_OF_LADING",
    "LETTER_OF_CREDIT",
    "STOCK_STATEMENT",
    # 7. Entity KYC & Corporate Constitution
    "BUSINESS_REGISTRATION",
    "MOA_AOA",
    "BOARD_RESOLUTION",
    "PARTNERSHIP_DEED",
    "TRUST_DEED",
    "SHAREHOLDING_PATTERN",
    # 8. Secured Lending & Collateral Property Documents
    "TITLE_DEED",
    "ENCUMBRANCE_CERTIFICATE",
    "PROPERTY_VALUATION_REPORT",
    "LEGAL_AUDIT_REPORT",
    # 9. Statutory Tax Declarations
    "FORM_60",
    # 10. Fallback
    "UNKNOWN",
]

TAXONOMY_DESCRIPTION = """
You are a Principal Document Intelligence Classifier for an Indian Bank / NBFC.
Classify the given document into EXACTLY ONE category from this comprehensive RBI/Banking list:

1. PASSPORT: Republic of India Passport, Passport No, Nationality Indian.
2. DRIVING_LICENCE: Union of India Driving Licence, State Licensing Authority/RTO, DL number, Form 7.
3. AADHAAR_CARD: UIDAI, Mera Aadhaar Meri Pehchan, 12-digit Aadhaar/VID number, e-Aadhaar.
4. VOTER_ID: Election Commission of India, EPIC Number, Elector's Name.
5. NREGA_JOB_CARD: MGNREGA Job Card, State Rural Development.
6. NPR_LETTER: National Population Register official letter.
7. PAN_CARD: Physical or electronic PAN card issued by Income Tax Department. MUST be the actual PAN card/slip itself, NOT another document (like Certificate of Incorporation, PO, Invoice, or Bank Statement) that merely quotes the organization's PAN number.
8. UTILITY_BILL: Electricity, Piped Gas, Water, Landline/Postpaid Telephone bill (Deemed OVD, Discom BESCOM, Tata Power, MSEDCL, etc.).
9. PROPERTY_TAX_RECEIPT: Municipal Corporation / Municipality property or municipal tax paid receipt.
10. PENSION_PAYMENT_ORDER: Pension or Family Pension Payment Order (PPO) issued to retired employees.
11. EMPLOYER_ACCOMMODATION_LETTER: Letter of allotment of accommodation from State/Central Govt, statutory body, PSU, or SCB.
12. SALARY_SLIP: Monthly Payslip, Salary Slip, Basic Pay, HRA, Deductions, Net Salary, Employee ID, Company Letterhead.
13. FORM_16: Certificate of Tax Deducted at Source (TDS) under Section 203 of IT Act (Part A TRACES or Part B).
14. EPFO_PASSBOOK: Employees' Provident Fund Organisation statement / UAN passbook.
15. BANK_STATEMENT: Bank Account Statement, IFSC, Account Number, Transaction History, Balance.
16. CANCELLED_CHEQUE: Cheque leaf with CANCELLED marked, Account Name, Number, IFSC / MICR code.
17. NACH_MANDATE: National Automated Clearing House / e-Mandate form signed for recurring EMI debit.
18. FD_RECEIPT: Fixed Deposit Receipt, Term Deposit Advice, Maturity Amount, Interest Rate.
19. SANCTION_LETTER: Loan Sanction Letter, In-principle Approval Letter, Credit Facility Offer from Bank/NBFC.
20. LOAN_ACCOUNT_STATEMENT: Statement of Loan Account, Amortization Schedule, Loan Repayment Schedule.
21. NO_DUE_CERTIFICATE: No Objection Certificate (NOC) / No Dues Certificate (NDC) issued by bank on loan closure.
22. DEMAND_PROMISSORY_NOTE: DPN executed promising unconditional loan repayment on demand.
23. GST_RETURN: ANY Goods and Services Tax document, Form GSTR-1, GSTR-3B, GSTR-9, GSTIN details.
24. INCOME_TAX_RETURN: Income Tax Return Acknowledgement, ITR-V, Assessment Year, Total Income.
25. PURCHASE_ORDER: Purchase Order, Work Order, PO Number, Order Date, Vendor line items.
26. TAX_INVOICE: Tax Invoice, Commercial Invoice, Bill of Supply, e-Invoice, IRN, HSN/SAC codes.
27. AUDITED_FINANCIALS: Balance Sheet, Profit & Loss Statement, Auditor's Report, Notes to Accounts, Form 3CA/3CB.
28. BILL_OF_LADING: Ocean Bill of Lading, Air Waybill (AWB), Lorry Receipt (LR) for goods transport.
29. LETTER_OF_CREDIT: Irrevocable Letter of Credit (LC), Bank Guarantee (BG), SWIFT MT700.
30. STOCK_STATEMENT: Monthly DP (Drawing Power) Stock & Book Debt statement submitted to banks.
31. BUSINESS_REGISTRATION: Certificate of Incorporation (CIN / MCA / Companies House / Registrar of Companies), Udyam / MSME Registration Certificate, Shop & Establishment Act license, GST Registration Certificate (REG-06).
32. MOA_AOA: Memorandum of Association and Articles of Association of a corporate borrower.
33. BOARD_RESOLUTION: Certified copy of Board Resolution authorizing credit facilities and signers (passed by Board of Directors, "RESOLVED THAT..."). NOT a Certificate of Incorporation.
34. PARTNERSHIP_DEED: Registered/Notarized Partnership Deed or LLP Agreement.
35. TRUST_DEED: Trust Deed, Society Registration Certificate, or Bye-laws for non-profits.
36. SHAREHOLDING_PATTERN: Beneficial ownership declaration, list of shareholders holding equity.
37. TITLE_DEED: Registered Sale Deed, Conveyance Deed, Gift Deed, Lease Deed with Sub-Registrar stamp.
38. ENCUMBRANCE_CERTIFICATE: Form 15/16 Encumbrance Certificate (EC) issued by Sub-Registrar.
39. PROPERTY_VALUATION_REPORT: Valuation certificate from Empanelled Valuer / Chartered Engineer.
40. LEGAL_AUDIT_REPORT: Title Search Report or Legal Opinion prepared by empanelled advocate.
41. FORM_60: Form 60 declaration under Rule 114B of IT Rules (filed when customer has no PAN).
42. UNKNOWN: Non-financial, non-banking, unrecognized, or illegible document.
"""

SYSTEM_PROMPT = f"""
{TAXONOMY_DESCRIPTION}

OUTPUT FORMAT RULES:
- Reply ONLY with a single JSON object.
- The "category" field MUST be one of the recognized categories or "UNKNOWN".
- A "Certificate of Incorporation" (whether issued by Registrar of Companies, MCA, Companies House, etc.) is BUSINESS_REGISTRATION. It is NEVER PAN_CARD, NEVER BOARD_RESOLUTION, and NEVER UNKNOWN.
- An "Udyam Registration Certificate" is BUSINESS_REGISTRATION.
- A "Memorandum of Association" or "Articles of Association" is MOA_AOA.
- Do NOT classify documents that mention a company's PAN or TAN number (such as Certificate of Incorporation, Purchase Order, Tax Invoice, Bank Statement) as PAN_CARD unless the document itself is a physical or electronic PAN Card issued by the Income Tax Department.
- Do NOT classify GST returns as BUSINESS_REGISTRATION; use GST_RETURN.
- Do NOT classify Work Orders as BUSINESS_REGISTRATION; use PURCHASE_ORDER.
- Do NOT classify Balance Sheets or Audit Reports as BUSINESS_REGISTRATION; use AUDITED_FINANCIALS.
- Do NOT classify Payslips as UNKNOWN; use SALARY_SLIP.
- Do NOT classify Electricity Bills as UNKNOWN; use UTILITY_BILL.
- Do NOT classify Cancelled Cheques as UNKNOWN; use CANCELLED_CHEQUE.
- CRITICAL FOR UNKNOWN: If the document does not fit any recognized banking category, set "category": "UNKNOWN", and provide a specific hypothesis in "guess" (e.g., "Academic Degree / Marksheet", "Medical Record / Hospital Bill", "Courier Receipt", "Personal Letter", etc.).
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
        and parses the structured classification response, enriching it with entity extraction.
        """
        if not ocr_text or len(ocr_text.strip()) < 10:
            logger.warning("OCR text is empty or too short. Defaulting to UNKNOWN.")
            return ClassificationResult(
                category="UNKNOWN",
                confidence_score=10,
                guess="Illegible / Blank Document",
                confidence=0.10,
                reasoning="Insufficient or no readable text extracted from document.",
                extracted_metadata={},
            )

        messages = self.build_prompt(ocr_text)
        payload: Dict[str, Any] = {
            "model": settings.LLAMA_MODEL_NAME,
            "messages": messages,
            "temperature": 0.05,
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
            
            # Enrich with deterministic entity extraction
            parsed_result.extracted_metadata = extract_key_entities(
                category=parsed_result.category,
                text=ocr_text,
                llm_metadata=parsed_result.extracted_metadata,
            )
            return parsed_result

        except httpx.RequestError as exc:
            logger.error("Network or connection error communicating with llama.cpp: %s", exc)
            fallback = self._heuristic_fallback(ocr_text, error=f"LLM server unreachable: {exc}")
            fallback.extracted_metadata = extract_key_entities(fallback.category, ocr_text)
            return fallback
        except Exception as exc:
            logger.error("Error during document classification: %s", exc, exc_info=True)
            fallback = self._heuristic_fallback(ocr_text, error=str(exc))
            fallback.extracted_metadata = extract_key_entities(fallback.category, ocr_text)
            return fallback

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

            # Rule reconciliation: Fix category discrepancies based on banking anchors
            if "GSTR" in sub_cat_str or "GSTR" in raw_upper or "GSTR-3B" in src_upper or "GSTR-1" in src_upper or "FORM GSTR" in src_upper:
                category = "GST_RETURN"
            elif "MEMORANDUM OF ASSOCIATION" in src_upper or "ARTICLES OF ASSOCIATION" in src_upper or "MOA & AOA" in sub_cat_str or "MOA" in sub_cat_str:
                category = "MOA_AOA"
            elif "CERTIFICATE OF INCORPORATION" in src_upper or "INCORPORATION" in sub_cat_str or "UDYAM" in sub_cat_str or "UDYAM REGISTRATION" in src_upper or "REGISTRAR OF COMPANIES" in src_upper or "MINISTRY OF CORPORATE AFFAIRS" in src_upper:
                category = "BUSINESS_REGISTRATION"
            elif "BALANCE SHEET" in sub_cat_str or "AUDITED" in sub_cat_str or "BALANCE SHEET" in src_upper or "AUDIT REPORT" in src_upper:
                category = "AUDITED_FINANCIALS"
            elif "WORK ORDER" in sub_cat_str or "PURCHASE ORDER" in sub_cat_str or "WORK ORDER" in src_upper or "PURCHASE ORDER" in src_upper:
                category = "PURCHASE_ORDER"
            elif "TAX INVOICE" in sub_cat_str or "TAX INVOICE" in src_upper or "COMMERCIAL INVOICE" in src_upper:
                category = "TAX_INVOICE"
            elif "PAYSLIP" in sub_cat_str or "SALARY SLIP" in src_upper or "PAY SLIP" in src_upper:
                category = "SALARY_SLIP"
            elif "ELECTRICITY" in src_upper or "DISCOM" in src_upper or "POWER DISTRIBUTION" in src_upper or "BESCOM" in src_upper or "MSEDCL" in src_upper:
                category = "UTILITY_BILL"
            elif "CANCELLED CHEQUE" in sub_cat_str or "CANCELLED CHEQUE" in src_upper or ("CHEQUE" in src_upper and "CANCELLED" in src_upper):
                category = "CANCELLED_CHEQUE"
            elif "FORM NO. 16" in src_upper or "FORM 16" in src_upper or "UNDER SECTION 203" in src_upper:
                category = "FORM_16"
            elif "AADHAAR" in sub_cat_str or "MERA AADHAAR" in src_upper or "UIDAI" in src_upper:
                category = "AADHAAR_CARD"
            elif "PERMANENT ACCOUNT NUMBER CARD" in src_upper or (
                "INCOME TAX DEPARTMENT" in src_upper
                and any(w in src_upper for w in ["FATHER", "DATE OF BIRTH", "SIGNATURE"])
                and "CERTIFICATE OF INCORPORATION" not in src_upper
                and "MINISTRY OF CORPORATE AFFAIRS" not in src_upper
            ):
                category = "PAN_CARD"
            elif "SANCTION" in sub_cat_str or "SANCTION LETTER" in src_upper:
                category = "SANCTION_LETTER"

            # Normalize non-taxonomy categories to UNKNOWN
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
                guess=guess if category == "UNKNOWN" else None,
                confidence=confidence_float,
                reasoning=reasoning,
                sub_category=sub_category,
                extracted_metadata={},
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
                extracted_metadata={},
            )

    def _guess_unknown_type(self, text: str) -> str:
        """Heuristically infers likely document type when outside recognized banking taxonomy."""
        upper = text.upper()
        if any(w in upper for w in ["CHASSIS", "REGISTRATION CERTIFICATE", "MOTOR VEHICLES", "INSURANCE POLICY", "POLICY NO"]):
            return "Vehicle Registration / Motor Insurance Document"
        if any(w in upper for w in ["MARKSHEET", "UNIVERSITY", "DEGREE", "SEMESTER", "ROLL NO", "EXAMINATION"]):
            return "Academic Degree / Educational Certificate"
        if any(w in upper for w in ["HOSPITAL", "DIAGNOSIS", "PATIENT", "PRESCRIPTION", "CLINIC", "RX"]):
            return "Medical Prescription / Health Record"
        if any(w in upper for w in ["COURIER", "CONSIGNMENT NO", "TRACKING ID", "AWB", "DISPATCHED"]):
            return "Courier Receipt / Postal Consignment"
        if any(w in upper for w in ["CURRICULUM VITAE", "RESUME", "WORK EXPERIENCE", "PROJECTS", "EDUCATION"]):
            return "Resume / Curriculum Vitae"
        return "Unclassified / Non-Banking Document"

    def _heuristic_fallback(self, text: str, error: Optional[str] = None) -> ClassificationResult:
        """
        Deterministic banking heuristics fallback in case llama.cpp is offline or busy.
        Ensures high availability for mission-critical banking pipelines.
        """
        upper_text = text.upper()

        # Corporate Constitution & Business Registration (Prioritized above PAN)
        if "MEMORANDUM OF ASSOCIATION" in upper_text or "ARTICLES OF ASSOCIATION" in upper_text:
            return ClassificationResult(category="MOA_AOA", confidence_score=92, confidence=0.92, reasoning="Memorandum / Articles of Association headers present.")
        if "CERTIFICATE OF INCORPORATION" in upper_text or "REGISTRAR OF COMPANIES" in upper_text or "MINISTRY OF CORPORATE AFFAIRS" in upper_text or "UDYAM REGISTRATION" in upper_text:
            return ClassificationResult(category="BUSINESS_REGISTRATION", confidence_score=95, confidence=0.95, reasoning="Certificate of Incorporation / Udyam registration anchors present.")

        # OVDs
        if "AADHAAR" in upper_text or "UIDAI" in upper_text or "MERA AADHAAR" in upper_text:
            return ClassificationResult(category="AADHAAR_CARD", confidence_score=92, confidence=0.92, reasoning="UIDAI / Aadhaar anchor terms present.")
        if "PERMANENT ACCOUNT NUMBER CARD" in upper_text or (
            "INCOME TAX DEPARTMENT" in upper_text
            and any(w in upper_text for w in ["FATHER", "DATE OF BIRTH", "DOB", "SIGNATURE"])
            and "CERTIFICATE OF INCORPORATION" not in upper_text
            and "MINISTRY OF CORPORATE AFFAIRS" not in upper_text
        ):
            return ClassificationResult(category="PAN_CARD", confidence_score=95, confidence=0.95, reasoning="Income Tax Department PAN Card anchors present.")
        if "ELECTION COMMISSION OF INDIA" in upper_text or ("IDENTITY CARD" in upper_text and "EPIC" in upper_text):
            return ClassificationResult(category="VOTER_ID", confidence_score=90, confidence=0.90, reasoning="Election Commission / EPIC anchors present.")
        if "DRIVING LICENCE" in upper_text or "UNION OF INDIA DRIVING LICENCE" in upper_text:
            return ClassificationResult(category="DRIVING_LICENCE", confidence_score=90, confidence=0.90, reasoning="Driving Licence keywords present.")
        if "PASSPORT" in upper_text and ("REPUBLIC OF INDIA" in upper_text or "INDIAN PASSPORT" in upper_text):
            return ClassificationResult(category="PASSPORT", confidence_score=95, confidence=0.95, reasoning="Republic of India Passport anchors present.")

        # Commercial & Lending
        if "GOODS AND SERVICES TAX" in upper_text or "GSTIN" in upper_text or "GSTR-3B" in upper_text or "GSTR-1" in upper_text or "FORM GSTR" in upper_text:
            return ClassificationResult(category="GST_RETURN", confidence_score=90, confidence=0.90, reasoning="Goods and Services Tax / GSTIN / GSTR keywords present.")
        if "ITR-V" in upper_text or "INDIAN INCOME TAX RETURN" in upper_text or "ACKNOWLEDGEMENT NUMBER" in upper_text:
            return ClassificationResult(category="INCOME_TAX_RETURN", confidence_score=90, confidence=0.90, reasoning="Income Tax Return / ITR-V anchors present.")
        if "FORM NO. 16" in upper_text or "FORM 16" in upper_text or "CERTIFICATE UNDER SECTION 203" in upper_text:
            return ClassificationResult(category="FORM_16", confidence_score=92, confidence=0.92, reasoning="Form 16 TDS certificate anchors present.")
        if "PAYSLIP" in upper_text or "SALARY SLIP" in upper_text or ("BASIC PAY" in upper_text and "NET PAY" in upper_text):
            return ClassificationResult(category="SALARY_SLIP", confidence_score=92, confidence=0.92, reasoning="Salary Slip / Payslip headers present.")
        if "PURCHASE ORDER" in upper_text or "P.O. NUMBER" in upper_text or "PO NO" in upper_text or "WORK ORDER" in upper_text:
            return ClassificationResult(category="PURCHASE_ORDER", confidence_score=90, confidence=0.90, reasoning="Purchase Order / Work Order headers present.")
        if "TAX INVOICE" in upper_text or "COMMERCIAL INVOICE" in upper_text or "INVOICE NO" in upper_text:
            return ClassificationResult(category="TAX_INVOICE", confidence_score=90, confidence=0.90, reasoning="Tax Invoice / Commercial Invoice headers present.")
        if "ACCOUNT STATEMENT" in upper_text or "IFSC CODE" in upper_text or ("CLOSING BALANCE" in upper_text and "TRANSACTION" in upper_text):
            return ClassificationResult(category="BANK_STATEMENT", confidence_score=90, confidence=0.90, reasoning="Bank Account Statement anchors present.")
        if "CANCELLED" in upper_text and ("CHEQUE" in upper_text or "BANK" in upper_text and "IFSC" in upper_text):
            return ClassificationResult(category="CANCELLED_CHEQUE", confidence_score=92, confidence=0.92, reasoning="Cancelled Cheque anchors present.")
        if "SANCTION LETTER" in upper_text or "CREDIT FACILITY SANCTION" in upper_text or "IN-PRINCIPLE APPROVAL" in upper_text:
            return ClassificationResult(category="SANCTION_LETTER", confidence_score=90, confidence=0.90, reasoning="Loan Sanction Letter anchors present.")
        if "BALANCE SHEET" in upper_text or "PROFIT AND LOSS" in upper_text or "AUDITOR'S REPORT" in upper_text or "AUDIT REPORT" in upper_text:
            return ClassificationResult(category="AUDITED_FINANCIALS", confidence_score=90, confidence=0.90, reasoning="Balance Sheet / Financial Statement headers present.")

        # Deemed OVDs
        if any(w in upper_text for w in ["ELECTRICITY BILL", "POWER DISTRIBUTION", "BESCOM", "TNEB", "DISCOM", "MSEDCL", "KWH", "METER READING", "CONSUMER NUMBER"]):
            return ClassificationResult(category="UTILITY_BILL", confidence_score=90, confidence=0.90, reasoning="Utility / Electricity bill anchors present.")

        # Fallback to UNKNOWN
        guess_val = self._guess_unknown_type(text)
        conf = 45 if guess_val != "Unclassified / Non-Banking Document" else 20
        return ClassificationResult(
            category="UNKNOWN",
            confidence_score=conf,
            guess=guess_val,
            confidence=round(conf / 100.0, 2),
            reasoning=f"Fallback triggered. Document could not be conclusively classified into banking taxonomy. ({error or 'No direct anchor match'})",
            extracted_metadata={},
        )


classifier_service = LLMClassifierService()
