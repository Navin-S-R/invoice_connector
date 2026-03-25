// Adds an "Extract from File" button to Purchase Invoice form
frappe.ui.form.on("Purchase Invoice", {
    refresh(frm) {
        if (frm.is_new()) {
            frm.add_custom_button(
                __("Extract from File"),
                () => show_extract_dialog(frm),
                __("Invoice Connector")
            );
        }
    },
});

function show_extract_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Extract Invoice from File"),
        fields: [
            {
                fieldname: "file",
                fieldtype: "Attach",
                label: __("Invoice File"),
                reqd: 1,
                description: __("Upload PDF, PNG, JPG, TIFF, or WEBP"),
            },
            {
                fieldname: "company",
                fieldtype: "Link",
                label: __("Company"),
                options: "Company",
                reqd: 1,
                default: frm.doc.company || frappe.defaults.get_user_default("Company"),
            },
        ],
        primary_action_label: __("Extract"),
        primary_action(values) {
            d.hide();
            frappe.call({
                method: "frappe.client.insert",
                args: {
                    doc: {
                        doctype: "Invoice Queue",
                        file: values.file,
                        company: values.company,
                    },
                },
                callback(r) {
                    if (r.message) {
                        frappe.show_alert({
                            message: __("Invoice queued for extraction: {0}", [r.message.name]),
                            indicator: "green",
                        });
                        frappe.set_route("Form", "Invoice Queue", r.message.name);
                    }
                },
            });
        },
    });
    d.show();
}
