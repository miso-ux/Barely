"""Domain errors. Each carries an i18n message key so routers can show it without branching."""

from typing import Any


class DomainError(Exception):
    message_key: str = "error.generic"

    def __init__(self, **params: Any) -> None:
        super().__init__(self.message_key)
        self.params = params


class InvalidCredentials(DomainError):
    message_key = "error.invalid_credentials"


class WeakPassword(DomainError):
    message_key = "error.weak_password"


class WrongCurrentPassword(DomainError):
    message_key = "error.wrong_current_password"


class UsernameTaken(DomainError):
    message_key = "error.username_taken"


class InvalidUsername(DomainError):
    message_key = "error.invalid_username"


class RegistrationDisabled(DomainError):
    message_key = "error.registration_disabled"


class NoRoleSelected(DomainError):
    message_key = "error.no_role_selected"


class UnknownRole(DomainError):
    message_key = "error.unknown_role"


class SelfRoleChange(DomainError):
    message_key = "error.self_role_change"


class SelfDeactivation(DomainError):
    message_key = "error.self_deactivation"


class ForbiddenRoleCombination(DomainError):
    message_key = "error.forbidden_role_combination"


class InvalidSettingValue(DomainError):
    message_key = "error.invalid_setting_value"


class UnknownSetting(DomainError):
    message_key = "error.unknown_setting"


class InvalidBarrelTransition(DomainError):
    message_key = "error.invalid_barrel_transition"


class ReasonRequired(DomainError):
    message_key = "error.reason_required"


class InvalidCount(DomainError):
    message_key = "error.invalid_count"


class InvalidBarrelCode(DomainError):
    message_key = "error.invalid_barrel_code"


class BarrelCodeTaken(DomainError):
    message_key = "error.barrel_code_taken"
