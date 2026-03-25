"""Extraction service — sends files to invoice-extractor and polls for results."""

import json
import os

import frappe

from invoice_connector.api.client import get_extractor_client, get_settings


def start_extraction(queue_name: str):
    """Send the uploaded file to invoice-extractor for processing.

    Called as a background job from InvoiceQueue.after_insert().

    Flow:
        1. Read the attached file from this ERPNext site
        2. POST to extractor's /extract endpoint
        3. Store the txn_id for polling
        4. Status: Queued → Extracting
    """
    doc = frappe.get_doc("Invoice Queue", queue_name)

    try:
        doc.status = "Extracting"
        doc.append_log("Sending file to extractor...")
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        # Read the attached file
        file_url = doc.file
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        file_path = file_doc.get_full_path()

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_name = os.path.basename(file_path)

        # Send to extractor
        settings = get_settings()
        with get_extractor_client(timeout=180) as client:
            with open(file_path, "rb") as f:
                params = {}
                if settings.extractor_provider:
                    params["provider"] = settings.extractor_provider
                if settings.extractor_model:
                    params["model"] = settings.extractor_model

                response = client.post(
                    "/extract",
                    files={"file": (file_name, f)},
                    params=params if params else None,
                )

            if response.status_code != 200:
                raise Exception(f"Extractor returned HTTP {response.status_code}: {response.text}")

            result = response.json()
            txn_id = result.get("txn_id")

            if not txn_id:
                raise Exception(f"No txn_id in extractor response: {result}")

            doc.extractor_txn_id = txn_id
            doc.append_log(f"Extraction started. Transaction ID: {txn_id}")
            doc.save(ignore_permissions=True)
            frappe.db.commit()

    except Exception as e:
        doc.status = "Failed"
        doc.error_message = str(e)
        doc.append_log(f"Extraction failed: {e}")
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.log_error(f"Invoice extraction failed for {queue_name}: {e}")


def poll_extraction_result(queue_name: str):
    """Poll the extractor for a completed result.

    Called by the scheduler or manually.

    Flow:
        1. GET /status/{txn_id} to check if extraction is done
        2. If completed, GET /result/{txn_id} to fetch full result
        3. Store extracted data, update status
        4. Optionally auto-send to mapper
    """
    doc = frappe.get_doc("Invoice Queue", queue_name)

    if doc.status != "Extracting" or not doc.extractor_txn_id:
        return

    try:
        with get_extractor_client() as client:
            # Check status
            status_response = client.get(f"/status/{doc.extractor_txn_id}")
            if status_response.status_code != 200:
                return  # Retry later

            status_data = status_response.json()
            extraction_status = status_data.get("status", "")

            if extraction_status == "processing":
                return  # Still working, check again later

            if extraction_status == "failed":
                doc.status = "Failed"
                doc.error_message = status_data.get("error", "Extraction failed")
                doc.append_log(f"Extraction failed: {doc.error_message}")
                doc.save(ignore_permissions=True)
                frappe.db.commit()
                return

            if extraction_status != "completed":
                return  # Unknown status, retry later

            # Fetch full result
            result_response = client.get(f"/result/{doc.extractor_txn_id}")
            if result_response.status_code != 200:
                return

            result = result_response.json()

            # Store extraction data
            invoice_data = result.get("invoice", {})
            metrics = result.get("metrics", {})
            validation = result.get("validation", {})

            doc.extracted_data = json.dumps(invoice_data)
            doc.extraction_confidence = validation.get("score_pct", 0)
            doc.extraction_provider = metrics.get("provider", "")
            doc.extraction_model = metrics.get("model", "")
            doc.extraction_cost = metrics.get("estimated_cost_usd", 0)
            doc.status = "Extracted"
            doc.append_log(
                f"Extraction complete. Confidence: {doc.extraction_confidence}%, "
                f"Provider: {doc.extraction_provider}/{doc.extraction_model}, "
                f"Cost: ${doc.extraction_cost:.4f}"
            )
            doc.save(ignore_permissions=True)
            frappe.db.commit()

            # Auto-send to mapper
            settings = get_settings()
            if settings.mapper_site_id:
                frappe.enqueue(
                    "invoice_connector.api.mapping.send_to_mapper",
                    queue_name=queue_name,
                    queue="short",
                    is_async=True,
                )

    except Exception as e:
        frappe.log_error(f"Polling extraction for {queue_name} failed: {e}")
