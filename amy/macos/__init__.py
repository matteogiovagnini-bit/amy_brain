"""Integrazione macOS."""

from .applescript import (
    MacOSError,
    activate_application,
    application_is_running,
    battery_status,
    battery_summary,
    find_application,
    frontmost_application,
    list_installed_apps,
    open_application,
    open_system_settings,
    open_url,
    parse_battery_output,
    quit_application,
    run_osascript,
    system_info,
    top_processes,
)

__all__ = [
    "MacOSError",
    "activate_application",
    "application_is_running",
    "battery_status",
    "battery_summary",
    "find_application",
    "frontmost_application",
    "list_installed_apps",
    "open_application",
    "open_system_settings",
    "open_url",
    "parse_battery_output",
    "quit_application",
    "run_osascript",
    "system_info",
    "top_processes",
]
