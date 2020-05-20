from async import async, await, delay
from debug_utils import LOG_NOTE
from mod_async_server import Server
from mod_websocket_server.frame import Frame
from mod_websocket_server.handshake import perform_handshake


@async
def echo(server, stream):
    host, port = stream.peer_addr
    LOG_NOTE("[{host}]:{port} connected".format(host=host, port=port))
    try:
        yield await(perform_handshake(stream))
        parser = Frame.multi_parser()
        while True:
            data = yield await(stream.read(512))
            frames = parser.send(data)
            for frame in frames:
                LOG_NOTE("[{host}]:{port} sent frame {frame}".format(host=host, port=port, frame=frame))

    finally:
        LOG_NOTE("[{host}]:{port} disconnected".format(host=host, port=port))


@async
def serve():
    with Server(echo, 4000) as server:
        while not server.closed:
            server.poll()
            yield await(delay(0))
