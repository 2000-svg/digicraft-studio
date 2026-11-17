# ==============================================================================
# DIGICRAFT MATRIX PALACE - PART 1 OF 3
# Core Engine, 7-Day Archive, DMC Swatches, Wing A (Textile) & Wing B (PBR/STL)
# ==============================================================================
import os
import time
import math
import json
import struct
import base64
import re
import gradio as gr
import google.generativeai as genai
import PIL.Image
import PIL.ImageDraw
import PIL.ImageOps
import PIL.ImageFilter
import numpy as np
from skimage import measure
from skimage.filters import gaussian

# חיבור מפתח Gemini API מהשרת ב-Render
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# ==========================================
# 1. ניהול ארכיון והיסטוריה אוטומטי ל-7 ימים
# ==========================================
HISTORY_DIR = "studio_history"
HISTORY_META = os.path.join(HISTORY_DIR, "metadata.json")
RETENTION_SECONDS = 7 * 24 * 3600  # 7 ימים

os.makedirs(HISTORY_DIR, exist_ok=True)


def clean_and_load_history():
    if not os.path.exists(HISTORY_META):
        return []
    try:
        with open(HISTORY_META, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception:
        items = []

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

    with open(HISTORY_META, "w", encoding="utf-8") as f:
        json.dump(valid_items, f, ensure_ascii=False, indent=2)
    return valid_items


def save_to_history(user_mode, room_name, svg_path=None, png_path=None, stl_path=None):
    if "אורח" in str(user_mode):
        return
    items = clean_and_load_history()
    ts = int(time.time())
    time_str = time.strftime("%d/%m/%Y %H:%M", time.localtime(ts))

    entry = {
        "id": f"job_{ts}_{len(items)}",
        "timestamp": ts,
        "date": time_str,
        "room": room_name,
        "svg_path": svg_path,
        "png_path": png_path,
        "stl_path": stl_path
    }
    items.insert(0, entry)
    with open(HISTORY_META, "w", encoding="utf-8") as f:
        json.dump(items[:60], f, ensure_ascii=False, indent=2)


def get_history_display():
    items = clean_and_load_history()
    gallery_imgs = []
    files_list = []
    if not items:
        return [], [], "<div class='telemetry-box'>הגלריה ריקה כרגע. תוצרים שייווצרו במצב 'משתמשת רשומה' יישמרו כאן למשך 7 ימים.</div>"

    rows_html = ["<div class='telemetry-box'><h4>יומן תוצרים שמורים בארכיון (תוקף: 7 ימים)</h4><ul>"]
    for item in items:
        png_p = item.get("png_path")
        svg_p = item.get("svg_path")
        stl_p = item.get("stl_path")
        if png_p and os.path.exists(png_p):
            gallery_imgs.append((png_p, f"{item['room']} ({item['date']})"))
            files_list.append(png_p)
        if svg_p and os.path.exists(svg_p):
            files_list.append(svg_p)
        if stl_p and os.path.exists(stl_p):
            files_list.append(stl_p)
        rows_html.append(f"<li><b>{item['date']}</b> | {item['room']}</li>")
    rows_html.append("</ul></div>")
    return gallery_imgs, files_list, "".join(rows_html)


# ==========================================
# 2. מאגר חוטי DMC ודוגמיות צבע ויזואליות (Swatches)
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
    """טעינת תמונה חכמה המנקה שקיפויות וצילומי מסך של טקסט לרקע לבן חלק"""
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
    """מייצר כרטיסיות צבע ויזואליות (Swatch Box) לצד קוד ה-HEX, חוט ה-DMC ואחוז הכיסוי"""
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


# ==========================================
# 3. מנוע המרת SVG ל-PNG ברזולוציה גבוהה
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

    img = PIL.Image.new("RGB", (img_w, img_h), "#141414")
    draw = PIL.ImageDraw.Draw(img)

    class_strokes = {
        "cut": ("#ff1744", max(2, int(1.5 * scale))),
        "fold": ("#00e5ff", max(1, int(1.2 * scale))),
        "reg": ("#00ffaa", max(1, int(1.0 * scale))),
        "bleed": ("#ff0055", max(1, int(1.0 * scale))),
        "spec": ("#888888", 1)
    }

    for tag_match in re.finditer(r'<(rect|circle|line|polygon|path|text)\b([^>]*)/?>', svg_code):
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

        fill_col = None if fill in ("none", "transparent", None) else fill
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


def save_dual_outputs(svg_code, base_name, user_mode, room_title, custom_png_img=None):
    ts = int(time.time())
    svg_file = os.path.join(HISTORY_DIR, f"{base_name}_{ts}.svg")
    png_file = os.path.join(HISTORY_DIR, f"{base_name}_{ts}.png")

    with open(svg_file, "w", encoding="utf-8") as f:
        f.write(svg_code)

    if custom_png_img is not None:
        custom_png_img.save(png_file, "PNG")
    else:
        render_svg_to_png(svg_code, png_file)

    save_to_history(user_mode, room_title, svg_path=svg_file, png_path=png_file)
    return svg_file, png_file


# ==========================================
# 4. אגף א': טקסטיל, אריגת ז'קארד ומטריצת פיקסלים
# ==========================================
def generate_pixel_matrix(image_path, grid_width, num_colors, style, user_mode):
    try:
        img = ensure_clean_rgb(image_path)
        w, h = img.size
        aspect_ratio = h / w
        grid_height = max(5, int(grid_width * aspect_ratio))

        img_small = img.resize((grid_width, grid_height), PIL.Image.Resampling.LANCZOS)
        img_quantized = img_small.quantize(colors=num_colors, method=PIL.Image.MEDIANCUT).convert('RGB')
        pixels = img_quantized.load()

        cell_size = 14
        svg_width = grid_width * cell_size
        svg_height = grid_height * cell_size

        bg_hex = "#141414" if style == "אריגת ז'קארד (Jacquard Weave)" else "#fafafa"
        svg_lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}" width="100%" height="100%">']
        svg_lines.append(f'<rect x="0" y="0" width="{svg_width}" height="{svg_height}" fill="{bg_hex}"/>')

        color_counter = {}
        ascii_chars = "@%#*+=-:. "

        if style == "ASCII Art (טיפוגרפיה)":
            svg_lines.append('<g font-family="monospace" font-weight="bold" font-size="13" text-anchor="middle" dominant-baseline="central">')
        else:
            svg_lines.append('<g>')

        for y in range(grid_height):
            for x in range(grid_width):
                r, g, b = pixels[x, y]
                lum = get_luminance(r, g, b)

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

        sorted_colors = sorted(color_counter.items(), key=lambda x: x[1], reverse=True)
        total_px = sum(color_counter.values())
        swatches_html = build_color_swatches_html(sorted_colors, total_px)

        svg_file, png_file = save_dual_outputs(svg_code, "textile_matrix", user_mode, f"טקסטיל: {style}")
        preview_html = f'<div class="canvas-preview">{svg_code}</div>'

        return preview_html, swatches_html, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", "", None, None


# ==========================================
# 5. אגף ב': טופוגרפיה, Heatmap, מפות PBR וייצוא STL לבמבו-לאב
# ==========================================
def generate_contours(image_path, num_levels, blur_sigma, stroke_col, bg_col, user_mode):
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

        svg_file, png_file = save_dual_outputs(svg_code, "topography_isolines", user_mode, "קווי גובה טופוגרפיים")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None


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


def generate_heatmap_room(image_path, mode_style, palette_name, resolution, blur_val, user_mode):
    try:
        img = ensure_clean_rgb(image_path).convert('L')
        w_orig, h_orig = img.size
        aspect = h_orig / w_orig

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
        svg_file, png_file = save_dual_outputs(svg_code, "heatmap_vector", user_mode, f"Heatmap: {palette_name}")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, swatches_html, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", "", None, None


def heightmap_to_watertight_stl(z_grid, stl_path, width_mm=100.0, height_mm=100.0, base_mm=2.0, relief_mm=2.5):
    """בונה קובץ STL בינארי אטום (Watertight) עם בסיס שטוח המוכן להדפסה ב-Bambu Studio"""
    ny, nx = z_grid.shape
    xs = np.linspace(0.0, width_mm, nx, dtype=np.float32)
    ys = np.linspace(0.0, height_mm, ny, dtype=np.float32)
    xv, yv = np.meshgrid(xs, ys)
    yv = height_mm - yv
    zv = base_mm + (z_grid.astype(np.float32) * relief_mm)

    tris = []

    p00 = np.stack([xv[:-1, :-1], yv[:-1, :-1], zv[:-1, :-1]], axis=-1)
    p10 = np.stack([xv[:-1, 1:], yv[:-1, 1:], zv[:-1, 1:]], axis=-1)
    p01 = np.stack([xv[1:, :-1], yv[1:, :-1], zv[1:, :-1]], axis=-1)
    p11 = np.stack([xv[1:, 1:], yv[1:, 1:], zv[1:, 1:]], axis=-1)

    t1 = np.stack([p00, p01, p11], axis=2).reshape(-1, 3, 3)
    t2 = np.stack([p00, p11, p10], axis=2).reshape(-1, 3, 3)
    tris.append(t1)
    tris.append(t2)

    b00 = np.array([0.0, height_mm, 0.0], dtype=np.float32)
    b10 = np.array([width_mm, height_mm, 0.0], dtype=np.float32)
    b01 = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    b11 = np.array([width_mm, 0.0, 0.0], dtype=np.float32)
    base_tris = np.array([[b00, b10, b11], [b00, b11, b01]], dtype=np.float32)
    tris.append(base_tris)

    walls = []
    for j in range(nx - 1):
        vt1 = [xv[0, j], yv[0, j], zv[0, j]]
        vt2 = [xv[0, j + 1], yv[0, j + 1], zv[0, j + 1]]
        vb1 = [xv[0, j], yv[0, j], 0.0]
        vb2 = [xv[0, j + 1], yv[0, j + 1], 0.0]
        walls.extend([[vt1, vt2, vb2], [vt1, vb2, vb1]])
    for j in range(nx - 1):
        vt1 = [xv[-1, j], yv[-1, j], zv[-1, j]]
        vt2 = [xv[-1, j + 1], yv[-1, j + 1], zv[-1, j + 1]]
        vb1 = [xv[-1, j], yv[-1, j], 0.0]
        vb2 = [xv[-1, j + 1], yv[-1, j + 1], 0.0]
        walls.extend([[vt2, vt1, vb1], [vt2, vb1, vb2]])
    for i in range(ny - 1):
        vt1 = [xv[i, 0], yv[i, 0], zv[i, 0]]
        vt2 = [xv[i + 1, 0], yv[i + 1, 0], zv[i + 1, 0]]
        vb1 = [xv[i, 0], yv[i, 0], 0.0]
        vb2 = [xv[i + 1, 0], yv[i + 1, 0], 0.0]
        walls.extend([[vt2, vt1, vb1], [vt2, vb1, vb2]])
    for i in range(ny - 1):
        vt1 = [xv[i, -1], yv[i, -1], zv[i, -1]]
        vt2 = [xv[i + 1, -1], yv[i + 1, -1], zv[i + 1, -1]]
        vb1 = [xv[i, -1], yv[i, -1], 0.0]
        vb2 = [xv[i + 1, -1], yv[i + 1, -1], 0.0]
        walls.extend([[vt1, vt2, vb2], [vt1, vb2, vb1]])

    tris.append(np.array(walls, dtype=np.float32))
    all_tris = np.concatenate(tris, axis=0)

    num_tris = all_tris.shape[0]
    stl_dtype = np.dtype([
        ('normal', '<f4', (3,)),
        ('v1', '<f4', (3,)),
        ('v2', '<f4', (3,)),
        ('v3', '<f4', (3,)),
        ('attr', '<u2')
    ])
    data = np.zeros(num_tris, dtype=stl_dtype)
    data['v1'] = all_tris[:, 0, :]
    data['v2'] = all_tris[:, 1, :]
    data['v3'] = all_tris[:, 2, :]

    with open(stl_path, 'wb') as f:
        header = b"DIGICRAFT_MATRIX_BAMBULAB_STL".ljust(80, b' ')
        f.write(header)
        f.write(struct.pack('<I', num_tris))
        f.write(data.tobytes())

    return stl_path


def generate_pbr_and_stl(image_path, mesh_res, smooth_sigma, contrast_boost, invert_map, tile_size_mm, base_thick_mm, relief_height_mm, user_mode):
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

        ts = int(time.time())
        hm_png_path = os.path.join(HISTORY_DIR, f"pbr_heightmap_{ts}.png")
        hm_img = PIL.Image.fromarray((hm_arr * 255).astype(np.uint8), mode='L')
        hm_img.save(hm_png_path, "PNG")

        gy, gx = np.gradient(hm_arr * relief_height_mm)
        nz = np.ones_like(hm_arr) * 0.35
        norm = np.sqrt(gx ** 2 + gy ** 2 + nz ** 2)
        lx, ly, lz = -0.55, -0.55, 0.62
        shaded = np.clip((gx * lx + gy * ly + nz * lz) / norm, 0.0, 1.0)
        shaded_img = PIL.Image.fromarray((shaded * 255).astype(np.uint8), mode='L').convert('RGB')

        w_orig, h_orig = img.size
        aspect = h_orig / w_orig
        nx = int(mesh_res)
        ny = max(20, int(nx * aspect))
        hm_mesh_img = hm_img.resize((nx, ny), PIL.Image.Resampling.LANCZOS)
        z_grid = np.array(hm_mesh_img, dtype=np.float32) / 255.0

        z_grid[0, :] *= 0.2
        z_grid[-1, :] *= 0.2
        z_grid[:, 0] *= 0.2
        z_grid[:, -1] *= 0.2

        stl_path = os.path.join(HISTORY_DIR, f"bambulab_tile_{ts}.stl")
        height_mm = tile_size_mm * aspect
        heightmap_to_watertight_stl(z_grid, stl_path, width_mm=tile_size_mm, height_mm=height_mm, base_mm=base_thick_mm, relief_mm=relief_height_mm)

        save_to_history(user_mode, "PBR Height Map + STL", png_path=hm_png_path, stl_path=stl_path)

        specs_msg = f"<div class='telemetry-box'><b>מוכן ל-Bambu Studio ול-Blender:</b> מידות אריח: {tile_size_mm:.0f}x{height_mm:.0f} מ\"מ | עובי בסיס: {base_thick_mm} מ\"מ | גובה תבליט: {relief_height_mm} מ\"מ | רשת: {nx}x{ny}</div>"
        return hm_img, shaded_img, stl_path, hm_png_path, stl_path, specs_msg
    except Exception as e:
        return None, None, None, None, None, f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>"


def generate_depth_texture(image_path, grid_size, shape_type, user_mode):
    try:
        if not os.environ.get("GEMINI_API_KEY"):
            return "<p style='color:#ff5252;'>שגיאה: מפתח GEMINI_API_KEY לא הוגדר ב-Environment Variables של השרת.</p>", None, None

        img = ensure_clean_rgb(image_path)
        model = genai.GenerativeModel('gemini-2.5-pro')

        prompt = f"""
        You are an expert computational designer. Analyze the depth and brightness of the attached image.
        Translate this visual data into a parametric 2D SVG texture.
        Strict Technical Requirements:
        1. Grid constraints: Create a grid of {grid_size}x{grid_size} geometric elements on viewBox="0 0 800 800".
        2. Shape type: Use {shape_type} as the primary repeating element.
        3. Parametric mapping: The size (radius/scale) or stroke-width of each {shape_type} MUST correspond directly to the brightness or perceived depth of that specific area in the image.
        4. Style: Include <rect x="0" y="0" width="800" height="800" fill="#ffffff"/> and monochrome black shapes (#111111).
        5. Clean code: Output ONLY the raw valid SVG code starting with <svg> and ending with </svg>. Do not wrap in ```svg tags.
        """

        response = model.generate_content([prompt, img])
        svg_code = re.sub(r'```(?:xml|svg)?\n|```', '', response.text).strip()

        svg_file, png_file = save_dual_outputs(svg_code, "ai_parametric_depth", user_mode, f"AI Depth: {shape_type}")
        preview_html = f'<div class="canvas-preview">{svg_code}</div>'
        return preview_html, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None
        # ==============================================================================
# DIGICRAFT MATRIX PALACE - PART 2 OF 3
# Wing C (Math Generators), Wing D (Panel Connector & Packaging), Wing E (Gentype)
# ==============================================================================

# ==========================================
# 6. אגף ג': מחוללים מתמטיים (Wave, Voxel, Guilloche)
# ==========================================
def generate_waveform(image_path, num_lines, amp, color, user_mode):
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

        svg_file, png_file = save_dual_outputs(svg_code, "waveform_art", user_mode, "גלי קול (Waveform)")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None


def generate_iso_voxels(image_path, grid_width, extrusion, gap, user_mode):
    try:
        img = ensure_clean_rgb(image_path)
        aspect = img.height / img.width
        grid_height = max(5, int(grid_width * aspect))

        img_small = img.resize((grid_width, grid_height), PIL.Image.Resampling.LANCZOS)
        img_quantized = img_small.quantize(colors=12, dither=PIL.Image.Dither.NONE).convert('RGB')
        pixels = img_quantized.load()

        step_w = 10
        step_h = 5
        base_h = 5

        min_x = -grid_height * step_w
        max_x = grid_width * step_w
        min_y = -extrusion - base_h - step_h
        max_y = (grid_width + grid_height) * step_h + extrusion

        ox = min_x - step_w * 2
        oy = min_y - step_h * 2
        svg_w = max_x - min_x + (step_w * 4)
        svg_h = max_y - min_y + (step_h * 4)

        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{ox} {oy} {svg_w} {svg_h}" width="100%" height="100%">']
        svg.append(f'<rect x="{ox}" y="{oy}" width="{svg_w}" height="{svg_h}" fill="#181818"/>')

        dw = step_w - gap
        dh = step_h - (gap / 2.0)

        color_counter = {}
        for y in range(grid_height):
            for x in range(grid_width):
                r, g, b = pixels[x, y]
                if r > 242 and g > 242 and b > 242:
                    continue

                color_counter[(r, g, b)] = color_counter.get((r, g, b), 0) + 1
                lum = get_luminance(r, g, b)
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

        svg.append('</svg>')
        svg_code = "\n".join(svg)

        sorted_colors = sorted(color_counter.items(), key=lambda x: x[1], reverse=True)
        swatches_html = build_color_swatches_html(sorted_colors, sum(color_counter.values()))
        svg_file, png_file = save_dual_outputs(svg_code, "voxel_sculpture", user_mode, "פסל איזומטרי (Voxel Art)")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, swatches_html, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", "", None, None


def generate_adaptive_guilloche(image_path, num_colors, base_R, rotations, user_mode):
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
        svg_file, png_file = save_dual_outputs(svg_code, "adaptive_guilloche", user_mode, "רוזטת גיליושה אדפטיבית")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, swatches_html, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", "", None, None


# ==========================================
# 7. אגף ד': Panel Connector (מחברים מכניים) + פריסות אריזה וסימני דפוס
# ==========================================
def build_connector_edge(x1, y1, x2, y2, conn_type, direction, tab_scale=1.0):
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    nx, ny = -uy * direction, ux * direction

    def pt(along, perp):
        return f"{x1 + ux * along * length + nx * perp * length * tab_scale:.2f} {y1 + uy * along * length + ny * perp * length * tab_scale:.2f}"

    if conn_type == "זנב סנונית (Dovetail Joint)":
        pts = [pt(0, 0), pt(0.38, 0), pt(0.32, 0.14), pt(0.68, 0.14), pt(0.62, 0), pt(1.0, 0)]
    elif conn_type == "מחבר חץ מכני (Arrow Lock)":
        pts = [pt(0, 0), pt(0.42, 0), pt(0.42, 0.08), pt(0.34, 0.08), pt(0.50, 0.20), pt(0.66, 0.08), pt(0.58, 0.08), pt(0.58, 0), pt(1.0, 0)]
    else:
        pts = [pt(0, 0), pt(0.40, 0), pt(0.35, 0.07), pt(0.40, 0.15), pt(0.50, 0.17), pt(0.60, 0.15), pt(0.65, 0.07), pt(0.60, 0), pt(1.0, 0)]

    return " L ".join(pts)


def generate_panel_connector(tile_shape, conn_type, inner_pattern, tile_size_mm, tab_scale, density, thickness_mm, user_mode):
    try:
        canvas = 500
        cx, cy = canvas / 2, canvas / 2
        half = 150

        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas} {canvas}" width="100%" height="100%">']
        svg.append(f'<rect x="0" y="0" width="{canvas}" height="{canvas}" fill="#141414"/>')

        svg.append('<g stroke="#222222" stroke-width="0.6">')
        for g in range(0, canvas, 25):
            svg.append(f'<line x1="{g}" y1="0" x2="{g}" y2="{canvas}"/>')
            svg.append(f'<line x1="0" y1="{g}" x2="{canvas}" y2="{g}"/>')
        svg.append('</g>')

        if tile_shape == "אריח ריבועי מודולרי (Square Tiling)":
            corners = [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half)]
            dirs = [1, 1, -1, -1]
        else:
            corners = []
            for i in range(6):
                ang = math.radians(i * 60)
                corners.append((cx + half * 1.15 * math.cos(ang), cy + half * 1.15 * math.sin(ang)))
            dirs = [1, -1, 1, -1, 1, -1]

        edge_segments = []
        for i in range(len(corners)):
            p1 = corners[i]
            p2 = corners[(i + 1) % len(corners)]
            seg = build_connector_edge(p1[0], p1[1], p2[0], p2[1], conn_type, dirs[i], tab_scale)
            edge_segments.append(seg)

        outer_path = f"M {corners[0][0]:.2f} {corners[0][1]:.2f} L " + " L ".join(edge_segments) + " Z"
        svg.append(f'<path d="{outer_path}" fill="#222222" stroke="#00e5ff" stroke-width="2.2"/>')

        inner_r = half * 0.78
        if inner_pattern == "עורקי עלים אורגניים (Organic Venation)":
            for b in range(int(density)):
                angle = (2 * math.pi * b) / density
                ex = cx + inner_r * math.cos(angle)
                ey = cy + inner_r * math.sin(angle)
                mx = cx + (inner_r * 0.5) * math.cos(angle + 0.25)
                my = cy + (inner_r * 0.5) * math.sin(angle + 0.25)
                svg.append(f'<path d="M {cx} {cy} Q {mx:.1f} {my:.1f} {ex:.1f} {ey:.1f}" stroke="#ff5252" stroke-width="2.5" fill="none"/>')
                sx = mx + (inner_r * 0.32) * math.cos(angle - 0.5)
                sy = my + (inner_r * 0.32) * math.sin(angle - 0.5)
                svg.append(f'<line x1="{mx:.1f}" y1="{my:.1f}" x2="{sx:.1f}" y2="{sy:.1f}" stroke="#ff5252" stroke-width="1.5"/>')

        elif inner_pattern == "רשת תאים / וורונוי (Cellular Web)":
            rings = max(2, int(density // 3))
            for r_idx in range(1, rings + 1):
                rad = (inner_r / rings) * r_idx
                num_pts = r_idx * 6
                for j in range(num_pts):
                    a1 = (2 * math.pi * j) / num_pts + (r_idx * 0.2)
                    px = cx + rad * math.cos(a1)
                    py = cy + rad * math.sin(a1)
                    hole_r = (inner_r / (rings * 2.2)) * (1.1 - 0.3 * (r_idx / rings))
                    svg.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{hole_r:.1f}" fill="#141414" stroke="#ff5252" stroke-width="1.8"/>')

        elif inner_pattern == "גלים פרמטריים משתלבים (Parametric Wave Lattice)":
            lines = int(density)
            step = (inner_r * 1.8) / max(1, lines)
            for l_idx in range(lines + 1):
                y_base = (cy - inner_r * 0.9) + l_idx * step
                pts = []
                for s in range(30):
                    px = (cx - inner_r * 0.9) + (s / 29.0) * (inner_r * 1.8)
                    py = y_base + math.sin((s / 29.0) * math.pi * 4 + l_idx) * 8.0
                    pts.append(f"{px:.1f} {py:.1f}")
                svg.append(f'<path d="M {" L ".join(pts)}" stroke="#ff5252" stroke-width="1.8" fill="none"/>')

        svg.append(f'<text x="{cx}" y="{canvas - 14}" fill="#888888" font-family="monospace" font-size="10" text-anchor="middle">PANEL_CONNECTOR // {tile_size_mm:.0f}MM // JOINT: {conn_type} // CUT: #00E5FF</text>')
        svg.append('</svg>')
        svg_code = "\n".join(svg)

        svg_file, png_file = save_dual_outputs(svg_code, "panel_connector", user_mode, f"Panel Connector: {conn_type}")

        png_img = PIL.Image.open(png_file).convert('L').resize((110, 110), PIL.Image.Resampling.LANCZOS)
        z_arr = (np.array(png_img, dtype=np.float32) > 25).astype(np.float32)
        ts = int(time.time())
        stl_file = os.path.join(HISTORY_DIR, f"panel_connector_{ts}.stl")
        heightmap_to_watertight_stl(z_arr, stl_file, width_mm=tile_size_mm, height_mm=tile_size_mm, base_mm=0.4, relief_mm=thickness_mm)

        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, stl_file, svg_file, png_file, stl_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None, None, None


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


def generate_custom_dieline(file_path, shape_type, w, h, d, graphic_mode, show_specs, user_mode):
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

        svg_file, png_file = save_dual_outputs(svg_code, "dieline_package", user_mode, f"פריסת אריזה: {shape_type}")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None


def generate_print_marks(file_path, artboard_w, artboard_h, bleed, style_theme, user_mode):
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
        svg_file, png_file = save_dual_outputs(svg_code, "registration_marks", user_mode, "סימני רישום ודפוס")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None


# ==========================================
# 8. אגף ה': Gentype Studio (מחולל טיפוגרפיה גנרטיבית מאוחד)
# ==========================================
def generate_gentype_typography(text_input, style_preset, custom_theme, engine_mode, primary_col, accent_col, user_mode):
    try:
        text_clean = (text_input or "DIGICRAFT").strip()
        w, h = 900, 420

        if engine_mode == "Gemini AI SVG Typography (דורש מכסת API)" and os.environ.get("GEMINI_API_KEY"):
            model = genai.GenerativeModel('gemini-2.5-pro')
            prompt = f"""
            You are a master computational typographer and generative SVG artist.
            Create an expressive, intricate, high-fashion vector SVG typographic artwork spelling the exact text: "{text_clean}".
            Visual Style Preset: {style_preset}. Additional theme details: {custom_theme}.
            Color Palette: Background #121212, Primary {primary_col}, Accent {accent_col}.
            Technical rules:
            1. Use viewBox="0 0 {w} {h}" and start with <rect x="0" y="0" width="{w}" height="{h}" fill="#121212"/>.
            2. Construct ornate vector paths, geometric weaves, liquid chrome gradients, or organic tendrils around/forming the letters.
            3. Output ONLY valid raw <svg>...</svg> code without markdown backticks.
            """
            response = model.generate_content(prompt)
            svg_code = re.sub(r'```(?:xml|svg)?\n|```', '', response.text).strip()
        else:
            svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" height="100%">']
            svg.append(f'''<defs>
                <linearGradient id="chromeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="{primary_col}"/>
                    <stop offset="50%" stop-color="#ffffff"/>
                    <stop offset="100%" stop-color="{accent_col}"/>
                </linearGradient>
            </defs>''')
            svg.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="#121212"/>')

            num_chars = max(1, len(text_clean))
            step_x = (w - 120) / num_chars
            font_sz = int(min(180, step_x * 1.15))

            for idx, ch in enumerate(text_clean):
                cx = 60 + step_x * (idx + 0.5)
                cy = h / 2

                if style_preset == "Y2K Liquid Chrome (כרום נוזלי ותלת-ממד)":
                    for layer in range(12, 0, -1):
                        off = layer * 2.2
                        col = accent_col if layer % 2 == 0 else "#2a2a35"
                        svg.append(f'<text x="{cx + off:.1f}" y="{cy + off:.1f}" font-family="sans-serif" font-weight="900" font-size="{font_sz}" fill="none" stroke="{col}" stroke-width="2" text-anchor="middle" dominant-baseline="central">{ch}</text>')
                    svg.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-family="sans-serif" font-weight="900" font-size="{font_sz}" fill="url(#chromeGrad)" stroke="#ffffff" stroke-width="1.5" text-anchor="middle" dominant-baseline="central">{ch}</text>')

                elif style_preset == "Cyber Stitch & Loom (רקמה ורשת דיגיטלית)":
                    for r_off in range(-40, 45, 10):
                        svg.append(f'<line x1="{cx - step_x*0.4:.1f}" y1="{cy + r_off:.1f}" x2="{cx + step_x*0.4:.1f}" y2="{cy - r_off:.1f}" stroke="{accent_col}" stroke-width="0.8"/>')
                    svg.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-family="monospace" font-weight="bold" font-size="{font_sz}" fill="none" stroke="{primary_col}" stroke-width="4" stroke-dasharray="6,4" text-anchor="middle" dominant-baseline="central">{ch}</text>')
                    svg.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-family="monospace" font-weight="bold" font-size="{font_sz}" fill="{primary_col}" opacity="0.85" text-anchor="middle" dominant-baseline="central">{ch}</text>')

                else:
                    for b in range(10):
                        ang = (2 * math.pi * b) / 10
                        rx = cx + math.cos(ang) * (font_sz * 0.55)
                        ry = cy + math.sin(ang) * (font_sz * 0.55)
                        svg.append(f'<path d="M {cx} {cy} Q {cx + 25} {cy - 25} {rx:.1f} {ry:.1f}" stroke="{accent_col}" stroke-width="1.5" fill="none"/>')
                        svg.append(f'<circle cx="{rx:.1f}" cy="{ry:.1f}" r="3.5" fill="{primary_col}"/>')
                    svg.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-family="serif" font-weight="bold" font-size="{font_sz}" fill="{primary_col}" stroke="#121212" stroke-width="2" text-anchor="middle" dominant-baseline="central">{ch}</text>')

            svg.append(f'<text x="{w/2}" y="{h - 16}" fill="#666666" font-family="monospace" font-size="10" text-anchor="middle">GENTYPE_STUDIO // STYLE: {style_preset} // INPUT: {text_clean}</text>')
            svg.append('</svg>')
            svg_code = "\n".join(svg)

        svg_file, png_file = save_dual_outputs(svg_code, "gentype_studio", user_mode, f"Gentype: {text_clean}")
        preview = f'<div class="canvas-preview">{svg_code}</div>'
        return preview, svg_file, png_file
    except Exception as e:
        return f"<p style='color:#ff5252;'>שגיאה: {str(e)}</p>", None, None
        # ==============================================================================
# DIGICRAFT MATRIX PALACE - PART 3 OF 3
# Custom Stitch UI/UX CSS, Unified Wings Interface & Render Server Launch
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
    max-width: 620px;
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

# ==========================================
# בניית הארמון המאוחד: DigiCraft Matrix
# ==========================================
with gr.Blocks(title="DigiCraft Matrix Palace", theme=gr.themes.Base(), css=STITCH_CSS) as master_studio:

    gr.HTML("""
    <div class="stitch-header">
        <div>
            <h1 class="stitch-title">🏰 DIGICRAFT MATRIX // COMPUTATIONAL DESIGN PALACE</h1>
            <div class="stitch-subtitle">ACTIVE TUNE // PIXEL-TO-VECTOR · JACQUARD · PBR & BAMBU STL · PANEL CONNECTORS · GENTYPE</div>
        </div>
        <div style="text-align:left; font-family:'Space Mono', monospace; font-size:11px; color:#888;">
            <div>RENDER_ENGINE: ONLINE</div>
            <div style="color:#4caf50;">● ARCHIVE_RETENTION: 7 DAYS</div>
        </div>
    </div>
    """)

    with gr.Row():
        user_mode_radio = gr.Radio(
            choices=[
                "🔐 משתמשת רשומה: Mai (שמירה אוטומטית בגלריה ל-7 ימים)",
                "👤 מצב אורח (ללא שמירה בגלריית ההיסטוריה)"
            ],
            value="🔐 משתמשת רשומה: Mai (שמירה אוטומטית בגלריה ל-7 ימים)",
            label="מצב חיבור ופרטיות גלריה"
        )

    with gr.Tabs():

        # ==========================================
        # אגף א': טקסטיל, ז'קארד ומטריצות
        # ==========================================
        with gr.Tab("🧶 אגף א': טקסטיל, ז'קארד ומטריצות"):
            with gr.Row():
                with gr.Column(scale=1):
                    r1_img = gr.Image(label="מקור קלט תמונה (תומך בצילומי מסך, טקסט ושקיפויות)", type="filepath")
                    r1_style = gr.Radio(
                        choices=[
                            "אריגת ז'קארד (Jacquard Weave)",
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
                    r1_btn = gr.Button("⚡ הפעל סינתזת מטריצה (SVG + PNG)", variant="primary")

                with gr.Column(scale=1):
                    r1_preview = gr.HTML(label="תצוגת השוואה וקטורית")
                    r1_palette = gr.HTML(label="פלטת צבעים וחוטים")
                    with gr.Row():
                        r1_out_svg = gr.File(label="📥 הורדת קובץ וקטורי (SVG)")
                        r1_out_png = gr.File(label="🖼️ הורדת תמונה חדה (PNG)")

            r1_btn.click(
                fn=generate_pixel_matrix,
                inputs=[r1_img, r1_grid, r1_colors, r1_style, user_mode_radio],
                outputs=[r1_preview, r1_palette, r1_out_svg, r1_out_png]
            )

        # ==========================================
        # אגף ב': עומק, Heatmap, מפות PBR ו-STL לבמבו-לאב
        # ==========================================
        with gr.Tab("⛰️ אגף ב': עומק, Heatmap, PBR ו-STL לתלת-ממד"):
            with gr.Tabs():

                with gr.Tab("🧊 מעבדת PBR Height Map & ייצוא STL (לבלנדר ולבמבו-לאב)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            pbr_img = gr.Image(label="העלאת תמונה / טקסטורה להמרה לתבליט תלת-ממד", type="filepath")
                            with gr.Row():
                                pbr_res = gr.Slider(minimum=40, maximum=160, step=10, value=100, label="רזולוציית רשת תלת-ממד (Mesh Grid)")
                                pbr_smooth = gr.Slider(minimum=0.0, maximum=5.0, step=0.5, value=1.0, label="החלקת משטח (Gaussian Smooth)")
                            with gr.Row():
                                pbr_contrast = gr.Slider(minimum=0.5, maximum=3.0, step=0.1, value=1.3, label="עוצמת קונטרסט עומק (PBR Contrast)")
                                pbr_invert = gr.Checkbox(label="היפוך גבהים (Invert Black/White)", value=False)
                            with gr.Row():
                                pbr_size = gr.Slider(minimum=30, maximum=220, step=5, value=100, label="רוחב אריח פיזי (מ\"מ)")
                                pbr_base = gr.Slider(minimum=0.8, maximum=10.0, step=0.2, value=2.0, label="עובי בסיס שטוח (מ\"מ)")
                                pbr_relief = gr.Slider(minimum=0.4, maximum=8.0, step=0.2, value=2.4, label="גובה תבליט הטקסטורה (מ\"מ)")
                            pbr_btn = gr.Button("🔨 ייצר מפת גובה (PBR) + קובץ STL מוכן ל-Bambu Studio", variant="primary")

                        with gr.Column(scale=1):
                            pbr_specs = gr.HTML()
                            with gr.Row():
                                pbr_hm_prev = gr.Image(label="מפת גובה (Non-Color Height Map לבלנדר)")
                                pbr_shade_prev = gr.Image(label="הדמיית תאורה וצל (Relief Preview)")
                            pbr_stl_viewer = gr.Model3D(label="תצוגה מקדימה תלת-ממדית חיה (אינטראקטיבי - לאישור ה-STL)")
                            with gr.Row():
                                pbr_out_png = gr.File(label="🖼️ הורדת Height Map (PNG לבלנדר)")
                                pbr_out_stl = gr.File(label="📦 הורדת קובץ 3D STL (ישירות ל-Bambu Lab)")

                    pbr_btn.click(
                        fn=generate_pbr_and_stl,
                        inputs=[pbr_img, pbr_res, pbr_smooth, pbr_contrast, pbr_invert, pbr_size, pbr_base, pbr_relief, user_mode_radio],
                        outputs=[pbr_hm_prev, pbr_shade_prev, pbr_stl_viewer, pbr_out_png, pbr_out_stl, pbr_specs]
                    )

                with gr.Tab("🔥 חדר Heatmap (מפת חום וקטורית וטרמית)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            hm_img = gr.Image(label="העלאת תמונה למיפוי חום וצפיפות", type="filepath")
                            hm_style = gr.Radio(
                                choices=[
                                    "שכבות איזותרמיות (Isothermal Contours)",
                                    "מטריצת תאים תרמית (Thermal Matrix Grid)",
                                    "בועות קרינה פרמטריות (Thermal Nodes)"
                                ],
                                value="שכבות איזותרמיות (Isothermal Contours)",
                                label="סגנון מפת חום"
                            )
                            hm_pal = gr.Dropdown(
                                choices=[
                                    "Cyber Thermal (סגול-אדום-צהוב ליבון)",
                                    "Stitch Amber (פחם-נחושת-זהב חם)",
                                    "Acid Infrared (ירוק-ליים-ציאן תעשייתי)",
                                    "Arctic Blue-Red (כחול קוטבי-אדום חם)"
                                ],
                                value="Cyber Thermal (סגול-אדום-צהוב ליבון)",
                                label="פלטת צבעים תרמית"
                            )
                            hm_res = gr.Slider(minimum=20, maximum=100, step=5, value=55, label="צפיפות רשת (למצב מטריצה/בועות)")
                            hm_blur = gr.Slider(minimum=1.0, maximum=12.0, step=0.5, value=4.0, label="רדיוס מיזוג חום (Thermal Diffusion)")
                            hm_btn = gr.Button("🌡️ ייצר מפת חום (SVG + PNG)", variant="primary")

                        with gr.Column(scale=1):
                            hm_prev = gr.HTML(label="תצוגה מקדימה")
                            hm_swatches = gr.HTML(label="ספקטרום צבעים")
                            with gr.Row():
                                hm_out_svg = gr.File(label="📥 הורדת SVG")
                                hm_out_png = gr.File(label="🖼️ הורדת PNG")

                    hm_btn.click(
                        fn=generate_heatmap_room,
                        inputs=[hm_img, hm_style, hm_pal, hm_res, hm_blur, user_mode_radio],
                        outputs=[hm_prev, hm_swatches, hm_out_svg, hm_out_png]
                    )

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
                    r2_c_btn.click(
                        fn=generate_contours,
                        inputs=[r2_c_img, r2_c_levels, r2_c_blur, r2_c_stroke, r2_c_bg, user_mode_radio],
                        outputs=[r2_c_prev, r2_c_svg, r2_c_png]
                    )

                with gr.Tab("🌊 טקסטורות עומק גיאומטריות (AI)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r2_d_img = gr.Image(label="העלאת תמונה", type="filepath")
                            r2_d_grid = gr.Slider(minimum=10, maximum=25, step=1, value=15, label="צפיפות רשת הגיאומטריה")
                            r2_d_shape = gr.Dropdown(choices=["Circles", "Squares", "Hexagons", "Lines"], value="Circles", label="צורת בסיס")
                            r2_d_btn = gr.Button("ייצר טקסטורת עומק (SVG + PNG)", variant="primary")
                        with gr.Column(scale=1):
                            r2_d_prev = gr.HTML(label="תצוגה מקדימה")
                            with gr.Row():
                                r2_d_svg = gr.File(label="📥 הורדת SVG")
                                r2_d_png = gr.File(label="🖼️ הורדת PNG")
                    r2_d_btn.click(
                        fn=generate_depth_texture,
                        inputs=[r2_d_img, r2_d_grid, r2_d_shape, user_mode_radio],
                        outputs=[r2_d_prev, r2_d_svg, r2_d_png]
                    )

        # ==========================================
        # אגף ג': מחוללים מתמטיים
        # ==========================================
        with gr.Tab("📐 אגף ג': מחוללים מתמטיים (Wave, Voxel, Guilloche)"):
            with gr.Tabs():
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
                    r3_w_btn.click(
                        fn=generate_waveform,
                        inputs=[r3_w_img, r3_w_lines, r3_w_amp, r3_w_col, user_mode_radio],
                        outputs=[r3_w_prev, r3_w_svg, r3_w_png]
                    )

                with gr.Tab("🧊 פסל אדריכלי תלת-ממדי (Voxel Art)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r3_i_img = gr.Image(label="העלאת תמונה", type="filepath")
                            r3_i_w = gr.Slider(minimum=10, maximum=100, step=1, value=45, label="רזולוציה (קוביות לרוחב)")
                            r3_i_ext = gr.Slider(minimum=0, maximum=150, step=5, value=45, label="בליטה תלת-ממדית (Z-Extrusion)")
                            r3_i_gap = gr.Slider(minimum=0, maximum=6, step=0.5, value=1, label="ריווח בין עמודים")
                            r3_i_btn = gr.Button("ייצר פסל תלת-ממדי (SVG + PNG)", variant="primary")
                        with gr.Column(scale=1):
                            r3_i_prev = gr.HTML(label="תצוגה מקדימה")
                            r3_i_swatches = gr.HTML(label="דוגמיות צבע")
                            with gr.Row():
                                r3_i_svg = gr.File(label="📥 הורדת SVG")
                                r3_i_png = gr.File(label="🖼️ הורדת PNG")
                    r3_i_btn.click(
                        fn=generate_iso_voxels,
                        inputs=[r3_i_img, r3_i_w, r3_i_ext, r3_i_gap, user_mode_radio],
                        outputs=[r3_i_prev, r3_i_swatches, r3_i_svg, r3_i_png]
                    )

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
                    r3_g_btn.click(
                        fn=generate_adaptive_guilloche,
                        inputs=[r3_g_img, r3_g_col, r3_g_R, r3_g_rot, user_mode_radio],
                        outputs=[r3_g_prev, r3_g_swatches, r3_g_svg, r3_g_png]
                    )

        # ==========================================
        # אגף ד': Panel Connector, אריזה ודפוס
        # ==========================================
        with gr.Tab("🧩 אגף ד': מחברים מכניים (Panel Connector), אריזה ודפוס"):
            with gr.Tabs():

                with gr.Tab("🔗 Panel Connector (מחולל אריחים ומחברים מכניים פרמטריים)"):
                    with gr.Row():
                        with gr.Column(scale=1):
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
                                    "גלים פרמטריים משתלבים (Parametric Wave Lattice)",
                                    "אריח חלק ללא חריטה פנימית (Solid Mechanical Tile)"
                                ],
                                value="עורקי עלים אורגניים (Organic Venation)",
                                label="פאטרן אורגני פנימי"
                            )
                            with gr.Row():
                                pc_size = gr.Slider(minimum=40, maximum=200, step=5, value=90, label="גודל אריח (מ\"מ)")
                                pc_scale = gr.Slider(minimum=0.6, maximum=1.5, step=0.1, value=1.0, label="גודל שן מחבר")
                            with gr.Row():
                                pc_density = gr.Slider(minimum=4, maximum=24, step=2, value=12, label="צפיפות פאטרן פנימי")
                                pc_thick = gr.Slider(minimum=1.5, maximum=8.0, step=0.5, value=3.0, label="עובי אריח ל-STL (מ\"מ)")
                            pc_btn = gr.Button("⚙️ ייצר אריח מכני (SVG + PNG + 3D STL)", variant="primary")

                        with gr.Column(scale=1):
                            pc_prev = gr.HTML(label="שרטוט וקטורי של האריח")
                            pc_stl_view = gr.Model3D(label="הדמיית STL תלת-ממדית של האריח")
                            with gr.Row():
                                pc_out_svg = gr.File(label="📥 הורדת SVG (לחיתוך/בלנדר)")
                                pc_out_png = gr.File(label="🖼️ הורדת PNG")
                                pc_out_stl = gr.File(label="📦 הורדת STL (ל-Bambu Lab)")

                    pc_btn.click(
                        fn=generate_panel_connector,
                        inputs=[pc_shape, pc_joint, pc_pattern, pc_size, pc_scale, pc_density, pc_thick, user_mode_radio],
                        outputs=[pc_prev, pc_stl_view, pc_out_svg, pc_out_png, pc_out_stl]
                    )

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
                    r4_d_btn.click(
                        fn=generate_custom_dieline,
                        inputs=[r4_d_file, r4_d_shape, r4_d_w, r4_d_h, r4_d_d, r4_d_mode, r4_d_specs, user_mode_radio],
                        outputs=[r4_d_prev, r4_d_svg, r4_d_png]
                    )

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
                    r4_r_btn.click(
                        fn=generate_print_marks,
                        inputs=[r4_r_file, r4_r_w, r4_r_h, r4_r_b, r4_r_theme, user_mode_radio],
                        outputs=[r4_r_prev, r4_r_svg, r4_r_png]
                    )

        # ==========================================
        # אגף ה': Gentype Studio (מחולל טיפוגרפיה)
        # ==========================================
        with gr.Tab("🔤 אגף ה': Gentype Studio (טיפוגרפיה גנרטיבית)"):
            with gr.Row():
                with gr.Column(scale=1):
                    gt_text = gr.Textbox(value="MAI STUDIO", label="הזנת אותיות / מילה (עברית או אנגלית)")
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
                            "Gemini AI SVG Typography (דורש מכסת API)"
                        ],
                        value="מנוע וקטורי פרמטרי מיידי (ללא תלות במכסת API)",
                        label="מנוע ייצור"
                    )
                    gt_theme = gr.Textbox(placeholder="תיאור חופשי נוסף (למצב AI): למשל מתכת נוזלית, קוצים, זכוכית...", label="הנחיית עיצוב נוספת (אופציונלי)")
                    with gr.Row():
                        gt_col1 = gr.ColorPicker(value="#e86c52", label="צבע ראשי")
                        gt_col2 = gr.ColorPicker(value="#00e5ff", label="צבע משני / הדגשה")
                    gt_btn = gr.Button("✨ ייצר טיפוגרפיה גנרטיבית (SVG + PNG)", variant="primary")

                with gr.Column(scale=1):
                    gt_prev = gr.HTML(label="תצוגת טיפוגרפיה")
                    with gr.Row():
                        gt_svg = gr.File(label="📥 הורדת SVG וקטורי")
                        gt_png = gr.File(label="🖼️ הורדת PNG")

            gt_btn.click(
                fn=generate_gentype_typography,
                inputs=[gt_text, gt_style, gt_theme, gt_engine, gt_col1, gt_col2, user_mode_radio],
                outputs=[gt_prev, gt_svg, gt_png]
            )

        # ==========================================
        # אגף ו': גלריית היסטוריה ל-7 ימים
        # ==========================================
        with gr.Tab("🗂️ אגף ו': גלריית היסטוריה (שמירה ל-7 ימים)"):
            gr.Markdown("### ארכיון התוצרים של הסטודיו (קבצים שנוצרו ב-7 הימים האחרונים במצב משתמשת רשומה)")
            hist_refresh_btn = gr.Button("🔄 רענן גלריה ובדוק קבצים שמורים", variant="primary")
            hist_info = gr.HTML()
            with gr.Row():
                hist_gallery = gr.Gallery(label="תצוגה מקדימה של תוצרים שמורים", columns=4, height="auto")
                hist_files = gr.File(label="הורדת קבצים מהארכיון (SVG / PNG / STL)")

            hist_refresh_btn.click(fn=get_history_display, inputs=[], outputs=[hist_gallery, hist_files, hist_info])

port = int(os.environ.get("PORT", 7860))
master_studio.launch(server_name="0.0.0.0", server_port=port)
