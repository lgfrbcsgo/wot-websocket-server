from base64 import b64encode
from collections import namedtuple
from hashlib import sha1
from typing import Pattern

from mod_async import Return, async_task
from mod_websocket_server.util import skip_first

KEY = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

SUCCESS_RESPONSE = (
    "HTTP/1.1 101 Switching Protocols\r\n"
    "Upgrade: WebSocket\r\n"
    "Connection: Upgrade\r\n"
    "Sec-WebSocket-Accept: {accept}\r\n\r\n"
)

Request = namedtuple(
    "Request", ("method", "url", "protocol", "protocol_version", "headers")
)


@async_task
def perform_handshake(stream, allowed_origins):
    request = yield read_request(stream)

    if request.method.upper() != "GET":
        raise AssertionError("Method must be GET")

    if float(request.protocol_version) < 1.1:
        raise AssertionError("HTTP version must be at least 1.1")

    if "websocket" not in request.headers["upgrade"].lower():
        raise AssertionError('Upgrade header must include "websocket"')

    if "upgrade" not in request.headers["connection"].lower():
        raise AssertionError('Connection header must include "upgrade"')

    if request.headers["sec-websocket-version"] != "13":
        raise AssertionError("Unsupported Websocket version")

    if allowed_origins and "origin" in request.headers:
        origin = request.headers["origin"]
        for allowed_origin in allowed_origins:
            if isinstance(allowed_origin, Pattern) and allowed_origin.match(origin):
                break
            elif allowed_origin == origin:
                break
        else:
            raise AssertionError(
                "Origin {origin} is not allowed.".format(origin=origin)
            )

    key = request.headers["sec-websocket-key"]
    accept = b64encode(sha1(key + KEY).digest())
    yield stream.send(SUCCESS_RESPONSE.format(accept=accept))
    raise Return(request.headers)


@async_task
def read_request(stream):
    parser = request_parser()
    for _ in range(8):
        data = yield stream.receive(512)
        request = parser.send(data)
        if request:
            raise Return(request)
    else:
        raise AssertionError("Request too large")


@skip_first
def header_line_splitter():
    read_buffer = bytes()
    while True:
        parts = read_buffer.split("\r\n")
        read_buffer = parts[-1]
        read_buffer += yield parts[:-1]


@skip_first
def request_parser():
    splitter = header_line_splitter()
    lines = []
    headers = dict()

    while len(lines) < 1:
        data = yield
        lines.extend(splitter.send(data))

    method, url, protocol_str = lines[0].split(" ")
    protocol, protocol_version = protocol_str.split("/")

    while "" not in lines:
        data = yield
        lines.extend(splitter.send(data))

    for line in lines[1:-1]:
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()

    yield Request(
        method=method,
        url=url,
        protocol=protocol,
        protocol_version=protocol_version,
        headers=headers,
    )
