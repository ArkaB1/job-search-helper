import json
import re
import ollama
from playwright.sync_api import sync_playwright
import db

# -----------------------------------------------------------------------------
# 1. CANDIDATE PROFILE SPECIFICATION
# -----------------------------------------------------------------------------
CANDIDATE_PROFILE = """
Candidate Background:
- Education: MBA (2025 Graduate) with Major in Operations and Minor in Marketing.
- Work Experience:
  1. Operations Executive at Teleforce (Process coordination, workflow tracking, ops execution).
  2. Marketing Executive at Numero Mobile (Campaign management, client communications, marketing execution).
  3. Valuation & Research at Research and India (Data analysis, financial valuation, market research).
- Preferred Roles: Operations Trainee/Intern, Marketing Analyst, Business Analyst, Product Marketing Manager Trainee.
- Preferred Locations: Gurgaon, Delhi, Noida, Greater Noida (Delhi-NCR).
- Stipend Rules:
  - Minimum acceptable stipend: Rs 11,000 / month.
  - Target stipend: Rs 15,000 / month.
  - Open to full-time roles if salary > Rs 20,000 / month.
"""

# -----------------------------------------------------------------------------
# 2. HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def parse_min_stipend(stipend_text: str) -> int:
    """Extracts lower-bound numerical stipend value from text."""
    numbers = re.findall(r'\d[\d,]*', stipend_text)
    if not numbers:
        return 0
    return int(numbers[0].replace(',', ''))


def scrape_page_text(url: str) -> str:
    """Launches Playwright in HEADED mode to capture visible body text."""
    with sync_playwright() as p:
        # Set headless=False and disable automation flags
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            no_viewport=True
        )
        page = context.new_page()

        # Mask navigator.webdriver
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)  # Brief delay to allow content to render visually

        raw_text = page.inner_text("body")
        cleaned_text = re.sub(r'\n\s*\n', '\n', raw_text).strip()
        browser.close()
        return cleaned_text

# -----------------------------------------------------------------------------
# 3. LOCAL LLM MATCHING & EXTRACTION ENGINE
# -----------------------------------------------------------------------------
def analyze_and_score_job(job_text: str, url: str) -> dict:
    """Uses Qwen 2.5 (3B) to extract job fields AND score match against candidate profile."""
    
    system_prompt = (
        "You are an expert HR recruiter and job evaluator. Extract structured job details and "
        "evaluate how well the role fits the candidate's profile. Return strictly valid JSON."
    )

    user_prompt = f"""
    Candidate Profile:
    {CANDIDATE_PROFILE}

    Job Posting Text:
    {job_text[:3500]}

    Extract the following details and perform profile evaluation:
    - title (string): Job or internship title
    - company (string): Hiring company name
    - location (string): Job location
    - stipend (string): Listed stipend or salary (e.g., 'Rs 15,000 / month')
    - skills (list of strings): Key required skills
    - fit_score (number): Match score from 0 to 100 based on candidate's Ops/Marketing/Valuation MBA background
    - fit_reasoning (string): Brief 1-2 sentence explanation of why this role is a good or poor match
    """

    try:
        response = ollama.chat(
            model='qwen2.5:3b',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            format='json'
        )
        data = json.loads(response['message']['content'])
        data['url'] = url
        return data
    except Exception as e:
        print(f"[X] AI Processing Error: {e}")
        return {}

# -----------------------------------------------------------------------------
# 4. AGENT EXECUTION
# -----------------------------------------------------------------------------
def run_targeted_search(target_urls: list):
    db.init_db()
    print("==================================================")
    print("      TARGETED GURGAON/DELHI-NCR JOB AGENT        ")
    print("==================================================")

    for url in target_urls:
        print(f"\n[*] Processing target page: {url}")
        
        try:
            page_text = scrape_page_text(url)
            print(f"[✔] Captured {len(page_text)} characters.")
        except Exception as e:
            print(f"[X] Failed to scrape {url}: {e}")
            continue

        analysis = analyze_and_score_job(page_text, url)
        if not analysis:
            continue

        stipend_str = analysis.get("stipend", "N/A")
        min_stipend = parse_min_stipend(stipend_str)
        fit_score = analysis.get("fit_score", 0)

        # Stipend Policy Evaluation
        if min_stipend > 0 and min_stipend < 11000:
            print(f"[⏩ SKIPPED] Stipend ({stipend_str}) is below your minimum ₹11,000 threshold.")
            continue

        print(f"\n--- Extracted Listing Details ---")
        print(f"• Title:    {analysis.get('title')}")
        print(f"• Company:  {analysis.get('company')}")
        print(f"• Location: {analysis.get('location')}")
        print(f"• Stipend:  {stipend_str}")
        print(f"• Match:    {fit_score}/100")
        print(f"• Reason:   {analysis.get('fit_reasoning')}")

        # Format skills string
        skills_raw = analysis.get("skills", [])
        skills_str = ", ".join(skills_raw) if isinstance(skills_raw, list) else str(skills_raw)

        # Save qualifying roles to SQLite
        res = db.save_job(
            title=analysis.get("title"),
            company=analysis.get("company"),
            location=analysis.get("location"),
            stipend=stipend_str,
            url=url,
            skills=f"Fit Score: {fit_score}/100 | Skills: {skills_str}"
        )
        print(f"[*] Database Status: {res}")


if __name__ == "__main__":
    # Test with URLs or search listings matching Gurgaon Operations/Marketing roles
    urls_to_scrape = [
        "https://internshala.com/internship/detail/strategy-operations-internship-in-gurgaon-at-meenadeep-experiences-private-limited1784538805",
        "https://internshala.com/internship/detail/inside-sales-internship-in-gurgaon-at-rpatech1785229948"
    ]
    
    run_targeted_search(urls_to_scrape)