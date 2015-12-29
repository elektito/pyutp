#!/usr/bin/env python3

import asyncio
import argparse
import logging
import sys
import aioutp

keep_running = False
logger = None
listen_mode = False

async def read_stdin():
    loop = asyncio.get_event_loop()

    fut = asyncio.futures.Future(loop=loop)
    def stdin_cb():
        data = sys.stdin.readline()
        if not fut.cancelled():
            fut.set_result(data)

    try:
        loop.add_reader(0, stdin_cb)
        return await fut
    finally:
        loop.remove_reader(0)

async def ucat(reader, writer):
    global keep_running

    loop = asyncio.get_event_loop()

    line_reader = None
    result = None
    while keep_running:
        try:
            tasks = [asyncio.ensure_future(reader.readline()),
                     asyncio.ensure_future(read_stdin())]
            done, pending = await asyncio.wait(
                tasks,
                timeout=0.1,
                return_when=asyncio.FIRST_COMPLETED)

            for t in pending:
                try:
                    t.cancel()
                    await t
                except asyncio.CancelledError:
                    pass

            if done:
                done = done.pop()
                result = done.result()
                if result == b'':
                    keep_running = False
                if done == tasks[1]:
                    writer.write(result.encode())
                else:
                    print(result.decode(), end='')
        except asyncio.TimeoutError:
            # This is here simply to let the user a chance to break
            # the loop by pressing Ctrl-C
            pass
        else:
            if result == b'':
                keep_running = False

    # Cancel the line reading task so that we won't get a warning
    if line_reader:
        try:
            line_reader.cancel()
            await line_reader
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    if not writer._transport.is_closing() and \
       not writer._transport.closed.is_set():
        writer.close()

    loop.stop()

async def run(loop, args):
    global listen_mode

    accepted = False
    async def connected_cb(reader, writer):
        nonlocal accepted

        if accepted:
            writer.close()
            return

        accepted = True
        await ucat(reader, writer)

    if listen_mode:
        server = await aioutp.start_server(connected_cb,
                                           args.bind_address, args.listen)
    else:
        reader, writer = await aioutp.open_connection(
            args.dest_host, args.dest_port)
        await ucat(reader, writer)

def main():
    global keep_running, logger, listen_mode

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
    if not args.listen and not (args.dest_host and args.dest_port):
        print('Destination host and destination port must be specified.')
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

    logger = logging.getLogger('aioucat')
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

    keep_running = True
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(run(loop, args))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        keep_running = False
        loop.run_forever()

if __name__ == '__main__':
    main()
