import os, sys, asyncio, re, signal
from firepup650 import console
from logs import log


class Globals: ...


G = Globals()
G.uniqueClients = 0
G.linked = []
port = 65048
G.msgs = []
G.remoteID = "firepi"
G.event = asyncio.Event()
G.loop = asyncio.get_event_loop()
G.interruptCount = 0
# Try to load a message log, if one exists
try:
    G.msgs = __import__("cache").msgs
    log(f"Got {len(G.msgs)} lines from message cache")
except ImportError:
    log("No server message cache.", level="WARN")
except Exception:
    log(
        "Abnormal state! Failed to load cache even though the file exists!",
        level="WARN",
    )
try:
    for arg in sys.argv:
        if arg.startswith("--port"):
            port = int(arg.lstrip("-port="))
        elif arg.startswith("-p"):
            port = int(arg.lstrip("-p="))
        elif arg in ["-n", "--no-cache"]:
            log("Explicitly erasing cached messages")
            G.msgs = []
        elif arg in ["-?", "-h", "--help"]:
            print("TODO: Help menu soon")
            exit(0)
except Exception:
    sys.tracebacklimit = 0
    raise ValueError("Invalid arguments. Please refer to -? for usage.") from None


async def handle_client(reader, writer):
    try:
        global G
        writer.write(b"Pleass identify yourself. Nick limit is 20 chars.\n")
        await writer.drain()
        name = repr((await reader.read(20)).decode("utf8").strip())[1:-1].replace(
            "\\\\", "\\"
        )
        if len(name) > 20:
            name = name[
                :19
            ]  # Really this is only possible if someone passes raw unicode as a nick, but let's clean it up anyways.
        try:
            await asyncio.wait_for(
                reader.read(), 0.01
            )  # Silently consume the excess useename data
        except asyncio.TimeoutError:
            pass
        if not name:
            writer.write(b"Nice try. Actually set a nick.\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return
        if name in G.linked:
            writer.write(f"Nick ({name}) in use\n".encode("utf8"))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return
        G.linked.extend([name])
        msgIndex = 0
        G.uniqueClients += 1
        G.msgs.extend([log(f"{name} has connected to the server.")])
        while 1:
            try:
                buffer = await asyncio.wait_for(reader.read(970), 0.1)
                request = repr(buffer.decode("utf8").strip())[1:-1].replace(
                    "\\\\", "\\"
                )
                response = None
                if request.startswith("/mes "):
                    response = log(f"* {name}'s {request[4:]}")
                elif request.startswith("/me "):
                    response = log(f"* {name} {request[3:]}")
                elif request.startswith("/h"):
                    writer.write(b"TODO: Command listing\n")
                    await writer.drain()
                elif request.startswith("/quit"):
                    break
                elif request:
                    response = log(f"  {name}: {request}")
                if response:
                    G.msgs.extend([response])
            except asyncio.TimeoutError:
                pass
            if msgIndex < len(G.msgs):
                writer.writelines(G.msgs[msgIndex:])
                msgIndex = len(G.msgs)
            await writer.drain()
        writer.close()
        await writer.wait_closed()
        G.msgs.extend([log(f"{name} has disconnected from the server.")])
        G.linked.remove(name)
    except ConnectionResetError:
        G.msgs.extend([log(f"{name} has disconnected from the server.")])
        G.linked.remove(name)


async def run_server(port):
    global G
    server = await asyncio.start_server(handle_client, "0.0.0.0", port)
    log(f"Listening on port {port}...")
    G.msgs.extend([log("Server startup")])
    crash = False
    try:
        log("Waiting on the Interrupt Event to be set...")
        await G.event.wait()
        log("Interrupt Event has been set, shutting down normally")
    except Exception:
        crash = True
        G.msgs.extend([log("Server crash", level="FATAL")[1:]])
        log("Shutting down from Exception")
        # TODO: Add format_exc here
    finally:
        if not crash:
            G.msgs.extend([log("Server shutdown")])
        log("Kicking all clients as we go down")
        server.close()
        # server.abort_clients()
        with open("cache.py", "w") as cache:
            cache.write(f"msgs = {G.msgs}\n")
        log("Saved logs, exiting now.")


class ServerInterruptException(KeyboardInterrupt): ...


def interruptCatch(s, f):
    global G
    print()
    G.loop.call_soon_threadsafe(G.event.set)
    G.interruptCount += 1
    sys.tracebacklimit = 0
    raise ServerInterruptException from None


signal.signal(signal.SIGINT, interruptCatch)
asyncio.run(run_server(port))
