import ctypes
import socket
from ctypes import cdll, c_int, c_void_p, c_uint, c_uint32, c_uint64, c_size_t, c_char, c_char_p, POINTER, CFUNCTYPE
from sockaddr import to_sockaddr, from_sockaddr, sockaddr_in

# callbacks
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

# states
UTP_STATE_CONNECT = 1
UTP_STATE_WRITABLE = 2
UTP_STATE_EOF = 3
UTP_STATE_DESTROYING = 4

# options
UTP_LOG_NORMAL = 16
UTP_LOG_MTU = 17
UTP_LOG_DEBUG = 18
UTP_SNDBUF = 19
UTP_RCVBUF = 20
UTP_TARGET_DELAY = 21

class UtpContext(ctypes.Structure):
    pass

class UtpSocket(ctypes.Structure):
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
    _fields_ = [('context', POINTER(UtpContext)),
                ('socket', POINTER(UtpSocket)),
                ('len', c_size_t),
                ('flags', c_uint32),
                ('callback_type', c_int),
                #('buf', c_char_p),
                ('buf', POINTER(c_char)),
                ('anon1', _U1),
                ('anon2', _U2)]

libutp = cdll.LoadLibrary('libutp.so')

CBFUNC = CFUNCTYPE(c_uint64, POINTER(UtpCallbackArgs))
user_callbacks = {}

@CBFUNC
def utp_callback(a):
    args = a.contents

    func = user_callbacks[args.callback_type]

    cb = args.callback_type
    ctx = args.context
    sock = args.socket

    if cb in [UTP_ON_FIREWALL, UTP_ON_ACCEPT, UTP_GET_UDP_MTU,
              UTP_GET_UDP_OVERHEAD, UTP_SENDTO]:
        addr = from_sockaddr(args.address.contents)
    else:
        addr = None

    if cb in [UTP_ON_READ, UTP_LOG, UTP_SENDTO]:
        data = ctypes.string_at(args.buf, args.len)
    else:
        data = None

    args = {
        UTP_ON_FIREWALL: (cb, ctx, addr),
        UTP_ON_ACCEPT: (cb, ctx, sock, addr),
        UTP_ON_CONNECT: (cb, ctx, sock),
        UTP_ON_ERROR: (cb, ctx, sock, args.error_code),
        UTP_ON_READ: (cb, ctx, sock, data),
        UTP_ON_OVERHEAD_STATISTICS: (cb, ctx, sock,
                                     args.send, args.len, args.type),
        UTP_ON_STATE_CHANGE: (cb, ctx, sock, args.state),
        UTP_GET_READ_BUFFER_SIZE: (cb, ctx, sock),
        UTP_ON_DELAY_SAMPLE: (cb, ctx, sock),
        UTP_GET_UDP_MTU: (cb, ctx, sock, addr),
        UTP_GET_UDP_OVERHEAD: (cb, ctx, sock, addr),
        UTP_GET_MILLISECONDS: (cb, ctx, sock),
        UTP_GET_MICROSECONDS: (cb, ctx, sock),
        UTP_GET_RANDOM: (cb, ctx, sock),
        UTP_LOG: (cb, ctx, sock, data),
        UTP_SENDTO: (cb, ctx, sock, data, addr, args.flags)
    }[args.callback_type]

    ret = func(*args)

    return ret

# utp_context *utp_init(int version);
def utp_init(version):
    return libutp.utp_init(version)

# void utp_destroy(utp_context *ctx);
def utp_destroy(ctx):
    libutp.utp_destroy(ctx)

# void utp_set_callback(utp_context *ctx, int callback_type,
#                       utp_callback_t *proc);
def utp_set_callback(ctx, callback_type, func):
    user_callbacks[callback_type] = func
    libutp.utp_set_callback(ctx, callback_type, utp_callback)

# utp_socket *utp_create_socket(utp_context *ctx);
def utp_create_socket(ctx):
    return libutp.utp_create_socket(ctx)

# int utp_process_udp(utp_context *ctx, const byte *buf, size_t len,
#                     const struct sockaddr *to, socklen_t tolen);
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
