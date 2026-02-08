import resend
import config
from typing import List, Dict, Any, Optional

from database import (
    get_subscribers_by_category,
    was_user_alerted_for_topic,
    was_user_alerted_for_category,
    log_alert,
    get_recent_predictions,
)

resend.api_key = config.RESEND_API_KEY


# =========================
# Single-alert email (used for DEMO)
# =========================
def send_trend_alert(
    email: str,
    topic: str,
    category: str,
    trend_score: float,
    confidence: float,
) -> bool:
    """Send ONE email about ONE trend (used for demo + optionally for single sends)."""

    html = f"""
    <html>
      <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;
                   max-width:680px;margin:0 auto;padding:20px;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding:24px;border-radius:14px;color:white;text-align:center;">
          <h1 style="margin:0;font-size:24px;">🚀 ModeUp AI — New Trend Alert</h1>
          <p style="margin:10px 0 0;opacity:0.95;">
            One trend detected in your subscribed categories.
          </p>
        </div>

        <div style="background:#f9f9f9;padding:16px;border-radius:10px;margin:18px 0;">
          <h2 style="margin:0;color:#111;">{topic}</h2>
          <p style="margin:10px 0 0;color:#555;font-size:14px;">
            <b>Category:</b> {category.replace('_',' ').title()} &nbsp; | &nbsp;
            <b>Score:</b> {trend_score:.1f}/100 &nbsp; | &nbsp;
            <b>Confidence:</b> {confidence:.0f}%
          </p>
        </div>

        <div style="margin-top:18px;color:#888;font-size:12px;text-align:center;">
          <p style="margin:0;">You’re receiving this because you subscribed to {category.replace('_',' ').title()}.</p>
        </div>
      </body>
    </html>
    """

    try:
        resend.Emails.send({
            "from": config.RESEND_FROM_EMAIL,
            "to": [email],
            "subject": f"🚀 Trending Now: {topic} ({category.replace('_',' ').title()})",
            "html": html,
        })
        print(f"✓ Sent single alert to {email}: {topic} ({category})")
        return True
    except Exception as e:
        print(f"✗ Error sending single alert to {email}: {e}")
        return False


# =========================
# Batch email template (anti-spam)
# =========================
def build_batch_email_html(email: str, chosen: List[Dict[str, Any]]) -> str:
    items_html = ""
    for p in chosen:
        items_html += f"""
        <div style="background:#f9f9f9;padding:16px;border-radius:10px;margin:12px 0;">
          <h3 style="margin:0;color:#111;">{p['topic']}</h3>
          <p style="margin:8px 0 0;color:#555;font-size:14px;">
            <b>Category:</b> {p['category'].replace('_',' ').title()} &nbsp; | &nbsp;
            <b>Score:</b> {p['trend_score']:.1f}/100 &nbsp; | &nbsp;
            <b>Confidence:</b> {p['confidence']:.0f}%
          </p>
        </div>
        """

    return f"""
    <html>
      <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;
                   max-width:680px;margin:0 auto;padding:20px;">

        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding:24px;border-radius:14px;color:white;text-align:center;">
          <h1 style="margin:0;font-size:24px;">🚀 ModeUp AI — Trend Alerts</h1>
          <p style="margin:10px 0 0;opacity:0.95;">
            Here are the strongest new trends detected in your subscribed categories.
          </p>
        </div>

        <div style="margin-top:18px;">
          {items_html}
        </div>

        <div style="margin-top:24px;color:#888;font-size:12px;text-align:center;">
          <p style="margin:0;">
            Cooldowns: per-category {config.ALERT_CATEGORY_COOLDOWN_HOURS}h,
            per-topic {config.ALERT_TOPIC_COOLDOWN_HOURS}h.
          </p>
        </div>

      </body>
    </html>
    """


# =========================
# Filtering / spam controls
# =========================
def filter_predictions_for_user(email: str, predictions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    strong = [
        p for p in predictions
        if p.get("trend_score", 0) >= config.ALERT_MIN_TREND_SCORE
        and p.get("confidence", 0) >= config.ALERT_MIN_CONFIDENCE
    ]

    if not strong:
        return []

    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for p in strong:
        cat = p.get("category")
        if not cat:
            continue
        by_cat.setdefault(cat, []).append(p)

    filtered: List[Dict[str, Any]] = []

    for cat, preds in by_cat.items():
        if was_user_alerted_for_category(email, cat, hours=config.ALERT_CATEGORY_COOLDOWN_HOURS):
            continue

        preds.sort(key=lambda x: x.get("trend_score", 0), reverse=True)
        for p in preds:
            topic = p.get("topic", "")
            if not topic:
                continue
            if was_user_alerted_for_topic(email, topic, hours=config.ALERT_TOPIC_COOLDOWN_HOURS):
                continue
            filtered.append(p)

    filtered.sort(key=lambda x: x.get("trend_score", 0), reverse=True)
    return filtered[: config.ALERT_MAX_ITEMS_PER_EMAIL]


# =========================
# Sending (batched, per user)
# =========================
def send_alerts_to_user(email: str, predictions: List[Dict[str, Any]]) -> bool:
    chosen = filter_predictions_for_user(email, predictions)
    if not chosen:
        return False

    html = build_batch_email_html(email, chosen)
    subject = f"🚀 ModeUp AI: {len(chosen)} new trend alert(s)"

    try:
        resend.Emails.send({
            "from": config.RESEND_FROM_EMAIL,
            "to": [email],
            "subject": subject,
            "html": html,
        })

        for p in chosen:
            log_alert(
                email=email,
                category=p["category"],
                topic=p["topic"],
                trend_score=p["trend_score"],
                confidence=p["confidence"],
            )

        print(f"✓ Sent 1 batched alert to {email} with {len(chosen)} item(s)")
        return True

    except Exception as e:
        print(f"✗ Error sending batched email to {email}: {e}")
        return False


def send_alerts_for_predictions(predictions_by_category: Dict[str, List[Dict[str, Any]]]) -> None:
    user_candidates: Dict[str, List[Dict[str, Any]]] = {}

    for category, preds in (predictions_by_category or {}).items():
        if not preds:
            continue

        normalized_preds: List[Dict[str, Any]] = []
        for p in preds:
            if not isinstance(p, dict):
                continue
            p2 = dict(p)
            p2["category"] = p2.get("category") or category
            normalized_preds.append(p2)

        subscribers = get_subscribers_by_category(category) or []
        for email in subscribers:
            user_candidates.setdefault(email, []).extend(normalized_preds)

    for email, preds in user_candidates.items():
        seen = set()
        deduped = []
        for p in preds:
            key = (p.get("category"), p.get("topic"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(p)

        send_alerts_to_user(email, deduped)


# =========================
# Demo: send ONE email immediately (no anti-spam gating)
# =========================
def send_demo_email_now(email: str, categories: Optional[List[str]] = None) -> bool:
    hours = getattr(config, "LOOKBACK_HOURS", 24)
    rows = get_recent_predictions(hours=hours, category=None)
    if not rows:
        print("No predictions available for demo email.")
        return False

    preds: List[Dict[str, Any]] = []
    for topic, category, trend_score, confidence, predicted_at, alerted in rows:
        preds.append({
            "topic": topic,
            "category": category,
            "trend_score": float(trend_score),
            "confidence": float(confidence or 0),
        })

    if categories:
        preds = [p for p in preds if p["category"] in categories]

    if not preds:
        print("No predictions match selected categories for demo.")
        return False

    preds.sort(key=lambda p: (p["trend_score"], p["confidence"]), reverse=True)
    best = preds[0]

    # Send immediately, always
    ok = send_trend_alert(
        email=email,
        topic=best["topic"],
        category=best["category"],
        trend_score=best["trend_score"],
        confidence=best["confidence"],
    )

    # Optional: log demo send so it appears in alerts history
    if ok:
        log_alert(email, best["category"], best["topic"], best["trend_score"], best["confidence"])

    return ok
