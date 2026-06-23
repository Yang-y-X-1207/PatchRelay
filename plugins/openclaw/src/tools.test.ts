import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import http from "node:http";
import type { AddressInfo } from "node:net";

import {
  patchrelay_cancel_task,
  patchrelay_get_task,
  patchrelay_submit_task,
} from "./tools.js";

let server: http.Server;
let baseUrl: string;
const requests: { method?: string; url?: string; body: string; authorization?: string }[] = [];

before(async () => {
  server = http.createServer((request, response) => {
    let body = "";
    request.on("data", (chunk) => {
      body += chunk;
    });
    request.on("end", () => {
      requests.push({
        method: request.method,
        url: request.url,
        body,
        authorization: request.headers.authorization,
      });
      response.setHeader("Content-Type", "application/json");
      if (request.url === "/message:send") {
        response.end(JSON.stringify({ taskId: "task-1", status: "queued" }));
        return;
      }
      if (request.url === "/tasks/task-1") {
        response.end(
          JSON.stringify({
            taskId: "task-1",
            status: "completed",
            phase: "completed",
            worker: "fake",
            latestEvent: { message: "Task execution completed." },
            eventCount: 9,
            artifacts: {
              "patchrelay.summary": {
                content: {
                  changedFiles: ["fake-change.txt"],
                  testStatus: "passed",
                },
              },
            },
          }),
        );
        return;
      }
      if (request.url === "/tasks/task-1:cancel") {
        response.end(JSON.stringify({ taskId: "task-1", status: "canceled" }));
        return;
      }
      response.statusCode = 404;
      response.end(JSON.stringify({ error: "not found" }));
    });
  });

  await new Promise<void>((resolve) => {
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  assert.equal(typeof address, "object");
  assert(address);
  baseUrl = `http://127.0.0.1:${(address as AddressInfo).port}`;
});

after(async () => {
  await new Promise<void>((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  });
});

test("patchrelay_submit_task posts A2A-like message", async () => {
  const response = await patchrelay_submit_task(
    { instruction: "fix bug", worker: "fake" },
    { baseUrl, token: "test-token" },
  );

  assert.deepEqual(response, { taskId: "task-1", status: "queued" });
  const request = requests.at(-1);
  assert.equal(request?.method, "POST");
  assert.equal(request?.url, "/message:send");
  assert.equal(request?.authorization, "Bearer test-token");
  assert.equal(JSON.parse(request?.body ?? "{}").message.parts[0].text, "fix bug");
});

test("patchrelay_get_task fetches task", async () => {
  const response = await patchrelay_get_task({ taskId: "task-1" }, { baseUrl });

  assert.equal(typeof response, "object");
  assert(response);
  const payload = response as Record<string, unknown>;
  assert.equal(payload.taskId, "task-1");
  assert.equal(payload.status, "completed");
});

test("patchrelay_get_task adds display summary", async () => {
  const response = await patchrelay_get_task({ taskId: "task-1" }, { baseUrl });

  assert.equal(typeof response, "object");
  assert(response);
  const payload = response as Record<string, unknown>;
  assert.equal(typeof payload.patchrelayDisplay, "string");
  assert.match(payload.patchrelayDisplay as string, /PatchRelay task task-1/);
  assert.match(payload.patchrelayDisplay as string, /test: passed/);
  assert.match(payload.patchrelayDisplay as string, /events: 9/);
  assert.match(payload.patchrelayDisplay as string, /latest: Task execution completed/);
});

test("patchrelay_cancel_task cancels task", async () => {
  const response = await patchrelay_cancel_task({ taskId: "task-1" }, { baseUrl });

  assert.deepEqual(response, { taskId: "task-1", status: "canceled" });
});

test("submit validation rejects empty instruction", async () => {
  await assert.rejects(() => patchrelay_submit_task({ instruction: "" }, { baseUrl }));
});
