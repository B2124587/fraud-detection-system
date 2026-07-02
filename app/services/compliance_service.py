"""Compliance reporting — BoZ monthly summary and audit exports."""
import csv
import json
import os
import uuid
from datetime import datetime
from io import StringIO
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.orm_models import (
    Transaction, FraudAlert, AuditLog, ComplianceReport,
    AlertStatus, RiskScore
)


def generate_monthly_report(
    db: Session,
    period_start: datetime,
    period_end: datetime,
    generated_by: int,
    report_dir: str = "./reports",
) -> dict:
    """Generate BoZ monthly compliance report."""
    os.makedirs(report_dir, exist_ok=True)
    report_id = str(uuid.uuid4())

    # Aggregate metrics for period
    total_txns = db.query(func.count(Transaction.id)).filter(
        Transaction.timestamp.between(period_start, period_end)
    ).scalar() or 0

    total_flagged = db.query(func.count(FraudAlert.id)).filter(
        FraudAlert.created_at.between(period_start, period_end)
    ).scalar() or 0

    confirmed = db.query(func.count(FraudAlert.id)).filter(
        FraudAlert.created_at.between(period_start, period_end),
        FraudAlert.status == AlertStatus.CONFIRMED_FRAUD,
    ).scalar() or 0

    false_pos = db.query(func.count(FraudAlert.id)).filter(
        FraudAlert.created_at.between(period_start, period_end),
        FraudAlert.status == AlertStatus.FALSE_POSITIVE,
    ).scalar() or 0

    fraud_amount = db.query(func.sum(Transaction.amount)).filter(
        Transaction.timestamp.between(period_start, period_end),
        Transaction.is_fraud == True,
    ).scalar() or 0.0

    # Build CSV content
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "BoZ Compliance Report",
        f"Period: {period_start.date()} to {period_end.date()}",
        f"Generated: {datetime.utcnow().isoformat()}",
    ])
    writer.writerow([])
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Total Transactions", total_txns])
    writer.writerow(["Total Flagged Alerts", total_flagged])
    writer.writerow(["Confirmed Fraud Cases", confirmed])
    writer.writerow(["False Positives", false_pos])
    writer.writerow(["Total Fraud Amount (ZMW)", f"{fraud_amount:,.2f}"])
    writer.writerow(["Detection Precision", f"{confirmed / max(confirmed + false_pos, 1):.2%}"])
    writer.writerow([])

    # Detailed fraud alerts
    writer.writerow(["Alert ID", "Transaction ID", "Status", "Amount (ZMW)", "Risk Score", "Fraud Type", "Resolved At"])
    alerts = db.query(FraudAlert).join(Transaction, FraudAlert.transaction_id == Transaction.id).filter(
        FraudAlert.created_at.between(period_start, period_end)
    ).all()

    for alert in alerts:
        txn = alert.transaction
        rs = txn.risk_score if txn else None
        writer.writerow([
            alert.alert_id,
            txn.transaction_id if txn else "",
            alert.status,
            txn.amount if txn else "",
            rs.risk_score if rs else "",
            alert.fraud_type or "",
            alert.resolved_at.isoformat() if alert.resolved_at else "",
        ])

    csv_content = output.getvalue()
    report_path = f"{report_dir}/boz_report_{report_id[:8]}.csv"
    with open(report_path, "w") as f:
        f.write(csv_content)

    # Save to DB
    report = ComplianceReport(
        report_id=report_id,
        report_type="MONTHLY_SUMMARY",
        period_start=period_start,
        period_end=period_end,
        generated_by=generated_by,
        total_transactions=total_txns,
        total_flagged=total_flagged,
        confirmed_fraud=confirmed,
        false_positives=false_pos,
        total_fraud_amount_zmw=round(float(fraud_amount), 2),
        report_path=report_path,
    )
    db.add(report)
    db.commit()

    return {
        "report_id": report_id,
        "report_path": report_path,
        "period": f"{period_start.date()} to {period_end.date()}",
        "summary": {
            "total_transactions": total_txns,
            "total_flagged": total_flagged,
            "confirmed_fraud": confirmed,
            "false_positives": false_pos,
            "fraud_amount_zmw": round(float(fraud_amount), 2),
        },
        "csv_content": csv_content,
    }


def export_audit_log(
    db: Session,
    start: datetime,
    end: datetime,
    event_type: Optional[str] = None,
) -> str:
    """Export audit log as CSV for BoZ regulatory submission."""
    query = db.query(AuditLog).filter(
        AuditLog.timestamp.between(start, end)
    )
    if event_type:
        query = query.filter(AuditLog.event_type == event_type)

    logs = query.order_by(AuditLog.timestamp.desc()).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Log ID", "Event Type", "Operator ID", "Transaction Ref",
                     "Timestamp", "Result", "IP Address", "Metadata"])
    for log in logs:
        writer.writerow([
            log.log_id, log.event_type, log.operator_id,
            log.transaction_ref, log.timestamp.isoformat(),
            log.result, log.ip_address, log.metadata_json,
        ])

    return output.getvalue()
