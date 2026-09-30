"use strict";
// The frame of the hub's page: where a project's desk is mounted and what the page believes of it
// (spec 4.5.5). The desk runs in an iframe at the address the hub gave for that project, on an origin
// of its own, so the page can neither read what the desk draws nor write to it: it can only choose
// where the desk is opened, by the hash, and hear where the desk says it is, by one message.
//
// The first half is pure. The address of a desk is the hub's `desk_url` of a running project, held to
// the rule of 4.5.5 (a loopback address, a port up to 65535 that is not the hub's, the desk's page),
// and is never taken from the page's own address. The hash the frame is given is written by the
// shared grammar, so it can hold no value the desk would refuse. A mounted frame is the same frame
// only while its project, its address and its instance are what the hub's row says. A message is
// believed only when it comes from the window of the mounted frame, from the origin of its address, as
// a plain object of exactly the four keys, about the mounted project, with ids of the grammar.
//
// The second half touches the page, and it is the only place that does: a NEW `<iframe>` element each
// time one is needed (never the `src` of an old one), the replacement of a mounted frame's location
// for a move inside the same project (only the fragment changes: no reload, no history entry), and
// the ONE listener for the desk's message. The message is for display: whoever listens gets a
// location, and what it may do is the caller's (here: highlight and write the page's own address).
// The page says nothing to the desk: there is no message from the hub to a desk, and settings and
// navigation go through the hash alone. It opens no door and reads no clock.
import {deskHash, preferenceHash, readDeskHash} from "./desk-hash.js";

/** The frame's sandbox (spec 4.5.5): no navigation of the top page is granted. */
export const SANDBOX = "allow-scripts allow-same-origin allow-forms allow-popups "
  + "allow-popups-to-escape-sandbox";
//: The one shape an address of a desk may have (spec 4.5.5): a loopback address, a port, the desk's page.
const DESK_URL = /^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})\/panel\/desk\.html$/;
//: The four keys of the desk's one message, sorted.
const MESSAGE_KEYS = "kind,project_id,run_id,task_id";

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

//: Whether the shared grammar of the desk's address accepts `value` as the id called `key`.
function fits(key, value) {
  return typeof value === "string" && readDeskHash(`#${new URLSearchParams({[key]: value})}`)[key]
    === value;
}

// -- the pure half -------------------------------------------------------------------------------

/**
 * The address of the desk of a running project, `{url, origin}`, or null. The address is the one the
 * hub gave (`desk_url`), and only while the project runs; it must be of the shape of 4.5.5 with a
 * port up to 65535 that is not the hub's own, and the project's id must be of the grammar.
 */
export function frameAddress(project, hubPort) {
  const found = isObject(project) && project.state === "running" && fits("project",
    project.project_id) ? DESK_URL.exec(typeof project.desk_url === "string" ? project.desk_url
      : "") : null;
  const effectiveHubPort = hubPort === "" ? 80 : Number(hubPort);
  if (found === null || Number(found[1]) > 65535 || Number(found[1]) === effectiveHubPort) return null;
  return Object.freeze({url: project.desk_url, origin: new URL(project.desk_url).origin});
}

/**
 * The hash a frame is given: the project, `embed=hub`, the navigation (`task`, `run`, `gate`,
 * `panel`, `new`) and the language and theme. A value the grammar refuses is not written. `nav` with
 * nothing in it is the minimal hash of a change of language or theme: it names no navigation key, so
 * the desk keeps what a person has chosen inside it.
 */
export function frameHash(projectId, nav, prefs) {
  const at = (key) => nav[key] ?? null;
  return preferenceHash(deskHash({project: projectId, embed: "hub", task: at("task"),
    run: at("run"), gate: at("gate"), panel: at("panel"), new: at("new")}), prefs);
}

/** Whether a mounted frame (`{project_id, desk_url, instance}`) is still the one the row describes. */
export function sameMount(mounted, project) {
  return mounted !== null && isObject(project) && project.state === "running"
    && mounted.project_id === project.project_id && mounted.desk_url === project.desk_url
    && mounted.instance === (project.instance ?? null);
}

/**
 * The location a message from the desk tells, `{task_id, run_id}`, or null when it is not a message
 * the page takes. `event` is `{source, origin, data}`; `mounted` is `{window, origin, project_id}`
 * of the frame on the page, or null. All of these must hold: the message comes from the window of the
 * mounted frame, from the origin of its address, is a plain object with exactly the keys `kind`,
 * `project_id`, `task_id` and `run_id`, names the mounted project, and each id is null or of the grammar.
 */
export function locationOf(event, mounted) {
  if (mounted === null || event.source !== mounted.window || event.origin !== mounted.origin) {
    return null;
  }
  const data = event.data;
  if (!isObject(data) || Object.getPrototypeOf(data) !== Object.prototype
      || Object.keys(data).sort().join(",") !== MESSAGE_KEYS) return null;
  if (data.kind !== "desk-location" || data.project_id !== mounted.project_id) return null;
  const right = (key, value) => value === null || fits(key, value);
  if (!right("task", data.task_id) || !right("run", data.run_id)) return null;
  return Object.freeze({task_id: data.task_id, run_id: data.run_id});
}

// -- the half that touches the page --------------------------------------------------------------

//: A NEW iframe element for the desk at `address`: the sandbox and the title are set before the
//: element meets the document, and `src` is set last, so no navigation starts without them.
function newFrame(project, address, nav, prefs, title) {
  const element = document.createElement("iframe");
  element.className = "hub-frame";
  element.setAttribute("sandbox", SANDBOX);
  element.setAttribute("title", title);
  element.setAttribute("src", `${address.url}${frameHash(project.project_id, nav, prefs)}`);
  return element;
}

/**
 * The host of the page's one frame, drawn into `mount`: `ensure` mounts or keeps it, `navigate`
 * replaces its location, `close` removes it, `current` names the project it holds. `onLocation` is
 * called with `{task_id, run_id}` for each message `locationOf` takes.
 */
export function createFrameHost(mount, onLocation) {
  let mounted = null;
  const held = () => (mounted === null ? null : {window: mounted.element.contentWindow,
    origin: mounted.origin, project_id: mounted.project_id});

  window.addEventListener("message", (event) => {
    const at = locationOf(event, held());
    if (at !== null) onLocation(at);
  });

  function close() {
    if (mounted !== null) mounted.element.remove();
    mounted = null;
  }

  /**
   * Mount the desk of `project` (`"mounted"`: a NEW element), keep the frame that already is its desk
   * (`"kept"`: only its title, said in the reader's language, is written again) or, for a project that
   * has no running desk, remove whatever is mounted and answer `null`.
   */
  function ensure(project, nav, prefs, hubPort, title) {
    const address = frameAddress(project, hubPort);
    if (address === null) {
      close();
      return null;
    }
    if (sameMount(mounted, project)) {
      mounted.element.setAttribute("title", title);
      return "kept";
    }
    close();
    const element = newFrame(project, address, nav, prefs, title);
    mount.append(element);
    mounted = {element, project_id: project.project_id, desk_url: project.desk_url,
      instance: project.instance ?? null, origin: address.origin};
    return "mounted";
  }

  /** Move the mounted desk of `projectId` to `nav`: only the fragment changes. */
  function navigate(projectId, nav, prefs) {
    if (mounted === null || mounted.project_id !== projectId) return false;
    mounted.element.contentWindow.location.replace(
      `${mounted.desk_url}${frameHash(projectId, nav, prefs)}`);
    return true;
  }

  return Object.freeze({ensure, navigate, close,
    current: () => (mounted === null ? null : mounted.project_id)});
}
