import assert from "node:assert/strict";
import { test } from "node:test";

import { getToolPluginMetadata } from "openclaw/plugin-sdk/tool-plugin";

import entry from "./index.js";

test("declares OpenClaw tool metadata", () => {
  const metadata = getToolPluginMetadata(entry);

  assert.deepEqual(
    metadata?.tools.map((tool) => tool.name),
    ["patchrelay_submit_task", "patchrelay_get_task", "patchrelay_cancel_task"],
  );
});
