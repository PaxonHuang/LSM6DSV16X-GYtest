#!/usr/bin/env python3
"""Generate docs/evt-a-wiring-2-6-11.html from the frozen EVT-A pin contract.

One source of truth for the CS GPIO map, the bus split and the gate channel
assignment, so the schematic SVG, the IC pin table, the net list and the
breadboard row table cannot drift apart.

    python3 tools/gen_evt_a_wiring_html.py

Regenerate after any change to the contract. Do not hand-edit the HTML.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "evt-a-wiring-2-6-11.html"

# --- frozen EVT-A A02/A03 contract -----------------------------------------
CS = (1, 2, 4, 5, 6, 7, 8, 9, 10, 14, 15)          # sid0..sid10
BUS = {0: "B", 1: "A", 2: "A", 3: "A", 4: "A", 5: "A", 6: "A",
       7: "B", 8: "B", 9: "B", 10: "B"}
BUSPINS = {
    "A": {"host": "SPI2", "sclk": 12, "mosi": 11, "miso": 13},
    "B": {"host": "SPI3", "sclk": 18, "mosi": 21, "miso": 47},
}
# sid -> (package, channel). Monotone: stage 6 is a prefix of stage 11,
# so nothing already wired has to move when U3 is added.
GATE = {0: (1, 1), 1: (1, 2), 2: (1, 3), 3: (1, 4),
        4: (2, 1), 5: (2, 2), 6: (2, 3), 7: (2, 4),
        8: (3, 1), 9: (3, 2), 10: (3, 3)}

PINNAMES = {1: "/1OE", 2: "1A", 3: "1Y", 4: "/2OE", 5: "2A", 6: "2Y", 7: "GND",
            8: "3Y", 9: "3A", 10: "/3OE", 11: "4Y", 12: "4A", 13: "/4OE",
            14: "VCC"}
ROLE_OF_PIN = {1: "oe", 2: "a", 3: "y", 4: "oe", 5: "a", 6: "y",
               10: "oe", 9: "a", 8: "y", 13: "oe", 12: "a", 11: "y"}
CH_OF_PIN = {1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 2,
             10: 3, 9: 3, 8: 3, 13: 4, 12: 4, 11: 4}
# package -> first breadboard row it occupies (spans 7 rows)
PKG_ROW = {1: 2, 2: 12, 3: 20}
SID_OF = {v: k for k, v in GATE.items()}

# fixed breadboard rows shared by every stage
ROW_SCLK, ROW_MOSI, ROW_MISO, ROW_MISO2 = 9, 10, 11, 19

STAGES = [
    dict(key="s2", label="2 源", sids=[0, 1], pkgs=[1],
         expect="0,1", bench="阶段 A（已验证）"),
    dict(key="s6", label="6 源", sids=[0, 1, 2, 3, 4, 7], pkgs=[1, 2],
         expect="0,1,2,3,4,7", bench="阶段 B（下一步实测）"),
    dict(key="s11", label="11 源", sids=list(range(11)), pkgs=[1, 2, 3],
         expect="0,1,2,3,4,5,6,7,8,9,10", bench="阶段 C（最终全源）"),
]


# --- helpers ---------------------------------------------------------------
def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def net_class(net: str) -> str:
    if net == "3V3":
        return "pwr"
    if net == "GND":
        return "gnd"
    if net == "OPEN" or net == "—":
        return "nc"
    if net.startswith("A_"):
        return "busA"
    if net.startswith("B_"):
        return "busB"
    if net.endswith("_CS"):
        return "cs"
    if net.endswith("_MISO"):
        return "miso"
    return "nc"


def half_pin(pkg: int, pin: int):
    base = PKG_ROW[pkg]
    if 1 <= pin <= 7:
        return base + pin - 1, "u"
    return base + 14 - pin, "l"


def y_targets(st):
    """Assign every gate output to a MISO collection row.

    Row 11 holds five holes per half: one for the DevKit wire, four for gate
    outputs. Anything beyond that spills to row 19, which is jumpered to row 11.
    """
    out = {}
    for bus in ("A", "B"):
        pins = sorted(((half_pin(*GATE[s])[0], half_pin(*GATE[s])[1], s)
                       for s in st["sids"] if BUS[s] == bus))
        first = pins[:4]
        rest = pins[4:]
        for _, _, s in first:
            out[s] = ("11", "u" if bus == "A" else "l")
        for _, _, s in rest:
            out[s] = ("19", "u" if bus == "A" else "l")
    return out


def cell(pkg: int, pin: int, st):
    """Return (net, [connection lines]) for one IC pin in this stage."""
    if pin == 7:
        return "GND", [f"U{pkg} p7 GND", "→ GND 轨"]
    if pin == 14:
        return "3V3", [f"U{pkg} p14 VCC", "→ 3V3 轨", "100nF 到 GND"]
    ch = CH_OF_PIN[pin]
    role = ROLE_OF_PIN[pin]
    sid = SID_OF.get((pkg, ch))
    sids = st.get("_sids", [])
    if sid is not None and sid in sids:
        if role == "oe":
            return f"SID{sid}_CS", [f"U{pkg} p{pin} /{ch}OE",
                                    f"← GPIO{CS[sid]}", "10k → 3V3",
                                    f"模块 sid{sid} CS"]
        if role == "a":
            return f"SID{sid}_MISO", [f"U{pkg} p{pin} {ch}A",
                                      f"← 模块 sid{sid} SDO"]
        row, half = st["_yt"][sid]
        side = "上" if half == "u" else "下"
        return f"{BUS[sid]}_MISO", [f"U{pkg} p{pin} {ch}Y",
                                    f"跳线 → row {row} {side}"]
    if role == "oe":
        return "3V3", [f"U{pkg} p{pin} /{ch}OE 未用", "→ 3V3 轨"]
    if role == "a":
        return "GND", [f"U{pkg} p{pin} {ch}A 未用", "→ GND 轨"]
    return "—", [f"U{pkg} p{pin} {ch}Y 悬空"]


def breadboard_rows(st):
    """row -> {'u': (net, lines), 'l': (net, lines)}"""
    rows = {1: {"u": ("3V3", ["跳线 → 3V3 轨"]),
                "l": ("GND", ["跳线 → GND 轨"])}}
    for pkg in st["pkgs"]:
        for pin in range(1, 15):
            r, h = half_pin(pkg, pin)
            rows.setdefault(r, {})[h] = cell(pkg, pin, st)
    rows.setdefault(ROW_SCLK, {})["u"] = (
        "A_SCLK", [f"GPIO{BUSPINS['A']['sclk']}", "→ bus A 各模块 SCL"])
    rows[ROW_SCLK]["l"] = (
        "B_SCLK", [f"GPIO{BUSPINS['B']['sclk']}", "→ bus B 各模块 SCL"])
    rows.setdefault(ROW_MOSI, {})["u"] = (
        "A_MOSI", [f"GPIO{BUSPINS['A']['mosi']}", "→ bus A 各模块 SDA"])
    rows[ROW_MOSI]["l"] = (
        "B_MOSI", [f"GPIO{BUSPINS['B']['mosi']}", "→ bus B 各模块 SDA"])
    rows.setdefault(ROW_MISO, {})["u"] = (
        "A_MISO", [f"GPIO{BUSPINS['A']['miso']}", "各 A 门 Y 汇流（≤4 个）"])
    rows[ROW_MISO]["l"] = (
        "B_MISO", [f"GPIO{BUSPINS['B']['miso']}", "各 B 门 Y 汇流（≤4 个）"])
    if any(r == str(ROW_MISO2) for r, _ in st["_yt"].values()):
        rows.setdefault(ROW_MISO2, {})["u"] = (
            "A_MISO₂", ["跳线 ↔ row 11 上", "余下 A 门 Y"])
        rows[ROW_MISO2]["l"] = (
            "B_MISO₂", ["跳线 ↔ row 11 下", "余下 B 门 Y"])
    return rows


# --- SVG -------------------------------------------------------------------
def svg_ic(x, y, pkg, st) -> str:
    w, h = 200, 6 * 30 + 46
    out = [f'<g transform="translate({x},{y})">',
           f'<rect x="0" y="0" width="{w}" height="{h}" rx="8" class="icbox"/>',
           f'<text x="{w/2}" y="22" class="ictitle" text-anchor="middle">'
           f'U{pkg}  SN74HC125N</text>']
    for i in range(7):
        yy = 42 + i * 30
        pl, pr = i + 1, 14 - i
        out.append(f'<line x1="-18" y1="{yy}" x2="0" y2="{yy}" class="pin"/>')
        out.append(f'<text x="8" y="{yy+4}" class="pinname">{pl} {PINNAMES[pl]}</text>')
        nl, _ = cell(pkg, pl, st)
        if nl != "—":
            out.append(f'<line x1="-18" y1="{yy}" x2="-32" y2="{yy}" '
                       f'class="{net_class(nl)}ln"/>')
            out.append(f'<text x="-38" y="{yy+4}" class="net {net_class(nl)}" '
                       f'text-anchor="end">{esc(nl)}</text>')
        out.append(f'<line x1="{w}" y1="{yy}" x2="{w+18}" y2="{yy}" class="pin"/>')
        out.append(f'<text x="{w-8}" y="{yy+4}" class="pinname" '
                   f'text-anchor="end">{pr} {PINNAMES[pr]}</text>')
        nr, _ = cell(pkg, pr, st)
        if nr != "—":
            out.append(f'<line x1="{w+18}" y1="{yy}" x2="{w+32}" y2="{yy}" '
                       f'class="{net_class(nr)}ln"/>')
            out.append(f'<text x="{w+38}" y="{yy+4}" class="net {net_class(nr)}">'
                       f'{esc(nr)}</text>')
    out.append("</g>")
    return "".join(out)


def svg_devkit(x, y, st) -> str:
    rows = [("3V3", "3V3", "pwr"), ("GND", "GND", "gnd")]
    for sid in st["sids"]:
        rows.append((f"GPIO{CS[sid]}", f"SID{sid}_CS", "cs"))
    for b in ("A", "B"):
        for k, t in (("sclk", "SCLK"), ("mosi", "MOSI"), ("miso", "MISO")):
            rows.append((f"GPIO{BUSPINS[b][k]}", f"{b}_{t}", f"bus{b}"))
    w = 250
    h = len(rows) * 26 + 58
    out = [f'<g transform="translate({x},{y})">',
           f'<rect x="0" y="0" width="{w}" height="{h}" rx="8" class="devbox"/>',
           '<text x="14" y="22" class="ictitle">ESP32-S3-DevKitC-1 N16R8</text>',
           '<text x="14" y="40" class="icnote">插拔式 Mainboard 对应脚位</text>']
    for i, (gpio, net, c) in enumerate(rows):
        yy = 62 + i * 26
        out.append(f'<text x="14" y="{yy+4}" class="pinname">{esc(gpio)}</text>')
        out.append(f'<line x1="{w}" y1="{yy}" x2="{w+18}" y2="{yy}" class="pin"/>')
        out.append(f'<line x1="{w+18}" y1="{yy}" x2="{w+32}" y2="{yy}" class="{c}ln"/>')
        out.append(f'<text x="{w+38}" y="{yy+4}" class="net {c}">{esc(net)}</text>')
    out.append("</g>")
    return "".join(out)


def svg_stage(st) -> str:
    # One column of ICs: left-side net labels of a block never collide with the
    # right-side labels of the block above it.
    ic_x, ic_y0, gap = 520, 20, 36
    dev_h = (2 + len(st["sids"]) + 6) * 26 + 58
    ic_h = 226
    n = len(st["pkgs"])
    width = ic_x + 200 + 190
    height = max(dev_h, ic_y0 + n * ic_h + (n - 1) * gap) + 30
    parts = [f'<svg viewBox="0 0 {width} {height}" class="sch" '
             f'xmlns="http://www.w3.org/2000/svg">',
             '<rect width="100%" height="100%" fill="#ffffff"/>']
    parts.append(svg_devkit(24, 20, st))
    for i, pkg in enumerate(st["pkgs"]):
        parts.append(svg_ic(ic_x, ic_y0 + i * (ic_h + gap), pkg, st))
    parts.append("</svg>")
    return "".join(parts)


# --- HTML sections ---------------------------------------------------------
def icon_table(st) -> str:
    head = ('<table class="pins"><thead><tr><th>pin</th><th>名称</th>'
            '<th>网络</th><th>接到</th></tr></thead><tbody>')
    body = []
    for pkg in st["pkgs"]:
        body.append(f'<tr class="pkghdr"><td colspan="4">U{pkg} '
                    f'SN74HC125N（面包板 row {PKG_ROW[pkg]}–'
                    f'{PKG_ROW[pkg]+6}）</td></tr>')
        for pin in range(1, 15):
            net, lines = cell(pkg, pin, st)
            c = net_class(net)
            body.append(
                f'<tr><td>{pin}</td><td>{PINNAMES[pin]}</td>'
                f'<td class="n-{c}">{esc(net)}</td>'
                f'<td class="conn">{" · ".join(esc(x) for x in lines)}</td></tr>')
    return head + "".join(body) + "</tbody></table>"


def module_table(st) -> str:
    head = ('<table class="pins"><thead><tr><th>sid</th><th>总线</th>'
            '<th>CS GPIO</th><th>SCL/SPC</th><th>SDA/MOSI</th>'
            '<th>SDO/MISO → 门</th><th>门脚</th></tr></thead><tbody>')
    body = []
    for sid in st["sids"]:
        b = BUS[sid]
        pkg, ch = GATE[sid]
        body.append(
            f'<tr><td><b>{sid}</b></td><td class="n-bus{b}">{b}</td>'
            f'<td class="n-cs">GPIO{CS[sid]}</td>'
            f'<td class="n-bus{b}">GPIO{BUSPINS[b]["sclk"]}</td>'
            f'<td class="n-bus{b}">GPIO{BUSPINS[b]["mosi"]}</td>'
            f'<td class="n-miso">{esc(f"SID{sid}_MISO")}</td>'
            f'<td>U{pkg} p{CHPIN[ch]["a"]} ({ch}A)</td></tr>')
    return head + "".join(body) + "</tbody></table>"


CHPIN = {1: {"oe": 1, "a": 2, "y": 3}, 2: {"oe": 4, "a": 5, "y": 6},
         3: {"oe": 10, "a": 9, "y": 8}, 4: {"oe": 13, "a": 12, "y": 11}}


def netlist_table(st) -> str:
    nets = {"3V3": [], "GND": [], "A_SCLK": [], "A_MOSI": [], "A_MISO": [],
            "B_SCLK": [], "B_MOSI": [], "B_MISO": []}
    for sid in st["sids"]:
        nets[f"SID{sid}_CS"] = []
        nets[f"SID{sid}_MISO"] = []
    nets["3V3"].append("DevKit 3V3 脚")
    nets["GND"].append("DevKit GND 脚")
    for sid in st["sids"]:
        b = BUS[sid]
        pkg, ch = GATE[sid]
        nets["3V3"].append(f"模块 sid{sid} VCC")
        nets["3V3"].append(f"10k 上拉（sid{sid} CS）")
        nets["GND"].append(f"模块 sid{sid} GND")
        nets[f"SID{sid}_CS"] = [f"DevKit GPIO{CS[sid]}",
                                f"U{pkg} p{CHPIN[ch]['oe']} /{ch}OE",
                                f"模块 sid{sid} CS", "10k → 3V3"]
        nets[f"SID{sid}_MISO"] = [f"模块 sid{sid} SDO",
                                  f"U{pkg} p{CHPIN[ch]['a']} {ch}A"]
        nets[f"{b}_MISO"].append(f"U{pkg} p{CHPIN[ch]['y']} {ch}Y")
        nets[f"{b}_SCLK"].append(f"模块 sid{sid} SCL")
        nets[f"{b}_MOSI"].append(f"模块 sid{sid} SDA")
    for pkg in st["pkgs"]:
        nets["3V3"].append(f"U{pkg} p14 VCC")
        nets["GND"].append(f"U{pkg} p7 GND")
        for pin in range(1, 15):
            net, _ = cell(pkg, pin, st)
            if net == "3V3" and pin != 14:
                nets["3V3"].append(f"U{pkg} p{pin} 未用 /OE")
            if net == "GND" and pin != 7:
                nets["GND"].append(f"U{pkg} p{pin} 未用 A")
    for b in ("A", "B"):
        nets[f"{b}_SCLK"].insert(0, f"DevKit GPIO{BUSPINS[b]['sclk']}")
        nets[f"{b}_MOSI"].insert(0, f"DevKit GPIO{BUSPINS[b]['mosi']}")
        nets[f"{b}_MISO"].insert(0, f"DevKit GPIO{BUSPINS[b]['miso']}")
    head = ('<table class="pins nl"><thead><tr><th>网络</th>'
            '<th>全部端点（万用表通断档逐点核对）</th></tr></thead><tbody>')
    body = []
    for name in sorted(nets, key=lambda n: (net_class(n), n)):
        c = net_class(name)
        body.append(f'<tr><td class="n-{c}"><b>{esc(name)}</b></td>'
                    f'<td class="conn">{" · ".join(esc(x) for x in nets[name])}</td></tr>')
    return head + "".join(body) + "</tbody></table>"


def breadboard_table(st) -> str:
    rows = breadboard_rows(st)
    head = ('<table><thead><tr><th>row</th>'
            '<th>上排 a–e（5 孔同网络）</th><th>下排 f–j（5 孔同网络）</th>'
            '</tr></thead><tbody>')
    body = []
    for r in range(1, 31):
        if r not in rows:
            body.append(f"<tr><th class='rowno'>{r}</th>"
                        "<td class='net net-spare' colspan='2'>留空</td></tr>")
            continue
        cells = []
        for h in ("u", "l"):
            if h in rows[r]:
                net, lines = rows[r][h]
                c = net_class(net)
                cells.append(
                    f'<td class="net net-{c}"><b>{esc(net)}</b><ul>'
                    + "".join(f"<li>{esc(x)}</li>" for x in lines) + "</ul></td>")
            else:
                cells.append("<td class='net net-spare'>—</td>")
        body.append(f"<tr><th class='rowno'>{r}</th>" + "".join(cells) + "</tr>")
    return head + "".join(body) + "</tbody></table>"


def checklist(st) -> str:
    items = [
        "USB 已拔掉，整板断电。",
        "3V3 轨与 GND 轨之间不短路（二极管档 / 电阻档）。",
        f"{len(st['sids'])} 颗模块的 VCC 都在 3V3 轨、GND 都在 GND 轨；没有 5V。",
        "每个 CS 到对应 GPIO 通，且各有一颗 10kΩ 到 3V3。",
        "每个模块 SDO/MISO 只进一个门输入（1A/2A/3A/4A），没有两颗共用。",
        "每片 74HC125 的 pin7=GND、pin14=3V3，各有一颗 100nF。",
        "未用通道：/OE→3V3、A→GND、Y 悬空；没有悬空输入。",
        "每个门输出只汇到本总线 MISO（A=GPIO13，B=GPIO47），不跨总线。",
    ]
    return ('<ol class="check">' + "".join(f"<li>{esc(x)}</li>" for x in items)
            + "</ol>")


def net_rules(st) -> str:
    pkg_list = "、".join(f"U{p}" for p in st["pkgs"])
    return f"""<div class="warn"><b>五条硬规则（违反任意一条都会得到假 PASS）</b><ol>
<li><b>一个门只接一颗 MISO。</b>两颗模块的 SDO 并到同一个 1A/2A/3A/4A 会互相驱动，
总线 B 尤其容易看起来"能过"。串一颗电阻<b>不是</b>隔离。</li>
<li><b>每颗 CS 必须 10kΩ 上拉到 3V3。</b>复位后到固件配置 GPIO 之前，
CS 是高阻浮空；没有上拉，/OE 可能被拉低，多个门同时打开。</li>
<li><b>同一时刻每条总线只能有一个 /OE 为低。</b>由固件保证；接线上不要
把两个 CS 并到同一个 GPIO。</li>
<li><b>未用门必须终止：</b>/OE→3V3、A→GND、Y 悬空。悬空的 CMOS 输入会
自激并把噪声灌进同一片芯片的其它通道。</li>
<li><b>禁止带电插拔 IMU。</b>断电改线，上电先量 3V3。</li>
</ol></div>
<div class="note"><b>本阶段用到 {pkg_list}。</b>74HC125 的 /OE 低有效，CS 也低有效，
所以 CS 直接接 /OE，选中时门导通；未选中时 Y 为高阻，不占用 MISO。
74HC125 是同相缓冲，MISO 极性不变。</div>"""


def stage_section(st) -> str:
    sids = st["sids"]
    pkgs = st["pkgs"]
    bA = [s for s in sids if BUS[s] == "A"]
    bB = [s for s in sids if BUS[s] == "B"]
    absent = [s for s in range(11) if s not in sids]
    absent_txt = "、".join(str(s) for s in absent) if absent else "无"
    warn_extra = ""
    if st["key"] == "s6":
        warn_extra = (
            '<div class="note"><b>6 源需要第 2 片 SN74HC125N。</b>'
            'U2 的 channel 2/3（对应 sid5/sid6）本阶段不用，必须按'
            '「/OE→3V3、A→GND、Y 悬空」终止。U3 不插。</div>')
    if st["key"] == "s11":
        warn_extra = (
            '<div class="note"><b>11 源需要第 3 片 SN74HC125N（U3）。</b>'
            'U3 的 channel 4 不用，同样终止。整板占 row 1–26，row 27–30 留空。</div>')
    return f"""
<section id="{st['key']}">
<h2>{st['label']} · {st['bench']}</h2>
<p><b>源：</b> sid {", ".join(map(str, sids))}<br>
<b>总线 A（SPI2，GPIO12/11/13）：</b> sid {", ".join(map(str, bA)) or "—"}<br>
<b>总线 B（SPI3，GPIO18/21/47）：</b> sid {", ".join(map(str, bB)) or "—"}<br>
<b>本阶段应为 ABSENT：</b> {absent_txt}</p>
{warn_extra}

<h3>精准原理图（逐脚网络标号，同名网络即相连）</h3>
{svg_stage(st)}
<div class="legend">
<span><i style="background:#fde2e1"></i>3V3</span>
<span><i style="background:#e9e9e9"></i>GND</span>
<span><i style="background:#dcecff"></i>总线 A</span>
<span><i style="background:#ffe8d1"></i>总线 B</span>
<span><i style="background:#ecd9f5"></i>CS / OE</span>
<span><i style="background:#f9d9ea"></i>原始 MISO（门输入）</span>
<span><i style="background:#f2f2f2"></i>未用</span>
</div>

<h3>74HC125 逐脚接线</h3>
{icon_table(st)}

<h3>模块侧接线（GY-LSM6DSV16X 6 针）</h3>
{module_table(st)}

<h3>网络清单（焊接/接线后逐条通断核对）</h3>
{netlist_table(st)}

{net_rules(st)}

<h3>面包板逐行表</h3>
<p>约定：74HC125 缺口朝上跨中缝，<b>上排 k 行 = pin k</b>，
<b>下排 k 行 = pin 15−k</b>。每横排 5 孔同网络，相邻行绝缘。
模块一律外置，用 6 根跳线接到对应行/轨。</p>
{breadboard_table(st)}

<h3>断电测量检查单</h3>
{checklist(st)}
</section>"""


def transition_section() -> str:
    return """
<section id="steps">
<h2>推进顺序与命令</h2>
<ol class="check">
<li><b>阶段 A（2 源）已完成并 PASS</b>，不要再跑。接线图见
<a href="breadboard-2-source-evt-a.html">breadboard-2-source-evt-a.html</a>。</li>
<li><b>阶段 B（6 源）</b>：在已验证的 U1 上启用 channel 3/4，新增 U2，
接 sid2/sid3/sid4/sid7，跑
<code>--expect-sources 0,1,2,3,4,7</code>。</li>
<li><b>阶段 C（11 源）</b>：U2 的 channel 2/3 改为 sid5/sid6，新增 U3 接
sid8/9/10，跑 <code>--expect-sources 0,1,...,10</code>，再做 60 s 与 600 s 流。</li>
</ol>

<h3>从阶段 A 改到阶段 B（只动这些）</h3>
<table class="pins move"><thead><tr><th>位置</th><th>阶段 A 现状</th><th>改为</th></tr></thead><tbody>
<tr><td>U1 p13 /4OE（row 3 下）</td><td>→ 3V3（禁用）</td><td class="n-cs">SID3_CS，GPIO5，10k</td></tr>
<tr><td>U1 p12 4A（row 4 下）</td><td>→ GND</td><td class="n-miso">sid3 SDO</td></tr>
<tr><td>U1 p11 4Y（row 5 下）</td><td>悬空</td><td class="n-busA">A_MISO → row 11 上</td></tr>
<tr><td>U1 p10 /3OE（row 6 下）</td><td>→ 3V3（禁用）</td><td class="n-cs">SID2_CS，GPIO4，10k</td></tr>
<tr><td>U1 p9 3A（row 7 下）</td><td>→ GND</td><td class="n-miso">sid2 SDO</td></tr>
<tr><td>U1 p8 3Y（row 8 下）</td><td>悬空</td><td class="n-busA">A_MISO → row 11 上</td></tr>
<tr><td>U1 p3 1Y（row 4 上）</td><td>直连 GPIO47</td><td>改跳线到 row 11 下（B_MISO 汇流）</td></tr>
<tr><td>U1 p6 2Y（row 7 上）</td><td>直连 GPIO13</td><td>改跳线到 row 11 上（A_MISO 汇流）</td></tr>
<tr><td>新增</td><td>—</td><td>U2 插 row 12–18；row 11 做 MISO 汇流</td></tr>
</tbody></table>
<p class="small">row 9 / row 10 的 SCLK、MOSI 不动；U1 channel 1/2 的
SID0_CS、SID0_MISO、SID1_CS、SID1_MISO 四个脚也不动。</p>

<h3>从阶段 B 改到阶段 C</h3>
<table class="pins move"><thead><tr><th>位置</th><th>阶段 B 现状</th><th>改为</th></tr></thead><tbody>
<tr><td>U2 p4 /2OE（row 15 上）</td><td>→ 3V3（禁用）</td><td class="n-cs">SID5_CS，GPIO7，10k</td></tr>
<tr><td>U2 p5 2A（row 16 上）</td><td>→ GND</td><td class="n-miso">sid5 SDO</td></tr>
<tr><td>U2 p6 2Y（row 17 上）</td><td>悬空</td><td class="n-busA">A_MISO → row 19 上</td></tr>
<tr><td>U2 p10 /3OE（row 16 下）</td><td>→ 3V3（禁用）</td><td class="n-cs">SID6_CS，GPIO8，10k</td></tr>
<tr><td>U2 p9 3A（row 17 下）</td><td>→ GND</td><td class="n-miso">sid6 SDO</td></tr>
<tr><td>U2 p8 3Y（row 18 下）</td><td>悬空</td><td class="n-busA">A_MISO → row 19 上</td></tr>
<tr><td>新增</td><td>—</td><td>U3 插 row 20–26，接 sid8/9/10（全在总线 B）</td></tr>
</tbody></table>

<h3>命令</h3>
<pre><code>. ~/.espressif/v6.0.2/esp-idf/export.sh
PORT=/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_98:88:E0:11:9F:08-if00

# 阶段 B 健康测试（6 源）
tools/mode.sh test &amp;&amp; tools/build.sh
python3 tools/run_tests.py --port "$PORT" --expect-sources 0,1,2,3,4,7 \\
    --raw evidence/2026-11-03-field/stage3-health.raw

# 阶段 B 60 s 流
tools/mode.sh stream &amp;&amp; tools/build.sh
python3 tools/stream_capture.py --port "$PORT" --duration 60 \\
    --out evidence/2026-11-03-field/stream-6src.jsonl \\
    --raw evidence/2026-11-03-field/stream-6src.raw
python3 tools/analyze_stream.py --input evidence/2026-11-03-field/stream-6src.jsonl \\
    --window 10 --out evidence/2026-11-03-field/stream-6src-analysis.json

# 阶段 C（同样两条，换 --expect-sources 0,1,2,3,4,5,6,7,8,9,10 和文件名）</code></pre>

<h3>判据</h3>
<ul>
<li>每个预期源 <code>UNIT_RESULT n PASS</code>、<code>WHO_AM_I=0x70</code>、
29–34 项自检全过。</li>
<li><code>BUS_BIND</code>：sid0→B、sid7→B、sid8/9/10→B，其余→A；
CS 与上表逐一对应。</li>
<li><code>BUS_STATS A tx&gt;0 err=0</code>、<code>BUS_STATS B tx&gt;0 err=0</code>。</li>
<li><code>SUMMARY</code> 的 present 等于预期集合，其余为 ABSENT。</li>
<li>Flash 回读字节一致（run_tests.py 自动做，失败即中止）。</li>
<li>流测试：每个源 valid_ratio=1.000、seq_gaps=0、errors=0、无 boot_epoch 变化。</li>
</ul>
<div class="warn"><b>不允许</b>通过降频、降阈值、把 ABSENT 当 PASS、或跳过 6 源
直接上 11 源来取得结果。任何一步失败：先停、保留原始日志、定位后再最多
复测一次。</div>
</section>"""


def page() -> str:
    for st in STAGES:
        st["_sids"] = st["sids"]
        st["_yt"] = y_targets(st)
    body = "".join(stage_section(st) for st in STAGES)
    body += transition_section()
    nav = "".join(f'<a href="#{st["key"]}">{st["label"]}</a>' for st in STAGES)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EVT-A 双 SPI · 2/6/11 源原理图与面包板接线</title>
<style>
body{{margin:0;background:#f4f3ee;color:#172320;font-family:Inter,'Noto Sans CJK SC','Microsoft YaHei',system-ui,sans-serif}}
main{{max-width:1280px;margin:0 auto;padding:24px 18px 64px}}
h1{{font-size:25px;margin:4px 0 6px}}
h2{{font-size:20px;margin:34px 0 12px;padding-top:12px;border-top:2px solid #d5ddd6}}
h3{{font-size:15px;margin:22px 0 8px;color:#25463c}}
p,li{{line-height:1.65;font-size:14px}}
.small{{font-size:12.5px;color:#555}}
nav{{position:sticky;top:0;background:#f4f3ee;padding:10px 0;z-index:5;
display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid #d9ded8}}
nav a{{font-size:13px;padding:5px 12px;border-radius:14px;background:#e5ebe5;
color:#20443a;text-decoration:none;font-weight:600}}
nav a:hover{{background:#cfdccf}}
.warn{{background:#fdecea;border-left:4px solid #b23a34;padding:12px 14px;border-radius:6px;margin:14px 0}}
.note{{background:#fbf6e6;border-left:4px solid #b58a3c;padding:12px 14px;border-radius:6px;margin:14px 0}}
.legend{{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin:10px 0}}
.legend i{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px}}
table{{border-collapse:collapse;width:100%;font-size:12px;background:#fff;margin:8px 0}}
th,td{{border:1px solid #c9d2ca;padding:5px 6px;vertical-align:top}}
thead th{{background:#e8efe9;text-align:left}}
.rowno{{background:#eef2ee;width:38px;text-align:center}}
.net ul{{margin:4px 0 0 14px;padding:0}}
.net li{{font-size:11.5px;line-height:1.45}}
.net-pwr{{background:#fde2e1}} .net-gnd{{background:#e9e9e9}}
.net-busA{{background:#dcecff}} .net-busB{{background:#ffe8d1}}
.net-cs{{background:#ecd9f5}} .net-miso{{background:#f9d9ea}}
.net-nc{{background:#f2f2f2;color:#777}} .net-spare{{background:#fafafa;color:#aaa}}
td.n-pwr,.n-pwr{{background:#fde2e1}} td.n-gnd,.n-gnd{{background:#e9e9e9}}
td.n-busA,.n-busA{{background:#dcecff}} td.n-busB,.n-busB{{background:#ffe8d1}}
td.n-cs,.n-cs{{background:#ecd9f5}} td.n-miso,.n-miso{{background:#f9d9ea}}
td.n-nc,.n-nc{{background:#f2f2f2;color:#777}}
.conn{{font-size:11.5px}}
table.pins td:first-child{{text-align:center;font-weight:700;width:42px}}
table.nl td:first-child{{width:150px}}
table.move td:first-child{{width:210px;text-align:left;font-weight:400}}
tr.pkghdr td{{background:#dfe9e2;font-weight:700}}
ol.check li{{margin:5px 0}}
pre{{background:#101614;color:#d9f2e4;padding:12px 14px;border-radius:7px;
overflow-x:auto;font-size:12px;line-height:1.55}}
code{{font-family:'JetBrains Mono',ui-monospace,monospace}}
svg.sch{{width:100%;height:auto;background:#fff;border:1px solid #d5ddd6;border-radius:8px}}
.icbox{{fill:#fbfdfb;stroke:#3c5a4c;stroke-width:1.4}}
.devbox{{fill:#f6f8fb;stroke:#2b4a6f;stroke-width:1.6}}
.ictitle{{font-size:12px;font-weight:700;fill:#1d3a2e}}
.icnote{{font-size:10px;fill:#68786f}}
.pinname{{font-size:10px;fill:#2b3b33;font-family:ui-monospace,monospace}}
.net{{font-size:10.5px;font-family:ui-monospace,monospace;font-weight:600}}
.net.pwr{{fill:#a8302a}} .net.gnd{{fill:#444}} .net.busA{{fill:#1d4ed8}}
.net.busB{{fill:#b45309}} .net.cs{{fill:#6d28d9}} .net.miso{{fill:#be185d}}
.net.nc{{fill:#9aa0a6}}
.pin{{stroke:#7b8a82;stroke-width:1}}
.pwrln{{stroke:#a8302a;stroke-width:1.2}} .gndln{{stroke:#444;stroke-width:1.2}}
.busAln{{stroke:#1d4ed8;stroke-width:1.2}} .busBln{{stroke:#b45309;stroke-width:1.2}}
.csln{{stroke:#6d28d9;stroke-width:1.2}} .misoln{{stroke:#be185d;stroke-width:1.2}}
.ncln{{stroke:#9aa0a6;stroke-width:1}}
@media print{{body{{background:#fff}}nav{{display:none}}pre{{background:#f2f2f2;color:#000}}}}
</style></head><body><main>
<h1>EVT-A 双 SPI · 2/6/11 源精准原理图与面包板接线</h1>
<p class="small">由 <code>tools/gen_evt_a_wiring_html.py</code> 从冻结的 EVT-A
A02/A03 引脚合同生成。CS 表 <code>1,2,4,5,6,7,8,9,10,14,15</code>；
总线 A=SPI2 GPIO12/11/13 对应 sid1–6，总线 B=SPI3 GPIO18/21/47 对应
sid0、7–10。与 <code>docs/evt-a-pinmap.json</code> 一致。</p>
<nav>{nav}<a href="#steps">推进顺序与命令</a></nav>
{body}
</main></body></html>
"""


def main() -> None:
    html = page()
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
