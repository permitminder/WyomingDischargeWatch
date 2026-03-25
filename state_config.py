"""
State configuration for this WyomingDischargeWatch instance.

All state-specific values are centralized here. To deploy for a new state,
run: python deploy_new_state.py <STATE_CODE>

This file is overwritten by deploy_new_state.py — do not add logic here.
"""

STATE_CODE = "WY"
STATE_NAME = "Wyoming"
APP_NAME = "WyomingDischargeWatch"
APP_TAGLINE = "Wyoming Discharge Monitoring"
DOMAIN = "wyomingdischargewatch.org"
DATA_FILE = "wy_exceedances_launch_ready.csv"
CONTACT_EMAIL = "data@wyomingdischargewatch.org"
MAILING_ADDRESS = ""
TIMEZONE_LABEL = "MST"
EPA_REGION = 8
