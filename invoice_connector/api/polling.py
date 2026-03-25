"""Scheduler job: polls extractor for all invoices stuck in 'Extracting' status."""

import frappe

from invoice_connector.api.extract import poll_extraction_result


def poll_pending_extractions():
    """Called by scheduler every minute. Polls all invoices in 'Extracting' state."""
    pending = frappe.get_all(
        "Invoice Queue",
        filters={"status": "Extracting", "extractor_txn_id": ["is", "set"]},
        pluck="name",
        limit=50,
    )

    for queue_name in pending:
        try:
            poll_extraction_result(queue_name)
        except Exception as e:
            frappe.log_error(f"Polling failed for {queue_name}: {e}")
