import { z } from "zod";

import {
  cancelTask,
  configFromEnv,
  getTask,
  submitTask,
  type CancelTaskInput,
  type GetTaskInput,
  type PatchRelayConfig,
  type SubmitTaskInput,
} from "./client.js";

export const submitTaskSchema = z.object({
  instruction: z.string().trim().min(1),
  worker: z.enum(["auto", "codex", "claude", "fake"]).default("auto"),
  testProfile: z.string().trim().min(1).default("default"),
});

export const getTaskSchema = z.object({
  taskId: z.string().trim().min(1),
});

export const cancelTaskSchema = getTaskSchema;

export async function patchrelay_submit_task(
  input: SubmitTaskInput,
  config: PatchRelayConfig = configFromEnv(),
): Promise<unknown> {
  const parsed = submitTaskSchema.parse(input);
  return submitTask(parsed, config);
}

export async function patchrelay_get_task(
  input: GetTaskInput,
  config: PatchRelayConfig = configFromEnv(),
): Promise<unknown> {
  const parsed = getTaskSchema.parse(input);
  return getTask(parsed, config);
}

export async function patchrelay_cancel_task(
  input: CancelTaskInput,
  config: PatchRelayConfig = configFromEnv(),
): Promise<unknown> {
  const parsed = cancelTaskSchema.parse(input);
  return cancelTask(parsed, config);
}

export const patchRelayTools = {
  patchrelay_submit_task,
  patchrelay_get_task,
  patchrelay_cancel_task,
};
