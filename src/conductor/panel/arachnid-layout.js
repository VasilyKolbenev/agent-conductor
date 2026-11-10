// Panel preferences contain two integer widths. They never reference a project or its evidence.
const KEY = "arachnid.panel-widths.v1";
const defaults = {sessions: 240, inspector: 420};
const clamp = (value, min, max) => Math.min(max, Math.max(min, Math.round(value)));

function readWidths() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY));
    if (saved && Object.keys(saved).length === 2 && Number.isInteger(saved.sessions) &&
        saved.sessions >= 184 && saved.sessions <= 320 && Number.isInteger(saved.inspector) &&
        saved.inspector >= 300 && saved.inspector <= 720)
      return {sessions: saved.sessions, inspector: saved.inspector};
  } catch { /* Disabled storage or an invalid old value: use the workspace defaults. */ }
  return {...defaults};
}

function writeWidths({sessions, inspector}) {
  try { localStorage.setItem(KEY, JSON.stringify({sessions, inspector})); }
  catch { /* In this browser the in-memory preference lasts for this visit. */ }
}

export function attachLayout(workspace, {locale, stop}) {
  const handles = {sessions: workspace.querySelector("#resizeSessions"),
    inspector: workspace.querySelector("#resizeInspector")};
  const events = stop(), options = {signal: events.signal};
  const doc = workspace.ownerDocument;
  let desired = readWidths(), drag = null, renderedWidth;

  function geometry() {
    const w = workspace.clientWidth, wide = w > 920;
    const open = workspace.classList.contains("with-detail");
    const chatMin = wide ? 360 : 280, rightMin = wide ? 320 : 300;
    const railBudget = wide && open ? w - chatMin - rightMin : 320;
    const sessions = clamp(desired.sessions, 184, Math.min(320, railBudget));
    const rightMax = Math.max(rightMin, Math.min(720, w - chatMin - (wide ? sessions : 0)));
    const inspector = clamp(desired.inspector, rightMin, rightMax);
    const leftMax = wide && open ? Math.min(320, w - chatMin - inspector) : 320;
    return {
      sessions: {value: sessions, min: 184, max: leftMax, active: wide},
      inspector: {value: inspector, min: rightMin, max: rightMax,
        active: w > 700 && open && (wide || !workspace.classList.contains("nav-open"))}
    };
  }

  function paint() {
    const spans = geometry();
    for (const [pane, handle] of Object.entries(handles)) {
      const {value, min, max} = spans[pane];
      workspace.style.setProperty("--" + pane + "-width", value + "px");
      handle.setAttribute("aria-valuemin", String(min));
      handle.setAttribute("aria-valuemax", String(max));
      handle.setAttribute("aria-valuenow", String(value));
      handle.setAttribute("aria-valuetext", value + (locale() === "ru" ? " пикс." : " px"));
    }
    renderedWidth = workspace.clientWidth;
  }

  function setWidth(pane, width) {
    const {min, max} = geometry()[pane];
    desired = {...desired, [pane]: clamp(width, min, max)};
    paint();
  }

  function finish(commit) {
    if (!drag) return;
    const {pane, pointer, before} = drag, handle = handles[pane];
    drag = null;
    delete workspace.dataset.resizing;
    if (handle.hasPointerCapture(pointer)) handle.releasePointerCapture(pointer);
    if (!commit) desired = before;
    else if (desired[pane] !== before[pane]) writeWidths(desired);
    paint();
  }

  function refresh() {
    if (drag && (workspace.clientWidth !== renderedWidth || !geometry()[drag.pane].active))
      finish(false);
    else paint();
  }

  for (const [pane, handle] of Object.entries(handles)) {
    const sign = pane === "sessions" ? 1 : -1;
    handle.addEventListener("pointerdown", event => {
      const {value, active} = geometry()[pane];
      if (drag || !active || !event.isPrimary || event.button !== 0) return;
      handle.setPointerCapture(event.pointerId);
      event.preventDefault(); // Keep the operator's text cursor in the conversation.
      drag = {pane, pointer: event.pointerId, startX: event.clientX, value, before: desired};
      workspace.dataset.resizing = pane;
    }, options);

    const moving = event => drag?.pane === pane && drag.pointer === event.pointerId;
    function follow(event) {
      const dx = event.clientX - drag.startX;
      if (dx === 0) { desired = drag.before; paint(); }
      else setWidth(pane, drag.value + sign * dx);
    }
    handle.addEventListener("pointermove", event => { if (moving(event)) follow(event); }, options);
    handle.addEventListener("pointerup", event => {
      if (moving(event)) { follow(event); finish(true); }
    }, options);
    for (const type of ["lostpointercapture", "pointercancel"])
      handle.addEventListener(type, event => { if (moving(event)) finish(false); }, options);
    handle.addEventListener("keydown", event => {
      const {value, min, max, active} = geometry()[pane];
      if (!active || drag || event.ctrlKey || event.metaKey || event.altKey) return;
      const step = (event.shiftKey ? 32 : 8) * sign;
      const next = {Home: min, End: max, ArrowLeft: value - step, ArrowRight: value + step};
      if (!Object.hasOwn(next, event.key)) return;
      event.preventDefault();
      setWidth(pane, next[event.key]);
      writeWidths(desired);
    }, options);
  }

  doc.addEventListener("keydown", event => {
    if (event.key !== "Escape" || !drag) return;
    event.preventDefault();
    event.stopPropagation(); // Escape during a drag rolls it back without dismissing the panel.
    finish(false);
  }, {...options, capture: true});
  const resized = new ResizeObserver(refresh), changed = new MutationObserver(refresh);
  resized.observe(workspace);
  changed.observe(workspace, {attributes: true, attributeFilter: ["class"]});
  changed.observe(doc.documentElement, {attributes: true, attributeFilter: ["lang"]});
  paint();
  return {dispose() {
    resized.disconnect(); changed.disconnect(); events.abort(); finish(false);
  }};
}
