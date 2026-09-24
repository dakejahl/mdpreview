#!/usr/bin/env python3
"""Split Markdown preview: source on the left, rendered page on the right.

The source buffer is what gets saved. The preview is GitHub-flavored Markdown
drawn with cmark-gfm, styled either like GitHub or like a GitBook page.
"""

import base64
import json
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
from urllib.request import pathname2url, url2pathname

import cmarkgfm
from cmarkgfm.cmark import Options
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

APP_ID = "io.github.dakejahl.mdpreview"
STATE_PATH = os.path.expanduser("~/.config/mdpreview/state.json")
MD_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd"}
IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".avif": "image/avif",
}
# Inline local images up to this size. Larger ones stay as file: URLs.
MAX_INLINE_IMAGE = 8 * 1024 * 1024

LEXER_ALIASES = {
    "ts": "typescript",
    "js": "javascript",
    "py": "python",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "yml": "yaml",
    "md": "markdown",
    "dockerfile": "docker",
    "text": "text",
    "plaintext": "text",
    "txt": "text",
    "c++": "cpp",
    "c#": "csharp",
}

_FORMATTER = HtmlFormatter(nowrap=True)
_PYGMENTS_CSS = "\n".join(
    [
        HtmlFormatter(style="default").get_style_defs(".markdown-body .highlight"),
        HtmlFormatter(style="github-dark").get_style_defs("html.dark .markdown-body .highlight"),
        HtmlFormatter(style="github-dark").get_style_defs("html.gitbook .markdown-body .highlight"),
    ]
)

PAGE_CSS = r"""
html {
  --fg: #1f2328;
  --bg: #ffffff;
  --border: #d0d7de;
  --muted: #59636e;
  --accent: #0969da;
  --code-bg: rgba(129, 139, 152, 0.12);
  --pre-bg: #f6f8fa;
  --stripe: #f6f8fa;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
  color-scheme: light;
}
html.dark {
  --fg: #e6edf3;
  --bg: #0d1117;
  --border: #3d444d;
  --muted: #9198a1;
  --accent: #4493f8;
  --code-bg: rgba(101, 108, 118, 0.2);
  --pre-bg: #161b22;
  --stripe: #161b22;
  color-scheme: dark;
}
html.gitbook {
  --fg: #1b1d1e;
  --bg: #ffffff;
  --border: #e6e8eb;
  --muted: #6c7278;
  --accent: #346ddb;
  --code-bg: #f1f3f5;
  --pre-bg: #0d1117;
}
html.gitbook.dark {
  --fg: #e7eaee;
  --bg: #1a1d21;
  --border: #2c3138;
  --muted: #9aa4b2;
  --accent: #7aa2f7;
  --code-bg: #2a3038;
  --pre-bg: #0d1117;
}
html, body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
}
.markdown-body {
  box-sizing: border-box;
  min-width: 200px;
  max-width: none;
  margin: 0;
  padding: 24px 32px 64px;
  font-family: var(--font);
  font-size: 16px;
  line-height: 1.5;
  word-wrap: break-word;
  color: var(--fg);
}
html.gitbook .markdown-body {
  max-width: 44rem;
  margin: 0 auto;
  padding: 2.75rem 2rem 5rem;
  font-size: 16.5px;
  line-height: 1.7;
}
.markdown-body > :first-child { margin-top: 0; }
.markdown-body p { margin-top: 0; margin-bottom: 16px; }
.markdown-body h1, .markdown-body h2, .markdown-body h3,
.markdown-body h4, .markdown-body h5, .markdown-body h6 {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
  line-height: 1.25;
}
.markdown-body h1 { font-size: 2em; padding-bottom: .3em; border-bottom: 1px solid var(--border); }
.markdown-body h2 { font-size: 1.5em; padding-bottom: .3em; border-bottom: 1px solid var(--border); }
.markdown-body h3 { font-size: 1.25em; }
.markdown-body h4 { font-size: 1em; }
.markdown-body h5 { font-size: .875em; }
.markdown-body h6 { font-size: .85em; color: var(--muted); }
html.gitbook .markdown-body h1,
html.gitbook .markdown-body h2 {
  border-bottom: 0;
  padding-bottom: 0;
}
html.gitbook .markdown-body h1 { font-size: 2.1rem; letter-spacing: -0.02em; }
html.gitbook .markdown-body h2 { font-size: 1.5rem; }
.markdown-body a { color: var(--accent); text-decoration: none; }
.markdown-body a:hover { text-decoration: underline; }
.markdown-body strong { font-weight: 600; }
.markdown-body ul, .markdown-body ol { margin-top: 0; margin-bottom: 16px; padding-left: 2em; }
.markdown-body li + li { margin-top: .25em; }
.markdown-body li:has(> input[type="checkbox"]) { list-style: none; }
.markdown-body li:has(> input[type="checkbox"]) > input {
  margin: 0 .4em .25em -1.4em;
  vertical-align: middle;
}
.markdown-body code, .markdown-body tt {
  font-family: var(--mono);
  font-size: 85%;
  padding: .2em .4em;
  margin: 0;
  background: var(--code-bg);
  border-radius: 6px;
  white-space: break-spaces;
}
.markdown-body pre.highlight {
  margin-top: 0;
  margin-bottom: 16px;
  padding: 16px;
  overflow: auto;
  font-size: 85%;
  line-height: 1.45;
  background: var(--pre-bg);
  border-radius: 6px;
  color: var(--fg);
}
html.gitbook .markdown-body pre.highlight,
html.dark .markdown-body pre.highlight {
  color: #e6edf3;
}
.markdown-body pre.highlight code {
  padding: 0;
  margin: 0;
  background: transparent;
  border-radius: 0;
  white-space: pre;
  font-size: 100%;
}
.markdown-body pre.highlight[data-lang]::before {
  content: attr(data-lang);
  float: right;
  margin-left: 16px;
  font-family: var(--font);
  font-size: 12px;
  line-height: 1.45;
  color: var(--muted);
}
html.gitbook .markdown-body pre.highlight[data-lang]::before,
html.dark .markdown-body pre.highlight[data-lang]::before {
  color: #8b949e;
}
.markdown-body blockquote {
  margin: 0 0 16px;
  padding: 0 1em;
  color: var(--muted);
  border-left: .25em solid var(--border);
}
.markdown-body .markdown-alert {
  padding: .5rem 1rem;
  margin: 0 0 16px;
  color: var(--fg);
  border-left-width: .25em;
  border-radius: 6px;
}
.markdown-body .markdown-alert-title { margin: 0 0 .25rem; font-weight: 600; }
.markdown-body .markdown-alert-note { border-color: #0969da; background: #ddf4ff; }
.markdown-body .markdown-alert-note .markdown-alert-title { color: #0969da; }
.markdown-body .markdown-alert-tip { border-color: #1a7f37; background: #dafbe1; }
.markdown-body .markdown-alert-tip .markdown-alert-title { color: #1a7f37; }
.markdown-body .markdown-alert-important { border-color: #8250df; background: #fbefff; }
.markdown-body .markdown-alert-important .markdown-alert-title { color: #8250df; }
.markdown-body .markdown-alert-warning { border-color: #9a6700; background: #fff8c5; }
.markdown-body .markdown-alert-warning .markdown-alert-title { color: #9a6700; }
.markdown-body .markdown-alert-caution { border-color: #cf222e; background: #ffebe9; }
.markdown-body .markdown-alert-caution .markdown-alert-title { color: #d1242f; }
html.dark .markdown-body .markdown-alert-note { border-color: #1f6feb; background: #121d2f; }
html.dark .markdown-body .markdown-alert-note .markdown-alert-title { color: #4493f8; }
html.dark .markdown-body .markdown-alert-tip { border-color: #238636; background: #12261e; }
html.dark .markdown-body .markdown-alert-tip .markdown-alert-title { color: #3fb950; }
html.dark .markdown-body .markdown-alert-important { border-color: #8957e5; background: #1e1630; }
html.dark .markdown-body .markdown-alert-important .markdown-alert-title { color: #ab7df8; }
html.dark .markdown-body .markdown-alert-warning { border-color: #9e6a03; background: #2e2208; }
html.dark .markdown-body .markdown-alert-warning .markdown-alert-title { color: #d29922; }
html.dark .markdown-body .markdown-alert-caution { border-color: #da3633; background: #2e1618; }
html.dark .markdown-body .markdown-alert-caution .markdown-alert-title { color: #f85149; }
.markdown-body table {
  display: block;
  width: max-content;
  max-width: 100%;
  overflow: auto;
  border-spacing: 0;
  border-collapse: collapse;
  margin-bottom: 16px;
}
.markdown-body th, .markdown-body td {
  padding: 6px 13px;
  border: 1px solid var(--border);
}
.markdown-body th { font-weight: 600; }
.markdown-body tbody tr:nth-child(even) { background: var(--stripe); }
.markdown-body img { max-width: 100%; height: auto; }
.markdown-body hr {
  height: .25em;
  margin: 24px 0;
  background: var(--border);
  border: 0;
}
.markdown-body kbd {
  display: inline-block;
  padding: .2em .4em;
  font-family: var(--mono);
  font-size: 85%;
  line-height: 1;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--pre-bg);
  box-shadow: inset 0 -1px 0 var(--border);
}
.markdown-body details {
  margin-bottom: 16px;
  padding: .5em 1em;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.markdown-body summary { font-weight: 600; cursor: pointer; }
.markdown-body .empty { color: var(--muted); }
"""


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_attr(text):
    return escape(text).replace('"', "&quot;")


def path_to_file_uri(path):
    return "file://" + pathname2url(os.path.abspath(path))


def slugify(text, seen):
    slug = text.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug, flags=re.UNICODE)
    slug = re.sub(r"[_\s]+", "-", slug).strip("-")
    if not slug:
        slug = "section"
    count = seen.get(slug, 0)
    seen[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count}"


def lexer_for(lang):
    name = (lang or "").strip()
    if not name:
        return get_lexer_by_name("text")
    candidates = [name, LEXER_ALIASES.get(name.lower(), "")]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return get_lexer_by_name(candidate)
        except ClassNotFound:
            continue
    return get_lexer_by_name("text")


def highlight_block(source, lang):
    try:
        inner = highlight(source, lexer_for(lang), _FORMATTER)
    except Exception:
        inner = escape(source)
    label = f' data-lang="{escape_attr(lang.strip())}"' if lang and lang.strip() else ""
    return f'<pre class="highlight"{label}><code>{inner}</code></pre>'


def image_source(path):
    ext = os.path.splitext(path)[1].lower()
    mime = IMAGE_MIME.get(ext)
    if mime is None or not os.path.isfile(path):
        return path_to_file_uri(path)
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size > MAX_INLINE_IMAGE:
        return path_to_file_uri(path)
    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def safe_url(url, base_dir, kind):
    url = (url or "").strip()
    if not url or any(char in url for char in ("\t", "\r", "\n", "\x00")):
        return None
    if kind == "link" and url.startswith("#"):
        return url
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme in ("javascript", "vbscript", "data"):
        return None
    if scheme in ("http", "https"):
        return url
    if scheme == "mailto" and kind == "link":
        return url
    if scheme not in ("", "file"):
        return None
    if scheme == "file":
        path = url2pathname(parts.path)
    elif base_dir is None:
        return None
    else:
        path = os.path.normpath(os.path.join(base_dir, unquote(parts.path)))
    if kind == "img":
        return image_source(path)
    fragment = f"#{parts.fragment}" if parts.fragment else ""
    return path_to_file_uri(path) + fragment


class Sanitizer(HTMLParser):
    """Allow the tags cmark emits, plus the HTML GitHub still renders.

    cmark's unsafe flag passes raw HTML through. The preview document runs
    JavaScript so it can swap the article without jumping the scroll position,
    and assigning that HTML with innerHTML does not run script tags. Event
    handlers and javascript: URLs would still run, so they never leave here.
    """

    DROP = {
        "script", "style", "iframe", "object", "embed", "link", "meta",
        "base", "form", "textarea", "title",
    }
    ALLOW = {
        "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "blockquote",
        "ul", "ol", "li", "strong", "em", "del", "s", "a", "img", "code",
        "pre", "table", "thead", "tbody", "tr", "th", "td", "input", "sup",
        "sub", "kbd", "details", "summary", "div", "span", "section",
    }
    VOID = {"br", "hr", "img", "input", "wbr"}

    def __init__(self, base_dir):
        super().__init__(convert_charrefs=True)
        self.base_dir = base_dir
        self.out = []
        self.skip = 0
        self.in_pre = False
        self.pre_lang = ""
        self.pre_text = []
        self.heading = None
        self.heading_text = []
        self.heading_html = []
        self.seen = {}

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, tag in self.VOID)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, True)

    def handle_endtag(self, tag):
        if self.skip:
            self.skip -= 1
            return
        if self.in_pre:
            if tag == "pre":
                self.in_pre = False
                self._emit(highlight_block("".join(self.pre_text), self.pre_lang))
            return
        if tag == self.heading:
            slug = slugify("".join(self.heading_text), self.seen)
            inner = "".join(self.heading_html)
            self.heading = None
            self.out.append(f'<{tag} id="{escape_attr(slug)}">{inner}</{tag}>')
            return
        if tag in self.ALLOW and tag not in self.VOID:
            self._emit(f"</{tag}>")

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_pre:
            self.pre_text.append(data)
            return
        if self.heading is not None:
            self.heading_text.append(data)
            self.heading_html.append(escape(data))
            return
        self.out.append(escape(data))

    def handle_comment(self, data):
        return

    def close(self):
        super().close()
        if self.in_pre:
            self.handle_endtag("pre")
        if self.heading:
            self.handle_endtag(self.heading)

    def _start(self, tag, attrs, void):
        if self.skip:
            if not void:
                self.skip += 1
            return
        if tag in self.DROP:
            if not void:
                self.skip = 1
            return
        amap = {key: value or "" for key, value in attrs}
        if self.in_pre:
            if tag == "code" and not self.pre_lang:
                for part in amap.get("class", "").split():
                    if part.startswith("language-"):
                        self.pre_lang = part[len("language-"):]
            return
        if tag == "pre":
            self.in_pre = True
            self.pre_lang = amap.get("lang", "")
            self.pre_text = []
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self.heading is None:
            self.heading = tag
            self.heading_text = []
            self.heading_html = []
            return
        if tag not in self.ALLOW:
            return
        opened = self._open_tag(tag, amap)
        if opened:
            self._emit(opened)

    def _emit(self, text):
        if self.heading is not None:
            self.heading_html.append(text)
        else:
            self.out.append(text)

    def _open_tag(self, tag, amap):
        if tag == "a":
            href = safe_url(amap.get("href", ""), self.base_dir, "link")
            if not href:
                return "<a>"
            title = amap.get("title")
            extra = f' title="{escape_attr(title)}"' if title else ""
            return f'<a href="{escape_attr(href)}"{extra}>'
        if tag == "img":
            src = safe_url(amap.get("src", ""), self.base_dir, "img")
            alt = escape_attr(amap.get("alt", ""))
            if not src:
                return f'<img alt="{alt}">'
            return f'<img src="{escape_attr(src)}" alt="{alt}">'
        if tag == "input":
            if amap.get("type") != "checkbox":
                return ""
            checked = " checked" if "checked" in amap else ""
            return f'<input type="checkbox" disabled{checked}>'
        if tag in ("th", "td", "div"):
            align = amap.get("align")
            if align in ("left", "center", "right"):
                return f'<{tag} align="{align}">'
            return f"<{tag}>"
        return f"<{tag}>"


_ALERT = re.compile(
    r"<blockquote>\s*<p>\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*",
    re.IGNORECASE,
)


def mark_alerts(html):
    def replace(match):
        word = match.group(1)
        kind = word.lower()
        return (
            f'<blockquote class="markdown-alert markdown-alert-{kind}">'
            f'<p class="markdown-alert-title">{word.capitalize()}</p><p>'
        )

    return _ALERT.sub(replace, html)


def render_markdown(text, base_dir):
    if not text.strip():
        return '<p class="empty">Rendered Markdown will show here.</p>'
    try:
        raw = cmarkgfm.github_flavored_markdown_to_html(text, Options.CMARK_OPT_UNSAFE)
        parser = Sanitizer(base_dir)
        parser.feed(raw)
        parser.close()
        return mark_alerts("".join(parser.out))
    except Exception as exc:
        return "<p class=\"empty\">" + escape(str(exc)) + "</p>"


def shell_html():
    css = _PYGMENTS_CSS + "\n" + PAGE_CSS
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f"<style>{css}</style></head><body>"
        "<article id=\"doc\" class=\"markdown-body\"></article>"
        "</body></html>"
    )


def self_test():
    import tempfile

    sample = "\n".join(
        [
            "# Title",
            "",
            "A **bold** word and a [link](https://example.com).",
            "",
            "hello",
            "world",
            "",
            "- [x] done",
            "- [ ] not",
            "",
            "| a | b |",
            "| --- | --- |",
            "| 1 | 2 |",
            "",
            "```python",
            "print('hi')",
            "```",
            "",
            "> [!WARNING]",
            "> Do not do this",
            "",
            "~~gone~~",
            "",
            "<script>alert(1)</script>",
            "<img src=\"x.png\" onerror=\"alert(1)\">",
            "",
            "[click](javascript:alert(1))",
        ]
    )
    with tempfile.TemporaryDirectory() as directory:
        png = os.path.join(directory, "shot.png")
        with open(png, "wb") as handle:
            handle.write(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
                )
            )
        html = render_markdown(sample + f"\n\n![pic](shot.png)\n", directory)

    failures = []

    def check(name, cond):
        if not cond:
            failures.append(name)

    check("heading id", 'id="title"' in html)
    check("bold", "<strong>bold</strong>" in html)
    check("link", 'href="https://example.com"' in html)
    check("softbreak is not a br", "<br" not in html.split("<pre")[0])
    check("task", 'type="checkbox"' in html and "disabled" in html and "checked" in html)
    check("table", "<table>" in html and "<td>1</td>" in html)
    check("highlight", 'data-lang="python"' in html and "highlight" in html and "<span" in html)
    check("alert", 'markdown-alert-warning' in html and "Warning" in html)
    check("strike", "<del>gone</del>" in html)
    check("script not live", "<script" not in html)
    check("handler dropped", "onerror" not in html)
    check("js url dropped", "javascript:" not in html)
    check("image inlined", "data:image/png;base64," in html)
    details = render_markdown("<details><summary>More</summary>\n\nHidden\n\n</details>\n", None)
    check("details", "<details>" in details and "<summary>More</summary>" in details)
    if failures:
        print("\n".join(failures))
        print(html)
        return 1
    print("ok")
    return 0


def read_text(path):
    # newline="" keeps CRLF files from being rewritten as LF on save.
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def main(argv):
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("WebKit", "6.0")
    gi.require_version("GtkSource", "5")
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk, GtkSource, WebKit

    class PreviewWindow(Adw.ApplicationWindow):
        def __init__(self, app, path):
            super().__init__(application=app)
            state = load_state()
            width = state.get("width") if isinstance(state.get("width"), int) else 1200
            height = state.get("height") if isinstance(state.get("height"), int) else 800
            self.set_default_size(max(width, 640), max(height, 480))
            if state.get("maximized") is True:
                self.maximize()
            self._saved_paned = state.get("paned") if isinstance(state.get("paned"), int) else None
            self.style = state.get("style") if state.get("style") in ("github", "gitbook") else "github"
            self.path = None
            self.dirty = False
            self.monitor = None
            self._watched = None
            self._loading = False
            self._ignore_file_events = False
            self._render_id = 0
            self._page_ready = False
            self._pending_html = ""
            self._fragment = None
            self._closing = False
            self._dark = False

            self.buffer = GtkSource.Buffer()
            language = GtkSource.LanguageManager.get_default().get_language("markdown")
            if language is not None:
                self.buffer.set_language(language)
            self.buffer.set_highlight_syntax(True)
            self.buffer.connect("changed", self.on_buffer_changed)
            self.schemes = GtkSource.StyleSchemeManager.get_default()

            self.view = GtkSource.View(
                buffer=self.buffer,
                monospace=True,
                show_line_numbers=True,
                wrap_mode=Gtk.WrapMode.WORD_CHAR,
                auto_indent=True,
                highlight_current_line=True,
                left_margin=8,
                right_margin=16,
                top_margin=8,
                bottom_margin=8,
                tab_width=2,
                indent_width=2,
                insert_spaces_instead_of_tabs=True,
                hexpand=True,
                vexpand=True,
            )
            scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
            scroller.set_child(self.view)

            self.webview = WebKit.WebView(hexpand=True, vexpand=True)
            settings = self.webview.get_settings()
            settings.set_enable_javascript(True)
            settings.set_javascript_can_open_windows_automatically(False)
            settings.set_allow_modal_dialogs(False)
            settings.set_enable_back_forward_navigation_gestures(False)
            self.webview.set_editable(False)
            self.webview.connect("load-changed", self.on_load_changed)
            self.webview.connect("decide-policy", self.on_decide_policy)
            self.webview.load_html(shell_html(), "about:blank")

            self.paned = Gtk.Paned(
                orientation=Gtk.Orientation.HORIZONTAL,
                wide_handle=True,
                hexpand=True,
                vexpand=True,
                start_child=scroller,
                end_child=self.webview,
                resize_start_child=True,
                resize_end_child=True,
                shrink_start_child=True,
                shrink_end_child=True,
            )
            scroller.set_size_request(160, -1)
            self.webview.set_size_request(160, -1)

            header = Adw.HeaderBar()
            open_button = Gtk.Button.new_from_icon_name("document-open-symbolic")
            open_button.set_tooltip_text("Open (Ctrl+O)")
            open_button.connect("clicked", lambda *_: self.open_dialog())
            self.save_button = Gtk.Button.new_from_icon_name("document-save-symbolic")
            self.save_button.set_tooltip_text("Save (Ctrl+S)")
            self.save_button.connect("clicked", lambda *_: self.save())
            header.pack_start(open_button)
            header.pack_start(self.save_button)
            self.style_drop = Gtk.DropDown.new_from_strings(["GitHub", "GitBook"])
            self.style_drop.set_selected(1 if self.style == "gitbook" else 0)
            self.style_drop.set_tooltip_text("How the preview is styled")
            self.style_drop.connect("notify::selected", self.on_style_selected)
            header.pack_end(self.style_drop)

            toolbar = Adw.ToolbarView()
            toolbar.add_top_bar(header)
            toolbar.set_content(self.paned)
            self.set_content(toolbar)

            self._add_action("open", self.open_dialog)
            self.save_action = self._add_action("save", self.save)
            self._add_action("save-as", self.save_as)
            for name, accel in (
                ("win.open", "<primary>o"),
                ("win.save", "<primary>s"),
                ("win.save-as", "<primary><shift>s"),
            ):
                app.set_accels_for_action(name, [accel])

            drop = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
            drop.connect("drop", self.on_drop)
            self.add_controller(drop)
            self.connect("close-request", self.on_close_request)
            Adw.StyleManager.get_default().connect("notify::dark", lambda *_: self.apply_theme())

            self.apply_theme()
            self.update_title()
            if path:
                self.load_path(path)
            else:
                self.set_document_text("")
                self.schedule_render()
            GLib.timeout_add(50, self._restore_paned, 0)

        def _add_action(self, name, callback):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_: callback())
            self.add_action(action)
            return action

        def _restore_paned(self, tries):
            width = self.paned.get_width()
            if width < 100:
                if tries < 20:
                    GLib.timeout_add(50, self._restore_paned, tries + 1)
                return False
            position = self._saved_paned
            if not isinstance(position, int) or position < 120 or position > width - 120:
                position = width // 2
            self.paned.set_position(position)
            return False

        def buffer_text(self):
            return self.buffer.get_text(
                self.buffer.get_start_iter(), self.buffer.get_end_iter(), True
            )

        def base_dir(self):
            if not self.path:
                return None
            return os.path.dirname(self.path)

        def on_buffer_changed(self, _buffer):
            if self._loading:
                return
            if not self.dirty:
                self.dirty = True
                self.update_title()
            self.schedule_render()

        def schedule_render(self):
            if self._render_id:
                GLib.source_remove(self._render_id)
            self._render_id = GLib.timeout_add(60, self.render_now)

        def render_now(self):
            self._render_id = 0
            self.push_html(render_markdown(self.buffer_text(), self.base_dir()))
            return False

        def push_html(self, fragment):
            self._pending_html = fragment
            if not self._page_ready:
                return
            script = "document.getElementById('doc').innerHTML = " + json.dumps(fragment) + ";"
            if self._fragment:
                script += "location.hash = " + json.dumps(self._fragment) + ";"
                self._fragment = None
            self.eval_js(script)

        def eval_js(self, script):
            self.webview.evaluate_javascript(script, -1, None, None, None, None, None)

        def on_load_changed(self, _webview, event):
            if event != WebKit.LoadEvent.FINISHED:
                return
            self._page_ready = True
            self.apply_theme()
            self.push_html(self._pending_html)

        def apply_theme(self):
            self._dark = Adw.StyleManager.get_default().get_dark()
            classes = []
            if self._dark:
                classes.append("dark")
            if self.style == "gitbook":
                classes.append("gitbook")
            color = Gdk.RGBA()
            color.parse(self.preview_background())
            self.webview.set_background_color(color)
            if self._page_ready:
                self.eval_js("document.documentElement.className = " + json.dumps(" ".join(classes)) + ";")
            scheme_id = "Adwaita-dark" if self._dark else "Adwaita"
            scheme = self.schemes.get_scheme(scheme_id)
            if scheme is not None:
                self.buffer.set_style_scheme(scheme)

        def preview_background(self):
            if self.style == "gitbook" and self._dark:
                return "#1a1d21"
            if self._dark:
                return "#0d1117"
            return "#ffffff"

        def on_style_selected(self, dropdown, _pspec):
            self.style = "gitbook" if dropdown.get_selected() == 1 else "github"
            self.apply_theme()

        def on_decide_policy(self, _webview, decision, decision_type):
            if decision_type not in (
                WebKit.PolicyDecisionType.NAVIGATION_ACTION,
                WebKit.PolicyDecisionType.NEW_WINDOW_ACTION,
            ):
                return False
            try:
                action = decision.get_navigation_action()
            except Exception:
                return False
            if action.get_navigation_type() != WebKit.NavigationType.LINK_CLICKED:
                return False
            uri = action.get_request().get_uri() or ""
            parts = urlsplit(uri)
            if parts.scheme == "about":
                decision.use()
                return True
            decision.ignore()
            if parts.scheme in ("http", "https", "mailto"):
                Gtk.UriLauncher.new(uri).launch(self, None, None)
                return True
            if parts.scheme == "file":
                path = url2pathname(parts.path)
                if os.path.splitext(path)[1].lower() in MD_EXTENSIONS:
                    fragment = parts.fragment or None
                    if self.path and os.path.abspath(path) == os.path.abspath(self.path):
                        if fragment:
                            self._fragment = fragment
                            self.eval_js("location.hash = " + json.dumps(fragment) + ";")
                    else:
                        self.open_path_checked(path, fragment)
                    return True
                Gtk.UriLauncher.new(uri).launch(self, None, None)
            return True

        def on_drop(self, _target, gfile, _x, _y):
            path = gfile.get_path()
            if path:
                self.open_path_checked(path)
            return True

        def set_document_text(self, text, keep_place=False):
            line = col = 0
            if keep_place:
                insert = self.buffer.get_iter_at_mark(self.buffer.get_insert())
                line = insert.get_line()
                col = insert.get_line_offset()
            self._loading = True
            try:
                self.buffer.begin_irreversible_action()
                self.buffer.set_text(text)
                self.buffer.end_irreversible_action()
            finally:
                self._loading = False
            self.dirty = False
            self.buffer.set_modified(False)
            if keep_place and self.buffer.get_line_count():
                line = min(line, self.buffer.get_line_count() - 1)
                cursor = self.buffer.get_iter_at_line(line)
                limit = max(0, cursor.get_chars_in_line() - 1)
                try:
                    cursor.set_line_offset(min(col, limit))
                except Exception:
                    pass
                self.buffer.place_cursor(cursor)
                self.view.scroll_to_mark(self.buffer.get_insert(), 0.05, False, 0.0, 0.0)
            else:
                self.buffer.place_cursor(self.buffer.get_start_iter())
            self.update_title()

        def load_path(self, path, fragment=None, from_disk_event=False):
            path = os.path.abspath(path)
            try:
                text = read_text(path)
            except UnicodeError:
                self.report_error("Could not open file", f"{path} is not UTF-8 text.")
                return
            except OSError as exc:
                self.report_error("Could not open file", str(exc))
                return
            self.path = path
            self._fragment = fragment
            self.set_document_text(text, keep_place=from_disk_event)
            self.watch(path)
            self.schedule_render()
            if not from_disk_event:
                self.view.grab_focus()

        def watch(self, path):
            if self._watched == path and self.monitor is not None:
                return
            if self.monitor is not None:
                self.monitor.cancel()
            self._watched = path
            gfile = Gio.File.new_for_path(path)
            self.monitor = gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
            self.monitor.connect("changed", self.on_file_event)

        def on_file_event(self, _monitor, _file, _other, event):
            if self._ignore_file_events or self.dirty or self._loading or not self.path:
                return
            if event != Gio.FileMonitorEvent.CHANGES_DONE_HINT:
                return
            try:
                if read_text(self.path) == self.buffer_text():
                    return
            except (OSError, UnicodeError):
                return
            self.load_path(self.path, from_disk_event=True)

        def open_path_checked(self, path, fragment=None):
            def go():
                self.load_path(path, fragment)

            if self.dirty:
                self.confirm(go)
            else:
                go()

        def open_dialog(self):
            dialog = Gtk.FileDialog(title="Open Markdown", modal=True)
            dialog.set_filters(markdown_filters())
            if self.path:
                dialog.set_initial_folder(Gio.File.new_for_path(os.path.dirname(self.path)))
            dialog.open(self, None, self.on_open_finished)

        def on_open_finished(self, dialog, result):
            try:
                chosen = dialog.open_finish(result)
            except GLib.Error:
                return
            path = chosen.get_path()
            if path:
                self.open_path_checked(path)

        def save(self, then=None):
            if not self.dirty and then is None:
                return
            if self.path:
                if self.write_path(self.path) and then is not None:
                    then()
                return
            self.save_as(then)

        def save_as(self, then=None):
            dialog = Gtk.FileDialog(title="Save Markdown", modal=True)
            dialog.set_filters(markdown_filters())
            if self.path:
                dialog.set_initial_file(Gio.File.new_for_path(self.path))
            else:
                dialog.set_initial_name("untitled.md")
            dialog.save(self, None, lambda file_dialog, result: self.on_save_finished(file_dialog, result, then))

        def on_save_finished(self, dialog, result, then):
            try:
                chosen = dialog.save_finish(result)
            except GLib.Error:
                return
            path = chosen.get_path()
            if path and self.write_path(path) and then is not None:
                then()

        def write_path(self, path):
            text = self.buffer_text()
            temporary = path + ".mdpreview-tmp"
            self._ignore_file_events = True
            try:
                with open(temporary, "w", encoding="utf-8", newline="") as handle:
                    handle.write(text)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            except OSError as exc:
                self.report_error("Could not save", str(exc))
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
                return False
            finally:
                GLib.timeout_add(400, self._listen_again)
            self.path = path
            self.dirty = False
            self.buffer.set_modified(False)
            self.watch(path)
            self.update_title()
            return True

        def _listen_again(self):
            self._ignore_file_events = False
            return False

        def confirm(self, then):
            dialog = Adw.AlertDialog(
                heading="Save changes to this file?",
                body="The source has edits that are not saved.",
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("discard", "Discard")
            dialog.add_response("save", "Save")
            dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")

            def on_response(_dialog, response):
                if response == "discard":
                    then()
                elif response == "save":
                    self.save(then)

            dialog.connect("response", on_response)
            dialog.present(self)

        def report_error(self, heading, body):
            dialog = Adw.AlertDialog(heading=heading, body=body)
            dialog.add_response("ok", "OK")
            dialog.present(self)

        def update_title(self):
            name = os.path.basename(self.path) if self.path else "Untitled"
            mark = "• " if self.dirty else ""
            self.set_title(f"{mark}{name}")
            self.save_action.set_enabled(self.dirty)
            self.save_button.set_sensitive(self.dirty)

        def on_close_request(self, *_args):
            if self._closing:
                return False
            if self.dirty:
                self.confirm(self.force_close)
                return True
            self.persist_state()
            self.shutdown()
            return False

        def force_close(self):
            self._closing = True
            self.dirty = False
            self.persist_state()
            self.shutdown()
            self.close()

        def shutdown(self):
            if self._render_id:
                GLib.source_remove(self._render_id)
                self._render_id = 0
            if self.monitor is not None:
                self.monitor.cancel()
                self.monitor = None

        def persist_state(self):
            width = self.get_width()
            height = self.get_height()
            data = {
                "width": width if width > 200 else 1200,
                "height": height if height > 200 else 800,
                "maximized": self.is_maximized(),
                "paned": self.paned.get_position(),
                "style": self.style,
            }
            directory = os.path.dirname(STATE_PATH)
            os.makedirs(directory, exist_ok=True)
            temporary = STATE_PATH + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            os.replace(temporary, STATE_PATH)

    def markdown_filters():
        store = Gio.ListStore.new(Gtk.FileFilter)
        markdown = Gtk.FileFilter()
        markdown.set_name("Markdown")
        for pattern in ("*.md", "*.markdown", "*.mdown", "*.mkd"):
            markdown.add_pattern(pattern)
        store.append(markdown)
        everything = Gtk.FileFilter()
        everything.set_name("All files")
        everything.add_pattern("*")
        store.append(everything)
        return store

    class PreviewApp(Adw.Application):
        def __init__(self):
            super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)

        def do_startup(self):
            Adw.Application.do_startup(self)
            Gtk.Window.set_default_icon_name("text-markdown")
            provider = Gtk.CssProvider()
            provider.load_from_data(
                b"paned > separator { min-width: 8px; background: @borders; }",
                -1,
            )
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

        def do_activate(self):
            if not self.get_windows():
                PreviewWindow(self, None).present()

        def do_open(self, files, _n_files, _hint):
            opened = False
            for gfile in files:
                path = gfile.get_path()
                if not path:
                    continue
                PreviewWindow(self, path).present()
                opened = True
            if not opened:
                self.do_activate()

    GLib.set_prgname("mdpreview")
    app = PreviewApp()
    return app.run(argv)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    raise SystemExit(main(sys.argv))
