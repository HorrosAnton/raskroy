# -*- coding: utf-8 -*-
import sys, os
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from dataclasses import dataclass, field
from copy import deepcopy
from PIL import Image, ImageDraw, ImageFont, ImageTk

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
                score = (min(r.w-pw, r.h-ph), max(r.w-pw, r.h-ph))
                if score < best_score:
                    best_score = score; best = r
                    best_w, best_h = pw, ph
                    best_rot = False; best_idx = i
            if can_rotate and pw != ph and ph <= r.w and pw <= r.h:
                score = (min(r.w-ph, r.h-pw), max(r.w-ph, r.h-pw))
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
            self.free_rects.append(GuillotineNode(r.x+pw+k, r.y, r.w-pw-k, r.h))
        if r.h - ph - k > 0:
            self.free_rects.append(GuillotineNode(r.x, r.y+ph+k, pw, r.h-ph-k))

    def get_wastes(self, min_useful=100):
        return [Waste(r.x, r.y, r.w, r.h, r.w >= min_useful and r.h >= min_useful)
                for r in self.free_rects if r.w > 10 and r.h > 10]

def _expand_parts(parts):
    expanded = []
    n = 1
    for p in parts:
        for _ in range(p.qty):
            expanded.append(Part(p.width, p.height, 1, p.label or ('D' + str(n)), p.can_rotate))
            n += 1
    return expanded

def optimize(sheets, parts, kerf=2, cut_price=75, min_useful=100):
    expanded = _expand_parts(parts)
    result = CuttingResult(cut_price=cut_price, kerf=kerf)
    remaining = expanded[:]
    for sheet in sorted(sheets, key=lambda s: s.area, reverse=True):
        if not remaining: break
        while remaining:
            packer = GuillotinePacker(sheet.width, sheet.height, kerf)
            placed = []
            for part in remaining:
                res = packer.insert(part.width, part.height, part.label, part.can_rotate)
                if res: placed.append(part)
            if not placed: break
            layout = SheetLayout(
                sheet=deepcopy(sheet),
                placements=packer.placements,
                wastes=packer.get_wastes(min_useful),
                cuts_count=len(placed)
            )
            result.layouts.append(layout)
            remaining = [p for p in remaining if p not in placed]
    result.unplaced_parts = remaining
    return result

COLORS = ['#4CAF50','#2196F3','#FF9800','#9C27B0','#F44336','#00BCD4']

def render_layout(layout, idx=0):
    scale = 0.5
    sw = int(layout.sheet.width * scale) + 100
    sh = int(layout.sheet.height * scale) + 120
    img = Image.new('RGB', (sw, sh), '#F8F8F8')
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('arial.ttf', 14)
        small = ImageFont.truetype('arial.ttf', 10)
    except:
        font = ImageFont.load_default()
        small = ImageFont.load_default()
    title = ('Лист ' + str(idx+1) + ' — ' + str(layout.sheet.width) +
             'x' + str(layout.sheet.height) + ' мм — ' + str(layout.efficiency) + '%')
    draw.text((20, 10), title, fill='black', font=font)
    ox, oy = 40, 60
    sw2 = int(layout.sheet.width * scale)
    sh2 = int(layout.sheet.height * scale)
    draw.rectangle([ox, oy, ox+sw2, oy+sh2], fill='#EEEEEE', outline='black', width=3)
    for i, p in enumerate(layout.placements):
        color = COLORS[i % len(COLORS)]
        x = ox + int(p.x * scale)
        y = oy + int(p.y * scale)
        x2 = x + int(p.width * scale)
        y2 = y + int(p.height * scale)
        draw.rectangle([x, y, x2, y2], fill=color, outline='black', width=2)
        rot = ' R' if p.rotated else ''
        draw.text((x+4, y+4), p.part_label + rot, fill='white', font=small)
    return img

class App:
    def __init__(self, root):
        self.root = root
        self.root.title('Оптимизатор Раскроя ЛДСП')
        self.root.geometry('1100x800')
        self.sheets = []
        self.parts = []
        self.result = None
        self.images = []
        self.build_ui()

    def build_ui(self):
        ttk.Label(self.root, text='Оптимизатор Раскроя ЛДСП',
                  font=('Arial', 16, 'bold')).pack(pady=10)
        top = ttk.Frame(self.root)
        top.pack(pady=5)
        ttk.Label(top, text='Пропил (мм):').pack(side=tk.LEFT, padx=5)
        self.kerf = tk.StringVar(value='2')
        ttk.Entry(top, textvariable=self.kerf, width=5).pack(side=tk.LEFT)
        ttk.Label(top, text='  Цена реза (руб):').pack(side=tk.LEFT, padx=5)
        self.cutprice = tk.StringVar(value='75')
        ttk.Entry(top, textvariable=self.cutprice, width=6).pack(side=tk.LEFT)

        btn = tk.Button(self.root, text='ЗАПУСТИТЬ РАСКРОЙ',
                        command=self.calculate,
                        bg='#4CAF50', fg='white',
                        font=('Arial', 12, 'bold'))
        btn.pack(pady=10, ipadx=20, ipady=8)

        self.log = scrolledtext.ScrolledText(self.root, font=('Consolas', 10))
        self.log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tk.Button(self.root, text='Сохранить карты раскроя PNG',
                  command=self.save_png,
                  bg='#2196F3', fg='white').pack(pady=8, ipadx=10, ipady=5)

    def calculate(self):
        self.log.delete(1.0, tk.END)
        if not self.sheets or not self.parts:
            self.log.insert(tk.END, 'Нет данных! Проверьте листы и детали в коде.')
            return
        try:
            kerf = int(self.kerf.get())
            cut_price = int(self.cutprice.get())
            self.result = optimize(self.sheets, self.parts, kerf, cut_price)
            self.show_result()
        except Exception as e:
            self.log.insert(tk.END, 'Ошибка: ' + str(e))

    def show_result(self):
        r = self.result
        self.images = []
        sep = '=' * 55
        self.log.insert(tk.END, sep + '\n')
        self.log.insert(tk.END, 'РЕЗУЛЬТАТ РАСКРОЯ\n')
        self.log.insert(tk.END, sep + '\n')
        self.log.insert(tk.END, 'Листов: ' + str(len(r.layouts)) + '\n')
        self.log.insert(tk.END, 'Стоимость: ' + str(round(r.total_cost)) + ' руб\n')
        self.log.insert(tk.END, 'Эффективность: ' + str(r.total_efficiency) + '%\n')
        self.log.insert(tk.END, 'Всего резов: ' + str(r.total_cuts_count) + '\n')
        if r.unplaced_parts:
            self.log.insert(tk.END, 'НЕ ПОМЕСТИЛИСЬ: ' + str(len(r.unplaced_parts)) + ' шт\n')
            for p in r.unplaced_parts:
                self.log.insert(tk.END, '  * ' + str(p.width) + 'x' + str(p.height) +
                                ' (' + p.label + ')\n')
        self.log.insert(tk.END, sep + '\n\n')
        for i, layout in enumerate(r.layouts):
            line = ('Лист ' + str(i+1) + ': ' +
                    str(layout.sheet.width) + 'x' + str(layout.sheet.height) +
                    ' — ' + str(layout.efficiency) + '%' +
                    ' — ' + str(layout.sheet.price) + ' руб\n')
            self.log.insert(tk.END, line)
            for pl in layout.placements:
                rot = ' (повернута)' if pl.rotated else ''
                self.log.insert(tk.END, '  * ' + pl.part_label + ' ' +
                                str(pl.width) + 'x' + str(pl.height) + rot + '\n')
            img = render_layout(layout, i)
            self.images.append(img)
            img.show(title='Лист ' + str(i+1))

    def save_png(self):
        if not self.images:
            messagebox.showinfo('Инфо', 'Сначала выполните расчет!')
            return
        folder = filedialog.askdirectory()
        if folder:
            for i, img in enumerate(self.images):
                path = os.path.join(folder, 'Raskroy_List_' + str(i+1) + '.png')
                img.save(path)
            messagebox.showinfo('Готово', 'Файлы сохранены в: ' + folder)

def main():
    root = tk.Tk()
    app = App(root)
    app.sheets = [
        Sheet(2700, 100,  645,  'ЛДСП 2700x100'),
        Sheet(2700, 300,  1093, 'ЛДСП 2700x300'),
        Sheet(2700, 400,  1324, 'ЛДСП 2700x400'),
        Sheet(2700, 500,  1865, 'ЛДСП 2700x500'),
        Sheet(2700, 600,  2082, 'ЛДСП 2700x600'),
        Sheet(2000, 300,  683,  'ЛДСП 2000x300'),
        Sheet(2000, 400,  910,  'ЛДСП 2000x400'),
        Sheet(2000, 500,  1238, 'ЛДСП 2000x500'),
        Sheet(2000, 600,  1405, 'ЛДСП 2000x600'),
        Sheet(1200, 300,  626,  'ЛДСП 1200x300'),
        Sheet(1200, 400,  754,  'ЛДСП 1200x400'),
        Sheet(800,  200,  276,  'ЛДСП 800x200'),
        Sheet(800,  300,  335,  'ЛДСП 800x300'),
        Sheet(800,  400,  432,  'ЛДСП 800x400'),
        Sheet(600,  300,  264,  'ЛДСП 600x300'),
        Sheet(600,  200,  218,  'ЛДСП 600x200'),
    ]
    app.parts = [
        Part(160, 690,  2, 'Бок'),
        Part(160, 658,  1, 'Царга'),
        Part(160, 1618, 2, 'Полка'),
    ]
    root.mainloop()

if __name__ == '__main__':
    main()
