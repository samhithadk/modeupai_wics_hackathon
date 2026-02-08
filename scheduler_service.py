# scheduler_service.py
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from data_collector import collect_global_discovery_and_save
from ml_model import run_predictions_for_all_categories
from email_service import send_alerts_for_predictions
import config

def collect_and_predict():
    print("\n" + "="*50)
    print("Starting GLOBAL discovery → classify → score cycle")
    print("="*50)

    # Debug: confirm keys are loaded
    print(f"SERPAPI_KEY loaded? {bool(getattr(config,'SERPAPI_KEY', None))}")
    print(f"TWITTER_BEARER_TOKEN loaded? {bool(getattr(config,'TWITTER_BEARER_TOKEN', None))}")
    print(f"ANTHROPIC_API_KEY loaded? {bool(getattr(config,'ANTHROPIC_API_KEY', None))}")

    try:
        collect_global_discovery_and_save()
    except Exception as e:
        print(f"Global discovery error: {e}")

    predictions = run_predictions_for_all_categories()

    try:
        send_alerts_for_predictions(predictions)
    except Exception as e:
        print(f"Email send error: {e}")

    print("\n" + "="*50)
    print("Cycle complete!")
    print("="*50)

def start_scheduler():
    scheduler = BackgroundScheduler()

    # ✅ schedule every N minutes
    scheduler.add_job(
        collect_and_predict,
        "interval",
        minutes=config.DATA_COLLECTION_INTERVAL_MINUTES,
        id="trend_job",
        replace_existing=True,
    )

    scheduler.start()
    print(f"✓ Scheduler started - running every {config.DATA_COLLECTION_INTERVAL_MINUTES} minutes")

    # ✅ IMPORTANT: run once immediately for demo/dev
    collect_and_predict()

    return scheduler

