"""
Name based matching between an AD computer object and a core InventoryBase
asset. Kept deliberately conservative: a single exact candidate links
automatically, anything else is left for manual resolution.
"""

from asset.inventory_base.models import InventoryBase


def normalize(name):
    """Upper-case, stripped, without a trailing NetBIOS '$'."""
    if not name:
        return ""
    return name.strip().rstrip("$").upper()


def find_asset_candidates(computer_name):
    """Return the queryset of InventoryBase assets whose name matches."""
    target = normalize(computer_name)
    if not target:
        return InventoryBase.objects.none()
    return InventoryBase.objects.filter(name__iexact=target)


def match_status_for(candidates_count):
    if candidates_count == 1:
        return "linked"
    if candidates_count == 0:
        return "unlinked"
    return "ambiguous"
