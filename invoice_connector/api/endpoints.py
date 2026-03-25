"""Whitelisted API endpoints callable from frontend or external systems."""

import frappe


@frappe.whitelist()
def upload_invoice(file_url: str, company: str) -> dict:
    """Create an Invoice Queue entry from a file URL.

    Called from the frontend or via API:
        POST /api/method/invoice_connector.api.endpoints.upload_invoice
        Body: { file_url: "/files/invoice.pdf", company: "My Company" }
    """
    doc = frappe.get_doc(
        {
            "doctype": "Invoice Queue",
            "file": file_url,
            "company": company,
        }
    )
    doc.insert()
    frappe.db.commit()

    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_queue_status(name: str) -> dict:
    """Get the current status of an Invoice Queue entry.

    Called from frontend for polling:
        GET /api/method/invoice_connector.api.endpoints.get_queue_status?name=IQ-00001
    """
    doc = frappe.get_doc("Invoice Queue", name)

    return {
        "name": doc.name,
        "status": doc.status,
        "extraction_confidence": doc.extraction_confidence,
        "purchase_invoice": doc.purchase_invoice,
        "error_message": doc.error_message,
    }


@frappe.whitelist()
def bulk_upload(file_urls: list, company: str) -> list:
    """Upload multiple invoices at once.

    POST /api/method/invoice_connector.api.endpoints.bulk_upload
    Body: { file_urls: ["/files/inv1.pdf", "/files/inv2.pdf"], company: "My Company" }
    """
    import json

    if isinstance(file_urls, str):
        file_urls = json.loads(file_urls)

    results = []
    for file_url in file_urls:
        try:
            result = upload_invoice(file_url, company)
            results.append(result)
        except Exception as e:
            results.append({"file_url": file_url, "error": str(e)})

    return results


@frappe.whitelist()
def sync_master_data() -> dict:
    """Manually trigger master data sync to mapper.

    POST /api/method/invoice_connector.api.endpoints.sync_master_data
    """
    from invoice_connector.api.sync import sync_master_data_to_mapper

    sync_master_data_to_mapper()
    return {"status": "ok", "message": "Master data synced to mapper"}


@frappe.whitelist()
def test_connections() -> dict:
    """Test connectivity to extractor and mapper services.

    GET /api/method/invoice_connector.api.endpoints.test_connections
    """
    settings = frappe.get_single("Invoice Processing Settings")
    return settings.test_connections()


@frappe.whitelist()
def register_site() -> dict:
    """Register this ERPNext site with the mapper service.

    POST /api/method/invoice_connector.api.endpoints.register_site
    """
    settings = frappe.get_single("Invoice Processing Settings")
    return settings.register_site()


@frappe.whitelist()
def build_mapped_data_from_extracted(queue_name: str) -> dict:
    """Build mapped_data by unwrapping confidence wrappers from extracted_data.

    This allows creating a Purchase Invoice directly from the review page
    without needing the mapper service running.
    """
    import json

    doc = frappe.get_doc("Invoice Queue", queue_name)
    if not doc.extracted_data:
        frappe.throw("No extracted data available")

    extracted = json.loads(doc.extracted_data)
    mapped = _unwrap_extracted(extracted)

    doc.mapped_data = json.dumps(mapped)
    if doc.status in ("Extracted", "Review", "Failed"):
        doc.status = "Mapped"
    doc.append_log("Built mapped data from reviewed extraction (no mapper)")
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return mapped


def _unwrap_extracted(data: dict) -> dict:
    """Recursively unwrap {value, confidence_score} wrappers to plain values."""
    result = {}

    for key, val in data.items():
        if key == "items" and isinstance(val, list):
            result["items"] = [_unwrap_item(item) for item in val]
        elif key == "taxes" and isinstance(val, list):
            result["taxes"] = [_unwrap_item(tax) for tax in val]
        elif isinstance(val, dict) and "value" in val:
            result[key] = val["value"]
        elif isinstance(val, dict):
            # Nested object (address, tax_ids, bank) — unwrap each field
            result[key] = {
                k: v.get("value", v) if isinstance(v, dict) and "value" in v else v
                for k, v in val.items()
            }
        else:
            result[key] = val

    return result


def _unwrap_item(item: dict) -> dict:
    """Unwrap a single line item or tax row."""
    result = {}
    for key, val in item.items():
        if isinstance(val, dict) and "value" in val:
            result[key] = val["value"]
        else:
            result[key] = val
    return result
