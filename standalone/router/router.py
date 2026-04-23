import argparse
import json
import socket
import socketserver
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REQUEST_DELIMITER = b"\n"
MAX_REQUEST_BYTES = 64 * 1024


def load_config(config_path: str) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as handle:
        config = json.load(handle)

    required_top = ["listen_host", "listen_port", "probe_timeout_ms", "probe_attempts", "regions"]
    missing_top = [field for field in required_top if field not in config]
    if missing_top:
        raise ValueError(f"Missing required config fields: {missing_top}")

    if not isinstance(config["regions"], list) or not config["regions"]:
        raise ValueError("Config field 'regions' must be a non-empty list")

    for region in config["regions"]:
        required_region = ["name", "probe_host", "probe_port", "backend_url"]
        missing_region = [field for field in required_region if field not in region]
        if missing_region:
            raise ValueError(f"Region entry missing fields {missing_region}: {region}")

    config["listen_port"] = int(config["listen_port"])
    config["probe_timeout_ms"] = int(config["probe_timeout_ms"])
    config["probe_attempts"] = int(config["probe_attempts"])
    config["backend_timeout_ms"] = int(config.get("backend_timeout_ms", 2000))
    for region in config["regions"]:
        region["probe_port"] = int(region["probe_port"])
    return config


def measure_tcp_connect_ms(host: str, port: int, timeout_seconds: float) -> Optional[float]:
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            pass
    except OSError:
        return None
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return round(elapsed_ms, 2)


def measure_region_latency_ms(region: Dict[str, Any], probe_timeout_ms: int, probe_attempts: int) -> Optional[float]:
    timeout_seconds = probe_timeout_ms / 1000.0
    samples: List[float] = []
    for _ in range(probe_attempts):
        sample = measure_tcp_connect_ms(region["probe_host"], region["probe_port"], timeout_seconds)
        if sample is not None:
            samples.append(sample)

    if not samples:
        return None

    average = sum(samples) / len(samples)
    return round(average, 2)


def choose_best_region(config: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Optional[float]]]:
    latencies: Dict[str, Optional[float]] = {}
    best_region: Optional[Dict[str, Any]] = None
    best_latency = float("inf")

    for region in config["regions"]:
        latency = measure_region_latency_ms(
            region=region,
            probe_timeout_ms=config["probe_timeout_ms"],
            probe_attempts=config["probe_attempts"],
        )
        latencies[region["name"]] = latency
        if latency is not None and latency < best_latency:
            best_latency = latency
            best_region = region

    return best_region, latencies


def forward_to_backend(backend_url: str, payload: Dict[str, Any], backend_timeout_ms: int) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        backend_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout_seconds = backend_timeout_ms / 1000.0
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        response_body = response.read()
    return json.loads(response_body.decode("utf-8"))


class RegionRouterTCPHandler(socketserver.BaseRequestHandler):
    server: "RegionRouterServer"

    def handle(self) -> None:
        self.request.settimeout(10)
        raw = self._read_json_line()
        if raw is None:
            return

        try:
            request_payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"ok": False, "error": "invalid_json"})
            return

        client_id = request_payload.get("clientId")
        payload = request_payload.get("payload")
        if client_id is None or payload is None:
            self._send_json({"ok": False, "error": "clientId_and_payload_are_required"})
            return

        best_region, latencies = choose_best_region(self.server.config)
        if best_region is None:
            self._send_json({"ok": False, "error": "no_reachable_region", "latenciesMs": latencies})
            return

        backend_payload = {"clientId": client_id, "payload": payload}
        try:
            backend_response = forward_to_backend(
                backend_url=best_region["backend_url"],
                payload=backend_payload,
                backend_timeout_ms=self.server.config["backend_timeout_ms"],
            )
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            self._send_json(
                {
                    "ok": False,
                    "error": f"backend_forward_failed: {exc}",
                    "selectedRegion": best_region["name"],
                    "latenciesMs": latencies,
                }
            )
            return

        self._send_json(
            {
                "ok": True,
                "selectedRegion": best_region["name"],
                "latenciesMs": latencies,
                "backendResponse": backend_response,
            }
        )

    def _read_json_line(self) -> Optional[bytes]:
        chunks: List[bytes] = []
        total = 0
        while True:
            data = self.request.recv(4096)
            if not data:
                break
            chunks.append(data)
            total += len(data)
            if total > MAX_REQUEST_BYTES:
                self._send_json({"ok": False, "error": "request_too_large"})
                return None
            if REQUEST_DELIMITER in data:
                break

        if not chunks:
            return None
        return b"".join(chunks).split(REQUEST_DELIMITER, 1)[0]

    def _send_json(self, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8") + REQUEST_DELIMITER
        self.request.sendall(encoded)


class RegionRouterServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address: Tuple[str, int], config: Dict[str, Any]):
        super().__init__(server_address, RegionRouterTCPHandler)
        self.config = config


def main() -> None:
    parser = argparse.ArgumentParser(description="Latency-based multi-region TCP forwarding router")
    parser.add_argument(
        "--config",
        type=str,
        default=str(Path(__file__).with_name("regions.example.json")),
        help="Path to region/router config JSON",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    listen_host = str(config["listen_host"])
    listen_port = int(config["listen_port"])

    server = RegionRouterServer((listen_host, listen_port), config)
    print(f"Router listening on {listen_host}:{listen_port} with {len(config['regions'])} regions")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
