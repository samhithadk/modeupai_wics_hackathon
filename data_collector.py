"""
data_collector.py

GLOBAL DISCOVERY → CLASSIFY → SAVE

Collects trend candidates globally (not per-category),
classifies each topic into one of your dashboard categories,
and saves categorized data points into SQLite.

Sources:
- Twitter/X (optional; requires TWITTER_BEARER_TOKEN)
- Google Trends via SerpAPI
- Google News via SerpAPI
- Google Search via SerpAPI
- YouTube via SerpAPI
- Topic extraction via Anthropic Claude (optional; heuristic fallback)
- Category classification via Anthropic Claude (optional; keyword fallback)

Important:
- We do NOT pass a forced category into collectors anymore.
- We discover broadly, then classify into category keys.
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import tweepy
from serpapi import GoogleSearch
import anthropic

import config
from database import save_data_point


# =========================
# Global discovery knobs
# =========================

# How much to pull per discovery "seed"
GLOBAL_TRENDS_SEEDS = 10
GLOBAL_TRENDS_RISING_PER_SEED = 20

GLOBAL_NEWS_SEEDS = 10
GLOBAL_NEWS_ARTICLES_PER_SEED = 12

GLOBAL_SEARCH_SEEDS = 8
GLOBAL_RELATED_SEARCHES_PER_SEED = 12
GLOBAL_ORGANIC_TITLES_PER_SEED = 10

GLOBAL_YOUTUBE_SEEDS = 8
GLOBAL_YOUTUBE_RESULTS_PER_SEED = 12

TWITTER_MAX_RESULTS = 80  # max 100 for v2 recent search

# Deduping / hygiene
TOPIC_MIN_LEN = 3
TOPIC_MAX_LEN = 80
DEDUP_CASEFOLD = True

# Claude models
CLAUDE_TOPIC_MODEL = "claude-haiku-4-5"
CLAUDE_CLASSIFY_MODEL = "claude-haiku-4-5"
CLAUDE_TOPIC_MAX_TOKENS = 50
CLAUDE_CLASSIFY_MAX_TOKENS = 20

# Caches (to save API calls)
_TOPIC_CACHE: Dict[str, str] = {}
_CLASSIFY_CACHE: Dict[str, str] = {}

# A low-bias set of *global* discovery seeds.
# These are intentionally broad so you aren’t only seeing what you pre-decided.
GLOBAL_DISCOVERY_SEEDS = [
    "today trending",
    "breaking news",
    "viral",
    "new release",
    "price surge",
    "outfit ideas",
    "workout routine",
    "AI news",
    "weather warning",
    "stock market",
    "election",
    "celebrity",
]


# =========================
# Helpers
# =========================

def _norm_key(s: str) -> str:
    s = (s or "").strip()
    return s.casefold() if DEDUP_CASEFOLD else s.lower()

def _is_valid_topic(topic: str) -> bool:
    if not topic:
        return False
    t = topic.strip()
    return TOPIC_MIN_LEN <= len(t) <= TOPIC_MAX_LEN

def _has_serpapi() -> bool:
    return bool(getattr(config, "SERPAPI_KEY", None))

def _has_claude() -> bool:
    return bool(getattr(config, "ANTHROPIC_API_KEY", None))

def _anthropic_client():
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

def init_twitter():
    if not getattr(config, "TWITTER_BEARER_TOKEN", None):
        return None
    return tweepy.Client(bearer_token=config.TWITTER_BEARER_TOKEN)

def parse_trend_value(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if s.lower() == "breakout":
        return 100.0

    s = s.replace("+", "").replace("%", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 100.0

def parse_youtube_views(views) -> float:
    if views is None:
        return 0.0
    if isinstance(views, (int, float)):
        return float(views)

    s = str(views).lower().replace("views", "").strip()
    s = s.replace(",", "")
    mult = 1.0
    if s.endswith("k"):
        mult = 1_000.0
        s = s[:-1]
    elif s.endswith("m"):
        mult = 1_000_000.0
        s = s[:-1]
    elif s.endswith("b"):
        mult = 1_000_000_000.0
        s = s[:-1]

    try:
        return float(s) * mult
    except ValueError:
        return 0.0

def extract_topic_from_text(text: str) -> str:
    """
    Extract a 2–5 word topic. Claude if available, else heuristic.
    Cached.
    """
    text = (text or "").strip()
    if not text:
        return ""

    if text in _TOPIC_CACHE:
        return _TOPIC_CACHE[text]

    def heuristic(s: str) -> str:
        s = re.sub(r"http\S+", "", s)
        s = re.sub(r"[^A-Za-z0-9\s\-\']", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return " ".join(s.split()[:4]) if s else ""

    if not _has_claude():
        topic = heuristic(text)
        _TOPIC_CACHE[text] = topic
        return topic

    try:
        client = _anthropic_client()
        msg = client.messages.create(
            model=CLAUDE_TOPIC_MODEL,
            max_tokens=CLAUDE_TOPIC_MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": (
                    "Extract the main topic/subject from this text in 2-5 words.\n"
                    "Be specific (e.g., 'Tesla stock crash' not just 'stocks').\n\n"
                    f"Text: {text[:250]}\n\n"
                    "Return ONLY the topic, nothing else."
                )
            }]
        )
        topic = (msg.content[0].text or "").strip()
    except Exception as e:
        print(f"Error extracting topic (Claude): {e}")
        topic = heuristic(text)

    _TOPIC_CACHE[text] = topic
    return topic


def classify_topic_to_category(topic: str, context: str = "") -> str:
    """
    Returns category key (one of config.CATEGORIES keys) or "unknown".
    Claude if available; otherwise keyword scoring fallback.
    Cached by topic string (and a tiny bit of context).
    """
    topic = (topic or "").strip()
    if not topic:
        return "unknown"

    cache_key = f"{topic}||{context[:80]}"
    if cache_key in _CLASSIFY_CACHE:
        return _CLASSIFY_CACHE[cache_key]

    # --- 1) Keyword-score fallback (fast + cheap) ---
    topic_l = (topic + " " + (context or "")).lower()
    best_cat = "unknown"
    best_score = 0

    for cat_key, cat_info in config.CATEGORIES.items():
        kws = cat_info.get("keywords", []) or []
        score = 0
        for kw in kws:
            kw_l = kw.lower()
            if kw_l and kw_l in topic_l:
                # longer matches matter more
                score += max(1, len(kw_l) // 5)
        if score > best_score:
            best_score = score
            best_cat = cat_key

    # If we don’t have Claude, use fallback decision
    if not _has_claude():
        out = best_cat if best_score > 0 else "unknown"
        _CLASSIFY_CACHE[cache_key] = out
        return out

    # --- 2) Claude classification (more accurate) ---
    # Give Claude the allowed keys so it can’t hallucinate categories
    cat_lines = []
    for k, v in config.CATEGORIES.items():
        cat_lines.append(f"- {k}: {v.get('display_name', k)}")
    cat_block = "\n".join(cat_lines)

    try:
        client = _anthropic_client()
        msg = client.messages.create(
            model=CLAUDE_CLASSIFY_MODEL,
            max_tokens=CLAUDE_CLASSIFY_MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": (
                    "You are a strict classifier.\n"
                    "Choose exactly ONE category key from the list below.\n"
                    "If none fit, return: unknown\n\n"
                    f"Categories:\n{cat_block}\n\n"
                    f"Topic: {topic}\n"
                    f"Context: {context[:200]}\n\n"
                    "Return ONLY the category key (e.g., tech_ai) or unknown."
                )
            }]
        )
        ans = (msg.content[0].text or "").strip()

        allowed = set(config.CATEGORIES.keys()) | {"unknown"}
        out = ans if ans in allowed else (best_cat if best_score > 0 else "unknown")

    except Exception as e:
        print(f"Category classification error: {e}")
        out = best_cat if best_score > 0 else "unknown"

    _CLASSIFY_CACHE[cache_key] = out
    return out


# =========================
# GLOBAL DISCOVERY COLLECTORS
# =========================

def collect_google_trends_global() -> List[dict]:
    if not _has_serpapi():
        print("SerpAPI not configured")
        return []

    items = []
    seen = set()

    for seed in GLOBAL_DISCOVERY_SEEDS[:GLOBAL_TRENDS_SEEDS]:
        try:
            params = {
                "engine": "google_trends",
                "q": seed,
                "data_type": "RELATED_QUERIES",
                "api_key": config.SERPAPI_KEY,
            }
            results = GoogleSearch(params).get_dict() or {}
            rising = (results.get("related_queries", {}) or {}).get("rising", []) or []

            for r in rising[:GLOBAL_TRENDS_RISING_PER_SEED]:
                q = (r.get("query") or "").strip()
                val = r.get("value", 0)
                if not q:
                    continue

                topic = q
                if not _is_valid_topic(topic):
                    continue

                k = _norm_key(topic)
                if k in seen:
                    continue
                seen.add(k)

                items.append({
                    "platform": "google_trends",
                    "topic": topic,
                    "content": topic,
                    "engagement": parse_trend_value(val),
                    "metadata": {"search_volume": str(val), "seed": seed}
                })
        except Exception as e:
            print(f"Google Trends global error (seed={seed}): {e}")

    print(f"Collected {len(items)} Google Trends (global)")
    return items


def collect_news_global() -> List[dict]:
    if not _has_serpapi():
        print("SerpAPI not configured")
        return []

    items = []
    seen = set()

    for seed in GLOBAL_DISCOVERY_SEEDS[:GLOBAL_NEWS_SEEDS]:
        try:
            params = {
                "engine": "google_news",
                "q": seed,
                "api_key": config.SERPAPI_KEY,
                "num": 20,
            }
            results = GoogleSearch(params).get_dict() or {}
            news_results = results.get("news_results", []) or []

            for a in news_results[:GLOBAL_NEWS_ARTICLES_PER_SEED]:
                title = (a.get("title") or "").strip()
                if not title:
                    continue

                source = (a.get("source") or {}).get("name", "Unknown")
                link = a.get("link", "")

                topic = extract_topic_from_text(title)
                if not _is_valid_topic(topic):
                    continue

                k = _norm_key(topic)
                if k in seen:
                    continue
                seen.add(k)

                source_weight = {
                    "Reuters": 95, "BBC": 95, "CNN": 90,
                    "Bloomberg": 90, "WSJ": 90, "The Wall Street Journal": 90,
                    "NYT": 85, "The New York Times": 85,
                    "AP News": 85, "Associated Press": 85,
                }.get(source, 60)

                items.append({
                    "platform": "news",
                    "topic": topic,
                    "content": title,
                    "engagement": float(source_weight),
                    "metadata": {"source": source, "link": link, "seed": seed}
                })

        except Exception as e:
            print(f"News global error (seed={seed}): {e}")

    print(f"Collected {len(items)} News (global)")
    return items


def collect_google_search_global() -> List[dict]:
    if not _has_serpapi():
        print("SerpAPI not configured")
        return []

    items = []
    seen = set()

    for seed in GLOBAL_DISCOVERY_SEEDS[:GLOBAL_SEARCH_SEEDS]:
        try:
            params = {
                "engine": "google",
                "q": seed,
                "api_key": config.SERPAPI_KEY,
                "num": 10,
            }
            results = GoogleSearch(params).get_dict() or {}

            # Related searches
            for rel in (results.get("related_searches") or [])[:GLOBAL_RELATED_SEARCHES_PER_SEED]:
                q = (rel.get("query") or "").strip()
                if not q:
                    continue
                topic = q
                if not _is_valid_topic(topic):
                    continue

                k = _norm_key(topic)
                if k in seen:
                    continue
                seen.add(k)

                items.append({
                    "platform": "google_search",
                    "topic": topic,
                    "content": topic,
                    "engagement": 75.0,
                    "metadata": {"type": "related_search", "seed": seed}
                })

            # Organic titles
            for r in (results.get("organic_results") or [])[:GLOBAL_ORGANIC_TITLES_PER_SEED]:
                title = (r.get("title") or "").strip()
                if not title:
                    continue

                topic = extract_topic_from_text(title)
                if not _is_valid_topic(topic):
                    continue

                k = _norm_key(topic)
                if k in seen:
                    continue
                seen.add(k)

                items.append({
                    "platform": "google_search",
                    "topic": topic,
                    "content": title,
                    "engagement": 80.0,
                    "metadata": {"type": "organic_title", "position": r.get("position", 0), "seed": seed}
                })

        except Exception as e:
            print(f"Google Search global error (seed={seed}): {e}")

    print(f"Collected {len(items)} Google Search (global)")
    return items


def collect_youtube_global() -> List[dict]:
    if not _has_serpapi():
        print("SerpAPI not configured")
        return []

    items = []
    seen = set()

    for seed in GLOBAL_DISCOVERY_SEEDS[:GLOBAL_YOUTUBE_SEEDS]:
        try:
            params = {
                "engine": "youtube",
                "search_query": seed,
                "api_key": config.SERPAPI_KEY,
                "hl": "en",
                "gl": "us",
            }
            results = GoogleSearch(params).get_dict() or {}
            videos = (results.get("video_results") or []) or []
            shorts = (results.get("shorts_results") or []) or []
            combined = (videos + shorts)[:GLOBAL_YOUTUBE_RESULTS_PER_SEED]

            for item in combined:
                title = (item.get("title") or "").strip()
                if not title:
                    continue

                channel = (item.get("channel") or {}).get("name") or item.get("channel_name") or "Unknown"
                link = item.get("link") or ""
                views_raw = item.get("views") or item.get("view_count") or 0

                topic = extract_topic_from_text(title)
                if not _is_valid_topic(topic):
                    continue

                k = _norm_key(topic)
                if k in seen:
                    continue
                seen.add(k)

                views = parse_youtube_views(views_raw)
                engagement = min(views / 10_000.0, 300.0)

                items.append({
                    "platform": "youtube",
                    "topic": topic,
                    "content": title,
                    "engagement": float(engagement),
                    "metadata": {
                        "seed": seed,
                        "channel": channel,
                        "views_raw": str(views_raw),
                        "views": views,
                        "link": link
                    }
                })

        except Exception as e:
            print(f"YouTube global error (seed={seed}): {e}")

    print(f"Collected {len(items)} YouTube (global)")
    return items


def collect_twitter_global() -> List[dict]:
    client = init_twitter()
    if not client:
        print("Twitter API not configured - skipping")
        return []

    items = []
    seen = set()

    try:
        # broad OR query
        query = " OR ".join([f'"{s}"' for s in GLOBAL_DISCOVERY_SEEDS[:10]])

        tweets = client.search_recent_tweets(
            query=query,
            max_results=min(TWITTER_MAX_RESULTS, 100),
            tweet_fields=["created_at", "public_metrics", "text"]
        )

        if tweets and tweets.data:
            for t in tweets.data:
                metrics = t.public_metrics or {}
                likes = int(metrics.get("like_count", 0))
                rts = int(metrics.get("retweet_count", 0))
                replies = int(metrics.get("reply_count", 0))
                engagement = likes + (2 * rts) + replies

                topic = extract_topic_from_text(t.text)
                if not _is_valid_topic(topic):
                    continue

                k = _norm_key(topic)
                if k in seen:
                    continue
                seen.add(k)

                items.append({
                    "platform": "twitter",
                    "topic": topic,
                    "content": t.text,
                    "engagement": float(engagement),
                    "metadata": {
                        "likes": likes, "retweets": rts, "replies": replies,
                        "created_at": str(t.created_at) if getattr(t, "created_at", None) else None
                    }
                })

    except Exception as e:
        print(f"Twitter global error: {e}")

    print(f"Collected {len(items)} Twitter (global)")
    return items


# =========================
# Orchestrator: GLOBAL → CLASSIFY → SAVE
# =========================

def collect_global_discovery_and_save():
    """
    1) Discover candidates globally
    2) Classify each candidate into a category key
    3) Save to DB with categorized category field
    """
    print("\n=== GLOBAL DISCOVERY ===")

    candidates = []
    candidates += collect_google_trends_global()
    candidates += collect_news_global()
    candidates += collect_google_search_global()
    candidates += collect_youtube_global()
    # optional
    candidates += collect_twitter_global()

    print(f"Discovered total candidates: {len(candidates)}")

    saved = 0
    skipped_unknown = 0

    for item in candidates:
        topic = item["topic"]
        content = item.get("content", "")
        platform = item["platform"]
        engagement = float(item.get("engagement", 0.0))
        metadata = item.get("metadata", {})

        category_key = classify_topic_to_category(topic, context=content)

        # You can keep unknown if you want, but for the demo this avoids nonsense categories.
        if category_key == "unknown":
            skipped_unknown += 1
            continue

        save_data_point(
            platform=platform,
            category=category_key,
            topic=topic,
            content=content,
            engagement_score=engagement,
            metadata={**metadata, "classified_at": datetime.utcnow().isoformat()}
        )
        saved += 1

    print(f"Saved categorized points: {saved} | Skipped unknown: {skipped_unknown}")
    return saved
