# Python-talk (working name)

## A few quick notes:

Hello! Thanks for taking the tine to look at my little chat program!

Since the client for this isn't done yet, you'll need to use other tools to connect to the server (such as `nc`).

If you'd like to run your own server instance, that's great! I encourage you to do so!

The packages from pyproject.toml will only be required in the future by the client, not the server! This means you need nothing but python 3 (.11? might be .12) and the code to be able to run a server.

## Arguments:

The server accepts a good chunk of args to be passed when it boots, for various control options. However, none are required! You can just run it as-is, and it'll work just fine.

Valid args:
|Argument(s)|Function|
|-|-|
|`-?`/`-h`/`--help`|Shows the help for CLI args, much like the list here, but less verbose|
|`-l`/`--no-logs`|Disables the server saving logs when it shuts down. This does *NOT* disable logging to console.|
|`-c`/`--no-cache`|The server always tries to load cached messages on boot, this way however it will dump those before the server starts serving to clients|
|`-p=<number>`/`--port=<number>`|Specifies the port for the server to run on, defaults to `65048`.|
|`--address=<IP address>`|Specifies what address to listen on, defaults to `0.0.0.0` (all addresses)|
|`--hostname=<string>`|Sets the hostname for the server to use when communicating with other servers, defaults to the hostname of the system that it is run on.|
|`--link=<host>:<port>`|Establishes a S2S link with `<host>` on port `<port>` when the server is finsihed booting, e.g. `--link=example.com:29277`. This is the only argument may be specified multiple times to establish multiple server links.|

For any arg besides `--link`, if specified multiple times, the last time it is specified takes priority over earlier specifications.

## Commands:

When connected to the server, there are a few availiable commands as well! These are as follows:
|Command(s)|Function|
|-|-|
|`/h`/`/help`|Shows an in-"client" listing of valid commands|
|`/me <action>`|Sends a message as if you did an action, e.g. "* Firepup ate some fire"|
|`/mes <action>`|Sends a message as if your `<x>` did an action, e.g. "* Firepup's cat laid on the couch"|
|`/afk [reason]`|States that the user is AFK Accepts an optional reason. e.g. "* Firepup is afk to [reason]" or "* Firepup is afk"|
|`/back`|(Companion to `/afk`) States that the user is back. e.g. "* Firepup is back"|
|`/quit`|Causes the server to terminate your connection.|

## Future Plans:

1. Stress-test the server, get bug reports and fix them, to get the server as stable as possible.
2. IRC client support. This will probably require at least a few major changes, but it'd be a nice thing to support.
3. Stress-test IRC support.
4. Figure out a better name for this program. It's very vague right now.
5. (Wow this is low on my priority list) Make an actual client to go along with the server, not everyone is willing to run random commands to link to a random server.
6. Stress-test the client program.
7. Somehow bundle the client as a stand-alone released executable, for linux and windows, to make it easier to connect to servers!
8. Dunno! We'll see where the future takes me.

This is, of course, subject to change at any time, but it's my current rough plan for the future of this code.

## How to (in current state) run the code:

This is, of course, not the only way to get and run the code, but this is how I personally recommend doing it:
1. `git clone https://git.h.hackclub.app/Firepup650/python-talk.git`
2. `cd python-talk`
3. `python3 server.py [args, if any]`
4. Done! You've got the server up and running!

The current "client" for the server is just netcat (`nc`), and you can connect to the server with `nc <host> <port>`, for example, if you had a server running on `example.com` on the standard port, you'd run `nc example.com 65048`.

## Closing thoughts:

Feel free to suggest anything you'd like to see implemented into this little project of mine, and PRs are even more welcome/appreciated!

If you'd like to link up with what I'm currently considering the "hub" instance, let me know directly! I'm always happy to have a bigger network! ;)

Found a bug? Reach out to me, or file it in a new issue here (or work on it yourself, and PR it ;P) and I'll get around to reviewing and fixing fairly quickly, hopefullh.
