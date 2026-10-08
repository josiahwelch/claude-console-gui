"""Main application window, laid out like the Claude desktop app: a sidebar of
sessions on the left and the selected session's chat on the right."""

import itertools
import os
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

from . import recents
from .chat import MODELS, PERMISSION_MODES, ChatView, Composer, make_dropdown

APP_ICON = Path(__file__).resolve().parent.parent / "data" / "icons" / "claude-console-gui.svg"
WELCOME = "welcome"


def _display_path(folder):
    home = os.path.expanduser("~")
    if folder == home:
        return "~"
    if folder.startswith(home + os.sep):
        return "~" + folder[len(home):]
    return folder


def _folder_name(folder):
    return os.path.basename(folder.rstrip(os.sep)) or folder


class _Session:
    """One Claude conversation: its chat view, sidebar row, and title state."""

    _ids = itertools.count(1)

    def __init__(self, folder, on_changed, model=None, permission_mode="default"):
        self.id = f"session-{next(self._ids)}"
        self.folder = folder
        self.custom_title = None
        self.auto_title = ""
        self._on_changed = on_changed

        self.spinner = Gtk.Spinner(visible=False, valign=Gtk.Align.CENTER)
        self.spinner.add_css_class("session-spinner")
        self.title_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.title_label.add_css_class("session-title")
        folder_label = Gtk.Label(
            label=_folder_name(folder), xalign=0, ellipsize=Pango.EllipsizeMode.END
        )
        folder_label.add_css_class("session-folder")
        self.close_button = Gtk.Button(
            icon_name="window-close-symbolic",
            tooltip_text="Close session",
            valign=Gtk.Align.CENTER,
        )
        self.close_button.add_css_class("flat")
        self.close_button.add_css_class("circular")
        self.close_button.add_css_class("session-close")

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        labels.append(self.title_label)
        labels.append(folder_label)

        box = Gtk.Box(spacing=8)
        box.append(labels)
        box.append(self.spinner)
        box.append(self.close_button)

        self.row = Gtk.ListBoxRow(child=box)
        self.row.add_css_class("session-row")
        self.row.session = self

        self.chat = ChatView(
            folder,
            on_title=self._set_auto_title,
            on_busy=self._set_busy,
            model=model,
            permission_mode=permission_mode,
        )
        self._update_title()

    @property
    def title(self):
        return self.custom_title or self.auto_title or "New session"

    def _set_auto_title(self, title):
        self.auto_title = title
        self._update_title()

    def _set_busy(self, busy):
        self.spinner.set_visible(busy)
        self.spinner.set_spinning(busy)

    def rename(self, title):
        self.custom_title = title or None
        self._update_title()

    def _update_title(self):
        self.title_label.set_label(self.title)
        self.row.set_tooltip_text(f"{self.title}\n{_display_path(self.folder)}")
        self._on_changed(self)


class ClaudeConsoleWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Claude Console")
        self.set_default_size(1100, 760)
        self.sessions = []
        folders = recents.load()
        self.welcome_folder = folders[0] if folders else os.path.expanduser("~")

        self.split_view = Adw.OverlaySplitView(
            min_sidebar_width=220,
            max_sidebar_width=300,
            sidebar_width_fraction=0.24,
        )
        self.split_view.set_sidebar(self._build_sidebar())
        self.split_view.set_content(self._build_content())
        self.set_content(self.split_view)

        breakpoint = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 640sp"))
        breakpoint.add_setter(self.split_view, "collapsed", True)
        self.add_breakpoint(breakpoint)

        self._add_action("new-session", lambda *_a: self.show_welcome())
        self._add_action("open-folder", lambda *_a: self._choose_folder())
        self._add_action("close-current", lambda *_a: self._close_current())
        self._add_action("next-session", lambda *_a: self._cycle(1))
        self._add_action("previous-session", lambda *_a: self._cycle(-1))
        self._add_action("toggle-sidebar", lambda *_a: self._toggle_sidebar())
        self._add_action("stop", lambda *_a: self._stop_current())
        self._add_action("rename-session", self._on_rename_action, "s")
        self._add_action("close-session", self._on_close_action, "s")

        self.connect("close-request", self._on_close_request)
        self.show_welcome()

    def _add_action(self, name, callback, parameter_type=None):
        variant_type = GLib.VariantType(parameter_type) if parameter_type else None
        action = Gio.SimpleAction.new(name, variant_type)
        action.connect("activate", callback)
        self.add_action(action)

    def _on_close_request(self, _window):
        for session in self.sessions:
            session.chat.shutdown()
        # The application holds itself alive (so a failed launch can't quit it
        # silently); closing the window is the explicit way out.
        self.get_application().quit()
        return False

    # -- Layout ---------------------------------------------------------------

    def _build_sidebar(self):
        brand = Gtk.Label(label="Claude")
        brand.add_css_class("brand")

        header = Adw.HeaderBar(show_end_title_buttons=False, title_widget=brand)
        header.add_css_class("sidebar-header")

        new_button = Gtk.Button(
            child=Adw.ButtonContent(
                icon_name="list-add-symbolic", label="New session", halign=Gtk.Align.START
            ),
            action_name="win.new-session",
            tooltip_text="New session (Ctrl+Shift+T)",
        )
        new_button.add_css_class("new-session")

        heading = Gtk.Label(label="Sessions", xalign=0)
        heading.add_css_class("sidebar-heading")

        self.session_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.session_list.add_css_class("navigation-sidebar")
        self.session_list.connect("row-selected", self._on_row_selected)

        self.row_menu = Gtk.PopoverMenu(has_arrow=False, halign=Gtk.Align.START)
        self.row_menu.set_parent(self.session_list)
        right_click = Gtk.GestureClick(button=3)
        right_click.connect("pressed", self._on_session_list_right_click)
        self.session_list.add_controller(right_click)

        scroller = Gtk.ScrolledWindow(
            child=self.session_list,
            vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(new_button)
        box.append(heading)
        box.append(scroller)

        sidebar = Adw.ToolbarView(content=box)
        sidebar.add_top_bar(header)
        sidebar.add_css_class("sidebar-pane")
        return sidebar

    def _build_content(self):
        sidebar_button = Gtk.ToggleButton(
            icon_name="sidebar-show-symbolic",
            tooltip_text="Toggle sidebar (Ctrl+Shift+B)",
        )
        self.split_view.bind_property(
            "show-sidebar",
            sidebar_button,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        self.window_title = Adw.WindowTitle(title="Claude Console")
        header = Adw.HeaderBar(title_widget=self.window_title)
        header.pack_start(sidebar_button)
        header.add_css_class("content-header")

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(self._build_welcome(), WELCOME)

        content = Adw.ToolbarView(content=self.stack)
        content.add_top_bar(header)
        content.add_css_class("content-pane")
        return content

    def _build_welcome(self):
        if APP_ICON.exists():
            logo = Gtk.Image.new_from_file(str(APP_ICON))
        else:
            logo = Gtk.Image.new_from_icon_name("utilities-terminal-symbolic")
        logo.set_pixel_size(48)

        greeting = Gtk.Label(label="What are we working on?", wrap=True, justify=Gtk.Justification.CENTER)
        greeting.add_css_class("greeting")

        title_row = Gtk.Box(spacing=14, halign=Gtk.Align.CENTER)
        title_row.append(logo)
        title_row.append(greeting)

        self.welcome_composer = Composer(
            "Describe a task or ask a question…", self._on_welcome_submit
        )
        self.welcome_composer.add_css_class("welcome-composer")

        self.folder_label = Gtk.Label(ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=28)
        folder_content = Gtk.Box(spacing=6)
        folder_content.append(Gtk.Image.new_from_icon_name("folder-symbolic"))
        folder_content.append(self.folder_label)
        folder_content.append(Gtk.Image.new_from_icon_name("pan-down-symbolic"))

        self.folder_popover = Gtk.Popover(has_arrow=False)
        self.folder_popover.add_css_class("menu")
        self.folder_popover.connect("show", lambda _p: self._refresh_folder_menu())
        folder_button = Gtk.MenuButton(
            child=folder_content,
            popover=self.folder_popover,
            tooltip_text="Project folder",
        )
        folder_button.add_css_class("flat")
        folder_button.add_css_class("composer-dropdown")

        self.welcome_mode = make_dropdown(PERMISSION_MODES, "Permission mode")
        self.welcome_model = make_dropdown(MODELS, "Model")
        self.welcome_composer.controls.append(folder_button)
        self.welcome_composer.controls.append(self.welcome_mode)
        self.welcome_composer.controls.append(self.welcome_model)

        hint = Gtk.Label(label="Enter to send · Shift+Enter for a new line")
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=22,
            valign=Gtk.Align.CENTER,
            margin_top=36,
            margin_bottom=36,
            margin_start=24,
            margin_end=24,
        )
        box.append(title_row)
        box.append(self.welcome_composer)
        box.append(hint)

        self._update_folder_label()
        clamp = Adw.Clamp(child=box, maximum_size=680)
        return Gtk.ScrolledWindow(child=clamp, hscrollbar_policy=Gtk.PolicyType.NEVER)

    def _update_folder_label(self):
        self.folder_label.set_label(_folder_name(self.welcome_folder))
        self.folder_label.get_parent().get_parent().set_tooltip_text(_display_path(self.welcome_folder))

    def _refresh_folder_menu(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        folders = recents.load()
        home = os.path.expanduser("~")
        if home not in folders:
            folders.append(home)

        if folders:
            heading = Gtk.Label(label="Recent folders", xalign=0)
            heading.add_css_class("menu-heading")
            box.append(heading)
        for folder in folders:
            button = Gtk.Button()
            button.add_css_class("flat")
            button.add_css_class("folder-item")
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            name = Gtk.Label(label=_folder_name(folder), xalign=0)
            path = Gtk.Label(label=_display_path(folder), xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE)
            path.add_css_class("dim-label")
            path.add_css_class("caption")
            content.append(name)
            content.append(path)
            button.set_child(content)
            button.connect("clicked", lambda _b, f=folder: self._pick_welcome_folder(f))
            box.append(button)

        box.append(Gtk.Separator())
        choose = Gtk.Button(label="Choose another folder…", action_name="win.open-folder")
        choose.add_css_class("flat")
        choose.add_css_class("folder-item")
        choose.connect("clicked", lambda _b: self.folder_popover.popdown())
        box.append(choose)
        self.folder_popover.set_child(box)

    def _pick_welcome_folder(self, folder):
        self.welcome_folder = folder
        self._update_folder_label()
        self.folder_popover.popdown()
        self.welcome_composer.grab_focus()

    def _on_welcome_submit(self, text):
        mode = PERMISSION_MODES[self.welcome_mode.get_selected()][1]
        model = MODELS[self.welcome_model.get_selected()][1]
        session = self.start_session(self.welcome_folder, model=model, permission_mode=mode)
        session.chat.send(text)

    # -- Sessions -------------------------------------------------------------

    def show_welcome(self):
        self.session_list.unselect_all()
        self.stack.set_visible_child_name(WELCOME)
        self.window_title.set_title("New session")
        self.window_title.set_subtitle("")
        self.welcome_composer.grab_focus()
        if self.split_view.get_collapsed():
            self.split_view.set_show_sidebar(False)

    def start_session(self, folder, model=None, permission_mode="default"):
        recents.add(folder)
        session = _Session(folder, self._on_session_changed, model=model, permission_mode=permission_mode)
        self.sessions.append(session)
        session.close_button.connect("clicked", lambda _b: self.close_session(session))

        self.stack.add_named(session.chat, session.id)
        self.session_list.prepend(session.row)
        self.session_list.select_row(session.row)
        return session

    def close_session(self, session):
        if session not in self.sessions:
            return
        session.chat.shutdown()
        index = self.sessions.index(session)
        self.sessions.remove(session)
        was_selected = self.session_list.get_selected_row() is session.row
        self.session_list.remove(session.row)
        self.stack.remove(session.chat)

        if not was_selected:
            return
        if self.sessions:
            neighbor = self.sessions[min(index, len(self.sessions) - 1)]
            self.session_list.select_row(neighbor.row)
        else:
            self.show_welcome()

    def _current_session(self):
        row = self.session_list.get_selected_row()
        return row.session if row is not None else None

    def _session_by_id(self, session_id):
        return next((s for s in self.sessions if s.id == session_id), None)

    def _close_current(self):
        session = self._current_session()
        if session is not None:
            self.close_session(session)

    def _stop_current(self):
        session = self._current_session()
        if session is not None:
            session.chat.stop_turn()

    def _cycle(self, step):
        if not self.sessions:
            return
        rows = [self.session_list.get_row_at_index(i) for i in range(len(self.sessions))]
        current = self.session_list.get_selected_row()
        index = rows.index(current) + step if current in rows else 0
        self.session_list.select_row(rows[index % len(rows)])

    def _toggle_sidebar(self):
        self.split_view.set_show_sidebar(not self.split_view.get_show_sidebar())

    def _on_row_selected(self, _list, row):
        if row is None:
            return
        session = row.session
        self.stack.set_visible_child_name(session.id)
        self._update_window_title(session)
        session.chat.composer.grab_focus()
        if self.split_view.get_collapsed():
            self.split_view.set_show_sidebar(False)

    def _on_session_changed(self, session):
        if self._current_session() is session:
            self._update_window_title(session)

    def _update_window_title(self, session):
        self.window_title.set_title(session.title)
        self.window_title.set_subtitle(_display_path(session.folder))

    # -- Folder picker --------------------------------------------------------

    def _choose_folder(self):
        dialog = Gtk.FileDialog(title="Choose a project folder", modal=True)
        dialog.set_initial_folder(Gio.File.new_for_path(self.welcome_folder))

        def on_chosen(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
            except GLib.Error:
                return  # cancelled
            if folder is not None and folder.get_path():
                self.show_welcome()
                self._pick_welcome_folder(folder.get_path())

        dialog.select_folder(self, None, on_chosen)

    # -- Context menu, rename -------------------------------------------------

    def _on_session_list_right_click(self, _gesture, _n_press, x, y):
        row = self.session_list.get_row_at_y(int(y))
        if row is None:
            return
        target = GLib.Variant.new_string(row.session.id)
        menu = Gio.Menu()
        for label, action in (("Rename…", "win.rename-session"), ("Close", "win.close-session")):
            item = Gio.MenuItem.new(label, None)
            item.set_action_and_target_value(action, target)
            menu.append_item(item)

        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self.row_menu.set_menu_model(menu)
        self.row_menu.set_pointing_to(rect)
        self.row_menu.popup()

    def _on_close_action(self, _action, parameter):
        session = self._session_by_id(parameter.get_string())
        if session is not None:
            self.close_session(session)

    def _on_rename_action(self, _action, parameter):
        session = self._session_by_id(parameter.get_string())
        if session is None:
            return

        entry = Gtk.Entry(text=session.title, activates_default=True)

        dialog = Adw.AlertDialog(heading="Rename Session")
        dialog.set_body("Leave empty to name it after your first message.")
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("rename", "Rename")
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("rename")
        dialog.set_close_response("cancel")

        def on_response(_dialog, response):
            if response == "rename":
                session.rename(entry.get_text().strip())

        dialog.connect("response", on_response)
        dialog.present(self)
