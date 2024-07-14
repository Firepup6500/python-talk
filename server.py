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
G.remoteID = "pyTalkServ"
G.event = asyncio.Event()
G.loop = asyncio.get_event_loop()
G.interruptCount = 0
G.killList = {}
G.outboundLinks = []
G.S2SLogs = []
saveLogs = True
address = '0.0.0.0'
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
    sys.argv.pop(0)  # Ignore the filename
    for arg in sys.argv:
        if arg.startswith("--port") or arg.startswith("-p"):
            port = int(arg.lstrip("-port="))
        elif arg in ["-n", "--no-cache"]:
            log("Explicitly erasing cached messages")
            G.msgs = []
        elif arg in ["-?", "-h", "--help"]:
            print("TODO: Help menu soon")
            exit(0)
        elif arg in ["-l", "--no-logs"]:
            log("Explicitly disabling saving of logs!")
            saveLogs = False
        elif arg.startswith("--link"):
            G.outboundLinks.append((arg[6:], int(arg.split(":")[1])))
        elif arg.startswith("--hostname"):
            G.remoteID = arg[10:]
        elif arg.startswith("--address"):
            address = arg[9:]
        else:
            log(f"Unrecognized argument {arg}!", "WARN")
except Exception:
    sys.tracebacklimit = 0
    raise ValueError("Invalid arguments. Please refer to -? for usage.") from None


def raw(string: str) -> str:
    s = string.strip()
    s = f"{s!r}"[1:-1].replace("\\\\", "\\")
    if '"' in s:
        return s.replace("\\'", "'")
    else:
        return s


def fmt(msg: str, name: str = "", action: bool = False) -> str:
    if action:
        return f"* {name}{' '*(20-len(name))}  {msg}"
    else:
        return f"  {name}{' '*(20-len(name))}: {msg}"


async def handleClient(reader, writer):
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
            )  # Silently consume the excess username data
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
            G.clientsConnected.append(name.lower())
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
                    elif request.startswith("/afk"):
                        if len(request) > 5:
                            response = log(f"* {name} is afk to {request[4:]}")
                        else:
                            response = log(f"* {name} is afk")
                    elif request.startswith("/back"):
                        response = log(f"* {name} is back")
                    elif request:
                        response = log(f"  {name}: {request}")
                    if response:
                        G.msgs.extend([response])
                except asyncio.TimeoutError:
                    pass
                if msgIndex < len(G.msgs):
                    writer.writelines(G.msgs[msgIndex:])
                    await writer.drain()
                    msgIndex = len(G.msgs)
                if name.lower() in G.killList and G.killList[name.lower()]:
                    writer.write(b"Your client has been killed by the server\n")
                    G.killList[name.lower()] = False
                    break
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            G.uniqueClients -= 1
            G.msgs.append(log(f"{name} has disconnected from the server."))
            G.clientsConnected.remove(name.lower())
        else:  # This is... probably a server?
            sName = name[4:]  # Trim off the S2S label
            log(f"Server link! Link from {sName}")
            G.serverLinks += 1
            G.servers[sName] = []
            msgIndex = 0
            writer.write("I am awaiting your client listing.\n")
            while 1:
                client = raw((await reader.read(1024)).decode("utf8"))
                if client == f"END OF CLIENT LISTING FROM {sName}":
                    break
                if client.lower() in G.servers[sName] or client.lower() in G.clientsConnected:
                    writer.write(b"K Client rejected: Already exists\n")
                    await writer.drain()
                    continue
                writer.write(b"I added that client.\n")
                await writer.drain()
                G.msgs.append(log(f"{client} has connected from {sName}"))
                G.servers[sName].append(client.lower())
            writer.write(f"{G.remoteID}\n".encode("utf8"))
            await writer.drain()
            await reader.read()
            for client in G.clientsConnected:
                writer.write(f"{client}\n".encode("utf8"))
                resp = raw((await reader.read(1024)).decode("utf8"))
                if resp.startswith("K"):
                    G.killList[client.lower()] = True
            writer.write(f"END OF CLIENT LISTING FROM {G.remoteID}\n".encode("utf8"))
            G.clientsConnected.extend(G.servers[sName])
            while 1:
                try:
                    rawMsg = await asyncio.wait_for(reader.read(967), 0.1)
                    buffer = raw(rawMsg.decode("utf8"))
                    match buffer[0]:
                        case "S":  # Server notice
                            G.msgs.extend([log(buffer[2:])])
                            writer.write(b"I Mmm... Blueberries\n")
                        case "I":
                            pass
                        case "+":
                            cName = buffer[2:]
                            if cName.lower() not in G.clientsConnected:
                                G.msgs.append(
                                    log(f"{cName} has connected from {sName}")
                                )
                                G.servers[sName].append(cName.lower())
                                G.clientsConnected.append(cName.lower())
                                writer.write(b"I Mmm... Pineapples\n")
                            else:
                                writer.write(f"K {cName}\n".encode("utf8"))
                        case "-":
                            cName = buffer[2:]
                            G.msgs.append(log(f"{cName} has disconnected from {sName}"))
                            G.servers[sName].remove(cName.lower())
                            G.clientsConnected.remove(cName.lower())
                            writer.write(b"I Mmm... Bananas\n")
                        case "M":
                            cName = buffer[2:].split("|", 1)[0]
                            message = buffer[2:].split("|", 1)[1]
                            G.msgs.append(log(f"  {cName}: {message}"))
                            writer.write(
                                b"I Get these damn heretic ghost clients out of my store so i can buy my cult candles in peace."
                            )
                        case "A":
                            cName = buffer[2:].split("|", 1)[0]
                            message = buffer[2:].split("|", 1)[1]
                            G.msgs.append(log(f"* {cName} {message}"))
                            writer.write(b"I Mmm... Strawberries\n")
                        case "Q":
                            break
                        case "K":
                            cName = buffer[2:]
                            G.killList[cName] = True
                            writer.write(b"I Mmm... Blood\n")
                        case _:
                            writer.write(
                                f"S Your server is doing drugs over here, sending me bullshit messages man - {G.remoteID}, A fellow server\n".encode("utf8")
                            )
                    await writer.drain()
                except TimeoutError:
                    pass
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            for cName in G.servers[sName]:
                G.msgs.append(log(f"{cName}'s server is going down"))
                G.clientsConnected.remove(cName.lower())
            G.serverLinks -= 1
            G.servers.remove(sName)
            G.msgs.append(log(f"{sName} has de-linked from the network"))
    except (ConnectionResetError, BrokenPipeError):
        if not name.startswith("S2S-"):
            G.uniqueClients -= 1
            G.msgs.append(log(f"{name} has disconnected from the server."))
            G.clientsConnected.remove(name.lower())
        else:
            for cName in G.servers[name[4:]]:
                G.msgs.append(log(f"{cName}'s server is going down"))
                try:
                    G.clientsConnected.remove(cName.lower())
                except Exception:  # Crash during connection sequence?
                    pass
            G.serverLinks -= 1
            G.servers.remove(name[4:])
            G.msgs.append(log(f"{name[4:]} has de-linked from the network"))


async def connectServer(hostname: str, port: int):
    reader, writer = await asyncio.open_connection(hostname, port)
    await reader.read(1024)
    writer.write(f"S2S-{G.remoteID}\n".encode("utf8"))
    await writer.drain()
    await reader.read(1024)
    for client in G.clientsConnected:
        writer.write(f"{client}\n".encode("utf8"))
        await writer.drain()
        resp = raw((await reader.read(1024)).decode("utf8"))
        if resp.startswith("K"):
            G.killList[client.lower()] = True
    writer.write(f"END OF CLIENT LISTING FROM {G.remoteID}\n".encode("utf8"))
    await writer.drain()
    rID = raw((await reader.read(1024)).decode("utf8"))
    G.serverLinks += 1
    G.servers.append(rID)
    writer.write(b"I recieved your remote ID, now awaiting client listing\n")
    # recieve client list from the other server
    while 1:
        client = raw((await reader.read(1024)).decode("utf8"))
        if client == f"END OF CLIENT LISTING FROM {rID}":
            break
        if client.lower() in G.servers[rID] or client.lower() in G.clientsConnected:
            writer.write(b"K Client rejected: Already exists\n")
            await writer.drain()
            continue
        writer.write(b"I added that client.\n")
        await writer.drain()
        G.msgs.append(log(f"{client} has connected from {rID}"))
        G.servers[rID].append(client.lower())
    G.clientsConnected.extend(G.servers[rID])
    try:
        while 1:
            try:
                rawMsg = await asyncio.wait_for(reader.read(967), 0.1)
                buffer = raw(rawMsg.decode("utf8"))
                match buffer[0]:
                    case "S":
                        G.msgs.extend([log(buffer[2:])])
                        writer.write(b"I Mmm... Blueberries\n")
                    case "I":
                        pass
                    case "+":
                        cName = buffer[2:]
                        if cName.lower() not in G.clientsConnected:
                            G.msgs.append(log(f"{cName} has connected from {rID}"))
                            G.servers[rID].append(cName.lower())
                            G.clientsConnected.append(cName.lower())
                            writer.write(b"I Mmm... Pineapples\n")
                        else:
                            writer.write(f"K {cName}\n".encode("utf8"))
                    case "-":
                        cName = buffer[2:]
                        G.msgs.append(log(f"{cName} has disconnected from {sName}"))
                        G.servers[rID].remove(cName.lower())
                        G.clientsConnected.remove(cName.lower())
                    case "M":
                        cName = buffer[2:].split("|", 1)[0]
                        message = buffer[2:].split("|", 1)[1]
                        G.msgs.append(log(f" {cName}: {message}"))
                        writer.write(
                            b"I Get these damn heretic ghost clients out of my store so i can buy my cult candles in peace."
                        )
                    case "A":
                        cName = buffer[2:].split("|", 1)[0]
                        message = buffer[2:].split("|", 1)[1]
                        G.msgs.append(log(f"* {cName} {message}"))
                        writer.write(b"I Mmm... Strawberries\n")
                    case "Q":
                        break
                    case "K":
                        cName = buffer[2:]
                        G.killList[cName.lower()] = True
                        writer.write(b"I Mmm... Blood\n")
                    case _:
                        writer.write(
                            f"S Your server is doing drugs over here, sending me bullshit messages man - {G.remoteID}, A fellow server\n".encode(
                                "utf8"
                            )
                        )
                await writer.drain()
            except TimeoutError:
                pass
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            for cName in G.servers[rID]:
                G.msgs.append(log(f"{cName}'s server is going down"))
                G.clientsConnected.remove(cName.lower())
            G.serverLinks -= 1
            G.servers.remove(rID)
            G.msgs.append(log(f"{rID} has de-linked from the network"))
    except (ConnectionResetError, BrokenPipeError):
        for cName in G.servers[rID]:
            G.msgs.append(log(f"{cName}'s server is going down"))
            try:
                G.clientsConnected.remove(cName.lower())
            except Exception:
                pass
        G.serverLinks -= 1
        G.servers.remove(rID)
        G.msgs.append(log(f"{rID} has de-linked from the network"))


async def runServer(address: str, port: int):
    global G
    server = await asyncio.start_server(handleClient, address, port)
    log(f"Listening on port {port}...")
    G.msgs.append(log("Server startup"))
    links = []
    for hostname, portNum in G.outboundLinks:
        links.append(connectServer(hostname, portNum))
    crash = False
    try:
        links.append(G.event.wait())
        await asyncio.gather(*links)
    except Exception:
        crash = True
        G.msgs.append(log("Server crash", level="FATAL")[1:])
        log("Shutting down from Exception")
        # TODO: Add format_exc here
    finally:
        if not crash:
            G.msgs.append(log("Server shutdown"))
        log("Kicking all clients as we go down")
        server.close()
        # server.abort_clients()
        if saveLogs:
            with open("cache.py", "w") as cache:
                cache.write(f"msgs = {G.msgs}\n")
            log("Saved logs, exiting now.")
        else:
            log("Not saving logs, exiting now.")


class ServerInterruptException(KeyboardInterrupt): ...


def interruptCatch(s, f):
    global G
    print()
    G.loop.call_soon_threadsafe(G.event.set)
    G.interruptCount += 1
    sys.tracebacklimit = 0
    raise ServerInterruptException from None


signal.signal(signal.SIGINT, interruptCatch)
asyncio.run(runServer(address, port))
