import struct
from collections import deque

from mod_async import Return, TimeoutExpired, async_task, timeout
from mod_async_server import StreamClosed
from mod_websocket_server.frame import Frame, OpCode
from mod_websocket_server.handshake import perform_handshake
from mod_websocket_server.logging import LOG_NOTE


def encode_utf8(data):
    if isinstance(data, str):
        data = data.decode("utf8")
    return data.encode("utf8")


class MessageStream(object):
    def __init__(self, stream, handshake_headers):
        self.handshake_headers = handshake_headers
        self._stream = stream
        self._frame_parser = Frame.multi_parser()
        self._incoming_message_queue = deque()

    @property
    def addr(self):
        return self._stream.addr

    @property
    def peer_addr(self):
        return self._stream.peer_addr

    @async_task
    def receive_message(self):
        while len(self._incoming_message_queue) == 0:
            data = yield self._stream.receive(512)
            frames = self._frame_parser.send(data)
            for frame in frames:
                yield self._handle_frame(frame)

        raise Return(self._incoming_message_queue.popleft())

    @async_task
    def send_message(self, payload):
        frame = Frame(True, OpCode.TEXT, None, encode_utf8(payload))
        yield self._send_frame(frame)

    @async_task
    def close(self, code=1000, reason=""):
        payload = struct.pack("!H", code) + encode_utf8(reason)
        close = Frame(True, OpCode.CLOSE, None, payload)
        try:
            yield self._send_frame(close)
        except StreamClosed:
            pass
        finally:
            self._stream.close()

    @async_task
    def _handle_frame(self, frame):
        if not frame.fin:
            raise AssertionError("Message fragmentation is not supported.")

        if frame.op_code == OpCode.TEXT:
            message = frame.payload.decode("utf8")
            self._incoming_message_queue.append(message)
        elif frame.op_code == OpCode.BINARY:
            raise AssertionError("Binary frames are not supported.")
        elif frame.op_code == OpCode.CONTINUATION:
            raise AssertionError("Message fragmentation is not supported.")
        elif frame.op_code == OpCode.PING:
            pong = Frame(True, OpCode.PONG, None, frame.payload)
            yield self._send_frame(pong)
        elif frame.op_code == OpCode.CLOSE:
            if frame.payload:
                (code,) = struct.unpack("!H", frame.payload[:2])
                reason = frame.payload[2:].decode("utf8")
                yield self.close(code, reason)
            else:
                yield self.close()

    @async_task
    def _send_frame(self, frame):
        yield self._stream.send(frame.serialize())


def websocket_protocol(allowed_origins=None):
    def decorator(protocol):
        @async_task
        def wrapper(server, stream):
            try:
                handshake_headers = yield timeout(
                    5, perform_handshake(stream, allowed_origins)
                )
            except TimeoutExpired:
                return

            host, port = stream.peer_addr
            origin = handshake_headers.get("origin")
            LOG_NOTE(
                "Websocket: {origin} ([{host}]:{port}) connected.".format(
                    origin=origin, host=host, port=port
                )
            )

            message_stream = MessageStream(stream, handshake_headers)
            try:
                yield protocol(server, message_stream)
            finally:
                LOG_NOTE(
                    "Websocket: {origin} ([{host}]:{port}) disconnected.".format(
                        origin=origin, host=host, port=port
                    )
                )
                yield message_stream.close()

        return wrapper

    return decorator
