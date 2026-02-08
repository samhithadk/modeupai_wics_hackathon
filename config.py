import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")  # Optional
SERPAPI_KEY = os.getenv("SERPAPI_KEY")                    # REQUIRED
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")        # Optional but recommended
RESEND_API_KEY = os.getenv("RESEND_API_KEY")              # REQUIRED
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")

# Category baselines used for normalization + heuristics
ENGAGEMENT_BASELINES = {
    "stocks_finance": 250.0,
    "politics_news": 180.0,
    "fashion_trends": 120.0,
    "extreme_weather_environment": 160.0,
    "health_wellness": 130.0,
    "tech_ai": 220.0,
    "popular_culture": 200.0,
}

# Optional: how strict category validation should be
CATEGORY_VALIDATION_STRICT = True  # if True: Claude must say YES when available

# =========================
# Category configuration
# - keywords: used for google_trends + google_search + (fallback) news
# - news_terms: optional; if present, used for google_news queries
# - limits: per-category overrides for how much data to fetch
# =========================
CATEGORIES = {
    "stocks_finance": {
        "display_name": "Stock Market and Finance Trends",
        "keywords": [
            "earnings", "ipo", "options", "etf", "fed rates", "inflation",
            "recession", "jobs report", "cpi", "pce inflation", "interest rates", "bond yields",
            "s&p 500", "nasdaq", "dow jones", "treasury yields", "oil price",
            "bitcoin", "ethereum", "crypto regulation", "ai stocks"
        ],
        "news_terms": [
            "stock market", "earnings report", "federal reserve", "inflation report",
            "ipo filing", "bond yields", "market crash", "market rally"
        ],
        "limits": {
            "trends_keywords": 5,
            "rising_per_keyword": 18,
            "news_terms": 4,
            "news_articles_per_term": 12,
            "google_keywords": 3,
            "related_searches": 10,
            "organic_titles": 8,
            "twitter_max_results": 80
        }
    },

    "politics_news": {
        "display_name": "Politics / News",
        "keywords": [
            "election", "polls", "debate", "campaign", "congress", "senate", "house vote",
            "supreme court", "court ruling", "immigration", "border policy",
            "foreign policy", "geopolitics", "sanctions", "trade deal", "ceasefire",
            "government shutdown", "budget bill", "executive order", "breaking news"
        ],
        "news_terms": [
            "breaking news", "congress vote", "supreme court ruling", "election polls",
            "government shutdown", "foreign policy", "sanctions", "ceasefire"
        ],
        "limits": {
            "trends_keywords": 4,
            "rising_per_keyword": 15,
            "news_terms": 6,                 # politics benefits heavily from more news pulls
            "news_articles_per_term": 14,
            "google_keywords": 2,
            "related_searches": 10,
            "organic_titles": 10,
            "twitter_max_results": 90
        }
    },

    "fashion_trends": {
        "display_name": "Fashion Trends",
        "keywords": [
            "fashion week", "streetwear", "outfit ideas", "capsule wardrobe", "quiet luxury",
            "old money aesthetic", "coquette aesthetic", "clean girl aesthetic",
            "sneaker drop", "nike release", "adidas sambas", "bag trend",
            "skincare routine", "k-beauty", "makeup trend", "haircut trend",
            "summer outfits", "winter coats", "spring fashion", "menswear trend"
        ],
        "news_terms": [
            "fashion week", "designer collection", "streetwear trend", "beauty trend"
        ],
        "limits": {
            "trends_keywords": 5,
            "rising_per_keyword": 16,
            "news_terms": 3,
            "news_articles_per_term": 10,
            "google_keywords": 3,
            "related_searches": 12,
            "organic_titles": 8,
            "twitter_max_results": 70
        }
    },

    "extreme_weather_environment": {
        "display_name": "Extreme Weather & Environment",
        "keywords": [
            "hurricane", "tropical storm", "tornado", "severe weather", "storm warning",
            "wildfire", "smoke map", "air quality index", "heat wave", "extreme heat",
            "flash flood", "flood warning", "winter storm", "blizzard",
            "earthquake", "tsunami warning", "drought", "climate change", "el niño", "la niña"
        ],
        "news_terms": [
            "hurricane track", "tornado warning", "wildfire update", "air quality alert",
            "heat advisory", "flash flood warning", "winter storm warning", "earthquake update"
        ],
        "limits": {
            "trends_keywords": 4,
            "rising_per_keyword": 18,
            "news_terms": 6,                 # weather is very news-driven
            "news_articles_per_term": 15,
            "google_keywords": 2,
            "related_searches": 10,
            "organic_titles": 8,
            "twitter_max_results": 90
        }
    },

    "health_wellness": {
        "display_name": "Health and Wellness Trends (Diets, Workouts etc)",
        "keywords": [
            "workout routine", "gym workout", "pilates", "yoga", "running plan",
            "strength training", "hypertrophy", "zone 2 cardio", "hiit",
            "protein intake", "creatine", "pre workout", "supplements",
            "intermittent fasting", "keto diet", "high protein diet", "meal prep",
            "sleep optimization", "gut health", "cold plunge", "sauna benefits"
        ],
        "news_terms": [
            "fitness trend", "diet trend", "supplement trend", "wellness trend"
        ],
        "limits": {
            "trends_keywords": 5,
            "rising_per_keyword": 15,
            "news_terms": 3,
            "news_articles_per_term": 10,
            "google_keywords": 3,
            "related_searches": 12,
            "organic_titles": 8,
            "twitter_max_results": 70
        }
    },

    "tech_ai": {
        "display_name": "Technology and AI Trends",
        "keywords": [
            "openai", "anthropic", "chatgpt", "claude", "llm", "gpt",
            "ai agents", "rag", "vector database", "ai regulation",
            "nvidia gpu", "cuda", "data center", "chip shortage",
            "cybersecurity breach", "zero day", "apple", "google", "microsoft",
            "robotics", "humanoid robot"
        ],
        "news_terms": [
            "openai", "anthropic", "ai agents", "nvidia", "cybersecurity breach",
            "new ai model", "ai regulation", "data center"
        ],
        "limits": {
            "trends_keywords": 6,           # tech moves fast; let it pull more trends keywords
            "rising_per_keyword": 18,
            "news_terms": 4,
            "news_articles_per_term": 12,
            "google_keywords": 3,
            "related_searches": 12,
            "organic_titles": 10,
            "twitter_max_results": 90
        }
    },

    "popular_culture": {
        "display_name": "Popular Culture",
        "keywords": [
            "netflix", "box office",
            "new music", "album release", "tour dates", "billboard",
            "celebrity news", "relationship", "met gala",
            "gaming", "new game release", "steam top sellers",
            "anime", "manga", "kpop", "taylor swift", "drake", "beyonce",
            "memes", "viral video"
        ],
        "news_terms": [
            "movie trailer", "netflix new series", "album release", "tour dates",
            "celebrity news", "viral video"
        ],
        "limits": {
            "trends_keywords": 5,
            "rising_per_keyword": 16,
            "news_terms": 4,
            "news_articles_per_term": 12,
            "google_keywords": 3,
            "related_searches": 12,
            "organic_titles": 10,
            "twitter_max_results": 80
        }
    },
}


# =========================
# Default limits (fallbacks)
# Used if a category doesn't specify limits
# =========================
DEFAULT_LIMITS = {
    "trends_keywords": 4,
    "rising_per_keyword": 15,
    "news_terms": 3,
    "news_articles_per_term": 12,
    "google_keywords": 2,
    "related_searches": 10,
    "organic_titles": 8,
    "twitter_max_results": 80,
    "youtube_keywords": 3,
    "youtube_results": 12,

}


# ML Model Parameters
TREND_SCORE_THRESHOLD = 45
DATA_COLLECTION_INTERVAL_MINUTES = 30
LOOKBACK_HOURS = 24

# Alerting (anti-spam)
ALERT_MIN_TREND_SCORE = 65
ALERT_MIN_CONFIDENCE = 60

# Cooldowns
ALERT_TOPIC_COOLDOWN_HOURS = 24     # same topic to same user
ALERT_CATEGORY_COOLDOWN_HOURS = 6   # any email for same category to same user

# Email batching
ALERT_MAX_ITEMS_PER_EMAIL = 5       # include top N in one email

# ---- Prediction policy knobs (optional) ----
MIN_PLATFORMS_FOR_PREDICTION = 2
MIN_MENTIONS_FOR_TOPIC = 2
SINGLE_PLATFORM_MIN_SCORE = 75.0
TOP_N_PREDICTIONS_TO_SAVE = 10
