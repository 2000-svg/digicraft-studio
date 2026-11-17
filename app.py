import os
import gradio as gr
import google.generativeai as genai
import PIL.Image
import numpy as np
from skimage import measure
from skimage.filters import gaussian
import math
import base64
import re

api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# ==========================================
# פונקציות עזר גלובליות
# ==========================================
def rgb_to_hex(r, g, b):
    return '#{:02x}{:02x}{:02x}'.format(int(r), int(g), int(b))

def adjust_color(r, g, b, factor):
    return '#{:02x}{:02x}{:02x}'.format(
        int(max(0, min(255, r * factor))),
        int(max(0, min(255, g * factor))),
        int(max(0, min(255, b * factor)))
    )

def get_luminance(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b

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


# ==========================================
# חדר 1: מטריצת פיקסלים (טקסטיל, הלפטון ו-ASCII)
# ==========================================
def generate_pixel_matrix(image_path, grid_width, num_colors, style):
    try:
        img = PIL.Image.open(image_path).convert('RGB')
        w, h = img.size
        aspect_ratio = h / w
        grid_height = int(grid_width * aspect_ratio)
        
        img_small = img.resize((grid_width, grid_height), PIL.Image.Resampling.LANCZOS)
        img_quantized = img_small.quantize(colors=num_colors, method=PIL.Image.MEDIANCUT).convert('RGB')
        pixels = img_quantized.load()
        
        cell_size = 12 
        svg_width = grid_width * cell_size
        svg_height = grid_height * cell_size
        
        svg_lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}" width="100%" height="100%">']
        svg_lines.append(f'<rect width="{svg_width}" height="{svg_height}" fill="#fafafa"/>')
        
        unique_colors = set()
        ascii_chars = "@%#*+=-:. "
        
        if style == "ASCII Art (טיפוגרפיה)":
            svg_lines.append('<g font-family="monospace" font-weight="bold" font-size="12" text-anchor="middle" dominant-baseline="central">')
        else:
            svg_lines.append('<g>')

        for y in range(grid_height):
            for x in range(grid_width):
                r, g, b = pixels[x, y]
                lum = get_luminance(r, g, b)
                
                if r > 245 and g > 245 and b > 245 and style != "Dotted Halftone (נקודות)":
                    continue
                    
                hex_color = rgb_to_hex(r, g, b)
                unique_colors.add(hex_color)
                
                px = x * cell_size
                py = y * cell_size
                cx = px + cell_size / 2
                cy = py + cell_size / 2
                
                if style == "רקמת איקסים (Cross-Stitch)":
                    svg_lines.append(f'<path d="M {px+2} {py+2} L {px+cell_size-2} {py+cell_size-2} M {px+cell_size-2} {py+2} L {px+2} {py+cell_size-2}" stroke="{hex_color}" stroke-width="1.5" fill="none"/>')
                elif style == "גובלן / שטיח (Tapestry)":
                    svg_lines.append(f'<rect x="{px}" y="{py}" width="{cell_size}" height="{cell_size}" fill="{hex_color}" stroke="#dddddd" stroke-width="0.5"/>')
                elif style == "סריגה (Knitting)":
                    svg_lines.append(f'<path d="M {px+2} {py+2} L {cx} {py+cell_size-2} L {px+cell_size-2} {py+2}" stroke="{hex_color}" stroke-width="2" fill="none" stroke-linecap="round"/>')
                elif style == "ASCII Art (טיפוגרפיה)":
                    char_idx = int((lum / 255) * (len(ascii_chars) - 1))
                    char = ascii_chars[char_idx]
                    if char != " ": 
                        svg_lines.append(f'<text x="{cx}" y="{cy}" fill="{hex_color}">{char}</text>')
                elif style == "Dotted Halftone (נקודות)":
                    radius = (cell_size / 2) * (1 - (lum / 255))
                    if radius > 0.5:
                        svg_lines.append(f'<circle cx="{cx}" cy="{cy}" r="{radius:.2f}" fill="{hex_color}"/>')
        
        svg_lines.append('</g></svg>')
        svg_code = "\n".join(svg_lines)
        
        output_filename = "room1_pixel_matrix.svg"
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(svg_code)
            
        preview_html = f'<div style="padding:20px; border:1px solid #ccc; max-width: 550px; margin: auto; background:white;">{svg_code}</div>'
        color_palette = f"**פלטת צבעים/חוטים ({len(unique_colors)} צבעים):** {', '.join(list(unique_colors))}"
        
        return preview_html, output_filename, color_palette
    except Exception as e:
        return f"<p style='color:red;'>Error: {str(e)}</p>", None, ""


# ==========================================
# חדר 2: טופוגרפיה ועומק (Contour Lines & AI Depth)
# ==========================================
def generate_contours(image_path, num_levels, blur_sigma):
    try:
        img = PIL.Image.open(image_path).convert('L') 
        img_array = np.array(img)
        smoothed = gaussian(img_array, sigma=blur_sigma, preserve_range=True)
        height, width = smoothed.shape
        
        svg_lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">']
        svg_lines.append(f'<rect width="{width}" height="{height}" fill="#ffffff"/>')
        
        levels = np.linspace(0, 255, num_levels + 2)[1:-1]
        for level in levels:
            contours = measure.find_contours(smoothed, level)
            for contour in contours:
                path_data = "M " + " L ".join([f"{col:.1f} {row:.1f}" for row, col in contour])
                svg_lines.append(f'<path d="{path_data}" stroke="#222222" stroke-width="1.5" fill="none" vector-effect="non-scaling-stroke"/>')
                
        svg_lines.append('</svg>')
        svg_code = "\n".join(svg_lines)
        
        output_filename = "room2_topography_contours.svg"
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(svg_code)
            
        preview = f'<div style="background:white; padding:20px; border:1px solid #ccc; max-width: 550px; margin: auto;">{svg_code}</div>'
        return preview, output_filename
    except Exception as e:
        return f"<p style='color:red;'>Error: {str(e)}</p>", None

def generate_depth_texture(image_path, grid_size, shape_type):
    try:
        if not os.environ.get("GEMINI_API_KEY"):
            return "<p style='color:red;'>שגיאה: מפתח GEMINI_API_KEY לא הוגדר ב-Environment Variables של השרת.</p>", None
            
        img = PIL.Image.open(image_path)
        model = genai.GenerativeModel('gemini-2.5-pro')
        
        prompt = f"""
        You are an expert computational designer. Analyze the depth and brightness of the attached image.
        Translate this visual data into a parametric 2D SVG texture.
        Strict Technical Requirements:
        1. Grid constraints: Create a grid of {grid_size}x{grid_size} geometric elements.
        2. Shape type: Use {shape_type} as the primary repeating element.
        3. Parametric mapping: The size (radius/scale) or stroke-width of each {shape_type} MUST correspond directly to the brightness or perceived depth of that specific area in the image.
        4. Style: Monochrome (black shapes on a transparent background).
        5. Clean code: Output ONLY the raw valid SVG code starting with <svg> and ending with </svg>. Do not wrap in ```svg tags. No explanations.
        """
        
        response = model.generate_content([prompt, img])
        svg_code = re.sub(r'```(?:xml|svg)?\n|```', '', response.text).strip()
        
        output_filename = "room2_parametric_depth.svg"
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(svg_code)
            
        preview_html = f'<div style="background:#ffffff; padding:20px; border:1px solid #ccc; max-width: 550px; margin: auto; border-radius: 8px;">{svg_code}</div>'
        return preview_html, output_filename
    except Exception as e:
        return f"<p style='color:red;'>Error: {str(e)}</p>", None


# ==========================================
# חדר 3: מחוללים מתמטיים מבוססי תמונה
# ==========================================
def generate_waveform(image_path, num_lines, amp, color):
    try:
        img = PIL.Image.open(image_path).convert('RGB')
        w, h = 800, int(800 * (img.height / img.width))
        res_x = 100
        img_small = img.resize((res_x, num_lines), PIL.Image.Resampling.LANCZOS)
        pixels = img_small.load()
        
        svg = [f'<svg xmlns="[http://www.w3.org/2000/svg](http://www.w3.org/2000/svg)" viewBox="0 0 {w} {h}" width="100%" height="100%">']
        svg.append(f'<rect width="{w}" height="{h}" fill="#fafafa"/>')
        
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
                path_pts.append(f"{px:.1f},{py:.1f}")
                
            path_d = "M " + " L ".join(path_pts)
            svg.append(f'<path d="{path_d}" stroke="{color}" stroke-width="1.5" fill="none" vector-effect="non-scaling-stroke"/>')
            
        svg.append('</svg>')
        svg_code = "\n".join(svg)
        
        output_filename = "room3_waveform_art.svg"
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(svg_code)
            
        preview = f'<div style="background:white; padding:20px; border:1px solid #ccc; max-width: 550px; margin: auto;">{svg_code}</div>'
        return preview, output_filename
    except Exception as e:
        return f"<p style='color:red;'>Error: {str(e)}</p>", None

def generate_iso_voxels(image_path, grid_width, extrusion, gap):
    try:
        img = PIL.Image.open(image_path).convert('RGB')
        aspect = img.height / img.width
        grid_height = int(grid_width * aspect)
        
        img_small = img.resize((grid_width, grid_height), PIL.Image.Resampling.LANCZOS)
        img_quantized = img_small.quantize(colors=15, dither=PIL.Image.Dither.NONE).convert('RGB')
        pixels = img_quantized.load()
        
        step_w = 10
        step_h = 5
        base_h = 5 
        
        min_x = -grid_height * step_w
        max_x = grid_width * step_w
        min_y = -extrusion - base_h - step_h
        max_y = (grid_width + grid_height) * step_h + extrusion
        
        svg_w = max_x - min_x + (step_w * 4)
        svg_h = max_y - min_y + (step_h * 4)
        
        svg = [f'<svg xmlns="[http://www.w3.org/2000/svg](http://www.w3.org/2000/svg)" viewBox="{min_x - step_w*2} {min_y - step_h*2} {svg_w} {svg_h}" width="100%" height="100%">']
        
        dw = step_w - gap
        dh = step_h - (gap / 2.0)
        stroke_width = "0.4" if gap == 0 else "0"
        
        for y in range(grid_height):
            for x in range(grid_width):
                r, g, b = pixels[x, y]
                if r > 240 and g > 240 and b > 240:
                    continue
                
                lum = get_luminance(r, g, b)
                h_z = base_h + (lum / 255.0) * extrusion
                
                color_top = adjust_color(r, g, b, 1.0)
                color_left = adjust_color(r, g, b, 0.85)
                color_right = adjust_color(r, g, b, 0.65)
                
                cx = (x - y) * step_w
                cy = (x + y) * step_h
                rx, ry = cx, cy - h_z
                
                p_left = f"{rx - dw},{ry} {rx},{ry + dh} {cx},{cy + dh} {cx - dw},{cy}"
                p_right = f"{rx},{ry + dh} {rx + dw},{ry} {cx + dw},{cy} {cx},{cy + dh}"
                p_top = f"{rx},{ry - dh} {rx + dw},{ry} {rx},{ry + dh} {rx - dw},{ry}"
                
                svg.append(f'<polygon points="{p_left}" fill="{color_left}" stroke="{color_left}" stroke-width="{stroke_width}" stroke-linejoin="round"/>')
                svg.append(f'<polygon points="{p_right}" fill="{color_right}" stroke="{color_right}" stroke-width="{stroke_width}" stroke-linejoin="round"/>')
                svg.append(f'<polygon points="{p_top}" fill="{color_top}" stroke="{color_top}" stroke-width="{stroke_width}" stroke-linejoin="round"/>')
                
        svg.append('</svg>')
        svg_code = "\n".join(svg)
        
        output_filename = "room3_voxels.svg"
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(svg_code)
            
        preview = f'<div style="background:#e9e9e9; padding:20px; border:1px solid #ccc; max-width: 550px; margin: auto; overflow: hidden;">{svg_code}</div>'
        return preview, output_filename
    except Exception as e:
        return f"<p style='color:red;'>Error: {str(e)}</p>", None

def generate_adaptive_guilloche(image_path, num_colors, base_R, rotations):
    try:
        img = PIL.Image.open(image_path).convert('RGB')
        w, h = 800, 800
        img_resized = img.resize((w, h), PIL.Image.Resampling.LANCZOS)
        
        img_q = img_resized.quantize(colors=num_colors, method=PIL.Image.MEDIANCUT).convert('RGB')
        pixels = img_q.load()
        
        colors_counts = img_q.getcolors(maxcolors=256)
        colors_counts.sort(key=lambda x: x[0], reverse=True)
        unique_colors = [c[1] for c in colors_counts[:num_colors]]
        
        svg = [f'<svg xmlns="[http://www.w3.org/2000/svg](http://www.w3.org/2000/svg)" viewBox="0 0 {w} {h}" width="100%" height="100%">']
        svg.append(f'<rect width="{w}" height="{h}" fill="#111111"/>')
        
        cx, cy = w / 2, h / 2
        steps = int(rotations * 150) 
        
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
                        svg.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{hex_col}" stroke-width="1.2"/>')
                        
        svg.append('</svg>')
        svg_code = "\n".join(svg)
        
        output_filename = "room3_adaptive_guilloche.svg"
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(svg_code)
            
        preview = f'<div style="background:white; padding:20px; border:1px solid #ccc; max-width: 550px; margin: auto;">{svg_code}</div>'
        return preview, output_filename
    except Exception as e:
        return f"<p style='color:red;'>Error: {str(e)}</p>", None


# ==========================================
# חדר 4: פריסות אריזה וסימני דפוס (Dielines & Reg Marks)
# ==========================================
def generate_custom_dieline(file_path, shape_type, w, h, d, graphic_mode, show_specs):
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

        svg = [f'<svg xmlns="[http://www.w3.org/2000/svg](http://www.w3.org/2000/svg)" viewBox="0 0 {canvas_w} {canvas_h}" width="100%" height="100%">']
        svg.append('''<style>
            .cut { stroke: #ff1744; stroke-width: 1.5; fill: none; stroke-linejoin: round; }
            .fold { stroke: #00e5ff; stroke-width: 1.2; stroke-dasharray: 5,4; fill: none; }
            .spec { stroke: #888888; stroke-width: 0.6; fill: none; }
            .spec-txt { fill: #555555; font-family: monospace; font-size: 8px; text-anchor: middle; }
        </style>''')
        svg.append(f'<rect width="{canvas_w}" height="{canvas_h}" fill="#141414"/>')
        
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
            svg.append(f'<text class="spec-txt" x="65" y="15">DIGICRAFT_DIE_V4.2</text>')
            svg.append('</g>')

        svg.append('</svg>')
        svg_code = "\n".join(svg)
        
        output_filename = "room4_custom_dieline.svg"
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(svg_code)
            
        preview = f'<div style="background:#141414; padding:15px; border:1px solid #444; max-width: 600px; margin: auto; border-radius:8px;">{svg_code}</div>'
        return preview, output_filename
    except Exception as e:
        return f"<p style='color:red;'>Error: {str(e)}</p>", None

def generate_print_marks(file_path, artboard_w, artboard_h, bleed, style_theme):
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
        
        svg = [f'<svg xmlns="[http://www.w3.org/2000/svg](http://www.w3.org/2000/svg)" viewBox="0 0 {canvas_w} {canvas_h}" width="100%" height="100%">']
        svg.append(f'<style>.reg {{ stroke: {mark_col}; stroke-width: 0.8; fill: none; }} .bleed {{ stroke: {bleed_col}; stroke-width: 0.7; stroke-dasharray: 4,3; fill: none; }} .txt {{ fill: {mark_col}; font-family: monospace; font-size: 6px; }}</style>')
        svg.append(f'<rect width="{canvas_w}" height="{canvas_h}" fill="{bg_col}"/>')
        
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
        output_filename = "room4_registration_filter.svg"
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(svg_code)
            
        preview = f'<div style="background:{bg_col}; padding:15px; border:1px solid #ccc; max-width: 550px; margin: auto; border-radius:8px;">{svg_code}</div>'
        return preview, output_filename
    except Exception as e:
        return f"<p style='color:red;'>Error: {str(e)}</p>", None


# ==========================================
# ממשק האב המאוחד: DigiCraft Matrix
# ==========================================
with gr.Blocks(title="DigiCraft Matrix", theme=gr.themes.Soft()) as master_studio:
    gr.Markdown("<h1 style='text-align: center;'>🎛️ DigiCraft Matrix</h1>")
    gr.Markdown("<h4 style='text-align: center;'>סטודיו לעיצוב דאטה, טקסטיל פרמטרי, גיאומטריה וייצור דיגיטלי (Pixel-to-Vector)</h4>")
    
    with gr.Tabs():
        
        with gr.Tab("🧶 חדר 1: מטריצת פיקסלים (טקסטיל, ASCII והלפטון)"):
            with gr.Row():
                with gr.Column(scale=1):
                    r1_img = gr.Image(label="העלאת תמונה", type="filepath")
                    r1_style = gr.Radio(
                        choices=[
                            "רקמת איקסים (Cross-Stitch)", 
                            "גובלן / שטיח (Tapestry)", 
                            "סריגה (Knitting)",
                            "ASCII Art (טיפוגרפיה)",
                            "Dotted Halftone (נקודות)"
                        ], 
                        value="גובלן / שטיח (Tapestry)", 
                        label="סגנון המרה וקטורית"
                    )
                    r1_grid = gr.Slider(minimum=10, maximum=150, step=1, value=50, label="צפיפות רשת (Grid Resolution)")
                    r1_colors = gr.Slider(minimum=1, maximum=25, step=1, value=6, label="כמות צבעים בפלטה")
                    r1_btn = gr.Button("ייצר מטריצת פיקסלים (SVG)", variant="primary")
                    
                with gr.Column(scale=1):
                    r1_preview = gr.HTML(label="תצוגה מקדימה")
                    r1_palette = gr.Markdown()
                    r1_out = gr.File(label="הורדת קובץ SVG")
                    
            r1_btn.click(fn=generate_pixel_matrix, inputs=[r1_img, r1_grid, r1_colors, r1_style], outputs=[r1_preview, r1_out, r1_palette])

        with gr.Tab("⛰️ חדר 2: טופוגרפיה ועומק (Contours & AI)"):
            with gr.Tabs():
                with gr.Tab("🗺️ קווי גובה טופוגרפיים (Isolines)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r2_c_img = gr.Image(label="העלאת תמונה", type="filepath")
                            r2_c_levels = gr.Slider(minimum=3, maximum=30, step=1, value=12, label="מספר שכבות גובה (Levels)")
                            r2_c_blur = gr.Slider(minimum=1, maximum=15, step=0.5, value=5, label="החלקת צורות אורגניות (Blur)")
                            r2_c_btn = gr.Button("ייצר קווי מתאר טופוגרפיים", variant="primary")
                        with gr.Column(scale=1):
                            r2_c_prev = gr.HTML(label="תצוגה מקדימה")
                            r2_c_out = gr.File(label="הורדת SVG לחיתוך")
                    r2_c_btn.click(fn=generate_contours, inputs=[r2_c_img, r2_c_levels, r2_c_blur], outputs=[r2_c_prev, r2_c_out])

                with gr.Tab("🌊 טקסטורות עומק גיאומטריות (AI)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r2_d_img = gr.Image(label="העלאת תמונה", type="filepath")
                            r2_d_grid = gr.Slider(minimum=10, maximum=25, step=1, value=15, label="צפיפות רשת הגיאומטריה")
                            r2_d_shape = gr.Dropdown(choices=["Circles", "Squares", "Hexagons", "Lines"], value="Circles", label="צורת בסיס")
                            r2_d_btn = gr.Button("ייצר טקסטורת עומק", variant="primary")
                        with gr.Column(scale=1):
                            r2_d_prev = gr.HTML(label="תצוגה מקדימה")
                            r2_d_out = gr.File(label="הורדת קובץ SVG")
                    r2_d_btn.click(fn=generate_depth_texture, inputs=[r2_d_img, r2_d_grid, r2_d_shape], outputs=[r2_d_prev, r2_d_out])

        with gr.Tab("📐 חדר 3: מחוללים מתמטיים (Wave, Voxel, Guilloche)"):
            with gr.Tabs():
                with gr.Tab("〰️ גלי קול (Waveform)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r3_w_img = gr.Image(label="העלאת תמונה", type="filepath")
                            r3_w_lines = gr.Slider(minimum=20, maximum=150, step=1, value=60, label="מספר שורות (צפיפות)")
                            r3_w_amp = gr.Slider(minimum=5, maximum=100, step=1, value=30, label="גובה הגל")
                            r3_w_col = gr.ColorPicker(value="#1a1a1a", label="צבע הקווים")
                            r3_w_btn = gr.Button("ייצר וקטור גלים", variant="primary")
                        with gr.Column(scale=1):
                            r3_w_prev = gr.HTML(label="תצוגה מקדימה")
                            r3_w_out = gr.File(label="הורדת SVG")
                    r3_w_btn.click(fn=generate_waveform, inputs=[r3_w_img, r3_w_lines, r3_w_amp, r3_w_col], outputs=[r3_w_prev, r3_w_out])

                with gr.Tab("🧊 פסל אדריכלי תלת-ממדי (Voxel Art)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r3_i_img = gr.Image(label="העלאת תמונה", type="filepath")
                            r3_i_w = gr.Slider(minimum=10, maximum=120, step=1, value=45, label="רזולוציה (קוביות לרוחב)")
                            r3_i_ext = gr.Slider(minimum=0, maximum=150, step=5, value=40, label="בליטה תלת-ממדית (Z-Extrusion)")
                            r3_i_gap = gr.Slider(minimum=0, maximum=6, step=0.5, value=1, label="ריווח בין עמודים")
                            r3_i_btn = gr.Button("ייצר פסל תלת-ממדי", variant="primary")
                        with gr.Column(scale=1):
                            r3_i_prev = gr.HTML(label="תצוגה מקדימה")
                            r3_i_out = gr.File(label="הורדת SVG")
                    r3_i_btn.click(fn=generate_iso_voxels, inputs=[r3_i_img, r3_i_w, r3_i_ext, r3_i_gap], outputs=[r3_i_prev, r3_i_out])

                with gr.Tab("🌸 גיליושה אדפטיבית (Adaptive Geometry)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r3_g_img = gr.Image(label="העלאת תמונה", type="filepath")
                            r3_g_col = gr.Slider(minimum=2, maximum=12, step=1, value=4, label="מספר טקסטורות (צבעים)")
                            r3_g_R = gr.Slider(minimum=100, maximum=400, step=1, value=250, label="רדיוס מאסטר (Master R)")
                            r3_g_rot = gr.Slider(minimum=10, maximum=300, step=1, value=150, label="צפיפות סיבובים")
                            r3_g_btn = gr.Button("ייצר רוזטה אדפטיבית", variant="primary")
                        with gr.Column(scale=1):
                            r3_g_prev = gr.HTML(label="תצוגה מקדימה")
                            r3_g_out = gr.File(label="הורדת SVG")
                    r3_g_btn.click(fn=generate_adaptive_guilloche, inputs=[r3_g_img, r3_g_col, r3_g_R, r3_g_rot], outputs=[r3_g_prev, r3_g_out])

        with gr.Tab("✂️ חדר 4: פריסות אריזה וסימני דפוס (Dielines & Reg Marks)"):
            with gr.Tabs():
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
                            r4_d_btn = gr.Button("הלבש פילטר פריסה (SVG)", variant="primary")
                        with gr.Column(scale=1):
                            r4_d_prev = gr.HTML(label="תצוגה מקדימה")
                            r4_d_out = gr.File(label="הורדת קובץ SVG")
                    r4_d_btn.click(fn=generate_custom_dieline, inputs=[r4_d_file, r4_d_shape, r4_d_w, r4_d_h, r4_d_d, r4_d_mode, r4_d_specs], outputs=[r4_d_prev, r4_d_out])

                with gr.Tab("🎯 פילטר סימני רישום וכוונות (Registration Overlay)"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            r4_r_file = gr.File(label="העלאת תמונה / SVG", file_types=["image", ".svg"], type="filepath")
                            r4_r_theme = gr.Radio(choices=["Classic Pre-Press (Light)", "Dark Cyber / Acid Print"], value="Dark Cyber / Acid Print", label="סגנון אסתטי")
                            r4_r_w = gr.Slider(minimum=50, maximum=500, step=10, value=210, label="רוחב קנבס (Width mm)")
                            r4_r_h = gr.Slider(minimum=50, maximum=500, step=10, value=297, label="גובה קנבס (Height mm)")
                            r4_r_b = gr.Slider(minimum=0, maximum=20, step=1, value=5, label="שולי גלישה (Bleed mm)")
                            r4_r_btn = gr.Button("הלבש פילטר רישום ודפוס", variant="primary")
                        with gr.Column(scale=1):
                            r4_r_prev = gr.HTML(label="תצוגה מקדימה")
                            r4_r_out = gr.File(label="הורדת קובץ SVG")
                    r4_r_btn.click(fn=generate_print_marks, inputs=[r4_r_file, r4_r_w, r4_r_h, r4_r_b, r4_r_theme], outputs=[r4_r_prev, r4_r_out])

port = int(os.environ.get("PORT", 7860))
master_studio.launch(server_name="0.0.0.0", server_port=port)
