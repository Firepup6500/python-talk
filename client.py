import asyncio
import firepup650 as fp

rInput = fp.replitInput
fp.replitCursor = fp.bcolors.REPLIT + "> " + fp.bcolors.RESET


async def client(host, port):
    reader, writer = await asyncio.open_connection(host, port)

    print(f"Send: {message!r}")
    writer.write(message.encode())
    await writer.drain()

    data = await reader.read(100)
    print(f"Received: {data.decode()!r}")

    print("Close the connection")
    writer.close()
    await writer.wait_closed()


host, port = (rInput("Hostname"), rInput("Port (default is 65048)"))
asyncio.run(tcp_echo_client("Hello World!"))
