import argparse
import logging
import re
import time
import traceback
import typing
from collections import defaultdict
from types import TracebackType

import quarry.net.ticker
from quarry.net.auth import Profile
from quarry.net.client import ClientFactory, ClientProtocol, SpawningClientProtocol
from quarry.types.buffer import Buffer1_7, Buffer1_9, Buffer1_13, Buffer1_13_2, Buffer1_14, Buffer1_19, Buffer1_19_1
from quarry.types.uuid import UUID
from twisted.internet import defer, reactor

from msauth import login

AnyBuffer = typing.Union[
    Buffer1_7, Buffer1_9, Buffer1_13, Buffer1_13_2, Buffer1_14, Buffer1_19, Buffer1_19_1]


def hexdump(param: typing.Union[bytes, bytearray]):
    if type(param) == bytes:
        param = bytearray(param)
    for c in param:
        print(f'{c:02x}', end=' ')
    print()


# noinspection PyMethodMayBeStatic
class ProtocolO(ClientProtocol):
    def __init__(self, factory, remote_addr):
        super().__init__(factory, remote_addr)
        self.last_tick_time = 0
        self.last_world_age = 0
        self.total_unprocessed_data_recvd = 0
        self.seen_types = []

    def _19_1_send_message(self, message: str):
        buf: Buffer1_19_1 = self.buff_type
        buf.pack_string(message) + buf.pack('fl', time.time(), 0),

    def unified_send_message(self, message: str):
        if self.protocol_version & 0x40000000:  # snapshot
            ...
        elif self.protocol_version >= 760:  # 19.1 @ https://wiki.vg/index.php?title=Protocol&oldid=17873#Chat_Message
            return self._19_1_send_message(message)
        elif self.protocol_version >= 759:  # 19.0 @ https://wiki.vg/index.php?title=Protocol&oldid=17753#Chat_Message
            ...


    def packet_unhandled(self, buff, name):
        # EXCLUDE = ['entity_look_and_relative_move', 'entity_head_look', 'entity_status',
        #            'entity_velocity', 'entity_relative_move', 'entity_metadata',
        #            'entity_teleport', 'entity_properties', 'entity_look',
        #            'entity_equipment', 'spawn_mob', 'destroy_entities', 'effect',
        #            'sound_effect']
        EXCLUDE = []
        size = len(buff.read())
        self.total_unprocessed_data_recvd += size
        if name in EXCLUDE:
            buff.discard()
            return
        if name not in self.seen_types:
            self.seen_types.append(name)
            print(f'\rNew packet type \'{name}\'; size {size}'.ljust(75), flush=True)
        print(f'\r\'{name}\'; size {size}'.ljust(75), end='', flush=True)
        buff.discard()

    def packet_time_update(self, buff: AnyBuffer):
        _, world_age = buff.unpack('ll')
        rn = time.time()
        dt = rn - self.last_tick_time
        dtk = world_age - self.last_world_age
        if dtk == 0:
            return
        tps = dt / (dtk / 20)
        # print(f'time packet {dtk} on server over {dt:.2f}s about {tps:.1%}')
        if tps < 0.9:
            # self.send_packet("chat_message", self.buff_type.pack_string(f'test: Server lagging at {tps:.1%} of normal! (+{dtk} / {dt:.2f}s) '))
            ...
        self.last_world_age = world_age
        self.last_tick_time = time.time()
        buff.discard()

    def packet_keep_alive(self, buff: AnyBuffer):
        self.send_packet("keep_alive", buff.read())
        buff.discard()

    def packet_update_health(self, buff: AnyBuffer):
        health = buff.unpack('f')
        food = buff.unpack_varint()
        sat = buff.unpack('f')
        print(f'\rI now have {health} health, {food} food, and {sat} saturation'.ljust(75), flush=True)
        if health <= 0:
            self.do_respawn()
        buff.discard()

    def do_respawn(self):
        self.send_packet("client_status", self.buff_type.pack_varint(0))

    def spawn(self):
        self.ticker: quarry.net.ticker.Ticker
        self.ticker.add_delay(40, self.close)
        self.ticker.start()


class FactoryO(ClientFactory):
    protocol = ProtocolO


def poggers_bar(pct, width):
    b = '['
    width -= 2
    char = int(width * pct)
    fill = width - char
    b += '='*char
    b += ' '*fill
    b += ']'
    return b


@defer.inlineCallbacks
def go(args):
    try:
        print('\rLogging in...'.ljust(20) + poggers_bar(.2, 30), end='', flush=True)
        login_token, uuid, name = login()
        print('\rBuilding profile...'.ljust(20) + poggers_bar(.4, 30), end='', flush=True)
        profile: Profile = yield Profile("foo", login_token, name, UUID.from_hex(uuid))
        print('\rRetreving certs...'.ljust(20) + poggers_bar(.8, 30), end='', flush=True)
        yield profile.use_signing()
        print('\rConverting...'.ljust(20) + poggers_bar(.9, 30), end='', flush=True)
        dum = profile.certificates.convert_public_key(profile.certificates.public)

        print("\rPublic key hexdump ======".ljust(60))

        b = ''
        for i, x in enumerate(dum):
            print(f'{x:02x}', end=' ')
            b += chr(x) if re.match(r'[\x20-\x7e]', chr(x)) else '.'
            if (i + 1) % 16 == 0:
                print(f' {b}')
                b = ''
        print(((16-((i+1)%16)) * '   ') + f' {b}')
        print(f'End dump ====== {len(dum)} bytes')
        print('\rStarting: starting...'.ljust(20) + poggers_bar(1, 30), end='', flush=True)
        factory = FactoryO(profile)
        print('\rConnecting...'.ljust(60), flush=True)
        factory.connect(args.host, args.port)
    except Exception as e:
        print('\n\n' + '= ERROR =' * 20 + '\nOh noes!!')
        print(f'message >>> {e}')
        print(traceback.format_exc())


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("host", help="server host")
    parser.add_argument("-p", "--port", default=25565, type=int, help="server port")
    args = parser.parse_args(argv)

    go(args)
    reactor.run()


if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
