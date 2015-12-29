import asyncio
import aioutp

keep_running = False

class Proto(asyncio.Protocol):
    def __init__(self, is_client):
        self.is_client = is_client
        self.closed = False

    def connection_made(self, transport):
        print('conn made!')
        if self.is_client:
            transport.write(b'HEADER\n')
        self.transport = transport

    def connection_lost(self, exc):
        print('conn lost!')
        self.closed = True

    def data_received(self, data):
        print('data:', data)
        self.transport.write(b'mirror: ' + data)

    def eof_received(self):
        print('EOF!')

async def run_client(loop):
    global keep_running
    t, p = await aioutp.create_connection(lambda: Proto(True), '127.0.0.1', 5000)
    while keep_running:
        await asyncio.sleep(0.1)
        if p.closed:
            break
    else:
        t.close()
    loop.stop()

async def run_server(loop):
    global keep_running
    server = await aioutp.create_server(lambda: Proto(False), '127.0.0.1', 5000)
    while keep_running:
        await asyncio.sleep(0.1)
    server.close()
    await server.wait_closed()
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
