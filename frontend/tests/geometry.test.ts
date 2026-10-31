import assert from "node:assert/strict";
import { test } from "node:test";

import { isWinAnsi, userRect } from "../src/lib/engines/geometry.ts";

// Expected values come from the server's user_rect (backend/app/tools/overlay.py) for the same page and box.
const crop = { x: 10, y: 20, width: 575, height: 802 };
const box = { x: 0.1, y: 0.2, width: 0.3, height: 0.1 };
const expected: Record<number, number[]> = {
  0: [67.5, 581.4, 240.0, 661.6],
  90: [125.0, 100.2, 182.5, 340.8],
  180: [355.0, 180.4, 527.5, 260.6],
  270: [412.5, 501.2, 470.0, 741.8],
};

for (const [rotation, want] of Object.entries(expected)) {
  test(`userRect matches the server on pages rotated ${rotation}°`, () => {
    const r = userRect(Number(rotation), crop, box);
    const got = [r.x, r.y, r.x + r.width, r.y + r.height].map((v) => Math.round(v * 10) / 10);
    assert.deepEqual(got, want);
  });
}

test("isWinAnsi spots text the standard fonts can't draw", () => {
  assert.equal(isWinAnsi("Hello, Zoë – “quoted” €5"), true);
  assert.equal(isWinAnsi("Ωμέγα"), false);
  assert.equal(isWinAnsi("✓"), false);
});

test("fractionBox undoes userRect at every rotation", async () => {
  const { fractionBox } = await import("../src/lib/engines/geometry.ts");
  for (const rotation of [0, 90, 180, 270]) {
    const back = fractionBox(rotation, crop, userRect(rotation, crop, box));
    for (const k of ["x", "y", "width", "height"] as const) assert.ok(Math.abs(back[k] - box[k]) < 1e-9, `${rotation} ${k}`);
  }
});
