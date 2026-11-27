"use strict";

// A failed static import prevents the editor from executing at all. Only a fresh document
// gets a fresh module map. Keep its one retry on this history entry, including any desk handoff.
(() => {
  function showFailure() {
    const notice = document.getElementById("studioBootFailure");
    const button = document.getElementById("studioBootRetry");
    const langs = new URLSearchParams(location.hash.slice(1)).getAll("lang");
    const lang = langs.length === 1 && ["en", "ru"].includes(langs[0]) ? langs[0]
      : /^ru(?:-|$)/i.test(navigator.language) ? "ru" : "en";
    notice.lang = lang;
    if (lang === "ru") {
      document.getElementById("studioBootMessage").textContent = "Не удалось загрузить редактор.";
      button.textContent = "Загрузить ещё раз";
    }
    button.addEventListener("click", () => location.reload());
    notice.hidden = false;
  }

  function onEntry(event) {
    if (!event.isTrusted || event.target !== document.getElementById("studioEntry")) return;
    window.removeEventListener("load", onEntry, true);
    window.removeEventListener("error", onEntry, true);
    if (event.type === "load") return;

    if (history.state?.studioBootRetried !== true) {
      try {
        history.replaceState({...history.state, studioBootRetried: true}, "");
        location.reload();
        return;
      } catch {
        // If the browser cannot record the retry, leave the choice to the person.
      }
    }
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", showFailure, {once: true});
    } else {
      showFailure();
    }
  }

  window.addEventListener("load", onEntry, true);
  window.addEventListener("error", onEntry, true);
})();
