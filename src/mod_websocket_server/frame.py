import struct
from enum import IntEnum

from mod_websocket_server.util import skip_first


class OpCode(IntEnum):
    CONTINUATION = 0x0
    TEXT = 0x1
    BINARY = 0x2
    CLOSE = 0x8
    PING = 0x9
    PONG = 0xA


class Mask(object):
    def __init__(self, masking_key):
        if len(masking_key) != 4:
            raise ValueError(
                "Masking-key must be exactly four bytes, {length} given.".format(
                    length=len(masking_key)
                )
            )

        self.masking_key = bytearray(masking_key)

    def mask(self, data):
        data = bytearray(data)
        for i in xrange(len(data)):
            data[i] ^= self.masking_key[i % 4]
        return data


class Frame(object):
    def __init__(self, fin, op_code, mask, payload):
        self.fin = fin
        self.op_code = op_code
        self.mask = mask
        self.payload = payload

    @property
    def masked(self):
        return self.mask is not None

    @property
    def payload_length(self):
        return len(self.payload)

    def serialize(self):
        frame = bytearray()

        fin_bit = self.fin << 7
        frame += struct.pack("!B", fin_bit | self.op_code)

        masked_bit = self.masked << 7
        if self.payload_length <= 125:
            frame += struct.pack("!B", masked_bit | self.payload_length)
        elif self.payload_length < 2 ** 16:
            frame += struct.pack("!B", masked_bit | 126)
            frame += struct.pack("!H", self.payload_length)
        else:
            frame += struct.pack("!B", masked_bit | 127)
            frame += struct.pack("!Q", self.payload_length)

        if self.masked:
            frame += self.mask.masking_key
            frame += self.mask.mask(self.payload)
        else:
            frame += self.payload

        return frame

    @classmethod
    @skip_first
    def multi_parser(cls):
        parser = cls.parser()
        remaining = None
        frames = []
        while True:
            if remaining is None:
                remaining = yield frames
                frames = []

            result = parser.send(remaining)
            if result:
                frame, remaining = result
                frames.append(frame)
                parser = cls.parser()
            else:
                remaining = None

    @staticmethod
    @skip_first
    def parser():
        read_buffer = bytearray()

        # ------------------------------------------
        # first byte
        # ------------------------------------------

        while len(read_buffer) < 1:
            read_buffer += yield

        fin_mask = 0b10000000
        fin = bool(read_buffer[0] & fin_mask)

        rsv_mask = 0b01110000
        if read_buffer[0] & rsv_mask:
            raise AssertionError("Unsupported extension.")

        op_code_mask = 0b00001111
        op_code = OpCode(read_buffer[0] & op_code_mask)

        read_buffer = read_buffer[1:]

        # ------------------------------------------
        # second byte
        # ------------------------------------------

        while len(read_buffer) < 1:
            read_buffer += yield

        masked_mask = 0b10000000
        masked = bool(read_buffer[0] & masked_mask)

        payload_length_mask = 0b01111111
        payload_length = read_buffer[0] & payload_length_mask

        read_buffer = read_buffer[1:]

        # ------------------------------------------
        # extended length field
        # ------------------------------------------

        if payload_length == 126:
            while len(read_buffer) < 2:
                read_buffer += yield

            (payload_length,) = struct.unpack("!H", read_buffer[:2])

            read_buffer = read_buffer[2:]
        elif payload_length == 127:
            while len(read_buffer) < 4:
                read_buffer += yield

            (payload_length,) = struct.unpack("!Q", read_buffer[:4])

            read_buffer = read_buffer[4:]

        # ------------------------------------------
        # mask key
        # ------------------------------------------

        mask = None
        if masked:
            while len(read_buffer) < 4:
                read_buffer += yield

            mask = Mask(read_buffer[:4])

            read_buffer = read_buffer[4:]

        # ------------------------------------------
        # payload
        # ------------------------------------------

        while len(read_buffer) < payload_length:
            read_buffer += yield

        payload = read_buffer[:payload_length]

        read_buffer = read_buffer[payload_length:]

        # ------------------------------------------
        # assemble
        # ------------------------------------------

        if masked:
            payload = mask.mask(payload)

        yield Frame(fin, op_code, mask, payload), read_buffer

    def __repr__(self):
        return "Frame({op_code})".format(op_code=self.op_code)
