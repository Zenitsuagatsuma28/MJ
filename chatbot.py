# chatbot.py
import os
import re
import json
import math
import traceback
from flask import Blueprint, request, jsonify, current_app

# Import your existing db objects (db.py defines db and company_collection)
from db import db, company_collection

# Use requests for Gemini calls (simple, explicit)
import requests

# Blueprint
chatbot_bp = Blueprint('chatbot_bp', __name__, url_prefix='/chatbot')

# Small allowed general explanations (safe, no external info)
GENERAL_EXPLANATIONS = {
    "fraud_percentage": (
        "Fraud percentage is the share of analysed entries for a company that were "
        "flagged as fraudulent. It is computed as (fake_count / total_analysis_count) * 100."
    ),
    "confidence_scores": (
        "Confidence scores indicate how certain our analysis is for each detection. "
        "Higher values mean the classifier or rules flagged an item with more certainty."
    ),
    "what_is_pattern": (
        "A 'pattern' is a regex or rule used to detect suspicious text in internship postings "
        "(for example: a phrase promising payment for a certificate can be a red flag)."
    )
}

# Helper functions
def _safe_lower(s):
    return s.lower() if isinstance(s, str) else ""

def _normalize_company_name(name):
    return re.sub(r'\s+', ' ', _safe_lower(name).strip())

def _find_company_record(user_text):
    """
    Find a company record ONLY using data from company_collection.
    Returns a single record dict or None.
    """
    coll = company_collection

    # 1) Exact company_name match (case-insensitive)
    try:
        q = {"company_name": {"$regex": f"^{re.escape(user_text)}$", "$options": "i"}}
        rec = coll.find_one(q)
        if rec:
            return rec
    except Exception:
        # ignore and continue to fuzzy search
        pass

    # 2) Substring match across company_name values (safe: check types)
    try:
        names = coll.distinct("company_name")
    except Exception:
        names = []

    lower_text = _safe_lower(user_text)
    for name in names:
        if not isinstance(name, str):
            continue
        if _normalize_company_name(name) in lower_text:
            try:
                rec2 = coll.find_one({"company_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
            except Exception:
                rec2 = None
            if rec2:
                return rec2

    # 3) Website matching
    try:
        websites = coll.distinct("company_website")
    except Exception:
        websites = []
    for site in websites:
        if not isinstance(site, str):
            continue
        if site.lower() in lower_text:
            try:
                rec3 = coll.find_one({"company_website": site})
            except Exception:
                rec3 = None
            if rec3:
                return rec3

    return None

def _local_friendly_summary(record):
    """
    Produce a natural, plain-text, DB-only explanation (detailed, friendly).
    This is the guaranteed strict fallback if Gemini is not available.
    """
    company_name = record.get("company_name", "Unknown")
    website = record.get("company_website") or None
    total = int(record.get("total_analysis_count", 0) or 0)
    real = int(record.get("real_count", 0) or 0)
    fake = int(record.get("fake_count", 0) or 0)

    fraud_pct_raw = record.get("fraud_percentage")
    if fraud_pct_raw is None:
        fraud_pct = (fake / total * 100) if total > 0 else 0.0
    else:
        try:
            fraud_pct = float(fraud_pct_raw)
        except Exception:
            fraud_pct = 0.0

    fake_patterns = record.get("fake_internships", {}).get("pattern_matches", []) or []
    real_patterns = record.get("real_internships", {}).get("pattern_matches", []) or []

    # natural language construction
    lines = []
    # High-level sentence
    if fraud_pct >= 60:
        lines.append(f"{company_name} appears high-risk in our records.")
    elif fraud_pct >= 30:
        lines.append(f"{company_name} shows concerning indicators in our records.")
    elif fraud_pct > 0:
        lines.append(f"{company_name} has some flagged entries in our records.")
    else:
        lines.append(f"{company_name} looks legitimate in our records.")

    # add analysis summary
    if total > 0:
        lines.append(f"We analysed {total} posting{'s' if total!=1 else ''} linked to this company, "
                     f"of which {fake} were flagged as suspicious ({round(fraud_pct, 2)}% fraud rate).")
    else:
        lines.append("We have no analysis records for this company in our database.")

    # pattern explanation (natural)
    if fake_patterns:
        # describe patterns in natural language (do not leak raw regex)
        # convert known pattern keys into friendly phrases if possible
        pattern_phrases = []
        for p in fake_patterns:
            p_text = str(p)
            if "certificate" in p_text:
                pattern_phrases.append("certificate-payment cues (requests for payment for certificates)")
            elif "remote" in p_text or "virtual" in p_text:
                pattern_phrases.append("suspicious remote-internship phrasing")
            elif "payment" in p_text:
                pattern_phrases.append("requests for payment")
            else:
                # fallback: short sanitized pattern snippet
                sanitized = re.sub(r'[^a-zA-Z0-9 _-]', '', p_text)[:80]
                pattern_phrases.append(sanitized)
        if pattern_phrases:
            lines.append("We found indicators commonly associated with scams: " + ", ".join(pattern_phrases) + ".")
    else:
        lines.append("We did not detect suspicious pattern indicators in analysed postings.")

    # website if present
    if website:
        lines.append(f"Website on record: {website}")

    lines.append("Ask me to compare this company with another, or request a deeper breakdown.")
    return "\n".join(lines), {
        "company_name": company_name,
        "website": website,
        "total_analysis_count": total,
        "real_count": real,
        "fake_count": fake,
        "fraud_percentage": round(fraud_pct, 2),
        "fake_patterns": fake_patterns,
        "real_patterns": real_patterns
    }

def _format_db_docs_for_prompt(docs):
    """
    Create a compact JSON-safe representation of DB docs for passing to Gemini.
    Limit sizes to avoid huge payloads.
    """
    safe_docs = []
    for d in docs:
        # convert ObjectId if present
        try:
            if "_id" in d:
                d["_id"] = str(d["_id"])
        except Exception:
            pass
        # pick only relevant fields
        safe = {
            "company_name": d.get("company_name"),
            "company_website": d.get("company_website"),
            "total_analysis_count": int(d.get("total_analysis_count") or 0),
            "real_count": int(d.get("real_count") or 0),
            "fake_count": int(d.get("fake_count") or 0),
            "fraud_percentage": float(d.get("fraud_percentage") or 0.0),
            "real_internships": d.get("real_internships", {}),
            "fake_internships": d.get("fake_internships", {}),
            "confidence_scores": d.get("confidence_scores", {}),
            "timestamps": d.get("timestamps", {})
        }
        safe_docs.append(safe)
    return safe_docs

# Classifier: decide whether to use DB-first strict mode or free Gemini mode
def _is_db_query(user_text):
    t = _safe_lower(user_text)
    # keywords indicating company/fraud/domain-specific queries
    db_keywords = [
        "company", "companies", "fraud", "scam", "suspicious", "fake", "real",
        "internship", "internships", "pattern", "patterns", "compare", "compare with",
        "fraud percentage", "fraud%", "trust score", "trustscore", "website", "analysis",
        "analysed", "analysis", "fake_count", "real_count", "company_name", "search"
    ]
    # if contains a known short greeting question, it's not DB query
    greetings = ["hi", "hello", "how are you", "how r you", "how's it going", "what's up"]
    for g in greetings:
        if g in t:
            return False
    for kw in db_keywords:
        if kw in t:
            return True

    # number-based queries like "how many companies" or "companies with fraud above 30"
    if re.search(r'how many companies', t):
        return True
    if re.search(r'fraud (?:above|over|greater than|below|under|less than)\s*\d+', t):
        return True

    # default: not a DB query
    return False

def _call_gemini_api(prompt_text, short=True):
    """
    Correct Google AI Studio API call.
    Works with keys created from https://aistudio.google.com
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return None

    # Model names supported by AI Studio
    model = "gemini-2.5-flash"   # fastest, cheap
    url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={gemini_key}"

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt_text}
                ]
            }
        ]
    }

    try:
        resp = requests.post(url, json=body, timeout=18)
        if resp.status_code != 200:
            current_app.logger.warning("Gemini API status: %s - %s", resp.status_code, resp.text)
            return None

        data = resp.json()

        # Extract text from candidates
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except:
            return json.dumps(data)

    except Exception as e:
        current_app.logger.exception("Gemini call error: %s", e)
        return None

# Build strict prompt for DB mode
def _build_db_strict_prompt(user_question, docs):
    """
    Build a guarded prompt that instructs Gemini to ONLY use the provided DB JSON.
    The response is plain text, friendly and short (fast).
    """
    docs_json = json.dumps(docs, indent=2, default=str)
    prompt = (
        "You are InternGuard assistant. IMPORTANT: For questions about companies, internship fraud, "
        "patterns, analysis counts, or any company-specific facts, you MUST use ONLY the JSON data provided below. "
        "Do NOT use any external information or your own knowledge for company-specific facts. "
        "If the company asked about is NOT present in the provided JSON, respond EXACTLY with: "
        "\"This company is not present in our database.\" "
        "Do not hallucinate. Keep the reply friendly, concise (plain text), and useful. "
        "Explain patterns in natural language (for example: 'certificate-payment cues indicate requests for payment for certificates'). "
        "\n\nDATABASE RECORDS:\n"
        f"{docs_json}\n\n"
        "USER QUESTION:\n"
        f"{user_question}\n\n"
        "TASK: Answer in plain text, friendly tone. Use ONLY the database records above for any company-specific claims. "
        "If user asks a general question not about companies/fraud, you may say you can answer but do not invent DB facts. "
        "Keep the answer short and natural.\n"
    )
    return prompt

# Build general prompt for open mode (external knowledge allowed)
def _build_general_prompt(user_question):
    prompt = (
        "You are InternGuard assistant. You may use your general knowledge to answer non-company questions. "
        "If the user asks about companies or internship fraud and the user included database records, prefer them. "
        "Be friendly, concise (plain text), and helpful. Use simple sentences.\n\n"
        "USER QUESTION:\n"
        f"{user_question}\n\n"
        "Answer in plain text, friendly tone, short and direct.\n"
    )
    return prompt

# Additional DB-wide query implementations (count, filters)
def _handle_db_wide_queries(text_lower):
    # how many companies
    if re.search(r'\bhow many companies\b', text_lower):
        count = company_collection.count_documents({})
        return f"There are {count} companies in the database."

    # companies with fraud above/below number
    match = re.search(r'fraud (?:percentage )?(above|over|greater than|below|under|less than)\s+(\d+)', text_lower)
    if match:
        direction = match.group(1)
        value = float(match.group(2))
        if direction in ["above", "over", "greater than"]:
            query = {"fraud_percentage": {"$gt": value}}
        else:
            query = {"fraud_percentage": {"$lt": value}}
        docs = list(company_collection.find(query, {"company_name": 1, "fraud_percentage": 1}))
        formatted = [
            f"{d.get('company_name')} — {round(float(d.get('fraud_percentage', 0)), 2)}%"
            for d in docs if d.get("company_name") and d.get("fraud_percentage") is not None
        ]
        if not formatted:
            return "No companies match this condition."
        # sort by fraud desc for readability
        try:
            formatted_sorted = sorted(formatted, key=lambda s: float(s.split("—")[-1].strip().replace("%","")), reverse=True)
        except Exception:
            formatted_sorted = formatted
        return "Companies:\n" + "\n".join(formatted_sorted)

    # fake count above X
    match_fake = re.search(r'fake (?:count )?(above|over|greater than)\s+(\d+)', text_lower)
    if match_fake:
        value = int(match_fake.group(2))
        docs = list(company_collection.find({"fake_count": {"$gt": value}}, {"company_name": 1, "fake_count": 1}))
        formatted = [f"{d.get('company_name')} — fake_count: {d.get('fake_count',0)}" for d in docs if d.get("company_name")]
        if not formatted:
            return "No companies have fake_count above that number."
        return "\n".join(formatted)

    return None

@chatbot_bp.route('/api/query', methods=['POST'])
def api_query():
    """
    Main endpoint for chatbot queries.
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        user_text = payload.get("message", "")
        if not isinstance(user_text, str) or not user_text.strip():
            return jsonify({"reply": "Please send a non-empty message in the 'message' field.", "found": False}), 400

        text = user_text.strip()
        text_lower = _safe_lower(text)

        # 1) Small allowed canned general questions
        if re.search(r'\bfraud percentage\b', text_lower) or re.search(r'what does fraud percentage mean', text_lower):
            return jsonify({"reply": GENERAL_EXPLANATIONS["fraud_percentage"], "found": False, "strict": True})

        if re.search(r'\bconfidence score\b', text_lower) or re.search(r'what does confidence', text_lower):
            return jsonify({"reply": GENERAL_EXPLANATIONS["confidence_scores"], "found": False, "strict": True})

        if re.search(r'\bwhat is a pattern\b', text_lower) or re.search(r'what is pattern', text_lower):
            return jsonify({"reply": GENERAL_EXPLANATIONS["what_is_pattern"], "found": False, "strict": True})

        # 2) DB-wide quick queries (counts, filters)
        db_wide = _handle_db_wide_queries(text_lower)
        if db_wide is not None:
            return jsonify({"reply": db_wide, "found": True, "strict": True})

        # 3) Classify whether this is DB/company related
        is_db = _is_db_query(text)

        # 4) If DB query: try to find a company mention first
        if is_db:
            # Attempt to find a specific company record in the DB.
            rec = _find_company_record(text)
            if rec:
                # Build friendly local summary struct
                local_text, local_struct = _local_friendly_summary(rec)

                # Build safe docs for prompt (limit to 1 record)
                docs_for_prompt = _format_db_docs_for_prompt([rec])

                # Build strict prompt that forces DB-only facts for company-specific claims
                db_prompt = _build_db_strict_prompt(text, docs_for_prompt)

                # Call Gemini if configured (DB mode)
                gemini_reply = _call_gemini_api(db_prompt, short=True)

                if gemini_reply:
                    # ensure we do not return raw JSON; gemini_reply is expected plain text
                    return jsonify({"reply": gemini_reply, "found": True, "strict": True, "used_gemini": True, "record_summary": local_struct})
                else:
                    # Fallback: return local friendly summary (DB-only)
                    return jsonify({"reply": local_text, "found": True, "strict": True, "used_gemini": False, "record_summary": local_struct})
            else:
                # No company found in DB → strict required phrase
                return jsonify({"reply": "This company is not present in our database.", "found": False, "strict": True})

        # 5) Not a DB query => general open mode (Gemini allowed)
        general_prompt = _build_general_prompt(text)
        gemini_reply = _call_gemini_api(general_prompt, short=True)
        if gemini_reply:
            return jsonify({"reply": gemini_reply, "found": False, "strict": False, "used_gemini": True})
        else:
            # If Gemini not configured or failed, provide a friendly fallback
            fallback = (
                "I'm ready to help. I can answer general questions or look up companies in our database. "
                "Ask me about a company or say 'How many companies are in the database?'."
            )
            return jsonify({"reply": fallback, "found": False, "strict": False, "used_gemini": False})
    except Exception as e:
        # Log traceback to Flask logs for debugging
        current_app.logger.exception("chatbot api error: %s", e)
        # Return a safe, neutral error to the user
        return jsonify({"reply": "Server error. Please try again.", "found": False}), 500