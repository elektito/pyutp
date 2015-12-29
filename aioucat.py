import asyncio
import aioutp

class Proto(asyncio.Protocol):
    def connection_made(self, transport):
        print('conn made!')
        transport.write(b'HEADER\n')
        self.transport = transport

    def connection_lost(self, exc):
        print('conn lost!')

    def data_received(self, data):
        print('data:', data)
        self.transport.write(b'mirror: ' + data)

    def eof_received(self):
        print('EOF!')

async def run():
    t, p = await aioutp.create_connection(Proto, '127.0.0.1', 5000)
    while True:
        await asyncio.sleep(1)

def main():
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(run())
    loop.run_forever()

if __name__ == '__main__':
    main()
