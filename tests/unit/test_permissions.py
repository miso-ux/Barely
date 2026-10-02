from app.auth.permissions import PERMISSIONS, ROLE_PERMISSIONS, ROLES, WRITE_PERMISSIONS


def test_every_role_permission_is_in_the_catalogue() -> None:
    for role, codes in ROLE_PERMISSIONS.items():
        unknown = set(codes) - set(PERMISSIONS)
        assert not unknown, f"{role}: {unknown}"
    assert set(ROLE_PERMISSIONS) == set(ROLES)


def test_supervisor_bundle_is_read_only() -> None:
    assert not set(ROLE_PERMISSIONS["supervisor"]) & WRITE_PERMISSIONS


def test_super_admin_has_no_operational_access() -> None:
    operational_prefixes = ("barrels.", "orders.", "penalties.", "debtors.", "invoices.", "pumps.")
    assert not [
        code for code in ROLE_PERMISSIONS["super_admin"] if code.startswith(operational_prefixes)
    ]


def test_invoicing_cannot_be_done_by_warehouse() -> None:
    assert "invoices.issue" not in ROLE_PERMISSIONS["warehouse"]
    assert "invoices.issue" in ROLE_PERMISSIONS["invoicing"]
