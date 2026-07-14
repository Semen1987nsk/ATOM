"""API-09: admin user-list sort_by must be whitelisted (no arbitrary column access)."""
import admin_service


def test_sort_by_whitelist_constant():
    assert "hashed_password" not in admin_service._ALLOWED_SORT_COLUMNS
    assert "created_at" in admin_service._ALLOWED_SORT_COLUMNS
