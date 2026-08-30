#!/usr/bin/env python3
"""Serves TIMELINE.md (and PLAN.md) of an intercom checkout as styled HTML on 127.0.0.1 — read-only, auto-refreshing."""
import html, os, re, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.getcwd()
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 5341
CSS = """:root{color-scheme:light dark;--bg:#F0EEE6;--surface:#ECE9DF;--line:#D5D0C1;--text:#1F1E1B;--soft:#57544B;--dim:#6E6A5A;--accent:#D97757;--accent-bg:#F4E9E1;--ok:#3B7A57;--err:#9A3B22}
@media(prefers-color-scheme:dark){:root{--bg:#161411;--surface:#1c1915;--line:#332e27;--text:#EAE6DA;--soft:#B5AF9F;--dim:#948D7F;--accent:#E08A63;--accent-bg:#3A2A22;--ok:#6FBF8F;--err:#E08A70}}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 "Inter","Helvetica Neue",Arial,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 28px 60px}
h1,h2{font-family:"Newsreader","Iowan Old Style",Georgia,serif;font-weight:600;letter-spacing:0}
h1{font-size:30px;margin:0 0 4px}h2{font-size:20px;margin:28px 0 8px;padding-bottom:4px;border-bottom:1px solid var(--line)}
nav{display:flex;gap:10px;align-items:center;margin-bottom:18px;color:var(--dim);font-size:13px}
nav a{color:var(--accent);text-decoration:none;font-weight:600;padding:3px 10px;border:1px solid var(--accent-bg);background:var(--accent-bg);border-radius:8px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;background:var(--surface);border-radius:10px;overflow:hidden}
th,td{padding:7px 12px;text-align:left;border-bottom:1px solid var(--line)}th{color:var(--dim);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.06em}
ul{list-style:none;padding:0;margin:0}li{padding:6px 10px;border-left:3px solid var(--line);margin:4px 0;background:var(--surface);border-radius:0 8px 8px 0}
li.unacked{border-left-color:var(--err)}li.acked{border-left-color:var(--ok)}code,.mono{font-family:"JetBrains Mono",Menlo,monospace;font-size:12.5px;color:var(--soft)}
strong{color:var(--text)}.re{color:var(--dim)}.gen{color:var(--dim);font-size:12px}"""
def md_to_html(md):
    out, in_table, in_list = [], False, False
    for line in md.splitlines():
        if line.startswith("<!--"):
            out.append(f'<p class="gen">{html.escape(line.strip("<!-> "))}</p>'); continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r"-+", c) for c in cells):
                continue
            if not in_table:
                out.append("<table>"); in_table = True
                out.append("<tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in cells) + "</tr>"); continue
            out.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in cells) + "</tr>"); continue
        if in_table:
            out.append("</table>"); in_table = False
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>"); in_list = True
            t = html.escape(line[2:])
            cls = "unacked" if "unacked" in t or "ohne Ack" in t else ("acked" if "acked by" in t or "Ack von" in t else "")
            t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
            t = re.sub(r"↩ (re [^—]+)", r'<span class="re">↩ \1</span>', t)
            t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
            out.append(f'<li class="{cls}">{t}</li>'); continue
        if in_list:
            out.append("</ul>"); in_list = False
        if line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.strip():
            out.append(f"<p>{html.escape(line)}</p>")
    if in_table: out.append("</table>")
    if in_list: out.append("</ul>")
    return "\n".join(out)
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        name = "PLAN.md" if self.path.startswith("/plan") else "TIMELINE.md"
        try:
            md = open(os.path.join(ROOT, name), encoding="utf-8").read()
        except OSError:
            md = f"# {name}\n\nnot rendered yet — run `python3 intercom.py render`"
        page = (f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="60"><title>intercom · {name}</title>'
                f"<style>{CSS}</style><main><nav><a href='/'>Timeline</a><a href='/plan'>Plan</a>"
                f"<span>{html.escape(ROOT)} · refreshes every minute</span></nav>{md_to_html(md)}</main>")
        body = page.encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
HTTPServer(("127.0.0.1", PORT), H).serve_forever()
