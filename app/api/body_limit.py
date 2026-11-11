"""Bound streamed bodies before routing, including chunked requests."""

from app.storage.database import json_read

from .errors import error_response


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        length = headers.get(b"content-length")
        try:
            if length is not None and int(length) > self.max_bytes:
                return await error_response(413, "request_too_large", "Request body exceeds configured limit")(scope, receive, send)
        except ValueError:
            return await error_response(422, "invalid_request", "Invalid content length")(scope, receive, send)
        chunks, size = [], 0
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            size += len(event.get("body", b""))
            if size > self.max_bytes:
                return await error_response(413, "request_too_large", "Request body exceeds configured limit")(scope, receive, send)
            chunks.append(event)
            if not event.get("more_body", False):
                break
        body = b"".join(c.get("body", b"") for c in chunks)
        if body and b"json" in headers.get(b"content-type", b"application/json").lower():
            try:
                json_read(body)
            except (ValueError, UnicodeError):
                return await error_response(422, "invalid_json", "Request must contain valid JSON without duplicate fields or nonfinite numbers")(scope, receive, send)
        index = 0
        async def replay():
            nonlocal index
            if index < len(chunks):
                result = chunks[index]
                index += 1
                return result
            return await receive()
        return await self.app(scope, replay, send)
