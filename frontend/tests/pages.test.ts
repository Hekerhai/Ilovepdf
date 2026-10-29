import assert from "node:assert/strict";
import { test } from "node:test";

import { parsePageList, parseRangeGroups } from "../src/lib/pages.ts";

test("parses ranges like the server", () => {
  assert.deepEqual(parsePageList("1-3,5", 6), [0, 1, 2, 4]);
  assert.deepEqual(parsePageList("4-", 5), [3, 4]);
  assert.deepEqual(parsePageList("odd", 5), [0, 2, 4]);
  assert.deepEqual(parsePageList("3-1", 3), [2, 1, 0]);
  assert.deepEqual(parsePageList("last", 7), [6]);
  assert.deepEqual(parsePageList("", 2), [0, 1]);
});

test("rejects out-of-range pages", () => {
  assert.throws(() => parsePageList("9", 3), /out of range/);
  assert.throws(() => parsePageList("x", 3), /not a page number/);
});

test("groups ranges", () => {
  assert.deepEqual(parseRangeGroups("1-2, 3", 3), [[0, 1], [2]]);
});
