import streamlit as st


def inject_css():
    """Inject all EffluentWatch CSS into the current Streamlit page."""
    st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=IBM+Plex+Mono:wght@400;500;600&family=Source+Sans+3:wght@400;500;600;700&display=swap');

    /* Base */
    html, body, [class*="css"] {
        font-family: 'Source Sans 3', sans-serif;
    }

    .stApp {
        background: #f8f7f5;
    }

    /* Hide Streamlit chrome */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    div[data-testid="stToolbar"] {display: none;}

    /* Block container padding */
    .block-container {
        padding-top: 0 !important;
        padding-bottom: 40px !important;
        max-width: 1000px !important;
    }

    /* ── NAV BAR ── */
    .pm-nav {
        background: #ffffff;
        border-bottom: 1px solid #e8e4df;
        padding: 0 0 0 0;
        height: 56px;
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 0;
    }

    .pm-logo-mark {
        width: 24px; height: 24px;
        border: 1.5px solid #3a6b1a;
        border-radius: 3px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 9px;
        color: #3a6b1a;
        font-weight: 600;
        vertical-align: middle;
        margin-right: 6px;
    }

    .pm-logo-text {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 14px;
        font-weight: 600;
        color: #1a1814;
        letter-spacing: 0.3px;
    }

    /* ── HERO ── */
    .pm-hero {
        background: #ffffff;
        border-bottom: 1px solid #e8e4df;
        padding: 56px 0 48px 0;
        margin-bottom: 0;
    }

    .pm-eyebrow {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 10px;
        letter-spacing: 3px;
        text-transform: uppercase;
        color: #3a6b1a;
        margin-bottom: 18px;
    }

    .pm-headline {
        font-family: 'Libre Baskerville', serif;
        font-size: 44px;
        font-weight: 700;
        line-height: 1.1;
        color: #1a1814;
        margin-bottom: 16px;
    }

    .pm-headline em {
        font-style: italic;
        color: #3a6b1a;
    }

    .pm-subhead {
        font-size: 16px;
        color: #6b6560;
        line-height: 1.65;
        max-width: 560px;
        margin-bottom: 32px;
    }

    /* ── STAT STRIP ── */
    .pm-stats {
        background: #f8f7f5;
        border-bottom: 1px solid #e8e4df;
        padding: 28px 0;
        margin-bottom: 40px;
    }

    .pm-stat-num {
        font-family: 'Libre Baskerville', serif;
        font-size: 28px;
        font-weight: 700;
        color: #1a1814;
        line-height: 1;
    }

    .pm-stat-label {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 10px;
        letter-spacing: 2px;
        text-transform: uppercase;
        color: #b0aba6;
        margin-top: 4px;
    }

    /* ── SECTION TITLES ── */
    .pm-section-title {
        font-family: 'Libre Baskerville', serif;
        font-size: 20px;
        font-weight: 700;
        color: #1a1814;
        margin-bottom: 4px;
    }

    .pm-section-sub {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 10px;
        letter-spacing: 2px;
        text-transform: uppercase;
        color: #b0aba6;
        margin-bottom: 20px;
    }

    /* ── SEARCH INPUT ── */
    .stTextInput > div > div > input {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 14px !important;
        border: 1.5px solid #e8e4df !important;
        border-radius: 6px !important;
        background: #ffffff !important;
        color: #1a1814 !important;
        padding: 12px 14px !important;
    }

    .stTextInput > div > div > input:focus {
        border-color: #3a6b1a !important;
        box-shadow: 0 0 0 3px rgba(58,107,26,0.08) !important;
    }

    /* ── BUTTONS ── */
    .stButton > button {
        background: #3a6b1a !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        letter-spacing: 0.5px !important;
        padding: 11px 20px !important;
        transition: background 0.15s !important;
    }

    .stButton > button:hover {
        background: #2e5414 !important;
    }

    /* Secondary button */
    .stButton > button[kind="secondary"] {
        background: #ffffff !important;
        color: #3a6b1a !important;
        border: 1.5px solid #3a6b1a !important;
    }

    /* ── METRIC CARDS ── */
    [data-testid="metric-container"] {
        background: white;
        border: 1px solid #e8e4df;
        border-radius: 8px;
        padding: 20px !important;
    }

    [data-testid="metric-container"] label {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 10px !important;
        letter-spacing: 2px !important;
        text-transform: uppercase !important;
        color: #b0aba6 !important;
        font-weight: 500 !important;
    }

    [data-testid="metric-container"] [data-testid="metric-value"] {
        font-family: 'Libre Baskerville', serif !important;
        font-size: 30px !important;
        font-weight: 700 !important;
        color: #1a1814 !important;
    }

    /* ── TABLE ── */
    .dataframe {
        font-family: 'Source Sans 3', sans-serif !important;
        font-size: 14px !important;
    }

    .dataframe th {
        font-family: 'IBM Plex Mono', monospace !important;
        background: #f8f7f5 !important;
        color: #b0aba6 !important;
        font-size: 10px !important;
        text-transform: uppercase !important;
        letter-spacing: 1.5px !important;
        font-weight: 500 !important;
        padding: 12px !important;
    }

    .dataframe td {
        padding: 14px 12px !important;
        border-bottom: 1px solid #f0ece8 !important;
        color: #1a1814 !important;
    }

    /* ── BADGES ── */
    .badge-over {
        background: #fdf0f0;
        color: #b83232;
        padding: 3px 10px;
        border-radius: 3px;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 1px;
        text-transform: uppercase;
        display: inline-block;
        border: 1px solid #f5c6c6;
    }

    .badge-within {
        background: #eef4e8;
        color: #3a6b1a;
        padding: 3px 10px;
        border-radius: 3px;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 1px;
        text-transform: uppercase;
        display: inline-block;
        border: 1px solid #c5dda8;
    }

    /* ── CARDS ── */
    .pm-card {
        background: white;
        border: 1px solid #e8e4df;
        border-radius: 8px;
        padding: 28px;
        margin-bottom: 20px;
    }

    /* ── DIVIDER ── */
    hr {
        border: none !important;
        border-top: 1px solid #e8e4df !important;
        margin: 32px 0 !important;
    }

    /* ── FOOTER ── */
    .pm-footer {
        text-align: center;
        color: #b0aba6;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 11px;
        letter-spacing: 0.5px;
        margin-top: 60px;
        padding-top: 24px;
        border-top: 1px solid #e8e4df;
        line-height: 1.8;
    }

    /* ── ALERTS / INFO ── */
    .stAlert {
        border-radius: 6px !important;
        font-family: 'Source Sans 3', sans-serif !important;
    }

    /* ── CTA BANNER ── */
    .pm-cta-banner {
        background: #eef4e8;
        border: 1px solid #c5dda8;
        border-radius: 8px;
        padding: 20px 24px;
        margin: 24px 0;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .pm-cta-banner .pm-cta-text {
        font-family: 'Source Sans 3', sans-serif;
        font-size: 15px;
        color: #1a1814;
    }
    .pm-cta-banner .pm-cta-sub {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 11px;
        color: #6b6560;
        margin-top: 2px;
    }
</style>
""", unsafe_allow_html=True)
