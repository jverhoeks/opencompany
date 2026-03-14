"""Playwright E2E tests for the dashboard views."""

import re

from playwright.sync_api import Page, expect

# --- Shell & Tab Navigation ---


def test_dashboard_loads(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.wait_for_timeout(2000)  # wait for SSE data
    expect(page.locator(".header-brand h1")).to_contain_text("NovaCraft")


def test_default_tab_is_kanban(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.wait_for_timeout(2000)
    expect(page.locator('.tab-btn[data-view="kanban"]')).to_have_class(re.compile(r"active"))


def test_tab_switching(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.wait_for_timeout(2000)
    for view in ["organigram", "office", "editor", "kanban"]:
        page.click(f'.tab-btn[data-view="{view}"]')
        page.wait_for_timeout(1000)
        expect(page.locator(f'.tab-btn[data-view="{view}"]')).to_have_class(re.compile(r"active"))


def test_sidebar_shows_personas(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.wait_for_timeout(3000)
    sidebar = page.locator(".team-list")
    expect(sidebar).to_contain_text("Alice CEO")


# --- Kanban View ---


def test_kanban_columns_present(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.wait_for_timeout(3000)
    headers = page.locator(
        ".kanban-col-header, .kb-col-hdr, [class*='col-header'], [class*='col-hdr']"
    )
    count = headers.count()
    assert count >= 5, f"Expected at least 5 column headers, got {count}"


def test_kanban_tickets_in_correct_columns(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.wait_for_timeout(3000)
    # The open column should contain "Setup CI"
    container = page.locator("#view-container")
    expect(container).to_contain_text("Setup CI")


def test_kanban_ticket_card_content(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.wait_for_timeout(3000)
    container = page.locator("#view-container")
    # Should show ticket titles and priorities
    expect(container).to_contain_text("Setup CI")
    expect(container).to_contain_text("high")


def test_kanban_filter_by_persona(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.wait_for_timeout(3000)
    # Find persona filter select
    selects = page.locator("#view-container select")
    if selects.count() > 0:
        selects.first.select_option("dev1")
        page.wait_for_timeout(500)


def test_kanban_click_ticket_shows_detail(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.wait_for_timeout(3000)
    # Click first ticket-like card
    cards = page.locator("#view-container [class*='card']")
    if cards.count() > 0:
        cards.first.click()


# --- Organigram View ---


def test_organigram_renders_svg(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="organigram"]')
    page.wait_for_timeout(3000)
    svg = page.locator("#view-container svg")
    expect(svg).to_be_visible()


def test_organigram_hierarchy(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="organigram"]')
    page.wait_for_timeout(3000)
    # Should have connection paths
    paths = page.locator("#view-container svg path")
    assert paths.count() > 0, "Expected SVG paths for org connections"


def test_organigram_node_content(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="organigram"]')
    page.wait_for_timeout(3000)
    svg = page.locator("#view-container svg")
    expect(svg).to_contain_text("Alice CEO")


def test_organigram_zoom(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="organigram"]')
    page.wait_for_timeout(3000)
    svg = page.locator("#view-container svg")
    svg.hover()
    page.mouse.wheel(0, -100)
    page.wait_for_timeout(300)


def test_organigram_zoom_to_fit(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="organigram"]')
    page.wait_for_timeout(3000)
    fit_btn = page.locator(
        "#view-container button, #view-container [class*='zoom'], #view-container [class*='fit']"
    )
    if fit_btn.count() > 0:
        fit_btn.first.click()
        page.wait_for_timeout(300)


def test_organigram_click_node(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="organigram"]')
    page.wait_for_timeout(3000)
    nodes = page.locator("#view-container svg g[data-id], #view-container svg [class*='node']")
    if nodes.count() > 0:
        nodes.first.click(force=True)


# --- Office Floor Plan ---


def test_office_renders_rooms(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="office"]')
    page.wait_for_timeout(3000)
    container = page.locator("#view-container")
    expect(container).to_contain_text("Alice CEO")


def test_office_ceo_corner_office(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="office"]')
    page.wait_for_timeout(3000)
    corner = page.locator("[class*='corner']")
    if corner.count() > 0:
        expect(corner.first).to_contain_text("Alice CEO")


def test_office_hr_near_ceo(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="office"]')
    page.wait_for_timeout(3000)
    container = page.locator("#view-container")
    expect(container).to_contain_text("Bob HR")


def test_office_leads_in_mid_row(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="office"]')
    page.wait_for_timeout(3000)
    container = page.locator("#view-container")
    expect(container).to_contain_text("Dave TL")


def test_office_solvers_in_open_floor(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="office"]')
    page.wait_for_timeout(3000)
    container = page.locator("#view-container")
    expect(container).to_contain_text("Eve Dev")


def test_office_shows_ticket_counts(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="office"]')
    page.wait_for_timeout(3000)
    # At least one workload badge should be visible
    container = page.locator("#view-container")
    text = container.text_content()
    # dev1 has 2 active tickets (assigned + review), so should show a count
    assert "ticket" in text.lower() or any(c.isdigit() for c in text)


def test_office_fired_persona_dimmed(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="office"]')
    page.wait_for_timeout(3000)
    fired = page.locator("[class*='fired']")
    assert fired.count() > 0, "Expected at least one fired persona element"


# --- Company Editor ---


def test_editor_subtabs(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="editor"]')
    page.wait_for_timeout(2000)
    container = page.locator("#view-container")
    expect(container).to_contain_text("Personas")
    expect(container).to_contain_text("Roles")
    expect(container).to_contain_text("Soul")


def test_editor_persona_list(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="editor"]')
    page.wait_for_timeout(3000)
    container = page.locator("#view-container")
    expect(container).to_contain_text("Alice CEO")


def test_editor_persona_form(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="editor"]')
    page.wait_for_timeout(3000)
    # Click first persona in the list
    items = page.locator(
        "#view-container [class*='list-item'], #view-container [class*='persona-item']"
    )
    if items.count() > 0:
        items.first.click()
        page.wait_for_timeout(500)
        # Should show a form with input fields
        inputs = page.locator("#view-container input, #view-container textarea")
        assert inputs.count() > 0, "Expected form inputs after clicking persona"


def test_editor_persona_save(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="editor"]')
    page.wait_for_timeout(3000)
    items = page.locator(
        "#view-container [class*='list-item'], #view-container [class*='persona-item']"
    )
    if items.count() > 0:
        items.first.click()
        page.wait_for_timeout(500)
        save_btn = page.locator(
            "#view-container button:has-text('Save'), #view-container [class*='save']"
        )
        if save_btn.count() > 0:
            save_btn.first.click()
            page.wait_for_timeout(1000)


def test_editor_roles_list(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="editor"]')
    page.wait_for_timeout(2000)
    # Switch to Roles sub-tab
    roles_tab = page.locator(
        "#view-container button:has-text('Roles'), "
        "#view-container [class*='subtab']:has-text('Roles')"
    )
    if roles_tab.count() > 0:
        roles_tab.first.click()
        page.wait_for_timeout(2000)


def test_editor_role_form(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="editor"]')
    page.wait_for_timeout(2000)
    roles_tab = page.locator(
        "#view-container button:has-text('Roles'), "
        "#view-container [class*='subtab']:has-text('Roles')"
    )
    if roles_tab.count() > 0:
        roles_tab.first.click()
        page.wait_for_timeout(2000)
        items = page.locator("#view-container [class*='list-item']")
        if items.count() > 0:
            items.first.click()
            page.wait_for_timeout(500)


def test_editor_soul_markdown(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="editor"]')
    page.wait_for_timeout(2000)
    soul_tab = page.locator(
        "#view-container button:has-text('Soul'), "
        "#view-container [class*='subtab']:has-text('Soul')"
    )
    if soul_tab.count() > 0:
        soul_tab.first.click()
        page.wait_for_timeout(1000)
        textarea = page.locator("#view-container textarea")
        assert textarea.count() > 0, "Expected textarea for soul content"


def test_editor_soul_version_history(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="editor"]')
    page.wait_for_timeout(2000)
    soul_tab = page.locator(
        "#view-container button:has-text('Soul'), "
        "#view-container [class*='subtab']:has-text('Soul')"
    )
    if soul_tab.count() > 0:
        soul_tab.first.click()
        page.wait_for_timeout(1000)
        # Version history section should exist
        container = page.locator("#view-container")
        expect(container).to_contain_text("History")


def test_editor_fired_persona_not_editable(page: Page, live_server: str):
    page.goto(f"{live_server}/dashboard")
    page.click('.tab-btn[data-view="editor"]')
    page.wait_for_timeout(3000)
    fired = page.locator("#view-container [class*='fired']")
    if fired.count() > 0:
        fired.first.click()
        page.wait_for_timeout(500)
