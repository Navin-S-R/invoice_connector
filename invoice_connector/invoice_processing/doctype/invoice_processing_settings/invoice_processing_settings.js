frappe.ui.form.on("Invoice Processing Settings", {
    refresh(frm) {
        frm.add_custom_button(__("Test Connections"), () => {
            frm.call("test_connections").then((r) => {
                if (r.message) {
                    let msg = "";
                    for (const [service, status] of Object.entries(r.message)) {
                        const icon = status.startsWith("Connected") ? "✓" : "✗";
                        msg += `<b>${service}:</b> ${icon} ${status}<br>`;
                    }
                    frappe.msgprint({ title: __("Connection Status"), message: msg, indicator: "blue" });
                    frm.reload_doc();
                }
            });
        });

        if (!frm.doc.mapper_site_id) {
            frm.add_custom_button(__("Register Site with Mapper"), () => {
                frm.call("register_site").then(() => frm.reload_doc());
            }).addClass("btn-primary");
        }

        frm.add_custom_button(__("Sync Master Data Now"), () => {
            frappe.call({
                method: "invoice_connector.api.endpoints.sync_master_data",
                callback(r) {
                    frappe.show_alert({ message: __("Master data synced"), indicator: "green" });
                    frm.reload_doc();
                },
            });
        });
    },
});
