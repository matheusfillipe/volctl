"""
OSD volume overlay

A transparent OSD volume indicator.

Various code snippets taken from https://github.com/kozec/sc-controller
"""

import math
from pathlib import Path

import cairo
import gi
from gi.repository import Gdk, GdkX11, GLib, Gtk

import volctl.xwrappers as X

gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg


class VolumeOverlay(Gtk.Window):
    """Window that displays volume sliders."""

    BASE_WIDTH = 300
    BASE_HEIGHT = 250
    BASE_FONT_SIZE = 42
    BASE_LINE_WIDTH = 5
    SCREEN_MARGIN = 64
    BASE_PADDING = 24
    BG_OPACITY = 0.93
    BG_CORNER_RADIUS = 20
    MUTE_OPACITY = 0.2
    TEXT_OPACITY = 0.8
    NUM_BARS = 16

    def __init__(self, volctl):
        super().__init__()
        self._volctl = volctl
        self.position = -self.SCREEN_MARGIN, -self.SCREEN_MARGIN
        self.osd_position = self._volctl.settings.get_string("osd-position")

        scale = self._volctl.settings.get_int("osd-scale") / 100
        self.scale = scale
        self._width = int(self.BASE_WIDTH * scale)
        self._height = int(self.BASE_HEIGHT * scale)
        self._font_size = int(self.BASE_FONT_SIZE * scale)
        self._line_width = self.BASE_LINE_WIDTH * scale
        self._padding = int(self.BASE_PADDING * scale)
        self._corner_radius = int(self.BG_CORNER_RADIUS * scale)

        self.set_default_size(self._width, self._height)
        self._volume = 0
        self._mute = False
        self._hide_timeout = None
        self._fadeout_timeout = None
        self._opacity = 1.0

        self.set_decorated(False)
        self.stick()
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_resizable(False)

        self.screen = self.get_screen()
        self.visual = self.screen.get_rgba_visual()
        if self.visual is not None and self.screen.is_composited():
            self._compositing = True
            self.set_visual(self.visual)
        else:
            self._compositing = False
        self.set_app_paintable(True)
        self.connect("draw", self._draw_osd)

        self.realize()
        self.get_window().set_override_redirect(True)
        self._move_to_position(self.osd_position)
        Gtk.Window.show(self)
        self._make_window_clickthrough()

    def update_values(self, volume, mute):
        """Remember current volume and mute values."""
        self._volume = volume
        self._mute = mute
        self._unhide()
        if self._hide_timeout is not None:
            GLib.Source.remove(self._hide_timeout)
        self._hide_timeout = GLib.timeout_add(
            self._volctl.settings.get_int("osd-timeout"), self._cb_hide_timeout
        )

    def _move_to_position(self, position):
        # Adjusts position for currently active screen (display).
        xpos, ypos = 0, 0
        marginx, marginy = self.position
        width, height = self._get_window_size()
        swidth = Gdk.Screen.width()
        sheight = Gdk.Screen.height()
        geometry = self._get_active_screen_geometry()
        if geometry:
            xpos = geometry.x
            ypos = geometry.y
            swidth = geometry.width
            sheight = geometry.height

        yname, xname = position.split("-")

        # Caluclate x, y coords

        if xname == "left":
            xpos = -marginx + xpos
        elif xname == "center":
            xpos = (swidth - width) / 2 + xpos
        elif xname == "right":
            xpos = marginx + xpos + swidth - width
        else:
            raise ValueError("Got unknown x position for OSD.")

        if yname == "top":
            ypos = -marginy + ypos
        elif yname == "center":
            ypos = (sheight - height) / 2 + ypos
        elif yname == "bottom":
            ypos = marginy + ypos + sheight - height
        else:
            raise ValueError("Got unknown y position for OSD.")

        self.move(xpos / 2 + 30, ypos / 2 + 60)

    def _draw_osd(self, _, cairo_r):
        """Draw on-screen volume display."""
        mute_opacity = self.MUTE_OPACITY if self._mute else 1.0
        xcenter = self._width / 2

        # Background
        deg = math.pi / 180.0
        cairo_r.new_sub_path()
        cairo_r.arc(
            self._width - self._corner_radius,
            self._corner_radius,
            self._corner_radius,
            -90 * deg,
            0,
        )
        cairo_r.arc(
            self._width - self._corner_radius,
            self._height - self._corner_radius,
            self._corner_radius,
            0,
            90 * deg,
        )
        cairo_r.arc(
            self._corner_radius,
            self._height - self._corner_radius,
            self._corner_radius,
            90 * deg,
            180 * deg,
        )
        cairo_r.arc(
            self._corner_radius,
            self._corner_radius,
            self._corner_radius,
            180 * deg,
            270 * deg,
        )
        cairo_r.close_path()

        cairo_r.set_source_rgba(0.13, 0.145, 0.18, self.BG_OPACITY * self._opacity)
        cairo_r.set_operator(cairo.OPERATOR_SOURCE)
        cairo_r.fill()
        cairo_r.set_operator(cairo.OPERATOR_OVER)

        # Color
        cairo_r.set_source_rgba(
            1.0, 1.0, 1.0, self.TEXT_OPACITY * mute_opacity * self._opacity
        )

        # Text
        text = f"{round(100 * self._volume)} %"
        cairo_r.select_font_face("sans-serif")
        cairo_r.set_font_size(self._font_size)
        _, _, text_width, text_height, _, _ = cairo_r.text_extents(text)
        cairo_r.move_to(xcenter - text_width / 2, self._height - self._padding)
        cairo_r.show_text(text)

        # Volume indicator
        icon = Rsvg.Handle().new_from_file(
            str(Path(__file__).parent / "icons/volume_muted.svg")
            if self._mute
            else str(Path(__file__).parent / "icons/volume_off.svg")
            if self._volume <= 0.1
            else str(Path(__file__).parent / "icons/volume_low.svg")
            if self._volume < 0.25
            else str(Path(__file__).parent / "icons/volume_medium.svg")
            if self._volume < 0.5
            else str(Path(__file__).parent / "icons/volume_high.svg")
        )
        ratio = icon.props.em / icon.props.dpi_x
        icon.set_dpi(192 / ratio)
        dim = icon.get_dimensions()
        rec = Rsvg.Rectangle()
        rec.width = dim.width * self.scale
        rec.height = dim.height * self.scale
        rec.x = xcenter - dim.width / 2
        rec.y = self._padding
        icon.render_document(cairo_r, rec)

        # Draw progress bar
        cairo_r.set_source_rgba(0.2, 0.2, 0.2, self.BG_OPACITY * self._opacity)
        height = 10
        y = -80
        cairo_r.rectangle(
            self._padding,
            self._height - height + y,
            self._width - self._padding * 2,
            height,
        )
        cairo_r.fill()
        cairo_r.set_source_rgba(1, 1, 1, mute_opacity)
        height = 8
        cairo_r.rectangle(
            self._padding,
            self._height - height + y - 1,
            (self._width - self._padding * 2) * self._volume,
            height,
        )
        cairo_r.fill()
        # ind_height = self._height - 3 * self._padding - text_height
        # outer_radius = ind_height / 2
        # inner_radius = outer_radius / 1.618
        # bars = min(round(self.NUM_BARS * self._volume), self.NUM_BARS)
        # cairo_r.set_line_width(self._line_width)
        # cairo_r.set_line_cap(cairo.LINE_CAP_ROUND)
        # for i in range(bars):
        #     cairo_r.identity_matrix()
        #     cairo_r.translate(xcenter, self._padding + ind_height / 2)
        #     cairo_r.rotate(math.pi + 2 * math.pi / self.NUM_BARS * i)
        #     cairo_r.move_to(0.0, -inner_radius)
        #     cairo_r.line_to(0.0, -outer_radius)
        #     cairo_r.stroke()

    def _make_window_clickthrough(self):
        """Make events pass through window."""
        dpy = X.Display(hash(GdkX11.x11_get_default_xdisplay()))
        try:
            xid = self.get_window().get_xid()
        except AttributeError:
            # Probably on Wayland
            return
        win = X.XID(xid)
        reg = X.create_region(dpy, None, 0)
        X.set_window_shape_region(dpy, win, X.SHAPE_BOUNDING, 0, 0, 0)
        X.set_window_shape_region(dpy, win, X.SHAPE_INPUT, 0, 0, reg)
        X.destroy_region(dpy, reg)

    def _get_active_screen_geometry(self):
        """
        Returns geometry of active screen or None if active screen
        cannot be determined.
        """
        screen = self.get_window().get_screen()
        active_window = screen.get_active_window()
        if active_window:
            monitor = screen.get_monitor_at_window(active_window)
            if monitor is not None:
                return screen.get_monitor_geometry(monitor)
        return None

    def _get_window_size(self):
        return self.get_window().get_width(), self.get_window().get_height()

    def _hide(self):
        if self._compositing:
            self._fadeout_timeout = GLib.timeout_add(30, self._cb_fadeout_timeout)
        else:
            self.destroy()

    def _unhide(self):
        if self._fadeout_timeout is not None:
            GLib.Source.remove(self._fadeout_timeout)
            self._fadeout_timeout = None
        self._move_to_position(self.osd_position)
        self._opacity = 1.0
        self.queue_draw()

    def _cb_fadeout_timeout(self):
        self._opacity -= 0.05
        self.queue_draw()
        if self._opacity >= 0:
            return True
        self._opacity = 0.0
        self._fadeout_timeout = None
        self.destroy()
        return False

    def _cb_hide_timeout(self):
        self._hide_timeout = None
        self._hide()
