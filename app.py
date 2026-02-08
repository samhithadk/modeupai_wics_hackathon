import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import init_db, subscribe_user, get_recent_predictions
from scheduler_service import start_scheduler
import config
from datetime import datetime
from email_service import send_demo_email_now


KEY_TO_DISPLAY = {k: v.get("display_name", k) for k, v in config.CATEGORIES.items()}
DISPLAY_TO_KEY = {v.get("display_name", k): k for k, v in config.CATEGORIES.items()}

# Page config
st.set_page_config(
    page_title="ModeUp AI",
    layout="wide"
)

# Initialize database
init_db()

# Start background scheduler (only once)
@st.cache_resource
def _get_scheduler():
    return start_scheduler()

_get_scheduler()


# Custom CSS
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    .stButton>button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.75rem 2rem;
        font-size: 16px;
        font-weight: 600;
        border-radius: 8px;
        width: 100%;
    }
    .trend-card {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 4px solid #667eea;
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
    <div style='text-align: center; padding: 2rem 0;'>
        <h1 style='font-size: 3rem; margin-bottom: 0.5rem;'> ModeUp AI</h1>
        <p style='font-size: 1.2rem; color: #666;'>
            Get notified about trends <strong>before</strong> they hit peak popularity
        </p>
    </div>
""", unsafe_allow_html=True)

# Tabs
tab1, tab2, tab3 = st.tabs(["📧 Subscribe", "📊 Live Dashboard", "ℹ️ About"])

# TAB 1: Subscribe
with tab1:
    st.markdown("### Get Trend Alerts Delivered to Your Email")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        email = st.text_input("Your Email Address", placeholder="you@example.com")
        
        st.markdown("**Select Categories You're Interested In:**")
        
        selected_categories = []
        
        # Display categories in 2 columns
        cat_col1, cat_col2 = st.columns(2)
        
        categories_list = list(config.CATEGORIES.keys())
        mid_point = len(categories_list) // 2

        with cat_col1:
            for cat in categories_list[:mid_point]:
                label = KEY_TO_DISPLAY.get(cat, cat)
                if st.checkbox(label, key=f"cat_{cat}"):
                    selected_categories.append(cat)

        with cat_col2:
            for cat in categories_list[mid_point:]:
                label = KEY_TO_DISPLAY.get(cat, cat)
                if st.checkbox(label, key=f"cat_{cat}"):
                    selected_categories.append(cat)

        
        if st.button("🔔 Subscribe to Alerts"):
            if not email:
                st.error("Please enter your email address")
            elif not selected_categories:
                st.error("Please select at least one category")
            else:
                subscribe_user(email, selected_categories)
                st.success("✅ Subscribed! You'll receive alerts for: " + ", ".join([KEY_TO_DISPLAY[c] for c in selected_categories]))

        st.markdown("---")
        st.markdown("### 🧪 Demo: Send me a test alert right now")

        if st.button("📨 Send Demo Email Now"):
            if not email:
                st.error("Enter your email above first.")
            else:
                ok, msg = send_demo_email_now(
                    email=email,
                    categories=selected_categories
                )

                if ok:
                    st.success(f"✅ {msg}")
                else:
                    st.error(msg)
    
    with col2:
        st.markdown("""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    padding: 1.5rem; border-radius: 12px; color: white; margin-top: 2rem;'>
            <h3 style='margin-top: 0;'>How It Works</h3>
            <ol style='padding-left: 1.2rem;'>
                <li>Select your categories</li>
                <li>Our AI monitors Twitter, Reddit & Google</li>
                <li>Get email alerts for emerging trends</li>
                <li>Act before everyone else!</li>
            </ol>
        </div>
        """, unsafe_allow_html=True)

# TAB 2: Live Dashboard
with tab2:
    st.markdown("### 📈 Current Trending Predictions")
    
    # Category filter
    selected_dash_category = st.selectbox(
        "Filter by category:",
        ["All Categories"] + [KEY_TO_DISPLAY[k] for k in config.CATEGORIES.keys()]
    )

    if selected_dash_category == "All Categories":
        filter_category = None
    else:
        filter_category = DISPLAY_TO_KEY[selected_dash_category]

    
    # Get predictions
    predictions = get_recent_predictions(hours=24, category=filter_category)
    
    if predictions:
        # Create DataFrame
        df = pd.DataFrame(predictions, columns=[
            'Topic', 'Category', 'Trend Score', 'Confidence', 'Predicted At', 'Alerted'
        ])
        
        # Format timestamps
        df['Predicted At'] = pd.to_datetime(df['Predicted At']).dt.strftime('%Y-%m-%d %H:%M')
        
        # Display metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Predictions", len(df))
        
        with col2:
            avg_score = df['Trend Score'].mean()
            st.metric("Avg Trend Score", f"{avg_score:.1f}")
        
        with col3:
            high_confidence = len(df[df['Confidence'] > 70])
            st.metric("High Confidence", high_confidence)
        
        # Visualization
        st.markdown("#### Trend Scores by Category")
        
        fig = px.scatter(
            df,
            x='Predicted At',
            y='Trend Score',
            size='Confidence',
            color='Category',
            hover_data=['Topic'],
            title="Trending Topics Over Time"
        )
        
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
        
        # Top predictions
        st.markdown("#### 🔥 Top Trending Topics")
        
        top_trends = df.nlargest(10, 'Trend Score')
        
        for idx, row in top_trends.iterrows():
            st.markdown(f"""
            <div class='trend-card'>
                <h4 style='margin-top: 0; color: #333;'>{row['Topic']}</h4>
                <p style='color: #666; margin: 0.5rem 0;'>
                    <strong>Category:</strong> {KEY_TO_DISPLAY.get(row['Category'], row['Category'])} &nbsp;|&nbsp; 
                    <strong>Score:</strong> {row['Trend Score']:.1f}/100 &nbsp;|&nbsp; 
                    <strong>Confidence:</strong> {row['Confidence']:.1f}%
                </p>
                <p style='color: #999; font-size: 0.9rem; margin: 0;'>
                    Predicted at {row['Predicted At']}
                </p>
            </div>
            """, unsafe_allow_html=True)
    
    else:
        st.info("No predictions yet. The system will start collecting data and making predictions shortly.")

# TAB 3: About
with tab3:
    st.markdown("""
    ### How Our Prediction System Works
    
    Our AI-powered platform monitors multiple data sources in real-time:
    
    #### Data Sources
    -- Google Trends (SerpAPI): Rising related queries (RELATED_QUERIES → rising)
    -- Google News (SerpAPI): Trending headlines from news search results
    -- Google Search (SerpAPI): Related searches + organic titles as early signals
    -- YouTube (SerpAPI): Video + Shorts results + view-based momentum proxy
    -- Twitter/X: Recent tweet search
    -- Claude: Topic extraction + category validation (yes/no gate)
    
    #### Machine Learning Model
    
    Our prediction algorithm analyzes:
    1. **Cross-Platform Signals**: Topics appearing on multiple platforms score higher
    2. **Engagement Velocity**: How quickly content is gaining traction
    3. **Platform Weights**: Reddit trends often predict Google trends by 12-48 hours
    4. **Historical Patterns**: Learn from past trending topics
    
    #### Trend Score Calculation
    
    Each topic's trend score is computed using four signals:

    Cross-Platform Presence (up to 20 points)
    Topics appearing across multiple platforms (Google Trends, News, Search, YouTube, Twitter/X) score higher.

    Normalized Engagement Strength (up to 30 points)
    Engagement signals are normalized per category (e.g., Tech vs Fashion) to prevent high-volume categories from dominating results.

    Growth Velocity (up to 25 points)
    Measures how quickly mentions are increasing in the last 6 hours compared to the last 24 hours.

    Platform Authority Weighting (up to 25 points)
    Different platforms contribute different weights based on how early they surface trends:

        - Google Trends → strongest early signal
        - News → high-authority confirmation
        - YouTube → momentum proxy via views
        - Twitter/X → real-time social amplification

    Final Trend Score
    All signals are combined into a capped 0–100 score, with alerts triggered only when confidence and score thresholds are met.
    
    #### Categories
    
    We track trends across:
    """)
    
    cols = st.columns(3)
    for idx, (key, info) in enumerate(config.CATEGORIES.items()):
        with cols[idx % 3]:
            st.markdown(f"**{key.title().replace('_', ' ')}**")
            # st.caption(f"Monitoring {len(info['subreddits'])} subreddits")
    
    st.markdown("""
    ---
    
    ### Tech Stack

    - Frontend: Streamlit
    - Storage: SQLite (trends.db)
    - Collectors: SerpAPI + Tweepy
    - LLM: Anthropic Claude (topic extraction + category gate)
    - Scoring: Feature-based trend score (platform diversity, engagement, velocity, weights)
    - Scheduling: Python scheduler (runs every DATA_COLLECTION_INTERVAL_MINUTES)
    - Notifications: Resend Email
    
    **Unique Value:** Predict trends 12-48 hours before they peak on Google Trends!
    """)

# Footer
st.markdown("""
    <div style='text-align: center; padding: 2rem; color: #999; font-size: 0.9rem; margin-top: 3rem;'>
        <p>Built with ❤️ using SerpAPI | Refreshes every {} minutes</p>
    </div>
""".format(config.DATA_COLLECTION_INTERVAL_MINUTES), unsafe_allow_html=True)