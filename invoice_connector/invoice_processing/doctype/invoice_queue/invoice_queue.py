import json

import frappe
from frappe.model.document import Document


class InvoiceQueue(Document):
    def after_insert(self):
        """Automatically start extraction when a new queue entry is created."""
        frappe.enqueue(
            "invoice_connector.api.extract.start_extraction",
            queue_name=self.name,
            queue="short",
            is_async=True,
        )
        self.append_log("Invoice queued for extraction")

    def append_log(self, message):
        """Append a timestamped message to the processing log."""
        import datetime

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current = self.processing_log or ""
        self.processing_log = f"{current}[{ts}] {message}\n"
        self.save(ignore_permissions=True)

    @frappe.whitelist()
    def retry_extraction(self):
        """Retry extraction for a failed queue entry."""
        if self.status not in ("Failed",):
            frappe.throw("Can only retry failed extractions")

        self.status = "Queued"
        self.error_message = ""
        self.save(ignore_permissions=True)

        frappe.enqueue(
            "invoice_connector.api.extract.start_extraction",
            queue_name=self.name,
            queue="short",
            is_async=True,
        )

    @frappe.whitelist()
    def send_to_mapper(self):
        """Send extracted data to the mapper for field resolution."""
        if not self.extracted_data:
            frappe.throw("No extracted data available")

        frappe.enqueue(
            "invoice_connector.api.mapping.send_to_mapper",
            queue_name=self.name,
            queue="short",
            is_async=True,
        )

    @frappe.whitelist()
    def create_purchase_invoice(self):
        """Create a draft Purchase Invoice from the mapped data."""
        if not self.mapped_data:
            frappe.throw("No mapped data available. Run mapping first.")

        from invoice_connector.api.invoice_creator import create_purchase_invoice

        pi_name = create_purchase_invoice(self.name)
        return pi_name

    @frappe.whitelist()
    def open_mapper_review(self):
        """Return the URL to open the mapper's review UI for this invoice."""
        settings = frappe.get_single("Invoice Processing Settings")
        if not settings.mapper_site_id or not self.mapper_invoice_id:
            frappe.throw("Invoice not yet sent to mapper")

        # Mapper frontend URL for reviewing this invoice
        mapper_frontend = settings.mapper_url.replace(":8098", ":5173")
        return f"{mapper_frontend}/invoices/{self.mapper_invoice_id}"
