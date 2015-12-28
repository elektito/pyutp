import socket
import select
import sys
import os
import logging
import utp

keep_running = True
writable = False

backlog = b''
s = None
sock_fd = None
ctx = None
sock = None

def sendto_cb(cb, ctx, sock, data, addr, flags):
    addr, port = addr
    logging.debug('sending {} byte(s) to {}:{}'.format(len(data), addr, port))
    s.sendto(data, (addr, port))
    return 0

def state_change_cb(cb, ctx, sock, state):
    global keep_running, writable, backlog

    msg = {
        utp.UTP_STATE_CONNECT: 'CONNECT',
        utp.UTP_STATE_WRITABLE: 'WRITABLE',
        utp.UTP_STATE_EOF: 'EOF',
        utp.UTP_STATE_DESTROYING: 'DESTROYING'
    }[state]
    logging.debug('Changed state to: {}'.format(msg))

    if state == utp.UTP_STATE_EOF:
        keep_running = False
    elif state == utp.UTP_STATE_WRITABLE or state == utp.UTP_STATE_CONNECT:
        writable = True

        if backlog:
            write_data(backlog)
            backlog = b''

    return 0

def error_cb(cb, ctx, sock, error_code):
    logging.error('UTP error: {}'.format(error_code))
    return 0

def read_cb(cb, ctx, sock, data):
    print(data.decode(), end='')
    utp.utp_read_drained(sock)
    return 0

def firewall_cb(cb, ctx, addr):
    logging.debug('On firewall: {}:{}'.format(addr[0], addr[1]))
    return 0

def log_cb(cb, ctx, sock, msg):
    logging.debug('UTP log: {}'.format(msg.decode()))
    return 0

def write_data(data):
    global backlog
    if not writable:
        logging.warning('Socket not writable. Buffering data for later.')
        backlog += data
        return

    sent = 0
    while sent < len(data):
        sent = utp.utp_write(sock, data)
        if sent == 0:
            print('Socket no longer writable.')
            return
        data = data[sent:]

def network_loop():
    global keep_running

    poll = select.poll()
    poll.register(sock_fd, select.POLLIN)
    poll.register(sys.stdin.fileno(), select.POLLIN)
    while keep_running:
        results = poll.poll(100)
        for fd, ev in results:
            if fd == sock_fd:
                drained = False
                while not drained:
                    try:
                        data, addr = s.recvfrom(1500)
                    except socket.error as e:
                        if e.errno == socket.EAGAIN or e.errno == socket.EWOULDBLOCK:
                            logging.debug('Issuing deferred acks.')
                            utp.utp_issue_deferred_acks(ctx)
                            drained = True
                        else:
                            logging.error(e)
                            exit(1)
                    utp.utp_process_udp(ctx, data, addr)
            elif fd == sys.stdin.fileno():
                data = os.read(sys.stdin.fileno(), 2000)
                if data == b'':
                    logging.debug('EOF from stdin.')
                    poll.unregister(fd)
                    os.close(sys.stdin.fileno())
                    keep_running = False
                else:
                    write_data(data)

        utp.utp_check_timeouts(ctx)

def main():
    global s, sock_fd, ctx, sock

    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout,
                        format='%(asctime) -15s - %(levelname) -8s - %(message)s')

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_fd = s.fileno()
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

    try:
        network_loop()
    except KeyboardInterrupt:
        print()

    utp.utp_close(sock)
    utp.utp_destroy(ctx)

if __name__ == '__main__':
    main()
