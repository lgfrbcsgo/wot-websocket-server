from base64 import b64encode
from collections import namedtuple
from hashlib import sha1

from async import async, await
from BWUtil import AsyncReturn
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


@async
def perform_handshake(stream):
    request = yield await(read_request(stream))  # type: Request

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

    key = request.headers["sec-websocket-key"]
    accept = b64encode(sha1(key + KEY).digest())
    yield await(stream.write(SUCCESS_RESPONSE.format(accept=accept)))


@async
def read_request(stream):
    parser = request_parser()
    while True:
        data = yield await(stream.read(512))
        request = parser.send(data)
        if request:
            raise AsyncReturn(request)


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
