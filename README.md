# LinkedIn Job Automation & Tracker

Automated local pipeline that dumps raw LinkedIn job posts via a Chrome extension, filters disqualifiers, extracts structured data with local AI models, and generates an interactive HTML job dashboard.

---

## 🏗 System Architecture

```
[ LinkedIn Web Page ]
       │
       ▼ (Chrome Extension)
[ Raw JSON Dumps ] ────► (~/Downloads/linkedin_dumps/)
                               │
                               ▼ (agent.py Pipeline)
 ┌─────────────────────────────────────────────────────────┐
 │  1. Rule Engine: Location, Company, & Title Hard-Filter │
 │  2. Extractor Agent: Qwen2.5-Coder parses JSON details │
 │  3. Evaluator Agent: Phi-4 Mini scores Operations/Mktg  │
 └─────────────────────────────────────────────────────────┘
                               │
                               ▼
            [ SQLite DB (jobs.db) ] ──► [ HTML Dashboard ]

```

---

## 🧩 Components Overview

### 1. Chrome Extension (`linkedin-scraper`)

* **Purpose**: Extracts post text, post links, and recruiter details directly from active LinkedIn search feeds and post lists.
* **Functionality**:
* Runs on active browser tabs to capture raw LinkedIn feed payload.
* Filters out non-job content at the DOM layer where possible.
* Downloads structured JSON dump files into `~/Downloads/linkedin_dumps/`.



### 2. Python Core Engine (`agent.py`)

* **Directory Monitoring**: Continuously scans `~/Downloads/linkedin_dumps/` and local fallback folders for unparsed `.json` dumps.
* **Deterministic Rule Filtering**: Fast pre-filtering via `job_rules.txt` for:
* **Locations**: Target areas (e.g., Gurgaon, Delhi NCR, Remote).
* **Exclusions**: Blacklisted company names, irrelevant roles (HR, Tech Support, BPO), and high-seniority caps.
* **Contact & Card Validation**: Verifies native job card metadata or extracted email/phone/apply links.


* **Multi-Agent Local AI Processing (Ollama)**:
* **Extractor (`qwen2.5-coder:3b`)**: Extracts title, company, stipend, experience, responsibilities, and flags restrictive commitments (e.g., service bonds, exclusive constraints).
* **Evaluator (`phi4-mini`)**: Evaluates role alignment for Operations, Marketing, and Business Analytics entry-level positions, assigning a fit score (0–100) and recommendation verdict.


* **Database & Dashboard Storage**: Writes processed entries into `jobs.db` (`SQLite3`) and triggers `view_jobs.py` to compile the web UI dashboard (`job_tracker.html`).

---

## 🚀 Quick Start Guide

### Prerequisites

1. Install and launch [Ollama](https://ollama.com/).
2. Pull required local LLMs:
```bash
ollama pull qwen2.5-coder:3b
ollama pull phi4-mini

```


3. Install Python dependencies:
```bash
pip install requests

```



### Setup & Execution

1. **Load Chrome Extension**:
* Open `chrome://extensions/` in Google Chrome.
* Enable **Developer mode** (top-right toggle).
* Click **Load unpacked** and select the extension directory.


2. **Run Python Pipeline**:
```bash
python agent.py

```


3. **Scrape Jobs**: Trigger the extension on a LinkedIn search page. The Python script automatically ingests the downloaded dumps, processes them with Ollama, and opens your local job tracker dashboard upon completion.
