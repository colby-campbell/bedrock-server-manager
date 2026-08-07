from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
import os
import json


_CLI_COMMANDS_SIMPLE = [
    ':help', ':online', ':start', ':stop',
    ':restart', ':backup', ':list', ':mark',
    ':unmark', ':switch', ':check', ':update',
    ':exit', ':quit'
]

_CLI_COMMANDS_ARGS = {
    ':mark': {
        'args': ['<backup_name | latest | YYYY-MM-DD>'],
        'completions': [{'type': 'backups', 'extras': ['latest']}]
    },
    ':unmark':  {
        'args': ['<backup_name | latest | YYYY-MM-DD>'],
        'completions': [{'type': 'backups', 'extras': ['latest']}]
    },
    ':switch':  {
        'args': ['<backup_name>'],
        'completions': [{'type': 'backups'}]
    },
}

_TARGET_SELECTORS = ['@a', '@e', '@r']

_BEDROCK_COMMANDS_FILE = "bedrock_commands.json"


def load_commands():
    """Load the bedrock commands from a JSON file and return (commands dict, categories dict)."""
    commands_file = os.path.join(os.path.dirname(__file__), _BEDROCK_COMMANDS_FILE)
    try:
        with open(commands_file, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("commands", {}), data.get("categories", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}, {}


def _tokenize(text):
    """
    Tokenize the input text
    Args:
        text (str): The input text to tokenize
    Returns:
        tokens (list of str): The list of tokens in the input text
        trailing_space (bool): Whether the input text ends with a space
        ext_trailing_space (bool): Whether the input text ends with at least two spaces
    """
    tokens = text.split()
    trailing_space = text and text[-1] == ' '
    ext_trailing_space = text and text.endswith('  ')
    return tokens, trailing_space, ext_trailing_space


def _navigate(commands: dict, tokens, trailing_space):
    """
    Navigate the command tree given the current token list and whether the input ends with a space.
    Args:
        commands (dict): The command tree to navigate
        tokens (list of str): The list of tokens to navigate through
        trailing_space (bool): Whether the input ends with a space
    Returns:
        node (dict or None): The deepest matching command node, or None if the root command is not recognised
        arg_index (int): Positional index within node.completions for the next completion
        current_word (str): The partial token being typed ('' when trailing_space is True)
    """
    # If there are no tokens or the first token doesn't match any command, return None
    if not tokens or tokens[0] not in commands:
        return None, 0, ''

    # Grab the root command and get the remaining tokens
    node = commands[tokens[0]]
    remaining_tokens = tokens[1:]

    # If there is a trailing space, we are starting a new token and the current word is empty
    if trailing_space:
        args_to_process = remaining_tokens
        current_word = ''
    # If there is no trailing space, we are continuing the current token
    else:
        args_to_process = remaining_tokens[:-1] # Get rid of the last token?
        current_word = remaining_tokens[-1] if remaining_tokens else '' # The current word is the last token (if it exists)

    # Iterate through the tokens and navigate the command tree as far as possible, then navigate through the arguments to determine the current argument index
    arg_index = 0
    for token in args_to_process:
        children = node.get('children', {})
        if children and token in children:
            node = children[token]
            arg_index = 0
        else:
            arg_index += 1

    return node, arg_index, current_word


class BedrockCompleter(Completer):
    def __init__(self, commands, get_players, get_backups):
        self._commands = commands
        self._get_players = get_players
        self._get_backups = get_backups

    def _yield_completions(self, node, arg_index, current_word):
        """
        Yield completions for the current node and argument index, prioritizing child commands over argument completions.
        Args:
            node (dict): The current command node to yield completions for
            arg_index (int): Positional index within node.completions for the next completion
            current_word (str): The partial token being typed
        """
        # If there are argument completions, do those first
        comp_list = node.get('completions', [])
        if comp_list and arg_index < len(comp_list):
            # Grab the completion info for the current argument
            comp = comp_list[arg_index]
            candidates = []
            goto_children = False
            match comp['type']:
                case 'skip':
                    return # No completions for this argument
                case 'goto-children':
                    goto_children = True
                case 'boolean':
                    candidates = ['true', 'false']
                case 'players':
                    candidates = _TARGET_SELECTORS + self._get_players()
                case 'backups':
                    candidates = self._get_backups() + comp.get('extras', [])
                case 'enum':
                    candidates = comp['values']
            if not goto_children:
                # If any candidates start with the current word, yield a completion for it
                for value in candidates:
                    if value.lower().startswith(current_word.lower()):
                        yield Completion(value, start_position=-len(current_word))
                return
            else:
                # Otherwise complete with them the children
                children = node.get('children', {})
                if children:
                    for name in children:
                        if name.lower().startswith(current_word.lower()):
                            yield Completion(name, start_position=-len(current_word))

    def get_completions(self, document, _complete_event):
        """Yield completions for the current input."""
        # Grab text before the cursor and tokenize it
        text = document.text_before_cursor
        tokens, trailing_space, ext_trailing_space = _tokenize(text)

        # Don't attempt to complete if there is an extended trailing space
        if ext_trailing_space:
            return

        # CLI commands, hardcoded since they won't change and we don't want them removed from the JSON file
        if text.startswith(':'):
            word = tokens[0]
            # Argument completion
            if trailing_space or len(tokens) > 1:
                node, arg_index, current_word = _navigate(_CLI_COMMANDS_ARGS, tokens, trailing_space)
                if node is not None:
                    yield from self._yield_completions(node, arg_index, current_word)
            # Command name completion
            else:
                for cmd in _CLI_COMMANDS_SIMPLE:
                    if cmd.lower().startswith(word.lower()):
                        yield Completion(cmd, start_position=-len(word))
        # Bedrock command completion, loaded from JSON file
        else:
            # Argument completion
            if trailing_space or len(tokens) > 1:
                node, arg_index, current_word = _navigate(self._commands, tokens, trailing_space)
                if node is not None:
                    yield from self._yield_completions(node, arg_index, current_word)
            # Command name completion
            else:
                word = tokens[0] if tokens else ''
                for cmd in self._commands:
                    if cmd.lower().startswith(word.lower()):
                        yield Completion(cmd, start_position=-len(word))


class BedrockAutoSuggest(AutoSuggest):
    def __init__(self, commands):
        self._commands = commands

    def get_suggestion(self, _buffer, document):
        """Return a suggestion for the current input, or None if no suggestion is available."""

        # Everything the user has typed so far
        text = document.text_before_cursor
        # Don't suggest anything if the input is empty or just whitespace
        if not text.strip():
            return None

        # Tokenize the input and check
        tokens, trailing_space, ext_trailing_space = _tokenize(text)

        # If there is an extra trailing space, don't suggest anything
        if ext_trailing_space:
            return None

        # Hardcode CLI commands since they won't change and we don't want the user to remove them from the JSON file
        cmd_dict = _CLI_COMMANDS_ARGS if text.startswith(':') else self._commands

        # If the first token doesn't match any command, we can't suggest anything
        if tokens[0] not in cmd_dict:
            return None

        node, arg_index, current_word = _navigate(cmd_dict, tokens, trailing_space)

        # Grab the argument syntax for the current depth
        args_syntax = node.get('args', [])
        # If there is no argument syntax, don't suggest anything
        if not args_syntax:
            return None

        # If current_word, show the next argument, otherwise show the current argument
        remaining = args_syntax[arg_index + 1:] if current_word else args_syntax[arg_index:]
        if not remaining:
            return None
        prefix = ' ' if trailing_space else '  '
        return Suggestion(prefix + ' '.join(remaining))
