# company_name_extractor.py
import os
import requests
import json
import re
from dotenv import load_dotenv

load_dotenv()

def _call_gemini_for_extraction(jd_text):
    """
    Call Gemini API to extract company name and website from JD text.
    Returns dict: {"company_name": str, "website": str}
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("ERROR: GEMINI_API_KEY not found in .env")
        return {"company_name": "unknown", "website": "unknown"}

    model = "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={gemini_key}"

    prompt = f"""Extract the company name and website from this job description.

Return ONLY a valid JSON object with two fields: "company_name" and "website"

Rules:
- If company name not found: use "unknown"
- If website not found: use "unknown"
- Remove legal suffixes (Pvt Ltd, LLC, Inc, Limited, Private Limited)
- Ignore generic names like "The Company", "Our Company", "This Organization"
- Return the standardized official company name (e.g., "Google" not "Google Inc")
- Company name should be title-cased
- Website should be lowercase with protocol if available

Job Description:
{jd_text[:800]}

JSON output only:"""

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    try:
        resp = requests.post(url, json=body, timeout=15)
        if resp.status_code != 200:
            print(f"ERROR: Gemini API returned status {resp.status_code}")
            print(f"Response: {resp.text}")
            return {"company_name": "unknown", "website": "unknown"}

        data = resp.json()
        
        try:
            response_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError) as e:
            print(f"ERROR: Unexpected Gemini response format - {e}")
            print(f"Full response: {data}")
            return {"company_name": "unknown", "website": "unknown"}

        # Clean the response
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*', '', response_text)
        response_text = response_text.strip()
        
        # Extract JSON object
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
        else:
            print(f"ERROR: Could not find JSON in response: {response_text}")
            return {"company_name": "unknown", "website": "unknown"}
        
        # Parse JSON
        result = json.loads(response_text)
        
        # Validate and clean results
        company_name = str(result.get("company_name", "unknown")).strip()
        website = str(result.get("website", "unknown")).strip()
        
        if not company_name or company_name.lower() in ["unknown", "", "none", "n/a", "null"]:
            company_name = "unknown"
        
        if not website or website.lower() in ["unknown", "", "none", "n/a", "null"]:
            website = "unknown"
        
        return {
            "company_name": company_name,
            "website": website
        }

    except json.JSONDecodeError as e:
        print(f"ERROR: JSON parse failed - {e}")
        print(f"Problematic response: {response_text}")
        return {"company_name": "unknown", "website": "unknown"}
            
    except Exception as e:
        print(f"ERROR: Gemini extraction failed - {e}")
        import traceback
        traceback.print_exc()
        return {"company_name": "unknown", "website": "unknown"}


def _extract_location_heuristic(jd_text):
    """
    Extract location from JD text and categorize as Remote/Hybrid/Onsite.
    Does NOT use Gemini API - uses pattern matching.
    
    Returns: "Remote", "Hybrid", or actual location string (Onsite)
    """
    if not jd_text or not isinstance(jd_text, str) or not jd_text.strip():
        return "unknown"
    
    text_lower = jd_text.lower()
    
    # Check for Remote indicators
    remote_patterns = [
        r'\bremote\b',
        r'\bwork from home\b',
        r'\bwfh\b',
        r'\bwork remotely\b',
        r'\bfully remote\b',
        r'\b100% remote\b',
        r'\bvirtual\b',
        r'\bonline work\b'
    ]
    
    for pattern in remote_patterns:
        if re.search(pattern, text_lower):
            return "Remote"
    
    # Check for Hybrid indicators
    hybrid_patterns = [
        r'\bhybrid\b',
        r'\bpart remote\b',
        r'\bpartially remote\b',
        r'\bflexible work\b',
        r'\bremote.*office\b',
        r'\boffice.*remote\b'
    ]
    
    for pattern in hybrid_patterns:
        if re.search(pattern, text_lower):
            return "Hybrid"
    
    # Try to extract specific location (Onsite)
    # Pattern 1: "Location: City, State"
    match = re.search(r'location\s*[:\-–]\s*([A-Za-z\s,\-()]+?)(?:\n|$|\.)', jd_text, re.IGNORECASE)
    if match:
        location = match.group(1).strip()
        # Clean up
        location = re.sub(r'\s+', ' ', location)
        if location and len(location) < 100:
            return location
    
    # Pattern 2: "Based in City"
    match = re.search(r'based\s+in\s+([A-Za-z\s,]+?)(?:\n|$|\.)', jd_text, re.IGNORECASE)
    if match:
        location = match.group(1).strip()
        location = re.sub(r'\s+', ' ', location)
        if location and len(location) < 100:
            return location
    
    # Pattern 3: Common city patterns
    city_pattern = r'\b(Mumbai|Bangalore|Delhi|Hyderabad|Chennai|Pune|Kolkata|Ahmedabad|' \
                   r'Gurgaon|Noida|Jaipur|New York|San Francisco|London|Singapore|' \
                   r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*,\s*([A-Z][A-Za-z\s]+)\b'
    
    match = re.search(city_pattern, jd_text)
    if match:
        return match.group(0).strip()
    
    # If no location found
    return "unknown"


def extract_company_info(jd_text):
    """
    Main function to extract company name, website, and location from JD.
    
    Args:
        jd_text (str): The job description text
    
    Returns:
        dict: {"company_name": str, "website": str, "location": str}
    """
    if not jd_text or not isinstance(jd_text, str) or not jd_text.strip():
        print("WARNING: Empty or invalid JD text provided")
        return {"company_name": "unknown", "website": "unknown", "location": "unknown"}
    
    # Extract company and website using Gemini
    gemini_result = _call_gemini_for_extraction(jd_text)
    
    # Extract location using heuristic (no Gemini)
    location = _extract_location_heuristic(jd_text)
    
    return {
        "company_name": gemini_result["company_name"],
        "website": gemini_result["website"],
        "location": location
    }