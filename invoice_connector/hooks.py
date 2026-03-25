app_name = "invoice_connector"
app_title = "Invoice Connector"
app_publisher = "Aerele Technologies"
app_description = "Connect ERPNext with Invoice Extractor & Mapper services"
app_email = "hello@aerele.in"
app_license = "MIT"
required_apps = ["frappe", "erpnext"]

# --------------------------------------------------------------------------
# DocType JS overrides — adds "Extract Invoice" button on Purchase Invoice
# --------------------------------------------------------------------------
doctype_js = {
    "Purchase Invoice": "public/js/purchase_invoice.js",
}

# --------------------------------------------------------------------------
# Scheduled tasks
# --------------------------------------------------------------------------
scheduler_events = {
    "hourly_long": [
        "invoice_connector.api.sync.sync_master_data_to_mapper",
    ],
    "cron": {
        # Poll extraction status for queued invoices every 30 seconds
        "*/1 * * * *": [
            "invoice_connector.api.polling.poll_pending_extractions",
        ],
    },
}

# --------------------------------------------------------------------------
# Doc events — auto-sync master data on changes
# --------------------------------------------------------------------------
doc_events = {
    "Supplier": {
        "after_insert": "invoice_connector.api.sync.on_supplier_change",
        "on_update": "invoice_connector.api.sync.on_supplier_change",
    },
    "Item": {
        "after_insert": "invoice_connector.api.sync.on_item_change",
        "on_update": "invoice_connector.api.sync.on_item_change",
    },
}

# --------------------------------------------------------------------------
# Fixtures — export settings & custom fields
# --------------------------------------------------------------------------
fixtures = []

# --------------------------------------------------------------------------
# On app install
# --------------------------------------------------------------------------
after_install = "invoice_connector.setup.after_install"
