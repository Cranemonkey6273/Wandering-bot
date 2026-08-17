from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SOURCE = (ROOT / "dashboard.py").read_text(encoding="utf-8")


def test_command_navigation_panel_visibility_requires_open_state():
    assert ".command-top-nav details[open] .nav-menu" in DASHBOARD_SOURCE
    assert ".command-top-nav details:hover .nav-menu" not in DASHBOARD_SOURCE
    assert ".command-top-nav details:focus-within .nav-menu" not in DASHBOARD_SOURCE


def test_command_navigation_closes_stale_and_competing_menus():
    assert 'group.setAttribute("name", "wandering-command-navigation")' in DASHBOARD_SOURCE
    assert "if (group.open) closeGroups(group);" in DASHBOARD_SOURCE
    assert 'if (event.target.closest("a"))' in DASHBOARD_SOURCE
    assert "if (!nav.contains(event.target))" in DASHBOARD_SOURCE
    assert 'if (event.key !== "Escape") return;' in DASHBOARD_SOURCE
    assert 'window.addEventListener("pageshow", () => closeGroups());' in DASHBOARD_SOURCE
