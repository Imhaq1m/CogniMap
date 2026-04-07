"""
auto_test_level1.py — Automated Level 1 (Remember) test using the existing PDF.

This script:
1. Resets P01's progress
2. Logs in and gives consent
3. Uploads the existing PDF from uploads/
4. Extracts concepts
5. Validates definitions for each node
6. Generates and submits a quiz
7. Reports full audit log

Requires LM Studio to be running at http://localhost:1234 for real AI validation.

Run with: python auto_test_level1.py
"""
import requests
import sys
import time
from pathlib import Path

BASE_URL = "http://localhost:5000"
UPLOADS_DIR = Path(__file__).parent / "uploads"

# Find the first PDF in uploads/
PDF_FILES = list(UPLOADS_DIR.glob("*.pdf"))
if not PDF_FILES:
    print("❌ No PDF found in uploads/ directory")
    sys.exit(1)

PDF_FILE = PDF_FILES[0]


class TestSession:
    def __init__(self):
        self.session = requests.Session()
        self.participant_id = None
        self.participant_code = None

    def reset(self):
        """Reset participant progress."""
        resp = self.session.post(f"{BASE_URL}/api/reset")
        return resp.status_code == 200

    def login(self, code="P01"):
        """Log in as participant."""
        resp = self.session.post(f"{BASE_URL}/api/login", json={"code": code})
        data = resp.json()
        if resp.status_code != 200:
            print(f"❌ Login failed: {data.get('error')}")
            return False
        self.participant_id = data["participant_id"]
        self.participant_code = data["code"]
        return True

    def consent(self):
        """Give consent."""
        resp = self.session.post(f"{BASE_URL}/api/consent")
        return resp.status_code == 200

    def upload_pdf(self, pdf_path):
        """Upload PDF and extract concepts."""
        with open(pdf_path, "rb") as f:
            files = {"file": (pdf_path.name, f, "application/pdf")}
            resp = self.session.post(f"{BASE_URL}/api/pdf/upload", files=files, data={"layer": 1})
        return resp.json()

    def get_nodes(self):
        """Get all concept nodes."""
        resp = self.session.get(f"{BASE_URL}/api/graph?layer=1")
        return resp.json().get("nodes", [])

    def validate_definition(self, node_id, concept, definition):
        """Validate a definition."""
        resp = self.session.post(
            f"{BASE_URL}/api/level1/validate",
            json={"concept": concept, "definition": definition, "node_id": node_id}
        )
        return resp.json()

    def generate_quiz(self):
        """Generate Level 1 quiz."""
        resp = self.session.post(f"{BASE_URL}/api/level1/quiz/generate", json={})
        return resp.json()

    def submit_quiz(self, answers):
        """Submit quiz."""
        resp = self.session.post(f"{BASE_URL}/api/level1/quiz/submit", json={"answers": answers})
        return resp.json()

    def get_progress(self):
        """Get progress."""
        resp = self.session.get(f"{BASE_URL}/api/progress")
        return resp.json()

    def get_audit_logs(self):
        """Get audit logs."""
        resp = self.session.get(f"{BASE_URL}/api/audit-logs")
        return resp.json()

    def get_llm_logs(self):
        """Get LLM logs."""
        resp = self.session.get(f"{BASE_URL}/api/llm-logs")
        return resp.json()


def print_section(title):
    print(f"\n{'=' * 60}")
    print(title)
    print(f"{'=' * 60}")


def run_auto_test():
    ts = TestSession()

    print_section("🧠 CogniMap Level 1 Auto-Test")
    print(f"📄 PDF: {PDF_FILE.name}")
    print(f" API: {BASE_URL}")

    # Step 1: Reset
    print_section("[1] Resetting P01...")
    if ts.reset():
        print("✅ Progress cleared")
    else:
        print("⚠️ Reset failed (may not be logged in yet)")

    # Step 2: Login
    print_section("[2] Logging in...")
    if ts.login("P01"):
        print(f"✅ Logged in as P01 (ID: {ts.participant_id})")
    else:
        print("❌ Cannot continue without login")
        return

    # Step 3: Consent
    print_section("[3] Giving consent...")
    if ts.consent():
        print("✅ Consent recorded")
    else:
        print("⚠️ Consent may already be given")

    # Step 4: Upload PDF
    print_section(f"[4] Uploading PDF: {PDF_FILE.name}")
    upload_result = ts.upload_pdf(PDF_FILE)

    if "error" in upload_result:
        print(f"❌ Upload failed: {upload_result['error']}")
        return

    node_count = upload_result.get("count", 0)
    print(f"✅ Extracted {node_count} concepts")

    nodes = upload_result.get("nodes", [])
    for i, node in enumerate(nodes, 1):
        print(f"   {i}. {node['concept']} — {node['definition'][:70]}...")

    # Step 5: Validate definitions
    print_section("[5] Validating definitions...")
    verified_count = 0
    validation_results = []

    for node in nodes[:8]:  # Validate first 8 nodes
        # Use the extracted definition (from PDF) as the student's definition
        definition = node.get("definition", f"Definition of {node['concept']}")

        result = ts.validate_definition(node["id"], node["concept"], definition)

        status = "✅" if result.get("result") == "VALID" else "🔄"
        feedback = result.get("feedback", "")[:60]
        print(f"   {status} {node['concept']}: {result.get('result', 'ERROR')} — {feedback}")

        validation_results.append({
            "concept": node["concept"],
            "result": result.get("result"),
            "feedback": feedback
        })

        if result.get("result") == "VALID":
            verified_count += 1

    print(f"\n   Verified: {verified_count}/{len(nodes[:8])}")

    # Step 6: Check quiz availability
    print_section("[6] Checking quiz availability...")
    all_nodes = ts.get_nodes()
    verified_nodes = [n for n in all_nodes if n.get("verification_status") == "verified"]
    quiz_available = len(verified_nodes) >= 3

    print(f"   Total nodes: {len(all_nodes)}")
    print(f"   Verified nodes: {len(verified_nodes)}")
    print(f"   Quiz available: {'✅ Yes' if quiz_available else '❌ No (need 3+ verified)'}")

    # Step 7: Generate and submit quiz
    if quiz_available:
        print_section("[7] Generating quiz...")
        quiz = ts.generate_quiz()

        if "error" in quiz:
            print(f"❌ Quiz generation failed: {quiz['error']}")
        else:
            question_count = quiz.get("count", 0)
            print(f"✅ Generated {question_count} questions")

            # Mock submit with 80% correct
            print_section("[8] Submitting quiz...")
            answers = {}
            for i in range(question_count):
                answers[f"q{i+1}"] = {"is_correct": i < int(question_count * 0.8)}

            quiz_result = ts.submit_quiz(answers)
            score = quiz_result.get("score", 0)
            passed = quiz_result.get("passed", False)

            print(f"   Score: {score:.0f}% ({quiz_result.get('correct', 0)}/{quiz_result.get('total', 0)})")
            print(f"   Passed (≥80%): {'✅ Yes' if passed else '❌ No'}")

            if passed:
                print("   🎉 Level 2 unlocked!")
    else:
        print("\n⚠️ Skipping quiz — not enough verified nodes")

    # Step 9: Final progress
    print_section("[9] Final Progress")
    progress = ts.get_progress()
    level_names = {1: "Remember", 2: "Understand", 3: "Apply", 4: "Analyze", 5: "Evaluate", 6: "Create"}

    for level, status in progress.get("progress", {}).items():
        emoji = {"complete": "✅", "active": "▶️", "locked": "🔒"}.get(status, "?")
        name = level_names.get(int(level), "?")
        print(f"   {emoji} Level {level} ({name}): {status}")

    # Step 10: Audit log summary
    print_section("[10] Audit Log Summary")
    audit_logs = ts.get_audit_logs()

    if audit_logs:
        for log in audit_logs[-10:]:  # Last 10 actions
            timestamp = log.get("timestamp", "?")[:19]
            action = log.get("action", "?")
            details = log.get("details", "")
            if details and len(details) > 50:
                details = details[:50] + "..."
            print(f"   [{timestamp}] {action} {details}")
    else:
        print("   (No audit logs)")

    # Step 11: LLM response times
    print_section("[11] LLM Response Times")
    llm_logs = ts.get_llm_logs()

    if llm_logs:
        for log in llm_logs[-5:]:  # Last 5 LLM calls
            feature = log.get("feature", "?")
            response_time = log.get("response_time_ms", 0)
            speed = "⚡" if response_time < 5000 else ("🐌" if response_time > 10000 else "✓")
            print(f"   {speed} {feature}: {response_time}ms")

        avg_time = sum(l.get("response_time_ms", 0) for l in llm_logs) / len(llm_logs)
        print(f"\n   Average response time: {avg_time:.0f}ms")
    else:
        print("   (No LLM logs)")

    print_section("✅ Auto-Test Complete!")
    print("Open http://localhost:5000 and press Ctrl+Shift+D to view the audit log panel")


if __name__ == "__main__":
    try:
        # Test if API is running
        resp = requests.get(f"{BASE_URL}/api/session", timeout=3)
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to CogniMap API at http://localhost:5000")
        print("   Start the Flask app first: python app_flask.py")
        sys.exit(1)

    run_auto_test()
