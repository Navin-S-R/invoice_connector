import frappe
from frappe.model.document import Document


class InvoiceProcessingSettings(Document):
    def validate(self):
        if self.extractor_url:
            self.extractor_url = self.extractor_url.rstrip("/")
        if self.mapper_url:
            self.mapper_url = self.mapper_url.rstrip("/")

    @frappe.whitelist()
    def test_connections(self):
        """Test connectivity to extractor and mapper services."""
        import httpx

        results = {}

        # Test extractor
        try:
            r = httpx.get(f"{self.extractor_url}/docs", timeout=10)
            results["extractor"] = "Connected" if r.status_code == 200 else f"Error: HTTP {r.status_code}"
        except Exception as e:
            results["extractor"] = f"Failed: {e}"

        # Test mapper
        try:
            r = httpx.get(f"{self.mapper_url}/api/health", timeout=10)
            results["mapper"] = "Connected" if r.status_code == 200 else f"Error: HTTP {r.status_code}"
        except Exception as e:
            results["mapper"] = f"Failed: {e}"

        self.extractor_status = results.get("extractor", "Unknown")
        self.mapper_status = results.get("mapper", "Unknown")
        self.save()

        return results

    @frappe.whitelist()
    def register_site(self):
        """Register this ERPNext site with the mapper service."""
        import httpx

        if not self.site_url:
            frappe.throw("Please set 'This Site URL' first")

        payload = {
            "name": frappe.local.site,
            "url": self.site_url,
            "api_key": self.site_api_key or "",
            "api_secret": self.get_password("site_api_secret") or "",
        }

        try:
            r = httpx.post(f"{self.mapper_url}/api/sites", json=payload, timeout=30)
            if r.status_code == 201:
                data = r.json()
                self.mapper_site_id = data.get("id")
                self.save()
                frappe.msgprint(f"Site registered. Mapper Site ID: {self.mapper_site_id}")
                return data
            elif r.status_code == 409:
                frappe.msgprint("Site already registered. Update the Mapper Site ID manually if needed.")
            else:
                frappe.throw(f"Registration failed: HTTP {r.status_code} — {r.text}")
        except httpx.ConnectError:
            frappe.throw(f"Cannot connect to mapper at {self.mapper_url}")
