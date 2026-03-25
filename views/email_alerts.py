import re
import secrets as stdlib_secrets
from datetime import datetime, timezone
import streamlit as st
from supabase import create_client

from utils.email_utils import send_verification_email
from utils.secrets import get_secret


def render_email_alerts(df_all):
    """Render the Email Alerts page."""
    st.markdown("""
    <div class="pm-hero">
        <div class="pm-eyebrow">Email Alerts</div>
        <div class="pm-headline">Get notified when facilities <em>exceed permit limits.</em></div>
        <div class="pm-subhead">
            Sign up to receive email alerts when new exceedances are reported via EPA ECHO.
            Filter by permit number, county, or facility type.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:32px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="pm-section-title">Sign Up for Alerts</div>', unsafe_allow_html=True)
    st.markdown('<div class="pm-section-sub">Choose how you want to be notified</div>', unsafe_allow_html=True)

    # Build options for dynamic second field
    counties = sorted(df_all.loc[df_all["COUNTY_NAME"] != "Unknown", "COUNTY_NAME"].unique())
    facility_types = sorted(df_all.loc[df_all["SIC_DESC"] != "", "SIC_DESC"].unique().tolist())

    with st.form("signup_form", clear_on_submit=True):
        signup_email = st.text_input("Email address", placeholder="you@example.com")

        alert_type = st.selectbox(
            "Alert type",
            ["Permit Number", "County", "Facility Type"],
            index=0,
        )

        # Dynamic second field based on alert type
        if alert_type == "Permit Number":
            alert_value = st.text_input("Permit number", placeholder="e.g., TX0255858")
        elif alert_type == "County":
            alert_value = st.selectbox("County", counties, index=None, placeholder="Choose a county")
        else:
            alert_value = st.selectbox("Facility type", facility_types, index=None, placeholder="Choose a facility type")

        submitted = st.form_submit_button("Sign Up for Alerts")

    if submitted:
        email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
        if not signup_email or not re.match(email_pattern, signup_email):
            st.error("Please enter a valid email address.")
        elif not alert_value or (isinstance(alert_value, str) and not alert_value.strip()):
            st.error("Please provide a value for your selected alert type.")
        else:
            clean_email = signup_email.strip().lower()
            clean_value = alert_value.strip() if isinstance(alert_value, str) else alert_value

            try:
                supabase = create_client(
                    get_secret("supabase", "url"),
                    get_secret("supabase", "key"),
                )

                # Check for existing signup with same (email, alert_type, alert_value)
                existing = (
                    supabase.table("signups")
                    .select("id, verified")
                    .eq("email", clean_email)
                    .eq("alert_type", alert_type)
                    .eq("alert_value", clean_value)
                    .execute()
                )

                if existing.data and existing.data[0].get("verified"):
                    st.info(
                        f"You're already subscribed to **{alert_type}**: **{clean_value}**. "
                        "You'll continue receiving alerts."
                    )
                else:
                    token = stdlib_secrets.token_urlsafe(32)

                    unsub_token = stdlib_secrets.token_urlsafe(32)

                    if existing.data:
                        # Unverified duplicate — refresh token and resend
                        supabase.table("signups").update({
                            "verify_token": token,
                            "unsub_token": unsub_token,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }).eq("id", existing.data[0]["id"]).execute()
                    else:
                        supabase.table("signups").insert({
                            "email": clean_email,
                            "alert_type": alert_type,
                            "alert_value": clean_value,
                            "verify_token": token,
                            "unsub_token": unsub_token,
                        }).execute()

                    if send_verification_email(clean_email, token):
                        st.success(
                            f"Check your email! We sent a confirmation link to **{clean_email}**. "
                            "Click it to activate your alert."
                        )
                    else:
                        st.warning(
                            "Your signup was saved but we had trouble sending the confirmation email. "
                            "Please try again in a few minutes."
                        )

            except Exception as e:
                st.error(f"Signup failed \u2014 please try again. ({e})")

    st.markdown('<hr>', unsafe_allow_html=True)

    # ── MANAGE SUBSCRIPTIONS ──────────────────────────────────────────────
    st.markdown('<div class="pm-section-title">Manage Subscriptions</div>', unsafe_allow_html=True)
    st.markdown('<div class="pm-section-sub">Look up and remove your existing alerts</div>', unsafe_allow_html=True)

    with st.form("manage_form"):
        lookup_email = st.text_input("Email address", placeholder="you@example.com", key="manage_email")
        lookup_submitted = st.form_submit_button("Look Up My Subscriptions")

    if lookup_submitted and lookup_email and lookup_email.strip():
        clean_lookup = lookup_email.strip().lower()
        try:
            supabase = create_client(
                get_secret("supabase", "url"),
                get_secret("supabase", "key"),
            )
            subs_result = (
                supabase.table("signups")
                .select("id, alert_type, alert_value, verified")
                .eq("email", clean_lookup)
                .execute()
            )
            rows = subs_result.data or []
            verified_rows = [r for r in rows if r.get("verified")]

            if not verified_rows:
                st.info("No active subscriptions found for that email address.")
            else:
                st.session_state["_manage_subs"] = verified_rows
                st.session_state["_manage_email"] = clean_lookup
        except Exception as e:
            st.error(f"Lookup failed \u2014 please try again. ({e})")

    # Display subscriptions if we have them
    if st.session_state.get("_manage_subs"):
        managed_subs = st.session_state["_manage_subs"]
        st.markdown(
            f"**{len(managed_subs)} active subscription(s)** for "
            f"**{st.session_state.get('_manage_email', '')}**:"
        )

        to_remove = []
        for sub in managed_subs:
            checked = st.checkbox(
                f"{sub['alert_type']}: {sub['alert_value']}",
                key=f"unsub_{sub['id']}",
            )
            if checked:
                to_remove.append(sub)

        if st.button("Remove Selected", disabled=len(to_remove) == 0):
            try:
                supabase = create_client(
                    get_secret("supabase", "url"),
                    get_secret("supabase", "key"),
                )
                for sub in to_remove:
                    supabase.table("signups").delete().eq("id", sub["id"]).execute()
                st.success(f"Removed {len(to_remove)} subscription(s).")
                # Clear the cached list
                del st.session_state["_manage_subs"]
                del st.session_state["_manage_email"]
                st.rerun()
            except Exception as e:
                st.error(f"Failed to remove subscriptions \u2014 please try again. ({e})")

    st.markdown('<hr>', unsafe_allow_html=True)
    st.info("Raw reported data, not a compliance determination. Data sourced from EPA ECHO system. Your email will only be used for exceedance alerts.")
