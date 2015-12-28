import socket
import select
import utp

s = None

def sendto_cb(cb, ctx, sock, data, addr, flags):
    addr, port = addr
    print('sending {} byte(s) to {}:{}'.format(len(data), addr, port))
    s.sendto(data, (addr, port))
    return 0

def state_change_cb(cb, ctx, sock, state):
    msg = {
        utp.UTP_STATE_CONNECT: '=> connect',
        utp.UTP_STATE_WRITABLE: '=> writable',
        utp.UTP_STATE_EOF: '=> eof',
        utp.UTP_STATE_DESTROYING: '=> destroying'
    }[state]
    print(msg)
    if state == utp.UTP_STATE_CONNECT:
        utp.utp_write(sock, b'foobar\n')
    return 0

def error_cb(cb, ctx, sock, error_code):
    print('error:', error_code)
    return 0

def read_cb(cb, ctx, sock, data):
    print('read:', data)
    utp.utp_read_drained(sock)
    return 0

def firewall_cb(cb, ctx, addr):
    print('on firewall:', addr)
    return 0

def log_cb(cb, ctx, sock, msg):
    print('log:', msg)
    return 0


def main():
    global s

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fd = s.fileno()
    s.setblocking(0)
    s.bind(('127.0.0.1', 5002))

    ctx = utp.utp_init(2)

    utp.utp_set_callback(ctx, utp.UTP_SENDTO, sendto_cb)
    utp.utp_set_callback(ctx, utp.UTP_LOG, log_cb)
    utp.utp_set_callback(ctx, utp.UTP_ON_STATE_CHANGE, state_change_cb)
    utp.utp_set_callback(ctx, utp.UTP_ON_ERROR, error_cb)
    utp.utp_set_callback(ctx, utp.UTP_ON_READ, read_cb)
    utp.utp_set_callback(ctx, utp.UTP_ON_FIREWALL, firewall_cb)

    #utp.utp_context_set_option(ctx, utp.UTP_LOG_NORMAL, 1)
    #utp.utp_context_set_option(ctx, utp.UTP_LOG_DEBUG, 1)
    #utp.utp_context_set_option(ctx, utp.UTP_LOG_MTU, 1)

    sock = utp.utp_create_socket(ctx);
    ret = utp.utp_connect(sock, ('127.0.0.1', 5001))

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
                        utp.utp_issue_deferred_acks(ctx)
                        drained = True
                    else:
                        print(e)
                        exit(1)
                utp.utp_process_udp(ctx, data, addr)

        utp.utp_check_timeouts(ctx)

    utp.utp_close(sock)
    utp.utp_destroy(ctx)

if __name__ == '__main__':
    main()
