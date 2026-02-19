from flask import Flask, render_template, request, jsonify, send_file
import os

from dotenv import load_dotenv
import re
from db import company_collection   # already exists in db.py

# NEW: legit companies collection
from db import db
legit_companies_collection = db["legit_companies"]

load_dotenv()

from enhanced_prediction_utils import EnhancedFakeInternshipPredictor
from scraping_utils import extract_text_from_url, is_valid_url
import json
from datetime import datetime
import io
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors

# NEW IMPORTS FOR IMAGE EXTRACTION
from PIL import Image
import pytesseract
from io import BytesIO
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Test MongoDB connection
from db import test_connection
print("MongoDB Connected:", test_connection())

app = Flask(__name__)
app.secret_key = 'your-secret-key'

from chatbot import chatbot_bp
app.register_blueprint(chatbot_bp)


# ML model
predictor = EnhancedFakeInternshipPredictor()

# -----------------------------
#     HOME PAGE
# -----------------------------
@app.route('/')
def index():
    return render_template('index.html')


# ==============================
#     MAIN ML DETECTION
# ==============================
@app.route('/detect', methods=['POST'])
def detect_fraud():
    try:
        data = request.get_json()
        text = data.get("text", "").strip()
        source = data.get("source", "").strip().lower()

        if not text:
            return jsonify({"error": "No text provided"}), 400

        # ========================================
        # STEP 1: EXTRACT COMPANY INFO USING GEMINI + LOCATION HEURISTIC
        # ========================================
        from company_name_extractor import extract_company_info
        
        extracted_info = extract_company_info(text)
        company_name = extracted_info.get("company_name", "unknown")
        website = extracted_info.get("website", "unknown")
        location = extracted_info.get("location", "unknown")
        
        print(f"Extraction Results: company={company_name}, website={website}, location={location}")

        # ========================================
        # STEP 2: ML PREDICTION
        # ========================================
        result = predictor.enhanced_predict(text)
        
        confidence = result.get("confidence_score", 0)
        patterns = result.get("pattern_matches", [])
        
        # Normalize status to REAL / FAKE
        res_text = result.get("result", "")
        status = "REAL" if "REAL" in res_text.upper() else "FAKE"

        # ========================================
        # STEP 3: ADD TO LEGIT DB IF REAL
        # (Only if Gemini found a valid company name)
        # ========================================
        if status == "REAL" and company_name != "unknown":
            exists = legit_companies_collection.find_one(
                {"company_name": {"$regex": f"^{re.escape(company_name)}$", "$options": "i"}}
            )
            if not exists:
                legit_companies_collection.insert_one({"company_name": company_name})
                print(f"INFO: Added to legit_companies: {company_name}")

        # ========================================
        # STEP 4: UPDATE COMPANY STATS
        # (Skip image source)
        # ========================================
        if source != "image":
            from db_update import update_company_stats
            update_company_stats(
                company_name=company_name,
                website=website,
                location=location,
                result=status,
                confidence=confidence,
                patterns=patterns
            )

        # ========================================
        # STEP 5: RETURN RESULT
        # ========================================
        result["company_name"] = company_name
        result["website"] = website
        result["location"] = location
        
        return jsonify(result)

    except Exception as e:
        print(f"ERROR in /detect: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500



# -----------------------------
#        EXTRACT URL
# -----------------------------
@app.route('/extract_url', methods=['POST'])
def extract_url():
    try:
        data = request.get_json()
        url = data.get("url", "").strip()

        if not url:
            return jsonify({"error": "No URL provided"}), 400

        if not is_valid_url(url):
            return jsonify({"error": "Invalid URL"}), 400

        extracted_text = extract_text_from_url(url)
        if not extracted_text:
            return jsonify({"error": "Could not extract text"}), 400

        return jsonify({
            "success": True,
            "text": extracted_text,
            "word_count": len(extracted_text.split())
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# -----------------------------
#   IMAGE TEXT EXTRACTION
# -----------------------------
@app.route('/extract_image', methods=['POST'])
def extract_image():
    try:
        if 'image' not in request.files:
            return jsonify({"error": "No image file uploaded"}), 400

        file = request.files['image']
        if file.filename == '':
            return jsonify({"error": "Empty file"}), 400

        img_bytes = file.read()
        img = Image.open(BytesIO(img_bytes)).convert("RGB")

        try:
            extracted_text = pytesseract.image_to_string(img)
        except Exception as e:
            return jsonify({"error": f"Text extraction failed ({str(e)})"}), 500

        if not extracted_text.strip():
            return jsonify({"error": "No readable text found in image"}), 400

        return jsonify({
            "success": True,
            "text": extracted_text,
            "word_count": len(extracted_text.split())
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# -----------------------------
#     COMPANY SEARCH
# -----------------------------
@app.route('/search_company', methods=['POST'])
def search_company():
    try:
        data = request.get_json() or {}
        query = (data.get("company_name") or "").strip()

        if len(query) < 2:
            return jsonify({
                "success": True,
                "suggestions": [],
                "message": "Type at least 2 letters to search"
            })

        regex = {"$regex": re.escape(query), "$options": "i"}

        cursor = company_collection.find(
            {
                "$or": [
                    {"company_name": regex},
                    {"company_website": regex}
                ]
            },
            {
                "company_name": 1,
                "company_website": 1,
                "fraud_percentage": 1,
                "total_analysis_count": 1
            }
        ).limit(15)

        results = []
        for c in cursor:
            results.append({
                "company_name": c.get("company_name", "unknown"),
                "company_website": c.get("company_website", "unknown"),
                "fraud_percentage": float(c.get("fraud_percentage", 0.0)),
                "total_analysis_count": c.get("total_analysis_count", 0)
            })

        if not results:
            return jsonify({"success": True, "suggestions": []})

        if len(results) == 1:
            name = results[0]["company_name"]
            regex_exact = {"$regex": f"^{re.escape(name)}$", "$options": "i"}
            full = company_collection.find_one({"company_name": regex_exact})
            if full and "_id" in full:
                full["_id"] = str(full["_id"])
            return jsonify({"success": True, "company": full})

        suggestions = [r["company_name"] for r in results]
        return jsonify({"success": True, "suggestions": suggestions})

    except Exception as e:
        print("search_company ERROR:", e)
        return jsonify({"success": False, "error": str(e)}), 500



# -----------------------------------
#   FETCH FULL COMPANY DETAILS
# -----------------------------------
@app.route('/company_details', methods=['POST'])
def company_details():
    try:
        data = request.get_json() or {}
        name = (data.get("company_name") or "").strip()

        if not name:
            return jsonify({"success": False, "error": "No company_name provided"}), 400

        regex = {"$regex": f"^{re.escape(name)}$", "$options": "i"}
        doc = company_collection.find_one({"company_name": regex})

        if not doc:
            return jsonify({"success": False, "error": "Company not found in database"}), 404

        if "_id" in doc:
            doc["_id"] = str(doc["_id"])

        fraud_pct = float(doc.get("fraud_percentage", 0.0))
        trust_score = round(100 - fraud_pct, 2)

        company_obj = {
            "company_name": doc.get("company_name"),
            "company_website": doc.get("company_website", "unknown"),
            "total_analysis_count": doc.get("total_analysis_count", 0),
            "real_count": doc.get("real_count", 0),
            "fake_count": doc.get("fake_count", 0),
            "fraud_percentage": float(doc.get("fraud_percentage", 0.0)),
            "real_internships": doc.get("real_internships", {}),
            "fake_internships": doc.get("fake_internships", {})
        }

        return jsonify({"success": True, "company": company_obj})

    except Exception as e:
        print("company_details ERROR:", e)
        return jsonify({"success": False, "error": str(e)}), 500



# -----------------------------
#        EXPORT PDF
# -----------------------------
@app.route('/export_pdf', methods=['POST'])
def export_pdf():
    try:
        data = request.get_json()
        analysis = data.get("analysis_data", {})

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2563eb'),
            alignment=1
        )
        story.append(Paragraph("InternGuard Report", title_style))
        story.append(Spacer(1, 20))

        result_data = [
            ["Metric", "Value"],
            ["Result", analysis.get("result", "N/A")],
            ["Confidence", f"{analysis.get('confidence_score', 0)}%"],
            ["Words Analyzed", analysis.get("word_count", "0")],
            ["Suspicious Patterns", str(len(analysis.get("pattern_matches", [])))]
        ]

        table = Table(result_data, colWidths=[200, 250])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.blue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(table)
        story.append(Spacer(1, 20))

        if analysis.get("pattern_matches"):
            story.append(Paragraph("<b>Suspicious Patterns:</b>", styles["Heading3"]))
            for p in analysis["pattern_matches"]:
                story.append(Paragraph(f"- {p}", styles["Normal"]))

        doc.build(story)
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name="internguard_report.pdf"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# -----------------------------
#    ANALYTICS DASHBOARD
# -----------------------------
from analytics_core import AnalyticsCore

@app.route("/analytics")
def analytics_page():
    return render_template("analytics.html")

@app.route("/api/analytics/data")
def analytics_api():
    try:
        data = AnalyticsCore.create_dashboard()
        return jsonify(data)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# -----------------------------
#      RUN APP
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)