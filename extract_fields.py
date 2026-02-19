# extract_fields.py
import re

# legal endings to remove (case-insensitive)
_LEGAL_ENDINGS = [
    r'\bpvt\.?\s*ltd\.?\b',
    r'\bprivate\s+limited\b',
    r'\b(llc|inc|ltd|co\.?|corporation)\b'
]

_GENERIC_ABOUT_BLACKLIST = {
    "the", "this", "our", "role", "job", "position", "company", "profile", "team"
}

# NEW: hard blacklist for generic "About the job" headings
_ABOUT_GENERIC_PHRASES = {
    "about the job",
    "about this job",
    "about this role",
    "about the role",
    "about position",
    "about the position",
    "about opportunity",
}


def _strip_legal_suffixes(name: str) -> str:
    if not name:
        return name
    n = name.strip()
    for pat in _LEGAL_ENDINGS:
        n = re.sub(pat, '', n, flags=re.IGNORECASE).strip()
    n = re.sub(r'[\-\|,:;]+$', '', n).strip()
    return n


def _title_normalize(name: str) -> str:
    if not name:
        return "unknown"
    name = re.sub(r'\s+', ' ', name).strip()
    parts = []
    for w in name.split():
        if w.isupper() and len(w) <= 5:
            parts.append(w)
        else:
            parts.append(w.title())
    return " ".join(parts)


def _is_generic_about(match_text: str) -> bool:
    if not match_text:
        return False
    first = match_text.strip().split()[0].lower()
    return first in _GENERIC_ABOUT_BLACKLIST


def extract_company_name(text: str) -> str:
    """
    Heuristic extraction of company name.
    """
    if not text or not text.strip():
        return "unknown"

    # Normalize OCR garbage
    def clean(s):
        return re.sub(r'[^a-z0-9 ]+', '', s.lower())

    # Work line-by-line
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # -------------------------------------
    # 1) Try explicit Company: style
    # -------------------------------------
    for ln in lines:
        m = re.search(r'company\s*[:\-–]\s*(.+)', ln, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            candidate = _strip_legal_suffixes(candidate)
            candidate = _title_normalize(candidate)
            if candidate:
                return candidate

    # -------------------------------------
    # 2) "About <Company>" — FIXED ORDER HERE
    # -------------------------------------
    for ln in lines:
        ln_lower = ln.lower().strip()

        # STRONG SKIP BEFORE MATCHING
        clean_ln = re.sub(r'[^a-zA-Z0-9 ]+', ' ', ln_lower)
        clean_ln = re.sub(r'\s+', ' ', clean_ln).strip()

        if (
            clean_ln.startswith("about the job") or
            clean_ln.startswith("about job") or
            clean_ln.startswith("about this job") or
            clean_ln.startswith("about role") or
            clean_ln.startswith("about the role")
        ):
            continue

        if ln_lower in _ABOUT_GENERIC_PHRASES:
            continue

        # match only AFTER skipping invalid "About" lines
        m = re.match(r'about\s+(.+)', ln, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()

            cand_norm = clean(candidate)
            if (
                cand_norm.startswith("the job") or
                cand_norm.startswith("this job") or
                cand_norm.startswith("role")
            ):
                continue

            candidate = re.split(r'\.|,|-|:|\(|\n', candidate)[0].strip()
            candidate = _strip_legal_suffixes(candidate)
            candidate = _title_normalize(candidate)

            if candidate and candidate.lower() not in ("the job", "this role"):
                return candidate

    # -------------------------------------
    # 3) standalone title-cased lines
    # -------------------------------------
    for ln in lines:
        words = ln.split()
        if 1 <= len(words) <= 6:
            matches_title = all(re.match(r'^[A-Za-z0-9&\-\']+$', w) for w in words)
            if not matches_title:
                continue

            title_like_count = sum(1 for w in words if w[0].isupper() or w.isupper())
            if title_like_count >= 1:
                candidate = _strip_legal_suffixes(ln)
                candidate = _title_normalize(candidate)

                low = candidate.lower()
                if low in ("about the job", "job title", "about", "responsibilities", "role overview"):
                    continue

                if re.search(r'\b(is|are|provides|offers|requires|includes)\b', ln, re.IGNORECASE):
                    continue

                return candidate

    # -------------------------------------
    # 4) Look for "by <Company>"
    # -------------------------------------
    for ln in lines:
        m = re.search(r'\bby\s+([A-Z][A-Za-z0-9&\-\s]{2,100})', ln)
        if m:
            candidate = m.group(1).strip()
            candidate = _strip_legal_suffixes(candidate)
            candidate = _title_normalize(candidate)
            return candidate

    # -------------------------------------
    # 5) posted by / via
    # -------------------------------------
    for ln in lines:
        m = re.search(r'(posted\s+by|via)\s+([A-Z][A-Za-z0-9&\-\s]{2,60})', ln, re.IGNORECASE)
        if m:
            candidate = m.group(2).strip()
            candidate = _strip_legal_suffixes(candidate)
            candidate = _title_normalize(candidate)
            return candidate

    # -------------------------------------
    # Fallback: first TitleCase token sequence
    # -------------------------------------
    m = re.search(r'([A-Z][A-Za-z0-9&\-\']+(?:\s+[A-Z][A-Za-z0-9&\-\']+){0,4})', text)
    if m:
        candidate = m.group(1).strip()
        candidate = _strip_legal_suffixes(candidate)
        candidate = _title_normalize(candidate)
        return candidate

    return "unknown"


def extract_website(text: str) -> str:
    if not text:
        return "unknown"

    m = re.search(r'(https?://[^\s,)\]]+)', text, re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip('.,)').lower()

    m = re.search(r'(www\.[A-Za-z0-9\-\.]+\.[A-Za-z]{2,})', text, re.IGNORECASE)
    if m:
        return m.group(1).lower()

    m = re.search(r'([A-Za-z0-9\-]+\.(?:com|in|io|co|net|org|edu|gov|tech|ai)\b)', text, re.IGNORECASE)
    if m:
        return m.group(1).lower()

    return "unknown"


def extract_location(text: str) -> str:
    if not text:
        return "unknown"

    m = re.search(r'location\s*[:\-]\s*([A-Za-z0-9,\s\-()]+)', text, re.IGNORECASE)
    if m:
        loc = m.group(1).strip()
        low = loc.lower()
        if "remote" in low or "virtual" in low:
            return "Remote"
        if "hybrid" in low:
            return "unknown"
        return loc.strip()

    m = re.search(r'based in\s+([A-Za-z\s,]+)', text, re.IGNORECASE)
    if m:
        loc = m.group(1).strip()
        if "hybrid" in loc.lower():
            return "unknown"
        if "remote" in loc.lower() or "virtual" in loc.lower():
            return "Remote"
        return loc.strip()

    if re.search(r'\b(remote|virtual|work from home|wfh)\b', text, re.IGNORECASE):
        return "Remote"

    return "unknown"


# LOCAL TEST
if __name__ == "__main__":
    sample = """
    About the job
    Job Title: AI Intern
    Quik Hire
    Location: Remote
    """
    print("Company:", extract_company_name(sample))