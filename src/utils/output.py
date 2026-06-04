import sys


class _ServerOutputMsg:
    """Class to represent a single output message with its source."""
    def __init__(self, msg, src):
        self.msg = msg
        self.src = src


class HandleServerOutput:
    """Class to handle server output messages."""
    def __init__(self):
        self.messages = []
        self.error = False

    def add_message(self, msg, src):
        for line in msg.splitlines():
            self.messages.append(_ServerOutputMsg(line, src))

    def add_error(self, msg, src):
        self.error = True
        for line in msg.splitlines():
            self.messages.append(_ServerOutputMsg(line, src))

    def print_messages(self):
        output_message = ["bedrock-server:"]
        prev_src = None
        future_src = None
        indent_lvl = 1
        for i, msg in enumerate(self.messages):
            # Look ahead to the next message's src
            if i < len(self.messages) - 1:
                future_src = self.messages[i + 1].src
            else:
                future_src = None
            if prev_src is None or msg.src != prev_src:
                if future_src is None or future_src != msg.src:
                    # Print src header and msg inline
                    output_message.append(f"{indent_lvl * '  '}{msg.src}:")
                    indent_lvl += 1
                    output_message.append(f"{indent_lvl * '  '}{msg.msg}")
                    indent_lvl -= 1
                else:
                    # Print src header and msg on separate lines
                    output_message.append(f"{indent_lvl * '  '}{msg.src}:")
                    indent_lvl += 1
                    output_message.append(f"{indent_lvl * '  '}{msg.msg}")
            else:
                # Print msg inline with previous message
                output_message.append(f"{indent_lvl * '  '}{msg.msg}")
                if future_src is None or future_src != msg.src:
                    indent_lvl -= 1
            prev_src = msg.src
        if self.error:
            print("\n".join(output_message), file=sys.stderr)
        else:
            print("\n".join(output_message))
