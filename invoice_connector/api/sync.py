"""Master data sync — pushes ERPNext master data to invoice-mapper."""

import frappe

from invoice_connector.api.client import get_mapper_client, get_mapper_site_id, get_settings


# Fields to sync per doctype (must match what mapper expects)
SYNC_DOCTYPES = {
    "suppliers": {
        "doctype": "Supplier",
        "fields": ["name", "supplier_name", "supplier_group", "country"],
        "filters": {"disabled": 0},
    },
    "items": {
        "doctype": "Item",
        "fields": ["name", "item_name", "item_group", "description", "stock_uom"],
        "filters": {"disabled": 0},
    },
    "accounts": {
        "doctype": "Account",
        "fields": ["name", "account_name", "account_type", "parent_account", "is_group"],
        "filters": {"is_group": 0, "disabled": 0},
    },
    "uoms": {
        "doctype": "UOM",
        "fields": ["name"],
        "filters": {"enabled": 1},
    },
    "currencies": {
        "doctype": "Currency",
        "fields": ["name", "symbol"],
        "filters": {"enabled": 1},
    },
}


def sync_master_data_to_mapper():
    """Sync all master data doctypes from this ERPNext to the mapper.

    Called by hourly scheduler or manually.
    Reads data from ERPNext DB and POSTs as CSV to the mapper's import endpoint.
    """
    settings = get_settings()
    if not settings.auto_sync_master_data:
        return

    site_id = get_mapper_site_id()

    with get_mapper_client(timeout=120) as client:
        for collection_name, config in SYNC_DOCTYPES.items():
            try:
                _sync_one_doctype(client, site_id, collection_name, config)
            except Exception as e:
                frappe.log_error(f"Sync failed for {collection_name}: {e}")

    # Update last sync timestamp
    settings.last_sync_at = frappe.utils.now_datetime()
    settings.save(ignore_permissions=True)
    frappe.db.commit()


def _sync_one_doctype(client, site_id: str, collection_name: str, config: dict):
    """Sync a single doctype to the mapper via CSV import."""
    import csv
    import io

    doctype = config["doctype"]
    fields = config["fields"]
    filters = config.get("filters", {})

    # Fetch all records from ERPNext
    records = frappe.get_all(doctype, fields=fields, filters=filters, limit_page_length=0)

    if not records:
        return

    # Build CSV in memory
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=fields)
    writer.writeheader()
    for record in records:
        writer.writerow({f: record.get(f, "") for f in fields})

    csv_content = csv_buffer.getvalue().encode("utf-8")

    # Upload to mapper
    response = client.post(
        f"/api/sites/{site_id}/master-data/{collection_name}/import-csv",
        files={"file": (f"{collection_name}.csv", csv_content, "text/csv")},
    )

    if response.status_code == 200:
        result = response.json()
        count = result.get("imported", result.get("count", len(records)))
        frappe.logger().info(f"Synced {count} {collection_name} to mapper")
    else:
        frappe.log_error(f"Mapper CSV import failed for {collection_name}: HTTP {response.status_code} — {response.text}")


def on_supplier_change(doc, method=None):
    """Called on Supplier after_insert / on_update. Queues a sync."""
    _queue_incremental_sync("suppliers")


def on_item_change(doc, method=None):
    """Called on Item after_insert / on_update. Queues a sync."""
    _queue_incremental_sync("items")


def _queue_incremental_sync(collection_name: str):
    """Queue a background sync for a specific doctype (debounced by enqueue dedup)."""
    settings = get_settings()
    if not settings.auto_sync_master_data or not settings.mapper_site_id:
        return

    frappe.enqueue(
        "invoice_connector.api.sync._run_incremental_sync",
        collection_name=collection_name,
        queue="long",
        is_async=True,
        deduplicate=True,  # Prevents duplicate jobs within the same queue cycle
    )


def _run_incremental_sync(collection_name: str):
    """Run sync for a single doctype."""
    settings = get_settings()
    site_id = settings.mapper_site_id
    config = SYNC_DOCTYPES.get(collection_name)

    if not config or not site_id:
        return

    with get_mapper_client(timeout=120) as client:
        _sync_one_doctype(client, site_id, collection_name, config)
