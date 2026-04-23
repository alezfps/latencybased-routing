# Standalone Multi-Region Forwarding Prototype

This directory is a self-contained development sandbox for multi-region routing:

- `client-cpp/`: C++ TCP client
- `router/`: Python TCP router + latency selector
- `backend/`: Fastify backend service (run one per region)

## Region selection strategy

Selection is **latency-based**:

1. Router measures TCP connect latency to each region's probe target.
2. It executes `probe_attempts` samples per region.
3. It computes average latency per region.
4. It selects the region with the lowest average latency.
5. If all regions fail probes, it returns `no_reachable_region`.

TCP-connect probing is used instead of ICMP ping so it works in normal VPS/firewall setups without privileged raw sockets.

## Protocol

### Client -> Router (TCP line-delimited JSON)

```json
{"clientId":"client-001","payload":"hello from cpp"}
```

### Router -> Client (TCP line-delimited JSON)

```json
{
  "ok": true,
  "selectedRegion": "amsterdam",
  "latenciesMs": {
    "amsterdam": 5.31,
    "milan": 23.8
  },
  "backendResponse": {
    "ok": true,
    "region": "amsterdam",
    "clientId": "client-001",
    "echo": "hello from cpp",
    "handledAt": "2026-04-23T00:00:00.000Z"
  }
}
```

## Local standalone run

### 1) Start Fastify backends (simulate Amsterdam + Milan)

```bash
cd standalone/backend
npm install
REGION_NAME=amsterdam PORT=3001 node server.js
```

Second terminal:

```bash
cd standalone/backend
REGION_NAME=milan PORT=3002 node server.js
```

### 2) Start router

Use the provided local example config (`standalone/router/regions.example.json`) and run:

```bash
python3 standalone/router/router.py --config standalone/router/regions.example.json
```

### 3) Build and run C++ client

```bash
cd standalone/client-cpp
make
./latency_client 127.0.0.1 7000 client-001 "hello from cpp"
```

## VPS deployment with your Amsterdam + Milan servers

### Backends

Deploy `standalone/backend` to both VPS nodes and run:

- Amsterdam VPS:
  ```bash
  npm install
  REGION_NAME=amsterdam PORT=3001 node server.js
  ```
- Milan VPS:
  ```bash
  npm install
  REGION_NAME=milan PORT=3001 node server.js
  ```

### Router config

On router host, copy `standalone/router/regions.example.json` to `regions.prod.json` and replace hosts:

```json
{
  "listen_host": "0.0.0.0",
  "listen_port": 7000,
  "probe_timeout_ms": 1000,
  "probe_attempts": 3,
  "backend_timeout_ms": 2000,
  "regions": [
    {
      "name": "amsterdam",
      "probe_host": "<AMS_PUBLIC_IP>",
      "probe_port": 3001,
      "backend_url": "http://<AMS_PUBLIC_IP>:3001/handle"
    },
    {
      "name": "milan",
      "probe_host": "<MIL_PUBLIC_IP>",
      "probe_port": 3001,
      "backend_url": "http://<MIL_PUBLIC_IP>:3001/handle"
    }
  ]
}
```

Then start router:

```bash
python3 standalone/router/router.py --config /path/to/regions.prod.json
```
