import os, sys, asyncio, re, signal
from firepup650 import console
from logs import log


class Globals: ...


G = Globals()
G.uniqueClients = 0
G.serverLinks = 0
G.servers = {}
G.clientsConnected = []
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


def raw(string: str) -> str:
    s = string.strip()
    return f"{s!r}"[1:-1].replace("\\\\", "\\")

def fmt(msg: str, name: str = "", action: bool = False) -> str:
    if action:
        return f"* {name}{' '*(20-len(name))}  {msg}"
    else:
        return f"  {name}{' '*(20-len(name))}: {msg}"

async def handle_client(reader, writer):
    try:
        global G
        writer.write(b"Please identify yourself. Nick limit is 20 chars.\n")
        await writer.drain()
        name = raw((await reader.read(20)).decode("utf8"))
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
        if name in G.clientsConnected:
            writer.write(f"Nick ({name}) in use\n".encode("utf8"))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return
        if not name.startswith("S2S-"):
            G.clientsConnected.extend([name])
            msgIndex = 0
            G.uniqueClients += 1
            G.msgs.extend([log(f"{name} has connected to the server.")])
            while 1:
                try:
                    buffer = await asyncio.wait_for(reader.read(967), 0.1)
                    request = raw(buffer.decode("utf8"))
                    response = None
                    if request.startswith("/mes "):
                        response = log(f"* {name}'s {request[5:]}")
                    elif request.startswith("/me "):
                        response = log(f"* {name} {request[4:]}")
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
            G.uniqueClients -= 1
            G.msgs.extend([log(f"{name} has disconnected from the server.")])
            G.clientsConnected.remove(name)
        else:  # This is... probably a server?
            sName = name[4:]  # Trim off the S2S label
            log(f"Server link! Link from {sName}")
            G.serverLinks += 1
            G.servers[sName] = []
            msgIndex = 0
            while 1:
                client = await reader.read(967)
                if client == f"END OF CLIENT LISTING FROM {sName}":
                    break
                G.msgs.extend([log(f"{client} has connected from {sName}")])
                G.servers[sName].append(client)
            G.clientsConnected.extend(G.servers[sName])
            while 1:
                buffer = await asyncio.wait_for(reader.read(967), 0.1)
                request = raw(buffer.decode("utf8"))
                match buffer[0]:
                    case "S":  # Server notice
                        G.msgs.extend([log(buffer[2:])])
                        writer.write(b"I Mmm... Blueberries\n")
                        await writer.drain()
                    case "I":
                        pass
                    case "+":
                        cName = buffer[2:]
                        G.msgs.extend([log(f"{cName} has connected from {sName}")])
                        G.clientsConnected.extend([cName])
                        writer.write(b"I Mmm... Pineapples"\n")
                        await writer.drain()
                    case "-":
                        cName = buffer[2:]
                        G.clientsConnected.remove(cName)
                        await writer.drain()
    except ConnectionResetError:
        if not name.startswith("S2S-"):
            G.msgs.extend([log(f"{name} has disconnected from the server.")])
            G.clientsConnected.remove(name)
        else:
            for cName in G.serverLinks[name[4:]]:
                G.msgs.extend([log(f"{cName}'s server is going down")])
                G.clientsConnected.remove(cName)
            G.serverLinks -= 1
            G.servers.remove(name[4:])
            G.msgs.extend([log(f"{name[4:]} has de-linked from the network")])


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
