"""The Atlas planning card exposes two separate human decisions and preserves the operator input."""
from urllib.parse import urljoin

from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_studio_rendered import studio_url  # noqa: F401


def test_planner_renders_actual_limits_and_only_clicks_can_authorize(chromium, studio_url):
    context = chromium.new_context(viewport={"width": 375, "height": 810})
    page = context.new_page()
    try:
        page.goto(urljoin(studio_url, "/#new=1&lang=en"))
        expect(page.locator("#planner")).to_have_count(1)
        page.evaluate("""async () => {
          const {renderPlanner} = await import("/panel/arachnid-planner-view.js");
          const host = document.createElement("div");
          host.id = "plannerWitness"; document.body.prepend(host);
          window.events = [];
          window.card = {sessionId:"new:one", locale:"en", phase:"advice-preview",
            actor:"local-operator", lead:"codex", model:"gpt-6.1-sol",
            input:{task:"Supplied material"},
            brief:"Inspect the counter", advicePreview:{terms:{run_id:"review-one", max_actions:1,
              max_action_seconds:153, max_total_task_seconds:153, duration_seconds:350,
              node_limits:[{node_id:"advise", timeout_seconds:153, max_attempts:1}]},
              preview_digest:"sha256:" + "a".repeat(64),
              valid_until:"2099-01-01T23:01:20Z"}};
          const h = Object.fromEntries(["actorChanged","reviewAdvice","authorizeAdvice",
            "prepareMain",
            "authorizeMain","refresh","openRun"].map(key => [key, arg => {
              window.events.push(key); if (key === "actorChanged") {
                window.card.actor = arg; window.redraw();
              }
            }]));
          window.redraw = () => renderPlanner(host, window.card, h); window.redraw();
        }""")
        host = page.locator("#plannerWitness")
        expect(host).to_contain_text("Inspect the counter")
        expect(host).to_contain_text("153")
        expect(host).to_contain_text("gpt-6.1-sol")
        expect(host).to_contain_text("quota is unknown")
        host.get_by_text("Material sent to Codex").click()
        expect(host.locator(".planner-exact pre").first).to_contain_text("Supplied material")
        assert not page.evaluate("events")
        actor = host.get_by_label("Operator")
        actor.fill("")
        expect(host.locator("[data-planner-action=authorizeAdvice]")).to_be_disabled()
        actor.fill("my-name")
        expect(actor).to_be_focused()
        host.locator("[data-planner-action=authorizeAdvice]").click()
        assert page.evaluate("events").count("authorizeAdvice") == 1
        assert "authorizeMain" not in page.evaluate("events")
        page.evaluate("""() => {
          card.phase = "main-preview"; card.mainPreview = null; redraw();
        }""")
        expect(host.locator("[data-planner-action=authorizeMain]")).to_have_count(0)
        page.evaluate("""() => {
          card.phase = "main-preview"; card.runId = "dalio-one";
          card.mainPreview = {...card.advicePreview,
            terms:{...card.advicePreview.terms, run_id:"dalio-one", max_actions:7}};
          redraw();
        }""")
        expect(host).to_contain_text("dalio-one")
        expect(host).to_contain_text("7")
        expect(actor).to_have_value("my-name")
        expect(actor).to_have_js_property("readOnly", True)
        host.locator("[data-planner-action=authorizeMain]").click()
        assert page.evaluate("events").count("authorizeMain") == 1
        page.evaluate("""() => {
          card.mainPreview.valid_until = "2000-01-01T00:00:00Z"; redraw();
        }""")
        expect(host).to_contain_text("has expired")
        expect(host.locator("[data-planner-action=authorizeMain]")).to_have_count(0)
        expect(host.locator("[data-planner-action=prepareMain]")).to_be_enabled()
        page.evaluate("""() => {
          card.phase = "proposal"; card.terms = card.mainPreview.terms;
          card.plan = {criterion:"The counter returns 4.", question:"Which input?", roles:{}};
          redraw();
        }""")
        expect(host).to_contain_text("Proposed limits")
        expect(host).to_contain_text("Reply in this chat")
        expect(host.locator("[data-planner-action=prepareMain]")).to_have_count(0)
        page.evaluate("""() => {
          card.phase = "blocked"; card.issue = "subscription_unavailable"; redraw();
        }""")
        expect(host.locator("[data-planner-action=authorizeMain]")).to_have_count(0)
        expect(host.locator("[data-planner-action=refresh]")).to_be_visible()
    finally:
        close_context(context)
