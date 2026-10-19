"""
Profile LifeLink Donor Dataset
Strictly read-only profiling script for Phase C.1 ML Feasibility Audit.
"""

import sys
import os
import json
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def run_profiling(csv_path: str):
    print(f"=== Profiling: {csv_path} ===")
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        return

    file_size_bytes = os.path.getsize(csv_path)
    print(f"File size: {file_size_bytes:,} bytes ({file_size_bytes / (1024*1024):.2f} MB)")

    df = pd.read_csv(csv_path)
    rows, cols = df.shape
    print(f"Dimensions: {rows} rows, {cols} columns")

    # Column dtypes and nulls
    print("\n--- Columns and Missing Values ---")
    null_counts = df.isnull().sum()
    info_list = []
    for col in df.columns:
        info_list.append({
            "col": col,
            "dtype": str(df[col].dtype),
            "nulls": int(null_counts[col]),
            "pct_null": round(float(null_counts[col] / rows * 100), 2),
            "nunique": int(df[col].nunique())
        })
    print(pd.DataFrame(info_list).to_string())

    # Duplicates
    full_dupes = df.duplicated().sum()
    id_dupes = df['Donor_ID'].duplicated().sum()
    email_dupes = df['Email'].duplicated().sum()
    phone_dupes = df['Contact_Number'].duplicated().sum()
    print(f"\nExact duplicate rows: {full_dupes}")
    print(f"Duplicate Donor_IDs: {id_dupes}")
    print(f"Duplicate Emails: {email_dupes}")
    print(f"Duplicate Contact Numbers: {phone_dupes}")

    # Numeric summaries
    print("\n--- Numerical Columns Summary ---")
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    print(df[num_cols].describe().T[['count', 'mean', 'std', 'min', '25%', '50%', '75%', 'max']].to_string())

    # Categorical distributions
    cat_cols = df.select_dtypes(include=['object']).columns.tolist()
    print("\n--- Categorical Unique Values ---")
    for col in cat_cols:
        nu = df[col].nunique()
        print(f"\nColumn: {col} (Unique: {nu})")
        if nu <= 15:
            val_counts = df[col].value_counts(dropna=False)
            print(val_counts.to_string())
        else:
            top5 = df[col].value_counts(dropna=False).head(5)
            print(f"Top 5 values:\n{top5.to_string()}")

    # Potential Targets
    print("\n--- Potential Target Analysis ---")
    for candidate in ['Eligible_for_Donation', 'Availability', 'Eligibility_Reason']:
        if candidate in df.columns:
            print(f"\nDistribution of {candidate}:")
            print(df[candidate].value_counts(dropna=False))
            print(df[candidate].value_counts(normalize=True).mul(100).round(2).astype(str) + '%')

    # Relationship between Eligible_for_Donation and other features
    print("\n--- Cross-tabulation: Eligible_for_Donation vs Availability ---")
    if 'Eligible_for_Donation' in df.columns and 'Availability' in df.columns:
        print(pd.crosstab(df['Eligible_for_Donation'], df['Availability'], dropna=False))

    # Cross tab with medical conditions/fever/infection
    print("\n--- Cross-tabulation: Eligible_for_Donation vs Clinical Preconditions ---")
    for feature in ['Infection', 'Fever', 'Recent_Surgery', 'Medical_Condition', 'Taking_Medicine', 'Tattooed', 'Recently_Donated']:
        if feature in df.columns:
            print(f"\nEligible_for_Donation vs {feature}:")
            print(pd.crosstab(df['Eligible_for_Donation'], df[feature], dropna=False))

    # Reason breakdown for Ineligible
    if 'Eligibility_Reason' in df.columns and 'Eligible_for_Donation' in df.columns:
        print("\n--- Eligibility_Reason when Eligible_for_Donation == 'No' ---")
        ineligible_reasons = df[df['Eligible_for_Donation'] == 'No']['Eligibility_Reason'].value_counts()
        print(ineligible_reasons.head(10))

        print("\n--- Eligibility_Reason when Eligible_for_Donation == 'Yes' ---")
        eligible_reasons = df[df['Eligible_for_Donation'] == 'Yes']['Eligibility_Reason'].value_counts()
        print(eligible_reasons.head(5))

    # Date ranges
    print("\n--- Date Ranges ---")
    for date_col in ['Registration_Date', 'Last_Donation_Date', 'Tattoo_Date']:
        if date_col in df.columns:
            parsed = pd.to_datetime(df[date_col], format='%d-%m-%Y', errors='coerce')
            print(f"{date_col}: Min = {parsed.min()}, Max = {parsed.max()}, Invalid/NaT = {parsed.isna().sum()}")

if __name__ == '__main__':
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "d:/Life link 🖤🖤/LifeLink_Realistic_Synthetic_30K_Donors.csv"
    run_profiling(csv_file)
