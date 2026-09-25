"use strict";
// Preferences never enter a frozen run, a draft, a request or a read epoch.
import {element} from "./command-view.js";
import {message} from "./studio-i18n.js";

export function readPreferences(hash, language) {
  const fields = new URLSearchParams(hash.replace(/^#/, ""));
  const one = (key, allowed) => fields.getAll(key).length === 1
    && allowed.includes(fields.get(key)) ? fields.get(key) : null;
  return Object.freeze({locale: one("lang", ["en", "ru"])
    || (/^ru(?:-|$)/i.test(language || "") ? "ru" : "en"),
  theme: one("theme", ["dark", "light"])});
}

export function preferenceHash(hash, value) {
  const fields = new URLSearchParams(hash.replace(/^#/, ""));
  fields.set("lang", value.locale);
  if (value.theme === null) fields.delete("theme");
  else fields.set("theme", value.theme);
  return `#${fields}`;
}

function select(name, values, label, change) {
  const control = element("select", {"data-focus": `preference-${name}`, name});
  for (const [value, text] of values) control.append(element("option", {value, text}));
  control.addEventListener("change", () => change(control.value));
  const title = element("span", {text: label});
  return {control, title, node: element("label", {className: "studio-preference"}, [title, control])};
}

class Preferences {
  constructor(door) {
    this.door = door;
    this.value = readPreferences(door.hash, door.language);
    this.language = select("language", [["ru", "Русский"], ["en", "English"]], "", (locale) => this.choose({locale}));
    this.theme = select("theme", [["light", ""], ["dark", ""]], "", (theme) => this.choose({theme}));
    door.mount.replaceChildren(this.theme.node, this.language.node);
    this.changed = () => this.paint();
    door.media.addEventListener("change", this.changed);
    this.paint();
  }

  choose(patch) {
    if (Object.hasOwn(patch, "locale") && !["en", "ru"].includes(patch.locale)) return;
    if (Object.hasOwn(patch, "theme") && !["dark", "light"].includes(patch.theme)) return;
    this.value = Object.freeze({...this.value, ...patch});
    this.paint();
    this.door.change();
  }

  paint() {
    const {locale, theme} = this.value, {root, mount, media} = this.door;
    root.lang = locale;
    if (theme === null) root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    mount.setAttribute("aria-label", message(locale, "settings.label"));
    this.language.title.textContent = message(locale, "settings.language");
    this.language.control.value = locale;
    this.theme.title.textContent = message(locale, "settings.theme");
    this.theme.control.value = theme || (media.matches ? "dark" : "light");
    for (const option of this.theme.control.options) {
      option.textContent = message(locale, `settings.${option.value}`);
    }
  }

  dispose() { this.door.media.removeEventListener("change", this.changed); }
}

export function preferences(door) { return new Preferences(door); }
