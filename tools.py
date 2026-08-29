"""
tools.py — Modular Tool Suite for ReAct AI Agent
"""

import json
import requests
from bs4 import BeautifulSoup
from googlesearch import search as google_search
from playwright.sync_api import sync_playwright
import db

# Tool Schemas for Gemini Function Calling
TOOLS = [
    {
        "name": "web_search",
        "description": "Fast lightweight Google search. Returns top search result URLs.",
        "input_schema": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "scrape_url",
        "description": "Fast HTTP GET extraction using BeautifulSoup for static web pages.",
        "input_schema": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "Target webpage URL"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "browser_search",
        "description": "Live Headed Chrome search directly on Google.",
        "input_schema": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "browse_and_extract",
        "description": "Playwright headed-browser renderer for dynamic job sites.",
        "input_schema": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "Target webpage URL"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "save_job",
        "description": "Saves a validated job listing matching criteria directly into SQLite database.",
        "input_schema": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "description": "Job title/role name"},
                "company": {"type": "STRING", "description": "Hiring company name"},
                "location": {"type": "STRING", "description": "Job location"},
                "stipend": {"type": "STRING", "description": "Stipend amount or salary terms"},
                "link": {"type": "STRING", "description": "Direct URL link to job posting"}
            },
            "required": ["title", "company", "location", "stipend", "link"]
        }
    }
]


# --- 1. LIGHTWEIGHT TOOLS ---

def web_search(query: str) -> str:
    """Executes lightweight google search using googlesearch-python."""
    results = []
    try:
        for url in google_search(query, num_results=5):
            results.append({"url": url})
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": f"Search failed: {str(e)}"})


def scrape_url(url: str) -> str:
    """Executes fast HTTP GET scrape using requests and BeautifulSoup."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        for element in soup(["script", "style"]):
            element.decompose()

        text = soup.get_text(separator=" ")
        clean_text = " ".join(text.split())
        return clean_text[:3000]
    except Exception as e:
        return f"Scrape failed for {url}: {str(e)}"


# --- 2. HEADED PLAYWRIGHT BROWSER TOOLS ---

def browser_search(query: str) -> str:
    """Executes Google search inside Playwright Chromium in headed mode."""
    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = context.new_page()

            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            page.goto(search_url, wait_until="domcontentloaded", timeout=15000)

            try:
                page.wait_for_selector("h3", timeout=5000)
            except Exception:
                pass

            # Target heading anchors directly to bypass dynamic Google CSS classes
            links = page.query_selector_all("a:has(h3)")

            seen_urls = set()
            for link in links:
                try:
                    url = link.get_attribute("href")
                    title_elem = link.query_selector("h3")
                    title = title_elem.inner_text().strip() if title_elem else ""

                    if url and title and url.startswith("http") and "google.com" not in url:
                        if url not in seen_urls:
                            seen_urls.add(url)
                            results.append({
                                "title": title,
                                "url": url,
                                "snippet": ""
                            })
                            if len(results) >= 5:
                                break
                except Exception:
                    continue

            browser.close()
            return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": f"Google search failed: {str(e)}"})


def browse_and_extract(url: str) -> str:
    """Visually navigates to a URL in headed Chromium and extracts rendered text."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            content = page.inner_text("body")
            browser.close()
            return content[:3000].strip()
    except Exception as e:
        return f"Extraction failed for {url}: {str(e)}"


# --- 3. TOOL ROUTER ---

# --- In tools.py ---


def run_tool(tool_name: str, tool_args: dict):
  """Router for function execution calls."""
  if tool_name == "web_search":
    return web_search(tool_args.get("query", ""))
  elif tool_name == "scrape_url":
    return scrape_url(tool_args.get("url", ""))
  elif tool_name == "browser_search":
    return browser_search(tool_args.get("query", ""))
  elif tool_name == "browse_and_extract":
    return browse_and_extract(tool_args.get("url", ""))
  elif tool_name == "save_job":
    # FIXED: Calling db.save_job instead of non-existent db.insert_job
    return db.save_job(
        title=tool_args.get("title"),
        company=tool_args.get("company"),
        location=tool_args.get("location"),
        stipend=tool_args.get("stipend"),
        url=tool_args.get("link") or tool_args.get("url"),
        skills=tool_args.get("skills", ""),
    )
  return f"Unknown tool: {tool_name}"