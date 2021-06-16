import os
import re
import json
import subprocess
import urllib.request
import collections
import itertools
import time
import shutil

from cudatext import *
import cudatext_cmd


CUDA_LEXER_SYMBOL = "Symbol"
CUDA_LEXER_IDENTIFIER = "Identifier"

LOCALHOST = "127.0.0.1" if os.name == "nt" else "localhost"
LINE_GOTO_OFFSET = 5  # lines from top


class Tern:

    def __init__(self, timeout=3):

        self.timeout = timeout
        self.process = None
        self.port = None
        self.project_directory = None
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}))

    def start(self):

        if self.process:

            self.stop()

        try:

            self.project_directory = get_project_dir()
            self.process = subprocess.Popen(
                ("tern", "--persistent", "--ignore-stdin", "--no-port-file"),
                stdout=subprocess.PIPE,
                cwd=self.project_directory,
            )

        except:

            msg_box(
                "Cannot start Tern process.\nMake sure Tern.js and Node.js "
                "are installed.",
                MB_OK + MB_ICONERROR
            )
            self.stop()
            import traceback
            traceback.print_exc()
            return

        s = self.process.stdout.readline().decode("utf-8")
        match = re.match("Listening on port (\\d+)", s)
        if match:

            self.port = int(match.group(1))
            print('Started Tern (port %d)' % self.port)

        else:

            self.port = None
            msg_box(
                str.format(
                    "Can't start Tern process.\nCan't parse {!r} for port",
                    s,
                ),
                MB_OK + MB_ICONERROR
            )
            self.stop()

    def stop(self):

        if not self.process:

            return

        print('Stopping Tern..')
        if self.process.stdin:

            self.process.stdin.close()

        self.process.terminate()
        self.process = None
        self.port = None
        print('Stopped')

    def restart(self):

        self.stop()
        time.sleep(1)
        self.start()

    def request(self, data):

        project_directory = get_project_dir()
        if not self.process or project_directory != self.project_directory:

            self.project_directory = project_directory
            if self.project_directory and \
                    os.path.exists(self.project_directory):

                destination = os.path.join(
                    self.project_directory,
                    ".tern-project"
                )
                source = os.path.join(
                    os.path.dirname(__file__),
                    "tern-project.default",
                )
                shutil.copy(source, destination)

            self.start()

        if not self.process:

            return

        url = str.format("http://{}:{}/", LOCALHOST, self.port)
        data["timeout"] = self.timeout * 1000
        s = json.dumps(data).encode("utf-8")
        req = self.opener.open(url, s)
        return json.loads(req.read().decode("utf-8"))


def do_goto_file(filename, num_line, num_col):

    if not filename:
        return
    # print('Goto params: "%s", %d:%d' % (filename, num_line, num_col))

    # Tern gives "test/reload.js" while we edit "reload.js" in "test"
    dirname = get_project_dir()
    if dirname:
        filename = os.path.join(dirname, filename)

    if not os.path.isfile(filename):
        msg_box(
            'Tern: cannot find file:\n'+filename+'\n\n'
            'Install "Project Manager" plugin, and create/open some project. '
            'Dir of this CudaText project file will be used as dir of JS '
            'project.',
            MB_OK+MB_ICONINFO
        )
        return

    file_open(filename)
    ed.set_prop(PROP_LINE_TOP, str(max(0, num_line - LINE_GOTO_OFFSET)))
    ed.set_caret(num_col, num_line)

    msg_status('Tern: Go to file: ' + filename)
    print('Go to "%s", Line %d' % (filename, num_line + 1))


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
    # uses Project Manager plugin
    try:
        import cuda_project_man
        fn = cuda_project_man.global_project_info.get('filename', '')
        if not fn:

            return

        return os.path.dirname(fn)
    except ImportError:
        return


class Command:

    def __init__(self):

        self.tern = Tern()

    def restart_server(self):

        self.tern.restart()

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

        # collect all lexer tokens from start to caret position.
        # analyze "Symbol" tokens "(" and ")".
        # calculate "depth" for them.
        # when "Identifier" found with depth==0, we found function name.
        
        toks = ed_self.get_token(TOKEN_LIST_SUB, 0, caret.sy)
        if not toks:
            return
        for d in toks:
            x1 = d['x1']
            y1 = d['y1']
            if y1>caret.sy:
                break
            if y1==caret.sy and x1>=caret.sx:
                break
            tokens.append(d)

        depth = 1
        while tokens:

            d = tokens.pop()
            sx = d['x1']
            sy = d['y1']
            ex = d['x2']
            ey = d['y2']
            s = d['str']
            token_type = d['style']
            
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

    def get_docstring(self):

        params = get_params()
        if not params:
            return

        res = self.get_completes(*params)
        if not res:
            return

        res = res["completions"]
        if not res:
            return

        res = res[0]
        r1 = res.get("name", "?")+": "+res.get("type", "?")
        r2 = res.get("doc", "")
        if r2:
            return r1+"\n"+r2

    def show_docstr(self):

        text = self.get_docstring()
        if not text:
            msg_status('Tern: Cannot find doc-string')
            return

        ed.cmd(cudatext_cmd.cmd_ShowPanelOutput)

        app_log(LOG_CLEAR, '', panel=LOG_PANEL_OUTPUT)
        for s in text.splitlines():
            app_log(LOG_ADD, s, panel=LOG_PANEL_OUTPUT)

    def show_usages(self):

        params = get_params()
        if not params:
            return

        refs = self.get_references(*params)
        if not refs:
            return

        refs = refs.get('refs', [])
        if not refs:
            return

        items = ['%s\t%d' % (ref['file'], ref['start']['line']+1) for ref in refs]
        res = dlg_menu(DMENU_LIST, items, caption='Usages')
        if res is None:
            return

        ref = refs[res]
        filename = ref['file']
        num_line = ref['start']['line']
        num_col = ref['start']['ch']
        do_goto_file(filename, num_line, num_col)

    def open_tern_project_file(self):

        project_directory = get_project_dir()
        if not project_directory:

            msg_status("Tern: Project not opened")
            return

        tern_project_file = os.path.join(project_directory, ".tern-project")
        if not os.path.exists(tern_project_file):

            msg_status("Tern: Project has no '.tern-project' file")
            return

        file_open(tern_project_file)
        ed.set_prop(PROP_LEXER_FILE, "json")

    def get_completes(self, filename, text, caret):

        return self.tern.request(dict(
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

        return self.tern.request(dict(
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

        return self.tern.request(dict(
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

        return self.tern.request(dict(
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
