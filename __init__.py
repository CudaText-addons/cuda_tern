import subprocess
import re
import urllib.request
import json
import collections

from cudatext import *
import cudatext_cmd


TERN_PROCESS = subprocess.Popen(
    ("tern", "--persistent", "--ignore-stdin", "--no-port-file"),
    stdout=subprocess.PIPE,
)

s = TERN_PROCESS.stdout.readline().decode("utf-8")
match = re.match("Listening on port (\\d+)", s)
if match:

    PORT = int(match.group(1))

else:

    PORT = None
    ...


class Command:

    def on_complete(self, ed_self):

        carets = (sx, sy, ex, ey), *_ = ed_self.get_carets()
        if len(carets) > 1 or ex != -1:

            return

        result = self.complete(ed_self)
        if not result or not result.get("completions", None):

            return

        lx = result["start"]["ch"]
        rx = result["end"]["ch"]
        lines = []
        default = collections.ChainMap(dict(type="", name="", doc=""))
        fmt = "{type}|{name}|\t{doc}"
        for complete in map(default.new_child, result["completions"]):

            lines.append(str.format(fmt, **complete))

        ed_self.complete(str.join("\n", lines), sx - lx, rx - sx)
        return True

    def on_goto_def(self, ed_self):

        ...

    def on_func_hint(self, ed_self):

        ...

    def complete(self, ed_self):

        (sx, sy, ex, ey), *_ = ed_self.get_carets()
        return self.request(dict(
            files=[dict(
                type="full",
                name=ed_self.get_filename(),
                text=ed_self.get_text_all(),
            )],
            query=dict(
                type="completions",
                file=ed_self.get_filename(),
                end=dict(
                    line=sy,
                    ch=sx,
                ),
                lineCharPositions=True,
                types=True,
                docs=True,
            ),
        ))

    def request(self, data):

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        url = str.format("http://127.0.0.1:{}/", PORT)
        s = json.dumps(data).encode("utf-8")
        req = opener.open(url, s, 1)
        return json.loads(req.read().decode("utf-8"))
