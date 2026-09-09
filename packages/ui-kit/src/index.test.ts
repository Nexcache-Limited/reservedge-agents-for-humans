import assert from "node:assert/strict";
import test from "node:test";

import { PACKAGE_NAME, PACKAGE_STATUS } from "./index.js";

test("ui-kit public package identity is stable", () => {
  assert.equal(PACKAGE_NAME, "@itaa/ui-kit");
  assert.equal(PACKAGE_STATUS, "design-system");
  assert.notEqual(PACKAGE_STATUS, "placeholder");
});
