# db_update.py
import re
from datetime import datetime
from collections import Counter, OrderedDict
from db import company_collection


def _standardize_company_name(name):
    """
    Standardize company name for deduplication.
    - Remove legal suffixes
    - Remove extra spaces
    - Title case
    - Remove special chars for comparison
    """
    if not name or not isinstance(name, str):
        return "unknown"
    
    name = name.strip()
    lower = name.lower()
    
    # Block generic invalid names
    invalid_names = [
        "company", "the company", "this company", "our company",
        "organization", "the organization", "firm", "the firm",
        "employer", "the employer", "hiring company", "a company", 
        "your company", "unknown", "n/a", "na"
    ]
    
    if lower in invalid_names:
        return "unknown"
    
    # Remove common legal suffixes
    legal_patterns = [
        r'\s+pvt\.?\s*ltd\.?$',
        r'\s+private\s+limited$',
        r'\s+llc$',
        r'\s+inc\.?$',
        r'\s+ltd\.?$',
        r'\s+co\.?$',
        r'\s+corporation$',
        r'\s+corp\.?$',
        r'\s+limited$'
    ]
    
    for pattern in legal_patterns:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE).strip()
    
    # Remove trailing punctuation
    name = re.sub(r'[\-\|,:;.]+$', '', name).strip()
    
    # Limit to first 4 words (avoid long sentences)
    parts = name.split()
    if len(parts) > 4:
        name = " ".join(parts[:4])
    
    # Title case
    name = name.title()
    
    # Final validation
    if not name or name.lower() in invalid_names:
        return "unknown"
    
    return name


def _normalize_for_matching(name):
    """
    Create a normalized version for fuzzy matching.
    Removes spaces, special chars, converts to lowercase.
    """
    if not name:
        return ""
    # Remove all non-alphanumeric characters and lowercase
    normalized = re.sub(r'[^a-z0-9]', '', name.lower())
    return normalized


def _find_existing_company(company_name):
    """
    Find existing company by:
    1. Exact case-insensitive match
    2. Fuzzy match (normalized comparison)
    
    Returns: (existing_doc, match_type) or (None, None)
    """
    if not company_name or company_name == "unknown":
        return None, None
    
    # 1. Try exact case-insensitive match
    regex = {"$regex": f"^{re.escape(company_name)}$", "$options": "i"}
    exact_match = company_collection.find_one({"company_name": regex})
    if exact_match:
        return exact_match, "exact"
    
    # 2. Try fuzzy match (normalized)
    normalized_input = _normalize_for_matching(company_name)
    if not normalized_input:
        return None, None
    
    # Get all companies and check normalized versions
    all_companies = company_collection.find({}, {"company_name": 1})
    
    for doc in all_companies:
        existing_name = doc.get("company_name", "")
        normalized_existing = _normalize_for_matching(existing_name)
        
        if normalized_existing == normalized_input:
            return doc, "fuzzy"
    
    return None, None


def _normalize_location(raw):
    """
    Normalize location string.
    Returns: "Remote", "Hybrid", actual location, or "unknown"
    """
    if not raw or not isinstance(raw, str):
        return "unknown"
    
    loc = raw.strip()
    loc_lower = loc.lower()
    
    # Already categorized
    if loc in ["Remote", "Hybrid"]:
        return loc
    
    # Check for remote indicators
    remote_keywords = ["remote", "virtual", "online", "work from home", "wfh"]
    if any(keyword in loc_lower for keyword in remote_keywords):
        return "Remote"
    
    # Check for hybrid
    if "hybrid" in loc_lower:
        return "Hybrid"
    
    # Return actual location (onsite)
    return loc


def _choose_company_website(real_entries):
    """
    Pick most frequent website from REAL internships, ignoring "unknown".
    If all are unknown, return "unknown".
    
    Args:
        real_entries: list of real internship entries
    
    Returns:
        str: most frequent valid website or "unknown"
    """
    # Extract all websites from real entries, excluding "unknown"
    websites = [
        e.get("website", "").strip()
        for e in real_entries
        if e.get("website") and str(e.get("website")).strip().lower() != "unknown"
    ]
    
    if not websites:
        return "unknown"
    
    # Count frequencies
    website_counts = Counter(websites)
    
    # Return most common
    most_common = website_counts.most_common(1)[0][0]
    return most_common


def update_company_stats(company_name, website, location, result, confidence, patterns):
    """
    Update company stats with deduplication and standardization.
    
    Args:
        company_name: extracted company name
        website: extracted website (can be unknown)
        location: extracted location (Remote/Hybrid/Onsite location/unknown)
        result: "REAL" or "FAKE"
        confidence: number 0–100
        patterns: list of pattern matches
    """
    try:
        # Standardize company name
        name_clean = _standardize_company_name(company_name)
        
        # Don't save if unknown
        if not name_clean or name_clean == "unknown":
            print(f"INFO: Skipping DB update - company name is unknown")
            return True
        
        # Normalize location and website
        loc_clean = _normalize_location(location)
        website_clean = (website or "unknown").strip()
        timestamp = datetime.utcnow().isoformat()
        
        # Create entry with website and location
        entry = {
            "website": website_clean,
            "location": loc_clean,
            "timestamp": timestamp,
            "confidence_score": confidence
        }
        
        # Find existing company (handles duplicates)
        existing, match_type = _find_existing_company(name_clean)
        
        if existing:
            print(f"INFO: Found existing company via {match_type} match: {existing.get('company_name')}")
            
            # Use existing document as base
            base_doc = OrderedDict()
            base_doc["company_name"] = existing.get("company_name", name_clean)  # Keep original name
            base_doc["company_website"] = existing.get("company_website", "unknown")
            base_doc["total_analysis_count"] = existing.get("total_analysis_count", 0)
            base_doc["real_count"] = existing.get("real_count", 0)
            base_doc["fake_count"] = existing.get("fake_count", 0)
            base_doc["fraud_percentage"] = existing.get("fraud_percentage", 0.0)
            base_doc["real_internships"] = existing.get("real_internships", {"pattern_matches": [], "entries": []})
            base_doc["fake_internships"] = existing.get("fake_internships", {"pattern_matches": [], "entries": []})
        else:
            print(f"INFO: Creating new company entry: {name_clean}")
            
            # Create new document
            base_doc = OrderedDict()
            base_doc["company_name"] = name_clean
            base_doc["company_website"] = "unknown"
            base_doc["total_analysis_count"] = 0
            base_doc["real_count"] = 0
            base_doc["fake_count"] = 0
            base_doc["fraud_percentage"] = 0.0
            base_doc["real_internships"] = {"pattern_matches": [], "entries": []}
            base_doc["fake_internships"] = {"pattern_matches": [], "entries": []}
        
        # Append entry based on REAL/FAKE
        if str(result).strip().upper().startswith("REAL"):
            base_doc["real_internships"]["entries"].append(entry)
            base_doc["real_count"] += 1
        else:
            base_doc["fake_internships"]["entries"].append(entry)
            base_doc["fake_count"] += 1
        
        base_doc["total_analysis_count"] = base_doc["real_count"] + base_doc["fake_count"]
        
        # Merge unique patterns
        if patterns:
            if str(result).strip().upper().startswith("REAL"):
                existing_set = set(base_doc["real_internships"].get("pattern_matches", []))
                for p in patterns:
                    if p not in existing_set:
                        base_doc["real_internships"]["pattern_matches"].append(p)
                        existing_set.add(p)
            else:
                existing_set = set(base_doc["fake_internships"].get("pattern_matches", []))
                for p in patterns:
                    if p not in existing_set:
                        base_doc["fake_internships"]["pattern_matches"].append(p)
                        existing_set.add(p)
        
        # Calculate company_website from most repeated website in real_internships entries
        chosen_site = _choose_company_website(base_doc["real_internships"].get("entries", []))
        base_doc["company_website"] = chosen_site
        
        # Calculate fraud percentage
        total = base_doc["total_analysis_count"]
        fake = base_doc["fake_count"]
        base_doc["fraud_percentage"] = round((fake / total) * 100, 2) if total else 0.0
        
        # Prepare final document
        ordered_doc = OrderedDict()
        if existing:
            ordered_doc["_id"] = existing["_id"]
        
        ordered_doc["company_name"] = base_doc["company_name"]
        ordered_doc["company_website"] = base_doc["company_website"]
        ordered_doc["total_analysis_count"] = base_doc["total_analysis_count"]
        ordered_doc["real_count"] = base_doc["real_count"]
        ordered_doc["fake_count"] = base_doc["fake_count"]
        ordered_doc["fraud_percentage"] = base_doc["fraud_percentage"]
        ordered_doc["real_internships"] = base_doc["real_internships"]
        ordered_doc["fake_internships"] = base_doc["fake_internships"]
        
        # Save to database
        if existing:
            company_collection.replace_one({"_id": existing["_id"]}, ordered_doc)
            print(f"SUCCESS: Updated existing company: {base_doc['company_name']}")
        else:
            company_collection.insert_one(ordered_doc)
            print(f"SUCCESS: Created new company: {base_doc['company_name']}")
        
        return True
    
    except Exception as e:
        print(f"ERROR in update_company_stats: {e}")
        import traceback
        traceback.print_exc()
        return False