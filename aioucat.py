import asyncio
import aioutp

keep_running = False

async def run_client(loop):
    global keep_running
    reader, writer = await aioutp.open_connection('127.0.0.1', 5000)

    # A UTP connection is only established when the client has sent
    # some data to the server
    writer.write(b'HEADER\n')

    line_reader = None
    while keep_running:
        try:
            line_reader = asyncio.ensure_future(
                asyncio.wait_for(reader.readline(),
                                 timeout=0.1))
            data = await line_reader
        except asyncio.TimeoutError:
            # This is here simply to let the user a chance to break
            # the loop by pressing Ctrl-C
            pass
        else:
            if data == b'':
                break
            writer.write(b'mirror: ' + data)

    # Cancel the line reading task so that we won't get a warning
    if line_reader:
        try:
            line_reader.cancel()
            await line_reader
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    writer.close()

    loop.stop()

async def run_server(loop):
    async def connected_cb(reader, writer):
        data = await reader.readline()
        writer.write(b'mirror: ' + data)
        writer.close()

    global keep_running
    server = await aioutp.start_server(connected_cb, '127.0.0.1', 5000)
    while keep_running:
        await asyncio.sleep(0.1)
    loop.stop()

def main():
    global keep_running
    keep_running = True
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(run_server(loop))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        keep_running = False
        loop.run_forever()

if __name__ == '__main__':
    main()
