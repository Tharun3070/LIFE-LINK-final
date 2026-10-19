"""
LifeLink ML Readiness & Interaction Data Audit CLI
File: backend/scripts/audit_interaction_readiness.py

Executes a read-only audit of recorded donor interactions and reports on:
1. Total interactions and emergency diversity.
2. Synthetic vs. non-synthetic provenance counts.
3. Outcome distributions across lifecycle stages.
4. Timestamp, latency, and data integrity health.
5. Eligible samples for candidate prediction targets (Response, Acceptance, Completion).
6. Clear readiness verdict against minimum sample thresholds (zero data fabrication).
"""

import sys
import os
import argparse
import json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import SessionLocal, engine as default_engine
from app.services.ml_audit_service import MLAuditService


def mask_db_url(url_str: str) -> str:
    """Safely mask password credentials in database connection strings."""
    if "@" in url_str and "://" in url_str:
        scheme, rest = url_str.split("://", 1)
        creds, host_part = rest.split("@", 1)
        if ":" in creds:
            user, _ = creds.split(":", 1)
            return f"{scheme}://{user}:***@{host_part}"
        return f"{scheme}://***@{host_part}"
    return url_str


def format_report_text(report: dict, db_info: str = "") -> str:
    lines = [
        "================================================================================",
        "             LIFELINK ML READINESS & INTERACTION DATA AUDIT REPORT              ",
        "================================================================================",
        f"Audit Generated At: {report.get('audit_timestamp')}",
    ]
    if db_info:
        lines.append(f"Database Target:    {db_info}")
    lines.extend([
        "",
        "--- 1. INTERACTION VOLUME & DIVERSITY ---",
        f"  Total Interaction Records:      {report['volume']['total_interactions']}",
        f"  Distinct Emergencies:           {report['volume']['distinct_emergencies']}",
        f"  Distinct Candidate Donors:      {report['volume']['distinct_donors']}",
        "",
        "--- 2. PROVENANCE BREAKDOWN ---",
        f"  Production / Real Dispatches:   {report['provenance']['production_records']}",
        f"  Synthetic / Benchmark Records:  {report['provenance']['synthetic_records']}",
        f"  Provenance Breakdown:           {report['provenance']['breakdown']}",
        "",
        "--- 3. LIFECYCLE & OUTCOME DISTRIBUTIONS ---",
        f"  Contact Statuses:               {report['lifecycle_outcomes']['contact_status']}",
        f"  Response Statuses:              {report['lifecycle_outcomes']['response_status']}",
        f"  Acceptance Statuses:            {report['lifecycle_outcomes']['acceptance_status']}",
        f"  Completion Statuses:            {report['lifecycle_outcomes']['completion_status']}",
        "",
        "--- 4. DATA INTEGRITY & TIMESTAMPS ---",
        f"  Missing Attempt Timestamps:     {report['data_integrity']['missing_attempt_timestamps']}",
        f"  Missing Response Timestamps:    {report['data_integrity']['missing_response_timestamps']}",
        f"  Negative Latencies:             {report['data_integrity']['negative_latencies']}",
        f"  Chronology Order Violations:    {report['data_integrity']['chronology_errors']}",
        f"  Conflicting Lifecycle States:   {report['data_integrity']['conflicting_states']}",
        f"  Duplicate Active Pending Pairs: {report['data_integrity']['duplicate_pending_pairs']}",
        f"  Integrity Checks Passed:        {'YES' if report['data_integrity']['passed_integrity_checks'] else 'NO'}",
        "",
        "--- 5. RESPONSE LATENCY METRICS ---",
        f"  Observed Latencies Count:       {report['latency_metrics']['observed_count']} ({report['latency_metrics']['coverage_pct']}% of total)",
        f"  Mean Latency:                   {report['latency_metrics']['mean_seconds']} seconds" if report['latency_metrics']['mean_seconds'] else "  Mean Latency:                   N/A (unobserved)",
        f"  Min / Max Latency:              {report['latency_metrics']['min_seconds']}s / {report['latency_metrics']['max_seconds']}s" if report['latency_metrics']['min_seconds'] else "  Min / Max Latency:              N/A",
        "",
        "--- 6. TARGET-SPECIFIC ML TRAINING ELIGIBILITY ---",
        "  Target A: Response Propensity P(Response | Dispatch Attempt):",
        f"    Eligible Production Records:  {report['prediction_targets']['target_a_response_propensity']['eligible_records']}",
        f"    Positives (Responded):        {report['prediction_targets']['target_a_response_propensity']['positive_count (responded)']}",
        f"    Negatives (No Response):      {report['prediction_targets']['target_a_response_propensity']['negative_count (no_response/expired)']}",
        f"    Positive Ratio:               {report['prediction_targets']['target_a_response_propensity']['positive_ratio']}",
        "",
        "  Target B: Acceptance Propensity P(Accepted | Responded):",
        f"    Eligible Production Records:  {report['prediction_targets']['target_b_acceptance_propensity']['eligible_records']}",
        f"    Positives (Accepted):         {report['prediction_targets']['target_b_acceptance_propensity']['positive_count (accepted)']}",
        f"    Negatives (Declined):         {report['prediction_targets']['target_b_acceptance_propensity']['negative_count (declined)']}",
        f"    Positive Ratio:               {report['prediction_targets']['target_b_acceptance_propensity']['positive_ratio']}",
        "",
        "  Target C: Donation Completion P(Completed | Accepted):",
        f"    Eligible Production Records:  {report['prediction_targets']['target_c_donation_completion']['eligible_records']}",
        f"    Positives (Completed):        {report['prediction_targets']['target_c_donation_completion']['positive_count (completed)']}",
        f"    Negatives (Deferred/No-show): {report['prediction_targets']['target_c_donation_completion']['negative_count (deferred/no_show)']}",
        f"    Positive Ratio:               {report['prediction_targets']['target_c_donation_completion']['positive_ratio']}",
        "",
        "================================================================================",
        "--- 7. FINAL ML READINESS VERDICT ---",
        f"  Status:                         {report['verdict']['status']}",
        f"  Ready For Supervised Training:  {'YES' if report['verdict']['is_ready_for_training'] else 'NO'}",
        f"  MVD Threshold:                  {report['verdict']['minimum_required_records']} production interactions across {report['verdict']['minimum_required_emergencies']} emergencies",
    ])

    if report['verdict']['blocking_reasons']:
        lines.append("  Blocking Reasons:")
        for reason in report['verdict']['blocking_reasons']:
            lines.append(f"    - {reason}")

    lines.append("")
    lines.append(f"  Recommendation:                 {report['verdict']['recommendation']}")
    lines.append("================================================================================")
    return "\n".join(lines)


from sqlalchemy import inspect


def main():
    parser = argparse.ArgumentParser(description="LifeLink ML Readiness & Interaction Data Audit Tool")
    parser.add_argument("--json", action="store_true", help="Output audit results as formatted JSON")
    parser.add_argument("--db-path", type=str, default=None, help="Target SQLite database file path to audit")
    parser.add_argument("--db-url", type=str, default=None, help="Target SQLAlchemy database URL to audit")
    args = parser.parse_args()

    custom_engine = None
    target_engine = None

    if args.db_path:
        abs_path = os.path.abspath(args.db_path)
        if not os.path.exists(abs_path):
            error_data = {
                "error": f"Database file not found: {abs_path}",
                "status": "DATABASE_NOT_FOUND",
                "database_target": f"sqlite:///{abs_path}",
            }
            if args.json:
                print(json.dumps(error_data, indent=2))
            else:
                print(f"ERROR: Database file not found: {abs_path}", file=sys.stderr)
            sys.exit(2)

        custom_engine = create_engine(f"sqlite:///{abs_path}", connect_args={"check_same_thread": False})
        target_engine = custom_engine
        SessionCls = sessionmaker(autocommit=False, autoflush=False, bind=custom_engine)
        db = SessionCls()
        db_target_str = f"sqlite:///{abs_path}"
    elif args.db_url:
        is_sq = args.db_url.startswith("sqlite")
        if is_sq and not args.db_url.startswith("sqlite:///:memory:"):
            sq_path = os.path.abspath(args.db_url.replace("sqlite:///", ""))
            if not os.path.exists(sq_path):
                error_data = {
                    "error": f"SQLite database file not found: {sq_path}",
                    "status": "DATABASE_NOT_FOUND",
                    "database_target": mask_db_url(args.db_url),
                }
                if args.json:
                    print(json.dumps(error_data, indent=2))
                else:
                    print(f"ERROR: SQLite database file not found: {sq_path}", file=sys.stderr)
                sys.exit(2)

        try:
            custom_engine = create_engine(args.db_url, connect_args={"check_same_thread": False} if is_sq else {})
            target_engine = custom_engine
            SessionCls = sessionmaker(autocommit=False, autoflush=False, bind=custom_engine)
            db = SessionCls()
            db_target_str = mask_db_url(args.db_url)
        except Exception as e:
            error_data = {
                "error": f"Failed to initialize database connection: {e}",
                "status": "CONNECTION_FAILED",
                "database_target": mask_db_url(args.db_url),
            }
            if args.json:
                print(json.dumps(error_data, indent=2))
            else:
                print(f"ERROR: Failed to connect to database: {e}", file=sys.stderr)
            sys.exit(4)
    else:
        target_engine = default_engine
        db = SessionLocal()
        raw_url = str(default_engine.url)
        db_target_str = mask_db_url(raw_url)
        if raw_url.startswith("sqlite:///"):
            path_part = raw_url.replace("sqlite:///", "")
            db_target_str = f"{raw_url} (Resolved: {os.path.abspath(path_part)})"

    # Schema completeness check: Ensure interaction ledger table exists before querying
    try:
        inspector = inspect(target_engine)
        if not inspector.has_table("donor_emergency_interactions"):
            error_data = {
                "error": "Database schema incomplete: table 'donor_emergency_interactions' does not exist in target database.",
                "status": "SCHEMA_INCOMPLETE",
                "database_target": db_target_str,
            }
            if args.json:
                print(json.dumps(error_data, indent=2))
            else:
                print(f"ERROR: Schema incomplete: table 'donor_emergency_interactions' does not exist in target database ({db_target_str}).", file=sys.stderr)
            sys.exit(3)
    except Exception as e:
        error_data = {
            "error": f"Database inspection failed: {e}",
            "status": "INSPECTION_FAILED",
            "database_target": db_target_str,
        }
        if args.json:
            print(json.dumps(error_data, indent=2))
        else:
            print(f"ERROR: Database inspection failed: {e}", file=sys.stderr)
        sys.exit(4)

    try:
        report = MLAuditService.audit_interactions(db)
        if args.json:
            report["database_target"] = db_target_str
            print(json.dumps(report, indent=2))
        else:
            print(format_report_text(report, db_info=db_target_str))
    finally:
        db.close()
        if custom_engine:
            custom_engine.dispose()


if __name__ == "__main__":
    main()
