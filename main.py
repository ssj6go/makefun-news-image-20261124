#!/usr/bin/env python3
"""Draw the front page of Tuesday 24 November 2026: eight world-news
stories in one 1024x1024 image.

Standard library only. No network, no files read besides this program and
the font table in fontdata.py. Output is deterministic: two runs write
byte-identical PNGs.

The image is a newspaper front page: a masthead, the date in large type,
and eight panels (two columns by four rows), each with a region tag, a
headline, a short summary and a small drawn emblem. The program writes
entry.png into MAKEFUN_OUTPUT_DIR, or /output when that directory exists,
or the current directory otherwise.
"""

import hashlib
import math
import os
import struct
import sys
import zlib

from fontdata import FONT

W = 1024
H = 1024

PAPER = (248, 244, 236)
INK = (20, 24, 31)
NAVY = (14, 42, 71)
CREAM = (245, 237, 216)
MUTED = (96, 92, 84)
RULE = (180, 172, 156)
PANEL_BG = (255, 255, 255)
PANEL_LINE = (201, 194, 180)


# ---------------------------------------------------------------- canvas

class Canvas:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)
        self.fill_rect(0, 0, w, h, bg)

    def set(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i] = color[0]
            self.buf[i + 1] = color[1]
            self.buf[i + 2] = color[2]

    def fill_rect(self, x, y, w, h, color):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.buf[i:i + len(row)] = row

    def hline(self, x, y, w, color, thick=1):
        self.fill_rect(x, y, w, thick, color)

    def vline(self, x, y, h, color, thick=1):
        self.fill_rect(x, y, thick, h, color)

    def line(self, x0, y0, x1, y1, color):
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        x, y = x0, y0
        while True:
            self.set(x, y, color)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    def fill_circle(self, cx, cy, r, color):
        for yy in range(cy - r, cy + r + 1):
            dx = int(math.sqrt(max(0, r * r - (yy - cy) ** 2)))
            self.fill_rect(cx - dx, yy, 2 * dx + 1, 1, color)

    def ring(self, cx, cy, r, color, thick=2):
        for t in range(thick):
            rr = r - t
            for a in range(360):
                rad = math.radians(a)
                self.set(cx + int(rr * math.cos(rad)),
                         cy + int(rr * math.sin(rad)), color)

    def fill_poly(self, pts, color):
        # Scanline polygon fill.
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        for y in range(max(0, min(ys)), min(self.h, max(ys) + 1)):
            xs = []
            n = len(pts)
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    if y1 != y0:
                        xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.fill_rect(int(math.ceil(xs[i])), y,
                               int(math.floor(xs[i + 1])) - int(math.ceil(xs[i])) + 1,
                               1, color)

    def star(self, cx, cy, r_out, r_in, points, color):
        pts = []
        for i in range(points * 2):
            r = r_out if i % 2 == 0 else r_in
            a = math.pi * i / points - math.pi / 2
            pts.append((cx + int(r * math.cos(a)), cy + int(r * math.sin(a))))
        self.fill_poly(pts, color)


def _chunk(kind, data):
    out = struct.pack(">I", len(data)) + kind + data
    out += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return out


def encode_png(cv):
    ihdr = struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0)
    raw = bytearray()
    for y in range(cv.h):
        raw.append(0)
        raw += cv.buf[y * cv.w * 3:(y + 1) * cv.w * 3]
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr)
    png += _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += _chunk(b"IEND", b"")
    return png


# ------------------------------------------------------------------- text

def text_width(font_name, s):
    font = FONT[font_name]
    total = 0
    for ch in s:
        g = font["glyphs"].get(ord(ch))
        if g is None:
            total += font["glyphs"][ord(" ")][0]
        else:
            total += g[0]
    return total


def draw_text(cv, font_name, x, baseline_y, s, color):
    font = FONT[font_name]
    ascent = font["ascent"]
    cx = x
    for ch in s:
        g = font["glyphs"].get(ord(ch))
        if g is None:
            cx += font["glyphs"][ord(" ")][0]
            continue
        adv, w, h, top, hexdata = g
        if w and h:
            data = bytes.fromhex(hexdata)
            gy0 = baseline_y - ascent + top
            for row in range(h):
                for col in range(w):
                    idx = row * w + col
                    if (data[idx // 8] >> (7 - idx % 8)) & 1:
                        cv.set(cx + col, gy0 + row, color)
        cx += adv
    return cx


def draw_text_centered(cv, font_name, cx, baseline_y, s, color):
    draw_text(cv, font_name, cx - text_width(font_name, s) // 2,
              baseline_y, s, color)


def wrap_text(font_name, s, max_w):
    """Greedy word wrap; returns a list of lines."""
    words = s.split(" ")
    lines = []
    cur = ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if text_width(font_name, trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- emblems
# Small drawn emblems, one per story, in a 64x64 box at (x, y).

def emblem_hormuz(cv, x, y):
    blue = (28, 90, 140)
    for k in range(3):
        yy = y + 42 + k * 7
        for xx in range(0, 64, 4):
            cv.set(x + xx, yy + (1 if (xx // 4) % 2 else 0), blue)
            cv.set(x + xx + 1, yy + (1 if (xx // 4) % 2 else 0), blue)
            cv.set(x + xx, yy + 1 + (1 if (xx // 4) % 2 else 0), blue)
    cv.fill_rect(x + 6, y + 26, 46, 11, (30, 30, 34))          # hull
    cv.fill_poly([(x + 6, y + 37), (x + 16, y + 37), (x + 11, y + 44)], (30, 30, 34))
    cv.fill_rect(x + 30, y + 12, 9, 14, (30, 30, 34))          # bridge
    cv.fill_rect(x + 42, y + 16, 5, 10, (158, 43, 37))          # funnel
    cv.fill_rect(x + 32, y + 8, 5, 4, (232, 178, 40))           # flag


def emblem_corvette(cv, x, y):
    cv.fill_rect(x + 4, y + 44, 56, 4, (28, 90, 140))           # sea
    cv.fill_poly([(x + 12, y + 40), (x + 52, y + 40), (x + 46, y + 30),
                  (x + 18, y + 30)], (52, 58, 66))             # hull, listing
    cv.line(x + 30, y + 30, x + 30, y + 14, (52, 58, 66))       # mast
    cv.star(x + 44, y + 14, 12, 5, 8, (232, 148, 24))           # blast
    cv.star(x + 44, y + 14, 6, 2, 8, (250, 214, 90))


def emblem_strike(cv, x, y):
    cv.fill_rect(x + 8, y + 26, 18, 30, (120, 122, 126))        # block A
    cv.fill_rect(x + 30, y + 18, 18, 38, (96, 98, 102))         # block B
    for wy in (30, 40, 50):
        cv.fill_rect(x + 12, wy, 4, 4, (40, 42, 46))
        cv.fill_rect(x + 34, wy - 6, 4, 4, (40, 42, 46))
    cv.star(x + 46, y + 14, 13, 5, 8, (214, 82, 26))            # blast
    cv.star(x + 46, y + 14, 6, 2, 8, (250, 214, 90))
    cv.fill_circle(x + 16, y + 12, 4, (150, 150, 150))          # smoke
    cv.fill_circle(x + 24, y + 8, 5, (170, 170, 170))


def emblem_satellite(cv, x, y):
    cv.ring(x + 32, y + 32, 28, (28, 90, 140), 2)               # orbit
    cv.fill_rect(x + 10, y + 28, 16, 8, (52, 90, 160))          # panel
    cv.fill_rect(x + 38, y + 28, 16, 8, (52, 90, 160))          # panel
    cv.fill_rect(x + 27, y + 24, 10, 16, (30, 30, 34))          # body
    cv.line(x + 32, y + 24, x + 40, y + 14, (30, 30, 34))       # antenna
    cv.fill_circle(x + 41, y + 13, 2, (214, 82, 26))
    cv.fill_circle(x + 52, y + 50, 2, (232, 178, 40))           # stars
    cv.fill_circle(x + 12, y + 12, 2, (232, 178, 40))
    cv.fill_circle(x + 56, y + 16, 1, (28, 90, 140))


def emblem_chip(cv, x, y):
    green = (22, 120, 70)
    cv.fill_rect(x + 16, y + 16, 32, 32, green)                 # die
    cv.fill_rect(x + 24, y + 24, 16, 16, (248, 244, 236))       # core
    cv.fill_rect(x + 28, y + 28, 8, 8, green)
    for k in range(4):
        off = 20 + k * 8
        cv.fill_rect(x + off, y + 8, 3, 8, green)
        cv.fill_rect(x + off, y + 48, 3, 8, green)
        cv.fill_rect(x + 8, y + off, 8, 3, green)
        cv.fill_rect(x + 48, y + off, 8, 3, green)


def emblem_target(cv, x, y):
    cv.ring(x + 32, y + 32, 24, (158, 43, 37), 4)
    cv.ring(x + 32, y + 32, 14, (158, 43, 37), 3)
    cv.fill_circle(x + 32, y + 32, 4, (158, 43, 37))
    cv.line(x + 32, y + 2, x + 32, y + 12, (158, 43, 37))
    cv.line(x + 32, y + 52, x + 32, y + 62, (158, 43, 37))
    cv.line(x + 2, y + 32, x + 12, y + 32, (158, 43, 37))
    cv.line(x + 52, y + 32, x + 62, y + 32, (158, 43, 37))


def emblem_gavel(cv, x, y):
    brown = (120, 84, 44)
    cv.fill_poly([(x + 10, y + 6), (x + 38, y + 20), (x + 30, y + 32),
                  (x + 2, y + 18)], brown)                      # head
    cv.fill_poly([(x + 26, y + 28), (x + 30, y + 26), (x + 52, y + 50),
                  (x + 48, y + 52)], brown)                     # handle
    cv.fill_rect(x + 8, y + 54, 32, 5, (90, 90, 96))            # block


def emblem_eu(cv, x, y):
    cv.fill_circle(x + 32, y + 32, 26, (14, 42, 71))
    for k in range(12):
        a = 2 * math.pi * k / 12 - math.pi / 2
        sx = x + 32 + int(18 * math.cos(a))
        sy = y + 32 + int(18 * math.sin(a))
        cv.star(sx, sy, 4, 2, 5, (232, 196, 60))


EMBLEMS = {
    "hormuz": emblem_hormuz,
    "corvette": emblem_corvette,
    "strike": emblem_strike,
    "satellite": emblem_satellite,
    "chip": emblem_chip,
    "target": emblem_target,
    "gavel": emblem_gavel,
    "eu": emblem_eu,
}


# ---------------------------------------------------------------- stories

PANELS = [
    dict(tag="MIDDLE EAST - US-IRAN", accent=(158, 43, 37), icon="hormuz",
         head="HORMUZ STANDOFF DEEPENS",
         body="Iran threatens tighter control of the Strait of Hormuz until "
              "the US accepts seven conditions. Vance and Rubio meet Qatar's "
              "PM; the US sanctions 25+ shadow-banking entities."),
    dict(tag="UKRAINE - LIBYA", accent=(28, 90, 140), icon="corvette",
         head="UKRAINE SINKS RUSSIAN CORVETTE OFF LIBYA",
         body="Ukrainian sea drones sink the Russian corvette Merkury at its "
              "Benghazi base, in a strike first reported on 24 November. "
              "The UN calls for an independent investigation."),
    dict(tag="UKRAINE - WAR", accent=(196, 96, 24), icon="strike",
         head="RUSSIAN STRIKE HITS ZAPORIZHZHIA",
         body="An overnight strike kills 2 people and injures about 40, "
              "including four children, hitting an apartment block in the "
              "Ukrainian city."),
    dict(tag="SPACE - NATO", accent=(52, 68, 160), icon="satellite",
         head="NATO ON ALERT OVER RUSSIAN SPACE WEAPON",
         body="NATO chief Rutte says the alliance will defend against "
              "threats in space. Western intel says Russia plans "
              "a nuclear satellite launch within weeks; AWACS jets "
              "deploy to Poland."),
    dict(tag="TECH - MARKETS", accent=(22, 120, 70), icon="chip",
         head="HUANG BACK AS NVIDIA CHIEF",
         body="The board unanimously reinstates Jensen Huang as CEO less "
              "than two weeks after he stepped down. Shares jump about 30% "
              "as Wall Street rebounds."),
    dict(tag="GAZA - MIDDLE EAST", accent=(158, 43, 37), icon="target",
         head="ISRAELI STRIKE KILLS HAMAS SECURITY CHIEF",
         body="An Israeli air strike kills Hamas internal security director "
              "Naeem Abu Nahel and six others, including two police "
              "officers, in Gaza."),
    dict(tag="US - COURTS", accent=(110, 68, 150), icon="gavel",
         head="OREGON & VIRGINIA SUE SPACEX OVER GROK",
         body="Two states sue SpaceX over alleged child sexual-abuse images "
              "generated by its Grok chatbot."),
    dict(tag="EUROPE - LAW", accent=(16, 110, 110), icon="eu",
         head="ECHR: STATES MAY EXPEL MIGRANTS IN EMERGENCY",
         body="Europe's human rights court rules states may expel migrants "
              "during a hybrid border emergency."),
]


# ------------------------------------------------------------------ layout

def draw_panel(cv, x, y, w, h, panel):
    accent = panel["accent"]
    cv.fill_rect(x, y, w, h, PANEL_BG)
    # border
    cv.hline(x, y, w, PANEL_LINE)
    cv.hline(x, y + h - 1, w, PANEL_LINE)
    cv.vline(x, y, h, PANEL_LINE)
    cv.vline(x + w - 1, y, h, PANEL_LINE)
    # accent bar
    cv.fill_rect(x, y, w, 5, accent)
    # region tag
    draw_text(cv, "tag", x + 14, y + 30, panel["tag"], accent)
    # emblem, top right
    EMBLEMS[panel["icon"]](cv, x + w - 78, y + 14)
    # headline, two lines max, width leaves room for the emblem
    head_lines = wrap_text("head", panel["head"], w - 14 - 84)
    hy = y + 60
    for line in head_lines[:2]:
        draw_text(cv, "head", x + 14, hy, line, INK)
        hy += 29
    # body, full width, up to four lines
    body_lines = wrap_text("body", panel["body"], w - 28)
    by = hy + 10
    for line in body_lines[:4]:
        draw_text(cv, "body", x + 14, by, line, (44, 46, 52))
        by += 21


def build():
    cv = Canvas(W, H, PAPER)
    m = 16
    # masthead band
    cv.fill_rect(m, 14, W - 2 * m, 58, NAVY)
    draw_text_centered(cv, "mast", W // 2, 56, "THE WORLD IN ONE DAY", CREAM)
    # date, large
    draw_text_centered(cv, "mast", W // 2, 118, "TUESDAY, 24 NOVEMBER 2026", NAVY)
    # kicker
    draw_text_centered(cv, "tag", W // 2, 144,
                       "WORLD NEWS IN ONE IMAGE  -  EIGHT STORIES FROM TUESDAY",
                       MUTED)
    cv.hline(m, 152, W - 2 * m, RULE, 2)
    # grid: 2 columns x 4 rows
    gx, gy = m, 160
    gap = 10
    pw = (W - 2 * m - gap) // 2
    ph = 198
    for i, panel in enumerate(PANELS):
        px = gx + (i % 2) * (pw + gap)
        py = gy + (i // 2) * (ph + gap)
        draw_panel(cv, px, py, pw, ph, panel)
    # footer
    draw_text_centered(cv, "tag", W // 2, 1006,
                       "Sources: wire reports of 24 November 2026. All eight stories "
                       "happened or were first reported on Tuesday 24 November 2026.",
                       MUTED)
    return encode_png(cv)


def output_dir():
    env = os.environ.get("MAKEFUN_OUTPUT_DIR")
    if env:
        return env
    if os.path.isdir("/output"):
        return "/output"
    return "."


def main():
    data = build()
    outdir = output_dir()
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "entry.png")
    with open(path, "wb") as f:
        f.write(data)
    print("wrote %s (%d bytes) sha256=%s"
          % (path, len(data), hashlib.sha256(data).hexdigest()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
