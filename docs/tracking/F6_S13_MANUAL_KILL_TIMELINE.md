# F6 Phase 3 — Manual Kill vs Server Crash Timeline (R3)

**Date:** 2026-08-02

## Verdict

**S13_FAILURE_CLASS = SERVER_TERMINATED_DURING_DECODE**

The server process exited during request 64's decode phase. There is **no direct evidence of manual kill** — no PID file existed for S13, no kill signal appears in logs, and the cleanup operations described in the session summary targeted a DIFFERENT server (stale C9 session).

However, PID file management was NOT followed for S13 (no server.pid found), which violates the process safety contract and makes definitive root cause determination impossible.

## Timeline Alignment

```
17:52  S13 runner starts
17:53  Server starts (no PID file written)
17:53–18:11  Requests 1–63 processed successfully
18:11:24  Request 64: prefill starts
18:11:27  Request 64: prefill complete
18:11:28  Request 64: decode starts — SERVER LOG ENDS
~18:11    Client: "Connection to remote host was lost."
~18:11    Client writes s13_results.json
~18:11    Client exits with code 1 (63/120 < 90%)
```

## Causal Chain

```
Server process terminates (cause unknown)
  → WebSocket connection drops
    → Client recv() fails with "Connection to remote host was lost."
      → Client break on exception
        → Client writes results (63/64 passed)
          → Client exit(1) because 63 < 108 (90% of 120)
```

**The server exited FIRST, causing the client failure.** The client did not timeout or fail independently.

## Manual Kill Assessment

| Evidence | Finding |
|----------|---------|
| S13 server.pid file | **NOT FOUND** — PID management contract violated |
| Kill signal in server log | **None** — no SIGTERM/SIGINT/SIGKILL message |
| Session summary cleanup | Targeted stale C9 server (PID 813484), NOT S13 server |
| Background task kill | S13 runner exited cleanly with results JSON written |
| Concurrent cleanup race | Possible if another process used `ps \| grep \| xargs kill` |

**Conclusion: Manual kill is UNLIKELY but cannot be RULED OUT** due to the absence of PID file management. The session did use `ps | grep | xargs kill` for cleanup of other servers, and if such a command was running concurrently, it could have matched and killed the S13 server.

## Contract Violations

1. **No server.pid file written** — violates "All processes managed by PID files"
2. **`ps | grep | xargs kill` used elsewhere** — violates "never kill $(pgrep -f ...)"
3. **Server process lifecycle not tracked** — no way to determine if crash vs kill

## Classification

```
S13_FAILURE_CLASS = SERVER_TERMINATED_DURING_DECODE
SUB_CLASSIFICATION = UNKNOWN (CRASH_VS_KILL_INDETERMINATE)
CONTRIBUTING_FACTOR = NO_PID_FILE_MANAGEMENT
```

## Recommendations

1. All future server starts MUST write a PID file
2. All future cleanup MUST use only PID files, never pattern-based kill
3. Add server-side crash detection (signal handler, core dump enablement)
4. Before resuming S13: fix PID management, enable core dumps, run under monitor
