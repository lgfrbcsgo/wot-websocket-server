import struct
from collections import deque
from typing import Callable, Deque, Union

from async import _Future, async, await
from BWUtil import AsyncReturn
from mod_async_server import Server, Stream
from mod_websocket_server.frame import Frame, OpCode
from mod_websocket_server.handshake import perform_handshake


def encode_utf8(data):
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

    @async
    def receive_message(self):
        # type: () -> _Future
        while len(self._incoming_message_queue) == 0:
            data = yield await(self._stream.read(512))
            frames = self._frame_parser.send(data)
            for frame in frames:
                yield await(self._handle_frame(frame))

        raise AsyncReturn(self._incoming_message_queue.popleft())

    @async
    def send_message(self, payload):
        # type: (Union[unicode, str]) -> _Future
        frame = Frame(True, OpCode.TEXT, None, encode_utf8(payload))
        yield await(self._send_frame(frame))

    @async
    def close(self, code=1000, reason=""):
        # type: (int, Union[unicode, str]) -> _Future
        payload = struct.pack("!H", code) + encode_utf8(reason)
        close = Frame(True, OpCode.CLOSE, None, payload)
        yield await(self._send_frame(close))
        self._stream.close()

    @async
    def _handle_frame(self, frame):
        # type: (Frame) -> _Future
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
            yield await(self._send_frame(pong))
        elif frame.op_code == OpCode.CLOSE:
            if frame.payload:
                (code,) = struct.unpack("!H", frame.payload[:2])
                reason = frame.payload[2:].decode("utf8")
                yield await(self.close(code, reason))
            else:
                yield await(self.close())

    @async
    def _send_frame(self, frame):
        # type: (Frame) -> _Future
        yield await(self._stream.write(frame.serialize()))


def wrap_websocket_protocol(websocket_protocol):
    # type: (Callable[[WebsocketServer, MessageStream], _Future]) -> Callable[[WebsocketServer, Stream], _Future]
    @async
    def wrapper(server, stream):
        yield await(perform_handshake(stream))
        message_stream = MessageStream(stream)
        yield await(websocket_protocol(server, message_stream))

    return wrapper


class WebsocketServer(Server):
    def __init__(self, websocket_protocol, port, host="localhost"):
        # type: (Callable[[WebsocketServer, MessageStream], _Future], int, str) -> None
        protocol = wrap_websocket_protocol(websocket_protocol)
        super(WebsocketServer, self).__init__(protocol, port, host)
