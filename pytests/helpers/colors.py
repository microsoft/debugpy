# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import


if True:
    # On Win32, colorama is not active when pytest-timeout dumps captured output
    # on timeout, and ANSI sequences aren't properly interpreted.
    # TODO: re-enable on Windows after enabling proper ANSI sequence handling:
    # https://docs.microsoft.com/en-us/windows/console/console-virtual-terminal-sequences
    #
    # Azure Pipelines doesn't support ANSI sequences at all.
    # TODO: re-enable on all platforms after adding Azure Pipelines detection.

    RESET = ''
    BLACK = ''
    BLUE = ''
    CYAN = ''
    GREEN = ''
    RED = ''
    WHITE = ''
    LIGHT_BLACK = ''
    LIGHT_BLUE = ''
    LIGHT_CYAN = ''
    LIGHT_GREEN = ''
    LIGHT_MAGENTA = ''
    LIGHT_RED = ''
    LIGHT_WHITE = ''
    LIGHT_YELLOW = ''


    def colorize_json(s):
        return s


    def color_repr(obj):
        return repr(obj)


else:
    from colorama import Fore
    from pygments import highlight, lexers, formatters, token


    # Colors that are commented out don't work with PowerShell.
    RESET = Fore.RESET
    BLACK = Fore.BLACK
    BLUE = Fore.BLUE
    CYAN = Fore.CYAN
    GREEN = Fore.GREEN
    # MAGENTA = Fore.MAGENTA
    RED = Fore.RED
    WHITE = Fore.WHITE
    # YELLOW = Fore.YELLOW
    LIGHT_BLACK = Fore.LIGHTBLACK_EX
    LIGHT_BLUE = Fore.LIGHTBLUE_EX
    LIGHT_CYAN = Fore.LIGHTCYAN_EX
    LIGHT_GREEN = Fore.LIGHTGREEN_EX
    LIGHT_MAGENTA = Fore.LIGHTMAGENTA_EX
    LIGHT_RED = Fore.LIGHTRED_EX
    LIGHT_WHITE = Fore.LIGHTWHITE_EX
    LIGHT_YELLOW = Fore.LIGHTYELLOW_EX


    color_scheme = {
        token.Token: ('white', 'white'),
        token.Punctuation: ('', ''),
        token.Operator: ('', ''),
        token.Literal: ('brown', 'brown'),
        token.Keyword: ('brown', 'brown'),
        token.Name: ('white', 'white'),
        token.Name.Constant: ('brown', 'brown'),
        token.Name.Attribute: ('brown', 'brown'),
        # token.Name.Tag: ('white', 'white'),
        # token.Name.Function: ('white', 'white'),
        # token.Name.Variable: ('white', 'white'),
    }

    formatter = formatters.TerminalFormatter(colorscheme=color_scheme)
    json_lexer = lexers.JsonLexer()
    python_lexer = lexers.PythonLexer()


    def colorize_json(s):
        return highlight(s, json_lexer, formatter).rstrip()


    def color_repr(obj):
        return highlight(repr(obj), python_lexer, formatter).rstrip()


