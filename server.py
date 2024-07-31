#!/usr/bin/python3
import os, sys, asyncio, re, signal, socket
from platform import uname
from traceback import format_exc
from logs import log


class LinkDownError(Exception): ...


class FailedLinkError(Exception): ...


class Globals: ...


TimeoutErrors = (TimeoutError, asyncio.exceptions.TimeoutError)
DisconnectErrors = (
    ConnectionResetError,
    BrokenPipeError,
    IndexError,
    UnicodeDecodeError,
    *TimeoutErrors,
)
G = Globals()
G.uniqueClients = 0
G.servers = {}
G.clientsConnected = {}
port = 65048
G.msgs = []
G.remoteID = uname().node
G.event = asyncio.Event()
G.loop = asyncio.get_event_loop()
G.interruptCount = 0
G.killList = {}
G.outboundLinks = []
G.S2SLogs = []
G.cwlgd = False
G.NUL = "|"
saveLogs = True
address = "::"
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
    filename = sys.argv.pop(0)  # Ignore the filename
    for arg in sys.argv:
        if arg.startswith("--port") or arg.startswith("-p"):
            port = int(arg.lstrip("-port="))
        elif arg in ["-c", "--no-cache"]:
            log("Explicitly erasing cached messages")
            G.msgs = []
        elif arg in ["-?", "-h", "--help"]:
            filename = filename if filename.startswith("./") else "python3 " + filename
            print(
                f"""{filename} <args>
All arguments are optional!
All areguments are *expected* to only be specified once, if it appears mutliple times, the last one takes priority.
The exception to the above rule is `--link`, since you could want to link to multiple other servers.
Accepted arguments:
-?, -h, --help              - Triggers this help dialog
-l, --no-logs               - Disables the saving of logs when the server shuts down
-c, --no-cache              - Disables the loading of cached messages when the server boots
-p<number>, --port=<number> - Sets the port for the server to use, defaults to `65048`
--link=<host>:<port>        - Establishes an S2S link with remote server <host> on port <port> when the server starts up
--hostname=<string>         - Sets the hostname for this server to use when talking to other servers. Defaults to the current system's hostname (limit of 16 chars)
--address=<IP>              - Sets the IP to listen on, defaults to all addresses (0.0.0.0)
--cwlgd                     - Crashes the server when outbound links go down

Examples:
{filename} --hostname=Fun-chat --link=chat.example.com:65048 --port=92628
{filename} --no-logs --no-cache
{filename} --address=127.0.0.1 -l -p=7288"""
            )
            exit(0)
        elif arg in ["-l", "--no-logs"]:
            log("Explicitly disabling saving of logs!")
            saveLogs = False
        elif arg.startswith("--link"):
            G.outboundLinks.append((arg[7:].split(":")[0], int(arg.split(":")[1])))
        elif arg.startswith("--hostname"):
            G.remoteID = arg[11:]
            if not G.remoteID or len(G.remoteID) > 16:
                raise ValueError
        elif arg.startswith("--address"):
            address = arg[10:]
        elif arg.startswith("--cwlgd"):
            G.cwlgd = True
            log("Server will crash when outbound links go down!", "WARN")
        else:
            log(f"Unrecognized argument {arg}!", "WARN")
except Exception:
    sys.tracebacklimit = 0
    raise ValueError("Invalid arguments. Please refer to --help for usage.") from None

if not saveLogs:
    G.msgs.append(
        b"[00-00-0000 00:00:00] Notice: Logging is disabled on this server instance!\r\n"
    )
if len(G.remoteID) > 16:
    G.remoteID = G.remoteID[:15]


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
        name = ""
        global G
        writer.write(b"Please identify yourself. Nick limit is 20 chars.\r\n")
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
        except TimeoutErrors:
            pass
        if not name:
            writer.write(b"Nice try. Actually set a nick.\r\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return
        if name.lower() in G.clientsConnected:
            writer.write(f"Nick ({name}) in use\r\n".encode("utf8"))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return
        if not name.startswith("S2S-"):
            G.clientsConnected[name.lower()] = G.remoteID
            msgIndex = 0
            G.uniqueClients += 1
            G.msgs.extend([log(f"{name} has connected to the server.")])
            G.S2SLogs.append(("+", name, G.remoteID))
            while 1:
                try:
                    buffer = await asyncio.wait_for(reader.read(967), 0.1)
                    request = raw(buffer.decode("utf8"))
                    response = None
                    if request.startswith("/mes "):
                        response = log(f"* {name}'s {request[5:]}")
                        G.S2SLogs.append(("A", (name + "'s", request[5:]), G.remoteID))
                    elif request.startswith("/me "):
                        response = log(f"* {name} {request[4:]}")
                        G.S2SLogs.append(("A", (name, request[4:]), G.remoteID))
                    elif request.startswith("/h"):
                        writer.write(
                            b"""Command List:\r
/me <action>  - Sends a special message so it looks like you did <action>\r
/mes <action> - Same as /me, but adds a 's onto your nick\r
/afk [reason] - Optional reason, short hand for `/me is afk [to [reason]]`\r
/h, /help     - Triggers this command listing\r
/back         - Shorthand for `/me is back`\r
/stats        - Sends you some server stats\r
/quit         - Disconnects you from the server\r\n"""
                        )
                        await writer.drain()
                    elif request.startswith("/stats"):
                        writer.write(
                            f"""Server stats:\r
Linked servers:    {len(G.servers)}\r
Connected clients: {G.uniqueClients}\r
Total Clients:     {len(G.clientsConnected)}\r
Messages sent:     {len(G.msgs)}\r
\r
Please note that this is not network level statistics.\r\n""".encode(
                                "utf8"
                            )
                        )
                        await writer.drain()
                    elif request.startswith("/quit"):
                        break
                    elif request.startswith("/afk"):
                        if len(request) > 5:
                            response = log(f"* {name} is afk to {request[5:]}")
                            G.S2SLogs.append(
                                ("A", (name, f"is afk to {request[5:]}"), G.remoteID)
                            )
                        else:
                            response = log(f"* {name} is afk")
                            G.S2SLogs.append(("A", (name, "is afk"), G.remoteID))
                    elif request.startswith("/back"):
                        response = log(f"* {name} is back")
                        G.S2SLogs.append(("A", (name, "is back"), G.remoteID))
                    elif request:
                        response = log(f"  {name}: {request}")
                        G.S2SLogs.append(("M", (name, request), G.remoteID))
                    if response:
                        G.msgs.append(response)
                except TimeoutErrors:
                    pass
                if msgIndex < len(G.msgs):
                    writer.writelines(G.msgs[msgIndex:])
                    await writer.drain()
                    msgIndex = len(G.msgs)
                if name.lower() in G.killList and G.killList[name.lower()]:
                    writer.write(b"Your client has been killed by the server\r\n")
                    G.killList[name.lower()] = False
                    break
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            G.uniqueClients -= 1
            G.msgs.append(log(f"{name} has disconnected from the server."))
            del G.clientsConnected[name.lower()]
            G.S2SLogs.append(("-", name, G.remoteID))
        else:  # This is... probably a server?
            sName = name[4:]  # Trim off the S2S label
            if (
                G.servers.get(sName, False) != False
            ):  # Have to explicitly check, empty list is False, but does not == False
                writer.close()
                await writer.wait_closed()
                return  # Server is already "linked", drop the connection
            if G.remoteID == sName or not sName:  # Hey! you can't *also* be ***me***!
                writer.close()
                await writer.wait_closed()
                return  # drop "us"
            G.msgs.append(log(f"{sName} has linked to the network"))
            G.servers[sName] = {}
            msgIndex = 0
            writer.write(b"I am awaiting your client listing.\r\n")
            while 1:
                client = raw((await reader.read(1024)).decode("utf8"))
                if client == f"END OF CLIENT LISTING FROM {sName}":
                    break
                if (
                    client.lower() in G.servers[sName]
                    or client.lower() in G.clientsConnected
                ):
                    writer.write(b"K Client rejected: Already exists\r\n")
                    await writer.drain()
                    continue
                writer.write(b"I added that client.\r\n")
                await writer.drain()
                G.msgs.append(log(f"{client} has connected from {sName}"))
                G.servers[sName][client.lower()] = False
                G.S2SLogs.append(("+", client, sName))
            writer.write(f"{G.remoteID}\r\n".encode("utf8"))
            await writer.drain()
            await reader.read(1024)
            for client in G.clientsConnected:
                writer.write(f"{client}\r\n".encode("utf8"))
                await writer.drain()
                resp = raw((await reader.read(1024)).decode("utf8"))
                if resp.startswith("K"):
                    if G.clientsConnected[client] == G.remoteID:
                        G.killList[client] = True
                    else:
                        G.servers[G.clientsConnected[client]][client] = True
            writer.write(f"END OF CLIENT LISTING FROM {G.remoteID}\r\n".encode("utf8"))
            await writer.drain()
            for client in G.servers[sName]:
                G.clientsConnected[client] = sName
            msgInd = len(G.S2SLogs)
            while 1:
                try:
                    rawMsg = await asyncio.wait_for(reader.read(967), 0.1)
                    buffer = raw(rawMsg.decode("utf8"))
                    match buffer[0]:
                        case "S":  # Server notice
                            G.msgs.extend([log(buffer[2:])])
                            writer.write(b"I Mmm... Blueberries\r\n")
                        case "I":
                            pass
                        case "+":
                            cName = buffer[2:]
                            if cName.lower() not in G.clientsConnected:
                                G.msgs.append(
                                    log(f"{cName} has connected from {sName}")
                                )
                                G.servers[sName][cName.lower()] = False
                                G.clientsConnected[cName.lower()] = sName
                                G.S2SLogs.append(("+", cName, sName))
                                writer.write(b"I Mmm... Pineapples\r\n")
                            else:
                                writer.write(f"K {cName}\r\n".encode("utf8"))
                        case "-":
                            cName = buffer[2:]
                            if G.clientsConnected.get(cName.lower(), None) == sName:
                                G.msgs.append(
                                    log(f"{cName} has disconnected from {sName}")
                                )
                                del G.servers[sName][cName.lower()]
                                del G.clientsConnected[cName.lower()]
                                G.S2SLogs.append(("-", cName, sName))
                                writer.write(b"I Mmm... Bananas\r\n")
                            else:
                                writer.write(
                                    f"S Your server is LYING about who is connected to it. - {G.remoteID}, a fellow server\r\n".encode(
                                        "utf8"
                                    )
                                )
                        case "M":
                            cName = buffer[2:].split(G.NUL, 1)[0]
                            message = buffer[2:].split(G.NUL, 1)[1]
                            G.msgs.append(log(f"  {cName}: {message}"))
                            G.S2SLogs.append(("M", (cName, message), sName))
                            writer.write(
                                b"I Get these damn heretic ghost clients out of my store so i can buy my cult candles in peace.\r\n"
                            )
                        case "A":
                            cName = buffer[2:].split(G.NUL, 1)[0]
                            message = buffer[2:].split(G.NUL, 1)[1]
                            G.msgs.append(log(f"* {cName} {message}"))
                            G.S2SLogs.append(("A", (cName, message), sName))
                            writer.write(b"I Mmm... Strawberries\r\n")
                        case "Q":
                            break
                        case "K":
                            cName = buffer[2:]
                            if not G.clientsConnected.get(cName.lower(), False):
                                pass  # They don't exist, safe to ignore
                            elif G.clientsConnected[cName.lower()] == G.remoteID:
                                G.killList[cName.lower()] = True
                            else:
                                G.servers[G.clientsConnected[cName.lower()]][
                                    cName.lower()
                                ] = True
                            writer.write(b"I Mmm... Blood\r\n")
                        case _:
                            writer.write(
                                f"S Your server is doing drugs over here, sending me bullshit messages man - {G.remoteID}, A fellow server\r\n".encode(
                                    "utf8"
                                )
                            )
                            log(
                                f"Recieved invalid message ({buffer}) from {sName}",
                                "WARN",
                            )
                    await writer.drain()
                except TimeoutErrors:
                    pass
                if any(G.servers[sName].values()):
                    for name in G.servers[sName]:
                        if G.servers[sName][name]:
                            writer.write(f"K {name}\r\n".encode("utf8"))
                            await writer.drain()
                            G.servers[sName][name] = False
                while msgInd < len(G.S2SLogs):
                    type, data, server = G.S2SLogs[msgInd]
                    # match-case on type
                    if server != sName:
                        match type:
                            case "A":
                                nick, msg = data
                                writer.write(f"A {nick}{G.NUL}{msg}\r\n".encode("utf8"))
                            case "M":
                                nick, msg = data
                                writer.write(f"M {nick}{G.NUL}{msg}\r\n".encode("utf8"))
                            case "+":
                                writer.write(f"+ {data}\r\n".encode("utf8"))
                            case "-":
                                writer.write(f"- {data}\r\n".encode("utf8"))
                            case _:
                                pass
                    await writer.drain()
                    msgInd += 1
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            for cName in G.servers[sName]:
                G.msgs.append(log(f"{cName}'s server is going down"))
                G.S2SLogs.append(("-", cName, sName))
                del G.clientsConnected[cName.lower()]
            del G.servers[sName]
            G.msgs.append(log(f"{sName} has de-linked from the network"))
    except DisconnectErrors:
        if not name:
            return
        if not name.startswith("S2S-"):
            G.uniqueClients -= 1
            G.msgs.append(log(f"{name} has disconnected from the server."))
            G.S2SLogs.append(("-", name, G.remoteID))
            del G.clientsConnected[name.lower()]
        else:
            for cName in G.servers[name[4:]]:
                G.msgs.append(log(f"{cName}'s server is going down"))
                try:
                    del G.clientsConnected[cName.lower()]
                    G.S2SLogs.append(("-", cName, name[4:]))
                except Exception:  # Crash during connection sequence?
                    pass
            del G.servers[name[4:]]
            G.msgs.append(log(f"{name[4:]} has de-linked from the network"))
    except Exception:
        Err = format_exc()
        for line in Err.split("\r\n"):
            log(line, "ERROR")


async def connectServer(hostname: str, port: int):
    global G
    try:
        reader, writer = await asyncio.open_connection(hostname, port)
        await reader.read(1024)
        writer.write(f"S2S-{G.remoteID}\r\n".encode("utf8"))
        await writer.drain()
        await reader.read(1024)
        for client in G.clientsConnected:
            writer.write(f"{client}\r\n".encode("utf8"))
            await writer.drain()
            resp = raw((await reader.read(1024)).decode("utf8"))
            if resp.startswith("K"):
                if G.clientsConnected[client] == G.remoteID:
                    G.killList[client] = True
                else:
                    G.servers[G.clientsConnected[client]][client] = True
        writer.write(f"END OF CLIENT LISTING FROM {G.remoteID}\r\n".encode("utf8"))
        await writer.drain()
        rID = raw((await reader.read(16)).decode("utf8"))
        try:
            await asyncio.wait_for(reader.read(1024), 0.1)
        except TimeoutErrors:
            pass
        if G.servers.get(rID, False) != False:
            writer.close()
            await writer.wait_closed()
            return
        if G.remoteID == rID or not rID:
            writer.close()
            await writer.wait_closed()
            return
        G.msgs.append(log(f"{rID} has linked to the network"))
        G.servers[rID] = {}
        writer.write(b"I recieved your remote ID, now awaiting client listing\r\n")
        await writer.drain()
        # recieve client list from the other server
        while 1:
            client = raw((await reader.read(1024)).decode("utf8"))
            if client == f"END OF CLIENT LISTING FROM {rID}":
                break
            if client.lower() in G.servers[rID] or client.lower() in G.clientsConnected:
                writer.write(b"K Client rejected: Already exists\r\n")
                await writer.drain()
                continue
            writer.write(b"I added that client.\r\n")
            await writer.drain()
            G.msgs.append(log(f"{client} has connected from {rID}"))
            G.servers[rID][client.lower()] = False
        for client in G.servers[rID]:
            G.clientsConnected[client] = rID
        msgInd = len(G.S2SLogs)
        try:
            while 1:
                try:
                    rawMsg = await asyncio.wait_for(reader.read(1024), 0.1)
                    buffer = raw(rawMsg.decode("utf8"))
                    match buffer[0]:
                        case "S":
                            G.msgs.extend([log(buffer[2:])])
                            writer.write(b"I Mmm... Blueberries\r\n")
                        case "I":
                            pass
                        case "+":
                            cName = buffer[2:]
                            if cName.lower() not in G.clientsConnected:
                                G.msgs.append(log(f"{cName} has connected from {rID}"))
                                G.S2SLogs.append(("+", cName, rID))
                                G.servers[rID][cName.lower()] = False
                                G.clientsConnected[cName.lower()] = rID
                                writer.write(b"I Mmm... Pineapples\r\n")
                            else:
                                writer.write(f"K {cName}\r\n".encode("utf8"))
                        case "-":
                            cName = buffer[2:]
                            if G.clientsConnected.get(cName.lower(), None) == rID:
                                G.msgs.append(
                                    log(f"{cName} has disconnected from {rID}")
                                )
                                del G.servers[rID][cName.lower()]
                                del G.clientsConnected[cName.lower()]
                                G.S2SLogs.append(("-", cName, rID))
                            else:
                                writer.write(
                                    f"S Your server is LYING about who is connected to it. - {G.remoteID}, a fellow server\r\n".encode(
                                        "utf8"
                                    )
                                )
                        case "M":
                            cName = buffer[2:].split(G.NUL, 1)[0]
                            message = buffer[2:].split(G.NUL, 1)[1]
                            G.msgs.append(log(f"  {cName}: {message}"))
                            G.S2SLogs.append(("M", (cName, message), rID))
                            writer.write(
                                b"I Get these damn heretic ghost clients out of my store so i can buy my cult candles in peace.\r\n"
                            )
                        case "A":
                            cName = buffer[2:].split(G.NUL, 1)[0]
                            message = buffer[2:].split(G.NUL, 1)[1]
                            G.S2SLogs.append(("A", (cName, message), rID))
                            G.msgs.append(log(f"* {cName} {message}"))
                            writer.write(b"I Mmm... Strawberries\r\n")
                        case "Q":
                            break
                        case "K":
                            cName = buffer[2:]
                            if not G.clientsConnected.get(cName.lower(), False):
                                pass  # They don't exist, safe to ignore
                            elif G.clientsConnected[cName.lower()] == G.remoteID:
                                G.killList[cName.lower()] = True
                            else:
                                G.servers[G.clientsConnected[cName.lower()]][
                                    cName.lower()
                                ] = True
                            writer.write(b"I Mmm... Blood\r\n")
                        case _:
                            writer.write(
                                f"S Your server is doing drugs over here, sending me bullshit messages man - {G.remoteID}, A fellow server\r\n".encode(
                                    "utf8"
                                )
                            )
                            log(
                                f"Recieved invalid message ({buffer}) from {rID}",
                                "WARN",
                            )
                    await writer.drain()
                except TimeoutErrors:
                    pass
                if any(G.servers[rID].values()):
                    for name in G.servers[rID]:
                        if G.servers[rID][name]:
                            writer.write(f"K {name}\r\n".encode("utf8"))
                            await writer.drain()
                            G.servers[rID][name] = False
                while msgInd < len(G.S2SLogs):
                    type, data, server = G.S2SLogs[msgInd]
                    if server != rID:
                        match type:
                            case "A":
                                nick, msg = data
                                writer.write(f"A {nick}{G.NUL}{msg}\r\n".encode("utf8"))
                            case "M":
                                nick, msg = data
                                writer.write(f"M {nick}{G.NUL}{msg}\r\n".encode("utf8"))
                            case "+":
                                writer.write(f"+ {data}\r\n".encode("utf8"))
                            case "-":
                                writer.write(f"- {data}\r\n".encode("utf8"))
                            case _:
                                pass
                    await writer.drain()
                    msgInd += 1
            if G.cwlgd:
                raise LinkDownError
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            for cName in G.servers[rID]:
                G.msgs.append(log(f"{cName}'s server is going down"))
                del G.clientsConnected[cName.lower()]
            del G.servers[rID]
            G.msgs.append(log(f"{rID} has de-linked from the network"))
        except DisconnectErrors:
            if G.cwlgd:
                raise LinkDownError
            for cName in G.servers[rID]:
                G.msgs.append(log(f"{cName}'s server is going down"))
                try:
                    del G.clientsConnected[cName.lower()]
                except Exception:
                    pass
            del G.servers[rID]
            G.msgs.append(log(f"{rID} has de-linked from the network"))
    except OSError as E:
        log("OSError: " + str(E), "ERROR")
        if G.cwlgd:
            raise FailedLinkError
    except Exception:
        Err = format_exc()
        for line in Err.split("\r\n"):
            log(line, "ERROR")
        raise FailedLinkError


async def runServer(address: str, port: int):
    global G
    sock = None
    try:
        if ":" in address:
            INET = socket.AF_INET6
        else:
            INET = socket.AF_INET
        sock = socket.socket(INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Reuse socket
        sock.bind((address, port))
    except OSError as E:
        if E.errno != 97 or address != '::':
            raise E
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Reuse socket
        sock.bind(('0.0.0.0', port))
    server = await asyncio.start_server(handleClient, sock=sock)
    log(f"Listening on port {port}...")
    G.msgs.append(log("Server startup"))
    links = []
    for hostname, portNum in G.outboundLinks:
        links.append(connectServer(hostname, portNum))
    crash = False
    try:
        links.append(G.event.wait())
        await asyncio.gather(*links)
    except LinkDownError:
        G.msgs.append(log("Lost a server link, going down", "FATAL")[1:])
        crash = True
    except FailedLinkError:
        G.msgs.append(log("Failed to establish a server link, going down", "FATAL")[1:])
    except Exception:
        crash = True
        G.msgs.append(log("Server crash", "FATAL")[1:])
        log("Shutting down from Exception", "FATAL")
        Err = format_exc()
        for line in Err.split("\r\n"):
            log(line, "ERROR")
    finally:
        if not crash:
            G.msgs.append(log("Server shutdown"))
        log("Kicking all clients as we go down")
        server.close()
        # server.abort_clients()
        if saveLogs:
            with open("cache.py", "w") as cache:
                cache.write(f"msgs = {G.msgs}\r\n")
            log("Saved logs, exiting now.")
        else:
            log("Not saving logs, exiting now.")
        sock.close()


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
