from async import async, await
from debug_utils import LOG_NOTE
from mod_async_server import delay
from mod_websocket_server import WebsocketServer


@async
def echo_protocol(server, message_stream):
    host, port = message_stream.peer_addr
    LOG_NOTE("[{host}]:{port} connected".format(host=host, port=port))
    try:
        # run until the client closes the connection.
        # the connection will be closed automatically when this function exits.
        # when the connection gets closed by the peer,
        # stream.receive_message and stream.send_message will raise a StreamClosed exception.
        while True:
            # wait until we receive a message.
            message = yield await(message_stream.receive_message())
            LOG_NOTE(
                "Received message from [{host}]:{port}: {message}".format(
                    host=host, port=port, message=message
                )
            )
            # echo the data back to client, wait until everything has been sent.
            yield await(message_stream.send_message(message))
    finally:
        # server closed or peer disconnected.
        LOG_NOTE("[{host}]:{port} disconnected".format(host=host, port=port))


@async
def serve_forever():
    # open server on localhost:4000 using the `echo_protocol` for serving individual connections.
    with WebsocketServer(echo_protocol, 4000) as server:
        # serve forever, serve once per frame.
        while not server.closed:
            server.poll()
            # delay next loop iteration into the next frame.
            yield await(delay(0))