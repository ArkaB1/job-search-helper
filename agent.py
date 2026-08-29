#!/usr/bin/env python3
"""
LinkedIn Job Scraping & Multi-Agent Evaluation Pipeline
Extracts, hard-filters, and evaluates job posts using local Ollama LLMs.
"""

import os
import sys
import glob
import json
import time
import re
import sqlite3
import requests
import hashlib
import subprocess
from typing import Dict, Any, Tuple, Optional, List

# ------------------------------------------------------------------------------
# MULTI-AGENT & PATH CONFIGURATION
# ------------------------------------------------------------------------------
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"

EXTRACTOR_MODEL = "qwen2.5-coder:3b"
EVALUATOR_MODEL = "phi4-mini"
MODEL_KEEP_ALIVE = "10m"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DUMP_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "linkedin_dumps")
LOCAL_ALT_DIR = os.path.join(SCRIPT_DIR, "linkedin_dumps")
DB_PATH = os.path.join(SCRIPT_DIR, "jobs.db")
RULES_PATH = os.path.join(SCRIPT_DIR, "job_rules.txt")
VIEW_JOBS_PATH = os.path.join(SCRIPT_DIR, "view_jobs.py")

SESSION = requests.Session()


# ------------------------------------------------------------------------------
# RULES HANDLER
# ------------------------------------------------------------------------------
def load_job_rules() -> Dict[str, List[str]]:
    """Loads and parses rules from the text file."""
    default_rules = {
        "locations": [],
        "companies": [],
        "roles": [],
        "experience": [],
        "triggers": [],
        "anywhere_rejects": []
    }
    if not os.path.exists(RULES_PATH):
        return default_rules

    try:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        return parse_rules_text(content)
    except Exception as e:
        print(f"⚠️ Warning: Could not read {RULES_PATH}: {e}")
        return default_rules


def parse_rules_text(text: str) -> Dict[str, List[str]]:
    """Converts rule definitions into structured lists."""
    rules = {
        "locations": [],
        "companies": [],
        "roles": [],
        "experience": [],
        "triggers": [],
        "anywhere_rejects": []
    }
    current_section = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            continue

        items = [x.strip().lower() for x in line.split(",") if x.strip()]
        if current_section == "TARGET_LOCATIONS":
            rules["locations"].extend(items)
        elif current_section == "REJECT_COMPANIES":
            rules["companies"].extend(items)
        elif current_section == "REJECT_ROLES":
            rules["roles"].extend(items)
        elif current_section == "REJECT_EXPERIENCE_WORDS":
            rules["experience"].extend(items)
        elif current_section in ("REJECT_ANYWHERE", "REJECT_DESCRIPTION_WORDS"):
            rules["anywhere_rejects"].extend(items)
        elif current_section == "HIRING_TRIGGERS":
            rules["triggers"].extend(items)

    return rules


def is_definitely_a_job(text: str, rules: Dict[str, List[str]]) -> bool:
    """Checks if text contains hiring trigger phrases."""
    text_lower = text.lower()
    trigger_count = sum(1 for trigger in rules.get("triggers", []) if trigger in text_lower)
    return trigger_count >= 2


def apply_hard_filters(
        extracted_data: Dict[str, Any],
        email: str,
        phone: str,
        form: str,
        rules: Dict[str, List[str]],
        raw_text: str
) -> Tuple[bool, str]:
    """Applies strict deterministic rules before querying evaluator AI."""
    title = str(extracted_data.get("title", "")).lower()
    company = str(extracted_data.get("company", "")).lower()
    location = str(extracted_data.get("location", "")).lower()
    experience = str(extracted_data.get("experience", "")).lower()

    # 1. Non-Job Content Filter
    if extracted_data.get("is_actual_job_post") is False:
        if not is_definitely_a_job(raw_text, rules):
            return False, "Not an actual job posting (Career Advice/Course)."

    # 2. Restrictive Criteria
    if extracted_data.get("is_rejected") is True:
        return False, extracted_data.get("reject_reason", "AI Disqualified: Restrictive condition found.")

    # 3. Contact Info & Job Metadata Check
    has_valid_metadata = (
            title not in ["n/a", "unknown", ""]
            and company not in ["n/a", "unknown", ""]
    )
    if email == "N/A" and phone == "N/A" and form == "N/A" and not has_valid_metadata:
        return False, "Missing contact info and essential job details."

    # 4. Blacklisted Companies
    for bad_comp in rules.get("companies", []):
        if bad_comp in company:
            return False, f"Rejected Company: {bad_comp}"

    # 5. Blacklisted Roles
    for bad_role in rules.get("roles", []):
        if re.search(r'\b' + re.escape(bad_role) + r'\b', title):
            return False, f"Rejected Role Keyword: {bad_role}"

    # 6. Rejected Experience Keywords
    for bad_exp in rules.get("experience", []):
        if bad_exp in experience or bad_exp in title:
            return False, f"Rejected Experience Level: {bad_exp}"

    # 7. Disallowed Text Tokens
    raw_text_clean = re.sub(r'\s+', ' ', raw_text.lower())
    for bad_word in rules.get("anywhere_rejects", []):
        if bad_word in raw_text_clean:
            return False, f"Rejected (Found restricted keyword): {bad_word}"

    # 8. Location Whitelist Check
    target_locs = [loc.strip() for loc in rules.get("locations", []) if loc.strip()]
    if target_locs and "*" not in target_locs:
        if not any(good_loc in location for good_loc in target_locs):
            return False, f"Rejected Location: '{extracted_data.get('location')}' outside target criteria."

    return True, "Passed hard filters"


# ------------------------------------------------------------------------------
# DATABASE OPS
# ------------------------------------------------------------------------------
def init_local_db() -> None:
    """Initializes the SQLite database with proper schema."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evaluated_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                company TEXT,
                location TEXT,
                stipend TEXT,
                contact_email TEXT,
                contact_phone TEXT,
                apply_form_link TEXT,
                experience TEXT,
                mba_required TEXT,
                responsibilities TEXT,
                link TEXT UNIQUE,
                url TEXT,
                match_score INTEGER,
                match_rating TEXT,
                verdict TEXT,
                reasoning TEXT,
                raw_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def save_local_job(data: Dict[str, Any]) -> str:
    """Inserts or skips a job post record in SQLite."""
    clean_link = data.get("link") or data.get("url") or "N/A"

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO evaluated_jobs 
                (title, company, location, stipend, contact_email, contact_phone, apply_form_link,
                 experience, mba_required, responsibilities, link, url, match_score, match_rating,
                 verdict, reasoning, raw_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("title", "N/A"),
                data.get("company", "N/A"),
                data.get("location", "N/A"),
                data.get("stipend", "N/A"),
                data.get("contact_email", "N/A"),
                data.get("contact_phone", "N/A"),
                data.get("apply_form_link", "N/A"),
                data.get("experience", "Fresher"),
                data.get("mba_required", "Yes"),
                data.get("responsibilities", "N/A"),
                clean_link,
                clean_link,
                data.get("match_score", 0),
                data.get("match_rating", "Low"),
                data.get("verdict", "Skip"),
                data.get("reasoning", "N/A"),
                data.get("raw_text", "")[:3000]
            ))
            conn.commit()
            return "SUCCESS" if cursor.rowcount > 0 else f"DUPLICATE_SKIPPED: {clean_link}"
    except Exception as e:
        return f"ERROR: {str(e)}"


# ------------------------------------------------------------------------------
# PARSERS & AI INFERENCE
# ------------------------------------------------------------------------------
def extract_contacts_and_links(text: str) -> Tuple[str, str, str]:
    """Extracts candidate emails, phone numbers, and job application URLs."""
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    phones = re.findall(r'(?:\+?91[\s-]*)?[6-9]\d{9}\b', text)

    form_links = re.findall(
        r'https?://(?:forms\.gle|docs\.google\.com|bit\.ly|tinyurl\.com|typeform\.com|lnkd\.in|careers\.|jobs\.|[\w-]+\.workday\.com|boards\.greenhouse\.io|jobs\.lever\.co|linkedin\.com/jobs|www\.linkedin\.com/jobs)[^\s<>"]+',
        text
    )

    clean_emails = list(dict.fromkeys(emails))
    clean_phones = list(dict.fromkeys([re.sub(r'\D', '', p) for p in phones]))
    clean_forms = list(dict.fromkeys(form_links))

    return (
        ", ".join(clean_emails) if clean_emails else "N/A",
        ", ".join(clean_phones) if clean_phones else "N/A",
        clean_forms[0] if clean_forms else "N/A"
    )


def query_ollama(model: str, prompt: str, temp: float = 0.1, num_predict: int = 500) -> Optional[Dict[str, Any]]:
    """Dispatches inference requests to local Ollama instance with robust parsing."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "keep_alive": MODEL_KEEP_ALIVE,
        "options": {"temperature": temp, "num_ctx": 2048, "num_predict": num_predict}
    }
    for _ in range(3):
        try:
            response = SESSION.post(OLLAMA_GENERATE_URL, json=payload, timeout=60)
            if response.status_code == 200:
                result_raw = response.json().get("response", "").strip()
                # Clean Markdown JSON tags if present
                clean_json_str = re.sub(r"^```json\s*|\s*```$", "", result_raw, flags=re.MULTILINE).strip()

                # Attempt direct load
                try:
                    return json.loads(clean_json_str)
                except json.JSONDecodeError:
                    # Fallback: Extract first valid JSON structure via regex
                    match = re.search(r'(\{.*\})', clean_json_str, re.DOTALL)
                    if match:
                        return json.loads(match.group(1))
        except Exception:
            time.sleep(1)
    return None


def unload_model(model_name: str) -> None:
    """Evicts the loaded model from VRAM/RAM."""
    try:
        SESSION.post(OLLAMA_GENERATE_URL, json={"model": model_name, "prompt": "", "keep_alive": 0}, timeout=10)
    except Exception:
        pass


def agent_extract_data(post_text: str) -> Optional[Dict[str, Any]]:
    """LLM Agent for structured entity extraction."""
    prompt = f"""You are a precise data parsing agent. Extract details from the LinkedIn post.
Do NOT cut off or summarize the responsibilities. Capture all of them.

FIRST, determine if this is an actual company hiring for a job/internship. 
If it is career advice, a course promotion, or interview tips, set "is_actual_job_post" to false.

SECOND, check if the job has strict disqualifiers:
- Exclusively for Female/Women candidates (e.g., "Female Only").
- Requires a "Service Agreement", "Bond", or "1-Year Contractual" commitment.
If ANY are present, set "is_rejected" to true and state the reason in "reject_reason" (otherwise false and "N/A").

LinkedIn Post:
\"\"\"{post_text[:2500]}\"\"\"

Respond ONLY with a valid JSON object matching this schema:
{{
    "is_actual_job_post": true,
    "is_rejected": false,
    "reject_reason": "N/A",
    "title": "Exact Role Title",
    "company": "Company Name if mentioned else Unknown",
    "location": "Location",
    "stipend": "CTC/Stipend/Salary if mentioned else N/A",
    "experience": "Experience requirements (e.g. Freshers / 0-2 Years)",
    "responsibilities": "Key responsibilities text."
}}
"""
    return query_ollama(EXTRACTOR_MODEL, prompt, temp=0.1, num_predict=600)


def agent_evaluate_fit(extracted_data: Dict[str, Any], raw_text: str) -> Optional[Dict[str, Any]]:
    """LLM Agent for candidate relevance scoring."""
    prompt = f"""Evaluate this job's fit for an MBA fresher looking for Operations & Marketing roles.

JOB TITLE: {extracted_data.get('title')}
LOCATION: {extracted_data.get('location')}
EXPERIENCE: {extracted_data.get('experience')}
STIPEND/SALARY: {extracted_data.get('stipend')}

Task: Evaluate if this job is an Operations, Marketing, Business Analysis, Management Trainee, Sales, or Business Development role.

SCORING RULES:
1. If YES (matches target roles): base score is 80.
2. If the post explicitly mentions "MBA", add +15 (Score = 95).
3. If it is an Internship (contains "intern" or "stipend"), set score to exactly 70.
4. If NO (does not match target roles), score 40 and output verdict "Skip".
5. Set verdict to "Apply" for any score >= 70.

Raw Text Snippet:
\"\"\"{raw_text[:2500]}\"\"\"

Respond ONLY with a valid JSON object in this format:
{{
    "match_score": 95,
    "verdict": "Apply"
}}
"""
    return query_ollama(EVALUATOR_MODEL, prompt, temp=0.1, num_predict=100)


# ------------------------------------------------------------------------------
# BATCH PROCESSING PIPELINE
# ------------------------------------------------------------------------------
def process_file_in_batches(file_path: str, user_rules: Dict[str, List[str]],
                            dashboard_proc: Optional[subprocess.Popen]) -> Optional[subprocess.Popen]:
    """Processes a JSON dump file through extraction, filtering, and evaluation."""
    print("\n" + "=" * 70)
    print(f"⚙️  BATCH PROCESSING: {os.path.basename(file_path)}")
    print("=" * 70)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            posts = json.load(f)
    except Exception as e:
        print(f"❌ Failed to parse JSON file {file_path}: {e}")
        return dashboard_proc

    valid_posts = [p for p in posts if len(p.get("text", "").strip()) >= 40]
    if not valid_posts:
        print("ℹ️ No valid posts found in file.")
        _mark_processed(file_path)
        return dashboard_proc

    extracted_results = []

    # Phase 1: Entity Extraction
    print(f"\n[PHASE 1] Extracting data from {len(valid_posts)} posts using [{EXTRACTOR_MODEL}]...")
    for idx, post in enumerate(valid_posts, 1):
        text = post.get("text", "").strip()
        print(f"   -> [{idx}/{len(valid_posts)}] Parsing post...")
        extracted_data = agent_extract_data(text)

        if not extracted_data:
            print(f"      ⚠️ Failed extraction for post {idx}")
            continue

        if extracted_data.get("is_actual_job_post") is False:
            print(f"      ⏭️  Skipped: Identified as Non-Job Content.")
            continue

        for key, value in extracted_data.items():
            if isinstance(value, list):
                extracted_data[key] = "\n• ".join([str(v) for v in value])
        extracted_results.append((post, extracted_data))

    unload_model(EXTRACTOR_MODEL)

    # Phase 2: Filtering & Scoring
    print(f"\n[PHASE 2] Filtering & Evaluating {len(extracted_results)} posts using [{EVALUATOR_MODEL}]...")
    saved_count = 0

    for idx, (post, extracted_data) in enumerate(extracted_results, 1):
        text = post.get("text", "").strip()
        url = post.get("url") or post.get("link") or "N/A"

        # Sanitize search or invalid URLs
        if "linkedin.com/search/" in url or url == "N/A":
            unique_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
            url = f"https://www.linkedin.com/post/placeholder-{unique_hash}"

        email, phone, form = extract_contacts_and_links(text)
        passed_hard_filters, reject_reason = apply_hard_filters(extracted_data, email, phone, form, user_rules, text)

        if not passed_hard_filters:
            evaluation_data = {"match_score": 0, "verdict": "Skip", "reasoning": reject_reason}
        else:
            evaluation_data = agent_evaluate_fit(extracted_data, text)
            if not evaluation_data:
                evaluation_data = {"match_score": 50, "verdict": "Skip", "reasoning": "Evaluator inference timed out."}
            else:
                evaluation_data["reasoning"] = "Passed all constraints. AI Recommended."

        final_data = {
            **extracted_data,
            **evaluation_data,
            "url": url,
            "link": url,
            "raw_text": text,
            "contact_email": email,
            "contact_phone": phone,
            "apply_form_link": form
        }

        db_result = save_local_job(final_data)
        score = final_data.get("match_score", 0)
        verdict = final_data.get("verdict", "Skip").upper()

        if verdict == "APPLY" or score >= 65:
            if "ERROR" in db_result:
                print(f"      ❌ DB ERROR: {db_result} | {final_data.get('title')}")
            elif "DUPLICATE" in db_result:
                print(f"      ⚠️ SKIPPED (Duplicate): {final_data.get('title')}")
            else:
                print(f"      ✅ [APPLY - {score}/100] {final_data.get('title')}")
                saved_count += 1
        else:
            print(f"      ❌ [SKIP] {final_data.get('title')} -> {final_data.get('reasoning')}")

    unload_model(EVALUATOR_MODEL)
    _mark_processed(file_path)

    print(f"\n🎉 Finished! Saved {saved_count} NEW job(s).")

    # Launch dashboard process once if not already running
    if os.path.exists(VIEW_JOBS_PATH):
        if dashboard_proc is None or dashboard_proc.poll() is not None:
            print("🌐 Starting Dashboard...")
            dashboard_proc = subprocess.Popen([sys.executable, VIEW_JOBS_PATH])

    return dashboard_proc


def _mark_processed(file_path: str) -> None:
    """Appends .processed suffix to the file to avoid re-reading."""
    try:
        os.rename(file_path, file_path + ".processed")
    except Exception as e:
        print(f"⚠️ Could not rename {file_path}: {e}")


def get_all_dump_files() -> List[str]:
    """Retrieves unprocessed JSON files sorted by modification time."""
    target_dirs = [DUMP_DIR, LOCAL_ALT_DIR]
    all_files = []
    for d in target_dirs:
        if os.path.exists(d):
            all_files.extend(glob.glob(os.path.join(d, "*.json")))

    unique_files = {}
    for f in all_files:
        if not f.endswith('.processed'):
            try:
                unique_files[os.path.realpath(f)] = f
            except Exception:
                pass

    sorted_files = list(unique_files.values())
    sorted_files.sort(key=os.path.getmtime)
    return sorted_files


# ------------------------------------------------------------------------------
# MAIN ENTRYPOINT
# ------------------------------------------------------------------------------
def main() -> None:
    init_local_db()
    print("=" * 70)
    print("  🤖 INTELLIGENT JOB INGESTION PIPELINE")
    print("=" * 70)

    dashboard_proc: Optional[subprocess.Popen] = None

    try:
        while True:
            # Hot-reload user rules each cycle
            user_rules = load_job_rules()
            dump_files = get_all_dump_files()

            if dump_files:
                for file_path in dump_files:
                    dashboard_proc = process_file_in_batches(file_path, user_rules, dashboard_proc)

            time.sleep(3)

    except KeyboardInterrupt:
        print("\n🛑 Pipeline shutdown requested. Cleaning up...")
        if dashboard_proc and dashboard_proc.poll() is None:
            dashboard_proc.terminate()
        sys.exit(0)


if __name__ == "__main__":
    main()