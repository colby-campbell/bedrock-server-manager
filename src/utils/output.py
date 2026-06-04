import sys
from itertools import groupby
from dataclasses import dataclass


@dataclass
class _ServerOutputMsg:
    msg: str
    src: str


class ServerOutput:
    def __init__(self):
        self.messages: list[_ServerOutputMsg] = []
        self.error = False

    def add_message(self, msg, src):
        for line in msg.splitlines():
            self.messages.append(_ServerOutputMsg(line, src))

    def add_error(self, msg, src):
        self.error = True
        for line in msg.splitlines():
            self.messages.append(_ServerOutputMsg(line, src))

    def print_messages(self):
        lines = ["bedrock-server:"]
        for src, group in groupby(self.messages, key=lambda m: m.src):
            lines.append(f"  {src}:")
            for msg in group:
                lines.append(f"    {msg.msg}")

        output = "\n".join(lines)
        print(output, file=sys.stderr if self.error else sys.stdout)
