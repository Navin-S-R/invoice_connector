import frappe


def after_install():
    """Create default settings record if it doesn't exist."""
    if not frappe.db.exists("Invoice Processing Settings", "Invoice Processing Settings"):
        frappe.get_doc(
            {
                "doctype": "Invoice Processing Settings",
                "extractor_url": "http://localhost:8099",
                "mapper_url": "http://localhost:8098",
                "auto_sync_master_data": 1,
                "auto_create_purchase_invoice": 0,
            }
        ).insert(ignore_permissions=True)
        frappe.db.commit()
