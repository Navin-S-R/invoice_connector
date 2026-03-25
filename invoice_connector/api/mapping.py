"""Mapping service — sends extracted data to invoice-mapper for field resolution."""

import json

import frappe

from invoice_connector.api.client import get_mapper_client, get_mapper_site_id


def send_to_mapper(queue_name: str):
    """Send extracted invoice data to the mapper for field suggestions and resolution.

    Flow:
        1. Upload extracted JSON to mapper
        2. Request batch suggestions (supplier, items, taxes, etc.)
        3. Auto-resolve if all suggestions have high confidence
        4. Otherwise, mark for review
    """
    doc = frappe.get_doc("Invoice Queue", queue_name)

    try:
        doc.status = "Mapping"
        doc.append_log("Sending to mapper for field resolution...")
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        site_id = get_mapper_site_id()
        extracted = json.loads(doc.extracted_data)

        with get_mapper_client(timeout=60) as client:
            # Step 1: Upload invoice to mapper
            file_name = (doc.file or "invoice").split("/")[-1]
            upload_response = client.post(
                f"/api/sites/{site_id}/invoices",
                json={"filename": file_name, "data": extracted},
            )

            if upload_response.status_code != 201:
                raise Exception(f"Mapper upload failed: HTTP {upload_response.status_code} — {upload_response.text}")

            mapper_invoice = upload_response.json()
            mapper_invoice_id = mapper_invoice["id"]
            doc.mapper_invoice_id = mapper_invoice_id
            doc.append_log(f"Uploaded to mapper. Invoice ID: {mapper_invoice_id}")

            # Step 2: Get batch suggestions for all Link fields
            suggest_response = client.post(
                f"/api/sites/{site_id}/mappings/suggest-batch",
                json={"invoice_id": mapper_invoice_id},
            )

            suggestions = {}
            if suggest_response.status_code == 200:
                suggestions = suggest_response.json()
                doc.mapping_suggestions = json.dumps(suggestions)
                doc.append_log(f"Received suggestions for {len(suggestions)} fields")

            # Step 3: Auto-confirm high-confidence suggestions
            auto_confirmed = 0
            needs_review = False

            for field_key, field_suggestions in suggestions.items():
                if not field_suggestions or not isinstance(field_suggestions, list):
                    continue

                # field_suggestions is a list of {field_type, extracted_value, suggestions: [...]}
                for suggestion_group in field_suggestions if isinstance(field_suggestions, list) else [field_suggestions]:
                    if not isinstance(suggestion_group, dict):
                        continue

                    sugg_list = suggestion_group.get("suggestions", [])
                    if not sugg_list:
                        needs_review = True
                        continue

                    top = sugg_list[0]
                    if top.get("score", 0) >= 0.95:
                        # Auto-confirm this mapping
                        try:
                            client.post(
                                f"/api/sites/{site_id}/mappings/confirm",
                                json={
                                    "field_type": suggestion_group.get("field_type", ""),
                                    "extracted_value": suggestion_group.get("extracted_value", ""),
                                    "mapped_to": top.get("name", ""),
                                    "invoice_id": mapper_invoice_id,
                                    "confidence": top.get("score", 0),
                                },
                            )
                            auto_confirmed += 1
                        except Exception:
                            needs_review = True
                    else:
                        needs_review = True

            doc.append_log(f"Auto-confirmed {auto_confirmed} mappings")

            # Step 4: Resolve the invoice (produce clean ERPNext JSON)
            resolve_response = client.post(f"/api/sites/{site_id}/invoices/{mapper_invoice_id}/resolve")

            if resolve_response.status_code == 200:
                resolved_data = resolve_response.json()
                doc.mapped_data = json.dumps(resolved_data)
                doc.append_log("Invoice resolved to ERPNext format")
            else:
                doc.append_log(f"Resolve returned HTTP {resolve_response.status_code}")
                needs_review = True

            # Step 5: Set status
            if needs_review:
                doc.status = "Review"
                doc.append_log("Some fields need manual review in the mapper UI")
            else:
                doc.status = "Mapped"
                doc.append_log("All fields mapped successfully")

                # Auto-create Purchase Invoice if enabled
                settings = frappe.get_single("Invoice Processing Settings")
                if settings.auto_create_purchase_invoice:
                    doc.save(ignore_permissions=True)
                    frappe.db.commit()
                    frappe.enqueue(
                        "invoice_connector.api.invoice_creator.create_purchase_invoice",
                        queue_name=queue_name,
                        queue="short",
                        is_async=True,
                    )
                    return

            doc.save(ignore_permissions=True)
            frappe.db.commit()

    except Exception as e:
        doc.status = "Failed"
        doc.error_message = str(e)
        doc.append_log(f"Mapping failed: {e}")
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.log_error(f"Invoice mapping failed for {queue_name}: {e}")
