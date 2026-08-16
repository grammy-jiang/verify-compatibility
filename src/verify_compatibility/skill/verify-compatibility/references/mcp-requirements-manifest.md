# MCP Requirements Manifest

The static MCP auditor reads `compatibility/requirements.json` unless another
path is supplied with `--manifest`.

```json
{
  "schema_version": 1,
  "artifact": "mcp-server",
  "name": "example-server",
  "capabilities": {
    "features": ["tools"],
    "transports": ["stdio", "streamable-http"],
    "authentication": ["none", "oauth"]
  }
}
```

Every feature is required for intended behavior. Transport entries are
alternatives offered by the server; a target needs at least one supported
option. Authentication entries use the same alternative semantics.

The declaration is not a substitute for an MCP initialization handshake. It
must not be reported as runtime evidence.
