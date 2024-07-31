#!/usr/bin/python3
from datetime import datetime as dt, timezone as tz
from sys import stdout, stderr
from typing import Union


def log(
    message: str,
    level: str = "LOG",
    origin: str = None,
    time: Union[dt, str] = "now",
) -> bytes:
    if level in ["EXIT", "CRASH", "FATAL", "ERROR"]:
        stream = stderr
    else:
        stream = stdout
    if time == "now":
        dtime = dt.now(tz.utc)
        dtime.replace(tzinfo=tz.utc)
    elif type(time) == str:
        raise ValueError('Only "now" is an accepted string argument for time')
    elif type(time) == dt:
        dtime = time
    else:
        raise ValueError("time must either be a string or a dt object")
    time = dtime.strftime("%d-%m-%Y %H:%M:%S")
    log = ""
    if not "\n" in message:
        log = f"[{level}]{'['+origin+']' if origin else ''}[{time}] {message}"
        print(
            f"[{level}]{'['+origin+']' if origin else ''}[{time}] {message}",
            file=stream,
        )
    else:
        for line in message.split("\n"):
            log = (
                log + f"\r\n[{level}]{'['+origin+']' if origin else ''}[{time}] {line}"
            )
            print(
                f"[{level}]{'['+origin+']' if origin else ''}[{time}] {line}",
                file=stream,
            )
    return (log[5:] + "\r\n").encode("utf8")
