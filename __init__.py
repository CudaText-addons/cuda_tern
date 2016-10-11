import os
import subprocess
import re
import urllib.request
import json
import collections
import functools
import itertools

from cudatext import *
import cudatext_cmd


CUDA_LEXER_SYMBOL = "Symbol"
CUDA_LEXER_IDENTIFIER = "Identifier"

LOCALHOST = "127.0.0.1" if os.name=='nt' else "localhost"
LINE_GOTO_OFFSET = 5 #lines from top

TERN_TIMEOUT = 3 #seconds
TERN_PROCESS = None
TERN_PORT = None


def do_start_server():

    global TERN_PROCESS
    global TERN_PORT
    
    try:
        TERN_PROCESS = subprocess.Popen(
            ("tern", "--persistent", "--ignore-stdin", "--no-port-file"),
            stdout=subprocess.PIPE,
        )
    except:
        msg_box('Cannot start Tern process.\nMake sure Tern.js and Node.js are installed.', MB_OK+MB_ICONERROR)
        return

    s = TERN_PROCESS.stdout.readline().decode("utf-8")
    match = re.match("Listening on port (\\d+)", s)
    if match:

        TERN_PORT = int(match.group(1))

    print('Started Tern (port %d)' % TERN_PORT)
    

def do_request(data):
    
    global TERN_PORT
    global TERN_TIMEOUT
        
    if not TERN_PORT:
        return

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = str.format("http://{}:{}/", LOCALHOST, TERN_PORT)
    s = json.dumps(data).encode("utf-8")
    req = opener.open(url, s, timeout=TERN_TIMEOUT)
    return json.loads(req.read().decode("utf-8"))


def do_goto_file(filename, num_line, num_col):

    if not os.path.isfile(filename):
        return

    file_open(filename)
    ed.set_prop(PROP_LINE_TOP, str(max(0, num_line-LINE_GOTO_OFFSET)))
    ed.set_caret(num_col, num_line)

    msg_status('Go to file: '+filename)
    print('Go to "%s", Line %d' % (filename, num_line+1))


do_start_server()

Caret = collections.namedtuple("Caret", "sx sy ex ey")


def normalize_caret(sx, sy, ex, ey):

    if ex == -1:

        ex, ey = sx, sy

    return Caret(ex, ey, sx, sy)


def prevent_multiply_carrets(f):

    @functools.wraps(f)
    def wrapped(self, ed_self):

        if len(ed_self.get_carets()) == 1:

            return f(self, ed_self)

    return wrapped


def unpack_editor_info(f):

    @functools.wraps(f)
    def wrapped(self, ed_self):

        caret, *_ = ed_self.get_carets()
        filename = ed_self.get_filename()
        text = ed_self.get_text_all()
        return f(self, ed_self, filename, text, normalize_caret(*caret))

    return wrapped


class Command:

    @prevent_multiply_carrets
    @unpack_editor_info
    def on_complete(self, ed_self, filename, text, caret):

        result = self.get_completes(filename, text, caret)
        if not result:

            return

        lx = result["start"]["ch"]
        rx = result["end"]["ch"]
        lines = []
        default = collections.ChainMap(dict(type="", name="", doc=""))
        fmt = "{type}|{name}|\t{doc}"
        for complete in map(default.new_child, result["completions"]):

            lines.append(str.format(fmt, **complete))

        ed_self.complete(str.join("\n", lines), caret.ex - lx, rx - caret.ex)
        return True

    @prevent_multiply_carrets
    @unpack_editor_info
    def on_goto_def(self, ed_self, filename, text, caret):

        result = self.get_definition(filename, text, caret)
        if result:
            do_goto_file(
                result["file"], 
                result["start"]["line"], 
                result["start"]["ch"],
            )        
        return True

    @prevent_multiply_carrets
    @unpack_editor_info
    def on_func_hint(self, ed_self, filename, text, caret):

        tokens = collections.deque()
        for i in itertools.count():

            token = ed_self.get_token(TOKEN_INDEX, i, 0)
            if token is None:
            
                break
            
            (sx, sy), (ex, ey), *_ = token
            tokens.append(token)
            if caret.sy == sy and sx <= caret.sx <= ex:

                break

            if (caret.ey, caret.ex) < (sy, sx):

                return

        depth = 1
        while tokens:

            (sx, sy), (ex, ey), s, token_type = tokens.pop()
            if token_type == CUDA_LEXER_SYMBOL:

                if s == "(":

                    depth -= 1

                elif s == ")":

                    depth += 1

            elif token_type == CUDA_LEXER_IDENTIFIER and depth == 0:

                break

        else:

            return

        result = self.get_calltip(filename, text, Caret(sx, sy, ex, ey))
        if "name" in result:

            hint = result["type"]
            if hint.startswith("fn("):

                hint = result["name"] + hint[2:]

            msg_status_alt(hint, 10)

    def get_completes(self, filename, text, caret):

        return do_request(dict(
            files=[dict(
                type="full",
                name=filename,
                text=text,
            )],
            query=dict(
                type="completions",
                file=filename,
                end=dict(
                    line=caret.ey,
                    ch=caret.ex,
                ),
                lineCharPositions=True,
                types=True,
                docs=True,
            ),
        ))

    def get_definition(self, filename, text, caret):

        return do_request(dict(
            files=[dict(
                type="full",
                name=filename,
                text=text,
            )],
            query=dict(
                type="definition",
                file=filename,
                end=dict(
                    line=caret.ey,
                    ch=caret.ex,
                ),
                start=dict(
                    line=caret.sy,
                    ch=caret.sx,
                ),
                lineCharPositions=True,
            ),
        ))

    def get_calltip(self, filename, text, caret):

        return do_request(dict(
            files=[dict(
                type="full",
                name=filename,
                text=text,
            )],
            query=dict(
                type="type",
                file=filename,
                end=dict(
                    line=caret.ey,
                    ch=caret.ex,
                ),
                start=dict(
                    line=caret.sy,
                    ch=caret.sx,
                ),
                lineCharPositions=True,
                preferFunction=True,
            ),
        ))

