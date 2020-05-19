from async import async, await
from debug_utils import LOG_NOTE
from mod_async_server import open_server
from mod_websocket_server.frame import Frame
from mod_websocket_server.handshake import perform_handshake


@async
def echo(reader, writer, addr):
    LOG_NOTE("[{host}]:{port} connected".format(host=addr[0], port=addr[1]))
    try:
        yield await(perform_handshake(reader, writer))
        parser = Frame.multi_parser()
        while True:
            data = yield await(reader(512))
            frames = parser.send(data)
            for frame in frames:
                LOG_NOTE("[{host}]:{port} sent frame {frame}".format(host=addr[0], port=addr[1], frame=frame))

    finally:
        LOG_NOTE("[{host}]:{port} disconnected".format(host=addr[0], port=addr[1]))


@async
def serve():
    with open_server(echo, 4000) as poll:
        while True:
            yield await(poll.poll_next_frame())
