"use strict";
// SHA-256, the id of a document the preparation chain publishes (spec 6.4.1, link 5), and the
// stable spelling of a value that a key or a comparison is made of.
//
// A document's id is `doc-` and the first 32 hex digits of the digest of the run, the reference,
// the media type and the content, joined by NUL: the same bytes always give the same id, so a
// request repeated after a lost answer is the same request and the server answers it with the
// record that stands. The wizard's model is pure and answers synchronously, so the digest is a
// fixed, documented function here and not the platform's, which answers with a promise. It
// imports nothing and keeps no state; a test holds it to `hashlib` over the lengths where the
// padding changes shape.
const ROUND = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
const INITIAL = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c,
  0x1f83d9ab, 0x5be0cd19];
const rotate = (value, bits) => (value >>> bits) | (value << (32 - bits));

//: The message as big-endian 32-bit words: its UTF-8 bytes, one 0x80, zeros up to 56 modulo 64,
//: and the length in bits as two words.
function wordsOf(text) {
  const bytes = Array.from(new TextEncoder().encode(text));
  const bits = bytes.length * 8;
  bytes.push(0x80);
  while (bytes.length % 64 !== 56) bytes.push(0);
  for (const part of [Math.floor(bits / 4294967296), bits >>> 0]) {
    for (let shift = 24; shift >= 0; shift -= 8) bytes.push((part >>> shift) & 0xff);
  }
  const words = [];
  for (let at = 0; at < bytes.length; at += 4) {
    words.push((bytes[at] << 24) | (bytes[at + 1] << 16) | (bytes[at + 2] << 8) | bytes[at + 3]);
  }
  return words;
}

//: The 64 words one 16-word block expands to.
function expand(block) {
  const schedule = block.slice();
  for (let at = 16; at < 64; at += 1) {
    const early = schedule[at - 15], late = schedule[at - 2];
    const small = rotate(early, 7) ^ rotate(early, 18) ^ (early >>> 3);
    const large = rotate(late, 17) ^ rotate(late, 19) ^ (late >>> 10);
    schedule.push((schedule[at - 16] + small + schedule[at - 7] + large) | 0);
  }
  return schedule;
}

//: One block folded into the running state.
function compress(state, block) {
  const schedule = expand(block);
  let [a, b, c, d, e, f, g, h] = state;
  for (let at = 0; at < 64; at += 1) {
    const choose = (e & f) ^ (~e & g);
    const first = (h + (rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25)) + choose + ROUND[at]
      + schedule[at]) | 0;
    const second = ((rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22))
      + ((a & b) ^ (a & c) ^ (b & c))) | 0;
    h = g; g = f; f = e; e = (d + first) | 0; d = c; c = b; b = a; a = (first + second) | 0;
  }
  return [a, b, c, d, e, f, g, h].map((value, at) => (state[at] + value) | 0);
}

//: The SHA-256 of the UTF-8 bytes of a text, as 64 lowercase hex digits.
export function sha256Hex(text) {
  const words = wordsOf(text);
  let state = INITIAL;
  for (let at = 0; at < words.length; at += 16) state = compress(state, words.slice(at, at + 16));
  return state.map((value) => (value >>> 0).toString(16).padStart(8, "0")).join("");
}

//: A value spelled the same whatever the order its keys were made in: what two things are compared
//: by when they must be equal as data, and what a key that holds a body is made of.
export function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const facts = Object.keys(value).sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`);
    return `{${facts.join(",")}}`;
  }
  return JSON.stringify(value);
}

//: The id of a document the chain publishes, derived from the bytes it carries.
export function documentId(runId, ref, mediaType, content) {
  return `doc-${sha256Hex([runId, ref, mediaType, content].join("\0")).slice(0, 32)}`;
}
