import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";

import {
  patchrelay_cancel_task,
  patchrelay_get_task,
  patchrelay_submit_task,
} from "./tools.js";
import type { PatchRelayConfig } from "./client.js";

export {
  patchRelayTools,
  patchrelay_cancel_task,
  patchrelay_get_task,
  patchrelay_submit_task,
} from "./tools.js";

export { cancelTask, configFromEnv, getTask, submitTask } from "./client.js";

const configSchema = Type.Object(
  {
    baseUrl: Type.Optional(
      Type.String({
        default: "http://127.0.0.1:8787",
        description: "PatchRelay server base URL.",
      }),
    ),
    token: Type.Optional(
      Type.String({
        description: "Bearer token for the PatchRelay server.",
      }),
    ),
  },
  { additionalProperties: false },
);

function patchRelayConfig(config: { baseUrl?: string; token?: string }): PatchRelayConfig {
  return {
    baseUrl: config.baseUrl ?? process.env.PATCHRELAY_URL ?? "http://127.0.0.1:8787",
    token: config.token ?? process.env.PATCHRELAY_TOKEN,
  };
}

export default defineToolPlugin({
  id: "patchrelay",
  name: "PatchRelay",
  description: "Relay coding tasks from OpenClaw to a local PatchRelay server.",
  configSchema,
  tools: (tool) => [
    tool({
      name: "patchrelay_submit_task",
      description: "Submit a coding task to PatchRelay.",
      parameters: Type.Object({
        instruction: Type.String({
          description: "Coding instruction to pass to the configured worker.",
          minLength: 1,
        }),
        worker: Type.Optional(
          Type.Union(
            [
              Type.Literal("auto"),
              Type.Literal("codex"),
              Type.Literal("claude"),
              Type.Literal("fake"),
            ],
            {
              default: "auto",
              description: "Worker to use for this task.",
            },
          ),
        ),
        testProfile: Type.Optional(
          Type.String({
            default: "default",
            description: "PatchRelay test profile to run after the worker finishes.",
            minLength: 1,
          }),
        ),
      }),
      execute: async (params, config) => patchrelay_submit_task(params, patchRelayConfig(config)),
    }),
    tool({
      name: "patchrelay_get_task",
      description: "Fetch PatchRelay task status, logs, events, diff, and test artifacts.",
      parameters: Type.Object({
        taskId: Type.String({
          description: "PatchRelay task id.",
          minLength: 1,
        }),
      }),
      execute: async (params, config) => patchrelay_get_task(params, patchRelayConfig(config)),
    }),
    tool({
      name: "patchrelay_cancel_task",
      description: "Cancel a queued or running PatchRelay task.",
      parameters: Type.Object({
        taskId: Type.String({
          description: "PatchRelay task id.",
          minLength: 1,
        }),
      }),
      execute: async (params, config) => patchrelay_cancel_task(params, patchRelayConfig(config)),
    }),
  ],
});
