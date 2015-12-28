#!/usr/bin/env python3

import socket
import select
import sys
import os
import logging
import argparse
import utp

keep_running = True
writable = False
listen_mode = False
logger = None
s = None
sock_fd = None
ctx = None
sock = None
exit_code = 0
data_buffer = b''

def sendto_cb(cb, ctx, sock, data, addr, flags):
    addr, port = addr
    logger.debug('sending {} byte(s) to {}:{}'.format(len(data), addr, port))
    s.sendto(data, (addr, port))
    return 0

def state_change_cb(cb, ctx, the_sock, state):
    global keep_running, writable, sock

    msg = {
        utp.UTP_STATE_CONNECT: 'CONNECT',
        utp.UTP_STATE_WRITABLE: 'WRITABLE',
        utp.UTP_STATE_EOF: 'EOF',
        utp.UTP_STATE_DESTROYING: 'DESTROYING'
    }[state]
    logger.debug('Changed state to: {}'.format(msg))

    if state == utp.UTP_STATE_EOF:
        keep_running = False
        utp.utp_close(sock)
        sock = None
    elif state == utp.UTP_STATE_WRITABLE or state == utp.UTP_STATE_CONNECT:
        writable = True
        write_data()
    elif state == utp.UTP_STATE_DESTROYING:
        if sock:
            utp.utp_close(sock)
        sock = None
        keep_running = False

    return 0

def error_cb(cb, ctx, sock, error_code):
    global keep_running

    logger.error('UTP error: {}'.format(error_code))
    utp.utp_close(sock)
    keep_running = False
    exit_code = 1
    return 0

def read_cb(cb, ctx, sock, data):
    print(data.decode(), end='')
    utp.utp_read_drained(sock)
    return 0

def firewall_cb(cb, ctx, addr):
    global sock

    if not listen_mode:
        logger.info(
            'Firewalling unexpected inbound connection in non-listen mode.')
        return 1

    if sock:
        logger.info('Firewalling second inbound connection.')
        return 1

    logger.debug('Firewall allowing inbound connection.')
    return 0

def accept_cb(cb, ctx, new_sock, addr):
    global sock

    assert not sock
    sock = new_sock
    logger.info('Accepted inbound connection.')
    write_data()
    return 0

def log_cb(cb, ctx, sock, msg):
    logger.debug('UTP log: {}'.format(msg.decode()))
    return 0

def write_data():
    global keep_running, sock, data_buffer
    if not writable and not (listen_mode and sock):
        logger.warning('Socket not writable.')
        return

    sent = 0
    while sent < len(data_buffer):
        sent = utp.utp_write(sock, data_buffer)
        if sent == 0:
            print('Socket no longer writable.')
            keep_running = False
            if sock:
                utp.utp_close(sock)
            sock = None
            exit_code = 0
            return
        data_buffer = data_buffer[sent:]

def network_loop():
    global keep_running, data_buffer

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
                        data, addr = s.recvfrom(1500, socket.MSG_DONTWAIT)
                    except socket.error as e:
                        if e.errno == socket.EAGAIN or e.errno == socket.EWOULDBLOCK:
                            logger.debug('Issuing deferred acks.')
                            utp.utp_issue_deferred_acks(ctx)
                            drained = True
                        else:
                            logger.error(e)
                            exit(1)
                    else:
                        utp.utp_process_udp(ctx, data, addr)
            elif fd == sys.stdin.fileno():
                data = os.read(sys.stdin.fileno(), 2000)
                if data == b'':
                    logger.debug('EOF from stdin.')
                    poll.unregister(fd)
                    os.close(sys.stdin.fileno())
                    keep_running = False
                else:
                    data_buffer += data
                    write_data()

        utp.utp_check_timeouts(ctx)

def main():
    global s, sock_fd, ctx, sock, logger, listen_mode, exit_code

    parser = argparse.ArgumentParser(
        description='netcat-like utility using uTP as the transport protocol.')

    parser.add_argument('dest_host', metavar='DEST-HOST', nargs='?',
                        help='Destination host.')
    parser.add_argument('dest_port', metavar='DEST-PORT', nargs='?', type=int,
                        help='Destination port.')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable libutp debug logs and also set logging '
                        'level to "debug".')
    parser.add_argument(
        '--listen', '-l', type=int, metavar='PORT',
        help='Listen mode. A port number should be passed as an argument.')
    parser.add_argument('--bind', '-b', default='127.0.0.1',
                        dest='bind_address',
                        help='The IP address to bind the socket to. '
                        'Defaults to 127.0.0.1.')
    parser.add_argument('--log-file', '-f', help='Log file.')
    parser.add_argument(
        '--log-level', '-L', default='info',
        choices=['critical', 'error', 'warning', 'info', 'debug'],
        help='Minimum level of the logged messages.')
    parser.add_argument('--log-to-stdout', '-o', action='store_true',
                        help='Write log messages to standard output.')

    args = parser.parse_args()

    if args.listen and (args.dest_host or args.dest_port):
        print('When in listen mode, destination host/port cannot be passed.')
        exit(1)
    if args.dest_host and not args.dest_port:
        print('Destination port not specified.')
        exit(1)

    if args.listen:
        listen_mode = True

    if args.debug:
        args.log_level = 'debug'

    log_level = {
        'critical': logging.CRITICAL,
        'error': logging.ERROR,
        'warning': logging.WARNING,
        'info': logging.INFO,
        'debug': logging.DEBUG
    }[args.log_level.lower()]

    logger = logging.getLogger('ucat')
    formatter = logging.Formatter(
        '%(asctime) -15s - %(levelname) -8s - %(message)s')

    if args.log_file:
        handler = logging.FileHandler(args.log_file)
        handler.setFormatter(formatter)
        handler.setLevel(log_level)
        logger.addHandler(handler)

    if args.log_to_stdout:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        handler.setLevel(log_level)
        logger.addHandler(handler)

    logger.setLevel(log_level)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_fd = s.fileno()
    s.setblocking(0)
    if listen_mode:
        s.bind((args.bind_address, args.listen))
    else:
        s.bind((args.bind_address, 0))

    ctx = utp.utp_init(2)

    utp.utp_set_callback(ctx, utp.UTP_SENDTO, sendto_cb)
    utp.utp_set_callback(ctx, utp.UTP_LOG, log_cb)
    utp.utp_set_callback(ctx, utp.UTP_ON_STATE_CHANGE, state_change_cb)
    utp.utp_set_callback(ctx, utp.UTP_ON_ERROR, error_cb)
    utp.utp_set_callback(ctx, utp.UTP_ON_READ, read_cb)
    utp.utp_set_callback(ctx, utp.UTP_ON_FIREWALL, firewall_cb)
    utp.utp_set_callback(ctx, utp.UTP_ON_ACCEPT, accept_cb)

    if args.debug:
        utp.utp_context_set_option(ctx, utp.UTP_LOG_NORMAL, 1)
        utp.utp_context_set_option(ctx, utp.UTP_LOG_DEBUG, 1)
        utp.utp_context_set_option(ctx, utp.UTP_LOG_MTU, 1)

    if not listen_mode:
        sock = utp.utp_create_socket(ctx);
        ret = utp.utp_connect(sock, (args.dest_host, args.dest_port))

    try:
        network_loop()
    except KeyboardInterrupt:
        print()
        if sock:
            utp.utp_close(sock)
            sock = None

    if data_buffer != b'':
        logger.warning('Send buffer not empty.')
        exit_code = 1

    utp.utp_destroy(ctx)

    exit(exit_code)

if __name__ == '__main__':
    main()
