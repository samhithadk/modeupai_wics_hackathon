# ModeUp AI

ModeUp AI is an AI-powered trend discovery platform that detects emerging topics **before they peak**, using cross-platform signals from search, news, and video data.

## What It Does
- Discovers rising topics globally (not keyword-only)
- Scores trends based on momentum, engagement, and platform diversity
- Sends real-time email alerts
- Interactive dashboard built with Streamlit

## Data Sources
- Google Trends (SerpAPI)
- Google News (SerpAPI)
- Google Search (related queries + organic titles)
- YouTube (videos + Shorts via SerpAPI)
- Anthropic Claude (topic extraction + category validation)

## Trend Scoring (0–100)
- Cross-platform presence
- Normalized engagement strength
- Growth velocity (last 6h vs 24h)
- Platform authority weighting

## Tech Stack
- Frontend: Streamlit
- Backend: Python
- ML / Scoring: scikit-learn + feature-based modeling
- APIs: SerpAPI, Twitter/X, Anthropic Claude
- Database: SQLite
- Notifications: Resend Email
- Scheduler: Python background scheduler

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
