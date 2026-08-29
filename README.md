# Job-search agent — starter skeleton

A minimal but real agent: Claude decides when to search the web, save a
job posting, look up saved jobs, or update an application's status.
You run the loop; nothing sends or applies anywhere automatically.

## Setup

```bash
cd job_agent
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here   # get one at console.anthropic.com
python agent.py
```

You'll be prompted for a goal. Try:

```
Find 5 recent product manager roles at fintech startups in India and save the best matches.
```

Then run it again with:

```
Show me the jobs you've saved so far.
```

Everything persists in `agent.db` (SQLite) between runs.

## How it's structured

- `db.py` — one generic `records` table (`record_type`, `data` JSON,
  `status`, `notes`). Same table works for job postings now, and later
  for anything else (fund profiles, contacts) if you fold the BD
  workflow back in — you'd just add new `record_type` values, not new
  tables.
- `tools.py` — the tool schemas Claude sees, plus the functions that
  actually run when it calls them. This is where you add capability.
- `agent.py` — the loop: send goal → Claude picks a tool or answers →
  run the tool → feed the result back → repeat.

## Natural next steps, in rough order

1. **Add `match_job_to_profile`** — a tool that takes a job description
   and your background/resume text, and returns a fit score + reasoning.
   This is where "general purpose but personalized" starts to show up.
2. **Add a resume/cover-letter draft tool** — same pattern as
   `save_job`, but returns text instead of writing to the DB.
3. **Add a review step** — right now `save_job` writes straight to the
   DB. Before you add anything that *sends* something externally
   (an email, an application), put a manual confirm step in between —
   don't let the agent auto-act on external systems.
4. **Swap the domain** — if you want to point this same skeleton at
   the distressed-fund/family-office workflow later, you'd add
   `record_type="fund_profile"` and a couple of new tools; `db.py` and
   the loop in `agent.py` don't need to change at all.

## Notes

- `web_search` here is Anthropic's hosted tool — Claude calls it and
  gets results back automatically, you don't implement it yourself.
- `max_turns=8` in `run_agent` just caps how many back-and-forths one
  goal can take before it stops — raise it if a goal needs more steps.
