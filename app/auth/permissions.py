"""Permission catalogue and default role bundles.

Code checks permissions, never role names. The full catalogue for all five roles is defined
up front so later phases only attach endpoints to existing codes. The seed syncs this into the
`permissions`, `roles` and `role_permissions` tables.
"""

from typing import Final


class Perm:
    # Users, configuration, audit
    USERS_READ: Final = "users.read"
    USERS_MANAGE: Final = "users.manage"
    SETTINGS_READ: Final = "settings.read"
    SETTINGS_MANAGE: Final = "settings.manage"
    AUDIT_READ_USERS: Final = "audit.read_users"
    AUDIT_READ_OPERATIONS: Final = "audit.read_operations"
    AUDIT_READ_INVOICING: Final = "audit.read_invoicing"
    AUDIT_READ_ALL: Final = "audit.read_all"
    # Barrels and stock (phase 2)
    BARRELS_READ: Final = "barrels.read"
    BARRELS_MANAGE: Final = "barrels.manage"
    STOCK_READ_FREE: Final = "stock.read_free"
    # Orders, exceptions (phase 3)
    ORDERS_READ_OWN: Final = "orders.read_own"
    ORDERS_CREATE: Final = "orders.create"
    ORDERS_READ_ALL: Final = "orders.read_all"
    ORDERS_MANAGE: Final = "orders.manage"
    EXCEPTIONS_CREATE: Final = "exceptions.create"
    EXCEPTIONS_DECIDE: Final = "exceptions.decide"
    # Returns, penalties, debtors (phase 4)
    PENALTIES_MANAGE: Final = "penalties.manage"
    PAYMENTS_RECORD_ONSITE: Final = "payments.record_onsite"
    DEBTORS_READ: Final = "debtors.read"
    # Pumps (phase 5)
    PUMPS_READ: Final = "pumps.read"
    PUMPS_MANAGE: Final = "pumps.manage"
    # Invoices (phase 6)
    INVOICES_READ: Final = "invoices.read"
    INVOICES_DRAFT: Final = "invoices.draft"
    INVOICES_ISSUE: Final = "invoices.issue"
    INVOICES_RECORD_PAYMENT: Final = "invoices.record_payment"
    # Reports (phases 7 and 8)
    REPORTS_READ_OPERATIONS: Final = "reports.read_operations"
    REPORTS_READ_INVOICING: Final = "reports.read_invoicing"
    REPORTS_READ_ALL: Final = "reports.read_all"
    # Everyone who is signed in
    NOTIFICATIONS_READ_OWN: Final = "notifications.read_own"


PERMISSIONS: Final[dict[str, str]] = {
    Perm.USERS_READ: "View the list of users",
    Perm.USERS_MANAGE: "Create users, change roles, deactivate accounts, reset passwords",
    Perm.SETTINGS_READ: "View configuration",
    Perm.SETTINGS_MANAGE: "Change configuration",
    Perm.AUDIT_READ_USERS: "View audit of user and role management",
    Perm.AUDIT_READ_OPERATIONS: "View audit of warehouse operations",
    Perm.AUDIT_READ_INVOICING: "View audit of invoicing",
    Perm.AUDIT_READ_ALL: "View the whole audit log",
    Perm.BARRELS_READ: "View barrels and their history",
    Perm.BARRELS_MANAGE: "Add barrels and change their status",
    Perm.STOCK_READ_FREE: "View the number of free barrels and pumps",
    Perm.ORDERS_READ_OWN: "View own orders, loans and penalties",
    Perm.ORDERS_CREATE: "Create and cancel own orders",
    Perm.ORDERS_READ_ALL: "View all orders and loans",
    Perm.ORDERS_MANAGE: "Prepare, issue and receive orders",
    Perm.EXCEPTIONS_CREATE: "Request an exception above the order limit",
    Perm.EXCEPTIONS_DECIDE: "Approve or reject exception requests",
    Perm.PENALTIES_MANAGE: "Create, cancel and record penalties",
    Perm.PAYMENTS_RECORD_ONSITE: "Record on-site payments",
    Perm.DEBTORS_READ: "View the list of debtors",
    Perm.PUMPS_READ: "View pump products and stock",
    Perm.PUMPS_MANAGE: "Receive pump stock and issue pump orders",
    Perm.INVOICES_READ: "View invoices",
    Perm.INVOICES_DRAFT: "Create and edit invoice drafts",
    Perm.INVOICES_ISSUE: "Issue, send and cancel invoices",
    Perm.INVOICES_RECORD_PAYMENT: "Record invoice payments",
    Perm.REPORTS_READ_OPERATIONS: "View operational reports",
    Perm.REPORTS_READ_INVOICING: "View invoicing reports",
    Perm.REPORTS_READ_ALL: "View all reports, timelines and exports",
    Perm.NOTIFICATIONS_READ_OWN: "View own notifications",
}

# role code -> i18n key of the display name
ROLES: Final[dict[str, str]] = {
    "super_admin": "role.super_admin",
    "warehouse": "role.warehouse",
    "invoicing": "role.invoicing",
    "supervisor": "role.supervisor",
    "user": "role.user",
}

_COMMON: Final[list[str]] = [Perm.NOTIFICATIONS_READ_OWN]

ROLE_PERMISSIONS: Final[dict[str, list[str]]] = {
    "super_admin": [
        *_COMMON,
        Perm.USERS_READ,
        Perm.USERS_MANAGE,
        Perm.SETTINGS_READ,
        Perm.SETTINGS_MANAGE,
        Perm.AUDIT_READ_USERS,
    ],
    "warehouse": [
        *_COMMON,
        Perm.USERS_READ,
        Perm.BARRELS_READ,
        Perm.BARRELS_MANAGE,
        Perm.STOCK_READ_FREE,
        Perm.ORDERS_READ_ALL,
        Perm.ORDERS_MANAGE,
        Perm.EXCEPTIONS_DECIDE,
        Perm.PENALTIES_MANAGE,
        Perm.PAYMENTS_RECORD_ONSITE,
        Perm.DEBTORS_READ,
        Perm.PUMPS_READ,
        Perm.PUMPS_MANAGE,
        Perm.INVOICES_DRAFT,
        Perm.REPORTS_READ_OPERATIONS,
        Perm.AUDIT_READ_OPERATIONS,
    ],
    "invoicing": [
        *_COMMON,
        Perm.INVOICES_READ,
        Perm.INVOICES_DRAFT,
        Perm.INVOICES_ISSUE,
        Perm.INVOICES_RECORD_PAYMENT,
        Perm.REPORTS_READ_INVOICING,
        Perm.AUDIT_READ_INVOICING,
    ],
    # Read-only by design (BR-22). Must never receive a write permission.
    "supervisor": [
        *_COMMON,
        Perm.USERS_READ,
        Perm.SETTINGS_READ,
        Perm.BARRELS_READ,
        Perm.STOCK_READ_FREE,
        Perm.ORDERS_READ_ALL,
        Perm.DEBTORS_READ,
        Perm.PUMPS_READ,
        Perm.INVOICES_READ,
        Perm.REPORTS_READ_ALL,
        Perm.AUDIT_READ_ALL,
    ],
    "user": [
        *_COMMON,
        Perm.STOCK_READ_FREE,
        Perm.ORDERS_READ_OWN,
        Perm.ORDERS_CREATE,
        Perm.EXCEPTIONS_CREATE,
        Perm.PUMPS_READ,
    ],
}

# Permissions that can change data. Used by tests to prove the supervisor bundle is read-only.
WRITE_PERMISSIONS: Final[frozenset[str]] = frozenset(
    code
    for code in PERMISSIONS
    if code.split(".")[1].split("_")[0]
    in {"manage", "create", "decide", "record", "draft", "issue"}
)
