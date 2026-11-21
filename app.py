# ==============================================================================
# DIGICRAFT MATRIX PALACE - PART 1 OF 5
# Auth & Admin Control Room, 7-Day Auto-Gallery, DMC Swatches, PNG & 3D STL Core
# ==============================================================================
import os
import time
import math
import json
import struct
import base64
import random
import smtplib
from email.message import EmailMessage
import re
import gradio as gr
import PIL.Image
import PIL.ImageDraw
import PIL.ImageOps
import PIL.ImageFilter
import PIL.ImageEnhance
import numpy as np
from skimage import measure
from skimage.filters import gaussian

try:
    import google.generativeai as genai
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
except Exception:
    genai = None

# ==========================================
# 1. מערכת משתמשים, אנליטיקס, שחזור סיסמה וארכיון 7 ימים
# ==========================================
DATA_DIR = "studio_data"
HISTORY_DIR = os.path.join(DATA_DIR, "history")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
HISTORY_META = os.path.join(DATA_DIR, "history_meta.json")
RETENTION_SECONDS = 7 * 24 * 3600  # 7 ימים

os.makedirs(HISTORY_DIR, exist_ok=True)


def init_databases():
    if not os.path.exists(USERS_FILE):
        default_users = {
            "mai": {
                "username": "mai",
                "password": "DigiCraft2026",
                "email": "mai@digicraft.studio",
                "role": "admin",
                "created_at": time.strftime("%d/%m/%Y %H:%M"),
                "creations_count": 0,
                "last_login": time.strftime("%d/%m/%Y %H:%M")
            }
        }
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_users, f, ensure_ascii=False, indent=2)

    if not os.path.exists(STATS_FILE):
        default_stats = {
            "total_visits": 1,
            "total_logins": 1,
            "total_generations": 0,
            "room_usage": {},
            "recent_events": [
                {"time": time.strftime("%d/%m/%Y %H:%M"), "event": "אתחול ארמון DigiCraft Palace"}
            ],
            "reset_codes": {}
        }
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_stats, f, ensure_ascii=False, indent=2)


init_databases()


def load_json(path, default_val):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_val


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_event(event_text):
    stats = load_json(STATS_FILE, {"total_visits": 1, "total_logins": 1, "total_generations": 0, "room_usage": {}, "recent_events": [], "reset_codes": {}})
    stats["recent_events"].insert(0, {"time": time.strftime("%d/%m/%Y %H:%M:%S"), "event": event_text})
    stats["recent_events"] = stats["recent_events"][:50]
    save_json(STATS_FILE, stats)


def record_visit():
    stats = load_json(STATS_FILE, {"total_visits": 0, "total_logins": 0, "total_generations": 0, "room_usage": {}, "recent_events": [], "reset_codes": {}})
    stats["total_visits"] = stats.get("total_visits", 0) + 1
    save_json(STATS_FILE, stats)


def handle_login(username, password):
    u = (username or "").strip().lower()
    p = (password or "").strip()
    users = load_json(USERS_FILE, {})
    if u in users and users[u]["password"] == p:
        users[u]["last_login"] = time.strftime("%d/%m/%Y %H:%M")
        save_json(USERS_FILE, users)
        stats = load_json(STATS_FILE, {})
        stats["total_logins"] = stats.get("total_logins", 0) + 1
        save_json(STATS_FILE, stats)
        log_event(f"התחברות משתמש: {u}")
        role_label = "מנהלת מערכת (Admin)" if users[u].get("role") == "admin" else "משתמש רשום"
        badge = f"🟢 מחובר/ת: {u} ({role_label}) — שמירה אוטומטית בגלריה פעילה"
        return u, badge, f"<div class='telemetry-box' style='color:#4caf50;'>התחברת בהצלחה בתור <b>{u}</b>!</div>"
    return "guest", "👤 מצב אורח (ללא שמירה בגלריה)", "<div class='telemetry-box' style='color:#ff5252;'>שם משתמש או סיסמה שגויים.</div>"


def handle_register(username, email, password):
    u = (username or "").strip().lower()
    e = (email or "").strip().lower()
    p = (password or "").strip()
    if len(u) < 2 or len(p) < 4 or "@" not in e:
        return "guest", "👤 מצב אורח", "<div class='telemetry-box' style='color:#ff5252;'>נא להזין שם משתמש (לפחות 2 תווים), דוא\"ל תקין וסיסמה (לפחות 4 תווים).</div>"
    users = load_json(USERS_FILE, {})
    if u in users:
        return "guest", "👤 מצב אורח", "<div class='telemetry-box' style='color:#ff5252;'>שם המשתמש כבר קיים במערכת.</div>"
    users[u] = {
        "username": u,
        "password": p,
        "email": e,
        "role": "user",
        "created_at": time.strftime("%d/%m/%Y %H:%M"),
        "creations_count": 0,
        "last_login": time.strftime("%d/%m/%Y %H:%M")
    }
    save_json(USERS_FILE, users)
    log_event(f"הרשמת משתמש חדש: {u} ({e})")
    badge = f"🟢 מחובר/ת: {u} (משתמש רשום) — שמירה אוטומטית בגלריה פעילה"
    return u, badge, f"<div class='telemetry-box' style='color:#4caf50;'>נרשמת והתחברת בהצלחה בתור <b>{u}</b>! כל יצירה שלך תישמר בגלריה ל-7 ימים.</div>"


def handle_guest_mode():
    return "guest", "👤 מצב אורח (ללא שמירה בגלריה)", "<div class='telemetry-box'>עברת למצב אורח. קבצים ניתנים להורדה ישירה אך לא יישמרו בגלריה.</div>"


def send_recovery_email(email_addr):
    e = (email_addr or "").strip().lower()
    users = load_json(USERS_FILE, {})
    found_user = None
    for uname, udata in users.items():
        if udata.get("email", "").lower() == e:
            found_user = uname
            break
    if not found_user:
        return "<div class='telemetry-box' style='color:#ff5252;'>לא נמצא משתמש הרשום תחת כתובת הדוא\"ל הזו.</div>"

    code = str(random.randint(100000, 999999))
    stats = load_json(STATS_FILE, {})
    if "reset_codes" not in stats:
        stats["reset_codes"] = {}
    stats["reset_codes"][e] = {"code": code, "user": found_user, "time": time.time()}
    save_json(STATS_FILE, stats)
    log_event(f"בקשת שחזור סיסמה עבור: {found_user} ({e})")

    smtp_user = os.environ.get("SMTP_EMAIL")
    smtp_pass = os.environ.get("SMTP_PASSWORD")
    if smtp_user and smtp_pass:
        try:
            msg = EmailMessage()
            msg["Subject"] = "DigiCraft Matrix - קוד שחזור סיסמה"
            msg["From"] = smtp_user
            msg["To"] = e
            msg.set_content(f"שלום {found_user},\nקוד השחזור שלך ל-DigiCraft Matrix הוא: {code}\nהזיני אותו בלשונית שחזור הסיסמה באתר.")
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            return f"<div class='telemetry-box' style='color:#4caf50;'>קוד שחזור נשלח בהצלחה אל <b>{e}</b>! הזיני אותו למטה לבחירת סיסמה חדשה.</div>"
        except Exception as ex:
            return f"<div class='telemetry-box' style='color:#ffb74d;'>הופק קוד שחזור עבור <b>{found_user}</b>. (הערת שרת דוא\"ל: {str(ex)} | קוד שחזור מיידי: <b>{code}</b>)</div>"
    else:
        return f"<div class='telemetry-box' style='color:#4caf50;'>קוד שחזור הופק עבור <b>{found_user}</b> ({e}): קוד האימות שלך הוא <b>{code}</b> (הזיני אותו בשדה למטה כדי לעדכן סיסמה).</div>"


def reset_password_with_code(email_addr, code_input, new_pass):
    e = (email_addr or "").strip().lower()
    c = (code_input or "").strip()
    np_str = (new_pass or "").strip()
    if len(np_str) < 4:
        return "<div class='telemetry-box' style='color:#ff5252;'>הסיסמה החדשה חייבת להכיל לפחות 4 תווים.</div>"
    stats = load_json(STATS_FILE, {})
    rec = stats.get("reset_codes", {}).get(e)
    if not rec or rec.get("code") != c:
        return "<div class='telemetry-box' style='color:#ff5252;'>קוד האימות שגוי או שפג תוקפו.</div>"

    uname = rec["user"]
    users = load_json(USERS_FILE, {})
    if uname in users:
        users[uname]["password"] = np_str
        save_json(USERS_FILE, users)
        del stats["reset_codes"][e]
        save_json(STATS_FILE, stats)
        log_event(f"סיסמה אופסה בהצלחה עבור: {uname}")
        return f"<div class='telemetry-box' style='color:#4caf50;'>הסיסמה עבור <b>{uname}</b> עודכנה בהצלחה! כעת ניתן להתחבר.</div>"
    return "<div class='telemetry-box' style='color:#ff5252;'>שגיאה באיתור המשתמש.</div>"


def get_admin_dashboard(current_user):
    users = load_json(USERS_FILE, {})
    u_info = users.get(str(current_user).lower(), {})
    if u_info.get("role") != "admin":
        return "<div class='telemetry-box' style='color:#ff5252;'>🔒 גישה לחדר הבקרה מורשית למנהלת המערכת בלבד (התחברי עם המשתמש <b>mai</b>).</div>"

    stats = load_json(STATS_FILE, {})
    items = clean_and_load_history()

    html = [
        "<div class='telemetry-box'>",
        "<h3 style='color:#e86c52; margin-top:0;'>🛡️ חדר בקרה למנהלת (Admin Control Room)</h3>",
        "<div style='display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:16px;'>",
        f"<div class='swatch-card'><div><div class='swatch-hex'>{stats.get('total_visits', 1)}</div><div class='swatch-meta'>סה\"כ כניסות לאתר</div></div></div>",
        f"<div class='swatch-card'><div><div class='swatch-hex'>{len(users)}</div><div class='swatch-meta'>משתמשים רשומים</div></div></div>",
        f"<div class='swatch-card'><div><div class='swatch-hex'>{stats.get('total_generations', 0)}</div><div class='swatch-meta'>סה\"כ יצירות שג'ונרטו</div></div></div>",
        f"<div class='swatch-card'><div><div class='swatch-hex'>{len(items)}</div><div class='swatch-meta'>קבצים פעילים בארכיון</div></div></div>",
        "</div>",
        "<h4>👥 רשימת משתמשים רשומים</h4>",
        "<table style='width:100%; border-collapse:collapse; font-size:12px; margin-bottom:16px;'>",
        "<tr style='border-bottom:1px solid #444; color:#d4a359; text-align:right;'><th>שם משתמש</th><th>דוא\"ל</th><th>הרשאה</th><th>תאריך הצטרפות</th><th>כניסה אחרונה</th><th>יצירות</th></tr>"
    ]
    for uname, ud in users.items():
        html.append(f"<tr style='border-bottom:1px solid #26262e;'><td><b>{uname}</b></td><td>{ud.get('email','')}</td><td>{ud.get('role','user')}</td><td>{ud.get('created_at','')}</td><td>{ud.get('last_login','')}</td><td>{ud.get('creations_count',0)}</td></tr>")
    html.append("</table>")

    html.append("<h4>📊 פילוח שימוש לפי חדרים</h4><ul>")
    for rname, rcount in stats.get("room_usage", {}).items():
        html.append(f"<li><b>{rname}:</b> {rcount} יצירות</li>")
    html.append("</ul>")

    html.append("<h4>🕒 יומן אירועים אחרונים באתר</h4><ul>")
    for ev in stats.get("recent_events", [])[:15]:
        html.append(f"<li><span style='color:#888;'>[{ev.get('time','')}]</span> {ev.get('event','')}</li>")
    html.append("</ul></div>")
    return "".join(html)


def clean_and_load_history():
    items = load_json(HISTORY_META, [])
    now = time.time()
    valid_items = []
    for item in items:
        if now - item.get("timestamp", 0) <= RETENTION_SECONDS:
            valid_items.append(item)
        else:
            for key in ["svg_path", "png_path", "stl_path"]:
                p = item.get(key)
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
    save_json(HISTORY_META, valid_items)
    return valid_items


def save_to_history(current_user, room_name, svg_path=None, png_path=None, stl_path=None):
    u = str(current_user or "mai").strip().lower()
    stats = load_json(STATS_FILE, {})
    stats["total_generations"] = stats.get("total_generations", 0) + 1
    ru = stats.get("room_usage", {})
    ru[room_name] = ru.get(room_name, 0) + 1
    stats["room_usage"] = ru
    save_json(STATS_FILE, stats)

    if u == "guest" or "אורח" in u:
        return

    users = load_json(USERS_FILE, {})
    if u in users:
        users[u]["creations_count"] = users[u].get("creations_count", 0) + 1
        save_json(USERS_FILE, users)

    items = clean_and_load_history()
    ts = int(time.time())
    time_str = time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(ts))

    entry = {
        "id": f"job_{ts}_{len(items)}",
        "user": u,
        "timestamp": ts,
        "date": time_str,
        "room": room_name,
        "svg_path": svg_path,
        "png_path": png_path,
        "stl_path": stl_path
    }
    items.insert(0, entry)
    save_json(HISTORY_META, items[:100])


def get_history_display(current_user="mai"):
    u = str(current_user or "mai").strip().lower()
    if u == "guest":
        return [], [], "<div class='telemetry-box' style='color:#ffb74d;'>את/ה במצב אורח. התחבר/י עם שם משתמש וסיסמה כדי שכל יצירה תישמר אוטומטית בגלריה ל-7 ימים.</div>"

    items = clean_and_load_history()
    users = load_json(USERS_FILE, {})
    is_admin = users.get(u, {}).get("role") == "admin"

    gallery_imgs = []
    files_list = []
    user_items = [it for it in items if is_admin or it.get("user") == u]

    if not user_items:
        return [], [], f"<div class='telemetry-box'>הגלריה של <b>{u}</b> ריקה כרגע. כל תוצר שתייצרי בחדרים יופיע כאן אוטומטית ללא צורך להוריד למחשב!</div>"

    rows_html = [f"<div class='telemetry-box'><h4>🗂️ ארכיון יצירות אוטומטי ({len(user_items)} פריטים פעילים ל-7 ימים)</h4><ul>"]
    for item in user_items:
        png_p = item.get("png_path")
        svg_p = item.get("svg_path")
        stl_p = item.get("stl_path")
        owner = item.get("user", "mai")
        caption = f"{item['room']} | {item['date']} ({owner})"
        if png_p and os.path.exists(png_p):
            gallery_imgs.append((png_p, caption))
            files_list.append(png_p)
        if svg_p and os.path.exists(svg_p):
            files_list.append(svg_p)
        if stl_p and os.path.exists(stl_p):
            files_list.append(stl_p)
        rows_html.append(f"<li><b>{item['date']}</b> — {item['room']} (משתמש: {owner})</li>")
    rows_html.append("</ul></div>")
    return gallery_imgs, files_list, "".join(rows_html)


# ==========================================
# 2. מאגר חוטי DMC, ניקוי תמונות ודוגמיות צבע (Swatches)
# ==========================================
DMC_PALETTE = [
    ("DMC-310", "Black", (0, 0, 0)),
    ("DMC-Ecru", "Ecru / Off-White", (240, 234, 218)),
    ("DMC-Blanc", "Pure White", (255, 255, 255)),
    ("DMC-817", "Coral Red Very Dark", (187, 5, 31)),
    ("DMC-666", "Bright Red", (227, 29, 66)),
    ("DMC-351", "Coral", (233, 106, 103)),
    ("DMC-741", "Tangerine Medium", (255, 163, 43)),
    ("DMC-444", "Lemon Dark", (255, 214, 0)),
    ("DMC-700", "Christmas Green", (7, 115, 27)),
    ("DMC-991", "Aquamarine Dark", (19, 117, 102)),
    ("DMC-3846", "Turquoise Bright", (6, 195, 218)),
    ("DMC-798", "Delft Blue Dark", (70, 106, 142)),
    ("DMC-820", "Royal Blue Very Dark", (14, 54, 92)),
    ("DMC-550", "Violet Very Dark", (92, 24, 78)),
    ("DMC-718", "Plum", (156, 36, 98)),
    ("DMC-434", "Brown Light", (152, 94, 51)),
    ("DMC-840", "Beige Brown Medium", (154, 124, 92)),
    ("DMC-414", "Steel Grey Dark", (140, 140, 140)),
    ("DMC-318", "Steel Grey Light", (171, 171, 171)),
    ("DMC-648", "Beaver Grey Light", (188, 180, 172)),
]


def find_closest_dmc(r, g, b):
    best_code, best_name, min_dist = "DMC-310", "Black", float("inf")
    for code, name, (dr, dg, db) in DMC_PALETTE:
        dist = (r - dr) ** 2 + (g - dg) ** 2 + (b - db) ** 2
        if dist < min_dist:
            min_dist = dist
            best_code, best_name = code, name
    return best_code, best_name


def ensure_clean_rgb(image_path):
    if not image_path:
        raise ValueError("לא נבחרה תמונה. אנא העלי קובץ תמונה.")
    img = PIL.Image.open(image_path)
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        alpha = img.convert('RGBA').split()[-1]
        bg = PIL.Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img.convert('RGB'), mask=alpha)
        return bg
    return img.convert('RGB')


def rgb_to_hex(r, g, b):
    return '#{:02x}{:02x}{:02x}'.format(int(max(0, min(255, r))), int(max(0, min(255, g))), int(max(0, min(255, b))))


def adjust_color(r, g, b, factor):
    return rgb_to_hex(r * factor, g * factor, b * factor)


def get_luminance(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def build_color_swatches_html(color_counts, total_pixels):
    html = [
        "<div class='swatch-panel'>",
        "<div class='swatch-title'>פלטת גוונים פעילה ומיפוי חוטי DMC (LIVE FEED)</div>",
        "<div class='swatch-grid'>"
    ]
    for (r, g, b), count in color_counts:
        hex_c = rgb_to_hex(r, g, b)
        dmc_code, dmc_name = find_closest_dmc(r, g, b)
        pct = (count / max(1, total_pixels)) * 100
        lum = int((get_luminance(r, g, b) / 255.0) * 100)
        html.append(f"""
        <div class='swatch-card'>
            <div class='swatch-box' style='background:{hex_c};'></div>
            <div class='swatch-info'>
                <span class='swatch-hex'>{hex_c.upper()}</span>
                <span class='swatch-dmc'>{dmc_code} ({dmc_name})</span>
                <span class='swatch-meta'>כיסוי: {pct:.1f}% | בהירות: {lum}%</span>
            </div>
        </div>
        """)
    html.append("</div></div>")
    return "".join(html)


def wrap_pil_as_svg(pil_img, footer_label="DIGICRAFT_PALACE"):
    """עוטף תמונת רסטר מפורטת בתוך קובץ SVG תקני עם מסגרת טכנית לצורך ייצוא כפול ותצוגה"""
    import io
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    w, h = pil_img.size
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h + 24}" width="100%" height="100%">
        <rect x="0" y="0" width="{w}" height="{h + 24}" fill="#141417"/>
        <image x="0" y="0" width="{w}" height="{h}" href="data:image/png;base64,{b64}"/>
        <text x="{w/2}" y="{h + 16}" fill="#888888" font-family="monospace" font-size="11" text-anchor="middle">{footer_label}</text>
    </svg>'''
    return svg


# ==========================================
# 3. מנוע המרת SVG ל-PNG ומנוע 3D STL עם חישוב תאורה וחיתוך סילואט ללא משטח ריבועי!
# ==========================================
def parse_svg_path_points(d_str, ox, oy, scale):
    tokens = re.findall(r'[MLQZmlqz]|-?\d+(?:\.\d+)?', d_str)
    subpaths = []
    curr = []
    i = 0
    cmd = 'M'
    while i < len(tokens):
        t = tokens[i]
        if t.isalpha():
            cmd = t.upper()
            i += 1
            if cmd == 'Z':
                if curr:
                    curr.append(curr[0])
                    subpaths.append(curr)
                    curr = []
            continue
        try:
            if cmd in ('M', 'L'):
                x = (float(tokens[i]) - ox) * scale
                y = (float(tokens[i + 1]) - oy) * scale
                if cmd == 'M' and curr:
                    subpaths.append(curr)
                    curr = []
                curr.append((x, y))
                i += 2
                cmd = 'L'
            elif cmd == 'Q':
                x1 = (float(tokens[i]) - ox) * scale
                y1 = (float(tokens[i + 1]) - oy) * scale
                x2 = (float(tokens[i + 2]) - ox) * scale
                y2 = (float(tokens[i + 3]) - oy) * scale
                x0, y0 = curr[-1] if curr else (x1, y1)
                for step in range(1, 9):
                    st = step / 8.0
                    qx = (1 - st) ** 2 * x0 + 2 * (1 - st) * st * x1 + st ** 2 * x2
                    qy = (1 - st) ** 2 * y0 + 2 * (1 - st) * st * y1 + st ** 2 * y2
                    curr.append((qx, qy))
                i += 4
            else:
                i += 1
        except Exception:
            break
    if curr:
        subpaths.append(curr)
    return subpaths


def render_svg_to_png(svg_code, output_png_path, target_max_dim=1400):
    vb_match = re.search(r'viewBox="([^"]+)"', svg_code)
    if vb_match:
        parts = [float(x) for x in vb_match.group(1).replace(',', ' ').split()]
        ox, oy, vw, vh = parts[0], parts[1], max(1.0, parts[2]), max(1.0, parts[3])
    else:
        ox, oy, vw, vh = 0.0, 0.0, 800.0, 800.0

    scale = target_max_dim / max(vw, vh)
    img_w = max(10, int(vw * scale))
    img_h = max(10, int(vh * scale))

    img = PIL.Image.new("RGB", (img_w, img_h), "#141417")
    draw = PIL.ImageDraw.Draw(img)

    class_strokes = {
        "cut": ("#ff1744", max(2, int(1.5 * scale))),
        "fold": ("#00e5ff", max(1, int(1.2 * scale))),
        "reg": ("#00ffaa", max(1, int(1.0 * scale))),
        "bleed": ("#ff0055", max(1, int(1.0 * scale))),
        "spec": ("#888888", 1)
    }

    for tag_match in re.finditer(r'<(rect|circle|line|polygon|path)\b([^>]*)/?>', svg_code):
        tag = tag_match.group(1)
        attrs = tag_match.group(2)

        def get_attr(name, default=None):
            m = re.search(rf'\b{name}="([^"]*)"', attrs)
            return m.group(1) if m else default

        fill = get_attr("fill", "none")
        stroke = get_attr("stroke", "none")
        sw = float(get_attr("stroke-width", "1") or 1)
        cls = get_attr("class", "")
        if cls in class_strokes:
            stroke, sw_px = class_strokes[cls]
        else:
            sw_px = max(1, int(sw * scale))

        fill_col = None if fill in ("none", "transparent", None) or str(fill).startswith("url(") else fill
        stroke_col = None if stroke in ("none", "transparent", None) else stroke

        try:
            if tag == "rect":
                rx = (float(get_attr("x", "0")) - ox) * scale
                ry = (float(get_attr("y", "0")) - oy) * scale
                rw = float(get_attr("width", vw)) * scale
                rh = float(get_attr("height", vh)) * scale
                draw.rectangle([rx, ry, rx + rw, ry + rh], fill=fill_col, outline=stroke_col, width=sw_px)
            elif tag == "circle":
                cx = (float(get_attr("cx", "0")) - ox) * scale
                cy = (float(get_attr("cy", "0")) - oy) * scale
                r = float(get_attr("r", "1")) * scale
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill_col, outline=stroke_col, width=sw_px)
            elif tag == "line":
                x1 = (float(get_attr("x1", "0")) - ox) * scale
                y1 = (float(get_attr("y1", "0")) - oy) * scale
                x2 = (float(get_attr("x2", "0")) - ox) * scale
                y2 = (float(get_attr("y2", "0")) - oy) * scale
                if stroke_col:
                    draw.line([x1, y1, x2, y2], fill=stroke_col, width=sw_px)
            elif tag == "polygon":
                pts_str = get_attr("points", "")
                pts = []
                for pair in pts_str.strip().split():
                    if "," in pair:
                        px, py = pair.split(",")
                        pts.append(((float(px) - ox) * scale, (float(py) - oy) * scale))
                if len(pts) >= 3:
                    draw.polygon(pts, fill=fill_col, outline=stroke_col)
            elif tag == "path":
                d_str = get_attr("d", "")
                subpaths = parse_svg_path_points(d_str, ox, oy, scale)
                for sp in subpaths:
                    if len(sp) >= 3 and fill_col:
                        draw.polygon(sp, fill=fill_col, outline=stroke_col)
                    elif len(sp) >= 2 and stroke_col:
                        draw.line(sp, fill=stroke_col, width=sw_px)
        except Exception:
            continue

    img.save(output_png_path, "PNG")
    return output_png_path


def save_dual_outputs(svg_code, base_name, current_user, room_title, custom_png_img=None, stl_path=None):
    ts = int(time.time() * 1000)
    svg_file = os.path.join(HISTORY_DIR, f"{base_name}_{ts}.svg")
    png_file = os.path.join(HISTORY_DIR, f"{base_name}_{ts}.png")

    with open(svg_file, "w", encoding="utf-8") as f:
        f.write(svg_code)

    if custom_png_img is not None:
        custom_png_img.save(png_file, "PNG")
    else:
        render_svg_to_png(svg_code, png_file)

    save_to_history(current_user, room_title, svg_path=svg_file, png_path=png_file, stl_path=stl_path)
    return svg_file, png_file


def write_binary_stl_with_normals(all_tris, stl_path):
    v1 = all_tris[:, 0, :]
    v2 = all_tris[:, 1, :]
    v3 = all_tris[:, 2, :]
    normals = np.cross(v2 - v1, v3 - v1)
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normals = normals / norms

    num_tris = all_tris.shape[0]
    stl_dtype = np.dtype([
        ('normal', '<f4', (3,)),
        ('v1', '<f4', (3,)),
        ('v2', '<f4', (3,)),
        ('v3', '<f4', (3,)),
        ('attr', '<u2')
    ])
    data = np.zeros(num_tris, dtype=stl_dtype)
    data['normal'] = normals.astype(np.float32)
    data['v1'] = v1.astype(np.float32)
    data['v2'] = v2.astype(np.float32)
    data['v3'] = v3.astype(np.float32)

    with open(stl_path, 'wb') as f:
        header = b"DIGICRAFT_PALACE_WATERTIGHT_STL".ljust(80, b' ')
        f.write(header)
        f.write(struct.pack('<I', num_tris))
        f.write(data.tobytes())
    return stl_path


def heightmap_to_watertight_stl(z_grid, stl_path, width_mm=100.0, height_mm=100.0, base_mm=1.6, relief_mm=2.8, cutout_bg=True, cutoff_thresh=0.08):
    ny, nx = z_grid.shape
    xs = np.linspace(0.0, width_mm, nx, dtype=np.float32)
    ys = np.linspace(height_mm, 0.0, ny, dtype=np.float32)
    xv, yv = np.meshgrid(xs, ys)
    zv = base_mm + (z_grid.astype(np.float32) * relief_mm)

    p00 = np.stack([xv[:-1, :-1], yv[:-1, :-1], zv[:-1, :-1]], axis=-1)
    p10 = np.stack([xv[:-1, 1:], yv[:-1, 1:], zv[:-1, 1:]], axis=-1)
    p01 = np.stack([xv[1:, :-1], yv[1:, :-1], zv[1:, :-1]], axis=-1)
    p11 = np.stack([xv[1:, 1:], yv[1:, 1:], zv[1:, 1:]], axis=-1)

    b00 = np.stack([xv[:-1, :-1], yv[:-1, :-1], np.zeros_like(zv[:-1, :-1])], axis=-1)
    b10 = np.stack([xv[:-1, 1:], yv[:-1, 1:], np.zeros_like(zv[:-1, 1:])], axis=-1)
    b01 = np.stack([xv[1:, :-1], yv[1:, :-1], np.zeros_like(zv[1:, :-1])], axis=-1)
    b11 = np.stack([xv[1:, 1:], yv[1:, 1:], np.zeros_like(zv[1:, 1:])], axis=-1)

    cell_val = 0.25 * (z_grid[:-1, :-1] + z_grid[:-1, 1:] + z_grid[1:, :-1] + z_grid[1:, 1:])
    if cutout_bg:
        mask = cell_val > cutoff_thresh
        if not np.any(mask):
            mask = np.ones_like(cell_val, dtype=bool)
    else:
        mask = np.ones_like(cell_val, dtype=bool)

    tris = []
    tris.append(np.stack([p00[mask], p01[mask], p11[mask]], axis=1))
    tris.append(np.stack([p00[mask], p11[mask], p10[mask]], axis=1))
    tris.append(np.stack([b00[mask], b11[mask], b01[mask]], axis=1))
    tris.append(np.stack([b00[mask], b10[mask], b11[mask]], axis=1))

    pad = np.pad(mask, 1, mode='constant', constant_values=False)
    top_b = mask & (~pad[:-2, 1:-1])
    bot_b = mask & (~pad[2:, 1:-1])
    left_b = mask & (~pad[1:-1, :-2])
    right_b = mask & (~pad[1:-1, 2:])

    if np.any(top_b):
        tris.append(np.stack([p00[top_b], p10[top_b], b10[top_b]], axis=1))
        tris.append(np.stack([p00[top_b], b10[top_b], b00[top_b]], axis=1))
    if np.any(bot_b):
        tris.append(np.stack([p11[bot_b], p01[bot_b], b01[bot_b]], axis=1))
        tris.append(np.stack([p11[bot_b], b01[bot_b], b11[bot_b]], axis=1))
    if np.any(left_b):
        tris.append(np.stack([p01[left_b], p00[left_b], b00[left_b]], axis=1))
        tris.append(np.stack([p01[left_b], b00[left_b], b01[left_b]], axis=1))
    if np.any(right_b):
        tris.append(np.stack([p10[right_b], p11[right_b], b11[right_b]], axis=1))
        tris.append(np.stack([p10[right_b], b11[right_b], b10[right_b]], axis=1))

    all_tris = np.concatenate(tris, axis=0)
    return write_binary_stl_with_normals(all_tris, stl_path)
    # ==============================================================================
# DIGICRAFT MATRIX PALACE - PART 2 OF 5
# Wing A (Jacquard, Teletext Pattern, Glyph Grid) & Wing B-1 (Cutout PBR/STL, Isolines, Depth)
# ==============================================================================

# ==========================================
# 4. אגף א': טקסטיל, ז'קארד, Teletext Pattern ו-Glyph Grid
# ==========================================
def generate_pixel_matrix(image_path, grid_width, num_colors, style, current_user):
    try:
        img = ensure_clean_rgb(image_path)
        w, h = img.size
        aspect_ratio = h / w
        grid_height = max(5, int(grid_width * aspect_ratio))

        img_small = img.resize((grid_width, grid_height), PIL.Image.Resampling.LANCZOS)
        if style == "Teletext Pattern (פסי שידור ורטרו CRT)":
            img_small = PIL.ImageEnhance.Contrast(img_small).enhance(1.45)
            img_small = PIL.ImageEnhance.Color(img_small).enhance(1.5)

        img_quantized = img_small.quantize(colors=num_colors, method=PIL.Image.MEDIANCUT).convert('RGB')
        pixels = img_quantized.load()

        cell_size = 14
        svg_width = grid_width * cell_size
        svg_height = grid_height * cell_size

        if style == "Glyph Grid (מטריצת קוד ובלוקים)":
            bg_hex = "#0018F9"
        elif style in ("אריגת ז'קארד (Jacquard Weave)", "Teletext Pattern (פסי שידור ורטרו CRT)"):
            bg_hex = "#101016"
        else:
            bg_hex = "#fafafa"

        svg_lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}" width="100%" height="100%">']
        svg_lines.append(f'<rect x="0" y="0" width="{svg_width}" height="{svg_height}" fill="{bg_hex}"/>')

        color_counter = {}
        ascii_chars = "@%#*+=-:. "
        glyph_pool = ["0", "1", "%", "{", "}", "7", "8", "3", "?", "=", "[", "]"]
        bayer_2x2 = [[0.2, 0.7], [0.85, 0.4]]

        if style in ("ASCII Art (טיפוגרפיה)", "Glyph Grid (מטריצת קוד ובלוקים)"):
            svg_lines.append('<g font-family="monospace" font-weight="bold" font-size="12" text-anchor="middle" dominant-baseline="central">')
        else:
            svg_lines.append('<g>')

        for y in range(grid_height):
            for x in range(grid_width):
                r, g, b = pixels[x, y]
                lum = get_luminance(r, g, b)

                if style == "Glyph Grid (מטריצת קוד ובלוקים)":
                    norm_l = lum / 255.0
                    px = x * cell_size
                    py = y * cell_size
                    cx = px + cell_size / 2
                    cy = py + cell_size / 2

                    if norm_l > 0.76:
                        # אזורים בהירים הופכים לבלוקים וקטוריים מלאים
                        svg_lines.append(f'<rect x="{px+0.8}" y="{py+0.8}" width="{cell_size-1.6}" height="{cell_size-1.6}" fill="#ffffff"/>')
                        color_counter[(255, 255, 255)] = color_counter.get((255, 255, 255), 0) + 1
                    elif norm_l > 0.22:
                        # אזורי ביניים הופכים לתווי קוד ונתונים
                        g_char = glyph_pool[(x * 7 + y * 13 + int(norm_l * 20)) % len(glyph_pool)]
                        g_col = "#ffffff" if norm_l > 0.48 else "#8ab4ff"
                        svg_lines.append(f'<text x="{cx}" y="{cy}" fill="{g_col}">{g_char}</text>')
                        rgb_k = (255, 255, 255) if norm_l > 0.48 else (138, 180, 255)
                        color_counter[rgb_k] = color_counter.get(rgb_k, 0) + 1
                    else:
                        color_counter[(0, 24, 249)] = color_counter.get((0, 24, 249), 0) + 1
                    continue

                if style == "Teletext Pattern (פסי שידור ורטרו CRT)":
                    # דית'רינג מטריציוני + פסי סריקה אנכיים בסגנון שידור טלוויזיה/סריגה
                    thresh = bayer_2x2[y % 2][x % 2] * 255.0
                    if lum < 35 and lum < thresh * 0.35:
                        color_counter[(16, 16, 22)] = color_counter.get((16, 16, 22), 0) + 1
                        continue
                    px = x * cell_size
                    py = y * cell_size
                    # מיפוי לפלטת טלטקסט ניגודית או צבעי המקור המוגברים
                    if lum > thresh:
                        tr, tg, tb = min(255, int(r * 1.15 + 30)), min(255, int(g * 1.15 + 25)), max(0, int(b * 0.85))
                    else:
                        tr, tg, tb = max(40, int(r * 0.75)), max(40, int(g * 0.75)), min(255, int(b * 1.25 + 45))
                    t_hex = rgb_to_hex(tr, tg, tb)
                    color_counter[(tr, tg, tb)] = color_counter.get((tr, tg, tb), 0) + 1
                    # עמודה אנכית עם מרווח קו סריקה שחור
                    svg_lines.append(f'<rect x="{px+1.5}" y="{py}" width="{cell_size-3.2}" height="{cell_size}" fill="{t_hex}"/>')
                    continue

                if r > 246 and g > 246 and b > 246 and style not in ("Dotted Halftone (נקודות)", "אריגת ז'קארד (Jacquard Weave)"):
                    continue

                rgb_tuple = (r, g, b)
                color_counter[rgb_tuple] = color_counter.get(rgb_tuple, 0) + 1
                hex_color = rgb_to_hex(r, g, b)

                px = x * cell_size
                py = y * cell_size
                cx = px + cell_size / 2
                cy = py + cell_size / 2

                if style == "אריגת ז'קארד (Jacquard Weave)":
                    warp_col = adjust_color(r, g, b, 1.08)
                    weft_col = adjust_color(r, g, b, 0.78)
                    if (x + y) % 2 == 0:
                        svg_lines.append(f'<rect x="{px+1}" y="{py}" width="{cell_size-2}" height="{cell_size}" fill="{warp_col}"/>')
                        svg_lines.append(f'<line x1="{px}" y1="{cy}" x2="{px+cell_size}" y2="{cy}" stroke="#111111" stroke-width="0.8"/>')
                    else:
                        svg_lines.append(f'<rect x="{px}" y="{py+1}" width="{cell_size}" height="{cell_size-2}" fill="{weft_col}"/>')
                        svg_lines.append(f'<line x1="{cx}" y1="{py}" x2="{cx}" y2="{py+cell_size}" stroke="#111111" stroke-width="0.8"/>')

                elif style == "רקמת גובלן / שטיח (Gobelin Tapestry)":
                    bevel_col = adjust_color(r, g, b, 0.8)
                    svg_lines.append(f'<rect x="{px+0.5}" y="{py+0.5}" width="{cell_size-1}" height="{cell_size-1}" fill="{hex_color}" stroke="{bevel_col}" stroke-width="1"/>')
                    svg_lines.append(f'<line x1="{px+2}" y1="{py+cell_size-2}" x2="{px+cell_size-2}" y2="{py+2}" stroke="#ffffff" stroke-width="0.6"/>')

                elif style == "רקמת איקסים (Cross-Stitch)":
                    svg_lines.append(f'<path d="M {px+2} {py+2} L {px+cell_size-2} {py+cell_size-2} M {px+cell_size-2} {py+2} L {px+2} {py+cell_size-2}" stroke="{hex_color}" stroke-width="2.0" fill="none"/>')

                elif style == "סריגה (Knitting)":
                    svg_lines.append(f'<path d="M {px+2} {py+2} L {cx} {py+cell_size-2} L {px+cell_size-2} {py+2}" stroke="{hex_color}" stroke-width="2.4" fill="none"/>')

                elif style == "ASCII Art (טיפוגרפיה)":
                    char_idx = int((lum / 255) * (len(ascii_chars) - 1))
                    char = ascii_chars[char_idx]
                    if char != " ":
                        svg_lines.append(f'<text x="{cx}" y="{cy}" fill="{hex_color}">{char}</text>')

                elif style == "Dotted Halftone (נקודות)":
                    radius = (cell_size / 2) * (1 - (lum / 255))
                    if radius > 0.6:
                        svg_lines.append(f'<circle cx="{cx}" cy="{cy}" r="{radius:.2f}" fill="{hex_color}"/>')

        svg_lines.append('</g></svg>')
        svg_code = "\n".join(svg_lines)

        sorted_colors = sorted(color_counter.items(), key=lambda x: x[1], reverse=True)[:16]
        total_px = max(1, sum(color_counter.values()))
        swatches_html = build_color_swatches_html(sorted_colors, total_px)

        svg_file, png_file = save_dual_outputs(svg_code, "textile_matrix", current_user, f"טקסטיל/מטריצה: {style}")
        preview_html = f'<div class="canvas-preview">{svg_code}</div>'

        return preview_html, swatches_html, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", "", None, None


# ==========================================
# 5. אגף ב' (חלק 1): מעבדת PBR & STL חתוך (ללא משטח ריבועי), קווי גובה ועומק
# ==========================================
def generate_pbr_and_stl(image_path, mesh_res, smooth_sigma, contrast_boost, invert_map, cutout_bg, cutoff_thresh, tile_size_mm, base_thick_mm, relief_height_mm, current_user):
    try:
        img = ensure_clean_rgb(image_path).convert('L')
        if invert_map:
            img = PIL.ImageOps.invert(img)

        hm_arr = np.array(img, dtype=np.float32) / 255.0
        if smooth_sigma > 0:
            hm_arr = gaussian(hm_arr, sigma=smooth_sigma, preserve_range=True)

        hm_min, hm_max = hm_arr.min(), hm_arr.max()
        if hm_max > hm_min:
            hm_arr = (hm_arr - hm_min) / (hm_max - hm_min)
        hm_arr = np.clip((hm_arr - 0.5) * contrast_boost + 0.5, 0.0, 1.0)

        corners_mean = float(np.mean([hm_arr[0, 0], hm_arr[0, -1], hm_arr[-1, 0], hm_arr[-1, -1]]))
        if cutout_bg and corners_mean > 0.75 and not invert_map:
            hm_arr = 1.0 - hm_arr

        ts = int(time.time() * 1000)
        hm_png_path = os.path.join(HISTORY_DIR, f"pbr_heightmap_{ts}.png")
        hm_img = PIL.Image.fromarray((hm_arr * 255).astype(np.uint8), mode='L')
        hm_img.save(hm_png_path, "PNG")

        gy, gx = np.gradient(hm_arr * relief_height_mm)
        nz = np.ones_like(hm_arr) * 0.35
        norm = np.sqrt(gx ** 2 + gy ** 2 + nz ** 2)
        lx, ly, lz = -0.55, -0.55, 0.62
        shaded = np.clip((gx * lx + gy * ly + nz * lz) / norm, 0.0, 1.0)
        if cutout_bg:
            shaded = np.where(hm_arr > cutoff_thresh, shaded, 0.08)
        shaded_img = PIL.Image.fromarray((shaded * 255).astype(np.uint8), mode='L').convert('RGB')

        w_orig, h_orig = img.size
        aspect = h_orig / w_orig
        nx = int(mesh_res)
        ny = max(20, int(nx * aspect))
        hm_mesh_img = hm_img.resize((nx, ny), PIL.Image.Resampling.LANCZOS)
        z_grid = np.array(hm_mesh_img, dtype=np.float32) / 255.0

        if not cutout_bg:
            z_grid[0, :] *= 0.2
            z_grid[-1, :] *= 0.2
            z_grid[:, 0] *= 0.2
            z_grid[:, -1] *= 0.2

        stl_path = os.path.join(HISTORY_DIR, f"bambulab_model_{ts}.stl")
        height_mm = tile_size_mm * aspect
        heightmap_to_watertight_stl(
            z_grid, stl_path,
            width_mm=tile_size_mm, height_mm=height_mm,
            base_mm=base_thick_mm, relief_mm=relief_height_mm,
            cutout_bg=cutout_bg, cutoff_thresh=cutoff_thresh
        )

        save_to_history(current_user, "PBR Height Map + 3D STL", png_path=hm_png_path, stl_path=stl_path)

        mode_str = "חיתוך צורני נקי (ללא משטח ריבועי)" if cutout_bg else "אריח מלא עם משטח בסיס"
        specs_msg = f"<div class='telemetry-box'><b>מוכן ל-Bambu Studio ול-Blender:</b> מצב: {mode_str} | מידות: {tile_size_mm:.0f}x{height_mm:.0f} מ\"מ | בסיס: {base_thick_mm} מ\"מ | תבליט: {relief_height_mm} מ\"מ</div>"
        return hm_img, shaded_img, stl_path, hm_png_path, stl_path, specs_msg
    except Exception as e:
        return None, None, None, None, None, f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>"


def generate_contours(image_path, num_levels, blur_sigma, stroke_col, bg_col, current_user):
    try:
        img = ensure_clean_rgb(image_path).convert('L')
        img_array = np.array(img)
        smoothed = gaussian(img_array, sigma=blur_sigma, preserve_range=True)
        height, width = smoothed.shape

        svg_lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">']
        svg_lines.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="{bg_col}"/>')

        levels = np.linspace(10, 245, num_levels)
        for level in levels:
            contours = measure.find_contours(smoothed, level)
            for contour in contours:
                step = max(1, len(contour) // 180)
                pts = contour[::step]
                if len(pts) >= 2:
                    path_data = "M " + " L ".join([f"{col:.1f} {row:.1f}" for row, col in pts])
                    svg_lines.append(f'<path d="{path_data}" stroke="{stroke_col}" stroke-width="1.6" fill="none"/>')

        svg_lines.append('</svg>')
        svg_code = "\n".join(svg_lines)

        svg_file, png_file = save_dual_outputs(svg_code, "topography_isolines", current_user, "קווי גובה טופוגרפיים")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None


def generate_depth_texture(image_path, grid_size, shape_type, fg_col, bg_col, current_user):
    try:
        img = ensure_clean_rgb(image_path).convert('L')
        w_orig, h_orig = img.size
        aspect = h_orig / w_orig
        gw = int(grid_size)
        gh = max(5, int(gw * aspect))

        img_small = img.resize((gw, gh), PIL.Image.Resampling.LANCZOS)
        pixels = img_small.load()

        cell = 24
        vw, vh = gw * cell, gh * cell
        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vw} {vh}" width="100%" height="100%">']
        svg.append(f'<rect x="0" y="0" width="{vw}" height="{vh}" fill="{bg_col}"/>')

        for y in range(gh):
            for x in range(gw):
                lum = pixels[x, y] / 255.0
                weight = 1.0 - lum if bg_col.lower() in ("#ffffff", "#fafafa") else lum
                if weight < 0.08:
                    continue
                cx = x * cell + cell / 2.0
                cy = y * cell + cell / 2.0
                max_r = (cell * 0.46) * weight

                if shape_type == "Circles (מעגלים פרמטריים)":
                    svg.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{max_r:.2f}" fill="none" stroke="{fg_col}" stroke-width="{max(1.0, weight*3.2):.2f}"/>')
                elif shape_type == "Squares (ריבועים מדורגים)":
                    s = max_r * 1.8
                    svg.append(f'<rect x="{cx - s/2:.1f}" y="{cy - s/2:.1f}" width="{s:.1f}" height="{s:.1f}" fill="none" stroke="{fg_col}" stroke-width="{max(1.0, weight*2.8):.2f}"/>')
                elif shape_type == "Hexagons (משושים גיאומטריים)":
                    pts = []
                    for i in range(6):
                        ang = math.radians(i * 60)
                        pts.append(f"{cx + max_r * math.cos(ang):.1f},{cy + max_r * math.sin(ang):.1f}")
                    svg.append(f'<polygon points="{" ".join(pts)}" fill="none" stroke="{fg_col}" stroke-width="{max(1.0, weight*2.5):.2f}"/>')
                else:
                    svg.append(f'<line x1="{cx - max_r:.1f}" y1="{cy - max_r:.1f}" x2="{cx + max_r:.1f}" y2="{cy + max_r:.1f}" stroke="{fg_col}" stroke-width="{max(1.0, weight*3.5):.2f}"/>')
                    svg.append(f'<line x1="{cx + max_r:.1f}" y1="{cy - max_r:.1f}" x2="{cx - max_r:.1f}" y2="{cy + max_r:.1f}" stroke="{fg_col}" stroke-width="{max(1.0, weight*2.0):.2f}"/>')

        svg.append('</svg>')
        svg_code = "\n".join(svg)

        svg_file, png_file = save_dual_outputs(svg_code, "parametric_depth_texture", current_user, f"טקסטורת עומק: {shape_type}")
        preview_html = f'<div class="canvas-preview">{svg_code}</div>'
        return preview_html, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None
        # ==============================================================================
# DIGICRAFT MATRIX PALACE - PART 3 OF 5
# Wing B-2 (Heatmap + Stipple Duotone + Thermal Noise + Raster Lines STL)
# & Wing C (Waveform, Interactive 3D Voxel Art, Guilloche, Liquid Screen)
# ==============================================================================

# ==========================================
# 6. אגף ב' (חלק 2): Heatmap מתקדם (Stipple Duotone & Thermal Noise) + Raster Lines
# ==========================================
def get_heatmap_palette(scheme):
    if scheme == "Cyber Thermal (סגול-אדום-צהוב ליבון)":
        return [
            (16, 12, 48), (62, 18, 108), (132, 24, 122),
            (196, 48, 88), (238, 104, 42), (250, 178, 34), (252, 248, 164)
        ]
    elif scheme == "Acid Infrared (ירוק-ליים-ציאן תעשייתי)":
        return [
            (12, 20, 18), (18, 64, 56), (22, 122, 92),
            (56, 188, 108), (144, 232, 72), (224, 250, 96), (255, 255, 210)
        ]
    elif scheme == "Stitch Amber (פחם-נחושת-זהב חם)":
        return [
            (18, 18, 20), (54, 34, 30), (112, 52, 40),
            (178, 82, 56), (224, 126, 72), (242, 184, 102), (252, 236, 196)
        ]
    else:
        return [
            (15, 35, 80), (35, 95, 160), (90, 175, 215),
            (225, 235, 215), (245, 175, 105), (215, 75, 55), (140, 15, 30)
        ]


def generate_heatmap_room(image_path, mode_style, palette_name, resolution, blur_val, current_user):
    try:
        img = ensure_clean_rgb(image_path).convert('L')
        w_orig, h_orig = img.size
        aspect = h_orig / w_orig

        # מצבים אמנותיים חדשים: Stipple Duotone ו-Thermal Noise עם הילת קווי מתאר
        if mode_style in ("Stipple Duotone (הילת ענבר וגרעיניות נייר קרם)", "Thermal Noise (ניאון אסיד מג'נטה-מנטה)"):
            w = 640
            h = max(120, int(w * aspect))
            img_res = img.resize((w, h), PIL.Image.Resampling.LANCZOS)
            arr = np.array(img_res, dtype=np.float32) / 255.0

            # זיהוי רקע אוטומטי והפרדת דמות/אובייקט
            corners_mean = float(np.mean([arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]]))
            obj_mask = (1.0 - arr) if corners_mean > 0.5 else arr
            obj_mask = np.clip((obj_mask - 0.18) * 1.45, 0.0, 1.0)

            # יצירת הילה זוהרת סביב קווי המתאר (Contour Glow Aura)
            aura_blur = gaussian(obj_mask, sigma=max(2.5, blur_val * 1.8), preserve_range=True)
            aura_ring = np.clip(aura_blur * 1.65 - obj_mask * 0.9, 0.0, 1.0)

            # רעש נקודתי סטוכסטי (Stochastic Stipple Grain)
            rng = np.random.default_rng(42)
            noise = rng.random((h, w), dtype=np.float32)
            paper_specks = rng.random((h, w), dtype=np.float32)

            if "Stipple Duotone" in mode_style:
                # רקע נייר קרם מנוקד (#F5EBD6) + הילה כתומה-ענברית (#FF9E2C) + דיו כחול-פחם (#0D1526)
                bg_col = np.array([245.0, 235.0, 214.0], dtype=np.float32)
                aura_col = np.array([255.0, 158.0, 44.0], dtype=np.float32)
                ink_col = np.array([13.0, 21.0, 38.0], dtype=np.float32)
                pal_swatches = [((245, 235, 214), 45), ((255, 158, 44), 25), ((13, 21, 38), 30)]
            else:
                # רקע מנטה-ליים (#A6F79C) + הילה מג'נטה זוהרת (#F2297A) + גרעין כהה סגול-שחור (#1A0714)
                bg_col = np.array([166.0, 247.0, 156.0], dtype=np.float32)
                aura_col = np.array([242.0, 41.0, 122.0], dtype=np.float32)
                ink_col = np.array([26.0, 7.0, 20.0], dtype=np.float32)
                pal_swatches = [((166, 247, 156), 45), ((242, 41, 122), 25), ((26, 7, 20), 30)]

            canvas = np.broadcast_to(bg_col, (h, w, 3)).copy()
            # נקודות נייר עדינות ברקע
            speck_mask = paper_specks > 0.965
            canvas[speck_mask] = canvas[speck_mask] * 0.72

            # מיזוג הילת קו המתאר
            aura_w = aura_ring[..., None]
            canvas = canvas * (1.0 - aura_w * 0.85) + aura_col * (aura_w * 0.85)

            # הטמעת נקודות הדיו (Stipple Dots) על האובייקט
            stipple_hit = (obj_mask > 0.12) & (noise < (obj_mask ** 0.85))
            canvas[stipple_hit] = ink_col

            out_pil = PIL.Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), mode='RGB')
            svg_code = wrap_pil_as_svg(out_pil, f"HEATMAP_ENGINE // {mode_style}")
            swatches_html = build_color_swatches_html(pal_swatches, 100)
            svg_file, png_file = save_dual_outputs(svg_code, "heatmap_stipple", current_user, f"Heatmap: {mode_style}", custom_png_img=out_pil)
            preview = f'<div class="canvas-preview">{svg_code}</div>'
            return preview, swatches_html, svg_file, png_file

        pal = get_heatmap_palette(palette_name)
        num_bands = len(pal)

        if mode_style == "שכבות איזותרמיות (Isothermal Contours)":
            w, h = 600, int(600 * aspect)
            img_res = img.resize((w, h), PIL.Image.Resampling.LANCZOS)
            arr = gaussian(np.array(img_res), sigma=blur_val, preserve_range=True)

            svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" height="100%">']
            bg_hex = rgb_to_hex(*pal[0])
            svg.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="{bg_hex}"/>')

            thresholds = np.linspace(25, 235, num_bands - 1)
            for idx, th in enumerate(thresholds):
                col_hex = rgb_to_hex(*pal[idx + 1])
                contours = measure.find_contours(arr, th)
                for c in contours:
                    step = max(1, len(c) // 140)
                    pts = c[::step]
                    if len(pts) >= 3:
                        d_str = "M " + " L ".join([f"{p[1]:.1f} {p[0]:.1f}" for p in pts]) + " Z"
                        svg.append(f'<path d="{d_str}" fill="{col_hex}" stroke="#111111" stroke-width="0.6"/>')
            svg.append('</svg>')
            svg_code = "\n".join(svg)
        else:
            gw = int(resolution)
            gh = max(5, int(gw * aspect))
            img_small = img.resize((gw, gh), PIL.Image.Resampling.LANCZOS)
            arr = gaussian(np.array(img_small), sigma=max(0.5, blur_val * 0.3), preserve_range=True)

            cell = 14
            vw, vh = gw * cell, gh * cell
            svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vw} {vh}" width="100%" height="100%">']
            svg.append(f'<rect x="0" y="0" width="{vw}" height="{vh}" fill="#121212"/>')

            for y in range(gh):
                for x in range(gw):
                    val = arr[y, x] / 255.0
                    b_idx = min(num_bands - 1, int(val * num_bands))
                    r, g, b = pal[b_idx]
                    col_hex = rgb_to_hex(r, g, b)
                    px, py = x * cell, y * cell
                    if mode_style == "מטריצת תאים תרמית (Thermal Matrix Grid)":
                        svg.append(f'<rect x="{px+1}" y="{py+1}" width="{cell-2}" height="{cell-2}" fill="{col_hex}"/>')
                    else:
                        rad = (cell * 0.48) * (0.25 + 0.75 * val)
                        svg.append(f'<circle cx="{px+cell/2}" cy="{py+cell/2}" r="{rad:.2f}" fill="{col_hex}"/>')
            svg.append('</svg>')
            svg_code = "\n".join(svg)

        color_counts = [(c, 100) for c in pal]
        swatches_html = build_color_swatches_html(color_counts, len(pal) * 100)
        svg_file, png_file = save_dual_outputs(svg_code, "heatmap_vector", current_user, f"Heatmap: {palette_name}")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, swatches_html, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", "", None, None


def generate_raster_lines(image_path, num_lines, amp, line_col, glow_col, current_user):
    """חדר Raster Lines: קווי סריקה טופוגרפיים זוהרים + ייצוא ישיר ל-STL לתבליט תלת-ממדי"""
    try:
        img = ensure_clean_rgb(image_path).convert('L')
        w, h = 840, max(240, int(840 * (img.height / img.width)))
        res_x = 150
        n_rows = int(num_lines)

        img_small = img.resize((res_x, n_rows), PIL.Image.Resampling.LANCZOS)
        arr = gaussian(np.array(img_small, dtype=np.float32) / 255.0, sigma=0.8, preserve_range=True)

        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" height="100%">']
        svg.append(f'''<defs>
            <linearGradient id="rasterGlow" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="{glow_col}"/>
                <stop offset="50%" stop-color="{line_col}"/>
                <stop offset="100%" stop-color="{glow_col}"/>
            </linearGradient>
        </defs>''')
        svg.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="#05080d"/>')

        step_y = (h - 40) / max(1, n_rows)
        step_x = w / max(1, res_x - 1)

        for y_idx in range(n_rows):
            py_base = 25 + y_idx * step_y
            pts = []
            max_row_val = 0.0
            for x_idx in range(res_x):
                val = float(arr[y_idx, x_idx])
                if val > max_row_val:
                    max_row_val = val
                px = x_idx * step_x
                py = py_base - (val * amp)
                pts.append(f"{px:.1f} {py:.1f}")

            path_d = "M " + " L ".join(pts)
            # שכבת הילה רחבה עדינה + קו ליבה חד ובוהק
            svg.append(f'<path d="{path_d}" stroke="{glow_col}" stroke-width="3.2" opacity="0.24" fill="none"/>')
            sw = 1.0 + max_row_val * 1.4
            svg.append(f'<path d="{path_d}" stroke="url(#rasterGlow)" stroke-width="{sw:.2f}" fill="none"/>')

        svg.append('</svg>')
        svg_code = "\n".join(svg)

        # בניית קובץ STL תלת-ממדי של גלי ה-Raster להדפסה ב-Bambu Lab
        ts = int(time.time() * 1000)
        stl_file = os.path.join(HISTORY_DIR, f"raster_lines_3d_{ts}.stl")
        z_grid = np.clip(arr, 0.0, 1.0)
        heightmap_to_watertight_stl(
            z_grid, stl_file,
            width_mm=100.0, height_mm=100.0 * (img.height / img.width),
            base_mm=1.4, relief_mm=max(1.2, amp * 0.08),
            cutout_bg=True, cutoff_thresh=0.06
        )

        svg_file, png_file = save_dual_outputs(svg_code, "raster_lines", current_user, "Raster Lines (גלי סריקה + STL)", stl_path=stl_file)
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, stl_file, svg_file, png_file, stl_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None, None, None


# ==========================================
# 7. אגף ג': מחוללים מתמטיים + 3D Voxel Art + Liquid Screen
# ==========================================
def generate_waveform(image_path, num_lines, amp, color, current_user):
    try:
        img = ensure_clean_rgb(image_path)
        w, h = 800, int(800 * (img.height / img.width))
        res_x = 110
        img_small = img.resize((res_x, num_lines), PIL.Image.Resampling.LANCZOS)
        pixels = img_small.load()

        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" height="100%">']
        svg.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="#fafafa"/>')

        step_y = h / num_lines
        step_x = w / (res_x - 1)

        for y_idx in range(num_lines):
            path_pts = []
            py_base = y_idx * step_y
            for x_idx in range(res_x):
                r, g, b = pixels[x_idx, y_idx]
                lum = get_luminance(r, g, b)
                displacement = amp * ((255 - lum) / 255)
                px = x_idx * step_x
                py = py_base - displacement
                path_pts.append(f"{px:.1f} {py:.1f}")

            path_d = "M " + " L ".join(path_pts)
            svg.append(f'<path d="{path_d}" stroke="{color}" stroke-width="1.6" fill="none"/>')

        svg.append('</svg>')
        svg_code = "\n".join(svg)

        svg_file, png_file = save_dual_outputs(svg_code, "waveform_art", current_user, "גלי קול (Waveform)")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None


def build_voxel_3d_stl(active_voxels, stl_path):
    tris = []
    for (x0, y0, x1, y1, z1) in active_voxels:
        z0 = 0.0
        v000 = [x0, y0, z0]
        v100 = [x1, y0, z0]
        v110 = [x1, y1, z0]
        v010 = [x0, y1, z0]
        v001 = [x0, y0, z1]
        v101 = [x1, y0, z1]
        v111 = [x1, y1, z1]
        v011 = [x0, y1, z1]

        tris.extend([
            [v001, v101, v111], [v001, v111, v011],
            [v000, v110, v100], [v000, v010, v110],
            [v000, v100, v101], [v000, v101, v001],
            [v110, v010, v011], [v110, v011, v111],
            [v010, v000, v001], [v010, v001, v011],
            [v100, v110, v111], [v100, v111, v101],
        ])

    if not tris:
        tris = [[[0, 0, 0], [10, 0, 0], [0, 10, 1]]]
    all_tris = np.array(tris, dtype=np.float32)
    return write_binary_stl_with_normals(all_tris, stl_path)


def generate_iso_voxels(image_path, grid_width, extrusion, gap, remove_bg_mode, current_user):
    try:
        img = ensure_clean_rgb(image_path)
        aspect = img.height / img.width
        grid_height = max(5, int(grid_width * aspect))

        img_small = img.resize((grid_width, grid_height), PIL.Image.Resampling.LANCZOS)
        img_quantized = img_small.quantize(colors=12, dither=PIL.Image.Dither.NONE).convert('RGB')
        pixels = img_quantized.load()

        step_w = 10
        step_h = 5
        base_h = 4

        min_x = -grid_height * step_w
        max_x = grid_width * step_w
        min_y = -extrusion - base_h - step_h
        max_y = (grid_width + grid_height) * step_h + extrusion

        ox = min_x - step_w * 2
        oy = min_y - step_h * 2
        svg_w = max_x - min_x + (step_w * 4)
        svg_h = max_y - min_y + (step_h * 4)

        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{ox} {oy} {svg_w} {svg_h}" width="100%" height="100%">']
        svg.append(f'<rect x="{ox}" y="{oy}" width="{svg_w}" height="{svg_h}" fill="#141417"/>')

        dw = step_w - gap
        dh = step_h - (gap / 2.0)

        color_counter = {}
        active_voxels_3d = []
        cell_mm = 2.0
        gap_mm = min(0.8, gap * 0.15)

        for y in range(grid_height):
            for x in range(grid_width):
                r, g, b = pixels[x, y]
                lum = get_luminance(r, g, b)

                if "בהיר" in remove_bg_mode and lum > 240:
                    continue
                if "כהה" in remove_bg_mode and lum < 22:
                    continue

                color_counter[(r, g, b)] = color_counter.get((r, g, b), 0) + 1
                h_z = base_h + (lum / 255.0) * extrusion

                color_top = adjust_color(r, g, b, 1.0)
                color_left = adjust_color(r, g, b, 0.82)
                color_right = adjust_color(r, g, b, 0.62)

                cx = (x - y) * step_w
                cy = (x + y) * step_h
                rx, ry = cx, cy - h_z

                p_left = f"{rx - dw},{ry} {rx},{ry + dh} {cx},{cy + dh} {cx - dw},{cy}"
                p_right = f"{rx},{ry + dh} {rx + dw},{ry} {cx + dw},{cy} {cx},{cy + dh}"
                p_top = f"{rx},{ry - dh} {rx + dw},{ry} {rx},{ry + dh} {rx - dw},{ry}"

                svg.append(f'<polygon points="{p_left}" fill="{color_left}"/>')
                svg.append(f'<polygon points="{p_right}" fill="{color_right}"/>')
                svg.append(f'<polygon points="{p_top}" fill="{color_top}"/>')

                vx0 = x * cell_mm + gap_mm
                vy0 = (grid_height - 1 - y) * cell_mm + gap_mm
                vx1 = (x + 1) * cell_mm - gap_mm
                vy1 = (grid_height - y) * cell_mm - gap_mm
                vz1 = 2.0 + (lum / 255.0) * (extrusion * 0.35)
                active_voxels_3d.append((vx0, vy0, vx1, vy1, vz1))

        svg.append('</svg>')
        svg_code = "\n".join(svg)

        ts = int(time.time() * 1000)
        stl_file = os.path.join(HISTORY_DIR, f"voxel_3d_{ts}.stl")
        build_voxel_3d_stl(active_voxels_3d, stl_file)

        sorted_colors = sorted(color_counter.items(), key=lambda x: x[1], reverse=True)
        swatches_html = build_color_swatches_html(sorted_colors, max(1, sum(color_counter.values())))
        svg_file, png_file = save_dual_outputs(svg_code, "voxel_sculpture", current_user, "פסל איזומטרי (3D Voxel Art)", stl_path=stl_file)

        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, stl_file, swatches_html, svg_file, png_file, stl_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, "", None, None, None


def generate_adaptive_guilloche(image_path, num_colors, base_R, rotations, current_user):
    try:
        img = ensure_clean_rgb(image_path)
        w, h = 800, 800
        img_resized = img.resize((w, h), PIL.Image.Resampling.LANCZOS)

        img_q = img_resized.quantize(colors=num_colors, method=PIL.Image.MEDIANCUT).convert('RGB')
        pixels = img_q.load()

        colors_counts = img_q.getcolors(maxcolors=256)
        colors_counts.sort(key=lambda x: x[0], reverse=True)
        unique_colors = [c[1] for c in colors_counts[:num_colors]]

        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" height="100%">']
        svg.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="#111111"/>')

        cx, cy = w / 2, h / 2
        steps = int(rotations * 130)

        for idx, color in enumerate(unique_colors):
            r = base_R * max(0.1, (0.15 + (idx * 0.27) % 0.8))
            d = base_R * (0.2 + (idx * 0.41) % 1.5)
            hex_col = rgb_to_hex(color[0], color[1], color[2])

            for i in range(steps):
                t1 = i * (2 * math.pi * rotations / steps)
                t2 = (i + 1) * (2 * math.pi * rotations / steps)

                x1 = cx + (base_R - r) * math.cos(t1) + d * math.cos(((base_R - r) / r) * t1)
                y1 = cy + (base_R - r) * math.sin(t1) - d * math.sin(((base_R - r) / r) * t1)
                x2 = cx + (base_R - r) * math.cos(t2) + d * math.cos(((base_R - r) / r) * t2)
                y2 = cy + (base_R - r) * math.sin(t2) - d * math.sin(((base_R - r) / r) * t2)

                mx, my = int((x1 + x2) / 2), int((y1 + y2) / 2)
                if 0 <= mx < w and 0 <= my < h:
                    if pixels[mx, my] == color:
                        svg.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{hex_col}" stroke-width="1.3"/>')

        svg.append('</svg>')
        svg_code = "\n".join(svg)

        swatches_html = build_color_swatches_html([(c[1], c[0]) for c in colors_counts[:num_colors]], w * h)
        svg_file, png_file = save_dual_outputs(svg_code, "adaptive_guilloche", current_user, "רוזטת גיליושה אדפטיבית")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, swatches_html, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", "", None, None


def generate_liquid_screen(image_path, drip_length, glow_intensity, aura_tint, current_user):
    """חדר Liquid Screen: רשת תת-פיקסלים RGB אנכית + הילה זוהרת ונזילת פיקסלים כלפי מטה"""
    try:
        img = ensure_clean_rgb(image_path)
        w = 600
        h = max(140, int(w * (img.height / img.width)))
        img_res = img.resize((w, h), PIL.Image.Resampling.LANCZOS)
        arr = np.array(img_res, dtype=np.float32) / 255.0
        lum = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]

        corners_mean = float(np.mean([lum[0, 0], lum[0, -1], lum[-1, 0], lum[-1, -1]]))
        silhouette = (1.0 - lum) if corners_mean > 0.55 else lum
        silhouette = np.clip((silhouette - 0.15) * 1.4, 0.0, 1.0)

        # זיהוי קווי מתאר והילת אור כחולה-סגולה / טורקיז
        blurred = gaussian(silhouette, sigma=4.5, preserve_range=True)
        edge_glow = np.clip(blurred * glow_intensity - silhouette * 0.65, 0.0, 1.0)

        # אלגוריתם נזילה אנכית (Vertical Pixel Melt / Drip Trails)
        drip_map = edge_glow.copy()
        steps = max(10, int(drip_length))
        decay = 0.965
        for step in range(1, steps):
            shifted = np.roll(edge_glow, shift=step, axis=0)
            shifted[:step, :] = 0.0
            # אפנון גלי לעמודות הנזילה ליצירת נטיפים אורגניים
            col_wave = 0.5 + 0.5 * np.sin(np.arange(w) * 0.22 + (step * 0.05))
            drip_map = np.maximum(drip_map, shifted * (decay ** step) * col_wave[None, :])

        if aura_tint == "Electric Cobalt & Violet (כחול חשמלי וסגול)":
            tint_rgb = np.array([75.0, 95.0, 255.0], dtype=np.float32)
        elif aura_tint == "Cyber Cyan & Emerald (ציאן ואמרלד)":
            tint_rgb = np.array([30.0, 235.0, 210.0], dtype=np.float32)
        else:
            tint_rgb = np.array([255.0, 75.0, 165.0], dtype=np.float32)

        # מיזוג התמונה המקורית עם ההילה והנזילות
        base_dark = arr * (silhouette[..., None] * 0.85 + 0.06)
        glow_layer = (drip_map[..., None] ** 1.1) * (tint_rgb / 255.0) * 1.25
        combined = np.clip(base_dark + glow_layer, 0.0, 1.0)

        # הלבשת רשת תת-פיקסלים RGB אנכית (LCD / CRT Subpixel Matrix)
        sub_mask = np.ones((h, w, 3), dtype=np.float32) * 0.35
        x_idx = np.arange(w)
        y_idx = np.arange(h)
        sub_mask[:, x_idx % 3 == 0, 0] = 1.15  # Red subpixel
        sub_mask[:, x_idx % 3 == 1, 1] = 1.15  # Green subpixel
        sub_mask[:, x_idx % 3 == 2, 2] = 1.15  # Blue subpixel
        sub_mask[y_idx % 4 == 0, :, :] *= 0.45   # Horizontal scanline gap

        final_arr = np.clip(combined * sub_mask * 255.0, 0, 255).astype(np.uint8)
        out_pil = PIL.Image.fromarray(final_arr, mode='RGB')

        svg_code = wrap_pil_as_svg(out_pil, f"LIQUID_SCREEN // DRIP: {steps}PX // {aura_tint}")
        svg_file, png_file = save_dual_outputs(svg_code, "liquid_screen", current_user, "Liquid Screen (מסך נוזלי)", custom_png_img=out_pil)
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None
        # ==============================================================================
# DIGICRAFT MATRIX PALACE - PART 4 OF 5
# Wing D (Tiled Panel Connector, Xerox Collage, Dielines, Print Marks) & Wing E (Gentype)
# ==============================================================================

# ==========================================
# 8. אגף ד': Panel Connector (תצוגת הרכבת אריחים), Xerox Collage, אריזה ודפוס
# ==========================================
def build_connector_edge(x1, y1, x2, y2, conn_type, direction, tab_scale=1.0):
    """בונה צלע עם שן מכנית מדויקת (זכר/נקבה) שננעלת בצורה חלקה באריח השכן"""
    if direction == 0:
        return f"{x2:.2f} {y2:.2f}"
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    nx, ny = -uy * direction, ux * direction

    def pt(along, perp):
        px = x1 + ux * along * length + nx * (perp * length * tab_scale)
        py = y1 + uy * along * length + ny * (perp * length * tab_scale)
        return f"{px:.2f} {py:.2f}"

    if conn_type == "זנב סנונית (Dovetail Joint)":
        pts = [pt(0.36, 0), pt(0.31, 0.15), pt(0.69, 0.15), pt(0.64, 0), pt(1.0, 0)]
    elif conn_type == "מחבר חץ מכני (Arrow Lock)":
        pts = [pt(0.42, 0), pt(0.42, 0.08), pt(0.33, 0.08), pt(0.50, 0.21), pt(0.67, 0.08), pt(0.58, 0.08), pt(0.58, 0), pt(1.0, 0)]
    else:  # Omega Puzzle Lock
        pts = [
            pt(0.38, 0), pt(0.36, 0.05), pt(0.32, 0.11),
            pt(0.37, 0.18), pt(0.50, 0.20), pt(0.63, 0.18),
            pt(0.68, 0.11), pt(0.64, 0.05), pt(0.62, 0), pt(1.0, 0)
        ]
    return " L ".join(pts)


def generate_panel_connector(image_path, grid_layout, tile_shape, conn_type, inner_pattern, tile_size_mm, tab_scale, density, thickness_mm, current_user):
    try:
        if "3x3" in grid_layout:
            n_grid = 3
        elif "2x2" in grid_layout:
            n_grid = 2
        else:
            n_grid = 1

        canvas = 660
        margin = 75
        usable = canvas - margin * 2

        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas} {canvas}" width="100%" height="100%">']
        svg.append(f'<rect x="0" y="0" width="{canvas}" height="{canvas}" fill="#141414"/>')

        svg.append('<g stroke="#222228" stroke-width="0.6">')
        for g in range(0, canvas, 30):
            svg.append(f'<line x1="{g}" y1="0" x2="{g}" y2="{canvas}"/>')
            svg.append(f'<line x1="0" y1="{g}" x2="{canvas}" y2="{g}"/>')
        svg.append('</g>')

        img_arr = None
        if image_path:
            img_gray = ensure_clean_rgb(image_path).convert('L').resize((canvas, canvas), PIL.Image.Resampling.LANCZOS)
            img_arr = np.array(img_gray, dtype=np.float32) / 255.0

        tile_centers = []
        if tile_shape == "אריח ריבועי מודולרי (Square Tiling)":
            step = usable / n_grid
            half = (step / 2.0) - (1.8 if n_grid > 1 else 0.0)
            for row in range(n_grid):
                for col in range(n_grid):
                    cx = margin + step * (col + 0.5)
                    cy = margin + step * (row + 0.5)
                    tile_centers.append((cx, cy, half, row, col))
                    corners = [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half)]
                    dirs = [-1, 1, 1, -1]
                    segs = [build_connector_edge(corners[i][0], corners[i][1], corners[(i+1)%4][0], corners[(i+1)%4][1], conn_type, dirs[i], tab_scale) for i in range(4)]
                    path_d = f"M {corners[0][0]:.2f} {corners[0][1]:.2f} L " + " L ".join(segs) + " Z"
                    fill_c = "#202026" if (row + col) % 2 == 0 else "#26262e"
                    svg.append(f'<path d="{path_d}" fill="{fill_c}" stroke="#00e5ff" stroke-width="2.0"/>')
        else:
            rad = (usable / (n_grid * 1.85))
            dx = rad * 1.5
            dy = rad * math.sqrt(3)
            for row in range(n_grid):
                for col in range(n_grid):
                    cx = margin + rad + col * dx
                    cy = margin + rad + row * dy + (col % 2) * (dy / 2.0)
                    r_draw = rad - (1.5 if n_grid > 1 else 0.0)
                    tile_centers.append((cx, cy, r_draw * 0.85, row, col))
                    corners = [(cx + r_draw * math.cos(math.radians(60 * i)), cy + r_draw * math.sin(math.radians(60 * i))) for i in range(6)]
                    dirs = [1, 1, 1, -1, -1, -1]
                    segs = [build_connector_edge(corners[i][0], corners[i][1], corners[(i+1)%6][0], corners[(i+1)%6][1], conn_type, dirs[i], tab_scale) for i in range(6)]
                    path_d = f"M {corners[0][0]:.2f} {corners[0][1]:.2f} L " + " L ".join(segs) + " Z"
                    svg.append(f'<path d="{path_d}" fill="#222228" stroke="#00e5ff" stroke-width="2.0"/>')

        for (cx, cy, half_r, row, col) in tile_centers:
            inner_r = half_r * 0.72
            if img_arr is not None:
                sub_n = max(4, int(density))
                step_p = (inner_r * 2) / sub_n
                for iy in range(sub_n):
                    for ix in range(sub_n):
                        px = (cx - inner_r) + (ix + 0.5) * step_p
                        py = (cy - inner_r) + (iy + 0.5) * step_p
                        ix_img = min(canvas - 1, max(0, int(px)))
                        iy_img = min(canvas - 1, max(0, int(py)))
                        val = 1.0 - img_arr[iy_img, ix_img]
                        if val > 0.15:
                            cr = (step_p * 0.44) * val
                            svg.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{cr:.2f}" fill="#141414" stroke="#ff5252" stroke-width="1.3"/>')

            elif inner_pattern == "עורקי עלים אורגניים (Organic Venation)":
                for b in range(int(density)):
                    angle = (2 * math.pi * b) / density + (row * 0.3 + col * 0.3)
                    ex = cx + inner_r * math.cos(angle)
                    ey = cy + inner_r * math.sin(angle)
                    mx = cx + (inner_r * 0.5) * math.cos(angle + 0.25)
                    my = cy + (inner_r * 0.5) * math.sin(angle + 0.25)
                    svg.append(f'<path d="M {cx:.1f} {cy:.1f} Q {mx:.1f} {my:.1f} {ex:.1f} {ey:.1f}" stroke="#ff5252" stroke-width="2.0" fill="none"/>')

            elif inner_pattern == "רשת תאים / וורונוי (Cellular Web)":
                rings = max(2, int(density // 3))
                for r_idx in range(1, rings + 1):
                    rad_c = (inner_r / rings) * r_idx
                    num_pts = r_idx * 6
                    for j in range(num_pts):
                        a1 = (2 * math.pi * j) / num_pts + (r_idx * 0.2)
                        px = cx + rad_c * math.cos(a1)
                        py = cy + rad_c * math.sin(a1)
                        hole_r = (inner_r / (rings * 2.3)) * (1.1 - 0.25 * (r_idx / rings))
                        svg.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{hole_r:.1f}" fill="#141414" stroke="#ff5252" stroke-width="1.5"/>')

            elif inner_pattern == "גלים פרמטריים משתלבים (Continuous Wave Lattice)":
                lines = max(3, int(density // 2))
                step_l = (inner_r * 1.8) / lines
                for l_idx in range(lines + 1):
                    y_base = (cy - inner_r * 0.9) + l_idx * step_l
                    pts = []
                    for s in range(24):
                        px = (cx - inner_r * 0.9) + (s / 23.0) * (inner_r * 1.8)
                        py = y_base + math.sin((px / 35.0) * math.pi * 2) * 6.0
                        pts.append(f"{px:.1f} {py:.1f}")
                    svg.append(f'<path d="M {" L ".join(pts)}" stroke="#ff5252" stroke-width="1.8" fill="none"/>')

        svg.append(f'<text x="{canvas/2}" y="{canvas - 14}" fill="#888888" font-family="monospace" font-size="11" text-anchor="middle">PANEL_ASSEMBLY: {n_grid}x{n_grid} // TILE: {tile_size_mm:.0f}MM // JOINT: {conn_type}</text>')
        svg.append('</svg>')
        svg_code = "\n".join(svg)

        ts = int(time.time() * 1000)
        stl_file = os.path.join(HISTORY_DIR, f"panel_connector_{ts}.stl")
        svg_file, png_file = save_dual_outputs(svg_code, "panel_connector_assembly", current_user, f"Panel Connector ({n_grid}x{n_grid})", stl_path=stl_file)

        png_img = PIL.Image.open(png_file).convert('L').resize((130, 130), PIL.Image.Resampling.LANCZOS)
        z_arr = np.where(np.array(png_img, dtype=np.float32) > 28, 1.0, 0.0).astype(np.float32)
        heightmap_to_watertight_stl(
            z_arr, stl_file,
            width_mm=tile_size_mm * n_grid, height_mm=tile_size_mm * n_grid,
            base_mm=0.2, relief_mm=thickness_mm,
            cutout_bg=True, cutoff_thresh=0.1
        )

        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, stl_file, svg_file, png_file, stl_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None, None, None


def generate_xerox_collage(image_path, serial_code, editorial_text, grain_level, paper_tint, current_user):
    """חדר Xerox Collage: הדפס מכונת צילום גרעיני + קרעי נייר וקטוריים, שרטוט אדריכלי, ברקוד וטקסט עריכתי"""
    try:
        img = ensure_clean_rgb(image_path).convert('L')
        w = 600
        h = max(450, int(w * (img.height / img.width)))
        img_res = img.resize((w, h), PIL.Image.Resampling.LANCZOS)

        # הגברת ניגודיות של מכונת צילום (High-Contrast Photocopy / Xerox Grain)
        arr = np.array(img_res, dtype=np.float32) / 255.0
        arr = np.clip((arr - 0.48) * (1.8 + grain_level * 0.25) + 0.5, 0.0, 1.0)
        rng = np.random.default_rng(105)
        xerox_noise = (rng.random((h, w), dtype=np.float32) - 0.5) * (0.28 + grain_level * 0.08)
        arr = np.clip(arr + xerox_noise, 0.0, 1.0)

        # קווי קיפול וטונר שחוק של מכונת צילום
        arr[h // 2 - 1:h // 2 + 2, :] *= 0.65
        arr[:, w // 2 - 1:w // 2 + 1] *= 0.72

        if paper_tint == "נייר ארכיון חם (Warm Sepia Paper)":
            p_light = np.array([238.0, 228.0, 208.0], dtype=np.float32)
            p_dark = np.array([22.0, 20.0, 18.0], dtype=np.float32)
            strip_fill = "#ebe1cc"
        else:
            p_light = np.array([242.0, 242.0, 240.0], dtype=np.float32)
            p_dark = np.array([15.0, 15.0, 17.0], dtype=np.float32)
            strip_fill = "#f2f2ef"

        xerox_rgb = p_dark[None, None, :] + (arr[..., None] * (p_light - p_dark)[None, None, :])
        xerox_pil = PIL.Image.fromarray(np.clip(xerox_rgb, 0, 255).astype(np.uint8), mode='RGB')

        import io
        buf = io.BytesIO()
        xerox_pil.save(buf, format="PNG")
        b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")

        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" height="100%">']
        svg.append(f'<image x="0" y="0" width="{w}" height="{h}" href="data:image/png;base64,{b64_img}"/>')

        # 1. קרע נייר שמאלי עם שרטוט תוכנית קומה אדריכלית (Ripped Paper Blueprint Strip)
        tear_pts = []
        steps_t = 36
        for i in range(steps_t + 1):
            ty = (i / steps_t) * (h * 0.62)
            tx = (w * 0.28) + math.sin(i * 1.7) * 8.0 + ((i * 19) % 7 - 3)
            tear_pts.append(f"{tx:.1f},{ty:.1f}")
        tear_poly = f"0,0 " + " ".join(tear_pts) + f" 0,{h*0.62:.1f}"
        svg.append(f'<polygon points="{tear_poly}" fill="{strip_fill}" stroke="#1a1a1a" stroke-width="0.8"/>')
        svg.append(f'<g stroke="#222222" stroke-width="1.1" fill="none">')
        svg.append(f'<rect x="24" y="25" width="{w*0.18:.1f}" height="{h*0.42:.1f}"/>')
        svg.append(f'<line x1="24" y1="{h*0.18:.1f}" x2="{w*0.16:.1f}" y2="{h*0.18:.1f}"/>')
        svg.append(f'<line x1="24" y1="{h*0.32:.1f}" x2="{w*0.21:.1f}" y2="{h*0.32:.1f}"/>')
        svg.append(f'<circle cx="{w*0.15:.1f}" cy="{h*0.11:.1f}" r="12"/>')
        svg.append(f'<text x="{w*0.15:.1f}" y="{h*0.11 + 4:.1f}" fill="#222222" font-family="monospace" font-size="10" text-anchor="middle">N</text>')
        svg.append('</g>')

        # 2. רצועת ברקוד וקטורית בצד ימין למעלה (Vector Barcode Strip)
        bx, by, bw, bh = w * 0.68, h * 0.05, w * 0.25, h * 0.34
        svg.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{strip_fill}" stroke="#111111" stroke-width="0.8"/>')
        s_clean = (serial_code or "21038259053").strip()
        curr_y = by + 16
        idx_b = 0
        while curr_y < by + bh - 16:
            bar_h = 2 + ((ord(s_clean[idx_b % len(s_clean)]) + idx_b * 3) % 5)
            if idx_b % 2 == 0:
                svg.append(f'<rect x="{bx + 14:.1f}" y="{curr_y:.1f}" width="{bw - 42:.1f}" height="{bar_h}" fill="#111111"/>')
            curr_y += bar_h + 2.5
            idx_b += 1
        svg.append(f'<text x="{bx + bw - 12:.1f}" y="{by + bh/2:.1f}" fill="#111111" font-family="monospace" font-size="12" font-weight="bold" text-anchor="middle" transform="rotate(-90 {bx + bw - 12:.1f} {by + bh/2:.1f})">{s_clean}</text>')

        # 3. בלוק טקסט עריכתי ושרטוט בפינה הימנית התחתונה (Editorial Spec Block)
        ex, ey, ew, eh = w * 0.62, h * 0.64, w * 0.35, h * 0.32
        svg.append(f'<rect x="{ex:.1f}" y="{ey:.1f}" width="{ew:.1f}" height="{eh:.1f}" fill="{strip_fill}" stroke="#111111" stroke-width="0.8"/>')
        ed_lines = (editorial_text or "DIGICRAFT ARCHIVE // SPEC 04 // TACTILE ZINE EDITION").split()
        line_str = ""
        row_y = ey + 20
        for word in ed_lines:
            if len(line_str + " " + word) > 22:
                svg.append(f'<text x="{ex + 12:.1f}" y="{row_y:.1f}" fill="#1a1a1a" font-family="monospace" font-size="10" font-weight="bold">{line_str}</text>')
                row_y += 14
                line_str = word
            else:
                line_str = (line_str + " " + word).strip()
        if line_str:
            svg.append(f'<text x="{ex + 12:.1f}" y="{row_y:.1f}" fill="#1a1a1a" font-family="monospace" font-size="10" font-weight="bold">{line_str}</text>')

        svg.append('</svg>')
        svg_code = "\n".join(svg)

        svg_file, png_file = save_dual_outputs(svg_code, "xerox_collage", current_user, "Xerox Collage (קולאז' זין ודפוס)")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None


def embed_graphic(file_path, target_x, target_y, target_w, target_h, scale_pct=1.0, opacity=1.0):
    if not file_path:
        return ""
    final_w = target_w * scale_pct
    final_h = target_h * scale_pct
    final_x = target_x + (target_w - final_w) / 2
    final_y = target_y + (target_h - final_h) / 2

    if file_path.lower().endswith('.svg'):
        with open(file_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()
        svg_content = re.sub(r'<\?xml.*?\?>', '', svg_content).strip()
        return f'<g opacity="{opacity}"><svg x="{final_x}" y="{final_y}" width="{final_w}" height="{final_h}" preserveAspectRatio="xMidYMid slice">{svg_content}</svg></g>'
    else:
        with open(file_path, "rb") as img_f:
            b64_data = base64.b64encode(img_f.read()).decode('utf-8')
        ext = "png" if file_path.lower().endswith('.png') else "jpeg"
        return f'<image x="{final_x}" y="{final_y}" width="{final_w}" height="{final_h}" opacity="{opacity}" href="data:image/{ext};base64,{b64_data}" preserveAspectRatio="xMidYMid slice"/>'


def generate_custom_dieline(file_path, shape_type, w, h, d, graphic_mode, show_specs, current_user):
    try:
        margin = 40
        glue = 18
        cuts, folds = [], []

        if shape_type == "קופסת כרית (Pillow Box)":
            total_w = (w * 2) + glue
            total_h = h + (w * 0.8)
            canvas_w, canvas_h = total_w + margin * 2, total_h + margin * 2
            sx, sy = margin + glue, margin + (w * 0.4)

            folds.extend([f"M {sx} {sy} L {sx} {sy + h}", f"M {sx + w} {sy} L {sx + w} {sy + h}", f"M {sx + w*2} {sy} L {sx + w*2} {sy + h}"])
            arc_depth = w * 0.25
            for panel_x in [sx, sx + w]:
                folds.append(f"M {panel_x} {sy} Q {panel_x + w/2} {sy + arc_depth} {panel_x + w} {sy}")
                folds.append(f"M {panel_x} {sy + h} Q {panel_x + w/2} {sy + h - arc_depth} {panel_x + w} {sy + h}")
                cuts.append(f"M {panel_x} {sy} Q {panel_x + w/2} {sy - arc_depth*1.3} {panel_x + w} {sy}")
                cuts.append(f"M {panel_x} {sy + h} Q {panel_x + w/2} {sy + h + arc_depth*1.3} {panel_x + w} {sy + h}")

            cuts.append(f"M {sx} {sy} L {sx - glue} {sy + 15} L {sx - glue} {sy + h - 15} L {sx} {sy + h}")
            cuts.append(f"M {sx + w*2} {sy} L {sx + w*2} {sy + h}")
            art_x, art_y, art_w, art_h = sx, sy, w * 2, h

        elif shape_type == "פריסת משושה (Hexagonal Box)":
            side = w * 0.55
            apoth = side * 0.866
            total_w, total_h = (side * 6) + glue, h + (side * 3.5)
            canvas_w, canvas_h = total_w + margin * 2, total_h + margin * 2
            sx, sy = margin + glue, margin + side * 1.75

            for i in range(7):
                px = sx + (i * side)
                folds.append(f"M {px} {sy} L {px} {sy + h}")
                if i < 6:
                    folds.extend([f"M {px} {sy} L {px + side} {sy}", f"M {px} {sy + h} L {px + side} {sy + h}"])
                    if i % 2 == 0:
                        cuts.extend([f"M {px} {sy} L {px + side/2} {sy - apoth} L {px + side} {sy}", f"M {px} {sy + h} L {px + side/2} {sy + h + apoth} L {px + side} {sy + h}"])
                    else:
                        cuts.extend([f"M {px} {sy} L {px + side*0.15} {sy - apoth*1.2} L {px + side*0.85} {sy - apoth*1.2} L {px + side} {sy}", f"M {px} {sy + h} L {px + side*0.15} {sy + h + apoth*1.2} L {px + side*0.85} {sy + h + apoth*1.2} L {px + side} {sy + h}"])

            cuts.extend([f"M {sx} {sy} L {sx - glue} {sy + 12} L {sx - glue} {sy + h - 12} L {sx} {sy + h}", f"M {sx + side*6} {sy} L {sx + side*6} {sy + h}"])
            art_x, art_y, art_w, art_h = sx, sy, side * 6, h

        elif shape_type == "מארז נשיאה עם ידית (Handle Carrier)":
            handle_h, gable_h = 45, d * 0.7
            total_w, total_h = (w * 2) + (d * 2) + glue, h + gable_h + handle_h + d
            canvas_w, canvas_h = total_w + margin * 2, total_h + margin * 2
            sx, sy = margin + glue, margin + handle_h + gable_h

            x_pts = [sx, sx + w, sx + w + d, sx + w*2 + d, sx + w*2 + d*2]
            for xp in x_pts:
                folds.append(f"M {xp} {sy} L {xp} {sy + h}")
            folds.extend([f"M {sx} {sy} L {x_pts[-1]} {sy}", f"M {sx} {sy + h} L {x_pts[-1]} {sy + h}"])

            for p_start in [x_pts[0], x_pts[2]]:
                folds.append(f"M {p_start} {sy - gable_h} L {p_start + w} {sy - gable_h}")
                cuts.append(f"M {p_start} {sy} L {p_start} {sy - gable_h} L {p_start + 15} {sy - gable_h - handle_h} L {p_start + w - 15} {sy - gable_h - handle_h} L {p_start + w} {sy - gable_h} L {p_start + w} {sy}")
                hw = w * 0.45
                hx, hy = p_start + (w - hw) / 2, sy - gable_h - handle_h * 0.65
                cuts.append(f"M {hx} {hy} L {hx + hw} {hy} L {hx + hw} {hy + 14} L {hx} {hy + 14} Z")

            for s_start in [x_pts[1], x_pts[3]]:
                cuts.append(f"M {s_start} {sy} L {s_start + d/2} {sy - gable_h} L {s_start + d} {sy}")
                folds.append(f"M {s_start + d/2} {sy} L {s_start + d/2} {sy - gable_h}")

            cuts.extend([f"M {sx} {sy} L {sx - glue} {sy + 10} L {sx - glue} {sy + h - 10} L {sx} {sy + h}", f"M {sx} {sy + h} L {sx} {sy + h + d*0.8} L {x_pts[-1]} {sy + h + d*0.8} L {x_pts[-1]} {sy}"])
            art_x, art_y, art_w, art_h = sx, sy - gable_h, total_w - glue, h + gable_h

        else:
            tuck, dust = 20, d * 0.65
            total_w, total_h = glue + (d * 2) + (w * 2), h + (tuck * 2) + (d * 2)
            canvas_w, canvas_h = total_w + margin * 2, total_h + margin * 2
            sx, sy = margin + glue, margin + tuck + d

            x_pts = [sx, sx + d, sx + d + w, sx + d*2 + w, sx + d*2 + w*2]
            for xp in x_pts:
                folds.append(f"M {xp} {sy} L {xp} {sy + h}")
            folds.extend([f"M {sx} {sy} L {x_pts[-1]} {sy}", f"M {sx} {sy + h} L {x_pts[-1]} {sy + h}", f"M {x_pts[1]} {sy - d} L {x_pts[2]} {sy - d}", f"M {x_pts[3]} {sy + h + d} L {x_pts[4]} {sy + h + d}"])

            cuts.extend([
                f"M {sx} {sy} L {sx - glue} {sy + 8} L {sx - glue} {sy + h - 8} L {sx} {sy + h}",
                f"M {sx} {sy} L {sx} {sy - dust} L {x_pts[1]} {sy - dust} L {x_pts[1]} {sy}",
                f"M {x_pts[1]} {sy} L {x_pts[1]} {sy - d} L {x_pts[1]+6} {sy - d - tuck} L {x_pts[2]-6} {sy - d - tuck} L {x_pts[2]} {sy - d} L {x_pts[2]} {sy}",
                f"M {x_pts[2]} {sy} L {x_pts[2]} {sy - dust} L {x_pts[3]} {sy - dust} L {x_pts[3]} {sy}",
                f"M {x_pts[3]} {sy} L {x_pts[4]} {sy} L {x_pts[4]} {sy + h}",
                f"M {x_pts[4]} {sy + h} L {x_pts[4]} {sy + h + d} L {x_pts[4]-6} {sy + h + d + tuck} L {x_pts[3]+6} {sy + h + d + tuck} L {x_pts[3]} {sy + h + d} L {x_pts[3]} {sy + h}",
                f"M {x_pts[2]} {sy + h} L {x_pts[2]} {sy + h + dust} L {x_pts[1]} {sy + h + dust} L {x_pts[1]} {sy + h}",
                f"M {sx} {sy + h} L {x_pts[1]} {sy + h}",
                f"M {x_pts[2]} {sy + h} L {x_pts[3]} {sy + h}"
            ])
            win_w, win_h = w * 0.55, h * 0.45
            win_x, win_y = x_pts[1] + (w - win_w) / 2, sy + (h - win_h) / 2
            cuts.append(f"M {win_x} {win_y} L {win_x + win_w} {win_y} L {win_x + win_w} {win_y + win_h} L {win_x} {win_y + win_h} Z")
            art_x, art_y, art_w, art_h = sx, sy, total_w - glue, h

        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas_w} {canvas_h}" width="100%" height="100%">']
        svg.append('''<style>
            .cut { stroke: #ff1744; stroke-width: 1.5; fill: none; stroke-linejoin: round; }
            .fold { stroke: #00e5ff; stroke-width: 1.2; stroke-dasharray: 5,4; fill: none; }
            .spec { stroke: #888888; stroke-width: 0.6; fill: none; }
            .spec-txt { fill: #777777; font-family: monospace; font-size: 8px; text-anchor: middle; }
        </style>''')
        svg.append(f'<rect x="0" y="0" width="{canvas_w}" height="{canvas_h}" fill="#141414"/>')

        svg.append('<g stroke="#222222" stroke-width="0.5">')
        for gx in range(0, int(canvas_w), 20):
            svg.append(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{canvas_h}"/>')
        for gy in range(0, int(canvas_h), 20):
            svg.append(f'<line x1="0" y1="{gy}" x2="{canvas_w}" y2="{gy}"/>')
        svg.append('</g>')

        if file_path:
            svg.append('<g id="Uploaded_Artwork">')
            if graphic_mode == "פילטר אסתטי מלא (תמונה על כל הפריסה)":
                svg.append(embed_graphic(file_path, margin/2, margin/2, canvas_w - margin, canvas_h - margin, 1.0, opacity=0.85))
            else:
                svg.append(embed_graphic(file_path, art_x, art_y, art_w, art_h, 0.95, opacity=0.9))
            svg.append('</g>')

        svg.append('<g id="Fold_Lines">' + "".join([f'<path class="fold" d="{f_p}"/>' for f_p in folds]) + '</g>')
        svg.append('<g id="Cut_Lines">' + "".join([f'<path class="cut" d="{c_p}"/>' for c_p in cuts]) + '</g>')

        if show_specs:
            svg.append('<g id="Tech_Specs">')
            svg.append(f'<line class="spec" x1="{art_x}" y1="{canvas_h - 15}" x2="{art_x + art_w}" y2="{canvas_h - 15}"/>')
            svg.append(f'<text class="spec-txt" x="{art_x + art_w/2}" y="{canvas_h - 6}">SPAN: {int(art_w)}mm // H: {int(h)}mm // D: {int(d)}mm // CUT: #FF1744 // CREASE: #00E5FF</text>')
            svg.append('</g>')

        svg.append('</svg>')
        svg_code = "\n".join(svg)

        svg_file, png_file = save_dual_outputs(svg_code, "dieline_package", current_user, f"פריסת אריזה: {shape_type}")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None


def generate_print_marks(file_path, artboard_w, artboard_h, bleed, style_theme, current_user):
    try:
        margin = 35
        canvas_w, canvas_h = artboard_w + (margin * 2), artboard_h + (margin * 2)
        x1, y1 = margin, margin
        x2, y2 = margin + artboard_w, margin + artboard_h
        bx1, by1 = x1 - bleed, y1 - bleed
        bx2, by2 = x2 + bleed, y2 + bleed

        bg_col = "#111111" if style_theme == "Dark Cyber / Acid Print" else "#ffffff"
        mark_col = "#00ffaa" if style_theme == "Dark Cyber / Acid Print" else "#000000"
        bleed_col = "#ff0055"

        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas_w} {canvas_h}" width="100%" height="100%">']
        svg.append(f'<style>.reg {{ stroke: {mark_col}; stroke-width: 0.8; fill: none; }} .bleed {{ stroke: {bleed_col}; stroke-width: 0.7; stroke-dasharray: 4,3; fill: none; }} .txt {{ fill: {mark_col}; font-family: monospace; font-size: 6px; }}</style>')
        svg.append(f'<rect x="0" y="0" width="{canvas_w}" height="{canvas_h}" fill="{bg_col}"/>')

        if file_path:
            svg.append('<g id="Print_Artwork">' + embed_graphic(file_path, bx1, by1, bx2 - bx1, by2 - by1, 1.0, opacity=1.0) + '</g>')

        svg.append(f'<rect class="bleed" x="{bx1}" y="{by1}" width="{bx2 - bx1}" height="{by2 - by1}"/>')

        c_len, c_gap = 12, 3
        svg.append('<g id="Registration_Overlay">')
        for cx, cy, dx, dy in [(x1, y1, -1, -1), (x2, y1, 1, -1), (x1, y2, -1, 1), (x2, y2, 1, 1)]:
            svg.append(f'<line class="reg" x1="{cx}" y1="{cy + dy*c_gap}" x2="{cx}" y2="{cy + dy*(c_gap + c_len)}"/>')
            svg.append(f'<line class="reg" x1="{cx + dx*c_gap}" y1="{cy}" x2="{cx + dx*(c_gap + c_len)}" y2="{cy}"/>')

        mid_x, mid_y = margin + (artboard_w / 2), margin + (artboard_h / 2)
        for tx, ty in [(mid_x, y1 - 16), (mid_x, y2 + 16), (x1 - 16, mid_y), (x2 + 16, mid_y)]:
            svg.append(f'<circle class="reg" cx="{tx}" cy="{ty}" r="5"/>')
            svg.append(f'<circle class="reg" cx="{tx}" cy="{ty}" r="2"/>')
            svg.append(f'<line class="reg" x1="{tx - 8}" y1="{ty}" x2="{tx + 8}" y2="{ty}"/>')
            svg.append(f'<line class="reg" x1="{tx}" y1="{ty - 8}" x2="{tx}" y2="{ty + 8}"/>')

        bar_Colors = ["#00ffff", "#ff00ff", "#ffff00", "#000000", "#333333", "#777777", "#bbbbbb", "#ffffff"]
        for idx, col in enumerate(bar_Colors):
            svg.append(f'<rect x="{x1 + idx*8}" y="{y1 - 18}" width="7" height="5" fill="{col}" stroke="{mark_col}" stroke-width="0.3"/>')

        svg.append(f'<text class="txt" x="{x1}" y="{y2 + 18}">DIGICRAFT MATRIX // REG_SPEC: {int(artboard_w)}x{int(artboard_h)}MM // BLEED: {bleed}MM</text>')
        svg.append('</g></svg>')

        svg_code = "\n".join(svg)
        svg_file, png_file = save_dual_outputs(svg_code, "registration_marks", current_user, "סימני רישום ודפוס")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None


# ==========================================
# 9. אגף ה': Gentype Studio (עם בורר פונטים בעברית ובאנגלית!)
# ==========================================
def generate_gentype_typography(text_input, font_choice, style_preset, custom_theme, engine_mode, primary_col, accent_col, current_user):
    try:
        text_clean = (text_input or "DIGICRAFT").strip()
        font_family = font_choice.split(" (")[0].strip()
        w, h = 900, 420

        if engine_mode == "Gemini AI SVG Typography (דורש מפתח API בשרת)" and os.environ.get("GEMINI_API_KEY") and genai:
            model = genai.GenerativeModel('gemini-2.5-pro')
            prompt = f"""
            You are a master computational typographer and generative SVG artist.
            Create an expressive vector SVG typographic artwork spelling the exact text: "{text_clean}".
            Font Family to use: "{font_family}". Visual Style Preset: {style_preset}. Additional theme details: {custom_theme}.
            Color Palette: Background #121212, Primary {primary_col}, Accent {accent_col}.
            Output ONLY valid raw <svg viewBox="0 0 {w} {h}">...</svg> code without markdown backticks.
            """
            response = model.generate_content(prompt)
            svg_code = re.sub(r'```(?:xml|svg)?\n|```', '', response.text).strip()
        else:
            svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" height="100%">']
            svg.append(f'''<defs>
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@700;800&amp;family=Cinzel:wght@700;900&amp;family=Frank+Ruhl+Libre:wght@700;900&amp;family=Heebo:wght@700;900&amp;family=Orbitron:wght@700;900&amp;family=Playfair+Display:ital,wght@0,800;1,800&amp;family=Rubik:wght@700;900&amp;family=Space+Mono:wght@700&amp;family=Syne:wght@700;800&amp;display=swap');
                </style>
                <linearGradient id="chromeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="{primary_col}"/>
                    <stop offset="50%" stop-color="#ffffff"/>
                    <stop offset="100%" stop-color="{accent_col}"/>
                </linearGradient>
            </defs>''')
            svg.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="#121212"/>')

            num_chars = max(1, len(text_clean))
            step_x = (w - 120) / num_chars
            font_sz = int(min(175, step_x * 1.15))

            for idx, ch in enumerate(text_clean):
                cx = 60 + step_x * (idx + 0.5)
                cy = h / 2

                if style_preset == "Y2K Liquid Chrome (כרום נוזלי ותלת-ממד)":
                    for layer in range(12, 0, -1):
                        off = layer * 2.2
                        col = accent_col if layer % 2 == 0 else "#2a2a35"
                        svg.append(f'<text x="{cx + off:.1f}" y="{cy + off:.1f}" font-family="\'{font_family}\', sans-serif" font-weight="900" font-size="{font_sz}" fill="none" stroke="{col}" stroke-width="2" text-anchor="middle" dominant-baseline="central">{ch}</text>')
                    svg.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-family="\'{font_family}\', sans-serif" font-weight="900" font-size="{font_sz}" fill="url(#chromeGrad)" stroke="#ffffff" stroke-width="1.5" text-anchor="middle" dominant-baseline="central">{ch}</text>')

                elif style_preset == "Cyber Stitch & Loom (רקמה ורשת דיגיטלית)":
                    for r_off in range(-40, 45, 10):
                        svg.append(f'<line x1="{cx - step_x*0.4:.1f}" y1="{cy + r_off:.1f}" x2="{cx + step_x*0.4:.1f}" y2="{cy - r_off:.1f}" stroke="{accent_col}" stroke-width="0.8"/>')
                    svg.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-family="\'{font_family}\', monospace" font-weight="800" font-size="{font_sz}" fill="none" stroke="{primary_col}" stroke-width="4" stroke-dasharray="6,4" text-anchor="middle" dominant-baseline="central">{ch}</text>')
                    svg.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-family="\'{font_family}\', monospace" font-weight="800" font-size="{font_sz}" fill="{primary_col}" opacity="0.85" text-anchor="middle" dominant-baseline="central">{ch}</text>')

                else:
                    for b in range(10):
                        ang = (2 * math.pi * b) / 10
                        rx = cx + math.cos(ang) * (font_sz * 0.55)
                        ry = cy + math.sin(ang) * (font_sz * 0.55)
                        svg.append(f'<path d="M {cx} {cy} Q {cx + 25} {cy - 25} {rx:.1f} {ry:.1f}" stroke="{accent_col}" stroke-width="1.5" fill="none"/>')
                        svg.append(f'<circle cx="{rx:.1f}" cy="{ry:.1f}" r="3.5" fill="{primary_col}"/>')
                    svg.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-family="\'{font_family}\', serif" font-weight="800" font-size="{font_sz}" fill="{primary_col}" stroke="#121212" stroke-width="2" text-anchor="middle" dominant-baseline="central">{ch}</text>')

            svg.append(f'<text x="{w/2}" y="{h - 16}" fill="#777777" font-family="monospace" font-size="10" text-anchor="middle">GENTYPE_STUDIO // FONT: {font_family.upper()} // STYLE: {style_preset}</text>')
            svg.append('</svg>')
            svg_code = "\n".join(svg)

        svg_file, png_file = save_dual_outputs(svg_code, "gentype_studio", current_user, f"Gentype ({font_family}): {text_clean}")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None
        # ==============================================================================
# DIGICRAFT MATRIX PALACE - PART 5 OF 5
# Custom Stitch CSS, Complete 7-Wing Interface, Auto-Gallery Wiring & Render Launch
# ==============================================================================

STITCH_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;600;800&family=Space+Mono:wght@400;700&display=swap');

body, .gradio-container {
    background-color: #0f0f11 !important;
    color: #eaeaea !important;
    font-family: 'Heebo', sans-serif !important;
    direction: rtl !important;
}

.stitch-header {
    background: linear-gradient(135deg, #18181c 0%, #121215 100%);
    border: 1px solid #2c2c34;
    border-right: 4px solid #e86c52;
    border-radius: 10px;
    padding: 16px 24px;
    margin-bottom: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.stitch-title {
    font-size: 24px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.5px;
    margin: 0;
}

.stitch-subtitle {
    font-family: 'Space Mono', monospace;
    font-size: 12px;
    color: #e86c52;
    margin-top: 4px;
}

.telemetry-box {
    background: #16161a;
    border: 1px solid #2b2b33;
    border-radius: 8px;
    padding: 12px 16px;
    font-family: 'Space Mono', 'Heebo', monospace;
    font-size: 12px;
    color: #c9c9d1;
    margin-top: 10px;
}

.canvas-preview {
    background: #141417;
    border: 1px solid #2e2e38;
    border-radius: 10px;
    padding: 16px;
    max-width: 640px;
    margin: 0 auto;
    box-shadow: inset 0 0 24px rgba(0,0,0,0.6);
}

.swatch-panel {
    background: #16161a;
    border: 1px solid #2c2c35;
    border-radius: 10px;
    padding: 14px;
    margin-top: 12px;
}

.swatch-title {
    font-family: 'Space Mono', 'Heebo', monospace;
    font-size: 12px;
    font-weight: 700;
    color: #d4a359;
    margin-bottom: 10px;
    border-bottom: 1px solid #26262e;
    padding-bottom: 6px;
}

.swatch-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(195px, 1fr));
    gap: 8px;
}

.swatch-card {
    display: flex;
    align-items: center;
    background: #1f1f25;
    border: 1px solid #32323c;
    border-radius: 6px;
    padding: 6px 8px;
    gap: 10px;
}

.swatch-box {
    width: 32px;
    height: 32px;
    border-radius: 4px;
    border: 1px solid rgba(255,255,255,0.25);
    flex-shrink: 0;
}

.swatch-info {
    display: flex;
    flex-direction: column;
    font-family: 'Space Mono', 'Heebo', monospace;
    line-height: 1.25;
}

.swatch-hex {
    font-size: 12px;
    font-weight: 700;
    color: #ffffff;
}

.swatch-dmc {
    font-size: 11px;
    color: #e86c52;
}

.swatch-meta {
    font-size: 10px;
    color: #9999a5;
}

button.primary {
    background: linear-gradient(90deg, #e86c52 0%, #d48a42 100%) !important;
    color: #111111 !important;
    font-weight: 800 !important;
    border: none !important;
}
"""


def on_app_load(current_user):
    record_visit()
    g_imgs, g_files, g_html = get_history_display(current_user)
    adm_html = get_admin_dashboard(current_user)
    return g_imgs, g_files, g_html, adm_html


# ==========================================
# בניית הארמון המאוחד: DigiCraft Matrix (7 אגפים)
# ==========================================
with gr.Blocks(title="DigiCraft Matrix Palace", theme=gr.themes.Base(), css=STITCH_CSS) as master_studio:

    current_user_state = gr.State("mai")

    gr.HTML("""
    <div class="stitch-header">
        <div>
            <h1 class="stitch-title">🏰 DIGICRAFT MATRIX // COMPUTATIONAL DESIGN PALACE</h1>
            <div class="stitch-subtitle">JACQUARD · TELETEXT · GLYPH GRID · CUTOUT STL · RASTER LINES · LIQUID SCREEN · XEROX ZINE · GENTYPE</div>
        </div>
        <div style="text-align:left; font-family:'Space Mono', monospace; font-size:11px; color:#888;">
            <div>RENDER_ENGINE: ONLINE</div>
            <div style="color:#4caf50;">● AUTO_ARCHIVE: 7 DAYS</div>
        </div>
    </div>
    """)

    with gr.Row():
        user_status_badge = gr.Textbox(
            value="🟢 מחובר/ת: mai (מנהלת מערכת - Admin) — שמירה אוטומטית בגלריה פעילה",
            label="סטטוס חיבור נוכחי",
            interactive=False,
            scale=3
        )
        guest_quick_btn = gr.Button("👤 מעבר מהיר למצב אורח", scale=1)

    with gr.Accordion("🔐 כניסת משתמשים / הרשמה / שחזור סיסמה בדוא\"ל (לחצי לפתיחה)", open=False):
        auth_feedback = gr.HTML()
        with gr.Tabs():
            with gr.Tab("התחברות (Login)"):
                with gr.Row():
                    login_user = gr.Textbox(label="שם משתמש", value="mai")
                    login_pass = gr.Textbox(label="סיסמה", type="password", value="DigiCraft2026")
                    login_btn = gr.Button("התחבר/י", variant="primary")
            with gr.Tab("הרשמת משתמש חדש"):
                with gr.Row():
                    reg_user = gr.Textbox(label="בחירת שם משתמש")
                    reg_email = gr.Textbox(label="כתובת דוא\"ל (לשחזור סיסמה)")
                    reg_pass = gr.Textbox(label="בחירת סיסמה", type="password")
                    reg_btn = gr.Button("צור חשבון והתחבר", variant="primary")
            with gr.Tab("שחזור סיסמה באמצעות דוא\"ל"):
                with gr.Row():
                    rec_email = gr.Textbox(label="הזיני את כתובת הדוא\"ל המשויכת לחשבון")
                    rec_send_btn = gr.Button("שלח קוד שחזור לדוא\"ל")
                with gr.Row():
                    rec_code = gr.Textbox(label="קוד אימות (6 ספרות)")
                    rec_new_pass = gr.Textbox(label="סיסמה חדשה", type="password")
                    rec_reset_btn = gr.Button("אפס סיסמה", variant="primary")

    with gr.Tabs():

        # ==========================================
        # אגף א': טקסטיל, ז'קארד, Teletext ו-Glyph Grid
        # ==========================================
        with gr.Tab("🧶 אגף א': טקסטיל, ז'קארד ומטריצות"):
            with gr.Row():
                with gr.Column(scale=1):
                    r1_img = gr.Image(label="מקור קלט תמונה (תומך בצילומי מסך, טקסט ושקיפויות)", type="filepath")
                    r1_style = gr.Radio(
                        choices=[
                            "אריגת ז'קארד (Jacquard Weave)",
                            "Teletext Pattern (פסי שידור ורטרו CRT)",
                            "Glyph Grid (מטריצת קוד ובלוקים)",
                            "רקמת גובלן / שטיח (Gobelin Tapestry)",
                            "רקמת איקסים (Cross-Stitch)",
                            "סריגה (Knitting)",
                            "ASCII Art (טיפוגרפיה)",
                            "Dotted Halftone (נקודות)"
                        ],
                        value="אריגת ז'קארד (Jacquard Weave)",
                        label="דפוס שזירה / המרה וקטורית"
                    )
                    r1_grid = gr.Slider(minimum=10, maximum=140, step=2, value=56, label="צפיפות רשת דגימה (Grid Size)")
                    r1_colors = gr.Slider(minimum=2, maximum=20, step=1, value=8, label="הגבלת פלטת חוטים (DMC Floss Colors)")
                    r1_btn = gr.Button("⚡ הפעל סינתזת מטריצה (נשמר אוטומטית בגלריה)", variant="primary")

                with gr.Column(scale=1):
                    r1_preview = gr.HTML(label="תצוגת השוואה וקטורית")
                    r1_palette = gr.HTML(label="פלטת צבעים וחוטים")
                    with gr.Row():
                        r1_out_svg = gr.File(label="📥 הורדת קובץ וקטורי (SVG)")
                        r1_out_png = gr.File(label="🖼️ הורדת תמונה חדה (PNG)")

        # ==========================================
        # אגף ב': עומק, Heatmap, Raster Lines, PBR ו-STL לתלת-ממד
        # ==========================================
        with gr.Tab("⛰️ אגף ב': עומק, Heatmap, Raster Lines ו-STL"):
            with gr.Tabs():

                with gr.Tab("🧊 מעבדת PBR Height Map & ייצוא STL (ללא משטח ריבועי)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            pbr_img = gr.Image(label="העלאת תמונה / טקסטורה להמרה לתבליט תלת-ממד", type="filepath")
                            with gr.Row():
                                pbr_cutout = gr.Checkbox(label="✂️ חיתוך צורני ללא משטח ריבועי (Silhouette Cutout)", value=True)
                                pbr_thresh = gr.Slider(minimum=0.02, maximum=0.45, step=0.02, value=0.10, label="סף חיתוך רקע (Cutoff Threshold)")
                            with gr.Row():
                                pbr_res = gr.Slider(minimum=40, maximum=160, step=10, value=100, label="רזולוציית רשת תלת-ממד (Mesh Grid)")
                                pbr_smooth = gr.Slider(minimum=0.0, maximum=5.0, step=0.5, value=1.0, label="החלקת משטח (Gaussian Smooth)")
                            with gr.Row():
                                pbr_contrast = gr.Slider(minimum=0.5, maximum=3.0, step=0.1, value=1.3, label="עוצמת קונטרסט עומק (PBR Contrast)")
                                pbr_invert = gr.Checkbox(label="היפוך גבהים (Invert Black/White)", value=False)
                            with gr.Row():
                                pbr_size = gr.Slider(minimum=30, maximum=220, step=5, value=100, label="רוחב אריח/אובייקט (מ\"מ)")
                                pbr_base = gr.Slider(minimum=0.4, maximum=8.0, step=0.2, value=1.6, label="עובי בסיס (מ\"מ)")
                                pbr_relief = gr.Slider(minimum=0.5, maximum=10.0, step=0.2, value=3.0, label="גובה תבליט הטקסטורה (מ\"מ)")
                            pbr_btn = gr.Button("🔨 ייצר מפת גובה (PBR) + קובץ STL מוכן ל-Bambu Studio", variant="primary")

                        with gr.Column(scale=1):
                            pbr_specs = gr.HTML()
                            with gr.Row():
                                pbr_hm_prev = gr.Image(label="מפת גובה (Non-Color Height Map לבלנדר)")
                                pbr_shade_prev = gr.Image(label="הדמיית תאורה וצל (Relief Preview)")
                            pbr_stl_viewer = gr.Model3D(label="תצוגה תלת-ממדית חיה מוארת (סובבי עם העכבר)")
                            with gr.Row():
                                pbr_out_png = gr.File(label="🖼️ הורדת Height Map (PNG לבלנדר)")
                                pbr_out_stl = gr.File(label="📦 הורדת קובץ 3D STL (ישירות ל-Bambu Lab)")

                with gr.Tab("🔥 Heatmap + Stipple Duotone & Thermal Noise"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            hm_img = gr.Image(label="העלאת תמונה למיפוי חום, נקודות או הילה תרמית", type="filepath")
                            hm_style = gr.Radio(
                                choices=[
                                    "Stipple Duotone (הילת ענבר וגרעיניות נייר קרם)",
                                    "Thermal Noise (ניאון אסיד מג'נטה-מנטה)",
                                    "שכבות איזותרמיות (Isothermal Contours)",
                                    "מטריצת תאים תרמית (Thermal Matrix Grid)",
                                    "בועות קרינה פרמטריות (Thermal Nodes)"
                                ],
                                value="Stipple Duotone (הילת ענבר וגרעיניות נייר קרם)",
                                label="סגנון מפת חום / הדפס"
                            )
                            hm_pal = gr.Dropdown(
                                choices=[
                                    "Cyber Thermal (סגול-אדום-צהוב ליבון)",
                                    "Stitch Amber (פחם-נחושת-זהב חם)",
                                    "Acid Infrared (ירוק-ליים-ציאן תעשייתי)",
                                    "Arctic Blue-Red (כחול קוטבי-אדום חם)"
                                ],
                                value="Cyber Thermal (סגול-אדום-צהוב ליבון)",
                                label="פלטת צבעים (למצבי שכבות/מטריצה/בועות)"
                            )
                            hm_res = gr.Slider(minimum=20, maximum=100, step=5, value=55, label="צפיפות רשת (למצב מטריצה/בועות)")
                            hm_blur = gr.Slider(minimum=1.0, maximum=12.0, step=0.5, value=4.0, label="רדיוס הילה / מיזוג חום (Aura Diffusion)")
                            hm_btn = gr.Button("🌡️ ייצר מפת חום / Stipple (SVG + PNG)", variant="primary")

                        with gr.Column(scale=1):
                            hm_prev = gr.HTML(label="תצוגה מקדימה")
                            hm_swatches = gr.HTML(label="ספקטרום צבעים")
                            with gr.Row():
                                hm_out_svg = gr.File(label="📥 הורדת SVG")
                                hm_out_png = gr.File(label="🖼️ הורדת PNG")

                with gr.Tab("⚡ Raster Lines (גלי סריקה זוהרים + STL לתלת-ממד)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            rl_img = gr.Image(label="העלאת תמונה ליצירת קווי סריקה טופוגרפיים", type="filepath")
                            rl_lines = gr.Slider(minimum=30, maximum=140, step=5, value=85, label="צפיפות קווי סריקה (Scanline Count)")
                            rl_amp = gr.Slider(minimum=10, maximum=90, step=2, value=42, label="גובה עיקול הגל (Elevation Amplitude)")
                            with gr.Row():
                                rl_line_col = gr.ColorPicker(value="#e0ffff", label="צבע ליבת הקו")
                                rl_glow_col = gr.ColorPicker(value="#00e5ff", label="צבע הילת ניאון")
                            rl_btn = gr.Button("⚡ ייצר Raster Lines (SVG + PNG + 3D STL)", variant="primary")

                        with gr.Column(scale=1):
                            rl_prev = gr.HTML(label="תצוגת Raster Lines")
                            rl_stl_view = gr.Model3D(label="הדמיית תבליט תלת-ממדי (STL)")
                            with gr.Row():
                                rl_out_svg = gr.File(label="📥 הורדת SVG")
                                rl_out_png = gr.File(label="🖼️ הורדת PNG")
                                rl_out_stl = gr.File(label="📦 הורדת 3D STL")

                with gr.Tab("🗺️ קווי גובה טופוגרפיים (Isolines)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r2_c_img = gr.Image(label="העלאת תמונה", type="filepath")
                            r2_c_levels = gr.Slider(minimum=3, maximum=30, step=1, value=14, label="מספר שכבות גובה (Levels)")
                            r2_c_blur = gr.Slider(minimum=1, maximum=15, step=0.5, value=4.5, label="החלקת צורות אורגניות (Blur)")
                            with gr.Row():
                                r2_c_stroke = gr.ColorPicker(value="#e86c52", label="צבע קווי גובה")
                                r2_c_bg = gr.ColorPicker(value="#141414", label="צבע רקע")
                            r2_c_btn = gr.Button("ייצר קווי מתאר טופוגרפיים (SVG + PNG)", variant="primary")
                        with gr.Column(scale=1):
                            r2_c_prev = gr.HTML(label="תצוגה מקדימה")
                            with gr.Row():
                                r2_c_svg = gr.File(label="📥 הורדת SVG")
                                r2_c_png = gr.File(label="🖼️ הורדת PNG")

                with gr.Tab("🌊 טקסטורות עומק גיאומטריות (ללא צורך ב-API)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r2_d_img = gr.Image(label="העלאת תמונה", type="filepath")
                            r2_d_grid = gr.Slider(minimum=10, maximum=45, step=1, value=24, label="צפיפות רשת הגיאומטריה")
                            r2_d_shape = gr.Dropdown(
                                choices=[
                                    "Circles (מעגלים פרמטריים)",
                                    "Squares (ריבועים מדורגים)",
                                    "Hexagons (משושים גיאומטריים)",
                                    "Cross / Lines (צלבים וקווים)"
                                ],
                                value="Circles (מעגלים פרמטריים)",
                                label="צורת בסיס"
                            )
                            with gr.Row():
                                r2_d_fg = gr.ColorPicker(value="#00e5ff", label="צבע אלמנטים")
                                r2_d_bg = gr.ColorPicker(value="#141417", label="צבע רקע")
                            r2_d_btn = gr.Button("ייצר טקסטורת עומק (SVG + PNG)", variant="primary")
                        with gr.Column(scale=1):
                            r2_d_prev = gr.HTML(label="תצוגה מקדימה")
                            with gr.Row():
                                r2_d_svg = gr.File(label="📥 הורדת SVG")
                                r2_d_png = gr.File(label="🖼️ הורדת PNG")

        # ==========================================
        # אגף ג': מחוללים מתמטיים (3D Voxel, Liquid Screen, Wave, Guilloche)
        # ==========================================
        with gr.Tab("📐 אגף ג': מחוללים מתמטיים (3D Voxel, Liquid Screen, Wave)"):
            with gr.Tabs():
                with gr.Tab("🧊 פסל אדריכלי תלת-ממדי אינטראקטיבי (3D Voxel Art)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r3_i_img = gr.Image(label="העלאת תמונה", type="filepath")
                            r3_i_bg_mode = gr.Radio(
                                choices=[
                                    "הסר רקע כהה ובהיר אוטומטית (ללא משטח ריבועי)",
                                    "הסר רקע כהה בלבד (כמו בצילום תרמי)",
                                    "הסר רקע בהיר בלבד",
                                    "השאר את כל המשטח"
                                ],
                                value="הסר רקע כהה ובהיר אוטומטית (ללא משטח ריבועי)",
                                label="סינון משטח רקע"
                            )
                            r3_i_w = gr.Slider(minimum=12, maximum=75, step=1, value=38, label="רזולוציה (קוביות לרוחב)")
                            r3_i_ext = gr.Slider(minimum=5, maximum=120, step=5, value=45, label="בליטה תלת-ממדית (Z-Extrusion)")
                            r3_i_gap = gr.Slider(minimum=0, maximum=4, step=0.5, value=0.8, label="ריווח בין עמודים")
                            r3_i_btn = gr.Button("🧊 ייצר פסל ווקסלים אינטראקטיבי (3D STL + SVG + PNG)", variant="primary")
                        with gr.Column(scale=1):
                            r3_i_stl_view = gr.Model3D(label="תצוגת 3D אינטראקטיבית של הקוביות (סובבי עם העכבר)")
                            r3_i_prev = gr.HTML(label="תצוגה איזומטרית וקטורית (2D SVG)")
                            r3_i_swatches = gr.HTML(label="דוגמיות צבע")
                            with gr.Row():
                                r3_i_svg = gr.File(label="📥 הורדת SVG")
                                r3_i_png = gr.File(label="🖼️ הורדת PNG")
                                r3_i_stl = gr.File(label="📦 הורדת 3D STL")

                with gr.Tab("💧 Liquid Screen (רשת תת-פיקסלים ונזילה אנכית)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            ls_img = gr.Image(label="העלאת תמונה / דמות בתנועה", type="filepath")
                            ls_drip = gr.Slider(minimum=15, maximum=160, step=5, value=75, label="אורך נזילת פיקסלים כלפי מטה (Pixel Melt)")
                            ls_glow = gr.Slider(minimum=0.8, maximum=3.2, step=0.1, value=1.8, label="עוצמת הילת מסך (Subpixel Glow)")
                            ls_tint = gr.Radio(
                                choices=[
                                    "Electric Cobalt & Violet (כחול חשמלי וסגול)",
                                    "Cyber Cyan & Emerald (ציאן ואמרלד)",
                                    "Neon Magenta & Rose (מג'נטה ורוד ניאון)"
                                ],
                                value="Electric Cobalt & Violet (כחול חשמלי וסגול)",
                                label="גוון הילת המסך"
                            )
                            ls_btn = gr.Button("💧 ייצר אפקט Liquid Screen (SVG + PNG)", variant="primary")
                        with gr.Column(scale=1):
                            ls_prev = gr.HTML(label="תצוגה מקדימה")
                            with gr.Row():
                                ls_out_svg = gr.File(label="📥 הורדת SVG")
                                ls_out_png = gr.File(label="🖼️ הורדת PNG")

                with gr.Tab("〰️ גלי קול (Waveform)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r3_w_img = gr.Image(label="העלאת תמונה", type="filepath")
                            r3_w_lines = gr.Slider(minimum=20, maximum=150, step=1, value=65, label="מספר שורות (צפיפות)")
                            r3_w_amp = gr.Slider(minimum=5, maximum=100, step=1, value=32, label="גובה הגל")
                            r3_w_col = gr.ColorPicker(value="#1a1a1a", label="צבע הקווים")
                            r3_w_btn = gr.Button("ייצר וקטור גלים (SVG + PNG)", variant="primary")
                        with gr.Column(scale=1):
                            r3_w_prev = gr.HTML(label="תצוגה מקדימה")
                            with gr.Row():
                                r3_w_svg = gr.File(label="📥 הורדת SVG")
                                r3_w_png = gr.File(label="🖼️ הורדת PNG")

                with gr.Tab("🌸 גיליושה אדפטיבית (Adaptive Geometry)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r3_g_img = gr.Image(label="העלאת תמונה", type="filepath")
                            r3_g_col = gr.Slider(minimum=2, maximum=12, step=1, value=5, label="מספר טקסטורות (צבעים)")
                            r3_g_R = gr.Slider(minimum=100, maximum=400, step=1, value=250, label="רדיוס מאסטר (Master R)")
                            r3_g_rot = gr.Slider(minimum=10, maximum=250, step=1, value=140, label="צפיפות סיבובים")
                            r3_g_btn = gr.Button("ייצר רוזטה אדפטיבית (SVG + PNG)", variant="primary")
                        with gr.Column(scale=1):
                            r3_g_prev = gr.HTML(label="תצוגה מקדימה")
                            r3_g_swatches = gr.HTML(label="דוגמיות צבע")
                            with gr.Row():
                                r3_g_svg = gr.File(label="📥 הורדת SVG")
                                r3_g_png = gr.File(label="🖼️ הורדת PNG")

        # ==========================================
        # אגף ד': Panel Connector, Xerox Collage, אריזה ודפוס
        # ==========================================
        with gr.Tab("🧩 אגף ד': מחברים מכניים, Xerox Collage, אריזה ודפוס"):
            with gr.Tabs():

                with gr.Tab("🔗 Panel Connector (תצוגת הרכבה של אריחים יושבים יחד)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            pc_img = gr.Image(label="העלאת תמונה לחריטה על פני האריחים (אופציונלי - לא חובה!)", type="filepath")
                            pc_layout = gr.Radio(
                                choices=[
                                    "מערך 2x2 אריחים מחוברים יחד (Assembly View)",
                                    "מערך 3x3 אריחים מחוברים יחד (Full Spread)",
                                    "אריח בודד (1x1 Single Tile)"
                                ],
                                value="מערך 2x2 אריחים מחוברים יחד (Assembly View)",
                                label="תצוגת חיבור ופיזור אריחים"
                            )
                            pc_shape = gr.Radio(
                                choices=[
                                    "אריח ריבועי מודולרי (Square Tiling)",
                                    "אריח משושה כוורת (Hexagon Tiling)"
                                ],
                                value="אריח ריבועי מודולרי (Square Tiling)",
                                label="גיאומטריית בסיס להשתלבות (Tiling)"
                            )
                            pc_joint = gr.Radio(
                                choices=[
                                    "זנב סנונית (Dovetail Joint)",
                                    "מחבר חץ מכני (Arrow Lock)",
                                    "אומגה / פאזל מכויל (Omega Interlock)"
                                ],
                                value="זנב סנונית (Dovetail Joint)",
                                label="סוג מחבר מכני (Mechanical Connector)"
                            )
                            pc_pattern = gr.Dropdown(
                                choices=[
                                    "עורקי עלים אורגניים (Organic Venation)",
                                    "רשת תאים / וורונוי (Cellular Web)",
                                    "גלים פרמטריים משתלבים (Continuous Wave Lattice)",
                                    "אריח חלק ללא חריטה פנימית (Solid Mechanical Tile)"
                                ],
                                value="עורקי עלים אורגניים (Organic Venation)",
                                label="פאטרן אורגני פנימי (כאשר לא מועלית תמונה)"
                            )
                            with gr.Row():
                                pc_size = gr.Slider(minimum=40, maximum=200, step=5, value=90, label="גודל אריח יחיד (מ\"מ)")
                                pc_scale = gr.Slider(minimum=0.6, maximum=1.4, step=0.1, value=1.0, label="גודל שן מחבר")
                            with gr.Row():
                                pc_density = gr.Slider(minimum=4, maximum=24, step=2, value=10, label="צפיפות פאטרן פנימי")
                                pc_thick = gr.Slider(minimum=1.5, maximum=8.0, step=0.5, value=3.0, label="עובי אריח ל-STL (מ\"מ)")
                            pc_btn = gr.Button("⚙️ ייצר מערך אריחים מחוברים (SVG + PNG + 3D STL)", variant="primary")

                        with gr.Column(scale=1):
                            pc_prev = gr.HTML(label="שרטוט הרכבה וקטורי (איך שהאריחים יושבים יחד)")
                            pc_stl_view = gr.Model3D(label="הדמיית 3D STL אינטראקטיבית של האריחים (ללא רקע ריבועי)")
                            with gr.Row():
                                pc_out_svg = gr.File(label="📥 הורדת SVG (לחיתוך/בלנדר)")
                                pc_out_png = gr.File(label="🖼️ הורדת PNG")
                                pc_out_stl = gr.File(label="📦 הורדת STL (ל-Bambu Lab)")

                with gr.Tab("📰 Xerox Collage (מחולל זין, הדפס מכונת צילום וברקוד)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            xc_img = gr.Image(label="העלאת תמונה להפיכה להדפס מכונת צילום וקולאז'", type="filepath")
                            xc_serial = gr.Textbox(value="21038259053", label="מספר סידורי לברקוד הווקטורי")
                            xc_text = gr.Textbox(value="DIGICRAFT ARCHIVE // SPEC 04 // TACTILE ZINE EDITION", label="טקסט טכני לבלוק העריכתי")
                            xc_grain = gr.Slider(minimum=1, maximum=5, step=0.5, value=2.5, label="עוצמת טונר וגרעיניות מכונת צילום")
                            xc_tint = gr.Radio(
                                choices=[
                                    "נייר ארכיון חם (Warm Sepia Paper)",
                                    "נייר מכונת צילום קלאסי (Cool Monochrome)"
                                ],
                                value="נייר ארכיון חם (Warm Sepia Paper)",
                                label="גוון נייר וקרעי שרטוט"
                            )
                            xc_btn = gr.Button("📰 ייצר קולאז' זין / Xerox (SVG + PNG)", variant="primary")
                        with gr.Column(scale=1):
                            xc_prev = gr.HTML(label="תצוגת קולאז'")
                            with gr.Row():
                                xc_out_svg = gr.File(label="📥 הורדת SVG")
                                xc_out_png = gr.File(label="🖼️ הורדת PNG")

                with gr.Tab("📦 מחולל גזרות אריזה (Multi-Shape Dielines)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r4_d_file = gr.File(label="העלאת תמונה / פוסטר / SVG", file_types=["image", ".svg"], type="filepath")
                            r4_d_shape = gr.Radio(
                                choices=[
                                    "קופסת כרית (Pillow Box)",
                                    "פריסת משושה (Hexagonal Box)",
                                    "מארז נשיאה עם ידית (Handle Carrier)",
                                    "קופסה עם חלון חיתוך (Window Tuck Box)"
                                ],
                                value="קופסת כרית (Pillow Box)",
                                label="בחירת מבנה הפריסה"
                            )
                            r4_d_mode = gr.Radio(
                                choices=[
                                    "פילטר אסתטי מלא (תמונה על כל הפריסה)",
                                    "מיקוד בגוף המארז בלבד"
                                ],
                                value="פילטר אסתטי מלא (תמונה על כל הפריסה)",
                                label="אופן הלבשת הגרפיקה"
                            )
                            r4_d_w = gr.Slider(minimum=40, maximum=250, step=5, value=110, label="רוחב בסיס (W mm)")
                            r4_d_h = gr.Slider(minimum=40, maximum=300, step=5, value=160, label="גובה (H mm)")
                            r4_d_d = gr.Slider(minimum=20, maximum=150, step=5, value=50, label="עומק (D mm)")
                            r4_d_specs = gr.Checkbox(label="הצג כיתוב מידות טכני וגריד (Blueprint Specs)", value=True)
                            r4_d_btn = gr.Button("הלבש פילטר פריסה (SVG + PNG)", variant="primary")
                        with gr.Column(scale=1):
                            r4_d_prev = gr.HTML(label="תצוגה מקדימה")
                            with gr.Row():
                                r4_d_svg = gr.File(label="📥 הורדת SVG")
                                r4_d_png = gr.File(label="🖼️ הורדת PNG")

                with gr.Tab("🎯 פילטר סימני רישום וכוונות (Registration Overlay)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r4_r_file = gr.File(label="העלאת תמונה / SVG", file_types=["image", ".svg"], type="filepath")
                            r4_r_theme = gr.Radio(choices=["Classic Pre-Press (Light)", "Dark Cyber / Acid Print"], value="Dark Cyber / Acid Print", label="סגנון אסתטי")
                            r4_r_w = gr.Slider(minimum=50, maximum=500, step=10, value=210, label="רוחב קנבס (Width mm)")
                            r4_r_h = gr.Slider(minimum=50, maximum=500, step=10, value=297, label="גובה קנבס (Height mm)")
                            r4_r_b = gr.Slider(minimum=0, maximum=20, step=1, value=5, label="שולי גלישה (Bleed mm)")
                            r4_r_btn = gr.Button("הלבש פילטר רישום ודפוס (SVG + PNG)", variant="primary")
                        with gr.Column(scale=1):
                            r4_r_prev = gr.HTML(label="תצוגה מקדימה")
                            with gr.Row():
                                r4_r_svg = gr.File(label="📥 הורדת SVG")
                                r4_r_png = gr.File(label="🖼️ הורדת PNG")

        # ==========================================
        # אגף ה': Gentype Studio (עם בורר פונטים!)
        # ==========================================
        with gr.Tab("🔤 אגף ה': Gentype Studio (טיפוגרפיה גנרטיבית ובחירת פונטים)"):
            with gr.Row():
                with gr.Column(scale=1):
                    gt_text = gr.Textbox(value="MAI STUDIO", label="הזנת אותיות / מילה (עברית או אנגלית)")
                    gt_font = gr.Dropdown(
                        choices=[
                            "Rubik (עברית/אנגלית - גיאומטרי עגול)",
                            "Heebo (עברית/אנגלית - מודרני נקי)",
                            "Frank Ruhl Libre (עברית/אנגלית - סריף קלאסי)",
                            "Assistant (עברית/אנגלית - דו-לשוני)",
                            "Orbitron (אנגלית - סייבר ועתידני)",
                            "Syne (אנגלית - אקספרימנטלי ואמנותי)",
                            "Cinzel (אנגלית - רומי מלכותי)",
                            "Playfair Display (אנגלית - אופנה ויוקרה)",
                            "Space Mono (מונוספייס טכני)"
                        ],
                        value="Orbitron (אנגלית - סייבר ועתידני)",
                        label="בחירת פונט (Font Family)"
                    )
                    gt_style = gr.Radio(
                        choices=[
                            "Y2K Liquid Chrome (כרום נוזלי ותלת-ממד)",
                            "Cyber Stitch & Loom (רקמה ורשת דיגיטלית)",
                            "Botanical Venation (עורקים וצמיחה אורגנית)"
                        ],
                        value="Y2K Liquid Chrome (כרום נוזלי ותלת-ממד)",
                        label="סגנון טיפוגרפי"
                    )
                    gt_engine = gr.Radio(
                        choices=[
                            "מנוע וקטורי פרמטרי מיידי (ללא תלות במכסת API)",
                            "Gemini AI SVG Typography (דורש מפתח API בשרת)"
                        ],
                        value="מנוע וקטורי פרמטרי מיידי (ללא תלות במכסת API)",
                        label="מנוע ייצור"
                    )
                    gt_theme = gr.Textbox(placeholder="תיאור חופשי נוסף (למצב AI)...", label="הנחיית עיצוב נוספת (אופציונלי)")
                    with gr.Row():
                        gt_col1 = gr.ColorPicker(value="#e86c52", label="צבע ראשי")
                        gt_col2 = gr.ColorPicker(value="#00e5ff", label="צבע משני / הדגשה")
                    gt_btn = gr.Button("✨ ייצר טיפוגרפיה גנרטיבית (SVG + PNG)", variant="primary")

                with gr.Column(scale=1):
                    gt_prev = gr.HTML(label="תצוגת טיפוגרפיה")
                    with gr.Row():
                        gt_svg = gr.File(label="📥 הורדת SVG וקטורי")
                        gt_png = gr.File(label="🖼️ הורדת PNG")

        # ==========================================
        # אגף ו': גלריית היסטוריה אוטומטית ל-7 ימים
        # ==========================================
        with gr.Tab("🗂️ אגף ו': גלריית היסטוריה אוטומטית (7 ימים)") as tab_gallery:
            gr.Markdown("### ארכיון יצירות אוטומטי (כל תוצר שנוצר בחדרים נשמר ומופיע כאן מיד ללא צורך להוריד למחשב)")
            hist_refresh_btn = gr.Button("🔄 רענן גלריה עכשיו", variant="primary")
            hist_info = gr.HTML()
            with gr.Row():
                hist_gallery = gr.Gallery(label="תצוגה מקדימה של כל התוצרים השמורים", columns=4, height="auto")
                hist_files = gr.File(label="הורדת קבצים שמורים מהארכיון (SVG / PNG / STL)")

        # ==========================================
        # אגף ז': חדר בקרה למנהלת (Admin Control Room)
        # ==========================================
        with gr.Tab("🛡️ אגף ז': חדר בקרה למנהלת (Admin)") as tab_admin:
            admin_refresh_btn = gr.Button("🔄 רענן נתוני מערכת וסטטיסטיקות", variant="primary")
            admin_html = gr.HTML()

    # ==========================================
    # חיבורי אירועים, שמירה ורענון אוטומטי לגלריה ולחדר הבקרה
    # ==========================================
    master_studio.load(
        fn=on_app_load,
        inputs=[current_user_state],
        outputs=[hist_gallery, hist_files, hist_info, admin_html]
    )

    login_btn.click(
        fn=handle_login,
        inputs=[login_user, login_pass],
        outputs=[current_user_state, user_status_badge, auth_feedback]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info]).then(fn=get_admin_dashboard, inputs=[current_user_state], outputs=[admin_html])

    reg_btn.click(
        fn=handle_register,
        inputs=[reg_user, reg_email, reg_pass],
        outputs=[current_user_state, user_status_badge, auth_feedback]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    guest_quick_btn.click(
        fn=handle_guest_mode,
        inputs=[],
        outputs=[current_user_state, user_status_badge, auth_feedback]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    rec_send_btn.click(fn=send_recovery_email, inputs=[rec_email], outputs=[auth_feedback])
    rec_reset_btn.click(fn=reset_password_with_code, inputs=[rec_email, rec_code, rec_new_pass], outputs=[auth_feedback])

    tab_gallery.select(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])
    hist_refresh_btn.click(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])
    tab_admin.select(fn=get_admin_dashboard, inputs=[current_user_state], outputs=[admin_html])
    admin_refresh_btn.click(fn=get_admin_dashboard, inputs=[current_user_state], outputs=[admin_html])

    # אגף א'
    r1_btn.click(
        fn=generate_pixel_matrix,
        inputs=[r1_img, r1_grid, r1_colors, r1_style, current_user_state],
        outputs=[r1_preview, r1_palette, r1_out_svg, r1_out_png]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    # אגף ב'
    pbr_btn.click(
        fn=generate_pbr_and_stl,
        inputs=[pbr_img, pbr_res, pbr_smooth, pbr_contrast, pbr_invert, pbr_cutout, pbr_thresh, pbr_size, pbr_base, pbr_relief, current_user_state],
        outputs=[pbr_hm_prev, pbr_shade_prev, pbr_stl_viewer, pbr_out_png, pbr_out_stl, pbr_specs]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    hm_btn.click(
        fn=generate_heatmap_room,
        inputs=[hm_img, hm_style, hm_pal, hm_res, hm_blur, current_user_state],
        outputs=[hm_prev, hm_swatches, hm_out_svg, hm_out_png]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    rl_btn.click(
        fn=generate_raster_lines,
        inputs=[rl_img, rl_lines, rl_amp, rl_line_col, rl_glow_col, current_user_state],
        outputs=[rl_prev, rl_stl_view, rl_out_svg, rl_out_png, rl_out_stl]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    r2_c_btn.click(
        fn=generate_contours,
        inputs=[r2_c_img, r2_c_levels, r2_c_blur, r2_c_stroke, r2_c_bg, current_user_state],
        outputs=[r2_c_prev, r2_c_svg, r2_c_png]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    r2_d_btn.click(
        fn=generate_depth_texture,
        inputs=[r2_d_img, r2_d_grid, r2_d_shape, r2_d_fg, r2_d_bg, current_user_state],
        outputs=[r2_d_prev, r2_d_svg, r2_d_png]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    # אגף ג'
    r3_i_btn.click(
        fn=generate_iso_voxels,
        inputs=[r3_i_img, r3_i_w, r3_i_ext, r3_i_gap, r3_i_bg_mode, current_user_state],
        outputs=[r3_i_prev, r3_i_stl_view, r3_i_swatches, r3_i_svg, r3_i_png, r3_i_stl]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    ls_btn.click(
        fn=generate_liquid_screen,
        inputs=[ls_img, ls_drip, ls_glow, ls_tint, current_user_state],
        outputs=[ls_prev, ls_out_svg, ls_out_png]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    r3_w_btn.click(
        fn=generate_waveform,
        inputs=[r3_w_img, r3_w_lines, r3_w_amp, r3_w_col, current_user_state],
        outputs=[r3_w_prev, r3_w_svg, r3_w_png]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    r3_g_btn.click(
        fn=generate_adaptive_guilloche,
        inputs=[r3_g_img, r3_g_col, r3_g_R, r3_g_rot, current_user_state],
        outputs=[r3_g_prev, r3_g_swatches, r3_g_svg, r3_g_png]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    # אגף ד'
    pc_btn.click(
        fn=generate_panel_connector,
        inputs=[pc_img, pc_layout, pc_shape, pc_joint, pc_pattern, pc_size, pc_scale, pc_density, pc_thick, current_user_state],
        outputs=[pc_prev, pc_stl_view, pc_out_svg, pc_out_png, pc_out_stl]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    xc_btn.click(
        fn=generate_xerox_collage,
        inputs=[xc_img, xc_serial, xc_text, xc_grain, xc_tint, current_user_state],
        outputs=[xc_prev, xc_out_svg, xc_out_png]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    r4_d_btn.click(
        fn=generate_custom_dieline,
        inputs=[r4_d_file, r4_d_shape, r4_d_w, r4_d_h, r4_d_d, r4_d_mode, r4_d_specs, current_user_state],
        outputs=[r4_d_prev, r4_d_svg, r4_d_png]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    r4_r_btn.click(
        fn=generate_print_marks,
        inputs=[r4_r_file, r4_r_w, r4_r_h, r4_r_b, r4_r_theme, current_user_state],
        outputs=[r4_r_prev, r4_r_svg, r4_r_png]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

    # אגף ה'
    gt_btn.click(
        fn=generate_gentype_typography,
        inputs=[gt_text, gt_font, gt_style, gt_theme, gt_engine, gt_col1, gt_col2, current_user_state],
        outputs=[gt_prev, gt_svg, gt_png]
    ).then(fn=get_history_display, inputs=[current_user_state], outputs=[hist_gallery, hist_files, hist_info])

port = int(os.environ.get("PORT", 7860))
master_studio.launch(server_name="0.0.0.0", server_port=port)
