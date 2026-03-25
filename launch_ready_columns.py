import pandas as pd
import numpy as np
from datetime import datetime

def prepare_launch_ready_dmr(df):
    """
    Add only the essential columns needed for EffluentWatch launch.
    Following ChatGPT's lightweight approach for Airtable/Softr.
    """
    
    # 1. EFFECTIVE RESULT (handle < and ND values)
    def calculate_effective_result(row):
        result_str = str(row['SAMPLE_VALUE']).strip()
        qualifier = str(row.get('VIOLATION_CONDITION', '')).strip()
        reporting_limit = row.get('Reporting_Limit', None)
        
        # Handle "less than" values like "<0.05"
        if result_str.startswith('<'):
            numeric_part = result_str.replace('<', '')
            try:
                limit_val = float(numeric_part)
                return limit_val / 2  # Use half the detection limit
            except:
                return 0
                
        # Handle "greater than" values like ">48400"  
        if result_str.startswith('>'):
            numeric_part = result_str.replace('>', '')
            try:
                return float(numeric_part)  # Use the actual value
            except:
                return np.nan
        
        # Handle ND (Non-Detect)
        if result_str.upper() in ['ND', 'BDL', 'NOT DETECTED']:
            if reporting_limit and not pd.isna(reporting_limit):
                return float(reporting_limit) / 2
            return 0
            
        # Regular numeric values
        try:
            return float(result_str)
        except:
            return np.nan
    
    df['Effective_Result'] = df.apply(calculate_effective_result, axis=1)
    
    # 2. EXCEEDANCE FLAG
    # Minimum-type stat base codes (abbreviations and descriptive names)
    _MIN_CODES = {'IB', 'DC', 'ME', 'MJ'}

    def _is_min_limit(row):
        stat = str(row.get('STAT_BASE_CODE', '')).strip()
        return stat.upper() in _MIN_CODES or 'minimum' in stat.lower()

    def is_exceedance(row):
        effective = row['Effective_Result']
        limit = row.get('PERMIT_VALUE', None)

        if pd.isna(effective) or pd.isna(limit) or limit == 0:
            return False
        if _is_min_limit(row):
            return effective < limit
        return effective > limit

    df['Is_Exceedance'] = df.apply(is_exceedance, axis=1)

    # 3. EXCEEDANCE CALCULATIONS
    df['Permit_Limit_Clean'] = pd.to_numeric(df.get('PERMIT_VALUE', 0), errors='coerce')

    # Detect minimum-limit rows for directional math
    _stat = df.get('STAT_BASE_CODE', pd.Series('', index=df.index)).fillna('')
    _min_mask = _stat.str.upper().isin(_MIN_CODES) | _stat.str.lower().str.contains('minimum', na=False)

    # Delta (how far from limit — positive means exceedance direction)
    _valid = (df['Effective_Result'].notna()) & (df['Permit_Limit_Clean'].notna()) & (df['Permit_Limit_Clean'] > 0)
    df['Exceedance_Delta'] = np.where(
        _valid & _min_mask,
        df['Permit_Limit_Clean'] - df['Effective_Result'],
        np.where(_valid, df['Effective_Result'] - df['Permit_Limit_Clean'], np.nan)
    )

    # Percent of limit
    df['Percent_of_Limit'] = np.where(
        (df['Effective_Result'].notna()) & (df['Permit_Limit_Clean'] > 0),
        (df['Effective_Result'] / df['Permit_Limit_Clean']) * 100,
        np.nan
    )

    # Percent over limit (the key metric — always positive for exceedances)
    df['Percent_Over_Limit'] = np.where(
        df['Is_Exceedance'] & _min_mask,
        ((df['Permit_Limit_Clean'] - df['Effective_Result']) / df['Permit_Limit_Clean']) * 100,
        np.where(
            df['Is_Exceedance'],
            ((df['Effective_Result'] - df['Permit_Limit_Clean']) / df['Permit_Limit_Clean']) * 100,
            0
        )
    )

    # NOTE: Severity column deliberately removed — we use pct_over (% over limit)
    # as a neutral numeric fact rather than severity classifications, per legal guidance.

    # 4. DATA QUALITY FLAGS
    def check_data_quality(row):
        issues = []
        
        if pd.isna(row.get('PERMIT_VALUE')) or row.get('PERMIT_VALUE', 0) == 0:
            issues.append('No permit limit')
        
        if pd.isna(row['Effective_Result']):
            issues.append('Invalid result')
            
        if pd.isna(row.get('UNIT_OF_MEASURE')) or str(row.get('UNIT_OF_MEASURE')).strip() == '':
            issues.append('Missing units')
            
        return '; '.join(issues) if issues else ''
    
    df['Data_Quality_Flag'] = df.apply(check_data_quality, axis=1)
    
    # 5. TIME GROUPINGS
    if 'MONITORING_PERIOD_BEGIN_DATE' in df.columns:
        df['Sample_Date'] = pd.to_datetime(df['MONITORING_PERIOD_BEGIN_DATE'], errors='coerce')
        df['Month_Bucket'] = df['Sample_Date'].dt.strftime('%Y-%m')
    else:
        df['Month_Bucket'] = ''
    
    # 6. PERIOD KEY (for deduplication)
    def make_compliance_key(row):
        month = row.get('Month_Bucket', '')
        outfall = row.get('OUTFALL_NUMBER', 'UNK')
        param_code = row.get('Parameter_Code', row.get('PARAMETER', 'UNK'))
        return f"{month}-{outfall}-{param_code}"
    
    df['Compliance_Period_Key'] = df.apply(make_compliance_key, axis=1)
    
    # 7. PROVENANCE FIELDS
    df['Source_File'] = 'TX_DMR_Data'  # Update this based on your file
    df['Ingested_At'] = datetime.now().isoformat()
    df['Row_Hash'] = df.apply(lambda x: hash(str(x.to_dict())), axis=1)
    
    return df

def add_chemical_laundering_flags(df):
    """
    Add basic chemical laundering detection flags
    """
    # Industrial parameters that indicate chemical laundering
    industrial_params = [
        'Aluminum, Total', 'Iron, Total', 'Manganese, Total',
        'Chromium', 'Lead', 'Mercury', 'Cadmium', 'Copper', 'Zinc',
        'Cyanide', 'Phenols', 'PCB', 'Benzene', 'Toluene'
    ]
    
    # Check if facility monitors industrial parameters
    df['Has_Industrial_Parameters'] = df['PARAMETER'].isin(industrial_params)
    
    # For each permit, flag if it has ANY industrial parameters
    permit_has_industrial = df[df['Has_Industrial_Parameters']]['PERMIT_NUMBER'].unique()
    df['Chemical_Laundering_Candidate'] = df['PERMIT_NUMBER'].isin(permit_has_industrial)
    
    return df

# Example usage
if __name__ == "__main__":
    # Load TX exceedance data
    raw_dmr = pd.read_csv('trimmed_tx_exceedances_2020_2024.csv')

    # Process for launch
    launch_ready = prepare_launch_ready_dmr(raw_dmr)
    launch_ready = add_chemical_laundering_flags(launch_ready)

    # Show exceedance summary
    exceedances = launch_ready[launch_ready['Is_Exceedance']]
    print(f"Found {len(exceedances)} exceedances")

    # Show chemical laundering candidates
    laundering_candidates = launch_ready[launch_ready['Chemical_Laundering_Candidate']]['PERMIT_NUMBER'].nunique()
    print(f"Chemical laundering candidates: {laundering_candidates} permits")

    # Save launch-ready data
    launch_ready.to_csv('tx_exceedances_launch_ready.csv', index=False)
    print("Launch-ready data saved as 'tx_exceedances_launch_ready.csv'!")

    # Quick preview of top exceedances
    print("\nTOP 10 WORST EXCEEDANCES:")
    top_exc = launch_ready[launch_ready['Is_Exceedance']].nlargest(10, 'Percent_Over_Limit')
    for _, row in top_exc.iterrows():
        print(f"   {row['PERMIT_NUMBER']}: {row['PARAMETER']} - {row['Percent_Over_Limit']:.0f}% over limit")

