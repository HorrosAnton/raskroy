# -*- coding: utf-8 -*-
import sys, os, json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, simpledialog, colorchooser
from dataclasses import dataclass, field
from copy import deepcopy
from PIL import Image, ImageDraw, ImageFont, ImageTk


# ===================== МОДЕЛИ ДАННЫХ =====================

@dataclass
class Part:
    width: int
    height: int
    qty: int = 1
    label: str = ""
    can_rotate: bool = True
    @property
    def area(self): return self.width * self.height

@dataclass
class Sheet:
    width: int
    height: int
    price: float
    label: str = ""
    decor: str = ""
    @property
    def area(self): return self.width * self.height

@dataclass
class Placement:
    x: int
    y: int
    width: int
    height: int
    part_label: str
    rotated: bool = False

@dataclass
class Waste:
    x: int
    y: int
    width: int
    height: int
    is_useful: bool = False
    @property
    def area(self): return self.width * self.height

@dataclass
class SheetLayout:
    sheet: Sheet
    placements: list = field(default_factory=list)
    wastes: list = field(default_factory=list)
    cuts_count: int = 0
    @property
    def used_area(self): return sum(p.width * p.height for p in self.placements)
    @property
    def efficiency(self):
        if self.sheet.area == 0: return 0.0
        return round(self.used_area / self.sheet.area * 100, 1)

@dataclass
class CuttingResult:
    layouts: list = field(default_factory=list)
    unplaced_parts: list = field(default_factory=list)
    cut_price: float = 0
    kerf: int = 0
    @property
    def total_sheets_cost(self): return sum(l.sheet.price for l in self.layouts)
    @property
    def total_cuts_count(self): return sum(l.cuts_count for l in self.layouts)
    @property
    def total_cuts_cost(self): return self.total_cuts_count * self.cut_price
    @property
    def total_cost(self): return self.total_sheets_cost + self.total_cuts_cost
    @property
    def total_efficiency(self):
        used = sum(l.used_area for l in self.layouts)
        total = sum(l.sheet.area for l in self.layouts)
        return round(used / total * 100, 1) if total else 0.0


# ===================== КАТАЛОГ ДЕКОРОВ =====================

DEFAULT_DECORS = {
    'Белый': {
        'color_code': '#FFFFFF',
        'border_color': '#CCCCCC',
        'sheets': [
            [2700, 100, 645], [2700, 300, 1093], [2700, 400, 1324],
            [2700, 500, 1865], [2700, 600, 2082], [2000, 300, 683],
            [2000, 400, 910], [2000, 500, 1238], [2000, 600, 1405],
            [1200, 300, 626], [1200, 400, 754], [800, 200, 276],
            [800, 300, 335], [800, 400, 432], [600, 300, 264],
            [600, 200, 218],
        ]
    },
    'Белый Премиум': {
        'color_code': '#F5F5F0',
        'border_color': '#D4AF37',
        'sheets': [
            [2700, 100, 710], [2700, 300, 1200], [2700, 400, 1456],
            [2700, 500, 2050], [2700, 600, 2290], [2000, 300, 750],
            [2000, 400, 1000], [2000, 500, 1360], [2000, 600, 1545],
            [1200, 300, 688], [1200, 400, 830], [800, 200, 303],
            [800, 300, 368], [800, 400, 475], [600, 300, 290],
            [600, 200, 240],
        ]
    },
    'Дуб Сонома': {
        'color_code': '#C4A882',
        'border_color': '#8B6914',
        'sheets': [
            [2700, 100, 680], [2700, 300, 1155], [2700, 400, 1400],
            [2700, 500, 1970], [2700, 600, 2200], [2000, 300, 720],
            [2000, 400, 960], [2000, 500, 1310], [2000, 600, 1485],
            [1200, 300, 662], [1200, 400, 797], [800, 200, 292],
            [800, 300, 354], [800, 400, 457], [600, 300, 279],
            [600, 200, 230],
        ]
    },
    'Бетон': {
        'color_code': '#A0A0A0',
        'border_color': '#666666',
        'sheets': [
            [2700, 100, 695], [2700, 300, 1180], [2700, 400, 1430],
            [2700, 500, 2015], [2700, 600, 2250], [2000, 300, 740],
            [2000, 400, 985], [2000, 500, 1340], [2000, 600, 1520],
            [1200, 300, 678], [1200, 400, 816], [800, 200, 299],
            [800, 300, 363], [800, 400, 468], [600, 300, 286],
            [600, 200, 236],
        ]
    },
}


def get_config_path():
    home = os.path.expanduser('~')
    cfg_dir = os.path.join(home, '.cutting_optimizer')
    if not os.path.exists(cfg_dir):
        os.makedirs(cfg_dir)
    return os.path.join(cfg_dir, 'decors.json')


def save_decors(decors):
    try:
        with open(get_config_path(), 'w', encoding='utf-8') as f:
            json.dump(decors, f, ensure_ascii=False, indent=2)
    except:
        pass


def load_decors():
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return deepcopy(DEFAULT_DECORS)


def get_sheets_for_decors(decor_catalog, selected_decors):
    sheets = []
    for decor_name in selected_decors:
        if decor_name in decor_catalog:
            info = decor_catalog[decor_name]
            for s in info['sheets']:
                w, h, price = s[0], s[1], s[2]
                label = decor_name + ' ' + str(w) + 'x' + str(h)
                sheets.append(Sheet(w, h, price, label, decor_name))
    return sheets


# ===================== ДВИЖОК РАСКРОЯ =====================

class GuillotineNode:
    def __init__(self, x, y, w, h):
        self.x = x; self.y = y; self.w = w; self.h = h

class GuillotinePacker:
    def __init__(self, sw, sh, kerf=2):
        self.kerf = kerf
        self.free_rects = [GuillotineNode(0, 0, sw, sh)]
        self.placements = []

    def insert(self, pw, ph, label='', can_rotate=True):
        best = None
        best_score = (float('inf'), float('inf'))
        best_w = best_h = best_idx = 0
        best_rot = False
        for i, r in enumerate(self.free_rects):
            if pw <= r.w and ph <= r.h:
                score = (min(r.w - pw, r.h - ph), max(r.w - pw, r.h - ph))
                if score < best_score:
                    best_score = score; best = r
                    best_w, best_h = pw, ph
                    best_rot = False; best_idx = i
            if can_rotate and pw != ph and ph <= r.w and pw <= r.h:
                score = (min(r.w - ph, r.h - pw), max(r.w - ph, r.h - pw))
                if score < best_score:
                    best_score = score; best = r
                    best_w, best_h = ph, pw
                    best_rot = True; best_idx = i
        if not best: return None
        p = Placement(best.x, best.y, best_w, best_h, label, best_rot)
        self.placements.append(p)
        self._split(best_idx, best_w, best_h)
        return p

    def _split(self, idx, pw, ph):
        r = self.free_rects.pop(idx)
        k = self.kerf
        if r.w - pw - k > 0:
            self.free_rects.append(GuillotineNode(r.x + pw + k, r.y, r.w - pw - k, r.h))
        if r.h - ph - k > 0:
            self.free_rects.append(GuillotineNode(r.x, r.y + ph + k, pw, r.h - ph - k))

    def get_wastes(self, min_useful=100):
        return [Waste(r.x, r.y, r.w, r.h, r.w >= min_useful and r.h >= min_useful)
                for r in self.free_rects if r.w > 10 and r.h > 10]


def _expand_parts(parts):
    expanded = []
    n = 1
    for p in parts:
        for _ in range(p.qty):
            lbl = p.label if p.label else ('D' + str(n))
            expanded.append(Part(p.width, p.height, 1, lbl, p.can_rotate))
            n += 1
    return expanded


def _sort_parts(parts, strategy="area_desc"):
    if strategy == "area_desc":
        return sorted(parts, key=lambda p: p.area, reverse=True)
    elif strategy == "long_desc":
        return sorted(parts, key=lambda p: max(p.width, p.height), reverse=True)
    elif strategy == "perimeter_desc":
        return sorted(parts, key=lambda p: 2 * (p.width + p.height), reverse=True)
    return parts


def _can_fit_any(sheet, parts, kerf):
    for p in parts:
        pw, ph = p.width, p.height
        sw, sh = sheet.width, sheet.height
        if (pw <= sw and ph <= sh) or (p.can_rotate and ph <= sw and pw <= sh):
            return True
    return False


def _remove_placed(remaining, placed):
    to_remove = []
    for p in placed:
        for i, r in enumerate(remaining):
            if i not in to_remove:
                if r.width == p.width and r.height == p.height and r.label == p.label:
                    to_remove.append(i)
                    break
    return [r for i, r in enumerate(remaining) if i not in to_remove]


def optimize(sheets, parts, kerf=2, cut_price=75, min_useful=100):
    expanded = _expand_parts(parts)
    valid_sheets = [s for s in sheets if _can_fit_any(s, expanded, kerf)]
    if not valid_sheets:
        return CuttingResult(cut_price=cut_price, kerf=kerf, unplaced_parts=expanded)

    strategies = ["area_desc", "long_desc", "perimeter_desc"]
    best_result = None

    def evaluate(r):
        all_placed = len(r.unplaced_parts) == 0
        return (all_placed, -r.total_cost, r.total_efficiency, -len(r.layouts))

    def try_update(result):
        nonlocal best_result
        if not result.layouts: return
        if best_result is None or evaluate(result) > evaluate(best_result):
            best_result = result

    for strategy in strategies:
        sorted_parts = _sort_parts(deepcopy(expanded), strategy)
        for sheet in valid_sheets:
            result = CuttingResult(cut_price=cut_price, kerf=kerf)
            remaining = list(sorted_parts)
            for _ in range(50):
                if not remaining: break
                if not _can_fit_any(sheet, remaining, kerf): break
                packer = GuillotinePacker(sheet.width, sheet.height, kerf)
                placed = []
                for part in remaining:
                    res = packer.insert(part.width, part.height, part.label, part.can_rotate)
                    if res: placed.append(part)
                if not placed: break
                layout = SheetLayout(sheet=deepcopy(sheet), placements=packer.placements,
                                     wastes=packer.get_wastes(min_useful), cuts_count=len(placed))
                result.layouts.append(layout)
                remaining = _remove_placed(remaining, placed)
            result.unplaced_parts = remaining
            try_update(result)

    for strategy in strategies:
        sorted_parts = _sort_parts(deepcopy(expanded), strategy)
        result = CuttingResult(cut_price=cut_price, kerf=kerf)
        remaining = list(sorted_parts)
        for _ in range(50):
            if not remaining: break
            best_layout = None
            best_placed = None
            best_score = None
            for sheet in valid_sheets:
                if not _can_fit_any(sheet, remaining, kerf): continue
                packer = GuillotinePacker(sheet.width, sheet.height, kerf)
                placed = []
                for part in remaining:
                    res = packer.insert(part.width, part.height, part.label, part.can_rotate)
                    if res: placed.append(part)
                if not placed: continue
                total_placed_area = sum(p.width * p.height for p in placed)
                sheet_cost = sheet.price + len(placed) * cut_price
                cost_per_area = sheet_cost / max(total_placed_area, 1)
                layout = SheetLayout(sheet=deepcopy(sheet), placements=packer.placements,
                                     wastes=packer.get_wastes(min_useful), cuts_count=len(placed))
                score = (len(placed), -cost_per_area, layout.efficiency)
                if best_score is None or score > best_score:
                    best_score = score; best_layout = layout; best_placed = placed
            if best_layout is None: break
            result.layouts.append(best_layout)
            remaining = _remove_placed(remaining, best_placed)
        result.unplaced_parts = remaining
        try_update(result)

    if best_result is None:
        best_result = CuttingResult(cut_price=cut_price, kerf=kerf, unplaced_parts=expanded)
    return best_result


# ===================== ВИЗУАЛИЗАЦИЯ =====================

PART_COLORS = ['#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#F44336', '#00BCD4',
               '#8BC34A', '#3F51B5', '#FFEB3B', '#795548', '#607D8B', '#E91E63']
WASTE_COLOR = '#FFCDD2'
USEFUL_WASTE_COLOR = '#FFF9C4'


def _get_font(size):
    paths = ['C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/segoeui.ttf',
             'C:/Windows/Fonts/tahoma.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    size = max(size, 6)
    for fp in paths:
        try: return ImageFont.truetype(fp, size)
        except: continue
    return ImageFont.load_default()


def render_layout(layout, idx=0, max_w=1000, max_h=700, decor_catalog=None):
    scale_w = (max_w - 120) / max(layout.sheet.width, 1)
    scale_h = (max_h - 160) / max(layout.sheet.height, 1)
    scale = min(scale_w, scale_h, 1.0)
    scale = max(scale, 0.05)

    margin = 50; header = 45; footer = 50
    img_w = int(layout.sheet.width * scale) + margin * 2
    img_h = int(layout.sheet.height * scale) + margin * 2 + header + footer

    img = Image.new('RGB', (img_w, img_h), '#FFFFFF')
    draw = ImageDraw.Draw(img)
    font_title = _get_font(13); font_small = _get_font(10); font_dim = _get_font(9)

    decor_text = ''
    if hasattr(layout.sheet, 'decor') and layout.sheet.decor:
        decor_text = ' [' + layout.sheet.decor + ']'

    title = ('Лист ' + str(idx + 1) + ': ' + str(layout.sheet.width) + 'x' +
             str(layout.sheet.height) + ' мм' + decor_text + '  |  ' +
             str(layout.efficiency) + '%  |  Резов: ' + str(layout.cuts_count) +
             '  |  ' + str(layout.sheet.price) + ' руб')
    draw.text((margin, 8), title, fill='black', font=font_title)

    sx = margin; sy = margin + header
    sw = int(layout.sheet.width * scale); sh = int(layout.sheet.height * scale)

    sheet_bg = '#F0F0F0'
    if decor_catalog and hasattr(layout.sheet, 'decor') and layout.sheet.decor in decor_catalog:
        sheet_bg = decor_catalog[layout.sheet.decor]['color_code']
    draw.rectangle([sx, sy, sx + sw, sy + sh], fill=sheet_bg, outline='#333333', width=2)

    for waste in layout.wastes:
        wx0 = sx + int(waste.x * scale); wy0 = sy + int(waste.y * scale)
        wx1 = wx0 + int(waste.width * scale); wy1 = wy0 + int(waste.height * scale)
        if wx1 - wx0 < 3 or wy1 - wy0 < 3: continue
        color = USEFUL_WASTE_COLOR if waste.is_useful else WASTE_COLOR
        draw.rectangle([wx0, wy0, wx1, wy1], fill=color, outline='#BDBDBD', width=1)
        if wx1 - wx0 > 40 and wy1 - wy0 > 15:
            draw.text((wx0 + 3, wy0 + 2), str(waste.width) + 'x' + str(waste.height),
                      fill='#757575', font=font_dim)

    for i, p in enumerate(layout.placements):
        color = PART_COLORS[i % len(PART_COLORS)]
        px0 = sx + int(p.x * scale); py0 = sy + int(p.y * scale)
        px1 = px0 + int(p.width * scale); py1 = py0 + int(p.height * scale)
        if px1 - px0 < 3 or py1 - py0 < 3: continue
        draw.rectangle([px0, py0, px1, py1], fill=color, outline='#212121', width=2)
        bw = px1 - px0 - 6; bh = py1 - py0 - 4
        if bw > 20 and bh > 12:
            rot = ' R' if p.rotated else ''
            draw.text((px0 + 4, py0 + 3), p.part_label + rot, fill='white', font=font_small)
            if bh > 25:
                draw.text((px0 + 4, py0 + 16), str(p.width) + 'x' + str(p.height),
                          fill='#E8F5E9', font=font_dim)

    fd = _get_font(10)
    ay = sy + sh + 8
    draw.line([(sx, ay), (sx + sw, ay)], fill='black', width=1)
    dw = str(layout.sheet.width) + ' мм'
    bb = draw.textbbox((0, 0), dw, font=fd)
    draw.text((sx + sw // 2 - (bb[2] - bb[0]) // 2, ay + 3), dw, fill='black', font=fd)
    ax = sx - 8
    draw.line([(ax, sy), (ax, sy + sh)], fill='black', width=1)
    dh = str(layout.sheet.height)
    bb = draw.textbbox((0, 0), dh, font=fd)
    draw.text((3, sy + sh // 2 - (bb[3] - bb[1]) // 2), dh, fill='black', font=fd)

    return img


# ===================== GUI ПРИЛОЖЕНИЕ =====================

class DecorEditorDialog:
    """Диалог редактирования декора"""
    def __init__(self, parent, decor_name, decor_info, is_new=False):
        self.result = None
        self.dlg = tk.Toplevel(parent)
        self.dlg.title('Редактирование декора: ' + decor_name if not is_new else 'Новый декор')
        self.dlg.geometry('650x550')
        self.dlg.grab_set()

        self.decor_info = deepcopy(decor_info)

        # Название
        name_frame = ttk.LabelFrame(self.dlg, text='Название декора', padding=5)
        name_frame.pack(fill=tk.X, padx=10, pady=5)
        self.name_var = tk.StringVar(value=decor_name)
        ttk.Entry(name_frame, textvariable=self.name_var, width=30, font=('Arial', 12)).pack(fill=tk.X)

        # Цвет
        color_frame = ttk.LabelFrame(self.dlg, text='Цвет декора', padding=5)
        color_frame.pack(fill=tk.X, padx=10, pady=5)

        cf = ttk.Frame(color_frame)
        cf.pack(fill=tk.X)

        self.color_canvas = tk.Canvas(cf, width=60, height=40, highlightthickness=2,
                                       highlightbackground=decor_info.get('border_color', '#999'))
        self.color_canvas.pack(side=tk.LEFT, padx=5)
        self.color_canvas.create_rectangle(2, 2, 58, 38,
            fill=decor_info.get('color_code', '#CCCCCC'), outline='', tags='color_rect')

        self.color_var = tk.StringVar(value=decor_info.get('color_code', '#CCCCCC'))
        ttk.Label(cf, textvariable=self.color_var, font=('Consolas', 11)).pack(side=tk.LEFT, padx=5)
        ttk.Button(cf, text='Выбрать цвет...', command=self.pick_color).pack(side=tk.LEFT, padx=10)

        # Таблица листов
        sheets_frame = ttk.LabelFrame(self.dlg, text='Листы этого декора', padding=5)
        sheets_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        cols = ('Ширина', 'Высота', 'Цена')
        self.tree = ttk.Treeview(sheets_frame, columns=cols, show='headings', height=10)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=100, anchor='center')

        sb = ttk.Scrollbar(sheets_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        for s in decor_info.get('sheets', []):
            self.tree.insert('', 'end', values=(s[0], s[1], s[2]))

        # Кнопки управления листами
        btn_sheets = ttk.Frame(self.dlg)
        btn_sheets.pack(fill=tk.X, padx=10, pady=3)

        # Поля для добавления
        add_f = ttk.Frame(btn_sheets)
        add_f.pack(fill=tk.X, pady=2)
        ttk.Label(add_f, text='Ш:').pack(side=tk.LEFT)
        self.new_w = ttk.Entry(add_f, width=6)
        self.new_w.pack(side=tk.LEFT, padx=2)
        ttk.Label(add_f, text='В:').pack(side=tk.LEFT)
        self.new_h = ttk.Entry(add_f, width=6)
        self.new_h.pack(side=tk.LEFT, padx=2)
        ttk.Label(add_f, text='Цена:').pack(side=tk.LEFT)
        self.new_price = ttk.Entry(add_f, width=7)
        self.new_price.pack(side=tk.LEFT, padx=2)

        btn_f = ttk.Frame(btn_sheets)
        btn_f.pack(fill=tk.X, pady=2)
        ttk.Button(btn_f, text='Добавить лист', command=self.add_sheet).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_f, text='Удалить выбранный', command=self.del_sheet).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_f, text='Изменить цену', command=self.edit_price).pack(side=tk.LEFT, padx=2)

        # Кнопки OK / Отмена
        ok_frame = ttk.Frame(self.dlg)
        ok_frame.pack(fill=tk.X, padx=10, pady=10)

        tk.Button(ok_frame, text='Сохранить', command=self.on_ok,
                  bg='#4CAF50', fg='white', font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=5, ipadx=20, ipady=5)
        tk.Button(ok_frame, text='Отмена', command=self.dlg.destroy,
                  font=('Arial', 11)).pack(side=tk.LEFT, padx=5, ipadx=20, ipady=5)

    def pick_color(self):
        color = colorchooser.askcolor(initialcolor=self.color_var.get(), title='Выберите цвет декора')
        if color and color[1]:
            self.color_var.set(color[1])
            self.color_canvas.delete('color_rect')
            self.color_canvas.create_rectangle(2, 2, 58, 38, fill=color[1], outline='', tags='color_rect')

    def add_sheet(self):
        try:
            w = int(self.new_w.get())
            h = int(self.new_h.get())
            price = float(self.new_price.get())
        except ValueError:
            messagebox.showerror('Ошибка', 'Введите корректные числа!')
            return
        if w <= 0 or h <= 0:
            messagebox.showerror('Ошибка', 'Размеры должны быть положительными!')
            return
        self.tree.insert('', 'end', values=(w, h, price))
        self.new_w.delete(0, tk.END)
        self.new_h.delete(0, tk.END)
        self.new_price.delete(0, tk.END)

    def del_sheet(self):
        sel = self.tree.selection()
        if sel:
            self.tree.delete(sel[0])

    def edit_price(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo('Инфо', 'Выберите лист для изменения цены')
            return
        item = sel[0]
        vals = self.tree.item(item, 'values')
        new_price = simpledialog.askfloat('Изменить цену',
            'Лист ' + str(vals[0]) + 'x' + str(vals[1]) + '\nНовая цена:',
            initialvalue=float(vals[2]), parent=self.dlg)
        if new_price is not None:
            self.tree.item(item, values=(vals[0], vals[1], new_price))

    def on_ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror('Ошибка', 'Введите название декора!')
            return

        sheets = []
        for item in self.tree.get_children():
            vals = self.tree.item(item, 'values')
            sheets.append([int(vals[0]), int(vals[1]), float(vals[2])])

        if not sheets:
            messagebox.showerror('Ошибка', 'Добавьте хотя бы один лист!')
            return

        self.result = {
            'name': name,
            'info': {
                'color_code': self.color_var.get(),
                'border_color': self.color_var.get(),
                'sheets': sheets
            }
        }
        self.dlg.destroy()


class App:
    def __init__(self, root):
        self.root = root
        self.root.title('Оптимизатор Раскроя ЛДСП v5')
        self.root.geometry('1400x900')
        self.root.minsize(1000, 650)

        self.decor_catalog = load_decors()
        self.parts_data = []
        self.result = None
        self.result_images = []
        self.photo_refs = []
        self.decor_vars = {}

        self.build_ui()
        self.load_default_parts()

    def build_ui(self):
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left = ttk.Frame(main_pane, width=520)
        main_pane.add(left, weight=1)
        right = ttk.Frame(main_pane)
        main_pane.add(right, weight=2)

        self.build_left(left)
        self.build_right(right)

    def build_left(self, parent):
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)

        decor_tab = ttk.Frame(notebook)
        notebook.add(decor_tab, text='  Декоры ЛДСП  ')

        parts_tab = ttk.Frame(notebook)
        notebook.add(parts_tab, text='  Детали  ')

        params_tab = ttk.Frame(notebook)
        notebook.add(params_tab, text='  Параметры  ')

        self.decor_tab = decor_tab
        self.build_decor_tab(decor_tab)
        self.build_parts_tab(parts_tab)
        self.build_params_tab(params_tab)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Button(btn_frame, text='РАССЧИТАТЬ РАСКРОЙ', command=self.calculate,
                  bg='#4CAF50', fg='white', font=('Arial', 13, 'bold'),
                  cursor='hand2').pack(fill=tk.X, ipady=12)

        tk.Button(btn_frame, text='Сохранить карты раскроя в PNG', command=self.save_images,
                  bg='#2196F3', fg='white', font=('Arial', 10)).pack(fill=tk.X, pady=5, ipady=6)

    def build_decor_tab(self, parent):
        # Очищаем вкладку
        for w in parent.winfo_children():
            w.destroy()
        self.decor_vars = {}

        # Заголовок
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(top, text='Декоры ЛДСП:', font=('Arial', 11, 'bold')).pack(side=tk.LEFT)

        # Кнопки управления декорами
        ttk.Button(top, text='+ Новый декор', command=self.add_new_decor).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top, text='Сбросить по умолчанию', command=self.reset_decors).pack(side=tk.RIGHT, padx=2)

        # Скроллируемая область для декоров
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))

        for decor_name, info in self.decor_catalog.items():
            var = tk.BooleanVar(value=False)
            self.decor_vars[decor_name] = var

            card = ttk.LabelFrame(inner, text=decor_name, padding=8)
            card.pack(fill=tk.X, padx=10, pady=4)

            top_row = ttk.Frame(card)
            top_row.pack(fill=tk.X)

            # Цветовой образец
            cc = tk.Canvas(top_row, width=45, height=45, highlightthickness=2,
                           highlightbackground=info.get('border_color', '#999'))
            cc.pack(side=tk.LEFT, padx=(0, 8))
            cc.create_rectangle(2, 2, 43, 43, fill=info.get('color_code', '#CCC'),
                                outline=info.get('border_color', '#999'), width=1)

            # Инфо
            info_f = ttk.Frame(top_row)
            info_f.pack(side=tk.LEFT, fill=tk.X, expand=True)

            cnt = len(info.get('sheets', []))
            prices = [s[2] for s in info.get('sheets', [])]
            if prices:
                ttk.Label(info_f, text='Листов: ' + str(cnt)).pack(anchor='w')
                ttk.Label(info_f, text='Цены: ' + str(int(min(prices))) + ' - ' +
                          str(int(max(prices))) + ' руб').pack(anchor='w')
            else:
                ttk.Label(info_f, text='Нет листов').pack(anchor='w')

            # Кнопки
            btn_f = ttk.Frame(top_row)
            btn_f.pack(side=tk.RIGHT)

            cb = ttk.Checkbutton(btn_f, text='Использовать', variable=var)
            cb.pack(anchor='e', pady=1)

            btns_row = ttk.Frame(btn_f)
            btns_row.pack(anchor='e')

            edit_name = decor_name
            ttk.Button(btns_row, text='Редактировать',
                       command=lambda n=edit_name: self.edit_decor(n)).pack(side=tk.LEFT, padx=1)
            ttk.Button(btns_row, text='Удалить',
                       command=lambda n=edit_name: self.delete_decor(n)).pack(side=tk.LEFT, padx=1)

    def add_new_decor(self):
        new_info = {
            'color_code': '#DDDDDD',
            'border_color': '#999999',
            'sheets': []
        }
        dlg = DecorEditorDialog(self.root, 'Новый декор', new_info, is_new=True)
        self.root.wait_window(dlg.dlg)

        if dlg.result:
            name = dlg.result['name']
            if name in self.decor_catalog:
                messagebox.showerror('Ошибка', 'Декор с таким именем уже есть!')
                return
            self.decor_catalog[name] = dlg.result['info']
            save_decors(self.decor_catalog)
            self.build_decor_tab(self.decor_tab)

    def edit_decor(self, decor_name):
        if decor_name not in self.decor_catalog:
            return
        info = self.decor_catalog[decor_name]
        dlg = DecorEditorDialog(self.root, decor_name, info)
        self.root.wait_window(dlg.dlg)

        if dlg.result:
            new_name = dlg.result['name']
            # Удаляем старый если переименовали
            if new_name != decor_name:
                del self.decor_catalog[decor_name]
            self.decor_catalog[new_name] = dlg.result['info']
            save_decors(self.decor_catalog)
            self.build_decor_tab(self.decor_tab)

    def delete_decor(self, decor_name):
        if messagebox.askyesno('Удаление', 'Удалить декор "' + decor_name + '"?'):
            if decor_name in self.decor_catalog:
                del self.decor_catalog[decor_name]
                save_decors(self.decor_catalog)
                self.build_decor_tab(self.decor_tab)

    def reset_decors(self):
        if messagebox.askyesno('Сброс', 'Сбросить все декоры к заводским настройкам?'):
            self.decor_catalog = deepcopy(DEFAULT_DECORS)
            save_decors(self.decor_catalog)
            self.build_decor_tab(self.decor_tab)

    def get_selected_decors(self):
        return [name for name, var in self.decor_vars.items() if var.get()]

    # ====== Детали ======
    def build_parts_tab(self, parent):
        cols = ('Ширина', 'Высота', 'Кол-во', 'Название', 'Вращение')
        self.parts_tree = ttk.Treeview(parent, columns=cols, show='headings', height=10)
        for c in cols:
            self.parts_tree.heading(c, text=c)
            w = 70 if c != 'Название' else 100
            self.parts_tree.column(c, width=w, anchor='center')
        self.parts_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        add_f = ttk.LabelFrame(parent, text='Добавить деталь', padding=5)
        add_f.pack(fill=tk.X, padx=5, pady=3)

        r1 = ttk.Frame(add_f); r1.pack(fill=tk.X, pady=2)
        ttk.Label(r1, text='Ширина:').pack(side=tk.LEFT, padx=2)
        self.p_w = ttk.Entry(r1, width=7); self.p_w.pack(side=tk.LEFT, padx=2)
        ttk.Label(r1, text='Высота:').pack(side=tk.LEFT, padx=2)
        self.p_h = ttk.Entry(r1, width=7); self.p_h.pack(side=tk.LEFT, padx=2)

        r2 = ttk.Frame(add_f); r2.pack(fill=tk.X, pady=2)
        ttk.Label(r2, text='Кол-во:').pack(side=tk.LEFT, padx=2)
        self.p_qty = ttk.Entry(r2, width=5); self.p_qty.insert(0, '1'); self.p_qty.pack(side=tk.LEFT, padx=2)
        ttk.Label(r2, text='Название:').pack(side=tk.LEFT, padx=2)
        self.p_label = ttk.Entry(r2, width=12); self.p_label.pack(side=tk.LEFT, padx=2)
        self.p_rotate = tk.BooleanVar(value=True)
        ttk.Checkbutton(r2, text='Вращение', variable=self.p_rotate).pack(side=tk.LEFT, padx=5)

        bf = ttk.Frame(parent); bf.pack(fill=tk.X, padx=5, pady=3)
        ttk.Button(bf, text='Добавить', command=self.add_part).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text='Удалить', command=self.del_part).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text='Очистить все', command=self.clear_parts).pack(side=tk.LEFT, padx=2)

    def add_part(self):
        try:
            w = int(self.p_w.get()); h = int(self.p_h.get()); qty = int(self.p_qty.get())
            label = self.p_label.get().strip() or (str(w) + 'x' + str(h))
            can_rotate = self.p_rotate.get()
        except ValueError:
            messagebox.showerror('Ошибка', 'Введите корректные числа!'); return
        if w <= 0 or h <= 0 or qty <= 0:
            messagebox.showerror('Ошибка', 'Все значения должны быть положительными!'); return
        self.parts_data.append(Part(w, h, qty, label, can_rotate))
        self.parts_tree.insert('', 'end', values=(w, h, qty, label, 'Да' if can_rotate else 'Нет'))
        self.p_w.delete(0, tk.END); self.p_h.delete(0, tk.END)
        self.p_qty.delete(0, tk.END); self.p_qty.insert(0, '1'); self.p_label.delete(0, tk.END)

    def del_part(self):
        sel = self.parts_tree.selection()
        if not sel: return
        idx = self.parts_tree.index(sel[0])
        self.parts_tree.delete(sel[0])
        if 0 <= idx < len(self.parts_data): self.parts_data.pop(idx)

    def clear_parts(self):
        if messagebox.askyesno('Подтверждение', 'Удалить все детали?'):
            self.parts_data.clear()
            for item in self.parts_tree.get_children(): self.parts_tree.delete(item)

    def load_default_parts(self):
        for w, h, qty, label, rot in [(160, 690, 2, 'Бок', True), (160, 658, 1, 'Царга', True), (160, 1618, 2, 'Полка', True)]:
            self.parts_data.append(Part(w, h, qty, label, rot))
            self.parts_tree.insert('', 'end', values=(w, h, qty, label, 'Да' if rot else 'Нет'))

    # ====== Параметры ======
    def build_params_tab(self, parent):
        pf = ttk.LabelFrame(parent, text='Настройки раскроя', padding=15)
        pf.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(pf, text='Ширина пропила (мм):').grid(row=0, column=0, sticky='w', pady=5)
        self.kerf_var = tk.StringVar(value='2')
        ttk.Entry(pf, textvariable=self.kerf_var, width=8).grid(row=0, column=1, padx=10, pady=5)
        ttk.Label(pf, text='Цена за один рез (руб):').grid(row=1, column=0, sticky='w', pady=5)
        self.cut_price_var = tk.StringVar(value='75')
        ttk.Entry(pf, textvariable=self.cut_price_var, width=8).grid(row=1, column=1, padx=10, pady=5)
        ttk.Label(pf, text='Мин. полезный остаток (мм):').grid(row=2, column=0, sticky='w', pady=5)
        self.min_useful_var = tk.StringVar(value='100')
        ttk.Entry(pf, textvariable=self.min_useful_var, width=8).grid(row=2, column=1, padx=10, pady=5)

        tips = ttk.LabelFrame(parent, text='Подсказки', padding=10)
        tips.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(tips, text='* Пропил - ширина реза пилы (2-5 мм)\n'
                  '* Цена реза - стоимость одного пропила\n'
                  '* Полезный остаток - минимальный размер обрезка\n'
                  '* Декоры и цены сохраняются между сеансами\n'
                  '* Если текстура направленная - отключите вращение',
                  font=('Arial', 9)).pack(anchor='w')

    # ====== Правая панель ======
    def build_right(self, parent):
        rf = ttk.LabelFrame(parent, text='Результат расчёта', padding=5)
        rf.pack(fill=tk.X, padx=5, pady=5)
        self.report = scrolledtext.ScrolledText(rf, height=12, font=('Consolas', 10))
        self.report.pack(fill=tk.X)

        img_f = ttk.LabelFrame(parent, text='Карты раскроя', padding=5)
        img_f.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.canvas = tk.Canvas(img_f, bg='#E0E0E0')
        sbv = ttk.Scrollbar(img_f, orient=tk.VERTICAL, command=self.canvas.yview)
        sbh = ttk.Scrollbar(img_f, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=sbv.set, xscrollcommand=sbh.set)
        sbv.pack(side=tk.RIGHT, fill=tk.Y); sbh.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.inner_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner_frame, anchor='nw')
        self.inner_frame.bind('<Configure>',
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))

    # ====== Расчёт ======
    def calculate(self):
        selected = self.get_selected_decors()
        if not selected:
            messagebox.showwarning('Внимание', 'Выберите хотя бы один декор!'); return
        if not self.parts_data:
            messagebox.showwarning('Внимание', 'Добавьте хотя бы одну деталь!'); return
        try:
            kerf = int(self.kerf_var.get())
            cut_price = float(self.cut_price_var.get())
            min_useful = int(self.min_useful_var.get())
        except ValueError:
            messagebox.showerror('Ошибка', 'Проверьте параметры!'); return

        all_sheets = get_sheets_for_decors(self.decor_catalog, selected)
        self.root.config(cursor='wait'); self.root.update()
        try:
            self.result = optimize(all_sheets, self.parts_data, kerf, cut_price, min_useful)
            self.show_result()
        except Exception as e:
            messagebox.showerror('Ошибка', str(e))
        finally:
            self.root.config(cursor='')

    def show_result(self):
        r = self.result
        self.report.delete(1.0, tk.END)
        sep = '=' * 55
        self.report.insert(tk.END, sep + '\n')
        self.report.insert(tk.END, 'РЕЗУЛЬТАТ РАСКРОЯ\n')
        self.report.insert(tk.END, sep + '\n\n')
        self.report.insert(tk.END, 'Листов: ' + str(len(r.layouts)) + '\n')
        self.report.insert(tk.END, 'Стоимость листов: ' + str(round(r.total_sheets_cost)) + ' руб\n')
        self.report.insert(tk.END, 'Резов: ' + str(r.total_cuts_count) + '\n')
        self.report.insert(tk.END, 'Стоимость резов: ' + str(round(r.total_cuts_cost)) + ' руб\n')
        self.report.insert(tk.END, 'ИТОГО: ' + str(round(r.total_cost)) + ' руб\n')
        self.report.insert(tk.END, 'Эффективность: ' + str(r.total_efficiency) + '%\n')
        if r.unplaced_parts:
            self.report.insert(tk.END, '\n!!! НЕ ПОМЕСТИЛИСЬ (' + str(len(r.unplaced_parts)) + '):\n')
            for p in r.unplaced_parts:
                self.report.insert(tk.END, '  * ' + str(p.width) + 'x' + str(p.height) + ' (' + p.label + ')\n')
        self.report.insert(tk.END, '\n' + sep + '\n')
        for i, layout in enumerate(r.layouts):
            dec = ''
            if hasattr(layout.sheet, 'decor') and layout.sheet.decor:
                dec = ' [' + layout.sheet.decor + ']'
            self.report.insert(tk.END, '\nЛист ' + str(i+1) + ': ' + str(layout.sheet.width) + 'x' +
                               str(layout.sheet.height) + dec + ' | ' + str(layout.efficiency) + '% | ' +
                               str(layout.sheet.price) + ' руб\n')
            for pl in layout.placements:
                rot = ' (поверн.)' if pl.rotated else ''
                self.report.insert(tk.END, '  * ' + pl.part_label + ' ' + str(pl.width) + 'x' +
                                   str(pl.height) + rot + '\n')

        for w in self.inner_frame.winfo_children(): w.destroy()
        self.photo_refs.clear(); self.result_images = []
        for i, layout in enumerate(r.layouts):
            img = render_layout(layout, i, 850, 550, self.decor_catalog)
            self.result_images.append(img)
            photo = ImageTk.PhotoImage(img)
            self.photo_refs.append(photo)
            ttk.Label(self.inner_frame, image=photo).pack(padx=5, pady=5)
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def save_images(self):
        if not self.result_images:
            messagebox.showinfo('Инфо', 'Сначала выполните расчёт!'); return
        folder = filedialog.askdirectory(title='Выберите папку')
        if not folder: return
        for i, img in enumerate(self.result_images):
            img.save(os.path.join(folder, 'Raskroy_' + str(i+1) + '.png'))
        messagebox.showinfo('Готово', 'Сохранено ' + str(len(self.result_images)) + ' файлов в:\n' + folder)


def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()

if __name__ == '__main__':
    main()
