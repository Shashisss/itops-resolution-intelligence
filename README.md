---
title: ITOps Resolution Intelligence
emoji: 🧭
colorFrom: indigo
colorTo: blue
sdk: streamlit
app_file: app.py
pinned: false
---

# ITOps Resolution Intelligence — Streamlit POC

A directly-accessible Streamlit app demonstrating **Signal → Context → Reason → Recommend → Verify** on sample data. It self-seeds on first run — no setup steps.

*(The YAML block above is the Hugging Face Spaces config so this folder works as a Space out of the box. Harmless elsewhere.)*

## Deploy to a public URL (pick one)

### Option A — Hugging Face Spaces (no GitHub needed) ⭐ fastest
1. Sign in at https://huggingface.co → **New → Space**.
2. Name it, **SDK = Streamlit**, visibility Public → **Create**.
3. In the Space, open the **Files** tab → **Add file → Upload files** → upload:
   `app.py`, `engine.py`, `seed.py`, `requirements.txt`, `README.md` (this file).
4. It builds automatically; when done you get a public URL:
   `https://huggingface.co/spaces/<your-user>/<space-name>`
5. Open it — the demo loads and self-seeds.

### Option B — Streamlit Community Cloud (needs a GitHub repo)
1. Push this folder to a GitHub repo.
2. Go to https://share.streamlit.io → **New app** → pick the repo → **Main file: `app.py`** → **Deploy**.
3. You get a public URL like `https://<name>.streamlit.app`.

## What you'll see
- **The story** — Payments → Payment API → checkout-api → payments-db
- **Business impact** — Checkout success ↓ to ~90% (computed over the graph)
- **Likely cause / blockers** — recent change + DB metric breaches (RCA over the graph)
- **Recommended action** — risk-classed, **policy-governed** (human approval for production)
- **Similar past incidents** — retrieval
- **Act & verify** — apply the fix → KPI recovers → verified

## Local run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Files
| File | Purpose |
|---|---|
| `app.py` | Streamlit UI (entry point; self-seeds on first run) |
| `engine.py` | Graph reasoning, RCA, policy recommendation, retrieval |
| `seed.py` | Sample data (SQLite + DuckDB) |
| `requirements.txt` | Dependencies |
| `setup.sh` | One-command bootstrap for Cloud Shell / any Linux |
| `policy/policy.rego` | Reference OPA policy for policy-governed autonomy |
