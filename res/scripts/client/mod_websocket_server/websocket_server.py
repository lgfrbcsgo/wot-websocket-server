import struct
from collections import deque
from typing import Callable, Deque, List, Optional, Pattern, Union

from mod_async import AsyncResult, Return, TimeoutExpired, async_task, timeout
from mod_async_server import Server, Stream
from mod_websocket_server.frame import Frame, OpCode
from mod_websocket_server.handshake import perform_handshake


def encode_utf8(data):
    # type: (Union[str, unicode]) -> str
    if isinstance(data, str):
        data = data.decode("utf8")
    return data.encode("utf8")


class MessageStream(object):
    def __init__(self, stream):
        # type: (Stream) -> None
        self._stream = stream
        self._frame_parser = Frame.multi_parser()
        self._incoming_message_queue = deque()  # type: Deque[unicode]

    @property
    def addr(self):
        return self._stream.addr

    @property
    def peer_addr(self):
        return self._stream.peer_addr

    @async_task
    def receive_message(self):
        # type: () -> AsyncResult[unicode]
        while len(self._incoming_message_queue) == 0:
            data = yield self._stream.receive(512)
            frames = self._frame_parser.send(data)
            for frame in frames:
                yield self._handle_frame(frame)

        raise Return(self._incoming_message_queue.popleft())

    @async_task
    def send_message(self, payload):
        # type: (Union[unicode, str]) -> AsyncResult
        frame = Frame(True, OpCode.TEXT, None, encode_utf8(payload))
        yield self._send_frame(frame)

    @async_task
    def close(self, code=1000, reason=""):
        # type: (int, Union[unicode, str]) -> AsyncResult
        payload = struct.pack("!H", code) + encode_utf8(reason)
        close = Frame(True, OpCode.CLOSE, None, payload)
        yield self._send_frame(close)
        self._stream.close()

    @async_task
    def _handle_frame(self, frame):
        # type: (Frame) -> AsyncResult
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
        # type: (Frame) -> AsyncResult
        yield self._stream.send(frame.serialize())


def websocket_protocol(allowed_origins=None):
    # type: (Optional[List[Union[Pattern, str]]]) -> ...
    def decorator(protocol):
        # type: (Callable[[Server, MessageStream], AsyncResult]) -> Callable[[Server, Stream], AsyncResult]
        @async_task
        def wrapper(server, stream):
            try:
                yield timeout(5, perform_handshake(stream, allowed_origins))
            except TimeoutExpired:
                return
            message_stream = MessageStream(stream)
            yield protocol(server, message_stream)

        return wrapper

    return decorator
