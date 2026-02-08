import sqlite3
from datetime import datetime, timedelta
import json

DB_PATH = "trends.db"

def init_db():
    """Initialize database tables"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    # Subscribers table
    c.execute('''CREATE TABLE IF NOT EXISTS subscribers
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT NOT NULL,
                  categories TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  active BOOLEAN DEFAULT 1)''')

    # Data points table (from all platforms)
    c.execute('''CREATE TABLE IF NOT EXISTS data_points
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  platform TEXT NOT NULL,
                  category TEXT NOT NULL,
                  topic TEXT NOT NULL,
                  content TEXT,
                  engagement_score REAL,
                  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  metadata TEXT)''')

    # Predictions table
    c.execute('''CREATE TABLE IF NOT EXISTS predictions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  topic TEXT NOT NULL,
                  category TEXT NOT NULL,
                  trend_score REAL NOT NULL,
                  confidence REAL,
                  predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  alerted BOOLEAN DEFAULT 0,
                  verified BOOLEAN DEFAULT 0)''')

    # Alerts sent table (legacy)
    c.execute('''CREATE TABLE IF NOT EXISTS alerts_sent
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT NOT NULL,
                  topic TEXT NOT NULL,
                  category TEXT NOT NULL,
                  sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # Alerts table (used for cooldown checks)
    c.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        category TEXT,
        topic TEXT,
        trend_score REAL,
        confidence REAL,
        alerted_at TEXT
    )
    """)

    # Optional performance indexes (help a lot once you have many alerts)
    c.execute("CREATE INDEX IF NOT EXISTS idx_alerts_email_topic_time ON alerts(email, topic, alerted_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_alerts_email_category_time ON alerts(email, category, alerted_at)")

    conn.commit()
    conn.close()


def subscribe_user(email, categories):
    """Add or update user subscription"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    categories_json = json.dumps(categories)

    c.execute("SELECT id FROM subscribers WHERE email = ?", (email,))
    existing = c.fetchone()

    if existing:
        c.execute(
            "UPDATE subscribers SET categories = ?, active = 1 WHERE email = ?",
            (categories_json, email),
        )
    else:
        c.execute(
            "INSERT INTO subscribers (email, categories) VALUES (?, ?)",
            (email, categories_json),
        )

    conn.commit()
    conn.close()


def get_subscribers_by_category(category):
    """Get all active subscribers for a category"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    c.execute("SELECT email, categories FROM subscribers WHERE active = 1")
    all_subscribers = c.fetchall()

    relevant_emails = []
    for email, categories_json in all_subscribers:
        try:
            categories = json.loads(categories_json)
        except Exception:
            categories = []
        if category in categories:
            relevant_emails.append(email)

    conn.close()
    return relevant_emails


def save_data_point(platform, category, topic, content, engagement_score, metadata=None):
    """Save a data point from any platform"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    metadata_json = json.dumps(metadata) if metadata else None

    c.execute(
        """INSERT INTO data_points 
           (platform, category, topic, content, engagement_score, metadata)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (platform, category, topic, content, engagement_score, metadata_json),
    )

    conn.commit()
    conn.close()


def save_prediction(topic, category, trend_score, confidence):
    """Save ML prediction"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    c.execute(
        """SELECT id FROM predictions 
           WHERE topic = ? AND category = ? 
           AND datetime(predicted_at) > datetime('now', '-1 hour')""",
        (topic, category),
    )

    if not c.fetchone():
        c.execute(
            """INSERT INTO predictions (topic, category, trend_score, confidence)
               VALUES (?, ?, ?, ?)""",
            (topic, category, trend_score, confidence),
        )
        conn.commit()
        pred_id = c.lastrowid
    else:
        pred_id = None

    conn.close()
    return pred_id


def get_recent_predictions(hours=24, category=None):
    """Get recent predictions"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    query = f"""SELECT topic, category, trend_score, confidence, predicted_at, alerted
                FROM predictions 
                WHERE datetime(predicted_at) > datetime('now', '-{hours} hours')"""

    if category:
        query += " AND category = ?"
        c.execute(query, (category,))
    else:
        c.execute(query)

    results = c.fetchall()
    conn.close()
    return results


def mark_prediction_alerted(topic, category):
    """Mark that alerts have been sent for this prediction"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    c.execute(
        "UPDATE predictions SET alerted = 1 WHERE topic = ? AND category = ?",
        (topic, category),
    )

    conn.commit()
    conn.close()


def log_alert_sent(email, topic, category):
    """Log that an alert was sent (legacy table)"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    c.execute(
        "INSERT INTO alerts_sent (email, topic, category) VALUES (?, ?, ?)",
        (email, topic, category),
    )

    conn.commit()
    conn.close()


def get_data_points(category, hours=24):
    """Get recent data points for analysis"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    c.execute(
        f"""SELECT platform, topic, content, engagement_score, timestamp, metadata
            FROM data_points
            WHERE category = ? 
            AND datetime(timestamp) > datetime('now', '-{hours} hours')
            ORDER BY timestamp DESC""",
        (category,),
    )

    results = c.fetchall()
    conn.close()
    return results


# =========================
# Cooldown helpers (used by email_service.py)
# =========================
def was_user_alerted_for_topic(email, topic, hours=24):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat(timespec="seconds")

    c.execute("""
        SELECT 1 FROM alerts
        WHERE email = ? AND topic = ? AND alerted_at >= ?
        LIMIT 1
    """, (email, topic, cutoff))

    row = c.fetchone()
    conn.close()
    return row is not None


def was_user_alerted_for_category(email, category, hours=6):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat(timespec="seconds")

    c.execute("""
        SELECT 1 FROM alerts
        WHERE email = ? AND category = ? AND alerted_at >= ?
        LIMIT 1
    """, (email, category, cutoff))

    row = c.fetchone()
    conn.close()
    return row is not None


def log_alert(email, category, topic, trend_score, confidence):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    now = datetime.utcnow().isoformat(timespec="seconds")

    c.execute("""
        INSERT INTO alerts (email, category, topic, trend_score, confidence, alerted_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (email, category, topic, trend_score, confidence, now))

    conn.commit()
    conn.close()
