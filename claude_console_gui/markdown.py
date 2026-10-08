"""A small Markdown renderer for chat messages: prose becomes Pango markup in
selectable labels, fenced code becomes a monospace card with a copy button."""

import re

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gdk, Gtk, Pango

_FENCE = re.compile(r"^\s*(```|~~~)\s*([\w+#.-]*)\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")

_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_ITALIC = re.compile(r"(?<![\w*])([*_])(?=\S)(.+?)(?<=\S)\1(?![\w*])")
_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")

_HEADING_SIZES = {1: "x-large", 2: "large", 3: "large"}


def inline(text):
    """Convert inline Markdown to Pango markup. Code spans and links are pulled
    out first so their contents aren't touched by emphasis rules."""
    stash = []

    def keep(markup):
        stash.append(markup)
        # Private-use delimiters: GLib truncates strings at NUL characters.
        return f"\ue000{len(stash) - 1}\ue001"

    text = _CODE_SPAN.sub(
        lambda m: keep(f'<span font_family="monospace" background="#3A3936"> {GLib.markup_escape_text(m.group(1))} </span>'),
        text,
    )
    text = _LINK.sub(
        lambda m: keep(
            f'<a href="{GLib.markup_escape_text(m.group(2))}">{GLib.markup_escape_text(m.group(1))}</a>'
        ),
        text,
    )
    text = GLib.markup_escape_text(text)
    text = _BOLD.sub(r"<b>\2</b>", text)
    text = _ITALIC.sub(r"<i>\2</i>", text)
    text = _STRIKE.sub(r"<s>\1</s>", text)
    return re.sub("\ue000(\\d+)\ue001", lambda m: stash[int(m.group(1))], text)


def safe_markup(markup):
    """Return markup unchanged if Pango accepts it, else the text with tags
    stripped, so a mis-nested emphasis never blanks a label."""
    # GtkLabel handles <a> itself; Pango's parser doesn't know it.
    without_links = re.sub(r"</?a\b[^>]*>", "", markup)
    try:
        Pango.parse_markup(without_links, -1, "\0")
    except GLib.Error:
        return GLib.markup_escape_text(re.sub(r"<[^>]*>", "", markup))
    return markup


def parse(text):
    """Split Markdown into blocks: ("prose", markup), ("code", lang, text),
    ("table", text) and ("rule",)."""
    blocks = []
    prose = []
    lines = text.split("\n")
    i = 0

    def flush():
        while prose and not prose[-1].strip():
            prose.pop()
        if prose:
            blocks.append(("prose", "\n".join(prose)))
        prose.clear()

    while i < len(lines):
        line = lines[i]

        fence = _FENCE.match(line)
        if fence:
            flush()
            lang = fence.group(2)
            body = []
            i += 1
            while i < len(lines) and not _FENCE.match(lines[i]):
                body.append(lines[i])
                i += 1
            blocks.append(("code", lang, "\n".join(body)))
            i += 1
            continue

        if "|" in line and i + 1 < len(lines) and _TABLE_SEPARATOR.match(lines[i + 1]):
            flush()
            rows = []
            while i < len(lines) and "|" in lines[i]:
                if not _TABLE_SEPARATOR.match(lines[i]):
                    rows.append([cell.strip() for cell in lines[i].strip().strip("|").split("|")])
                i += 1
            blocks.append(("table", rows))
            continue

        if _RULE.match(line):
            flush()
            blocks.append(("rule",))
            i += 1
            continue

        if not line.strip():
            if prose and prose[-1] != "":
                prose.append("")
            i += 1
            continue

        heading = _HEADING.match(line)
        bullet = _BULLET.match(line)
        numbered = _NUMBERED.match(line)
        quote = _QUOTE.match(line)
        if heading:
            level = len(heading.group(1))
            size = _HEADING_SIZES.get(level, "medium")
            if prose and prose[-1] != "":
                prose.append("")
            prose.append(f'<span size="{size}" weight="bold">{inline(heading.group(2))}</span>')
        elif bullet:
            indent = "    " * (len(bullet.group(1)) // 2)
            prose.append(f"{indent}  •  {inline(bullet.group(2))}")
        elif numbered:
            indent = "    " * (len(numbered.group(1)) // 2)
            prose.append(f"{indent}  {numbered.group(2)}.  {inline(numbered.group(3))}")
        elif quote:
            prose.append(f'<span foreground="#A6A39A">┃  <i>{inline(quote.group(1))}</i></span>')
        else:
            prose.append(inline(line))
        i += 1

    flush()
    return blocks


def _copy_to_clipboard(widget, text):
    Gdk.Display.get_default().get_clipboard().set(text)


class _CodeBlock(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("code-block")
        self._text = ""

        self.lang_label = Gtk.Label(xalign=0, hexpand=True)
        self.lang_label.add_css_class("code-lang")
        copy = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Copy")
        copy.add_css_class("flat")
        copy.connect("clicked", lambda b: _copy_to_clipboard(b, self._text))
        header = Gtk.Box()
        header.add_css_class("code-header")
        header.append(self.lang_label)
        header.append(copy)

        self.code_label = Gtk.Label(xalign=0, selectable=True, wrap=False)
        self.code_label.add_css_class("code-text")
        scroller = Gtk.ScrolledWindow(
            child=self.code_label,
            vscrollbar_policy=Gtk.PolicyType.NEVER,
            propagate_natural_height=True,
        )
        self.append(header)
        self.append(scroller)

    def update(self, lang, text):
        self._text = text
        self.lang_label.set_label(lang or "code")
        self.code_label.set_label(text)


class _Table(Gtk.Grid):
    def __init__(self):
        super().__init__(column_spacing=0, row_spacing=0)
        self.add_css_class("md-table")
        self._rows = None

    def update(self, rows):
        if rows == self._rows:
            return
        self._rows = rows
        while (child := self.get_first_child()) is not None:
            self.remove(child)
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                label = Gtk.Label(xalign=0, wrap=True, selectable=True, use_markup=True)
                label.set_markup(safe_markup(f"<b>{inline(cell)}</b>" if r == 0 else inline(cell)))
                label.add_css_class("md-cell")
                if r == 0:
                    label.add_css_class("md-header-cell")
                self.attach(label, c, r, 1, 1)


def _prose_label():
    label = Gtk.Label(
        xalign=0,
        wrap=True,
        wrap_mode=Pango.WrapMode.WORD_CHAR,
        selectable=True,
        use_markup=True,
    )
    label.add_css_class("md-prose")
    return label


class MarkdownView(Gtk.Box):
    """Renders Markdown, reusing child widgets so repeated set_text() calls
    while a reply streams in don't rebuild everything."""

    def __init__(self, text=""):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("markdown")
        self._children = []  # (kind, widget)
        self.text = ""
        if text:
            self.set_text(text)

    def set_text(self, text):
        self.text = text
        blocks = parse(text)
        for index, block in enumerate(blocks):
            kind = block[0]
            if index < len(self._children) and self._children[index][0] == kind:
                widget = self._children[index][1]
            else:
                widget = self._make(kind)
                if index < len(self._children):
                    self.remove(self._children[index][1])
                    sibling = self._children[index - 1][1] if index else None
                    self.insert_child_after(widget, sibling)
                    self._children[index] = (kind, widget)
                else:
                    self.append(widget)
                    self._children.append((kind, widget))
            self._fill(widget, block)
        for _kind, widget in self._children[len(blocks):]:
            self.remove(widget)
        del self._children[len(blocks):]

    def _make(self, kind):
        if kind == "code":
            return _CodeBlock()
        if kind == "table":
            return _Table()
        if kind == "rule":
            return Gtk.Separator()
        return _prose_label()

    def _fill(self, widget, block):
        kind = block[0]
        if kind == "code":
            widget.update(block[1], block[2])
        elif kind == "table":
            widget.update(block[1])
        elif kind == "prose":
            widget.set_markup(safe_markup(block[1]))
