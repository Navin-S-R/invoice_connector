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

        if (frm.doc.status === "Extracted") {
            frm.add_custom_button(__("Send to Mapper"), () => {
                frm.call("send_to_mapper").then(() => frm.reload_doc());
            }, __("Actions"));
        }

        if (frm.doc.status === "Review") {
            frm.add_custom_button(__("Open Mapper Review"), () => {
                frm.call("open_mapper_review").then((r) => {
                    if (r.message) {
                        window.open(r.message, "_blank");
                    }
                });
            }, __("Actions"));

            frm.add_custom_button(__("Refresh Mapped Data"), () => {
                frappe.call({
                    method: "invoice_connector.api.mapping.send_to_mapper",
                    args: { queue_name: frm.doc.name },
                    callback() { frm.reload_doc(); },
                });
            }, __("Actions"));
        }

        if (["Mapped", "Review"].includes(frm.doc.status) && frm.doc.mapped_data) {
            frm.add_custom_button(__("Create Purchase Invoice"), () => {
                frm.call("create_purchase_invoice").then((r) => {
                    if (r.message) {
                        frappe.set_route("Form", "Purchase Invoice", r.message);
                    }
                    frm.reload_doc();
                });
            }).addClass("btn-primary");
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
    },
});
