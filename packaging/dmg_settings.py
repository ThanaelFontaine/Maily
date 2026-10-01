# dmgbuild settings of the macOS disk image (Maily-X.Y.Z-macos-arm64.dmg).
# Used by scripts/build_dmg.sh:
#   dmgbuild -s packaging/dmg_settings.py -D app=PATH/Maily.app \
#            -D background=DIR/background.png "Maily" OUT.dmg
# Documentation: https://dmgbuild.readthedocs.io/en/latest/settings.html
#
# Opening the image shows a window with a 640 x 400 content area: Maily on the left, a shortcut to
# /Applications on the right, and the background (packaging/make_dmg_background.py)
# with an arrow and "Drag Maily to Applications". Coordinates are the icon
# centers, in points, from the top left corner of the window.
import os.path

application = defines["app"]  # noqa: F821  (injected by dmgbuild)
appname = os.path.basename(application)

# Compressed read-only image (zlib, readable by every supported macOS).
format = "UDZO"
filesystem = "HFS+"
# Size computed by dmgbuild from the content.

files = [application]
symlinks = {"Applications": "/Applications"}
hide_extensions = [appname]

# Volume icon: the Maily icon.
icon = defines.get("icon")  # noqa: F821

background = defines["background"]  # noqa: F821  (background@2x.png next to it)
# The frame size includes the title bar (about 30 points).
window_rect = ((200, 120), (640, 430))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
show_icon_preview = False
arrange_by = None
grid_offset = (0, 0)
grid_spacing = 100
label_pos = "bottom"
text_size = 14
icon_size = 128
icon_locations = {
    appname: (160, 200),
    "Applications": (480, 200),
}
