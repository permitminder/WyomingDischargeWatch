import os


def get_secret(section, key):
    """Get secret from st.secrets (Streamlit Cloud) or os.environ (Render)."""
    env_mapping = {
        ("supabase", "url"): "SUPABASE_URL",
        ("supabase", "key"): "SUPABASE_KEY",
        ("email", "sender"): "GMAIL_USER",
        ("email", "password"): "GMAIL_PASS",
    }

    # Try Streamlit secrets first (only if secrets file exists)
    try:
        import streamlit as st
        return st.secrets[section][key]
    except BaseException:
        pass

    # Fall back to environment variables
    env_name = env_mapping.get((section, key))
    if env_name:
        return os.environ.get(env_name, "")
    return ""
