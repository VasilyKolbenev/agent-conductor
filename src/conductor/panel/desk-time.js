"use strict";
// The time of an instant, said two ways (spec 5.6.7): `short`, the words a person reads
// ("28.09 16:50", in the browser's own zone), and `exact`, the string the server wrote, kept
// untouched for a hint and for the passport. The desk and the hub both show a waiting time in
// a row and its exact value in a `title`, and both take them from here.
//
// The module reads no clock: no `Date.now`, no `new Date()` without an argument, no timer, no
// `performance`. It parses only the string it is handed, so the same instant answers the same
// however late it is asked. `Intl` is used as the date formatter alone; the platform's own
// language and zone are never asked for by name -- the caller says the language, and the zone is
// the one the formatter runs in.
//
// This module is shared with the hub's page, which loads it without the Studio: it imports
// nothing. It says its own one phrase in the two languages of the panel ("time not given") so
// a value that is not an instant is never drawn as an empty text.

//: The one phrase this module says itself. The panel knows two languages: anything but Russian
//: is read as English, as the desk's own boot module does.
const NOT_GIVEN = Object.freeze({en: "time not given", ru: "время не указано"});
//: An instant as the server writes it: date, time, an optional fraction, and `Z` or an offset.
const INSTANT = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/;
//: The parts a short time is made of. The clock is on 24 hours in both languages, so a
//: reader of either says the same "16:50" and the parts never carry a day period.
const SHORT_PARTS = Object.freeze({day: "2-digit", month: "2-digit", hour: "2-digit",
  minute: "2-digit", hourCycle: "h23"});

//: The instant a string names, or null. The calendar is asked and not the parser alone: the
//: parser would carry the 31st of September over to the 1st of October and call it a time.
function parsed(iso) {
  const found = typeof iso === "string" ? INSTANT.exec(iso) : null;
  if (found === null) return null;
  const [year, month, day, hour, minute, second] = found.slice(1, 7).map(Number);
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const fits = month >= 1 && month <= 12 && day >= 1 && day <= daysInMonth
    && hour < 24 && minute < 60 && second < 60;
  const at = fits ? new Date(iso) : null;
  return at !== null && !Number.isNaN(at.getTime()) ? at : null;
}

//: Day and month in the locale's own order, then the clock: the formatter's own separator
//: between the two is dropped for one space, so the answer is one short run of text.
function said(tag, at) {
  const parts = new Intl.DateTimeFormat(tag, SHORT_PARTS).formatToParts(at);
  const clock = parts.findIndex((part) => part.type === "hour");
  const text = (list) => list.map((part) => part.value).join("");
  return `${text(parts.slice(0, clock)).replace(/[\s,]+$/, "")} ${text(parts.slice(clock))}`.trim();
}

//: `{short, exact, known}`. A value that is not an instant answers the phrase, the string it
//: was given (or nothing, when it was not a string) and `known: false`, so a caller can choose
//: a sentence that does not say "at" before a time nobody gave.
export function instantText(locale, iso) {
  const tag = Object.hasOwn(NOT_GIVEN, locale) ? locale : "en";
  const at = parsed(iso);
  if (at === null) {
    return Object.freeze({short: NOT_GIVEN[tag], exact: typeof iso === "string" ? iso : "",
      known: false});
  }
  return Object.freeze({short: said(tag, at), exact: iso, known: true});
}
