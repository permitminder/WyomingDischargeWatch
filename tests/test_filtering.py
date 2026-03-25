"""
Tests for exceedance filtering logic.

Covers the critical data quality rules:
  - Drop Monitor & Report rows (PERMIT_VALUE == 0)
  - Floor parameters (pH, DO, removal) with min codes: only sample < limit is exceedance
  - Non-floor parameters with min codes (Chlorine, Boron): treated as max-limit
  - Max-limit codes: only sample > limit is a real exceedance
  - pct_over calculation for both directions
  - direction assignment ("Over" vs "Under")

Uses the standalone filter_real_exceedances() from send_notifications.py,
which mirrors the logic in main.py load_data().
"""

import sys
import os
import numpy as np
import pandas as pd
import pytest

# Add project root to path so we can import send_notifications
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from send_notifications import filter_real_exceedances


def make_row(permit="TX0000001", parameter="BOD", permit_value=10.0,
             sample_value=15.0, stat_base_code="MK", violation_condition="="):
    """Helper to build a single-row DataFrame for testing."""
    return pd.DataFrame([{
        "PERMIT_NUMBER": permit,
        "PARAMETER": parameter,
        "PERMIT_VALUE": permit_value,
        "SAMPLE_VALUE": sample_value,
        "STAT_BASE_CODE": stat_base_code,
        "VIOLATION_CONDITION": violation_condition,
        "MONITORING_PERIOD_END_DATE": "12/31/2025",
        "COUNTY_NAME": "Test County",
    }])


def make_df(rows):
    """Concat multiple single-row DataFrames."""
    return pd.concat(rows, ignore_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Monitor & Report filtering
# ═══════════════════════════════════════════════════════════════════════════════

class TestMonitorAndReport:
    def test_drops_zero_permit_value(self):
        """PERMIT_VALUE == 0 means Monitor & Report — not a real limit."""
        df = make_row(permit_value=0, sample_value=5.0)
        result = filter_real_exceedances(df)
        assert len(result) == 0

    def test_keeps_nonzero_permit_value(self):
        """Real limits (PERMIT_VALUE > 0) should be kept if sample exceeds."""
        df = make_row(permit_value=10.0, sample_value=15.0, stat_base_code="MK")
        result = filter_real_exceedances(df)
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Minimum-limit filtering (IB, DC, ME, MJ)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMinimumLimitFiltering:
    """
    For floor parameters (pH, DO, removal) with min codes, an exceedance
    means the sample is BELOW the limit. Sample ABOVE the limit is within limit.
    """

    @pytest.mark.parametrize("code", ["IB", "DC", "ME", "MJ"])
    def test_drops_min_code_sample_above_limit(self, code):
        """Floor param + min code + sample > limit = within limit, should be dropped."""
        df = make_row(parameter="pH", permit_value=6.0, sample_value=7.0, stat_base_code=code)
        result = filter_real_exceedances(df)
        assert len(result) == 0

    @pytest.mark.parametrize("code", ["IB", "DC", "ME", "MJ"])
    def test_keeps_min_code_sample_below_limit(self, code):
        """Floor param + min code + sample < limit = real exceedance, should be kept."""
        df = make_row(parameter="pH", permit_value=6.0, sample_value=5.0, stat_base_code=code)
        result = filter_real_exceedances(df)
        assert len(result) == 1

    def test_drops_min_code_sample_equals_limit(self):
        """Floor param + min code + sample == limit = not an exceedance."""
        df = make_row(parameter="Oxygen, dissolved [DO]", permit_value=5.0, sample_value=5.0, stat_base_code="IB")
        result = filter_real_exceedances(df)
        assert len(result) == 0

    def test_minimum_text_in_stat_base(self):
        """Stat base containing 'minimum' + floor param should be treated as min-limit."""
        df = make_row(parameter="pH", permit_value=6.0, sample_value=7.0, stat_base_code="Daily Minimum")
        result = filter_real_exceedances(df)
        assert len(result) == 0  # above floor = within limit

    def test_case_insensitive_stat_codes(self):
        """Stat base codes should match regardless of case."""
        df = make_row(parameter="pH", permit_value=6.0, sample_value=5.0, stat_base_code="ib")
        result = filter_real_exceedances(df)
        assert len(result) == 1

    def test_removal_param_treated_as_floor(self):
        """Percent removal parameters with min codes are floors."""
        df = make_row(parameter="BOD, carb-5 day, 20 deg C, percent removal",
                      permit_value=85.0, sample_value=90.0, stat_base_code="MJ")
        result = filter_real_exceedances(df)
        assert len(result) == 0  # above minimum removal = within limit

    def test_non_floor_param_with_min_code_treated_as_max(self):
        """Pollutants (Chlorine, Boron) with min codes have ceiling limits, not floors."""
        df = make_row(parameter="Chlorine, total residual",
                      permit_value=0.02, sample_value=0.09, stat_base_code="IB")
        result = filter_real_exceedances(df)
        assert len(result) == 1  # above ceiling = real exceedance

    def test_boron_with_min_code_treated_as_max(self):
        """Boron with MJ code is a ceiling limit, not a floor."""
        df = make_row(parameter="Boron, total [as B]",
                      permit_value=10.0, sample_value=48.0, stat_base_code="MJ")
        result = filter_real_exceedances(df)
        assert len(result) == 1  # above ceiling = real exceedance


# ═══════════════════════════════════════════════════════════════════════════════
# Maximum-limit filtering (non-min codes)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMaximumLimitFiltering:
    """
    For maximum/average limits, an exceedance means sample ABOVE the limit.
    """

    @pytest.mark.parametrize("code", ["MK", "IA", "DD", "WA", "GA", "MO"])
    def test_keeps_max_code_sample_above_limit(self, code):
        """Max code + sample > limit = real exceedance."""
        df = make_row(permit_value=10.0, sample_value=15.0, stat_base_code=code)
        result = filter_real_exceedances(df)
        assert len(result) == 1

    def test_drops_max_code_sample_below_limit(self):
        """Max code + sample < limit = within limit, should be dropped."""
        df = make_row(permit_value=10.0, sample_value=5.0, stat_base_code="MK")
        result = filter_real_exceedances(df)
        assert len(result) == 0

    def test_drops_max_code_sample_equals_limit(self):
        """Max code + sample == limit = not an exceedance."""
        df = make_row(permit_value=10.0, sample_value=10.0, stat_base_code="MK")
        result = filter_real_exceedances(df)
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# ECHO VIOLATION_CONDITION field must be ignored (EPA source field name)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIgnoresEchoConditionField:
    """
    The ECHO field VIOLATION_CONDITION is '=' for ~99% of data. The filter
    must use actual value comparison, not this field.
    """

    def test_equals_condition_max_over(self):
        """condition='=' but sample > limit on max code → keep."""
        df = make_row(permit_value=10.0, sample_value=15.0,
                      stat_base_code="MK", violation_condition="=")
        result = filter_real_exceedances(df)
        assert len(result) == 1

    def test_equals_condition_min_above(self):
        """condition='=' but sample > limit on floor param + min code → drop (within limit)."""
        df = make_row(parameter="pH", permit_value=6.0, sample_value=7.0,
                      stat_base_code="IB", violation_condition="=")
        result = filter_real_exceedances(df)
        assert len(result) == 0

    def test_gt_condition_min_above(self):
        """condition='>' but sample > limit on floor param + min code → still drop."""
        df = make_row(parameter="pH", permit_value=6.0, sample_value=7.0,
                      stat_base_code="IB", violation_condition=">")
        result = filter_real_exceedances(df)
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# pct_over calculation
# ═══════════════════════════════════════════════════════════════════════════════

class TestPctOver:
    def test_over_limit_pct(self):
        """Max code: (sample - limit) / limit * 100."""
        df = make_row(permit_value=10.0, sample_value=15.0, stat_base_code="MK")
        result = filter_real_exceedances(df)
        assert result.iloc[0]["pct_over"] == 50.0

    def test_under_minimum_pct(self):
        """Floor param + min code: (limit - sample) / limit * 100."""
        df = make_row(parameter="pH", permit_value=6.0, sample_value=4.0, stat_base_code="IB")
        result = filter_real_exceedances(df)
        # (6.0 - 4.0) / 6.0 * 100 = 33.3
        assert result.iloc[0]["pct_over"] == 33.3

    def test_small_exceedance_pct(self):
        """Fractional percent should be rounded to 1 decimal."""
        df = make_row(permit_value=30.0, sample_value=31.0, stat_base_code="MK")
        result = filter_real_exceedances(df)
        assert result.iloc[0]["pct_over"] == 3.3

    def test_large_exceedance_pct(self):
        """Very large exceedances should calculate correctly."""
        df = make_row(permit_value=0.001, sample_value=1.0, stat_base_code="MK")
        result = filter_real_exceedances(df)
        assert result.iloc[0]["pct_over"] == 99900.0


# ═══════════════════════════════════════════════════════════════════════════════
# Mixed data (realistic scenario)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMixedData:
    def test_mixed_rows_filtered_correctly(self):
        """Realistic mix: only real exceedances survive."""
        df = make_df([
            # Real over-limit exceedance (MK, sample > limit)
            make_row(permit="TX001", permit_value=10, sample_value=15, stat_base_code="MK"),
            # False positive: pH floor, sample above floor (within limit)
            make_row(permit="TX002", parameter="pH", permit_value=6, sample_value=7, stat_base_code="IB"),
            # Monitor & Report (limit = 0)
            make_row(permit="TX003", permit_value=0, sample_value=5, stat_base_code="MK"),
            # Real under-minimum exceedance (pH IB, sample below floor)
            make_row(permit="TX004", parameter="pH", permit_value=6, sample_value=4, stat_base_code="IB"),
            # Within-limit max-limit row (sample < limit)
            make_row(permit="TX005", permit_value=10, sample_value=8, stat_base_code="MK"),
            # Chlorine with IB code — ceiling limit, sample above = real exceedance
            make_row(permit="TX006", parameter="Chlorine, total residual",
                     permit_value=0.02, sample_value=0.09, stat_base_code="IB"),
        ])
        result = filter_real_exceedances(df)
        assert len(result) == 3
        assert set(result["PERMIT_NUMBER"]) == {"TX001", "TX004", "TX006"}

    def test_real_csv_count(self):
        """Sanity check: filtering the actual CSV produces ~1,791 records."""
        csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "tx_exceedances_launch_ready.csv")
        if not os.path.exists(csv_path):
            pytest.skip("CSV not found")
        df = pd.read_csv(csv_path, low_memory=False)
        result = filter_real_exceedances(df)
        # Sanity check: should have a reasonable number of real exceedances.
        # Historical data (2020-2024) + ECHO FY2026 ≈ 35k; exact count grows with data updates.
        assert len(result) > 1000, f"Expected >1,000 real exceedances, got {len(result)}"


# ═══════════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_nan_stat_base_code(self):
        """NaN stat base code should be treated as max-limit (non-min)."""
        df = make_row(permit_value=10.0, sample_value=15.0)
        df["STAT_BASE_CODE"] = np.nan
        result = filter_real_exceedances(df)
        assert len(result) == 1

    def test_empty_dataframe(self):
        """Empty input should return empty output without error."""
        df = pd.DataFrame(columns=["PERMIT_NUMBER", "PARAMETER", "PERMIT_VALUE",
                                    "SAMPLE_VALUE", "STAT_BASE_CODE", "VIOLATION_CONDITION"])
        result = filter_real_exceedances(df)
        assert len(result) == 0

    def test_nan_sample_value_dropped(self):
        """NaN sample value can't be compared — should be dropped."""
        df = make_row(permit_value=10.0)
        df["SAMPLE_VALUE"] = np.nan
        result = filter_real_exceedances(df)
        assert len(result) == 0

    def test_nan_permit_value_dropped(self):
        """NaN permit value can't be compared — should be dropped."""
        df = make_row(sample_value=15.0)
        df["PERMIT_VALUE"] = np.nan
        result = filter_real_exceedances(df)
        assert len(result) == 0
