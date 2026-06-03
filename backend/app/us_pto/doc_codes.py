from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import yaml

from app.us_pto.config import DOC_CODES_CONFIG
from app.us_pto.email_templates import DOC_CODE_TEMPLATES


def _ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def build_interval_rules(base_months: int, extension_months: int = 0) -> list[tuple[int, str, int]]:
    rules: list[tuple[int, str, int]] = []
    for month_offset in range(1, base_months + 1):
        label = f"{_ordinal(month_offset)} Month Deadline"
        if month_offset == base_months:
            label = f"{_ordinal(month_offset)} Month [FINAL] Deadline"
        rules.append((month_offset, label, base_months))
    for extension_index in range(1, extension_months + 1):
        month_offset = base_months + extension_index
        rules.append((month_offset, f"{_ordinal(extension_index)} Month Extension Deadline", base_months))
    return rules


def custom_month_reminders(months: list[int]) -> list[tuple[int, str, int]]:
    return [
        (month, "24th Month Deadline" if month == 24 else f"Month {month} Reminder", month)
        for month in months
    ]


def _profile_to_rules(profile_name: str, profiles: dict[str, Any]) -> list[tuple[int, str, int]]:
    profile = profiles.get(profile_name, {})
    if "months" in profile:
        return custom_month_reminders(profile["months"])
    base_months = int(profile.get("base_months", 0))
    extension_months = int(profile.get("extension_months", 0))
    return build_interval_rules(base_months, extension_months)


@lru_cache(maxsize=1)
def load_doc_codes_config() -> dict[str, Any]:
    if not os.path.exists(DOC_CODES_CONFIG):
        raise FileNotFoundError(f"Doc codes config not found: {DOC_CODES_CONFIG}")
    with open(DOC_CODES_CONFIG, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def get_tracked_doc_codes() -> list[str]:
    config = load_doc_codes_config()
    return [
        str(item["code"]).strip().upper()
        for item in config.get("tracked_doc_codes", [])
        if item.get("code")
    ]


def get_email_template_keys() -> list[str]:
    return sorted(DOC_CODE_TEMPLATES.keys())


def normalize_email_template_value(raw: Any) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value or value.lower() in {"null", "none", ""}:
        return None
    return value.upper()


def get_email_template_for_code(doc_code: str) -> str | None:
    """YAML-configured email template key for a doc code, or None."""
    normalized = str(doc_code or "").strip().upper()
    config = load_doc_codes_config()
    for item in config.get("tracked_doc_codes", []):
        code = str(item.get("code", "")).strip().upper()
        if code != normalized:
            continue
        template_key = normalize_email_template_value(item.get("email_template"))
        if not template_key:
            return None
        if template_key not in DOC_CODE_TEMPLATES:
            return None
        return template_key
    return None


def email_template_label_for_code(doc_code: str) -> str:
    """Human-readable template mapping (same criteria as Step 3 draft selection)."""
    template_key = get_email_template_for_code(doc_code)
    return template_key if template_key else "None"


def yaml_email_template_value(raw: Any) -> str | None:
    """Persist None/unassigned templates as the literal string 'None' in YAML."""
    template_key = normalize_email_template_value(raw)
    if template_key:
        return template_key
    return "None"


def code_requires_email_draft(doc_code: str) -> bool:
    return get_email_template_for_code(doc_code) is not None


def get_code_to_profile_map() -> dict[str, str]:
    config = load_doc_codes_config()
    mapping: dict[str, str] = {}
    for item in config.get("tracked_doc_codes", []):
        code = str(item.get("code", "")).strip().upper()
        profile = str(item.get("calendar_profile", "")).strip()
        if code and profile:
            mapping[code] = profile
    return mapping


def build_reminder_rules() -> dict[str, list[tuple[int, str, int]]]:
    config = load_doc_codes_config()
    profiles = config.get("calendar_profiles", {})
    code_to_profile = get_code_to_profile_map()
    rules: dict[str, list[tuple[int, str, int]]] = {}

    for code, profile_name in code_to_profile.items():
        rules[code] = _profile_to_rules(profile_name, profiles)

    fallback = config.get("fallback", {})
    if fallback.get("enabled") and fallback.get("calendar_profile"):
        rules["__FALLBACK__"] = _profile_to_rules(str(fallback["calendar_profile"]), profiles)

    return rules


def is_tracked_doc_code(doc_code: str) -> bool:
    normalized = str(doc_code or "").strip().upper()
    return normalized in get_tracked_doc_codes()


def get_rules_for_doc_code(doc_code: str) -> list[tuple[int, str, int]] | None:
    normalized = str(doc_code or "").strip().upper()
    rules_map = build_reminder_rules()
    if normalized in rules_map:
        return rules_map[normalized]
    if "__FALLBACK__" in rules_map:
        return rules_map["__FALLBACK__"]
    return None


def get_rules_for_tracked_doc_code(doc_code: str) -> list[tuple[int, str, int]] | None:
    """Calendar Step 2: tracked codes only, no fallback."""
    normalized = str(doc_code or "").strip().upper()
    if not is_tracked_doc_code(normalized):
        return None
    rules_map = build_reminder_rules()
    return rules_map.get(normalized)


def get_calendar_profile_names() -> list[str]:
    config = load_doc_codes_config()
    return sorted(config.get("calendar_profiles", {}).keys())


def save_doc_codes_config(config: dict[str, Any]) -> None:
    """Validate and persist doc_codes.yaml."""
    _validate_doc_codes_config(config)
    try:
        with open(DOC_CODES_CONFIG, "w", encoding="utf-8") as handle:
            yaml.safe_dump(config, handle, default_flow_style=False, sort_keys=False)
    except OSError as exc:
        raise ValueError(f"Could not write doc codes config at {DOC_CODES_CONFIG}: {exc}") from exc
    load_doc_codes_config.cache_clear()


def _validate_doc_codes_config(config: dict[str, Any]) -> None:
    profiles = config.get("calendar_profiles", {})
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("calendar_profiles must be a non-empty mapping")

    tracked = config.get("tracked_doc_codes", [])
    if not isinstance(tracked, list):
        raise ValueError("tracked_doc_codes must be a list")

    seen_codes: set[str] = set()
    for item in tracked:
        if not isinstance(item, dict):
            raise ValueError("Each tracked_doc_codes entry must be an object")
        code = str(item.get("code", "")).strip().upper()
        profile = str(item.get("calendar_profile", "")).strip()
        if not code:
            raise ValueError("tracked doc code cannot be empty")
        if code in seen_codes:
            raise ValueError(f"duplicate tracked doc code: {code}")
        seen_codes.add(code)
        if profile not in profiles:
            raise ValueError(f"unknown calendar_profile '{profile}' for code {code}")
        template_key = normalize_email_template_value(item.get("email_template"))
        if template_key and template_key not in DOC_CODE_TEMPLATES:
            raise ValueError(
                f"unknown email_template '{template_key}' for code {code}; "
                f"valid keys: {', '.join(sorted(DOC_CODE_TEMPLATES.keys()))}"
            )

    fallback = config.get("fallback", {})
    if isinstance(fallback, dict) and fallback.get("enabled"):
        fb_profile = str(fallback.get("calendar_profile", "")).strip()
        if fb_profile and fb_profile not in profiles:
            raise ValueError(f"unknown fallback calendar_profile '{fb_profile}'")


def config_for_api() -> dict[str, Any]:
    """JSON-friendly view for GET /doc-codes."""
    config = load_doc_codes_config()
    profiles = config.get("calendar_profiles", {})
    tracked = []
    for item in config.get("tracked_doc_codes", []):
        code = str(item.get("code", "")).strip().upper()
        tracked.append(
            {
                "code": code,
                "calendar_profile": str(item.get("calendar_profile", "")).strip(),
                "email_template": email_template_label_for_code(code),
            }
        )
    return {
        "tracked_doc_codes": tracked,
        "calendar_profile_names": sorted(profiles.keys()),
        "calendar_profiles": profiles,
        "fallback": config.get("fallback", {}),
        "email_template_keys": get_email_template_keys(),
        "config_path": DOC_CODES_CONFIG,
    }
