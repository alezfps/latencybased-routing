# latencybased-routing

Standalone multi-region forwarding prototype lives in `standalone/`.

It includes:

- `standalone/router/` - Python TCP router with latency-based region selection.
- `standalone/backend/` - Fastify backend service (run once per region).
- `standalone/client-cpp/` - C++ TCP client for standalone testing.

See `standalone/README.md` for setup, local simulation, and VPS deployment notes.
