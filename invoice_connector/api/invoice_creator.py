"""Creates ERPNext Purchase Invoices from mapped invoice data."""

import json

import frappe


def create_purchase_invoice(queue_name: str) -> str:
    """Create a draft Purchase Invoice from resolved mapper data.

    The mapped_data from invoice-mapper is already in ERPNext Purchase Invoice format:
    {
        "supplier": "Supplier Name",
        "posting_date": "2026-03-20",
        "bill_no": "INV-001",
        "currency": "INR",
        "items": [{"item_name": "...", "qty": 1, "rate": 100, ...}],
        "taxes": [{"charge_type": "...", "account_head": "...", "rate": 18}],
        ...
    }
    """
    doc = frappe.get_doc("Invoice Queue", queue_name)

    try:
        doc.status = "Creating"
        doc.append_log("Creating Purchase Invoice...")
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        if not doc.mapped_data:
            raise ValueError("No mapped data available")

        mapped = json.loads(doc.mapped_data)
        settings = frappe.get_single("Invoice Processing Settings")

        # Build the Purchase Invoice document
        pi_data = {
            "doctype": "Purchase Invoice",
            "docstatus": 0,  # Draft
            "company": doc.company or settings.default_company,
            "supplier": mapped.get("supplier", ""),
            "supplier_name": mapped.get("supplier_name", ""),
            "posting_date": mapped.get("posting_date") or mapped.get("bill_date"),
            "due_date": mapped.get("due_date"),
            "bill_no": mapped.get("bill_no"),
            "bill_date": mapped.get("bill_date") or mapped.get("posting_date"),
            "currency": mapped.get("currency", "INR"),
            "remarks": mapped.get("remarks", ""),
            "items": [],
            "taxes": [],
        }

        # Validate supplier exists
        supplier = pi_data["supplier"]
        if supplier and not frappe.db.exists("Supplier", supplier):
            # Try supplier_name
            supplier_by_name = frappe.db.get_value("Supplier", {"supplier_name": supplier}, "name")
            if supplier_by_name:
                pi_data["supplier"] = supplier_by_name
            else:
                raise ValueError(f"Supplier '{supplier}' not found in ERPNext. Please create it first.")

        # Build items
        for item in mapped.get("items", []):
            pi_item = {
                "item_name": item.get("item_name", item.get("description", "")),
                "description": item.get("description", item.get("item_name", "")),
                "qty": item.get("qty", 1),
                "rate": item.get("rate", 0),
                "uom": item.get("uom", "Nos"),
            }

            # Try to resolve item_code
            item_code = item.get("item_code", "")
            if item_code and frappe.db.exists("Item", item_code):
                pi_item["item_code"] = item_code
            elif item_code:
                # Try by item_name
                found = frappe.db.get_value("Item", {"item_name": item_code}, "name")
                if found:
                    pi_item["item_code"] = found

            # Set expense account
            if not pi_item.get("expense_account") and settings.default_expense_account:
                pi_item["expense_account"] = settings.default_expense_account

            # Optional fields
            if item.get("discount_percentage"):
                pi_item["discount_percentage"] = item["discount_percentage"]
            if item.get("discount_amount"):
                pi_item["discount_amount"] = item["discount_amount"]

            pi_data["items"].append(pi_item)

        if not pi_data["items"]:
            raise ValueError("No line items found in mapped data")

        # Build taxes
        for tax in mapped.get("taxes", []):
            account_head = tax.get("account_head", "")

            # Validate account exists
            if account_head and not frappe.db.exists("Account", account_head):
                # Try partial match
                found = frappe.db.get_value(
                    "Account",
                    {"account_name": ["like", f"%{account_head}%"], "company": pi_data["company"]},
                    "name",
                )
                if found:
                    account_head = found
                else:
                    doc.append_log(f"Warning: Tax account '{account_head}' not found, skipping")
                    continue

            pi_tax = {
                "charge_type": tax.get("charge_type", "On Net Total"),
                "account_head": account_head,
                "description": tax.get("description", ""),
                "rate": tax.get("rate", 0),
            }

            if tax.get("charge_type") == "Actual" and tax.get("tax_amount"):
                pi_tax["tax_amount"] = tax["tax_amount"]

            pi_data["taxes"].append(pi_tax)

        # Create the Purchase Invoice
        pi = frappe.get_doc(pi_data)
        pi.flags.ignore_permissions = True
        pi.insert()
        frappe.db.commit()

        # Update queue entry
        doc.purchase_invoice = pi.name
        doc.status = "Completed"
        doc.append_log(f"Purchase Invoice {pi.name} created (Draft)")
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        return pi.name

    except Exception as e:
        doc.status = "Failed"
        doc.error_message = str(e)
        doc.append_log(f"Purchase Invoice creation failed: {e}")
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.log_error(f"PI creation failed for {queue_name}: {e}")
        raise
