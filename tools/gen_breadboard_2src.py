#!/usr/bin/env python3
"""Generate the 2-source EVT-A breadboard row map.

The map is a table whose rows are the breadboard's 30 hole rows and whose
columns are the two 5-hole halves plus the four vertical rails. Each used row
is one net; the cell lists every wire that lands in that row.
"""
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "docs" / "breadboard-2-source-evt-a.html"

# row -> (net name, css class, [connections])
TOP = {
    1: ("3V3 备用", "pwr", ["跳线 → 3V3 轨（可选）"]),
    2: ("SID0_CS", "cs", ["U1 pin1 /1OE", "模块 sid0 CS", "GPIO1", "RCS0 10k → 3V3 轨"]),
    3: ("SID0_MISO", "miso", ["U1 pin2 1A", "模块 sid0 MISO/SDO"]),
    4: ("B_MISO", "busB", ["U1 pin3 1Y", "GPIO47"]),
    5: ("SID1_CS", "cs", ["U1 pin4 /2OE", "模块 sid1 CS", "GPIO2", "RCS1 10k → 3V3 轨"]),
    6: ("SID1_MISO", "miso", ["U1 pin5 2A", "模块 sid1 MISO/SDO"]),
    7: ("A_MISO", "busA", ["U1 pin6 2Y", "GPIO13"]),
    8: ("GND", "gnd", ["U1 pin7", "跳线 → GND 轨"]),
    9: ("A_SCLK", "busA", ["GPIO12", "模块 sid1 SCL/SPC"]),
    10: ("A_MOSI", "busA", ["GPIO11", "模块 sid1 MOSI/SDA/SDI"]),
}
BOTTOM = {
    1: ("GND", "gnd", ["跳线 → GND 轨", "CU1 100nF 一端"]),
    2: ("U1_VCC", "pwr", ["U1 pin14", "跳线 → 3V3 轨", "CU1 100nF 另一端"]),
    3: ("未用 /4OE", "nc", ["U1 pin13 → 3V3 轨"]),
    4: ("未用 4A", "nc", ["U1 pin12 → GND 轨"]),
    5: ("未用 4Y", "nc", ["U1 pin11 悬空"]),
    6: ("未用 /3OE", "nc", ["U1 pin10 → 3V3 轨"]),
    7: ("未用 3A", "nc", ["U1 pin9 → GND 轨"]),
    8: ("未用 3Y", "nc", ["U1 pin8 悬空"]),
    9: ("B_SCLK", "busB", ["GPIO18", "模块 sid0 SCL/SPC"]),
    10: ("B_MOSI", "busB", ["GPIO21", "模块 sid0 MOSI/SDA/SDI"]),
}

PINS = [
    ("1", "/1OE", "sid0 CS 门控", "上 2"),
    ("2", "1A", "sid0 MISO 输入", "上 3"),
    ("3", "1Y", "sid0 缓冲输出", "上 4（B_MISO）"),
    ("4", "/2OE", "sid1 CS 门控", "上 5"),
    ("5", "2A", "sid1 MISO 输入", "上 6"),
    ("6", "2Y", "sid1 缓冲输出", "上 7（A_MISO）"),
    ("7", "GND", "地", "GND 轨"),
    ("8", "3Y", "未用，悬空", "下 8"),
    ("9", "3A", "未用，拉低", "下 7 → GND"),
    ("10", "/3OE", "未用，拉高禁用", "下 6 → 3V3"),
    ("11", "4Y", "未用，悬空", "下 5"),
    ("12", "4A", "未用，拉低", "下 4 → GND"),
    ("13", "/4OE", "未用，拉高禁用", "下 3 → 3V3"),
    ("14", "VCC", "3.3V", "3V3 轨"),
]


def cell(net_map, row):
    if row in net_map:
        name, cls, wires = net_map[row]
        items = "".join(f"<li>{w}</li>" for w in wires)
        return f'<td class="net net-{cls}"><b>{name}</b><ul>{items}</ul></td>'
    return '<td class="net net-spare">空</td>'


def pin_table():
    rows = "".join(
        f"<tr><td>{p}</td><td>{n}</td><td>{u}</td><td>{w}</td></tr>"
        for p, n, u, w in PINS
    )
    return (
        "<table class='pins'><thead><tr><th>pin</th><th>名称</th>"
        "<th>2 源用途</th><th>接到</th></tr></thead><tbody>"
        + rows
        + "</tbody></table>"
    )


def main():
    body = []
    for r in range(1, 11):
        body.append(
            "<tr>"
            f"<th class='rowno'>{r}</th>"
            "<td class='rail rail-pwr'>3V3</td>"
            "<td class='rail rail-gnd'>GND</td>"
            f"{cell(TOP, r)}"
            f"{cell(BOTTOM, r)}"
            "<td class='rail rail-gnd'>GND</td>"
            "<td class='rail rail-pwr'>3V3</td>"
            "</tr>"
        )
    body.append(
        "<tr><th class='rowno'>11–30</th>"
        "<td class='rail rail-pwr'>3V3</td><td class='rail rail-gnd'>GND</td>"
        "<td class='net net-spare' colspan='2'>全部留空（本 2 源方案只用 1–10 行）</td>"
        "<td class='rail rail-gnd'>GND</td><td class='rail rail-pwr'>3V3</td></tr>"
    )

    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EVT-A 2 源面包板逐行接线图</title>
<style>
body{{margin:0;background:#f4f3ee;color:#172320;font-family:Inter,'Noto Sans CJK SC','Microsoft YaHei',system-ui,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:24px 18px 48px}}
h1{{font-size:24px;margin:4px 0 10px}}
h2{{font-size:18px;margin:26px 0 10px}}
p,li{{line-height:1.65;font-size:14px}}
.warn{{background:#fdecea;border-left:4px solid #b23a34;padding:12px 14px;border-radius:6px;margin:14px 0}}
.note{{background:#fbf6e6;border-left:4px solid #b58a3c;padding:12px 14px;border-radius:6px;margin:14px 0}}
.legend{{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin:10px 0}}
.legend i{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px}}
table{{border-collapse:collapse;width:100%;font-size:12px;background:#fff}}
th,td{{border:1px solid #c9d2ca;padding:5px 6px;vertical-align:top}}
thead th{{background:#e8efe9;text-align:left;position:sticky;top:0}}
.rowno{{background:#eef2ee;width:34px;text-align:center}}
.rail{{width:52px;text-align:center;font-weight:700;font-size:11px}}
.rail-pwr{{background:#fde2e1;color:#8c2b26}}
.rail-gnd{{background:#e7e7e7;color:#333}}
.net{{width:44%}}
.net ul{{margin:4px 0 0 16px;padding:0}}
.net li{{font-size:11.5px;line-height:1.45}}
.net-pwr{{background:#fde2e1}}
.net-gnd{{background:#e9e9e9}}
.net-busA{{background:#dcecff}}
.net-busB{{background:#ffe8d1}}
.net-cs{{background:#ecd9f5}}
.net-miso{{background:#f9d9ea}}
.net-nc{{background:#f2f2f2;color:#777}}
.net-spare{{background:#fafafa;color:#aaa}}
table.pins{{margin-top:8px}}
table.pins td:first-child{{text-align:center;font-weight:700;width:40px}}
.split{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
@media(max-width:820px){{.split{{grid-template-columns:1fr}}}}
@media print{{body{{background:#fff}}main{{padding:0}}h1{{font-size:18px}}thead th{{position:static}}}}
</style></head><body><main>
<h1>EVT-A 双 SPI · 2 源面包板逐行接线图</h1>
<p>sid0（腕部 / 总线 B，CS=GPIO1）＋ sid1（拇近 / 总线 A，CS=GPIO2）。
标准面包板：上排 a–e、下排 f–j 各 5×30；左右各两组纵向 25 孔电源轨
（本图左外/右外=3V3，左内/右内=GND）。</p>
<div class="warn"><b>三个关键点：</b>
① GY 模块是 6 针，<b>不能</b>插进 5 孔行，必须外置用 6 根跳线；
② 74HC125N 跨中缝插，pin1 在上 2 的 e 列、pin14 在下 2 的 f 列，
上 2 与下 2 是不同网络；
③ 每一横排 5 孔同网络，相邻行绝缘。</div>
<div class="legend">
<span><i style="background:#fde2e1"></i>3V3</span>
<span><i style="background:#e9e9e9"></i>GND</span>
<span><i style="background:#dcecff"></i>总线 A（sid1）</span>
<span><i style="background:#ffe8d1"></i>总线 B（sid0）</span>
<span><i style="background:#ecd9f5"></i>CS / OE</span>
<span><i style="background:#f9d9ea"></i>原始 MISO</span>
<span><i style="background:#f2f2f2"></i>未用</span>
</div>
<table>
<thead><tr><th>行</th><th>左外<br>3V3</th><th>左内<br>GND</th>
<th>上排 a–e（5 孔同网络）</th><th>下排 f–j（5 孔同网络）</th>
<th>右内<br>GND</th><th>右外<br>3V3</th></tr></thead>
<tbody>{''.join(body)}</tbody></table>
<div class="note"><b>电源轨：</b>左外↔右外、左内↔右内各用一根跳线连起来；
DevKit 的 3V3/GND 各接一次即可。上电前用万用表确认 3V3–GND 不短路。</div>
<h2>U1 = SN74HC125N 引脚表</h2>
{pin_table()}
<div class="split">
<div><h2>sid0 腕部 / 总线 B（CS=GPIO1）</h2>
<table><thead><tr><th>模块引脚</th><th>接到</th></tr></thead><tbody>
<tr><td>VCC</td><td>3V3 轨</td></tr>
<tr><td>GND</td><td>GND 轨</td></tr>
<tr><td>SCL / SPC</td><td>下 9（B_SCLK）</td></tr>
<tr><td>MOSI / SDA / SDI</td><td>下 10（B_MOSI）</td></tr>
<tr><td>MISO / SDO</td><td>上 3（U1 pin2 / 1A）</td></tr>
<tr><td>CS</td><td>上 2（U1 pin1 / 1OE）</td></tr>
</tbody></table></div>
<div><h2>sid1 拇近 / 总线 A（CS=GPIO2）</h2>
<table><thead><tr><th>模块引脚</th><th>接到</th></tr></thead><tbody>
<tr><td>VCC</td><td>3V3 轨</td></tr>
<tr><td>GND</td><td>GND 轨</td></tr>
<tr><td>SCL / SPC</td><td>上 9（A_SCLK）</td></tr>
<tr><td>MOSI / SDA / SDI</td><td>上 10（A_MOSI）</td></tr>
<tr><td>MISO / SDO</td><td>上 6（U1 pin5 / 2A）</td></tr>
<tr><td>CS</td><td>上 5（U1 pin4 / 2OE）</td></tr>
</tbody></table></div>
</div>
<h2>DevKitC-1 → 面包板</h2>
<table><thead><tr><th>信号</th><th>GPIO</th><th>接到</th></tr></thead><tbody>
<tr><td>3V3</td><td>3V3</td><td>3V3 轨</td></tr>
<tr><td>GND</td><td>GND</td><td>GND 轨</td></tr>
<tr><td>CS0 / sid0</td><td>GPIO1</td><td>上 2</td></tr>
<tr><td>CS1 / sid1</td><td>GPIO2</td><td>上 5</td></tr>
<tr><td>A_SCLK</td><td>GPIO12</td><td>上 9</td></tr>
<tr><td>A_MOSI</td><td>GPIO11</td><td>上 10</td></tr>
<tr><td>A_MISO</td><td>GPIO13</td><td>上 7</td></tr>
<tr><td>B_SCLK</td><td>GPIO18</td><td>下 9</td></tr>
<tr><td>B_MOSI</td><td>GPIO21</td><td>下 10</td></tr>
<tr><td>B_MISO</td><td>GPIO47</td><td>上 4</td></tr>
</tbody></table>
<div class="note"><b>电阻/电容：</b>RCS0 10k 上 2↔3V3；RCS1 10k 上 5↔3V3；
CU1 100nF 下 2↔下 1；CB1 4.7–10µF 跨 3V3/GND 轨；每颗模块 VCC–GND
尽量近处加 100nF。10k 上拉不能省。</div>
<div class="warn"><b>顺序：</b>先电源→U1 电源/未用脚→只接 sid0 跑
<code>--expect 1</code>→再加 sid1 跑 <code>--expect 2</code>。失败就停，
不跳 6/11，不降频、不串电阻掩盖。</div>
</main></body></html>
"""
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
