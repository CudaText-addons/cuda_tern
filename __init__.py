import os
import re
import json
import subprocess
import urllib.request
import collections
import itertools

from cudatext import *
import cudatext_cmd


CUDA_LEXER_SYMBOL = "Symbol"
CUDA_LEXER_IDENTIFIER = "Identifier"

LOCALHOST = "127.0.0.1" if os.name == "nt" else "localhost"
LINE_GOTO_OFFSET = 5  # lines from top

TERN_TIMEOUT = 3  # seconds
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
        msg_box("Cannot start Tern process.\nMake sure Tern.js and Node.js "
                "are installed.",
                MB_OK + MB_ICONERROR)
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

    if not filename:
        return
    #print('Goto params: "%s", %d:%d' % (filename, num_line, num_col))

    # Tern gives "test/reload.js" while we edit "reload.js" in "test"
    dirname = get_project_dir()
    if dirname:
        filename = os.path.join(dirname, filename)

    if not os.path.isfile(filename):
        msg_box(
            'Tern: cannot find file:\n'+filename+'\n\n'
            'Install "Project Manager" plugin, and create/open some project. '
            'Dir of this CudaText project file will be used as dir of JS project.',
            MB_OK+MB_ICONINFO
        )
        return

    file_open(filename)
    ed.set_prop(PROP_LINE_TOP, str(max(0, num_line - LINE_GOTO_OFFSET)))
    ed.set_caret(num_col, num_line)

    msg_status('Goto file: ' + filename)
    print('Go to "%s", Line %d' % (filename, num_line + 1))


do_start_server()

Caret = collections.namedtuple("Caret", "sx sy ex ey")


def normalize_caret(sx, sy, ex, ey):

    if ex == -1:

        ex, ey = sx, sy

    return Caret(ex, ey, sx, sy)


def get_params():

    carets = ed.get_carets()
    if len(carets) != 1:
        return

    filename = ed.get_filename()
    text = ed.get_text_all()
    return (filename, text, normalize_caret(*carets[0]))


def is_wordchar(s):

    return (s == '_') or s.isalnum()


def get_word_lens():
    """ Gets count of word-chars to left/right of caret
    """

    x0, y0, x1, y1 = ed.get_carets()[0]
    line = ed.get_text_line(y0)

    x = x0
    while x > 0 and is_wordchar(line[x - 1]):
        x -= 1
    len1 = x0 - x

    x = x0
    while x < len(line) and is_wordchar(line[x]):
        x += 1
    len2 = x - x0

    return (len1, len2)


def get_project_dir():
    #uses Project Manager plugin
    try:
        import cuda_project_man
        fn = cuda_project_man.global_project_info.get('filename', '')
        return os.path.dirname(fn)
    except ImportError:
        return


class Command:

    def on_complete(self, ed_self):

        params = get_params()
        if not params:
            return

        result = self.get_completes(*params)
        if not result:

            return

        par_len1, par_len2 = get_word_lens()
        if par_len1 <= 0:

            return True

        lines = []
        default = collections.ChainMap(dict(type="", name="", doc=""))
        fmt = "|{name}|{type}|\t{doc}"

        for complete in map(default.new_child, result["completions"]):

            lines.append(str.format(fmt, **complete))

        par_text = str.join("\n", lines)
        ed_self.complete(par_text, par_len1, par_len2)
        return True

    def on_goto_def(self, ed_self):

        params = get_params()
        if not params:
            return True

        result = self.get_definition(*params)
        if result:
            do_goto_file(
                result.get("file", ''),
                result.get("start", {}).get("line", 0),
                result.get("start", {}).get("ch", 0),
            )
        return True


    def on_func_hint(self, ed_self):

        params = get_params()
        if not params:
            return

        filename, text, caret = params

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

    def show_usages(self):

        if len(ed.get_carets()) == 1:

            caret, *_ = ed.get_carets()
            filename = ed.get_filename()
            text = ed.get_text_all()
            par_len1, par_len2 = get_word_lens()
            if par_len1 + par_len2 == 0:

                return

            result = self.get_references(
                filename,
                text,
                normalize_caret(*caret),
            )
            print(result)

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
                expandWordForward=False,  # need when caret inside funcname
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

    def get_references(self, filename, text, caret):

        return do_request(dict(
            files=[dict(
                type="full",
                name=filename,
                text=text,
            )],
            query=dict(
                type="refs",
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
