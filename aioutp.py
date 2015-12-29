import asyncio
import socket
import utp
from collections import deque

class UtpTransport(asyncio.Transport):
    def __init__(self, loop, protocol, host, port, local_addr=None):
        self._loop = loop
        self._protocol = protocol
        self._peername = (host, port)
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setblocking(0)
        self._udp_sock_fd = self._udp_sock.fileno()

        self.__writable = False
        self.__closing = False
        self.__closed = False
        self.__close_exception = None
        self.__paused_reading = False
        self.__writing = False
        self.__send_buf = deque()

        if local_addr == None:
            self._udp_sock.bind(('127.0.0.1', 0))
        else:
            self._udp_sock.bind(localaddr)

        self.__ctx = utp.utp_init(2)

        utp.utp_set_callback(self.__ctx, utp.UTP_SENDTO, self.__sendto_cb)
        utp.utp_set_callback(self.__ctx, utp.UTP_ON_STATE_CHANGE,
                             self.__state_change_cb)
        utp.utp_set_callback(self.__ctx, utp.UTP_ON_ERROR, self.__error_cb)
        utp.utp_set_callback(self.__ctx, utp.UTP_ON_READ, self.__read_cb)

        self.__sock = utp.utp_create_socket(self.__ctx)
        ret = utp.utp_connect(self.__sock, (host, port))
        if ret != 0:
            raise RuntimeError('Could not establish UTP connection.')

        self._loop.add_reader(self._udp_sock_fd, self.__read_udp)

    def __sendto_cb(self, cb, ctx, sock, data, addr, flags):
        self.__send_buf.append(data)
        if not self.__writing:
            self._loop.add_writer(self._udp_sock_fd, self.__write_udp)
            self.__writing = True

    def __state_change_cb(self, cb, ctx, sock, state):
        if state in (utp.UTP_STATE_CONNECT, utp.UTP_STATE_WRITABLE):
            self.__writable = True
            self._loop.call_soon(self._protocol.connection_made, self)

            self._loop.call_later(1, self.__check_for_timeouts)
        elif state == utp.UTP_STATE_EOF:
            self._loop.call_soon(self._protocol.eof_received)
            self.close()
        elif state == utp.UTP_STATE_DESTROYING:
            self.__closing = False
            self.__closed = True
        else:
            raise RuntimeError('Encountered unknown UTP state: {}', state)

    def __error_cb(self, cb, ctx, sock, error_code):
        self.__close_exception = RuntimeError('UTP Error: {}'.format(error_code))
        self.close()

    def __read_cb(self, cb, ctx, sock, data):
        self._loop.call_soon(self._protocol.data_received, data)
        utp.utp_read_drained(self.__sock)

    def __read_udp(self):
        drained = False
        while not drained:
            try:
                data, addr = self._udp_sock.recvfrom(1500, socket.MSG_DONTWAIT)
            except socket.error as e:
                if e.errno == socket.EAGAIN or e.errno == socket.EWOULDBLOCK:
                    utp.utp_issue_deferred_acks(self.__ctx)
                    drained = True
                else:
                    self.__close_exception = e
                    self.close()
            else:
                utp.utp_process_udp(self.__ctx, data, addr)

    def __write_udp(self):
        while len(self.__send_buf) != 0:
            data = self.__send_buf.pop()
            sent = self._udp_sock.sendto(data, self._peername)
            if sent < len(data):
                raise RuntimeError('Could not send datagram.')

        self._loop.remove_writer(self._udp_sock_fd)
        self.__writing = False

    def __check_for_timeouts(self):
        if self.__closing or self.__closed:
            return

        utp.utp_check_timeouts(self.__ctx)
        self._loop.call_later(1, self.__check_for_timeouts)

    def close(self):
        self.__closing = True
        utp.utp_close(self.__sock)
        self._loop.call_soon(self._protocol.connection_lost,
                             self.__close_exception)
        self._loop.remove_reader(self._udp_sock_fd)

    def is_closing(self):
        return self.__closing

    def get_extra_info(self, name, default=None):
        return {
            'peername': self._peername,
            'socket': self.__sock,
            'sockname': self._udp_sock.getsockname()
        }.get(name, default)

    def pause_reading(self):
        if self.__closing:
            raise RuntimeError('Cannot pause reading while closing.')
        if self.__paused_reading:
            raise RuntimeError('Already paused.')
        self.__paused_reading = True
        self._loop.remove_reader(self._udp_sock_fd)

    def resume_reading(self):
        if not self.__paused_reading:
            raise RuntimeError('Not paused.')
        self.__paused_reading = False
        self._loop.add_reader(self._udp_sock_fd, self.__read_udp)

    def write(self, data):
        utp.utp_write(self.__sock, data)

    def can_write_eof(self):
        return False

    def abort(self):
        utp.utp_close(self.__sock)
        utp.utp_destroy(self.__ctx)
        self._loop.call_soon(self._protocol.connection_lost, None)
        self.closed = False

async def create_connection(protocol_factory, host=None, port=None, local_addr=None, loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    proto = protocol_factory()
    transport = UtpTransport(loop, proto, host, port, local_addr)
    return transport, proto

async def open_connection(host=None, port=None):
    pass

async def create_server(protocol_factory, host=None, port=None):
    pass

async def start_server(client_connected_cb, host=None, port=None):
    pass
