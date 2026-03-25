frappe.ui.form.on("Invoice Queue", {
    refresh(frm) {
        // Status indicator colors
        const status_colors = {
            Queued: "orange",
            Extracting: "blue",
            Extracted: "cyan",
            Mapping: "blue",
            Mapped: "green",
            Review: "yellow",
            Creating: "blue",
            Completed: "green",
            Failed: "red",
        };
        const color = status_colors[frm.doc.status] || "grey";
        frm.page.set_indicator(__(frm.doc.status), color);

        // Action buttons based on status
        if (frm.doc.status === "Failed") {
            frm.add_custom_button(__("Retry Extraction"), () => {
                frm.call("retry_extraction").then(() => frm.reload_doc());
            });
        }

        if (frm.doc.status === "Extracting") {
            frm.add_custom_button(__("Check Status"), () => {
                frm.call("poll_extraction").then(() => frm.reload_doc());
            });
        }

        if (frm.doc.status === "Extracted") {
            frm.add_custom_button(__("Send to Mapper"), () => {
                frm.call("send_to_mapper").then(() => frm.reload_doc());
            }, __("Actions"));
        }

        if (frm.doc.purchase_invoice) {
            frm.add_custom_button(__("View Purchase Invoice"), () => {
                frappe.set_route("Form", "Purchase Invoice", frm.doc.purchase_invoice);
            });
        }

        // Auto-refresh while processing
        if (["Extracting", "Mapping", "Creating"].includes(frm.doc.status)) {
            setTimeout(() => frm.reload_doc(), 5000);
        }

        // Show review panel when extracted data is available
        if (frm.doc.extracted_data && !frm.doc.purchase_invoice) {
            render_review_panel(frm);
        }
    },
});

function render_review_panel(frm) {
    const $panel = frm.fields_dict.review_panel.$wrapper;
    $panel.empty();

    let data;
    try {
        data = JSON.parse(frm.doc.extracted_data);
    } catch (e) {
        $panel.html('<div class="text-muted">Could not parse extracted data</div>');
        return;
    }

    // Helper: unwrap {value, confidence_score} or return raw value
    function unwrap(field) {
        if (field && typeof field === "object" && "value" in field) {
            return { value: field.value, confidence: field.confidence_score || 0 };
        }
        return { value: field, confidence: 100 };
    }

    // Helper: confidence badge
    function badge(confidence) {
        if (confidence === undefined || confidence === null) return "";
        const c = Math.round(confidence);
        let color = "green";
        if (c < 70) color = "red";
        else if (c < 90) color = "orange";
        return `<span class="badge badge-${color}" style="font-size:11px; margin-left:6px; padding:2px 6px; border-radius:3px;
            background:var(--bg-${color}); color:var(--text-on-${color})">${c}%</span>`;
    }

    // Helper: editable field
    function editable_field(key, val, conf, type = "text") {
        const input_type = type === "number" ? "number" : "text";
        const step = type === "number" ? 'step="any"' : "";
        return `
            <div class="form-group" style="margin-bottom:8px;">
                <label style="font-size:11px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">
                    ${frappe.model.unscrub(key)} ${badge(conf)}
                </label>
                <input type="${input_type}" ${step}
                    class="form-control form-control-sm review-field"
                    data-key="${key}" value="${val ?? ""}"
                    style="font-size:13px; ${conf < 70 ? "border-color:var(--red); background:var(--red-50, #fff5f5);" : ""}">
            </div>
        `;
    }

    // ── Build the review HTML ──────────────────────────────────

    let html = `<div style="border:1px solid var(--border-color); border-radius:8px; padding:16px; margin-bottom:16px; background:var(--card-bg);">`;
    html += `<h5 style="margin-top:0; margin-bottom:16px; font-weight:600;">Invoice Review</h5>`;

    // ── PDF Preview + Header side by side ──
    html += `<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:16px;">`;

    // Left: PDF preview
    const file_url = frm.doc.file;
    if (file_url) {
        const ext = file_url.split(".").pop().toLowerCase();
        if (ext === "pdf") {
            html += `<div>
                <label style="font-size:11px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px; display:block; margin-bottom:6px;">
                    Original Document
                </label>
                <iframe src="${file_url}" style="width:100%; height:500px; border:1px solid var(--border-color); border-radius:4px;"></iframe>
            </div>`;
        } else {
            html += `<div>
                <label style="font-size:11px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px; display:block; margin-bottom:6px;">
                    Original Document
                </label>
                <img src="${file_url}" style="width:100%; max-height:500px; object-fit:contain; border:1px solid var(--border-color); border-radius:4px;">
            </div>`;
        }
    } else {
        html += `<div class="text-muted" style="padding:20px;">No document preview available</div>`;
    }

    // Right: Header fields
    html += `<div>`;
    html += `<h6 style="margin-top:0; margin-bottom:12px; font-weight:600;">Invoice Details</h6>`;

    const supplier = unwrap(data.supplier);
    const supplier_name = unwrap(data.supplier_name);
    const posting_date = unwrap(data.posting_date);
    const due_date = unwrap(data.due_date);
    const bill_no = unwrap(data.bill_no);
    const currency = unwrap(data.currency);
    const grand_total = unwrap(data.grand_total);
    const total = unwrap(data.total);

    html += editable_field("supplier", supplier.value, supplier.confidence);
    html += editable_field("supplier_name", supplier_name.value, supplier_name.confidence);
    html += `<div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">`;
    html += editable_field("bill_no", bill_no.value, bill_no.confidence);
    html += editable_field("posting_date", posting_date.value, posting_date.confidence);
    html += editable_field("due_date", due_date.value, due_date.confidence);
    html += editable_field("currency", currency.value, currency.confidence);
    html += editable_field("total", total.value, total.confidence, "number");
    html += editable_field("grand_total", grand_total.value, grand_total.confidence, "number");
    html += `</div>`;

    // Supplier tax IDs
    const tax_ids = data.supplier_tax_ids;
    if (tax_ids) {
        const gstin = unwrap(tax_ids.gstin || tax_ids);
        const pan = unwrap(tax_ids.pan);
        if (gstin.value || pan.value) {
            html += `<div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:4px;">`;
            if (gstin.value) html += editable_field("gstin", gstin.value, gstin.confidence);
            if (pan.value) html += editable_field("pan", pan.value, pan.confidence);
            html += `</div>`;
        }
    }

    html += `</div>`;  // close right column
    html += `</div>`;  // close grid

    // ── Line Items Table ──
    const items = data.items || [];
    if (items.length > 0) {
        html += `<h6 style="font-weight:600; margin-bottom:8px;">Line Items (${items.length})</h6>`;
        html += `<div style="overflow-x:auto;">`;
        html += `<table class="table table-bordered table-sm" style="font-size:12px; margin-bottom:16px;">`;
        html += `<thead style="background:var(--subtle-accent);">
            <tr>
                <th style="width:5%">#</th>
                <th style="width:25%">Item Name</th>
                <th style="width:10%">HSN/SAC</th>
                <th style="width:8%">Qty</th>
                <th style="width:8%">UOM</th>
                <th style="width:12%">Rate</th>
                <th style="width:12%">Amount</th>
                <th style="width:8%">Tax %</th>
                <th style="width:12%">Tax Amt</th>
            </tr>
        </thead><tbody>`;

        items.forEach((item, idx) => {
            const item_name = unwrap(item.item_name);
            const qty = unwrap(item.qty);
            const uom = unwrap(item.uom);
            const rate = unwrap(item.rate);
            const amount = unwrap(item.amount);
            const hsn = unwrap(item.hsn_sac);
            const tax_rate = unwrap(item.tax_rate);
            const tax_amount = unwrap(item.tax_amount);

            // Row background based on lowest confidence
            const min_conf = Math.min(
                item_name.confidence || 100, qty.confidence || 100,
                rate.confidence || 100, amount.confidence || 100
            );
            const row_bg = min_conf < 70 ? "background:var(--red-50, #fff5f5);" :
                           min_conf < 90 ? "background:var(--yellow-50, #fffde7);" : "";

            html += `<tr style="${row_bg}">
                <td>${idx + 1}</td>
                <td>
                    <input type="text" class="form-control form-control-sm review-item-field"
                        data-idx="${idx}" data-field="item_name"
                        value="${item_name.value || ""}" style="font-size:12px;">
                    ${badge(item_name.confidence)}
                </td>
                <td>
                    <input type="text" class="form-control form-control-sm review-item-field"
                        data-idx="${idx}" data-field="hsn_sac"
                        value="${hsn.value || ""}" style="font-size:12px;">
                </td>
                <td>
                    <input type="number" step="any" class="form-control form-control-sm review-item-field"
                        data-idx="${idx}" data-field="qty"
                        value="${qty.value ?? ""}" style="font-size:12px;">
                    ${badge(qty.confidence)}
                </td>
                <td>
                    <input type="text" class="form-control form-control-sm review-item-field"
                        data-idx="${idx}" data-field="uom"
                        value="${uom.value || "Nos"}" style="font-size:12px;">
                </td>
                <td>
                    <input type="number" step="any" class="form-control form-control-sm review-item-field"
                        data-idx="${idx}" data-field="rate"
                        value="${rate.value ?? ""}" style="font-size:12px;">
                    ${badge(rate.confidence)}
                </td>
                <td>
                    <input type="number" step="any" class="form-control form-control-sm review-item-field"
                        data-idx="${idx}" data-field="amount"
                        value="${amount.value ?? ""}" style="font-size:12px;">
                </td>
                <td>
                    <input type="number" step="any" class="form-control form-control-sm review-item-field"
                        data-idx="${idx}" data-field="tax_rate"
                        value="${tax_rate.value ?? ""}" style="font-size:12px;">
                </td>
                <td>
                    <input type="number" step="any" class="form-control form-control-sm review-item-field"
                        data-idx="${idx}" data-field="tax_amount"
                        value="${tax_amount.value ?? ""}" style="font-size:12px;">
                </td>
            </tr>`;
        });

        html += `</tbody></table></div>`;
    }

    // ── Taxes Table ──
    const taxes = data.taxes || [];
    if (taxes.length > 0) {
        html += `<h6 style="font-weight:600; margin-bottom:8px;">Taxes & Charges</h6>`;
        html += `<table class="table table-bordered table-sm" style="font-size:12px; margin-bottom:16px;">`;
        html += `<thead style="background:var(--subtle-accent);">
            <tr>
                <th>Description</th>
                <th style="width:15%">Rate %</th>
                <th style="width:15%">Amount</th>
                <th style="width:20%">Charge Type</th>
            </tr>
        </thead><tbody>`;

        taxes.forEach((tax, idx) => {
            const desc = unwrap(tax.description);
            const rate = unwrap(tax.rate);
            const amt = unwrap(tax.tax_amount);
            const charge_type = unwrap(tax.charge_type);

            html += `<tr>
                <td>
                    <input type="text" class="form-control form-control-sm review-tax-field"
                        data-idx="${idx}" data-field="description"
                        value="${desc.value || ""}" style="font-size:12px;">
                    ${badge(desc.confidence)}
                </td>
                <td>
                    <input type="number" step="any" class="form-control form-control-sm review-tax-field"
                        data-idx="${idx}" data-field="rate"
                        value="${rate.value ?? ""}" style="font-size:12px;">
                </td>
                <td>
                    <input type="number" step="any" class="form-control form-control-sm review-tax-field"
                        data-idx="${idx}" data-field="tax_amount"
                        value="${amt.value ?? ""}" style="font-size:12px;">
                </td>
                <td>
                    <input type="text" class="form-control form-control-sm review-tax-field"
                        data-idx="${idx}" data-field="charge_type"
                        value="${charge_type.value || "On Net Total"}" style="font-size:12px;">
                </td>
            </tr>`;
        });

        html += `</tbody></table>`;
    }

    // ── Action Buttons ──
    html += `<div style="display:flex; gap:8px; margin-top:12px;">`;

    if (!frm.doc.purchase_invoice) {
        html += `<button class="btn btn-primary btn-sm" id="btn-save-and-create-pi">
            Create Purchase Invoice
        </button>`;
    }

    html += `<button class="btn btn-default btn-sm" id="btn-save-review">
        Save Changes
    </button>`;

    html += `</div>`;
    html += `</div>`;  // close main panel

    $panel.html(html);

    // ── Event: Save Changes ──
    $panel.find("#btn-save-review").on("click", () => {
        save_review_changes(frm, data, $panel);
        frappe.show_alert({ message: __("Changes saved to extracted data"), indicator: "green" });
    });

    // ── Event: Create Purchase Invoice ──
    $panel.find("#btn-save-and-create-pi").on("click", () => {
        save_review_changes(frm, data, $panel);

        // Build mapped_data from the (now unwrapped) extracted data
        frappe.call({
            method: "invoice_connector.api.endpoints.build_mapped_data_from_extracted",
            args: { queue_name: frm.doc.name },
            callback(r) {
                if (r.message) {
                    frm.reload_doc();
                    // Now create the PI
                    frm.call("create_purchase_invoice").then((r2) => {
                        if (r2.message) {
                            frappe.set_route("Form", "Purchase Invoice", r2.message);
                        }
                        frm.reload_doc();
                    });
                }
            },
        });
    });
}

function save_review_changes(frm, data, $panel) {
    // Collect header field changes
    $panel.find(".review-field").each(function () {
        const key = $(this).data("key");
        const val = $(this).val();
        if (data[key] && typeof data[key] === "object" && "value" in data[key]) {
            data[key].value = val;
        } else {
            data[key] = val;
        }
    });

    // Collect item field changes
    $panel.find(".review-item-field").each(function () {
        const idx = $(this).data("idx");
        const field = $(this).data("field");
        const val = $(this).val();
        if (data.items && data.items[idx]) {
            const item = data.items[idx];
            if (item[field] && typeof item[field] === "object" && "value" in item[field]) {
                item[field].value = isNaN(val) ? val : parseFloat(val) || val;
            } else {
                item[field] = isNaN(val) ? val : parseFloat(val) || val;
            }
        }
    });

    // Collect tax field changes
    $panel.find(".review-tax-field").each(function () {
        const idx = $(this).data("idx");
        const field = $(this).data("field");
        const val = $(this).val();
        if (data.taxes && data.taxes[idx]) {
            const tax = data.taxes[idx];
            if (tax[field] && typeof tax[field] === "object" && "value" in tax[field]) {
                tax[field].value = isNaN(val) ? val : parseFloat(val) || val;
            } else {
                tax[field] = isNaN(val) ? val : parseFloat(val) || val;
            }
        }
    });

    // Save back to the doc
    frm.doc.extracted_data = JSON.stringify(data);
    frm.dirty();
    frm.save();
}
