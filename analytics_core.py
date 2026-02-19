# analytics_core.py
from db import company_collection

class AnalyticsCore:

    @staticmethod
    def compute_totals():
        """Compute global analytics across all companies."""
        companies = list(company_collection.find({}))

        total_real = sum(c.get("real_count", 0) for c in companies)
        total_fake = sum(c.get("fake_count", 0) for c in companies)
        total_analyses = total_real + total_fake

        fraud_percentage = (
            round((total_fake / total_analyses) * 100, 2) if total_analyses > 0 else 0
        )

        return {
            "total_analyses": total_analyses,
            "total_real": total_real,
            "total_fake": total_fake,
            "fraud_percentage": fraud_percentage
        }

    @staticmethod
    def compute_pie_chart():
        totals = AnalyticsCore.compute_totals()
        return {
            "labels": ["Legit", "Fake"],
            "values": [totals["total_real"], totals["total_fake"]]
        }

    @staticmethod
    def top_fraud_companies():
        companies = list(company_collection.find({}))
        frauds = [
            {
                "company_name": c.get("company_name", "unknown"),
                "fraud_percentage": c.get("fraud_percentage", 0),
                "total_analysis_count": c.get("total_analysis_count", 0)
            }
            for c in companies
            if c.get("fraud_percentage", 0) > 0
        ]

        frauds.sort(key=lambda x: x["fraud_percentage"], reverse=True)
        return frauds[:3]

    @staticmethod
    def remote_vs_onsite():
        companies = list(company_collection.find({}))

        remote = 0
        onsite = 0

        for c in companies:
            # Count all REAL and FAKE entries
            real_entries = c.get("real_internships", {}).get("entries", [])
            fake_entries = c.get("fake_internships", {}).get("entries", [])
            all_entries = real_entries + fake_entries

            for e in all_entries:
                loc = (e.get("location", "") or "").strip().lower()
                if loc == "remote":
                    remote += 1
                else:
                    onsite += 1

        return {"remote": remote, "onsite": onsite}

    @staticmethod
    def create_dashboard():
        return {
            "success": True,
            "totals": AnalyticsCore.compute_totals(),
            "pie_chart": AnalyticsCore.compute_pie_chart(),
            "top_fraud_companies": AnalyticsCore.top_fraud_companies(),
            "location_stats": AnalyticsCore.remote_vs_onsite(),
            "patterns_placeholder": [],
            "recommendations_placeholder": []
        }