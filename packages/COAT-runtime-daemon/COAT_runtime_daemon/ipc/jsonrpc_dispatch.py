"""In-process JSON-RPC 2.0 dispatcher over :class:`COATRuntime` (M4 PR-18).

Pure request/response mapping — no sockets, no HTTP. The daemon's future
HTTP server (PR-19) will parse bytes, call :meth:`JsonRpcHandler.handle`,
and serialize the returned dict back to JSON.

Methods are dotted names grouped by domain:

``joinpoint.submit``
    Params: ``{"joinpoint": <JoinpointEvent wire>, "return_none_when_empty"?: bool, "context"?: object}``
    Result: ``ConcernInjection`` wire object or ``null``.

``concern.list`` / ``concern.get`` / ``concern.upsert`` / ``concern.delete``
    Thin wrappers around :class:`~COAT_runtime_core.ports.ConcernStore`.

``runtime.snapshot`` / ``runtime.current_vector`` / ``runtime.last_injection``
    Introspection helpers for health checks and the CLI.

``dcn.activation_log``
    Params: ``{"concern_id"?: str, "limit"?: int}`` — forwards to
    :meth:`~COAT_runtime_core.ports.DCNStore.activation_log`.

``health.ping``
    Result: ``{"ok": true}`` — proves the handler is wired without
    touching stores.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from COAT_runtime_core import COATRuntime
from COAT_runtime_protocol import Concern, ConcernInjection, JoinpointEvent
from pydantic import ValidationError

# JSON-RPC 2.0 error codes (subset we use today).
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603


class JsonRpcParamsError(ValueError):
    """Invalid params for a known method — maps to JSON-RPC -32602."""


def _expect_params_dict(params: dict[str, Any] | list[Any]) -> dict[str, Any]:
    if isinstance(params, list):
        raise JsonRpcParamsError("this method expects a params object, not an array")
    return params


def _json_safe(obj: Any) -> Any:
    """Recursively coerce datetimes and Pydantic models for JSON encoding."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, Concern | JoinpointEvent | ConcernInjection):
        return obj.model_dump(mode="json")
    md = getattr(obj, "model_dump", None)
    if callable(md):
        return _json_safe(md(mode="json"))
    try:
        return _json_safe(asdict(obj))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(obj)


def _success_response(req_id: Any, result: Any) -> dict[str, Any]:
    # JSON-RPC 2.0 §5: Response objects MUST contain an ``id`` member
    # — the request's id verbatim, or ``null`` if the server couldn't
    # detect it (e.g. parse / invalid-request errors before id was
    # readable). Notifications (request without an ``id`` member) get
    # *no* response at all, which is the caller's responsibility.
    return {"jsonrpc": "2.0", "result": _json_safe(result), "id": req_id}


def _error_response(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "error": {"code": code, "message": message},
        "id": req_id,
    }


class JsonRpcHandler:
    """Dispatch JSON-RPC requests against a live :class:`COATRuntime`."""

    def __init__(self, runtime: COATRuntime) -> None:
        self._rt = runtime
        self._methods: dict[str, Any] = {
            "health.ping": self._health_ping,
            "joinpoint.submit": self._joinpoint_submit,
            "concern.list": self._concern_list,
            "concern.get": self._concern_get,
            "concern.upsert": self._concern_upsert,
            "concern.delete": self._concern_delete,
            "runtime.snapshot": self._runtime_snapshot,
            "runtime.current_vector": self._runtime_current_vector,
            "runtime.last_injection": self._runtime_last_injection,
            "dcn.activation_log": self._dcn_activation_log,
        }

    def handle(self, message: str | dict[str, Any]) -> dict[str, Any] | None:
        """Parse ``message``, dispatch, and return a JSON-RPC response dict.

        Returns ``None`` when the request is a **notification** (a
        request object without an ``id`` member, per JSON-RPC 2.0
        §4.1): the server MUST NOT reply. The future HTTP layer
        translates ``None`` into a 204 No Content / empty body.
        """
        try:
            req = json.loads(message) if isinstance(message, str) else dict(message)
        except (TypeError, json.JSONDecodeError) as exc:
            # Parse error: id was never readable, spec says reply with id=null.
            return _error_response(None, _PARSE_ERROR, f"Parse error: {exc}")

        if not isinstance(req, dict):
            return _error_response(None, _INVALID_REQUEST, "Request must be a JSON object")

        is_notification = "id" not in req
        req_id = req.get("id")  # may legitimately be null in the request

        def _maybe(resp: dict[str, Any]) -> dict[str, Any] | None:
            # JSON-RPC 2.0 §4.1: notifications get no response object.
            return None if is_notification else resp

        if req.get("jsonrpc") != "2.0":
            return _maybe(_error_response(req_id, _INVALID_REQUEST, "jsonrpc must be '2.0'"))

        method = req.get("method")
        if not isinstance(method, str) or not method:
            return _maybe(
                _error_response(req_id, _INVALID_REQUEST, "method must be a non-empty string")
            )

        handler = self._methods.get(method)
        if handler is None:
            return _maybe(_error_response(req_id, _METHOD_NOT_FOUND, f"Unknown method: {method!r}"))

        params = req.get("params")
        if params is None:
            params_obj: dict[str, Any] | list[Any] = {}
        elif isinstance(params, (dict, list)):
            params_obj = params
        else:
            return _maybe(
                _error_response(
                    req_id,
                    _INVALID_PARAMS,
                    "params must be object, array, or null",
                )
            )

        try:
            result = handler(params_obj)
        except JsonRpcParamsError as exc:
            return _maybe(_error_response(req_id, _INVALID_PARAMS, str(exc)))
        except ValidationError as exc:
            # Codex P2 on PR-18: schema validation failures are *client*
            # input bugs, not server faults. Surface them as -32602
            # so callers can fix the payload instead of paging on-call.
            return _maybe(_error_response(req_id, _INVALID_PARAMS, f"validation error: {exc}"))
        except Exception as exc:
            return _maybe(_error_response(req_id, _INTERNAL_ERROR, str(exc)))

        return _maybe(_success_response(req_id, result))

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    @staticmethod
    def _health_ping(_params: dict[str, Any] | list[Any]) -> dict[str, bool]:
        return {"ok": True}

    def _joinpoint_submit(self, params: dict[str, Any] | list[Any]) -> Any:
        p = _expect_params_dict(params)
        raw = p.get("joinpoint")
        if not isinstance(raw, dict):
            raise JsonRpcParamsError("joinpoint must be an object")
        jp = JoinpointEvent.model_validate(raw)
        ret_none = bool(p.get("return_none_when_empty", False))
        ctx = p.get("context")
        context = ctx if isinstance(ctx, dict) else None
        inj = self._rt.on_joinpoint(jp, context=context, return_none_when_empty=ret_none)
        return None if inj is None else inj.model_dump(mode="json")

    def _concern_list(self, params: dict[str, Any] | list[Any]) -> list[Any]:
        p = _expect_params_dict(params)
        allowed = ("kind", "tag", "lifecycle_state", "limit")
        kwargs: dict[str, Any] = {k: p[k] for k in allowed if k in p}
        concerns = self._rt.concern_store.list(**kwargs)
        return [c.model_dump(mode="json") for c in concerns]

    def _concern_get(self, params: dict[str, Any] | list[Any]) -> Any:
        p = _expect_params_dict(params)
        cid = p.get("concern_id")
        if not isinstance(cid, str) or not cid:
            raise JsonRpcParamsError("concern_id must be a non-empty string")
        c = self._rt.concern_store.get(cid)
        return None if c is None else c.model_dump(mode="json")

    def _concern_upsert(self, params: dict[str, Any] | list[Any]) -> Any:
        p = _expect_params_dict(params)
        raw = p.get("concern")
        if not isinstance(raw, dict):
            raise JsonRpcParamsError("concern must be an object")
        c = Concern.model_validate(raw)
        out = self._rt.concern_store.upsert(c)
        return out.model_dump(mode="json")

    def _concern_delete(self, params: dict[str, Any] | list[Any]) -> None:
        p = _expect_params_dict(params)
        cid = p.get("concern_id")
        if not isinstance(cid, str) or not cid:
            raise JsonRpcParamsError("concern_id must be a non-empty string")
        self._rt.concern_store.delete(cid)

    def _runtime_snapshot(self, _params: dict[str, Any] | list[Any]) -> Any:
        return self._rt.snapshot()

    def _runtime_current_vector(self, _params: dict[str, Any] | list[Any]) -> Any:
        v = self._rt.current_vector()
        return None if v is None else v.model_dump(mode="json")

    def _runtime_last_injection(self, _params: dict[str, Any] | list[Any]) -> Any:
        inj = self._rt.last_injection()
        return None if inj is None else inj.model_dump(mode="json")

    def _dcn_activation_log(self, params: dict[str, Any] | list[Any]) -> list[Any]:
        p = _expect_params_dict(params)
        cid = p.get("concern_id")
        concern_id = cid if isinstance(cid, str) else None
        limit = p.get("limit")
        lim = int(limit) if isinstance(limit, int) else None
        rows = self._rt.dcn_store.activation_log(concern_id, limit=lim)
        return [dict(r) for r in rows]


__all__ = ["JsonRpcHandler", "JsonRpcParamsError"]
