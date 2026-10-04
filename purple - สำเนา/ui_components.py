"""
ส่วนประกอบหน้าตา (UI) ที่เป็น Python ล้วน ไม่พึ่ง streamlit เพื่อให้ app.py อ่านง่ายและทดสอบแยกได้
- fmt_duration            : แปลงวินาที -> ข้อความไทย
- build_heatmap_html      : ตาราง GitHub-style Habit Tracker
- build_focus_widget_html : วิดเจ็ตจับเวลาโฟกัส พร้อมเอฟเฟกต์ดอกไม้/แมวร่วงลงมา
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta

THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
ROW_LABELS = {1: "จ", 3: "พ", 5: "ศ"}  # แถวของตาราง: 0=อาทิตย์, 1=จันทร์, ... 6=เสาร์


# ------------------------------------------------------------------
# ข้อความเวลา
# ------------------------------------------------------------------
def fmt_duration(sec: float, with_seconds: bool = False) -> str:
    sec = max(0, int(round(sec)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if with_seconds:
        if h:
            return f"{h} ชม. {m} นาที {s:02d} วินาที"
        if m:
            return f"{m} นาที {s:02d} วินาที"
        return f"{s} วินาที"
    if h:
        return f"{h} ชม. {m} นาที"
    if m == 0 and 0 < s < 60:
        return f"{s} วินาที"
    return f"{m} นาที"


# ------------------------------------------------------------------
# GitHub-style Habit Tracker (heatmap)
# ------------------------------------------------------------------
HEATMAP_CSS = """
.hm-wrap{display:flex;gap:6px;align-items:flex-start;margin:4px 0 6px 0;overflow-x:auto;padding-bottom:4px;}
.hm-days{display:grid;grid-template-rows:repeat(7,12px);gap:3px;margin-top:17px;font-size:10px;color:#9ca3af;}
.hm-days div{height:12px;line-height:12px;}
.hm-main{display:flex;flex-direction:column;gap:3px;}
.hm-months{display:grid;grid-auto-flow:column;grid-auto-columns:12px;gap:3px;height:14px;font-size:10px;color:#9ca3af;}
.hm-month{white-space:nowrap;line-height:14px;}
.hm-grid{display:grid;grid-template-rows:repeat(7,12px);grid-auto-flow:column;grid-auto-columns:12px;gap:3px;}
.hm-cell{width:12px;height:12px;border-radius:3px;background:rgba(148,163,184,.22);}
.hm-l1{background:#fbcfe8;}
.hm-l2{background:#f9a8d4;}
.hm-l3{background:#ec4899;}
.hm-l4{background:#be185d;}
.hm-future{background:transparent;}
.hm-legend{font-size:11px;color:#9ca3af;margin:0 0 14px 0;}
.hm-legend .hm-cell{display:inline-block;vertical-align:middle;margin:0 1px;}
"""


def heatmap_range(today: date, weeks: int = 26) -> tuple[date, date]:
    """ช่วงวันที่ของตาราง: เริ่มต้นวันอาทิตย์ของสัปดาห์แรก จบที่วันนี้"""
    start = today - timedelta(weeks=weeks - 1)
    start -= timedelta(days=(start.weekday() + 1) % 7)  # weekday(): จันทร์=0 ... อาทิตย์=6
    return start, today


def levels_for_habit(checked_dates: set[str]) -> dict[str, int]:
    """habit เดี่ยว: ติ๊กแล้ว = เข้มสุด"""
    return {d: 3 for d in checked_dates}


def levels_for_all(habit_checks: dict[int, set[str]], habit_ids: list[int]) -> dict[str, int]:
    """ภาพรวมทุก habit: ยิ่งติ๊กครบหลายอันในวันนั้น สียิ่งเข้ม"""
    total = len(habit_ids)
    if total == 0:
        return {}
    counts: Counter = Counter()
    for hid in habit_ids:
        for d in habit_checks.get(hid, set()):
            counts[d] += 1
    levels = {}
    for d, n in counts.items():
        ratio = n / total
        levels[d] = 1 if ratio <= 0.25 else 2 if ratio <= 0.5 else 3 if ratio <= 0.75 else 4
    return levels


def build_heatmap_html(levels: dict[str, int], today: date, weeks: int = 26) -> str:
    start, end = heatmap_range(today, weeks)
    n_cols = (end - start).days // 7 + 1

    # ป้ายชื่อเดือนเหนือตาราง (เว้นห่างอย่างน้อย 3 คอลัมน์ไม่ให้ตัวหนังสือชนกัน)
    month_cells, last_idx = [], -10
    for w in range(n_cols):
        d0 = start + timedelta(weeks=w)
        if w == 0:
            nxt = [(start + timedelta(weeks=k)).month for k in (1, 2)]
            show = all(m == d0.month for m in nxt)
        else:
            show = d0.month != (start + timedelta(weeks=w - 1)).month and (w - last_idx) >= 3
        if show:
            last_idx = w
            month_cells.append(f'<div class="hm-month">{THAI_MONTHS[d0.month - 1]}</div>')
        else:
            month_cells.append("<div></div>")

    cells = []
    for w in range(n_cols):
        for dow in range(7):
            d = start + timedelta(days=w * 7 + dow)
            if d > end:
                cells.append('<div class="hm-cell hm-future"></div>')
                continue
            lv = levels.get(d.isoformat(), 0)
            tip = f"{d.day} {THAI_MONTHS[d.month - 1]} {d.year}" + (" · ทำแล้ว" if lv else "")
            cells.append(f'<div class="hm-cell hm-l{lv}" title="{tip}"></div>')

    day_labels = "".join(f"<div>{ROW_LABELS.get(i, '')}</div>" for i in range(7))
    return (
        '<div class="hm-wrap">'
        f'<div class="hm-days">{day_labels}</div>'
        '<div class="hm-main">'
        f'<div class="hm-months">{"".join(month_cells)}</div>'
        f'<div class="hm-grid">{"".join(cells)}</div>'
        "</div></div>"
    )


HEATMAP_LEGEND_HTML = (
    '<div class="hm-legend">น้อย '
    '<span class="hm-cell"></span><span class="hm-cell hm-l1"></span><span class="hm-cell hm-l2"></span>'
    '<span class="hm-cell hm-l3"></span><span class="hm-cell hm-l4"></span> มาก</div>'
)


# ------------------------------------------------------------------
# Focus Timer widget (HTML + JS ทำงานฝั่งเบราว์เซอร์ ไม่ต้องรีรัน Streamlit ทุกวินาที)
# ------------------------------------------------------------------
_FOCUS_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html,body{margin:0;padding:0;font-family:'Segoe UI',Tahoma,'Noto Sans Thai',sans-serif;background:transparent;}
  .box{position:relative;overflow:hidden;height:236px;border-radius:18px;border:2px solid #fbcfe8;
       background:linear-gradient(135deg,#fff5f8 0%,#f3e8ff 100%);text-align:center;box-sizing:border-box;}
  .cat{font-size:60px;margin-top:16px;display:inline-block;animation:bob 1.6s ease-in-out infinite;position:relative;z-index:2;}
  .timer{font-size:46px;font-weight:700;color:#be185d;letter-spacing:2px;margin-top:4px;position:relative;z-index:2;}
  .msg{font-size:15px;color:#7c3aed;margin-top:8px;min-height:22px;position:relative;z-index:2;padding:0 10px;}
  .petal{position:absolute;top:-34px;user-select:none;pointer-events:none;animation:fall linear forwards;z-index:1;}
  @keyframes bob{0%,100%{transform:translateY(0) rotate(-4deg)}50%{transform:translateY(-9px) rotate(4deg)}}
  @keyframes fall{to{transform:translateY(300px) rotate(360deg);opacity:.25}}
</style></head>
<body>
<div class="box" id="box">
  <div class="cat" id="cat">🐱</div>
  <div class="timer" id="timer">00:00</div>
  <div class="msg" id="msg"></div>
</div>
<script>
(function(){
  var MODE = "__MODE__";
  var START_MS = __START_MS__;      // เวลาเริ่มโฟกัส (epoch มิลลิวินาที) จากเซิร์ฟเวอร์ ถ้ารันในเครื่องตัวเองนาฬิกาตรงกันอยู่แล้ว
  var DONE_TEXT = __DONE_TEXT__;
  var box = document.getElementById('box');
  var timerEl = document.getElementById('timer');
  var msgEl = document.getElementById('msg');
  var catEl = document.getElementById('cat');
  var PETALS = ['🌸','🌷','🌼','🌺','💮','🐱','😺','🐾'];

  function spawn(){
    var p = document.createElement('span');
    p.className = 'petal';
    p.textContent = PETALS[Math.floor(Math.random()*PETALS.length)];
    p.style.left = (Math.random()*92) + '%';
    p.style.fontSize = (16 + Math.random()*16) + 'px';
    p.style.animationDuration = (4 + Math.random()*3) + 's';
    box.appendChild(p);
    setTimeout(function(){ p.remove(); }, 7500);
  }
  function pad(n){ return String(n).padStart(2,'0'); }
  function fmt(sec){
    var h = Math.floor(sec/3600), m = Math.floor((sec%3600)/60), s = sec%60;
    return (h > 0 ? h + ':' + pad(m) : pad(m)) + ':' + pad(s);
  }

  if (MODE === 'running'){
    var msgs = ['โฟกัสอยู่นะ สู้ๆ! 🌸','น้องแมวนั่งเฝ้าให้อยู่ 🐱','อีกนิดเดียว เก่งมากเลย 🌷','ดื่มน้ำสักอึกนะ 💧','ทำได้อยู่แล้ว! ✨'];
    var i = 0;
    catEl.textContent = '🐱📖';
    msgEl.textContent = msgs[0];
    var tick = function(){
      var sec = Math.max(0, Math.floor((Date.now() - START_MS)/1000));
      timerEl.textContent = fmt(sec);
    };
    tick();
    setInterval(tick, 250);
    setInterval(spawn, 900);
    setInterval(function(){ i = (i+1) % msgs.length; msgEl.textContent = msgs[i]; }, 15000);
  } else if (MODE === 'done'){
    catEl.textContent = '😻';
    timerEl.textContent = 'เก่งมาก!';
    msgEl.textContent = DONE_TEXT;
    for (var k = 0; k < 26; k++){ setTimeout(spawn, k*120); }
  } else {
    catEl.textContent = '😺💤';
    timerEl.textContent = '00:00';
    msgEl.textContent = 'พร้อมเมื่อไหร่ก็กดเริ่มโฟกัสได้เลย 🌷';
    setInterval(spawn, 2500);
  }
})();
</script>
</body></html>"""

FOCUS_WIDGET_HEIGHT = 240


def build_focus_widget_html(mode: str, start_ts: float | None = None, done_text: str = "") -> str:
    """mode: 'idle' (ยังไม่เริ่ม) | 'running' (กำลังจับเวลา) | 'done' (เพิ่งหยุด แสดงฉลอง)"""
    start_ms = int((start_ts or 0) * 1000)
    return (
        _FOCUS_TEMPLATE
        .replace("__MODE__", mode)
        .replace("__START_MS__", str(start_ms))
        .replace("__DONE_TEXT__", json.dumps(done_text, ensure_ascii=False))
    )