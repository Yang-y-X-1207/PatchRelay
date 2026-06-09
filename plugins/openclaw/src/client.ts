export type PatchRelayConfig = {
  baseUrl: string;
  token?: string;
};

export type SubmitTaskInput = {
  instruction: string;
  worker?: "auto" | "codex" | "claude" | "fake";
  testProfile?: string;
};

export type GetTaskInput = {
  taskId: string;
};

export type CancelTaskInput = {
  taskId: string;
};

export function configFromEnv(env: NodeJS.ProcessEnv = process.env): PatchRelayConfig {
  return {
    baseUrl: env.PATCHRELAY_URL ?? "http://127.0.0.1:8787",
    token: env.PATCHRELAY_TOKEN,
  };
}

export async function submitTask(input: SubmitTaskInput, config: PatchRelayConfig): Promise<unknown> {
  return patchRelayFetch(config, "/message:send", {
    method: "POST",
    body: JSON.stringify({
      message: {
        role: "ROLE_USER",
        parts: [{ text: input.instruction }],
      },
      metadata: {
        patchrelay: {
          worker: input.worker ?? "auto",
          testProfile: input.testProfile ?? "default",
        },
      },
    }),
  });
}

export async function getTask(input: GetTaskInput, config: PatchRelayConfig): Promise<unknown> {
  return patchRelayFetch(config, `/tasks/${encodeURIComponent(input.taskId)}`, {
    method: "GET",
  });
}

export async function cancelTask(input: CancelTaskInput, config: PatchRelayConfig): Promise<unknown> {
  return patchRelayFetch(config, `/tasks/${encodeURIComponent(input.taskId)}:cancel`, {
    method: "POST",
  });
}

async function patchRelayFetch(
  config: PatchRelayConfig,
  path: string,
  init: RequestInit,
): Promise<unknown> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (config.token) {
    headers.set("Authorization", `Bearer ${config.token}`);
  }

  const response = await fetch(new URL(path, config.baseUrl), {
    ...init,
    headers,
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(`PatchRelay request failed (${response.status}): ${text}`);
  }
  return payload;
}
