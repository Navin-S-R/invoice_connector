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
