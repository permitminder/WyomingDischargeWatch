# EffluentWatch — Multi-State Template

> **This is a template.** Run `python deploy_new_state.py <STATE_CODE>` to configure for your state.

Automated water discharge permit exceedance monitoring for US NPDES facilities. Clone this repo, run the deploy script, and get a working EPA ECHO exceedance tracker for any US state.

## Quick Start (New State)

```bash
# Clone and configure for Ohio:
git clone <this-repo> ohio-discharge-monitor
cd ohio-discharge-monitor
python deploy_new_state.py OH --app-name "BuckeyeWatch"

# Or auto-generate app name:
python deploy_new_state.py OH
# → Creates "Ohio Discharge Monitor"
```

The deploy script updates `state_config.py`, creates the data CSV with correct headers, and prints a checklist of manual setup steps.

## Current Configuration

All state-specific values live in `state_config.py`:

```python
STATE_CODE = "TX"          # 2-letter state code
STATE_NAME = "Texas"       # Full state name
APP_NAME = "EffluentWatch" # Brand name
APP_TAGLINE = "Texas Discharge Monitoring"
DOMAIN = "effluentwatch.org"
DATA_FILE = "tx_exceedances_launch_ready.csv"
EPA_REGION = 6
```

See `STATES.md` for EPA region tracking across all states and territories.

## Key Features

- **Automated Data Collection** — GitHub Actions scrapes EPA ECHO bulk DMR data weekly, filtering to the configured state
- **Exceedance Detection** — Compares reported discharge values against permit limits to identify exceedances
- **Daily Email Alerts** — Subscribers receive notifications when facilities exceed permit limits
- **Interactive Dashboard** — Streamlit + Plotly charts for exploring exceedance data by county, parameter, and time
- **Stripe-Integrated Paywall** — Free tier (20 results/query) and Pro tier ($29/month for unlimited access + daily alerts)
- **Supabase Backend** — Authentication, subscription management, and data storage

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | Python 3.11, Streamlit |
| Data Processing | Pandas, NumPy |
| Charts | Plotly |
| Database | Supabase (PostgreSQL) |
| Payments | Stripe |
| Automation | GitHub Actions |
| Hosting | Render |

## Architecture

```
EPA ECHO (bulk DMR data)
    │
    ▼
echo_dmr_scraper.py  ←── GitHub Actions (weekly, Monday 6AM UTC)
    │
    ▼
{state}_exceedances_launch_ready.csv  (append-only, deduped)
    │
    ├──► main.py (Streamlit app on Render)
    │       ├── Search Records
    │       ├── Email Alerts (Supabase signups)
    │       └── Dashboard (Plotly charts)
    │
    └──► send_notifications.py  ←── GitHub Actions (daily)
            └── Gmail SMTP → subscribers
```

## Data Source

All data is sourced from the EPA ECHO ICIS-NPDES bulk download:
https://echo.epa.gov/tools/data-downloads/icis-npdes-dmr-and-limit-data-set

State permits are filtered by `STATE_CODE` from `state_config.py`.

## Revenue Model

| Tier | Price | Features |
|------|-------|----------|
| Free | $0 | 20 results per query |
| Pro | $29/month | Unlimited results + daily email alerts |

## Environment Variables

The following secrets are required for full operation:

```
SUPABASE_URL        # Supabase project URL
SUPABASE_KEY        # Supabase anon key
STRIPE_SECRET_KEY   # Stripe API key
STRIPE_PRICE_ID     # Stripe price ID for Pro tier
GMAIL_USER          # Sender Gmail address
GMAIL_PASS          # Gmail app password
```

## License

MIT License — see [LICENSE](LICENSE) for details.
