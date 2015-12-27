import ctypes
import socket
import select
from ctypes import cdll, c_int, c_void_p, c_uint, c_uint32, c_uint64, c_size_t, c_char, c_char_p, POINTER, CFUNCTYPE
from sockaddr import to_sockaddr, from_sockaddr, sockaddr_in

# callback names
UTP_ON_FIREWALL = 0
UTP_ON_ACCEPT = 1
UTP_ON_CONNECT = 2
UTP_ON_ERROR = 3
UTP_ON_READ = 4
UTP_ON_OVERHEAD_STATISTICS = 5
UTP_ON_STATE_CHANGE = 6
UTP_GET_READ_BUFFER_SIZE = 7
UTP_ON_DELAY_SAMPLE = 8
UTP_GET_UDP_MTU = 9
UTP_GET_UDP_OVERHEAD = 10
UTP_GET_MILLISECONDS = 11
UTP_GET_MICROSECONDS = 12
UTP_GET_RANDOM = 13
UTP_LOG = 14
UTP_SENDTO = 15

UTP_STATE_CONNECT = 1
UTP_STATE_WRITABLE = 2
UTP_STATE_EOF = 3
UTP_STATE_DESTROYING = 4

UTP_LOG_NORMAL = 16
UTP_LOG_MTU = 17
UTP_LOG_DEBUG = 18
UTP_SNDBUF = 19
UTP_RCVBUF = 20
UTP_TARGET_DELAY = 21

class utp_context(ctypes.Structure):
    pass

class utp_socket(ctypes.Structure):
    pass

class UtpCallbackArgs(ctypes.Structure):
    class _U1(ctypes.Union):
        _fields_ = [('address', POINTER(sockaddr_in)),
                    ('send', c_int),
                    ('sample_ms', c_int),
                    ('error_code', c_int),
                    ('state', c_int)]
    class _U2(ctypes.Union):
        _fields_ = [('address_len', c_uint32),
                    ('type', c_int)]
    _anonymous_ = ('anon1', 'anon2')
    _fields_ = [('context', POINTER(utp_context)),
                ('socket', POINTER(utp_socket)),
                ('len', c_size_t),
                ('flags', c_uint32),
                ('callback_type', c_int),
                #('buf', c_char_p),
                ('buf', POINTER(c_char)),
                ('anon1', _U1),
                ('anon2', _U2)]

libutp = cdll.LoadLibrary('libutp.so')

# utp_context *utp_init(int version);
def utp_init(version):
    return libutp.utp_init(version)

# void utp_destroy(utp_context *ctx);
def utp_destroy(ctx):
    libutp.utp_destroy(ctx)

# void utp_set_callback(utp_context *ctx, int callback_name, utp_callback_t *proc);
CBFUNC = CFUNCTYPE(c_uint64, POINTER(UtpCallbackArgs))
def utp_set_callback(ctx, callback_name, func):
    libutp.utp_set_callback(ctx, callback_name, func)

# utp_socket *utp_create_socket(utp_context *ctx);
def utp_create_socket(ctx):
    return libutp.utp_create_socket(ctx)

# int utp_process_udp(utp_context *ctx, const byte *buf, size_t len, const struct sockaddr *to, socklen_t tolen);
def utp_process_udp(ctx, data, addr):
    addr, addrlen = to_sockaddr(socket.AF_INET, addr)
    return libutp.utp_process_udp(ctx,
                                  data, c_size_t(len(data)),
                                  ctypes.byref(addr), addrlen)

# void utp_issue_deferred_acks(utp_context *ctx);
def utp_issue_deferred_acks(ctx):
    libutp.utp_issue_deferred_acks(ctx)

# void utp_check_timeouts(utp_context *ctx);
def utp_check_timeouts(ctx):
    libutp.utp_check_timeouts(ctx)

# int utp_context_set_option(utp_context *ctx, int opt, int val);
def utp_context_set_option(ctx, opt, val):
    libutp.utp_context_set_option(ctx, opt, val)

# int utp_connect(utp_socket *s, const struct sockaddr *to, socklen_t tolen);
def utp_connect(sock, dst):
    addr, addrlen = to_sockaddr(socket.AF_INET, dst)
    return libutp.utp_connect(sock, ctypes.byref(addr), addrlen)

# ssize_t utp_write(utp_socket *s, void *buf, size_t count);
def utp_write(sock, buf):
    return libutp.utp_write(sock, buf, len(buf))

# void utp_read_drained(utp_socket *s);
def utp_read_drained(sock):
    libutp.utp_read_drained(sock)

# void utp_close(utp_socket *s);
def utp_close(sock):
    libutp.utp_close(sock)

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fd = s.fileno()
    s.setblocking(0)
    s.bind(('127.0.0.1', 5002))

    def sendto_cb(a):
        args = a.contents
        addr, port = from_sockaddr(args.address.contents)
        data = ctypes.string_at(args.buf, args.len)
        print('sending {} byte(s) to {}:{}'.format(len(data), addr, port))
        s.sendto(data, (addr, port))
        return 0

    def state_change_cb(a):
        args = a.contents
        msg = {
            UTP_STATE_CONNECT: '=> connect',
            UTP_STATE_WRITABLE: '=> writable',
            UTP_STATE_EOF: '=> eof',
            UTP_STATE_DESTROYING: '=> destroying'
        }[args.state]
        print(msg)
        if args.state == UTP_STATE_CONNECT:
            utp_write(args.socket, b'foobar\n')
        return 0

    def error_cb(a):
        args = a.contents

        print('error:', args.error_code)
        return 0

    def read_cb(a):
        args = a.contents
        print('read:', ctypes.string_at(args.buf, args.len))
        utp_read_drained(args.socket)

        return 0

    def firewall_cb(a):
        print('on firewall')
        args = a.contents

        return 0

    def log_cb(a):
        args = a.contents
        print('log:', ctypes.string_at(args.buf))
        utp_read_drained(args.socket)
        return 0

    ctx = utp_init(2)

    sendto_cb_proc = CBFUNC(sendto_cb)
    state_change_cb_proc = CBFUNC(state_change_cb)
    error_cb_proc = CBFUNC(error_cb)
    read_cb_proc = CBFUNC(read_cb)
    firewall_cb_proc = CBFUNC(firewall_cb)
    log_cb_proc = CBFUNC(log_cb)
    utp_set_callback(ctx, UTP_SENDTO, sendto_cb_proc)
    utp_set_callback(ctx, UTP_LOG, log_cb_proc)
    utp_set_callback(ctx, UTP_ON_STATE_CHANGE, state_change_cb_proc)
    utp_set_callback(ctx, UTP_ON_ERROR, error_cb_proc)
    utp_set_callback(ctx, UTP_ON_READ, read_cb_proc)
    utp_set_callback(ctx, UTP_ON_FIREWALL, firewall_cb_proc)

    #utp_context_set_option(ctx, UTP_LOG_NORMAL, 1)
    #utp_context_set_option(ctx, UTP_LOG_DEBUG, 1)
    #utp_context_set_option(ctx, UTP_LOG_MTU, 1)

    sock = utp_create_socket(ctx);
    ret = utp_connect(sock, ('127.0.0.1', 5001))

    poll = select.poll()
    poll.register(fd, select.POLLIN)
    while True:
        results = poll.poll(100)
        if len(results) > 0:
            drained = False
            while not drained:
                try:
                    data, addr = s.recvfrom(1500)
                except socket.error as e:
                    if e.errno == socket.EAGAIN or e.errno == socket.EWOULDBLOCK:
                        print('issuing deferred acks')
                        utp_issue_deferred_acks(ctx)
                        drained = True
                    else:
                        print(e)
                        exit(1)
                utp_process_udp(ctx, data, addr)

        utp_check_timeouts(ctx)

    utp_close(sock)
    utp_destroy(ctx)

if __name__ == '__main__':
    main()
