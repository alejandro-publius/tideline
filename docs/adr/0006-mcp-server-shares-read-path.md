# ADR 0006: Expose the data over MCP, reusing the HTTP read path

**Status:** accepted (July 2026)

## Context

The interesting artifact this app produces — the surge residual, per station,
right now and historically — is exactly the kind of live fact an AI assistant
would want to look up mid-conversation. The Model Context Protocol (MCP) is the
emerging standard for giving an assistant callable tools. Adding an MCP server
turns Tideline from "a dashboard a human reads" into "a tool an agent queries."

The risk with a second access surface is drift: the HTTP API and the MCP server
computing surge slightly differently, so the same question gets two answers.

## Decision

Add an MCP server (`app/mcp_server.py`, four tools: `list_stations`,
`surge_overview`, `station_surge`, `surge_history`) that **shares the exact
read-only query functions with the REST API** rather than reimplementing them.
To make that sharing possible, two functions were factored out of the HTTP
layer into `service.py`:

- `overview_from_db(db)` — the read half of the overview (no NOAA refresh),
- `daily_surge(db, station_id, days)` — the daily aggregation the history
  endpoint had inlined.

The HTTP endpoints now call these too, so there is exactly one implementation
of each query behind both surfaces. Every MCP tool is **read-only** and touches
only the database — no NOAA calls — so agent tool-calls are fast and
deterministic; the HTTP layer and background sweep keep the data fresh.

`surge_overview` sorts by absolute surge so the most anomalous stations come
first — an agent asking "where is the water unusual?" gets the answer at the
top, not buried alphabetically.

## Consequences

- One query implementation, two surfaces: the API and the agent tools cannot
  disagree about what the surge is.
- The factoring is a net simplification of the HTTP layer (the history query
  left the router), not just addition.
- MCP is a new dependency (`mcp`) and stdio-only for now. A network transport
  (streamable-HTTP, which is how hosted agent platforms connect) is a config
  change on `mcp.run()`, not a rewrite — deferred until there's a reason.
- Tools are read-only by design. A write tool (e.g. "watch this station and
  alert me") would need auth and a durable subscription store — out of scope,
  and called out here so the boundary is explicit.
