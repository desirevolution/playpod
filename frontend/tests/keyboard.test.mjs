import { test } from "node:test";
import assert from "node:assert/strict";
import { shortcut } from "../src/keyboard.ts";

const event = (key, code = key, extra = {}) => ({ key, code, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, repeat: false, isComposing: false, defaultPrevented: false, ...extra });
test("P opens the player from other views and focused navigation", () => {
  assert.equal(shortcut(event("p", "KeyP"), false, true, false), "player");
  assert.equal(shortcut(event("P", "KeyP"), false, false, false), "player");
});
test("volume arrows support holding; playback keys ignore repeats", () => {
  assert.equal(shortcut(event("ArrowUp", "ArrowUp", {repeat: true}), false, false, false), "volume-up");
  assert.equal(shortcut(event("ArrowDown"), false, false, false), "volume-down");
  assert.equal(shortcut(event(" ", "Space", {repeat: true}), false, false, false), null);
  for (const [key, code, action] of [[" ", "Space", "toggle"], ["ArrowLeft", "ArrowLeft", "rewind"], ["ArrowRight", "ArrowRight", "forward"], ["n", "KeyN", "next"]])
    assert.equal(shortcut(event(key, code), false, false, false), action);
});
test("typing, dialogs, native controls and browser shortcuts keep their keys", () => {
  assert.equal(shortcut(event("p"), true, false, false), null);
  assert.equal(shortcut(event("p"), false, false, true), null);
  assert.equal(shortcut(event("ArrowUp"), false, true, false), null);
  assert.equal(shortcut(event(" ", "Space"), false, true, false), null);
  for (const flag of ["ctrlKey", "metaKey", "altKey", "shiftKey", "isComposing", "defaultPrevented"])
    assert.equal(shortcut(event("p", "KeyP", {[flag]: true}), false, false, false), null);
});
