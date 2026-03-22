from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from tools.db_mcp_contracts import (  # noqa: E402
    SERVER_NAME,
    SERVER_PROTOCOL_VERSION,
    SERVER_VERSION,
    TOOL_DEFINITIONS,
)
from tools.db_mcp_service import CivicquantDbMcpService, ServiceError  # noqa: E402


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def _log(message: str) -> None:
    print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


def _read_message() -> dict[str, Any] | None:
    """
    MCP stdio uses one JSON-RPC message per line.
    """
    line = sys.stdin.buffer.readline()
    if line == b"":
        return None

    raw = line.decode("utf-8", errors="replace").strip()
    if not raw:
        return None

    try:
        message = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JsonRpcError(code=-32700, message="Invalid JSON payload.") from exc

    if not isinstance(message, dict):
        raise JsonRpcError(code=-32600, message="JSON-RPC payload must be an object.")

    return message


def _write_message(payload: dict[str, Any]) -> None:
    """
    Write one JSON-RPC response per line.
    """
    body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    sys.stdout.write(body + "\n")
    sys.stdout.flush()


def _jsonrpc_result(*, id_value: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_value, "result": result}


def _jsonrpc_error(*, id_value: Any, error: JsonRpcError) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": error.code, "message": error.message}
    if error.data is not None:
        payload["data"] = error.data
    return {"jsonrpc": "2.0", "id": id_value, "error": payload}


def _handle_request(
    message: dict[str, Any],
    service: CivicquantDbMcpService,
) -> dict[str, Any] | None:
    if message.get("jsonrpc") != "2.0":
        raise JsonRpcError(code=-32600, message="Unsupported JSON-RPC version.")

    method = message.get("method")
    if not isinstance(method, str):
        raise JsonRpcError(code=-32600, message="Missing method.")

    request_id = message.get("id")
    params = message.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise JsonRpcError(code=-32602, message="Params must be an object.")

    if method == "notifications/initialized":
        _log("Received notifications/initialized")
        return None

    if method == "initialize":
        _log("Received initialize")
        requested_protocol = params.get("protocolVersion")
        negotiated_protocol = SERVER_PROTOCOL_VERSION
        if isinstance(requested_protocol, str) and requested_protocol == SERVER_PROTOCOL_VERSION:
            negotiated_protocol = requested_protocol

        result = {
            "protocolVersion": negotiated_protocol,
            "capabilities": {
                "tools": {
                    "listChanged": False,
                }
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
        }
        return _jsonrpc_result(id_value=request_id, result=result)

    if method == "tools/list":
        _log("Received tools/list")
        return _jsonrpc_result(id_value=request_id, result={"tools": TOOL_DEFINITIONS})

    if method == "tools/call":
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise JsonRpcError(code=-32602, message="tools/call requires a valid tool name.")

        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise JsonRpcError(code=-32602, message="tools/call arguments must be an object.")

        normalized_tool_name = tool_name.strip()
        _log(f"Received tools/call for {normalized_tool_name}")

        try:
            payload = service.call_tool(normalized_tool_name, arguments)
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(payload, ensure_ascii=True),
                    }
                ],
                "structuredContent": payload,
            }
            return _jsonrpc_result(id_value=request_id, result=result)
        except ServiceError as exc:
            payload = {"ok": False, "error": exc.to_dict()}
            result = {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(payload, ensure_ascii=True),
                    }
                ],
                "structuredContent": payload,
            }
            return _jsonrpc_result(id_value=request_id, result=result)

    raise JsonRpcError(code=-32601, message=f"Method not found: {method}")


def main() -> None:
    _log("Starting MCP server")
    service = CivicquantDbMcpService()
    _log("Service initialized")

    while True:
        message: dict[str, Any] | None = None
        try:
            message = _read_message()
        except JsonRpcError as exc:
            _log(f"Read error: {exc.message}")
            _write_message(_jsonrpc_error(id_value=None, error=exc))
            continue
        except Exception as exc:  # noqa: BLE001
            _log(f"Unexpected read error: {type(exc).__name__}: {exc}")
            _write_message(
                _jsonrpc_error(
                    id_value=None,
                    error=JsonRpcError(
                        code=-32000,
                        message=f"Internal server error: {type(exc).__name__}",
                    ),
                )
            )
            continue

        if message is None:
            _log("EOF received, shutting down")
            break

        try:
            response = _handle_request(message, service)
            if response is not None and "id" in message:
                _write_message(response)
        except JsonRpcError as exc:
            _log(f"JSON-RPC error: {exc.message}")
            if "id" in message:
                _write_message(_jsonrpc_error(id_value=message.get("id"), error=exc))
        except Exception as exc:  # noqa: BLE001
            _log(f"Unhandled error: {type(exc).__name__}: {exc}")
            if "id" in message:
                error = JsonRpcError(
                    code=-32000,
                    message=f"Internal server error: {type(exc).__name__}",
                )
                _write_message(_jsonrpc_error(id_value=message.get("id"), error=error))


if __name__ == "__main__":
    main()