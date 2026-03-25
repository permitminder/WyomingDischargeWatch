# check_new_exceedances.py - Finds genuinely new exceedances vs yesterday
import pandas as pd
import json
import os
from datetime import datetime, timedelta
import hashlib

class NewExceedanceDetector:
    def __init__(self, data_dir="./data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
    def get_today_filename(self):
        """Generate filename for today's exceedances"""
        return f"{self.data_dir}/exceedances_{datetime.now().strftime('%Y_%m_%d')}.csv"
    
    def get_yesterday_filename(self):
        """Generate filename for yesterday's exceedances"""
        yesterday = datetime.now() - timedelta(days=1)
        return f"{self.data_dir}/exceedances_{yesterday.strftime('%Y_%m_%d')}.csv"
    
    def create_exceedance_hash(self, exceedance_row):
        """Create unique hash for exceedance to detect duplicates"""
        # Use permit + parameter + date + value to create unique ID
        key_parts = [
            str(exceedance_row.get('PERMIT_NUMBER', '')),
            str(exceedance_row.get('PARAMETER', '')),
            str(exceedance_row.get('NON_COMPLIANCE_DATE', '')),
            str(exceedance_row.get('SAMPLE_VALUE', ''))
        ]
        key_string = '|'.join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def load_exceedances_file(self, filename):
        """Load exceedances CSV and add hash column"""
        try:
            df = pd.read_csv(filename)
            if df.empty:
                return df
            
            # Add hash column for comparison
            df['exceedance_hash'] = df.apply(self.create_exceedance_hash, axis=1)
            return df
        except FileNotFoundError:
            print(f"File not found: {filename}")
            return pd.DataFrame()
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            return pd.DataFrame()
    
    def find_new_exceedances(self, recent_days=30):
        """Find exceedances that are new compared to yesterday"""
        
        # Load today's and yesterday's data
        today_file = self.get_today_filename()
        yesterday_file = self.get_yesterday_filename()
        
        print(f"Checking for new exceedances...")
        print(f"Today's file: {today_file}")
        print(f"Yesterday's file: {yesterday_file}")
        
        today_df = self.load_exceedances_file(today_file)
        yesterday_df = self.load_exceedances_file(yesterday_file)
        
        if today_df.empty:
            print("No today's exceedances found")
            return pd.DataFrame()
        
        print(f"Today's exceedances: {len(today_df)}")
        print(f"Yesterday's exceedances: {len(yesterday_df)}")
        
        # If no yesterday file, all exceedances are "new" but filter by date
        if yesterday_df.empty:
            print("No yesterday file - filtering by recent dates only")
            new_exceedances = self.filter_recent_exceedances(today_df, recent_days)
        else:
            # Find exceedances with hashes not in yesterday's data
            yesterday_hashes = set(yesterday_df['exceedance_hash'])
            new_exceedances = today_df[~today_df['exceedance_hash'].isin(yesterday_hashes)]
            
            # Also filter by date to ignore old exceedances that might appear
            new_exceedances = self.filter_recent_exceedances(new_exceedances, recent_days)
        
        print(f"New exceedances found: {len(new_exceedances)}")
        return new_exceedances
    
    def filter_recent_exceedances(self, df, recent_days=30):
        """Filter to exceedances from recent days only"""
        if df.empty:
            return df
        
        cutoff_date = datetime.now() - timedelta(days=recent_days)
        
        # Convert date column to datetime
        df['date_check'] = pd.to_datetime(df['NON_COMPLIANCE_DATE'], errors='coerce')
        
        # Filter to recent exceedances
        recent_df = df[df['date_check'] >= cutoff_date].copy()
        
        print(f"Filtered to {len(recent_df)} recent exceedances (last {recent_days} days)")
        return recent_df
    
    def save_new_exceedances(self, new_exceedances_df):
        """Save new exceedances for alert processing"""
        if new_exceedances_df.empty:
            return None
        
        filename = f"{self.data_dir}/new_exceedances_{datetime.now().strftime('%Y_%m_%d')}.csv"
        new_exceedances_df.to_csv(filename, index=False)
        print(f"Saved {len(new_exceedances_df)} new exceedances to {filename}")
        return filename
    
    def run_daily_check(self):
        """Main function to run daily new exceedance detection"""
        print(f"\n=== Daily Exceedance Check - {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
        
        # Find new exceedances
        new_exceedances = self.find_new_exceedances()
        
        if new_exceedances.empty:
            print("No new exceedances detected today")
            return None
        
        # Save new exceedances file
        new_exceedances_file = self.save_new_exceedances(new_exceedances)
        
        # Log summary
        print(f"\n=== Summary ===")
        print(f"New exceedances: {len(new_exceedances)}")
        
        # Show breakdown by % over limit range
        if 'pct_over' in new_exceedances.columns:
            pct = pd.to_numeric(new_exceedances['pct_over'], errors='coerce')
            print(f"  0-50% over: {((pct >= 0) & (pct < 50)).sum()}")
            print(f"  50-100% over: {((pct >= 50) & (pct < 100)).sum()}")
            print(f"  100-200% over: {((pct >= 100) & (pct < 200)).sum()}")
            print(f"  200%+ over: {(pct >= 200).sum()}")
        
        return new_exceedances_file

# daily_scraper.py - Runs your existing scraper and saves with date
import subprocess
import sys
from datetime import datetime
import shutil

class DailyScraper:
    def __init__(self):
        self.today_str = datetime.now().strftime('%Y_%m_%d')
        
    def run_scraper(self):
        """Run your existing ECHO DMR scraper"""
        print(f"Running ECHO DMR scraper for {self.today_str}...")
        
        try:
            # Run your existing scraper script
            # Replace 'your_scraper.py' with your actual scraper filename
            result = subprocess.run([
                sys.executable, 'process_exceedances.py'
            ], capture_output=True, text=True, timeout=1800)  # 30 min timeout
            
            if result.returncode == 0:
                print("Scraper completed successfully")
                
                # Move the output file to dated version
                source_file = 'tx_exceedances_launch_ready.csv'
                dest_file = f'data/exceedances_{self.today_str}.csv'
                
                if os.path.exists(source_file):
                    shutil.copy2(source_file, dest_file)
                    print(f"Saved daily data to {dest_file}")
                    return dest_file
                else:
                    print(f"Warning: Expected output file {source_file} not found")
                    return None
            else:
                print(f"Scraper failed with return code {result.returncode}")
                print(f"Error: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print("Scraper timed out after 30 minutes")
            return None
        except Exception as e:
            print(f"Error running scraper: {e}")
            return None

# daily_alerts.py - Send alerts for new exceedances only
import csv

class DailyAlertSystem:
    def __init__(self, gmail_email=None, gmail_password=None):
        self.gmail_email = gmail_email
        self.gmail_password = gmail_password
        
    def load_subscriptions(self):
        """Load email subscriptions from Streamlit app"""
        subscriptions = {}
        
        try:
            with open('alert_subscriptions.csv', 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    email = row['email']
                    permits = row['permits'].split(',')
                    
                    if email not in subscriptions:
                        subscriptions[email] = {
                            'permits': [],
                            'frequency': row.get('frequency', 'daily')
                        }
                    
                    subscriptions[email]['permits'].extend(permits)
            
            print(f"Loaded {len(subscriptions)} email subscriptions")
            return subscriptions
            
        except FileNotFoundError:
            print("No subscriptions file found")
            return {}
    
    def filter_exceedances_for_subscriber(self, exceedances_df, subscriber_permits):
        """Filter exceedances to only those for subscribed permits"""
        if exceedances_df.empty:
            return exceedances_df
        
        return exceedances_df[exceedances_df['PERMIT_NUMBER'].isin(subscriber_permits)]
    
    def send_daily_alerts(self, new_exceedances_file):
        """Send alerts for today's new exceedances"""
        if not new_exceedances_file or not os.path.exists(new_exceedances_file):
            print("No new exceedances file to process")
            return
        
        # Load new exceedances
        new_exceedances = pd.read_csv(new_exceedances_file)
        if new_exceedances.empty:
            print("No new exceedances to alert on")
            return
        
        # Load subscriptions
        subscriptions = self.load_subscriptions()
        if not subscriptions:
            print("No subscriptions - no alerts to send")
            return
        
        print(f"Processing alerts for {len(new_exceedances)} new exceedances")
        
        # Send alerts to each subscriber
        alerts_sent = 0
        for email, settings in subscriptions.items():
            
            # Filter exceedances for this subscriber's permits
            subscriber_exceedances = self.filter_exceedances_for_subscriber(
                new_exceedances, settings['permits']
            )
            
            if not subscriber_exceedances.empty:
                success = self.send_exceedance_alert(email, subscriber_exceedances)
                if success:
                    alerts_sent += 1
                    
        print(f"Sent {alerts_sent} alert emails")
    
    def send_exceedance_alert(self, email, exceedances_df):
        """Send individual exceedance alert email"""
        # Import your existing alert system
        from exceedance_alerts import ExceedanceAlertSystem
        
        alert_system = ExceedanceAlertSystem(self.gmail_email, self.gmail_password)
        
        # Convert DataFrame to exceedance format
        exceedances_list = []
        for _, row in exceedances_df.iterrows():
            exceedances_list.append({
                'permit': row['PERMIT_NUMBER'],
                'facility': row['PF_NAME'],
                'county': row['COUNTY_NAME'],
                'date': row['NON_COMPLIANCE_DATE'],
                'parameter': row['PARAMETER'],
                'exceedance_percent': row.get('Percent_Over_Limit', 'N/A'),
                'sample_value': row.get('SAMPLE_VALUE', 'N/A'),
                'permit_value': row.get('PERMIT_VALUE', 'N/A'),
                'unit': row.get('UNIT_OF_MEASURE', 'N/A')
            })
        
        # Format and send email
        subject, body = alert_system.format_alert_email(exceedances_list, email)
        if subject and body:
            return alert_system.send_email(email, subject, body)
        
        return False

# main.py - Orchestrates the daily monitoring process
def main():
    """Main daily monitoring process"""
    print(f"\n{'='*60}")
    print(f"EFFLUENTWATCH DAILY MONITORING")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    # Step 1: Run scraper to get today's data
    scraper = DailyScraper()
    scraper_result = scraper.run_scraper()
    
    if not scraper_result:
        print("❌ Scraper failed - aborting daily check")
        return False
    
    # Step 2: Detect new exceedances vs yesterday
    detector = NewExceedanceDetector()
    new_exceedances_file = detector.run_daily_check()
    
    # Step 3: Send alerts for new exceedances
    if new_exceedances_file:
        # Get email credentials from environment variables
        gmail_email = os.environ.get('GMAIL_EMAIL')
        gmail_password = os.environ.get('GMAIL_PASSWORD')
        
        alert_system = DailyAlertSystem(gmail_email, gmail_password)
        alert_system.send_daily_alerts(new_exceedances_file)
    
    print(f"\n✅ Daily monitoring completed at {datetime.now().strftime('%H:%M:%S')}")
    return True

if __name__ == "__main__":
    main()