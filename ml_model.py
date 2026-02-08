import re
import numpy as np
from sklearn.preprocessing import StandardScaler

from database import get_data_points, save_prediction
import config


# -----------------------
# Parsing / normalization
# -----------------------
def safe_parse_engagement(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if s.lower() == "breakout":
        return 100.0

    s = s.replace(",", "").replace("+", "")
    if s.endswith("%"):
        s = s[:-1]

    try:
        return float(s)
    except ValueError:
        return 0.0


def normalize_topic(s: str) -> str:
    """
    Normalize topics so near-duplicates collapse:
    - lowercase
    - remove punctuation
    - drop common junk tokens
    """
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\b(today|live|2024|2025|2026|news|stock|price|official|trailer)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# -----------------------
# Optional config helpers
# -----------------------
def _cfg(name: str, default):
    return getattr(config, name, default)


# Default policy knobs (work even if not in config.py)
MIN_PLATFORMS_DEFAULT = 2                    # require >=2 platforms normally
SINGLE_PLATFORM_HIGH_SCORE_DEFAULT = 75.0    # allow 1-platform only if score >= this
MIN_MENTIONS_DEFAULT = 2                     # require at least N datapoints per topic
TOP_N_SAVE_DEFAULT = 10                      # save top 10 per category


class TrendPredictor:
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.model_path = "models/trend_classifier.pkl"

    # -----------------------
    # Feature extraction
    # -----------------------
    def extract_features(self, topic, data_points, category):
        norm_topic = normalize_topic(topic)

        # match same normalized topic across sources
        topic_data = [dp for dp in data_points if normalize_topic(dp[1]) == norm_topic]
        if not topic_data:
            return None

        platforms = [dp[0] for dp in topic_data]
        unique_platforms = set(platforms)
        platform_count = len(unique_platforms)

        # Engagement normalization per category baseline
        raw_engagement = [safe_parse_engagement(dp[3]) for dp in topic_data]
        baseline = getattr(config, "ENGAGEMENT_BASELINES", {}).get(category, 150.0)
        engagement_scores = [e / max(baseline, 1.0) for e in raw_engagement]

        if not engagement_scores:
            return None

        avg_engagement = float(np.mean(engagement_scores))
        max_engagement = float(np.max(engagement_scores))
        total_mentions = len(topic_data)

        # Velocity: fraction of mentions in last 6 hours
        from datetime import datetime, timedelta
        now = datetime.now()
        six_hours_ago = now - timedelta(hours=6)

        recent_mentions = 0
        for dp in topic_data:
            try:
                ts = datetime.fromisoformat(dp[4])
                if ts > six_hours_ago:
                    recent_mentions += 1
            except Exception:
                continue

        velocity = recent_mentions / max(total_mentions, 1)

        # Platform weights: count occurrences with weights
        twitter_weight = sum(1 for p in platforms if p == "twitter") * 2.0
        news_weight = sum(1 for p in platforms if p == "news") * 2.5
        google_trends_weight = sum(1 for p in platforms if p == "google_trends") * 3.0
        google_search_weight = sum(1 for p in platforms if p == "google_search") * 1.5
        youtube_weight = sum(1 for p in platforms if p == "youtube") * 2.2

        # Key new feature: corroboration bonus
        # (topic appears on multiple distinct sources)
        corroboration = platform_count

        # Another useful feature: breadth of mentions (log-scaled so it won’t explode)
        mention_strength = float(np.log1p(total_mentions))  # 0..~3 for small counts

        return {
            "platform_count": platform_count,
            "avg_engagement": avg_engagement,
            "max_engagement": max_engagement,
            "total_mentions": total_mentions,
            "velocity": velocity,
            "twitter_weight": twitter_weight,
            "news_weight": news_weight,
            "google_trends_weight": google_trends_weight,
            "google_search_weight": google_search_weight,
            "youtube_weight": youtube_weight,
            "corroboration": corroboration,
            "mention_strength": mention_strength,
        }

    # -----------------------
    # Scoring (0-100)
    # -----------------------
    def calculate_trend_score(self, f):
        if not f:
            return 0.0

        score = 0.0

        # 1) Corroboration / platform diversity (big deal for “prediction” vibe)
        # 0..30 points
        # 1 platform = 8 pts, 2 platforms = 18 pts, 3+ platforms = up to 30
        score += min(8 + (f["platform_count"] - 1) * 10, 30)

        # 2) Engagement (normalized by category baseline) 0..25
        # avg/max are typically ~0.2 to 5.0+
        score += min(f["avg_engagement"] * 7.0, 12.5)
        score += min(f["max_engagement"] * 3.0, 12.5)

        # 3) Velocity (0..20)
        score += float(f["velocity"]) * 20.0

        # 4) Mention strength (0..10)
        score += min(f["mention_strength"] * 4.0, 10.0)

        # 5) Platform authority weights (0..15)
        platform_score = (
            min(f["news_weight"] / 20 * 6, 6) +
            min(f["google_trends_weight"] / 12 * 4, 4) +
            min(f["youtube_weight"] / 12 * 3, 3) +
            min(f["twitter_weight"] / 20 * 2, 2)
        )
        score += platform_score

        # Clamp
        return float(min(score, 100.0))

    # -----------------------
    # Confidence (0-100)
    # -----------------------
    def calculate_confidence(self, f):
        """
        Confidence should mean:
        - multiple platforms
        - enough mentions
        - not just a single random datapoint
        """
        if not f:
            return 0.0

        # Platform confidence (0..55)
        # 1 platform=20, 2=40, 3=50, 4+=55
        plat = min(20 + (f["platform_count"] - 1) * 20, 55)

        # Mention confidence (0..25)
        # 1 mention=5, 2=12, 3=18, 5+=25
        m = f["total_mentions"]
        if m <= 1:
            mention = 5
        elif m == 2:
            mention = 12
        elif m == 3:
            mention = 18
        elif m == 4:
            mention = 22
        else:
            mention = 25

        # Velocity confidence (0..20)
        vel = min(f["velocity"] * 20.0, 20.0)

        return float(min(plat + mention + vel, 100.0))

    # -----------------------
    # Filtering policy
    # -----------------------
    def passes_prediction_policy(self, f, score):
        """
        Enforce multi-platform corroboration:
        - default: require >=2 platforms
        - allow 1 platform only if score is VERY high
        - require min mentions overall
        """
        min_platforms = _cfg("MIN_PLATFORMS_FOR_PREDICTION", MIN_PLATFORMS_DEFAULT)
        min_mentions = _cfg("MIN_MENTIONS_FOR_TOPIC", MIN_MENTIONS_DEFAULT)
        single_platform_high = _cfg("SINGLE_PLATFORM_MIN_SCORE", SINGLE_PLATFORM_HIGH_SCORE_DEFAULT)

        if f["total_mentions"] < min_mentions:
            return False

        if f["platform_count"] >= min_platforms:
            return True

        # If single-platform, only allow if extremely strong (prevents junk)
        return (f["platform_count"] == 1) and (score >= single_platform_high)

    # -----------------------
    # Main per-category run
    # -----------------------
    def predict_trends(self, category):
        data_points = get_data_points(category, hours=config.LOOKBACK_HOURS)
        if not data_points:
            print(f"No data points found for {category}")
            return []

        topics = list(set(dp[1] for dp in data_points if dp[1]))
        predictions = []

        for topic in topics:
            try:
                f = self.extract_features(topic, data_points, category)
                if not f:
                    continue

                score = self.calculate_trend_score(f)

                # apply policy BEFORE threshold
                if not self.passes_prediction_policy(f, score):
                    continue

                confidence = self.calculate_confidence(f)

                if score >= config.TREND_SCORE_THRESHOLD:
                    predictions.append({
                        "topic": topic,
                        "trend_score": score,
                        "confidence": confidence,
                        "category": category,
                        "features": f
                    })

            except Exception as e:
                print(f"Error processing topic '{topic}': {e}")
                continue

        predictions.sort(key=lambda x: x["trend_score"], reverse=True)

        # Save top N (default 10)
        top_n = _cfg("TOP_N_PREDICTIONS_TO_SAVE", TOP_N_SAVE_DEFAULT)
        for pred in predictions[:top_n]:
            try:
                save_prediction(
                    topic=pred["topic"],
                    category=pred["category"],
                    trend_score=pred["trend_score"],
                    confidence=pred["confidence"]
                )
            except Exception as e:
                print(f"Error saving prediction: {e}")

        return predictions


def run_predictions_for_all_categories():
    predictor = TrendPredictor()
    all_predictions = {}

    for category in config.CATEGORIES.keys():
        try:
            preds = predictor.predict_trends(category)
            all_predictions[category] = preds
            print(f"{category}: {len(preds)} trending topics predicted")
        except Exception as e:
            print(f"Error predicting for {category}: {e}")
            all_predictions[category] = []

    return all_predictions
