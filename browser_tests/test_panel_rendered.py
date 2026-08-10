"""Rendered-result checks for the live December panel.

The fast suite in ``tests/test_panel_*`` intentionally reasons about the source
stylesheet and script. This module crosses the remaining boundary: it serves a
real merged project, lets Chromium render the packaged panel, and reads the DOM
and computed styles the user actually receives.

It lives outside pytest's configured ``testpaths`` so Playwright remains an
explicit development/CI dependency. Run it with ``pytest browser_tests`` after
installing the ``browser`` extra and Chromium.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

from conductor import demo, server


@pytest.fixture(scope="session")
def panel_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Serve the packaged demo through the production loopback server."""
    root = demo.materialize(tmp_path_factory.mktemp("rendered-panel"))
    httpd = server.build(root, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    try:
        yield f"http://{host}:{port}/"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "panel server did not stop"


@pytest.fixture(scope="session")
def chromium() -> Iterator[Browser]:
    """Launch the same Chromium engine the independent CI job installs."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture(params=("dark", "light"))
def panel_page(chromium: Browser, panel_url: str, request: pytest.FixtureRequest) -> Iterator[Page]:
    """Open one isolated panel in each approved December colour scheme."""
    context = chromium.new_context(
        color_scheme=request.param,
        viewport={"width": 1440, "height": 1200},
    )
    page = context.new_page()
    page.goto(panel_url, wait_until="domcontentloaded")
    page.locator('[data-node="smoke"]').wait_for(state="visible")
    try:
        yield page
    finally:
        context.close()


def _box_profile(page: Page, node_id: str) -> dict[str, str | None]:
    """Read the browser's status-owned geometry and paint for one map node."""
    return page.locator(f'[data-node="{node_id}"] .box').evaluate(
        """box => {
          const style = getComputedStyle(box);
          return {
            rx: box.getAttribute("rx"),
            fill: style.fill,
            stroke: style.stroke,
            strokeWidth: style.strokeWidth,
            strokeDasharray: style.strokeDasharray,
            opacity: style.opacity,
          };
        }"""
    )


_CONTRAST = r"""({selector, property, against}) => {
  const target = document.querySelector(selector);
  if (!target) throw new Error("missing foreground: " + selector);

  function colour(value) {
    value = String(value).trim().toLowerCase();
    if (value === "transparent") return [0, 0, 0, 0];
    if (value.startsWith("color(srgb")) {
      const body = value.slice(value.indexOf(" ") + 1, -1);
      const halves = body.split("/");
      const channels = halves[0].trim().split(/\s+/).map(Number);
      return [channels[0] * 255, channels[1] * 255, channels[2] * 255,
              halves[1] === undefined ? 1 : Number(halves[1].trim())];
    }
    const match = value.match(/^rgba?\((.+)\)$/);
    if (!match) throw new Error("unsupported computed colour: " + value);
    const parts = match[1].replace(/,/g, " ").split(/\s+/).filter(Boolean);
    const channel = part => part.endsWith("%") ? parseFloat(part) * 2.55 : Number(part);
    return [channel(parts[0]), channel(parts[1]), channel(parts[2]),
            parts[3] === undefined ? 1 : Number(parts[3])];
  }

  function over(front, back) {
    const alpha = front[3] + back[3] * (1 - front[3]);
    if (!alpha) return [0, 0, 0, 0];
    return [
      (front[0] * front[3] + back[0] * back[3] * (1 - front[3])) / alpha,
      (front[1] * front[3] + back[1] * back[3] * (1 - front[3])) / alpha,
      (front[2] * front[3] + back[2] * back[3] * (1 - front[3])) / alpha,
      alpha,
    ];
  }

  function surface(element) {
    const chain = [];
    for (let node = element; node; node = node.parentElement) chain.push(node);
    let result = [0, 0, 0, 0];
    for (const node of chain.reverse())
      result = over(colour(getComputedStyle(node).backgroundColor), result);
    return result[3] < 1 ? over(result, [255, 255, 255, 1]) : result;
  }

  function luminance(rgb) {
    const linear = rgb.slice(0, 3).map(value => {
      const channel = value / 255;
      return channel <= .04045 ? channel / 12.92 : Math.pow((channel + .055) / 1.055, 2.4);
    });
    return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2];
  }

  const backdrop = against === "parent" ? surface(target.parentElement) : surface(target);
  const foreground = over(colour(getComputedStyle(target)[property]), backdrop);
  const a = luminance(foreground), b = luminance(backdrop);
  return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
}"""


def _contrast(page: Page, selector: str, property_name: str = "color",
              against: str = "self") -> float:
    """Measure a computed foreground against its composited live surface."""
    return page.evaluate(
        _CONTRAST,
        {"selector": selector, "property": property_name, "against": against},
    )


def test_rendered_status_channels_survive_pointer_focus_and_selection(panel_page: Page) -> None:
    """A real interaction cannot make a status impersonate another status."""
    expected = {
        "schemas": "pass",
        "api": "pass",
        "frontend": "pass",
        "stage": "pass",
        "deploy": "pass",
        "smoke": "fail",
        "live": "blocked",
    }
    for node_id, status in expected.items():
        node = panel_page.locator(f'[data-node="{node_id}"]')
        assert f"node--{status}" in (node.get_attribute("class") or "")
        rendered_mark = node.locator("text").last.text_content().strip()
        assert rendered_mark.endswith(" " + status)
        assert rendered_mark != status
        assert (node.get_attribute("aria-label") or "").endswith(": " + status)

    fail = panel_page.locator('[data-node="smoke"]')
    before = _box_profile(panel_page, "smoke")
    halo_before = fail.locator(".halo").evaluate("node => getComputedStyle(node).stroke")

    fail.hover()
    halo_hover = fail.locator(".halo").evaluate("node => getComputedStyle(node).stroke")
    assert halo_hover != halo_before
    assert _box_profile(panel_page, "smoke") == before

    fail.focus()
    fail.press("Enter")
    assert fail.get_attribute("aria-pressed") == "true"
    assert _box_profile(panel_page, "smoke") == before

    distinct = {
        tuple(_box_profile(panel_page, node_id).values())
        for node_id in ("schemas", "smoke", "live")
    }
    assert len(distinct) == 3


def test_browser_composites_status_chips_above_their_declared_thresholds(panel_page: Page) -> None:
    """Measure shipped word, glyph, and border pairs after Chromium composites them."""
    for node_id, status in (("schemas", "pass"), ("smoke", "fail"), ("live", "blocked")):
        panel_page.locator(f'[data-node="{node_id}"]').click()
        pill = panel_page.locator(f"#det .pill.p--{status}")
        pill.wait_for(state="visible")
        assert _contrast(panel_page, f"#det .pill.p--{status}") >= 4.5
        assert _contrast(panel_page, f"#det .pill.p--{status} .gl") >= 3.0
        assert _contrast(
            panel_page,
            f"#det .pill.p--{status}",
            property_name="borderColor",
            against="parent",
        ) >= 3.0


def test_rendered_orbit_keeps_order_return_and_non_overlapping_stages(panel_page: Page) -> None:
    """Both responsive layouts remain a closed, data-sized cycle in the live DOM."""
    names = ["plan", "implement", "review", "human-gate"]
    assert panel_page.locator("#orbitBody .orb__name").all_text_contents() == names
    assert "orbit--ring" in (panel_page.locator("#orbitField").get_attribute("class") or "")
    assert panel_page.locator("#orbitSvg .trk").count() == len(names)
    assert panel_page.locator("#orbitSvg .trk--next").count() == 1

    overlaps = panel_page.locator("#orbitBody .orb").evaluate_all(
        """stages => stages.flatMap((a, i) => stages.slice(i + 1).map(b => {
          const x = a.getBoundingClientRect(), y = b.getBoundingClientRect();
          return x.left < y.right && x.right > y.left && x.top < y.bottom && x.bottom > y.top;
        })).filter(Boolean).length"""
    )
    assert overlaps == 0

    panel_page.set_viewport_size({"width": 640, "height": 1200})
    panel_page.wait_for_function(
        "!document.querySelector('#orbitField').classList.contains('orbit--ring')"
    )
    assert "orbit--ring" not in (panel_page.locator("#orbitField").get_attribute("class") or "")
    assert panel_page.locator("#orbitSvg").evaluate("svg => getComputedStyle(svg).display") == "none"
    assert panel_page.locator("#orbitBody .orb__name").all_text_contents() == names
    assert panel_page.locator("#orbitBody .lnk:not(.lnk--next)").count() == len(names) - 1
    assert panel_page.locator("#orbitBody .lnk--next").count() == 1
    assert "next Run" in panel_page.locator("#orbitBody .lnk--next").inner_text()


def test_attention_light_is_derived_from_the_served_project_state(panel_page: Page) -> None:
    """The material level names the live state; clocks and invented ids cannot affect it."""
    state_name = panel_page.evaluate(
        "fetch('/state.json', {cache: 'no-store'}).then(r => r.json()).then(s => s.project_status.state)"
    )
    expected = {"blocked": "high", "active": "low"}.get(state_name, "none")
    assert panel_page.locator("html").get_attribute("data-attention") == expected
