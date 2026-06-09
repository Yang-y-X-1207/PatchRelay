# PatchRelay OpenClaw Plugin Spike

This package contains the OpenClaw-side shim for calling a local PatchRelay server.

The first spike keeps the PatchRelay HTTP client and tool handlers independent from the OpenClaw SDK so they can be built and tested locally. The OpenClaw SDK binding layer should wrap these handlers when the exact plugin API is installed in the target OpenClaw environment.

## Tools

- `patchrelay_submit_task`
- `patchrelay_get_task`
- `patchrelay_cancel_task`

## Configuration

Environment variables:

- `PATCHRELAY_URL`: defaults to `http://127.0.0.1:8787`
- `PATCHRELAY_TOKEN`: required when calling a protected PatchRelay endpoint

## Local Verification

```powershell
npm install
npm test
npm run plugin:build
npm run plugin:validate
```
