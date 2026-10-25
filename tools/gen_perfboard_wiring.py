#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate docs/perfboard-11-imu-wiring.html

Front (component side) + back (solder side) views on a 2.54 mm grid.
Board footprint: 180 x 115 mm, recommended stock board 200 x 150 mm.

Everything is drawn in millimetres inside SVG user units.
"""
from pathlib import Path

OUT = (Path(__file__).resolve().parent.parent
       / "docs" / "perfboard-11-imu-wiring.html")

# ---------------------------------------------------------------- constants
BOARD_W, BOARD_H = 180.0, 115.0

C_VCC   = "#c0392b"
C_GND   = "#222831"
C_SCLK  = "#1f6fb2"
C_MOSI  = "#e07b39"
C_MISO  = "#1f9d6b"
C_CAP   = "#1f6f8b"
C_CS    = "#7b4bb7"
C_INK   = "#1d232a"
C_MUTED = "#5b6470"
C_BODY  = "#eef3f7"
C_BLINE = "#8a97a3"
C_BOARD = "#fbfaf6"
C_HOLE  = "#e2ddd0"

CS_COLORS = ["#d1495b", "#00798c", "#edae49", "#30638e", "#8d5a97",
             "#2e933c", "#b5651d", "#6a4c93", "#c1121f", "#3a7ca5", "#7f6000"]

J1 = ["3V3", "3V3", "RST", "IO4", "IO5", "IO6", "IO7", "IO15", "IO16",
      "IO17", "IO18", "IO8", "IO3", "IO46", "IO9", "IO10", "IO11", "IO12",
      "IO13", "IO14", "5V", "GND"]
J3 = ["GND", "TX", "RX", "IO1", "IO2", "IO42", "IO41", "IO40", "IO39",
      "IO38", "IO37", "IO36", "IO35", "IO0", "IO45", "IO48", "IO47",
      "IO21", "IO20", "IO19", "GND", "GND"]

# source index -> (gpio, header, pin, row)   row 0 = first module row
CS_SRC = [
    (0,  "1",  "J3", 4,  0),
    (1,  "2",  "J3", 5,  0),
    (2,  "4",  "J1", 4,  0),
    (3,  "5",  "J1", 5,  0),
    (4,  "6",  "J1", 6,  0),
    (5,  "7",  "J1", 7,  0),
    (6,  "8",  "J1", 12, 1),
    (7,  "9",  "J1", 15, 1),
    (8,  "10", "J1", 16, 1),
    (9,  "14", "J1", 20, 1),
    (10, "15", "J1", 8,  1),
]

# ---------------------------------------------------------------- geometry
ESP_Y0   = 10.16
J3_X     = 7.62
J1_X     = 30.48
ESP_BODY = (6.35, 7.0, 31.75, 66.5)          # x1,y1,x2,y2

ROW1_Y, ROW2_Y = 30.48, 78.74
ROW1_X0, ROW2_X0 = 48.26, 58.42
MOD_PITCH = 20.32
MOD_PINS = ["VCC", "GND", "MISO", "MOSI", "SCLK", "CS"]

BUS1 = {"VCC": 40.64, "GND": 45.72, "MISO": 48.26, "MOSI": 50.80, "SCLK": 53.34}
BUS2 = {"VCC": 88.90, "GND": 93.98, "MISO": 96.52, "MOSI": 99.06, "SCLK": 101.60}
CAP1_Y, CAP2_Y = 35.56, 83.82
RES1_Y, RES2_Y = 35.56, 83.82

# left-hand connector verticals (explicit x, ESP32 pin)
CONN = {
    "VCC":  (32.50, 1),
    "GND":  (33.80, 22),
    "MISO": (35.10, 19),
    "MOSI": (36.40, 17),
    "SCLK": (37.70, 18),
}
# right-hand inter-row trunk (explicit x)
TRUNK = {"VCC": 167.64, "GND": 170.18, "MISO": 172.72,
         "MOSI": 175.26, "SCLK": 177.80}

BUS_COLOR = {"VCC": C_VCC, "GND": C_GND, "MISO": C_MISO,
             "MOSI": C_MOSI, "SCLK": C_SCLK}
BUS_W = {"VCC": 1.05, "GND": 1.05, "MISO": 0.55,
         "MOSI": 0.55, "SCLK": 0.55}

BULK1 = [(40.64, "CB1", "10µF"), (43.18, "CB2", "100µF")]
BULK2 = [(40.64, "CB3", "10µF")]


def f(v):
    return f"{v:.2f}"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def T(x, y, s, size=2.0, color=C_INK, anchor="start", weight=500,
      rot=None, halo=0.42, bg=C_BOARD):
    tr = f"translate({f(x)},{f(y)})"
    if rot is not None:
        tr += f" rotate({rot})"
    attrs = (f'font-size="{f(size)}" fill="{color}" text-anchor="{anchor}" '
             f'font-weight="{weight}"')
    if halo:
        attrs += (f' stroke="{bg}" stroke-width="{f(halo*2)}" '
                  f'paint-order="stroke" stroke-linejoin="round"')
    return f'<text transform="{tr}" {attrs}>{esc(s)}</text>'


def poly(pts, color, w=0.55, casing=1.15, dash=None, bg=C_BOARD):
    d = " ".join(f"{f(x)},{f(y)}" for x, y in pts)
    out = []
    if casing:
        out.append(f'<polyline points="{d}" fill="none" stroke="{bg}" '
                   f'stroke-width="{f(w + casing)}" stroke-linejoin="round" '
                   f'stroke-linecap="round"/>')
    da = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<polyline points="{d}" fill="none" stroke="{color}" '
               f'stroke-width="{f(w)}" stroke-linejoin="round" '
               f'stroke-linecap="round"{da}/>')
    return "\n".join(out)


def seg(x1, y1, x2, y2, color, w=0.55, casing=1.15, dash=None, bg=C_BOARD):
    return poly([(x1, y1), (x2, y2)], color, w, casing, dash, bg)


def dot(x, y, color, r=0.70):
    return f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{color}"/>'


def pad(x, y, color, r=0.95):
    return (f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{color}"/>'
            f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r*0.42)}" fill="{C_BOARD}"/>')


def pad_gray(x, y, r=0.55):
    return (f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="#fff" '
            f'stroke="{C_MUTED}" stroke-width="0.28"/>')


def res_body_v(x, cy, ref, side=1):
    out = [f'<rect x="{f(x-0.92)}" y="{f(cy-2.50)}" width="1.84" '
           f'height="5.00" rx="0.32" fill="#fff" stroke="{C_INK}" '
           f'stroke-width="0.38"/>']
    out.append(T(x + side * 1.30, cy + 1.55, ref, 1.28, C_INK,
                 rot=-90, halo=0.28))
    return "\n".join(out)


def cap_h(x1, x2, y, ref):
    mid = (x1 + x2) / 2.0
    out = []
    out.append(seg(x1, y, mid - 0.55, y, C_CAP, 0.50, 1.0))
    out.append(seg(mid + 0.55, y, x2, y, C_CAP, 0.50, 1.0))
    out.append(seg(mid - 0.55, y - 1.35, mid - 0.55, y + 1.35,
                   C_CAP, 0.62, 0))
    out.append(seg(mid + 0.55, y - 1.35, mid + 0.55, y + 1.35,
                   C_CAP, 0.62, 0))
    out.append(T(mid, y - 1.90, ref, 1.20, C_CAP, anchor="middle",
                 halo=0.26))
    return "\n".join(out)


def cap_h_local(x1, x2, y, ref):
    """100 nF across two vertical module drops; label sits in the gap left."""
    mid = (x1 + x2) / 2.0
    out = []
    out.append(seg(x1, y, mid - 0.55, y, C_CAP, 0.50, 1.0))
    out.append(seg(mid + 0.55, y, x2, y, C_CAP, 0.50, 1.0))
    out.append(seg(mid - 0.55, y - 1.35, mid - 0.55, y + 1.35,
                   C_CAP, 0.62, 0))
    out.append(seg(mid + 0.55, y - 1.35, mid + 0.55, y + 1.35,
                   C_CAP, 0.62, 0))
    out.append(T(x1 - 0.45, y + 0.45, ref, 1.15, C_CAP,
                 anchor="end", halo=0.24))
    return "\n".join(out)


def cap_v_sym(x, y1, y2):
    mid = (y1 + y2) / 2.0
    out = []
    out.append(seg(x, y1, x, mid - 0.45, C_VCC, 0.70, 0.95))
    out.append(seg(x, mid + 0.45, x, y2, C_GND, 0.70, 0.95))
    out.append(seg(x - 1.00, mid - 0.45, x + 1.00, mid - 0.45, C_INK, 0.55, 0))
    out.append(seg(x - 1.00, mid + 0.45, x + 1.00, mid + 0.45, C_INK, 0.55, 0))
    return "\n".join(out)


# ---------------------------------------------------------------- board base
def board_base(w=BOARD_W, h=BOARD_H, holes=True, mounting=True):
    o = [f'<rect x="0" y="0" width="{f(w)}" height="{f(h)}" rx="1.8" '
         f'fill="{C_BOARD}" stroke="#7f7f7f" stroke-width="0.45"/>']
    if holes:
        # Grid origin is 0,0 so every header pin (multiples of 2.54) lands on a hole.
        y = 2.54
        while y < h - 1.0:
            x = 2.54
            while x < w - 1.0:
                o.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="0.20" '
                         f'fill="{C_HOLE}"/>')
                x += 2.54
            y += 2.54
    if mounting:
        for mx, my in ((4.0, 4.0), (w - 4.0, 4.0),
                       (4.0, h - 4.0), (w - 4.0, h - 4.0)):
            o.append(f'<circle cx="{f(mx)}" cy="{f(my)}" r="1.55" '
                     f'fill="#fff" stroke="#9aa0a6" stroke-width="0.35"/>')
    return "\n".join(o)


def ruler():
    o = []
    for x in range(0, 181, 10):
        o.append(seg(x, 0, x, -1.35, "#9aa0a6", 0.30, 0))
        if x % 20 == 0 and x > 0:
            o.append(T(x, -1.75, f"{x}", 1.20, C_MUTED,
                       anchor="middle", halo=0.18))
    for y in range(0, 116, 10):
        o.append(seg(0, y, -1.35, y, "#9aa0a6", 0.30, 0))
        if y % 20 == 0 and y > 0:
            o.append(T(-1.65, y + 0.42, f"{y}", 1.20, C_MUTED,
                       anchor="end", halo=0.18))
    return "\n".join(o)


# ---------------------------------------------------------------- module draw
def module_geom(row):
    """return list of (idx, x0, header_y, bus, cap_y, res_y)"""
    out = []
    for i in range(11):
        if i < 6:
            x0 = ROW1_X0 + i * MOD_PITCH
            out.append((i, x0, ROW1_Y, BUS1, CAP1_Y, RES1_Y))
        else:
            x0 = ROW2_X0 + (i - 6) * MOD_PITCH
            out.append((i, x0, ROW2_Y, BUS2, CAP2_Y, RES2_Y))
    return out


MODS = module_geom(0)


def module_body(i, x0, yh):
    top = yh - 20.32
    out = [f'<rect x="{f(x0-1.60)}" y="{f(top)}" width="15.88" '
           f'height="18.72" rx="1.0" fill="{C_BODY}" stroke="{C_BLINE}" '
           f'stroke-width="0.35"/>']
    out.append(T(x0, top + 4.0, f"J{i+1}", 2.9, C_INK, weight=700,
                 halo=0.30, bg=C_BODY))
    out.append(T(x0 + 5.0, top + 3.7, f"IMU{i}", 1.55, C_MUTED,
                 halo=0.26, bg=C_BODY))
    # pin names, bottom-up
    for k, name in enumerate(MOD_PINS):
        px = x0 + k * 2.54
        out.append(T(px + 0.48, yh - 2.35, name, 1.42, C_INK,
                     rot=-90, halo=0.22, bg=C_BODY))
    return "\n".join(out)


# ---------------------------------------------------------------- front
def front_svg():
    o = []
    vb = "-7 -15 213 145"
    o.append(f'<svg id="frontSvg" viewBox="{vb}" width="100%" role="img" '
             f'aria-labelledby="frontTitle frontDesc">')
    o.append('<title id="frontTitle">11 路 LSM6DSV16X 洞洞板正面接线图</title>')
    o.append('<desc id="frontDesc">180 x 115 mm, 2.54 mm grid, ESP32-S3-DevKitC-1, '
             'shared SPI bus, 11 chip selects.</desc>')
    o.append(board_base())
    o.append(ruler())

    # --- ESP32 body
    x1, y1, x2, y2 = ESP_BODY
    o.append(f'<rect x="{f(x1)}" y="{f(y1)}" width="{f(x2-x1)}" '
             f'height="{f(y2-y1)}" rx="1.2" fill="#f0f2f5" '
             f'stroke="#6b7280" stroke-width="0.45"/>')
    o.append(T((x1+x2)/2, y2 + 2.8, "USB ↓", 1.50, C_MUTED,
               anchor="middle", halo=0.22, bg="#f0f2f5"))
    o.append(T((x1+x2)/2, y2 + 5.3, "ESP32-S3-DevKitC-1", 1.45, C_INK,
               anchor="middle", weight=600, halo=0.22, bg="#f0f2f5"))
    o.append(T(6.5, 75.0, "灰色数字 = 未使用引脚；完整排针名见第 1 节。",
               1.35, C_MUTED, halo=0.20))
    o.append(T(6.5, 77.5, "J3-1/21/22 的 GND 与 J1-22 内部相通，可不另接。",
               1.35, C_MUTED, halo=0.20))
    o.append(T(J3_X, y1 - 1.6, "J3", 2.6, C_INK, anchor="middle",
               weight=700, halo=0.3))
    o.append(T(J1_X, y1 - 1.6, "J1", 2.6, C_INK, anchor="middle",
               weight=700, halo=0.3))

    # --- front bus lanes (background)
    for name in ("VCC", "GND", "MISO", "MOSI", "SCLK"):
        y = BUS1[name]
        xa = CONN[name][0]
        xb = TRUNK[name]
        o.append(seg(xa, y, xb, y, BUS_COLOR[name], BUS_W[name], 1.0))
    for name in ("VCC", "GND", "MISO", "MOSI", "SCLK"):
        y = BUS2[name]
        xa = 40.64
        xb = TRUNK[name]
        o.append(seg(xa, y, xb, y, BUS_COLOR[name], BUS_W[name], 1.0))

    # --- inter-row trunks
    for name in ("VCC", "GND", "MISO", "MOSI", "SCLK"):
        x = TRUNK[name]
        o.append(seg(x, BUS1[name], x, BUS2[name],
                     BUS_COLOR[name], BUS_W[name], 1.0))

    # --- ESP32 to bus connectors
    for name in ("VCC", "GND", "MISO", "MOSI", "SCLK"):
        xc, pin = CONN[name]
        yp = ESP_Y0 + (pin - 1) * 2.54
        o.append(poly([(J1_X, yp), (xc, yp), (xc, BUS1[name])],
                      BUS_COLOR[name], BUS_W[name], 1.0))

    # second 3V3 pin (J1-2) ties into the same vertical
    o.append(seg(J1_X, ESP_Y0 + 2.54, CONN["VCC"][0], ESP_Y0 + 2.54,
                 C_VCC, 0.72, 0.95))
    o.append(dot(CONN["VCC"][0], ESP_Y0 + 2.54, C_VCC))

    # --- module bodies first (wire-side is below them)
    for i, x0, yh, bus, capy, resy in MODS:
        o.append(module_body(i, x0, yh))

    # --- module drops
    for i, x0, yh, bus, capy, resy in MODS:
        xv = x0 + MOD_PINS.index("VCC") * 2.54
        xg = x0 + MOD_PINS.index("GND") * 2.54
        xm = x0 + MOD_PINS.index("MISO") * 2.54
        xo = x0 + MOD_PINS.index("MOSI") * 2.54
        xs = x0 + MOD_PINS.index("SCLK") * 2.54
        xc = x0 + MOD_PINS.index("CS") * 2.54

        # VCC drop continues past the bus to the 100 nF left lead
        o.append(seg(xv, yh, xv, max(bus["VCC"], capy), C_VCC, 0.72, 0.95))
        o.append(seg(xg, yh, xg, bus["GND"], C_GND, 0.72, 0.95))
        o.append(seg(xm, yh, xm, bus["MISO"], C_MISO, 0.50, 0.95))
        o.append(seg(xo, yh, xo, bus["MOSI"], C_MOSI, 0.50, 0.95))
        o.append(seg(xs, yh, xs, bus["SCLK"], C_SCLK, 0.50, 0.95))
        # CS pull-up to VCC
        o.append(seg(xc, yh, xc, bus["VCC"], C_CS, 0.50, 0.95))
        # 100 nF across VCC/GND
        o.append(cap_h_local(xv, xg, capy, f"C{i+1}"))

    # --- component bodies over the leads
    for i, x0, yh, bus, capy, resy in MODS:
        xm = x0 + MOD_PINS.index("MISO") * 2.54
        xc = x0 + MOD_PINS.index("CS") * 2.54
        o.append(res_body_v(xm, resy, f"RM{i+1}", side=1))
        o.append(res_body_v(xc, (yh + bus["VCC"]) / 2.0, f"RC{i+1}", side=1))

    # --- bulk capacitors (leads land on the two power rails)
    for x, ref, label in BULK1:
        o.append(cap_v_sym(x, BUS1["VCC"], BUS1["GND"]))
    o.append(T(40.64, 39.30, "CB1", 1.05, C_INK, anchor="middle",
               weight=700, halo=0.20))
    o.append(T(43.18, 37.90, "CB2", 1.05, C_INK, anchor="middle",
               weight=700, halo=0.20))
    for x, ref, label in BULK2:
        o.append(cap_v_sym(x, BUS2["VCC"], BUS2["GND"]))
    o.append(T(40.64, 87.55, "CB3", 1.05, C_INK, anchor="middle",
               weight=700, halo=0.20))

    # --- junction dots
    for i, x0, yh, bus, capy, resy in MODS:
        for name in ("VCC", "GND", "MISO", "MOSI", "SCLK"):
            x = x0 + MOD_PINS.index(name) * 2.54
            o.append(dot(x, bus[name], BUS_COLOR[name]))
        xv = x0 + MOD_PINS.index("VCC") * 2.54
        xg = x0 + MOD_PINS.index("GND") * 2.54
        xc = x0 + MOD_PINS.index("CS") * 2.54
        o.append(dot(xv, capy, C_VCC))
        o.append(dot(xg, capy, C_GND))
        o.append(dot(xc, bus["VCC"], C_VCC))

    for name in ("VCC", "GND", "MISO", "MOSI", "SCLK"):
        o.append(dot(CONN[name][0], BUS1[name], BUS_COLOR[name]))
        o.append(dot(TRUNK[name], BUS1[name], BUS_COLOR[name]))
        o.append(dot(TRUNK[name], BUS2[name], BUS_COLOR[name]))
    for x, _, _ in BULK1:
        o.append(dot(x, BUS1["VCC"], C_VCC))
        o.append(dot(x, BUS1["GND"], C_GND))
    for x, _, _ in BULK2:
        o.append(dot(x, BUS2["VCC"], C_VCC))
        o.append(dot(x, BUS2["GND"], C_GND))

    # --- header pads and labels
    for pin, name in enumerate(J1, 1):
        y = ESP_Y0 + (pin - 1) * 2.54
        used = used_signal("J1", pin)
        if used:
            o.append(pad(J1_X, y, used[1]))
            o.append(T(J1_X - 1.45, y + 0.52, str(pin), 1.35, used[1],
                       anchor="end", weight=700, halo=0.26, bg="#f0f2f5"))
            o.append(T(J1_X - 4.10, y + 0.52, used[0], 1.35, used[1],
                       anchor="end", weight=600, halo=0.26, bg="#f0f2f5"))
        else:
            o.append(pad_gray(J1_X, y, 0.42))
            o.append(T(J1_X - 1.30, y + 0.40, str(pin), 0.98,
                       "#9aa0a6", anchor="end", halo=0.16, bg="#f0f2f5"))
    for pin, name in enumerate(J3, 1):
        y = ESP_Y0 + (pin - 1) * 2.54
        used = used_signal("J3", pin)
        if used:
            o.append(pad(J3_X, y, used[1]))
            o.append(T(J3_X + 1.45, y + 0.52, str(pin), 1.35, used[1],
                       weight=700, halo=0.26, bg="#f0f2f5"))
            o.append(T(J3_X + 4.20, y + 0.52, used[0], 1.35, used[1],
                       weight=600, halo=0.26, bg="#f0f2f5"))
        else:
            o.append(pad_gray(J3_X, y, 0.42))
            o.append(T(J3_X + 1.30, y + 0.40, str(pin), 0.98,
                       "#9aa0a6", halo=0.16, bg="#f0f2f5"))

    # --- module header pads
    for i, x0, yh, bus, capy, resy in MODS:
        for k, name in enumerate(MOD_PINS):
            x = x0 + k * 2.54
            col = C_CS if name == "CS" else BUS_COLOR[name]
            o.append(pad(x, yh, col))
        # CS source number badge
        bx, by = x0 + 14.35, yh + 1.95
        o.append(f'<circle cx="{f(bx)}" cy="{f(by)}" r="0.98" '
                 f'fill="{C_CS}"/>')
        o.append(T(bx, by + 0.42, str(i), 1.08, "#ffffff",
                   anchor="middle", weight=700, halo=0))

    # --- bus labels (right margin)
    for name in ("VCC", "GND", "MISO", "MOSI", "SCLK"):
        y = BUS1[name]
        label = "3V3" if name == "VCC" else name
        o.append(f'<rect x="180.60" y="{f(y-0.65)}" width="1.30" '
                 f'height="1.30" fill="{BUS_COLOR[name]}"/>')
        o.append(T(182.40, y + 0.70, label, 2.05, BUS_COLOR[name],
                   weight=700, halo=0.30))
    o.append(T(182.40, 57.5, "每颗 120 Ω", 1.45, C_MISO, halo=0.25))
    o.append(T(182.40, 60.3, "串在 MISO", 1.45, C_MISO, halo=0.25))
    o.append(T(182.40, 63.1, "10 kΩ 上拉 CS", 1.45, C_CS, halo=0.25))
    o.append(T(182.40, 66.0, "到 3V3", 1.45, C_CS, halo=0.25))

    # --- titles / notes
    o.append(T(-2.0, -10.0, "正面（元件面）· 11 路 LSM6DSV16X + ESP32-S3-DevKitC-1",
               4.15, C_INK, weight=700, halo=0))
    o.append(T(-2.0, -5.7, "180 × 115 mm 布局（建议 200 × 150 mm 洞洞板）· 2.54 mm 孔距 · "
               "模块逆时针旋转 90°，VCC 在左、CS 在右",
               2.0, C_MUTED, halo=0))

    # --- bottom legend
    lx = 2.0
    ly = 104.6
    items = [("3V3", C_VCC), ("GND", C_GND), ("MISO", C_MISO),
             ("MOSI", C_MOSI), ("SCLK", C_SCLK), ("CS→背面", C_CS)]
    for name, col in items:
        o.append(seg(lx, ly, lx + 4.2, ly, col, 0.9, 0))
        o.append(T(lx + 5.0, ly + 0.7, name, 1.55, col, halo=0.2))
        lx += 20.0
    o.append(T(2.0, 109.0,
               "RM = 120 Ω MISO 串阻（模块端）   RC = 10 kΩ CS 上拉到 3V3   "
               "C = 100 nF 模块本地去耦   CB = 10 µF / 100 µF 总线储能",
               1.62, C_INK, halo=0.2))
    o.append(T(2.0, 112.6,
               "模块针序：1=VCC  2=GND  3=MISO  4=MOSI  5=SCLK  6=CS。"
               "紫色圆环 = 背面 CS；总线断开处 = 仅交叉不连接，圆点 = 连接。",
               1.62, C_MUTED, halo=0.2))
    o.append('</svg>')
    return "\n".join(o)


USED_J1 = {
    1: ("3V3", C_VCC), 2: ("3V3", C_VCC),
    17: ("MOSI", C_MOSI), 18: ("SCLK", C_SCLK),
    19: ("MISO", C_MISO), 22: ("GND", C_GND),
    4: ("CS2", C_CS), 5: ("CS3", C_CS), 6: ("CS4", C_CS),
    7: ("CS5", C_CS), 12: ("CS6", C_CS), 15: ("CS7", C_CS),
    16: ("CS8", C_CS), 20: ("CS9", C_CS), 8: ("CS10", C_CS),
}
USED_J3 = {
    1: ("GND", C_GND), 21: ("GND", C_GND), 22: ("GND", C_GND),
    4: ("CS0", C_CS), 5: ("CS1", C_CS),
}


def used_signal(hdr, pin):
    return (USED_J1 if hdr == "J1" else USED_J3).get(pin)


# ---------------------------------------------------------------- header map
def header_map_svg():
    w, h = 200.0, 123.0
    o = [f'<svg id="headerSvg" viewBox="0 0 {w} {h}" width="100%" role="img" '
         f'aria-label="ESP32-S3-DevKitC-1 排针表">']
    o.append('<rect width="200" height="123" fill="#ffffff"/>')
    o.append(T(100, 6.5, "ESP32-S3-DevKitC-1 排针（USB 朝下，pin 1 在上）",
               3.4, C_INK, anchor="middle", weight=700, halo=0))
    cols = [("J1", J1, 22.0, USED_J1), ("J3", J3, 118.0, USED_J3)]
    for name, pins, x, used in cols:
        o.append(f'<rect x="{f(x-2.5)}" y="10.5" width="76" height="108" '
                 f'rx="1.5" fill="#f7f8fa" stroke="#c7ccd2" stroke-width="0.35"/>')
        o.append(T(x + 35.5, 15.3, name, 3.0, C_INK, anchor="middle",
                   weight=700, halo=0))
        for i, pname in enumerate(pins):
            pin = i + 1
            y = 19.0 + i * 4.45
            u = used.get(pin)
            if u:
                col = u[1]
                o.append(f'<rect x="{f(x-1.2)}" y="{f(y-3.25)}" width="71.5" '
                         f'height="4.05" rx="0.7" fill="#ffffff" '
                         f'stroke="{col}" stroke-width="0.42"/>')
                o.append(f'<rect x="{f(x-1.2)}" y="{f(y-3.25)}" width="1.55" '
                         f'height="4.05" fill="{col}"/>')
                o.append(T(x + 1.2, y, f"{pin:02d}", 1.75, col,
                           weight=700, halo=0))
                o.append(T(x + 8.6, y, pname, 1.72, C_INK, halo=0))
                o.append(T(x + 36.0, y, u[0], 1.62, col, weight=700, halo=0))
            else:
                o.append(T(x + 1.2, y, f"{pin:02d}", 1.55, "#9aa0a6", halo=0))
                o.append(T(x + 8.6, y, pname, 1.55, "#7b828b", halo=0))
    o.append('</svg>')
    return "\n".join(o)


# ---------------------------------------------------------------- back (CS)
def mx(x):
    return BOARD_W - x


def back_svg():
    o = []
    vb = "-7 -15 213 145"
    o.append(f'<svg id="backSvg" viewBox="{vb}" width="100%" role="img" '
             f'aria-labelledby="backTitle backDesc">')
    o.append('<title id="backTitle">背面 CS 扇出图</title>')
    o.append('<desc id="backDesc">Bottom view, mirrored. Eleven chip-select '
             'wires from ESP32 pins to module CS pins.</desc>')
    o.append(board_base())

    # mirrored ESP32 body
    bx1, by1, bx2, by2 = ESP_BODY
    x1, x2 = mx(bx2), mx(bx1)
    o.append(f'<rect x="{f(x1)}" y="{f(by1)}" width="{f(x2-x1)}" '
             f'height="{f(by2-by1)}" rx="1.2" fill="#f0f2f5" '
             f'stroke="#6b7280" stroke-width="0.45" stroke-dasharray="2 1.2"/>')
    o.append(T((x1+x2)/2, by2 + 3.4, "ESP32（背面镜像）", 1.55, C_MUTED,
               anchor="middle", weight=600, halo=0.22))

    # mirrored module outlines
    for i, x0, yh, bus, capy, resy in MODS:
        bx = mx(x0 + 14.28)
        o.append(f'<rect x="{f(bx)}" y="{f(yh-20.32)}" width="15.88" '
                 f'height="18.72" rx="1.0" fill="none" stroke="{C_BLINE}" '
                 f'stroke-width="0.3" stroke-dasharray="2 1.2"/>')
        o.append(T(mx(x0 + 7.94), yh - 18.0, f"J{i+1}", 1.55, C_MUTED,
                   anchor="middle", halo=0.2, bg=C_BOARD))
        for k, name in enumerate(MOD_PINS):
            px = mx(x0 + k * 2.54)
            col = C_CS if name == "CS" else "#b9c0c7"
            rr = 0.72 if name == "CS" else 0.40
            o.append(f'<circle cx="{f(px)}" cy="{f(yh)}" r="{f(rr)}" '
                     f'fill="{col if name=="CS" else "#fff"}" '
                     f'stroke="{col}" stroke-width="0.3"/>')

    # source pins and destination pins, routes
    row_lane_y = {0: lambda i: 8.55 - i * 0.95,
                  1: lambda i: 105.2 + (i - 6) * 0.95}
    lane_x = {i: 127.5 + i * 1.75 for i in range(11)}

    # helper to get geometry
    idx = {m[0]: m for m in MODS}

    for (i, gpio, hdr, pin, row) in CS_SRC:
        _, x0, yh, bus, capy, resy = idx[i]
        pad_x = mx(x0 + 12.70)
        pad_y = yh
        src_x = mx(J1_X if hdr == "J1" else J3_X)
        src_y = ESP_Y0 + (pin - 1) * 2.54
        col = CS_COLORS[i]
        xl = lane_x[i]
        yh_lane = row_lane_y[row](i)

        if hdr == "J1":
            pts = [(src_x, src_y), (src_x - 2.2, src_y),
                   (xl, src_y), (xl, yh_lane),
                   (pad_x, yh_lane), (pad_x, pad_y)]
        else:
            pts = [(src_x, src_y), (176.8, src_y), (176.8, 2.2),
                   (xl, 2.2), (xl, yh_lane),
                   (pad_x, yh_lane), (pad_x, pad_y)]
        o.append(poly(pts, col, 0.45, 0.90))

        # source label inside the mirrored ESP32 body, away from the route
        if hdr == "J3":
            o.append(T(src_x - 1.5, src_y + 0.45, f"CS{i}", 1.15, col,
                       anchor="end", weight=700, halo=0.24,
                       bg="#f0f2f5"))
        else:
            o.append(T(src_x + 1.5, src_y + 0.45, f"CS{i}", 1.15, col,
                       weight=700, halo=0.24, bg="#f0f2f5"))
        o.append(T(pad_x, pad_y + (3.0 if row == 0 else -2.2),
                   f"CS{i}", 1.30, col, anchor="middle",
                   weight=700, halo=0.30))
        # source pad
        o.append(pad(src_x, src_y, col, 0.78))
        # destination pad ring (through-hole CS pin)
        o.append(f'<circle cx="{f(pad_x)}" cy="{f(pad_y)}" r="1.05" '
                 f'fill="none" stroke="{col}" stroke-width="0.55"/>')

    # title / notes
    o.append(T(-2.0, -10.0, "背面（焊接面，从板底看，左右镜像）· CS0–CS10 扇出",
               4.05, C_INK, weight=700, halo=0))
    o.append(T(-2.0, -5.7, "端子位置与正面严格镜像对应；走线通道为建议路径。"
               "背面 CS 用绝缘飞线，交叉处不连接。",
               2.0, C_MUTED, halo=0))

    # legend in the free middle band (no routes there)
    for i in range(11):
        col = CS_COLORS[i]
        xx = 4.0 + (i % 6) * 18.6
        yy = 36.0 + (i // 6) * 6.0
        o.append(seg(xx, yy, xx + 3.4, yy, col, 1.1, 0))
        o.append(T(xx + 4.1, yy + 0.65, f"CS{i}", 1.45, col,
                   weight=700, halo=0.2))
    o.append(T(4.0, 47.0,
               "颜色仅用于追踪，电气上都是 CS；两端必须贴 CSn 标签。",
               1.55, C_MUTED, halo=0.2))
    o.append(T(4.0, 51.0,
               "CS0/CS1 在 J3 外侧排针，沿板边绕行；其余 CS 在 J1 内侧排针。",
               1.55, C_MUTED, halo=0.2))
    o.append('</svg>')
    return "\n".join(o)


# ---------------------------------------------------------------- tables
def module_rows_html():
    rows = []
    for i, x0, yh, bus, capy, resy in MODS:
        csx = x0 + 12.70
        rows.append(
            f"<tr><td>{i}</td><td>J{i+1}</td><td>IMU{i}</td>"
            f"<td>{'第一排' if i < 6 else '第二排'}</td>"
            f"<td>{x0:.1f} / {yh:.1f}</td>"
            f"<td>{csx:.1f} / {yh:.1f}</td>"
            f"<td>RM{i+1}</td><td>RC{i+1}</td><td>C{i+1}</td></tr>")
    return "\n".join(rows)


def cs_rows_html():
    rows = []
    for i, gpio, hdr, pin, row in CS_SRC:
        y = ESP_Y0 + (pin - 1) * 2.54
        rows.append(
            f"<tr><td>{i}</td><td>GPIO{gpio}</td><td>{hdr}-{pin}</td>"
            f"<td>{y:.1f}</td><td>J{i+1}</td>"
            f"<td>RC{i+1} → 3V3</td></tr>")
    return "\n".join(rows)


HEADER_ROWS_J1 = "\n".join(
    f"<tr><td>J1-{p}</td><td>{n}</td><td>{USED_J1[p][0] if p in USED_J1 else '—'}</td></tr>"
    for p, n in enumerate(J1, 1))
HEADER_ROWS_J3 = "\n".join(
    f"<tr><td>J3-{p}</td><td>{n}</td><td>{USED_J3[p][0] if p in USED_J3 else '—'}</td></tr>"
    for p, n in enumerate(J3, 1))


CSS = """
:root { --ink:#1d232a; --muted:#5b6470; --line:#d7dce2; --bg:#f3f1ea; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font:14px/1.6 -apple-system,"Segoe UI","Noto Sans SC",sans-serif; }
.page { max-width:1500px; margin:22px auto; background:#fff;
        padding:26px 32px 44px; box-shadow:0 2px 16px rgba(0,0,0,.08); }
h1 { font-size:23px; margin:0 0 4px; letter-spacing:.2px; }
h2 { font-size:17px; margin:30px 0 10px; border-bottom:2px solid var(--line);
     padding-bottom:6px; }
h3 { font-size:15px; margin:18px 0 6px; }
p.note { color:var(--muted); margin:4px 0 0; }
.warn { background:#fff7e6; border-left:4px solid #e0a000; padding:11px 14px;
        border-radius:6px; margin:14px 0; font-size:13.5px; }
.bad { background:#fdeeee; border-left:4px solid #c0392b; padding:11px 14px;
       border-radius:6px; margin:14px 0; font-size:13.5px; }
.card { border:1px solid var(--line); border-radius:10px; padding:12px;
        background:#fff; overflow-x:auto; }
svg { display:block; width:100%; height:auto; }
#frontSvg, #backSvg { min-width:1100px; }
table { width:100%; border-collapse:collapse; margin-top:8px; font-size:13px; }
th, td { border:1px solid var(--line); padding:5px 8px; text-align:left; }
th { background:#f6f5f1; font-weight:600; white-space:nowrap; }
td { vertical-align:top; }
code { background:#f1f1ec; padding:1px 5px; border-radius:4px; font-size:12.5px; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:20px; align-items:start; }
.tag { display:inline-block; padding:0 6px; border-radius:4px;
       font-size:11.5px; font-weight:700; color:#fff; }
.legendline { display:flex; gap:18px; flex-wrap:wrap; font-size:12.5px;
              color:var(--muted); margin-top:8px; }
.sw { display:inline-block; width:22px; height:3px; vertical-align:middle;
      margin-right:6px; }
ol, ul { margin:6px 0 0 20px; padding:0; }
li { margin:3px 0; }
@media print {
  body { background:#fff; }
  .page { box-shadow:none; margin:0; max-width:none; padding:0; }
  h2 { break-after:avoid; }
  .card, table, .warn, .bad { break-inside:avoid; }
  svg { min-width:0; }
  @page { size: A3 landscape; margin: 8mm; }
}
"""

HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LSM6DSV16X 11 路洞洞板整板接线图</title>
<style>__CSS__</style>
</head>
<body>
<div class="page">
  <h1>LSM6DSV16X 11 路洞洞板整板接线图（2 / 6 / 11 路分阶段兼容）</h1>
  <p class="note">配合 <code>docs/perfboard-11-imu.md</code> 使用。坐标按 2.54 mm
     孔距；开发板排针按 ESP32-S3-DevKitC-1 v1.1 官方 J1/J3 编号。图分
     <b>正面元件面</b> 与 <b>背面 CS 扇出</b> 两张，避免正面走线交叉不清。</p>

  <div class="bad">
    <b>先核对实物：</b>模块针序从上到下为 VCC、GND、MISO、MOSI、SCLK、CS；
    上板时逆时针旋转 90°，使 VCC 在左、CS 在右。不同批次 6 针小板可能改针序，
    以丝印为准。上电前必须断电测 3V3–GND 无短路。
  </div>

  <h2>1. ESP32-S3-DevKitC-1 排针（精确序号）</h2>
  <div class="card">__HEADER_SVG__</div>
  <div class="grid2" style="margin-top:14px">
    <div>
      <table>
        <tr><th>信号</th><th>GPIO</th><th>排针</th><th>说明</th></tr>
        <tr><td>SCLK</td><td>GPIO12</td><td>J1-18</td><td>共享，建议 22–33 Ω 串阻</td></tr>
        <tr><td>MOSI</td><td>GPIO11</td><td>J1-17</td><td>共享</td></tr>
        <tr><td>MISO</td><td>GPIO13</td><td>J1-19</td><td>共享，每模块经 120 Ω 接入</td></tr>
        <tr><td>3V3</td><td>3V3</td><td>J1-1 / J1-2</td><td>粗铜线总线</td></tr>
        <tr><td>GND</td><td>GND</td><td>J1-22（J3-1/21/22 内部相通）</td><td>粗铜线，星形一点</td></tr>
      </table>
      <p class="note">GPIO19/20 是 USB D-/D+，<b>绝对不要</b>接 CS。
         GPIO0/3/45/46 是启动/电压 strapping 脚，也不要占用。</p>
    </div>
    <div>
      <table>
        <tr><th>源</th><th>CS GPIO</th><th>排针</th><th>y (mm)</th><th>模块</th><th>上拉</th></tr>
        __CS_ROWS__
      </table>
    </div>
  </div>

  <h2>2. 正面（元件面）整板接线</h2>
  <div class="card">__FRONT_SVG__</div>
  <div class="legendline">
    <span><span class="sw" style="background:#c0392b"></span>3V3</span>
    <span><span class="sw" style="background:#222831"></span>GND</span>
    <span><span class="sw" style="background:#1f9d6b"></span>MISO（经 120 Ω）</span>
    <span><span class="sw" style="background:#e07b39"></span>MOSI</span>
    <span><span class="sw" style="background:#1f6fb2"></span>SCLK</span>
    <span><span class="sw" style="background:#7b4bb7"></span>CS（背面飞线）</span>
  </div>

  <h3>正面接线规则（逐模块相同）</h3>
  <table>
    <tr><th>模块针</th><th>接到</th><th>元件</th><th>要点</th></tr>
    <tr><td>1 VCC</td><td>3V3 总线</td><td>Cn 100 nF 到 GND</td>
        <td>电容紧贴模块；100 nF 两端分别落在 VCC、GND 引线上</td></tr>
    <tr><td>2 GND</td><td>GND 总线</td><td>—</td>
        <td>粗铜线；每个模块单独回星形点，不要串联成细地</td></tr>
    <tr><td>3 MISO</td><td>MISO 总线 → J1-19</td><td><b>RMn 120 Ω 串联</b></td>
        <td>电阻放在模块端，隔离未选中模块的 SDO</td></tr>
    <tr><td>4 MOSI</td><td>MOSI 总线 → J1-17</td><td>—</td><td>共享</td></tr>
    <tr><td>5 SCLK</td><td>SCLK 总线 → J1-18</td><td>可选 22–33 Ω</td><td>抑制振铃</td></tr>
    <tr><td>6 CS</td><td>GPIOx（见表）</td><td><b>RCn 10 kΩ 到 3V3</b></td>
        <td>同时接背面 CSn 飞线；上拉防止复位期间误选</td></tr>
  </table>

  <h2>3. 背面 CS 扇出（与正面镜像对应）</h2>
  <div class="card">__BACK_SVG__</div>
  <p class="note">背面图是从板底看的左右镜像。CS 用绝缘细飞线，交叉处不连接；
     两端贴 <code>CS0…CS10</code> 标签。CS0/CS1 在 J3 外侧排针，沿板边绕行；
     其余 CS 在 J1 内侧排针。</p>

  <h2>4. 模块位号、坐标与元件对照</h2>
  <table>
    <tr><th>源</th><th>模块位号</th><th>丝印标</th><th>排</th>
        <th>模块 x0 / 排针 y (mm)</th><th>CS 坐标 x / y (mm)</th>
        <th>MISO 串阻</th><th>CS 上拉</th><th>去耦</th></tr>
    __MOD_ROWS__
  </table>
  <p class="note">坐标原点为板左上角，x 向右、y 向下（与图面一致）。焊接时以孔位为准；
     模块 x0 是 6 针排母第 1 针（VCC）的 x 坐标。</p>

  <h2>5. BOM（分阶段）</h2>
  <div class="grid2">
    <div>
      <h3>2 路原型（先焊）</h3>
      <table>
        <tr><th>位号</th><th>规格</th><th>数量</th></tr>
        <tr><td>J0</td><td>2×22 2.54 mm 排母</td><td>1</td></tr>
        <tr><td>J1–J2</td><td>1×6 2.54 mm 排母</td><td>2</td></tr>
        <tr><td>RM1–RM2</td><td>120 Ω 1/4 W</td><td>2</td></tr>
        <tr><td>RC1–RC2</td><td>10 kΩ 1/4 W</td><td>2</td></tr>
        <tr><td>C1–C2</td><td>100 nF 陶瓷</td><td>2</td></tr>
        <tr><td>CB1 / CB2</td><td>10 µF / 100 µF</td><td>1 / 1</td></tr>
      </table>
    </div>
    <div>
      <h3>扩到 6 路 / 11 路追加</h3>
      <table>
        <tr><th>位号</th><th>规格</th><th>6 路</th><th>11 路</th></tr>
        <tr><td>J3–J6 / J7–J11</td><td>1×6 排母</td><td>+4</td><td>+9</td></tr>
        <tr><td>RM3–RM6 / RM7–RM11</td><td>120 Ω</td><td>+4</td><td>+9</td></tr>
        <tr><td>RC3–RC6 / RC7–RC11</td><td>10 kΩ</td><td>+4</td><td>+9</td></tr>
        <tr><td>C3–C6 / C7–C11</td><td>100 nF</td><td>+4</td><td>+9</td></tr>
        <tr><td>CB3</td><td>10 µF</td><td>—</td><td>+1</td></tr>
        <tr><td>板</td><td>200×150 mm 洞洞板</td><td>1</td><td>1</td></tr>
      </table>
    </div>
  </div>
  <p class="note">阶段对应：2 路 = J1–J2；6 路 = J1–J6（第一排）；
     11 路 = J1–J11（第二排再加 J7–J11）。表中 6 路 / 11 路列是相对 2 路基线的追加数量。</p>

  <h2>6. 装配顺序（每阶段断电再加线）</h2>
  <ol>
    <li><b>电源与排母：</b>焊 J0 2×22 排母、3V3/GND 粗铜线、CB1/CB2。
        断电测 3V3–GND 无短路，再上电测 3.3 V。</li>
    <li><b>J1 一路：</b>焊 J1 排母、RM1、RC1、C1 和全部 6 根线。
        上电测 J1 的 VCC≈3.3 V；烧 DIAG 固件确认 <code>WHO_AM_I=0x70</code>。</li>
    <li><b>J2：</b>同样焊好，跑
        <code>python3 tools/run_tests.py --port /dev/ttyACM0 --expect 2</code>。
        全部 PASS 才继续。</li>
    <li><b>6 路：</b>焊 J3–J6（第一排补齐），每颗都先单独确认 0x70，
        再跑 <code>--expect 6</code>。</li>
    <li><b>11 路：</b>焊 J7–J11（第二排），补齐 CB3，先逐颗确认，再跑
        <code>--expect 11</code>。</li>
    <li>每阶段单独保存串口日志；失败就停在该阶段，不跳级。</li>
  </ol>

  <h2>7. 上电前后检查清单</h2>
  <div class="grid2">
    <div>
      <h3>断电（万用表）</h3>
      <ul>
        <li>3V3–GND 不短路（>1 kΩ，随电容充电上升）。</li>
        <li>每个 Jn 的 VCC–GND 不短路。</li>
        <li>每根 CS 到对应 GPIO &lt;1 Ω；CS–GND 不导通。</li>
        <li>每根 MISO 经 120 Ω 到 J1-19；MISO–GND 不导通。</li>
        <li>SCLK→J1-18、MOSI→J1-17 &lt;1 Ω。</li>
        <li>每个模块 GND 到公共星形点 &lt;1 Ω。</li>
      </ul>
    </div>
    <div>
      <h3>上电（DIAG / TEST）</h3>
      <ul>
        <li>每个模块本地 VCC 3.2–3.4 V。</li>
        <li>每个已焊 CS 都能读到 <code>0x70</code>。</li>
        <li><code>--expect N</code> 全 PASS，退出码 0。</li>
        <li>流式模式逐源在线，热插拔事件正确显示。</li>
        <li>不要靠降 SPI 时钟掩盖接线问题。</li>
      </ul>
    </div>
  </div>

  <h2>8. 边界</h2>
  <p class="note">这套板验证的是<b>通信通路与健康度</b>，不是同步采样、精度、
     标定或无损记录。11 路轮询不构成同步采样；后续如需同步/连续记录，
     应走每颗 tagged FIFO + 传感器时间戳方案。1 MHz 是 bring-up 目标；
     坏帧先查焊接/地/串阻。</p>
</div>
</body>
</html>
"""


def build():
    html = (HTML
            .replace("__CSS__", CSS)
            .replace("__HEADER_SVG__", header_map_svg())
            .replace("__FRONT_SVG__", front_svg())
            .replace("__BACK_SVG__", back_svg())
            .replace("__CS_ROWS__", cs_rows_html())
            .replace("__MOD_ROWS__", module_rows_html()))
    return html


if __name__ == "__main__":
    text = build()
    OUT.write_text(text, encoding="utf-8")
    print(OUT)
    print(len(text.encode("utf-8")), "bytes")
