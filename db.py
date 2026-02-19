import os
from pymongo import MongoClient
from dotenv import load_dotenv
import certifi

load_dotenv()  # <-- REQUIRED

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise Exception("MONGO_URI is missing. Add it in your .env file.")

client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())


# choose database name
db = client["intern_guard"]

# choose collections
analysis_collection = db["analysis_logs"]
company_collection = db["company_stats"]


def test_connection():
    try:
        db.command("ping")
        return True
    except Exception as e:
        print("MongoDB Connection Error:", e)
        return False