"""HTTP client utilities for communicating with extractor and mapper services."""

import httpx
import frappe


def get_settings():
    """Load Invoice Processing Settings (cached within request)."""
    return frappe.get_single("Invoice Processing Settings")


def get_extractor_client(timeout: int = 120) -> httpx.Client:
    """Create an httpx client pointed at the extractor service."""
    settings = get_settings()
    return httpx.Client(
        base_url=settings.extractor_url,
        timeout=httpx.Timeout(connect=10, read=timeout, write=30, pool=10),
    )


def get_mapper_client(timeout: int = 30) -> httpx.Client:
    """Create an httpx client pointed at the mapper service."""
    settings = get_settings()
    return httpx.Client(
        base_url=settings.mapper_url,
        timeout=httpx.Timeout(connect=10, read=timeout, write=30, pool=10),
    )


def get_mapper_site_id() -> str:
    """Get the mapper site ID for this ERPNext instance."""
    settings = get_settings()
    if not settings.mapper_site_id:
        frappe.throw(
            "Mapper Site ID not configured. Go to Invoice Processing Settings and register this site.",
            title="Mapper Not Configured",
        )
    return settings.mapper_site_id
