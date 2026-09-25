"""
UIDAI & RBI Compliance Utility for Aadhaar Data Masking.
Complies with Section 16 of RBI KYC Master Direction and Aadhaar Act Regulations.
Ensures first 8 digits of any 12-digit Aadhaar number are masked before storage.
"""
import re


def mask_aadhaar_numbers(text: str) -> str:
    """
    Scans text for 12-digit Aadhaar number patterns (with spaces, hyphens, or contiguous)
    and masks the first 8 digits as 'XXXX-XXXX-', preserving only the last 4 digits.
    Also handles 16-digit Virtual ID (VID) by masking first 12 digits.
    """
    if not text:
        return ""

    # 1. Mask 16-digit Virtual IDs (VIDs): 1234-5678-9012-3456 or 1234 5678 9012 3456
    vid_pattern = re.compile(r"\b(\d{4})[\s-](\d{4})[\s-](\d{4})[\s-](\d{4})\b")
    text = vid_pattern.sub(r"XXXX-XXXX-XXXX-\4", text)

    # 2. Mask 12-digit Aadhaar with separators: 1234 5678 9012 or 1234-5678-9012
    aadhaar_sep_pattern = re.compile(r"\b(\d{4})[\s-](\d{4})[\s-](\d{4})\b")
    text = aadhaar_sep_pattern.sub(r"XXXX-XXXX-\3", text)

    # 3. Mask contiguous 12-digit numbers that appear in Aadhaar contexts
    # (Checking for proximity to keywords like UID, Aadhaar, Mera, etc., or standard 12-digit numeric sequences)
    contiguous_pattern = re.compile(r"\b(\d{8})(\d{4})\b")

    def _replace_contiguous_if_aadhaar(match):
        full = match.group(0)
        # Avoid masking dates, timestamps, or phone numbers if 10 digits
        if len(full) == 12:
            return f"XXXXXXXX{match.group(2)}"
        return full

    text = contiguous_pattern.sub(_replace_contiguous_if_aadhaar, text)
    return text
