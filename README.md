# mdpreview

Source on the left, rendered Markdown on the right. Drag the divider.

Save writes the source buffer back unchanged. The preview is GitHub-flavored Markdown via cmark-gfm: tables, task lists, fenced code, alerts, and images. The header switches the styling between GitHub and GitBook. GitBook `{% hint %}` tags are not parsed. Light and dark follow the desktop.

Images next to the file show in the preview. Remote image URLs are loaded. An `http` link opens in the browser. A relative link to another Markdown file opens in this app.

GTK 4, libadwaita, and WebKitGTK. Tested on Ubuntu 24.04.

## Install

```bash
sudo apt install python3-gi python3-cmarkgfm python3-pygments gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-webkit-6.0 gir1.2-gtksource-5
install -m 755 mdpreview.py ~/.local/bin/mdpreview
cp mdpreview.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications
xdg-mime default mdpreview.desktop text/markdown text/x-markdown
```

`~/.local/bin` has to be on `PATH`. The desktop file runs `mdpreview`.

| Key | Action |
| --- | --- |
| Ctrl+O | Open |
| Ctrl+S | Save |
| Ctrl+Shift+S | Save as |

Drop a file on the window to open it. Window size, divider position, and style are stored in `~/.config/mdpreview/state.json`.

```bash
python3 mdpreview.py --self-test
```

Licensed under MIT.
