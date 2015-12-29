import asyncio
import socket
import utp
from collections import deque

class UtpTransport(asyncio.Transport):
    def __init__(self, loop, protocol, host, port, local_addr=None, sock=None, ctx=None, server=None):
        self._loop = loop
        self._protocol = protocol
        self._peername = (host, port)
        self._local_addr = local_addr

        self.__writable = False
        self.__closing = False
        self.__closed = False
        self.__close_exception = None
        self.__paused_reading = False
        self.__writing = False
        self.__send_buf = deque()

        if sock is None:
            self.__server = None
            self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_sock.setblocking(0)
            self._udp_sock_fd = self._udp_sock.fileno()

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
        else:
            self.__sock = sock
            self.__ctx = ctx
            self.__server = server

        self.closed = asyncio.Event()

    def __sendto_cb(self, cb, ctx, sock, data, addr, flags):
        self.__send_buf.append(data)
        if not self.__writing:
            self._loop.add_writer(self._udp_sock_fd, self.__write_udp)
            self.__writing = True

    def __state_change_cb(self, cb, ctx, sock, state):
        if state in (utp.UTP_STATE_CONNECT, utp.UTP_STATE_WRITABLE):
            self.__writable = True
            self._loop.call_soon(self._protocol.connection_made, self)

            self._loop.call_later(0.5, self.__check_for_timeouts)
        elif state == utp.UTP_STATE_EOF:
            self._loop.call_soon(self._protocol.eof_received)
            self.close()
        elif state == utp.UTP_STATE_DESTROYING:
            self.__closing = False
            self.__closed = True
            self.closed.set()
            if self.__server:
                self.__server._transport_closed(self)
            else:
                self._loop.remove_reader(self._udp_sock_fd)
                utp.utp_destroy(self.__ctx)
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
        self._loop.call_later(0.5, self.__check_for_timeouts)

    def close(self):
        self.__closing = True
        utp.utp_close(self.__sock)
        self._loop.call_soon(self._protocol.connection_lost,
                             self.__close_exception)

    def is_closing(self):
        return self.__closing

    def get_extra_info(self, name, default=None):
        return {
            'peername': self._peername,
            'socket': self.__sock,
            'sockname': self._local_addr
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

    async def wait_closed(self):
        await self.closed.wait()

class UtpServer:
    def __init__(self, proto_factory, loop, bind_host, bind_port):
        self.transports = []
        self._proto_factory = proto_factory
        self._loop = loop
        self._bind_host = bind_host
        self._bind_port = bind_port
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setblocking(0)
        self._udp_sock_fd = self._udp_sock.fileno()

        if bind_host is None:
            bind_host = '127.0.0.1'
        if bind_port is None:
            bind_port = 0

        self._udp_sock.bind((bind_host, bind_port))

        self.__ctx = utp.utp_init(2)

        utp.utp_set_callback(self.__ctx, utp.UTP_SENDTO, self.__sendto_cb)
        utp.utp_set_callback(self.__ctx, utp.UTP_ON_STATE_CHANGE,
                             self.__state_change_cb)
        utp.utp_set_callback(self.__ctx, utp.UTP_ON_ERROR, self.__error_cb)
        utp.utp_set_callback(self.__ctx, utp.UTP_ON_READ, self.__read_cb)
        utp.utp_set_callback(self.__ctx, utp.UTP_ON_ACCEPT, self.__accept_cb)

        self.__writing = False
        self.__send_buf = deque()
        self.closed = asyncio.Event()

        self._loop.add_reader(self._udp_sock_fd, self.__read_udp)
        self._loop.call_later(0.5, self.__check_for_timeouts)

    def __sendto_cb(self, cb, ctx, sock, data, addr, flags):
        self.__send_buf.append((data, addr))
        if not self.__writing:
            self._loop.add_writer(self._udp_sock_fd, self.__write_udp)
            self.__writing = True

    def __state_change_cb(self, cb, ctx, sock, state):
        if self.transports or self.__closing_transports:
            transport = self.__get_transport(sock)
            transport._UtpTransport__state_change_cb(cb, ctx, sock, state)

    def __error_cb(self, cb, ctx, sock, error_code):
        transport = self.__get_transport(sock)
        proto = transport._protocol
        transport.__close_exception = RuntimeError(
            'UTP Error: {}'.format(error_code))
        transport.close()

    def __read_cb(self, cb, ctx, sock, data):
        transport = self.__get_transport(sock)
        proto = transport._protocol
        self._loop.call_soon(proto.data_received, data)
        utp.utp_read_drained(sock)

    def __accept_cb(self, cb, ctx, sock, addr):
        if self.sockets is None:
            raise RuntimeError('Connection arrived on closed server.')

        proto = self._proto_factory()
        transport = UtpTransport(self._loop, proto, addr[0], addr[1],
                                 (self._bind_host, self._bind_port),
                                 sock, self.__ctx, self)
        self._loop.call_soon(proto.connection_made, transport)
        self.transports.append(transport)

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
                    raise e
            else:
                utp.utp_process_udp(self.__ctx, data, addr)

    def __write_udp(self):
        while len(self.__send_buf) != 0:
            data, peer = self.__send_buf.pop()
            sent = self._udp_sock.sendto(data, peer)
            if sent < len(data):
                raise RuntimeError('Could not send datagram.')

        self._loop.remove_writer(self._udp_sock_fd)
        self.__writing = False

    def __check_for_timeouts(self):
        if self.closed.is_set():
            return

        utp.utp_check_timeouts(self.__ctx)
        self._loop.call_later(0.5, self.__check_for_timeouts)

    def __get_transport(self, sock):
        transports = self.transports if self.transports is not None \
                     else self.__closing_transports
        t = [t for t in transports if t.get_extra_info('socket') == sock]
        if not t:
            raise RuntimeError('Encountered unknown socket.')
        if len(t) > 1:
            raise RuntimeError('More than one transport for one socket.')

        return t[0]

    def _transport_closed(self, transport):
        if self.transports:
            del self.transports[self.transports.index(transport)]
        else:
            del self.__closing_transports[self.__closing_transports.index(transport)]
            if len(self.__closing_transports) == 0:
                self.closed.set()

    def __del__(self):
        utp.utp_destroy(self.__ctx)

    @property
    def sockets(self):
        if self.transports is None:
            return None
        else:
            return [t.get_extra_info('socket') for t in self.transports]

    def close(self):
        if self.transports is None:
            return

        for t in self.transports:
            t.close()

        self.__closing_transports = self.transports
        self.transports = None

        if not self.__closing_transports:
            self.closed.set()

    async def wait_closed(self):
        await self.closed.wait()

async def create_connection(protocol_factory, host=None, port=None, local_addr=None, loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    proto = protocol_factory()
    transport = UtpTransport(loop, proto, host, port, local_addr)
    return transport, proto

async def open_connection(host=None, port=None):
    pass

async def create_server(protocol_factory, host=None, port=None, loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    server = UtpServer(protocol_factory, loop, host, port)
    return server

async def start_server(client_connected_cb, host=None, port=None):
    pass
