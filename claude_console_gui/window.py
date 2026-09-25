"""Main application window: tabbed Claude terminal sessions."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

from .terminal import new_terminal, spawn_claude


class ClaudeConsoleWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Claude Console")
        self.set_default_size(1000, 650)

        self.tab_view = Adw.TabView()
        self.tab_view.connect("close-page", self._on_close_page)
        self.tab_view.connect("setup-menu", self._on_setup_tab_menu)
        self._menu_page = None

        tab_menu = Gio.Menu()
        tab_menu.append("Rename Tab…", "win.rename-tab")
        self.tab_view.set_menu_model(tab_menu)

        tab_bar = Adw.TabBar(view=self.tab_view, autohide=False)

        new_tab_button = Gtk.Button(
            icon_name="tab-new-symbolic",
            tooltip_text="New Claude session (Ctrl+Shift+T)",
        )
        new_tab_button.connect("clicked", lambda _button: self.new_tab())

        header = Adw.HeaderBar()
        header.pack_start(new_tab_button)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.add_top_bar(tab_bar)
        toolbar_view.set_content(self.tab_view)
        self.set_content(toolbar_view)

        self._add_action("new-tab", lambda *_a: self.new_tab())
        self._add_action("close-tab", lambda *_a: self.close_current_tab())
        self._add_action("rename-tab", lambda *_a: self._rename_tab())

        self.new_tab()

    def _add_action(self, name, callback):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)

    def new_tab(self, working_directory=None):
        terminal = new_terminal()
        page = self.tab_view.append(terminal)
        page.set_title("Claude")

        def on_exit(_term, _status):
            self.tab_view.close_page(page)

        spawn_claude(terminal, working_directory, on_exit=on_exit)
        self.tab_view.set_selected_page(page)
        return page

    def close_current_tab(self):
        page = self.tab_view.get_selected_page()
        if page is not None:
            self.tab_view.close_page(page)

    def _on_close_page(self, tab_view, page):
        tab_view.close_page_finish(page, True)
        return True

    def _on_setup_tab_menu(self, _tab_view, page):
        self._menu_page = page

    def _rename_tab(self):
        page = self._menu_page or self.tab_view.get_selected_page()
        if page is None:
            return

        entry = Gtk.Entry(text=page.get_title())
        entry.set_activates_default(True)

        dialog = Adw.AlertDialog(heading="Rename Tab")
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("rename", "Rename")
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("rename")
        dialog.set_close_response("cancel")

        def on_response(_dialog, response):
            if response == "rename":
                title = entry.get_text().strip()
                if title:
                    page.set_title(title)

        dialog.connect("response", on_response)
        dialog.present(self)
