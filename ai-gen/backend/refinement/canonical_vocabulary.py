"""Canonical engineering vocabulary for semantic refinement."""

from __future__ import annotations


FLOWS = {
    "login",
    "signup",
    "forgot_password",
    "otp_verification",
    "dashboard",
    "profile",
    "payment",
    "checkout",
    "approval",
    "document_upload",
    "settings",
    "search",
    "filter",
    "notification",
}

VARIANTS = {
    "phone_otp",
    "phone_number",
    "email_password",
    "social_login",
    "otp_only",
    "multi_step_form",
    "list_filter",
    "role_based",
    "attachment_upload",
}

SURFACES = {
    "ui_screen",
    "ui_validation",
    "ui_state",
    "api_controller",
    "api_validation",
    "service_logic",
    "database",
    "authentication",
    "authorization",
    "workflow",
    "notification_flow",
}

FIELDS = {
    "phone_number",
    "otp",
    "email",
    "password",
    "username",
    "attachment",
    "role",
    "amount",
    "search_query",
    "filter_value",
}

VALIDATIONS = {
    "required",
    "format",
    "regex",
    "length_limit",
    "range_limit",
    "uniqueness",
    "auth_required",
    "permission_required",
}

FLOW_ALIASES = {
    "sign_in": "login",
    "signin": "login",
    "signon": "login",
    "auth": "login",
    "authentication": "login",
    "register": "signup",
    "registration": "signup",
    "create_account": "signup",
    "reset_password": "forgot_password",
    "forgotpassword": "forgot_password",
    "verification": "otp_verification",
    "verify_code": "otp_verification",
    "verify_phone": "otp_verification",
    "home": "dashboard",
    "overview": "dashboard",
    "account": "profile",
    "billing": "payment",
    "transaction": "payment",
    "purchase": "checkout",
    "authorize": "approval",
    "upload": "document_upload",
    "file_upload": "document_upload",
    "preferences": "settings",
    "query": "search",
    "filters": "filter",
    "alerts": "notification",
}

VARIANT_ALIASES = {
    "mobile_otp": "phone_otp",
    "phone_login": "phone_otp",
    "phone_number_otp": "phone_otp",
    "otp_login": "phone_otp",
    "sms_code": "phone_otp",
    "verification_code": "phone_otp",
    "contact_number": "phone_number",
    "mobile_number": "phone_number",
    "phone_no": "phone_number",
    "mail_password": "email_password",
    "email_login": "email_password",
    "sso": "social_login",
    "otp_based": "otp_only",
    "step_form": "multi_step_form",
    "filter_list": "list_filter",
    "role_permissions": "role_based",
    "file_upload": "attachment_upload",
}

SURFACE_ALIASES = {
    "screen": "ui_screen",
    "page": "ui_screen",
    "form": "ui_screen",
    "component": "ui_screen",
    "validation": "ui_validation",
    "input_validation": "ui_validation",
    "state": "ui_state",
    "controller": "api_controller",
    "endpoint": "api_controller",
    "api": "api_controller",
    "request_validation": "api_validation",
    "service": "service_logic",
    "logic": "service_logic",
    "db": "database",
    "auth": "authentication",
    "authorization_flow": "authorization",
    "notify": "notification_flow",
}

FIELD_ALIASES = {
    "mobile": "phone_number",
    "mobile_no": "phone_number",
    "mobile_number": "phone_number",
    "contact_number": "phone_number",
    "phone": "phone_number",
    "phone_no": "phone_number",
    "sms_code": "otp",
    "verification_code": "otp",
    "one_time_password": "otp",
    "passcode": "otp",
    "mail": "email",
    "pwd": "password",
    "user_name": "username",
    "file": "attachment",
    "document": "attachment",
    "permission_role": "role",
    "price": "amount",
    "total": "amount",
    "search": "search_query",
    "query": "search_query",
    "filter": "filter_value",
}

VALIDATION_ALIASES = {
    "presence": "required",
    "email_format": "format",
    "phone_format": "format",
    "input_format": "format",
    "pattern": "regex",
    "max_length": "length_limit",
    "min_length": "length_limit",
    "length": "length_limit",
    "range": "range_limit",
    "unique": "uniqueness",
    "unique_value": "uniqueness",
    "authentication_required": "auth_required",
    "login_required": "auth_required",
    "authorization_required": "permission_required",
    "role_required": "permission_required",
}


def normalize_flow(value: str | None) -> str | None:
    return _normalize_value(value, FLOWS, FLOW_ALIASES)


def normalize_variant(value: str | None) -> str | None:
    return _normalize_value(value, VARIANTS, VARIANT_ALIASES)


def normalize_surface(value: str | None) -> str | None:
    return _normalize_value(value, SURFACES, SURFACE_ALIASES)


def normalize_field(value: str | None) -> str | None:
    return _normalize_value(value, FIELDS, FIELD_ALIASES)


def normalize_validation(value: str | None) -> str | None:
    return _normalize_value(value, VALIDATIONS, VALIDATION_ALIASES)


def canonicalize_token(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_value(value: str | None, allowed: set[str], aliases: dict[str, str]) -> str | None:
    token = canonicalize_token(value)
    if not token:
        return None
    token = aliases.get(token, token)
    return token if token in allowed else None
