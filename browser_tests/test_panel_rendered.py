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
from io import BytesIO

import pytest
from PIL import Image
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


def _box_profile(page: Page, node_id: str) -> dict[str, object]:
    """Capture a status box as geometry plus pixels, not a CSS-property list."""
    box = page.locator(f'[data-node="{node_id}"] .box')
    geometry = box.evaluate(
        """node => {
          const rect = node.getBoundingClientRect(), matrix = node.getScreenCTM();
          return {
            rect: [rect.x, rect.y, rect.width, rect.height],
            matrix: matrix && [matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f],
          };
        }"""
    )
    # The halo and generic focus outline are the interaction feedback expressly
    # allowed to change. Hide only those siblings while rasterizing the status
    # carrier; :hover/:focus/aria-pressed still apply to the box itself.
    saved = box.evaluate(
        """node => {
          const group = node.parentElement, halo = group.querySelector(".halo");
          const state = {halo: halo.style.visibility, outline: group.style.outline};
          halo.style.visibility = "hidden";
          group.style.outline = "none";
          return state;
        }"""
    )
    try:
        png = box.screenshot(animations="disabled", scale="css")
    finally:
        box.evaluate(
            """(node, state) => {
              const group = node.parentElement, halo = group.querySelector(".halo");
              halo.style.visibility = state.halo;
              group.style.outline = state.outline;
            }""",
            saved,
        )
    with Image.open(BytesIO(png)) as image:
        pixels = (image.size, image.convert("RGBA").tobytes())
    return {"geometry": geometry, "pixels": pixels}


_CONTRAST = r"""({selector, property, against, index}) => {
  const target = document.querySelectorAll(selector)[index || 0];
  if (!target) throw new Error("missing foreground: " + selector);

  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 1;
  const context = canvas.getContext("2d", {willReadFrequently: true});
  function colour(value) {
    context.clearRect(0, 0, 1, 1);
    context.fillStyle = "rgba(0,0,0,0)";
    context.fillStyle = String(value);
    context.fillRect(0, 0, 1, 1);
    const actual = context.getImageData(0, 0, 1, 1).data;
    return [actual[0], actual[1], actual[2], actual[3] / 255];
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
              against: str = "self", index: int = 0) -> float:
    """Measure a computed foreground against its composited live surface."""
    return page.evaluate(
        _CONTRAST,
        {"selector": selector, "property": property_name, "against": against,
         "index": index},
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

    for node_id in ("schemas", "smoke", "live"):
        node = panel_page.locator(f'[data-node="{node_id}"]')
        node.scroll_into_view_if_needed()
        before = _box_profile(panel_page, node_id)
        halo_before = node.locator(".halo").evaluate("item => getComputedStyle(item).stroke")

        node.hover()
        halo_hover = node.locator(".halo").evaluate("item => getComputedStyle(item).stroke")
        assert halo_hover != halo_before
        assert _box_profile(panel_page, node_id) == before

        node.focus()
        assert _box_profile(panel_page, node_id) == before
        node.press("Enter")
        assert node.get_attribute("aria-pressed") == "true"
        assert _box_profile(panel_page, node_id) == before

    distinct = {
        _box_profile(panel_page, node_id)["pixels"]
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

    visible = 0
    verdicts = panel_page.locator(".vd")
    for index in range(verdicts.count()):
        verdict = verdicts.nth(index)
        if not verdict.is_visible():
            continue
        visible += 1
        key = f"verdict-{index}"
        verdict.evaluate("(node, value) => node.dataset.renderCheck = value", key)
        selector = f'[data-render-check="{key}"]'
        assert _contrast(panel_page, selector) >= 4.5
        assert _contrast(panel_page, selector + " .gl") >= 3.0
        assert _contrast(
            panel_page, selector, property_name="borderColor", against="parent"
        ) >= 3.0
    assert visible > 0


def test_extended_srgb_is_measured_as_the_pixels_chromium_draws(panel_page: Page) -> None:
    """Out-of-gamut computed colours are normalized before contrast arithmetic."""
    panel_page.evaluate(
        """() => {
          const probe = document.createElement("span");
          probe.id = "gamutProbe";
          probe.style.cssText = "color:color(srgb 2 2 2);background:rgb(255 255 255)";
          probe.textContent = "probe";
          document.body.append(probe);
        }"""
    )
    assert _contrast(panel_page, "#gamutProbe") == pytest.approx(1.0)


def test_rendered_orbit_keeps_order_return_and_non_overlapping_stages(panel_page: Page) -> None:
    """Both responsive layouts remain a closed, data-sized cycle in the live DOM."""
    names = ["plan", "implement", "review", "human-gate"]
    assert panel_page.locator("#orbitBody .orb__name").all_text_contents() == names
    assert "orbit--ring" in (panel_page.locator("#orbitField").get_attribute("class") or "")
    assert panel_page.locator("#orbitSvg .trk").count() == len(names)
    assert panel_page.locator("#orbitSvg .trk--next").count() == 1

    geometry = panel_page.locator("#orbitField").evaluate(
        """field => {
          const stages = [...field.querySelectorAll(".orb")];
          const centers = stages.map(stage => {
            const box = stage.getBoundingClientRect();
            return {x: box.left + box.width / 2, y: box.top + box.height / 2, box};
          });
          const nearest = point => centers.reduce((best, center, index) => {
            const distance = Math.hypot(center.x - point.x, center.y - point.y);
            return distance < best.distance ? {index, distance} : best;
          }, {index: -1, distance: Infinity}).index;
          const links = [...field.querySelectorAll(".trk")].map(path => {
            const matrix = path.getScreenCTM(), length = path.getTotalLength();
            const at = offset => {
              const raw = path.getPointAtLength(offset);
              const point = new DOMPoint(raw.x, raw.y);
              return point.matrixTransform(matrix);
            };
            return [nearest(at(0)), nearest(at(length))];
          });
          const area = Math.abs(centers.reduce((sum, point, index) => {
            const next = centers[(index + 1) % centers.length];
            return sum + point.x * next.y - next.x * point.y;
          }, 0)) / 2;
          const overlaps = centers.flatMap((a, i) => centers.slice(i + 1).map(b =>
            a.box.left < b.box.right && a.box.right > b.box.left &&
            a.box.top < b.box.bottom && a.box.bottom > b.box.top
          )).filter(Boolean).length;
          return {area, links, overlaps};
        }"""
    )
    assert geometry["overlaps"] == 0
    assert geometry["area"] > 1_000
    assert geometry["links"] == [[0, 1], [1, 2], [2, 3], [3, 0]]

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


def test_the_split_cockpit_modules_boot_as_one_script_without_a_console_error(
        chromium: Browser, panel_url: str) -> None:
    """Chromium must resolve the whole module graph and mount the live Cockpit."""
    context = chromium.new_context(viewport={"width": 1440, "height": 1200})
    page = context.new_page()
    problems: list[str] = []
    served: list[tuple[str, int]] = []

    def note_console(message: object) -> None:
        if getattr(message, "type", "") == "error":
            problems.append(getattr(message, "text", ""))

    page.on("console", note_console)
    page.on("pageerror", lambda error: problems.append(str(error)))
    page.on("response", lambda response: served.append(
        (response.url, response.status)))
    try:
        page.goto(panel_url, wait_until="load")
        cockpit = page.locator("#commandCockpit")
        cockpit.locator("#commandRunId").wait_for(state="visible")
        assert cockpit.locator(".command-status").inner_text().startswith(
            "Enter a run id")
        assert cockpit.locator(".empty").count() == 0
        assert {
            url.rsplit("/", 1)[1]: status for url, status in served
            if "/panel/" in url
        } == {
            "command.css": 200, "command.js": 200,
            "command-projection.js": 200, "command-view.js": 200,
        }
        assert problems == []
    finally:
        context.close()


def test_attention_light_is_derived_from_the_served_project_state(panel_page: Page) -> None:
    """The material level names the live state; clocks and invented ids cannot affect it."""
    state_name = panel_page.evaluate(
        "fetch('/state.json', {cache: 'no-store'}).then(r => r.json()).then(s => s.project_status.state)"
    )
    expected = {"blocked": "high", "active": "low"}.get(state_name, "none")
    assert panel_page.locator("html").get_attribute("data-attention") == expected
