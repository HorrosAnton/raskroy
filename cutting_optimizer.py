# -*- coding: utf-8 -*-
import sys, os, json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, simpledialog, colorchooser
from dataclasses import dataclass, field
from copy import deepcopy
from itertools import combinations
from PIL import Image, ImageDraw, ImageFont, ImageTk


# ================================================================
# МОДЕЛИ ДАННЫХ (оригинал)
# ================================================================

@dataclass
class Part:
    width: int
    height: int
    qty: int = 1
    label: str = ""
    can_rotate: bool = True

    @property
    def area(self):
        return self.width * self.height


@dataclass
class Sheet:
    width: int
    height: int
    price: float
    label: str = ""
    qty: int = 999
    decor: str = ""

    @property
    def area(self):
        return self.width * self.height


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
    def area(self):
        return self.width * self.height


@dataclass
class SheetLayout:
    sheet: Sheet
    placements: list = field(default_factory=list)
    cuts: list = field(default_factory=list)
    wastes: list = field(default_factory=list)
    cuts_count: int = 0

    @property
    def used_area(self):
        return sum(p.width * p.height for p in self.placements)

    @property
    def waste_area(self):
        return self.sheet.area - self.used_area

    @property
    def efficiency(self):
        if self.sheet.area == 0:
            return 0
        return self.used_area / self.sheet.area * 100


@dataclass
class CuttingResult:
    layouts: list = field(default_factory=list)
    unplaced_parts: list = field(default_factory=list)
    cut_price: float = 0
    kerf: int = 0

    @property
    def total_sheets_cost(self):
        return sum(l.sheet.price for l in self.layouts)

    @property
    def total_cuts_count(self):
        return sum(l.cuts_count for l in self.layouts)

    @property
    def total_cuts_cost(self):
        return self.total_cuts_count * self.cut_price

    @property
    def total_cost(self):
        return self.total_sheets_cost + self.total_cuts_cost

    @property
    def total_efficiency(self):
        total_used = sum(l.used_area for l in self.layouts)
        total_sheet = sum(l.sheet.area for l in self.layouts)
        if total_sheet == 0:
            return 0
        return total_used / total_sheet * 100


# ================================================================
# ДВИЖОК ГИЛЬОТИННОГО РАСКРОЯ (оригинал)
# ================================================================

class GuillotineNode:
    def __init__(self, x, y, w, h):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    @property
    def area(self):
        return self.w * self.h


class GuillotinePacker:
    def __init__(self, sheet_w, sheet_h, kerf=0):
        self.sheet_w = sheet_w
        self.sheet_h = sheet_h
        self.kerf = kerf
        self.free_rects = [GuillotineNode(0, 0, sheet_w, sheet_h)]
        self.placements = []
        self.cuts_count = 0

    def _fits(self, rect, pw, ph):
        return pw <= rect.w and ph <= rect.h

    def _score_bssf(self, rect, pw, ph):
        leftover_w = rect.w - pw
        leftover_h = rect.h - ph
        return (min(leftover_w, leftover_h), max(leftover_w, leftover_h))

    def insert(self, part_w, part_h, label="", can_rotate=True):
        best_rect = None
        best_score = None
        best_w, best_h = 0, 0
        best_rotated = False
        best_idx = -1

        for idx, rect in enumerate(self.free_rects):
            if self._fits(rect, part_w, part_h):
                score = self._score_bssf(rect, part_w, part_h)
                if best_score is None or score < best_score:
                    best_score = score
                    best_rect = rect
                    best_w, best_h = part_w, part_h
                    best_rotated = False
                    best_idx = idx

            if can_rotate and part_w != part_h:
                if self._fits(rect, part_h, part_w):
                    score = self._score_bssf(rect, part_h, part_w)
                    if best_score is None or score < best_score:
                        best_score = score
                        best_rect = rect
                        best_w, best_h = part_h, part_w
                        best_rotated = True
                        best_idx = idx

        if best_rect is None:
            return None

        placement = Placement(
            x=best_rect.x, y=best_rect.y,
            width=best_w, height=best_h,
            part_label=label, rotated=best_rotated
        )
        self.placements.append(placement)
        self._split(best_idx, best_w, best_h)
        return placement

    def _split(self, rect_idx, pw, ph):
        rect = self.free_rects.pop(rect_idx)
        kerf = self.kerf

        r1_w = rect.w - pw - kerf
        r1_h = ph
        b1_w = rect.w
        b1_h = rect.h - ph - kerf

        r2_w = rect.w - pw - kerf
        r2_h = rect.h
        b2_w = pw
        b2_h = rect.h - ph - kerf

        def max_rect_area(rects_list):
            areas = [max(w * h, 0) for w, h in rects_list]
            return max(areas) if areas else 0

        v1_max = max_rect_area([(r1_w, r1_h), (b1_w, b1_h)])
        v2_max = max_rect_area([(r2_w, r2_h), (b2_w, b2_h)])

        if v1_max >= v2_max:
            if r1_w > 0 and r1_h > 0:
                self.free_rects.append(
                    GuillotineNode(rect.x + pw + kerf, rect.y, r1_w, r1_h))
            if b1_w > 0 and b1_h > 0:
                self.free_rects.append(
                    GuillotineNode(rect.x, rect.y + ph + kerf, b1_w, b1_h))
        else:
            if r2_w > 0 and r2_h > 0:
                self.free_rects.append(
                    GuillotineNode(rect.x + pw + kerf, rect.y, r2_w, r2_h))
            if b2_w > 0 and b2_h > 0:
                self.free_rects.append(
                    GuillotineNode(rect.x, rect.y + ph + kerf, b2_w, b2_h))

    def get_wastes(self, min_useful_size=100):
        wastes = []
        for rect in self.free_rects:
            if rect.w > 0 and rect.h > 0:
                is_useful = rect.w >= min_useful_size and rect.h >= min_useful_size
                wastes.append(Waste(
                    x=rect.x, y=rect.y,
                    width=rect.w, height=rect.h,
                    is_useful=is_useful
                ))
        return wastes


def _expand_parts(parts):
    expanded = []
    counter = 1
    for p in parts:
        for i in range(p.qty):
            expanded.append(Part(
                width=p.width, height=p.height, qty=1,
                label=p.label if p.label else ("D" + str(counter)),
                can_rotate=p.can_rotate
            ))
            counter += 1
    return expanded


def _sort_parts(parts, strategy="area_desc"):
    if strategy == "area_desc":
        return sorted(parts, key=lambda p: p.area, reverse=True)
    elif strategy == "long_desc":
        return sorted(parts, key=lambda p: max(p.width, p.height), reverse=True)
    elif strategy == "short_desc":
        return sorted(parts, key=lambda p: min(p.width, p.height), reverse=True)
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


def _pack_parts_into_sheet(sheet, parts, kerf, min_useful_size=100):
    packer = GuillotinePacker(sheet.width, sheet.height, kerf)
    placed_parts = []

    for part in parts:
        result = packer.insert(
            part.width, part.height,
            label=part.label,
            can_rotate=part.can_rotate
        )
        if result is not None:
            placed_parts.append(part)

    layout = SheetLayout(
        sheet=sheet,
        placements=packer.placements,
        wastes=packer.get_wastes(min_useful_size),
        cuts_count=0
    )

    return layout, placed_parts


def _count_guillotine_cuts(layout, kerf, min_useful_size=100):
    placements = layout.placements
    W = layout.sheet.width
    H = layout.sheet.height

    if not placements:
        return 0, [Waste(0, 0, W, H,
                         is_useful=(W >= min_useful_size and H >= min_useful_size))]

    def count_cuts_region(x, y, w, h, placed_in_region):
        if w <= 0 or h <= 0:
            return 0, []

        if not placed_in_region:
            is_useful = w >= min_useful_size and h >= min_useful_size
            return 0, [Waste(x, y, w, h, is_useful=is_useful)]

        if len(placed_in_region) == 1:
            p = placed_in_region[0]
            if p.x == x and p.y == y and p.width == w and p.height == h:
                return 0, []

        best_cuts = float('inf')
        best_wastes = []

        cut_lines_v = set()
        cut_lines_h = set()

        for p in placed_in_region:
            right = p.x + p.width
            if x < right < x + w:
                cut_lines_v.add(right)
            bottom = p.y + p.height
            if y < bottom < y + h:
                cut_lines_h.add(bottom)

        for cv in sorted(cut_lines_v):
            left_w = cv - x
            right_x = cv + kerf
            right_w = x + w - right_x

            if left_w <= 0 or right_w < 0:
                continue

            left_parts = []
            right_parts = []
            ok = True

            for p in placed_in_region:
                pr = p.x + p.width
                if pr <= cv:
                    left_parts.append(p)
                elif p.x >= right_x:
                    right_parts.append(p)
                else:
                    ok = False
                    break

            if not ok:
                continue

            c1, w1 = count_cuts_region(x, y, left_w, h, left_parts)
            c2, w2 = count_cuts_region(right_x, y, right_w, h, right_parts)
            total = 1 + c1 + c2

            if total < best_cuts:
                best_cuts = total
                best_wastes = w1 + w2

        for ch in sorted(cut_lines_h):
            top_h = ch - y
            bottom_y = ch + kerf
            bottom_h = y + h - bottom_y

            if top_h <= 0 or bottom_h < 0:
                continue

            top_parts = []
            bottom_parts = []
            ok = True

            for p in placed_in_region:
                pb = p.y + p.height
                if pb <= ch:
                    top_parts.append(p)
                elif p.y >= bottom_y:
                    bottom_parts.append(p)
                else:
                    ok = False
                    break

            if not ok:
                continue

            c1, w1 = count_cuts_region(x, y, w, top_h, top_parts)
            c2, w2 = count_cuts_region(x, bottom_y, w, bottom_h, bottom_parts)
            total = 1 + c1 + c2

            if total < best_cuts:
                best_cuts = total
                best_wastes = w1 + w2

        if best_cuts == float('inf'):
            return len(placed_in_region), []

        return best_cuts, best_wastes

    cuts, wastes = count_cuts_region(0, 0, W, H, list(placements))
    return cuts, wastes


def optimize_single_sheet(sheet, parts, kerf, cut_price, min_useful_size=100):
    layout, placed_parts = _pack_parts_into_sheet(sheet, parts, kerf, min_useful_size)
    cuts_count, wastes = _count_guillotine_cuts(layout, kerf, min_useful_size)
    layout.cuts_count = cuts_count
    layout.wastes = wastes
    return layout, placed_parts


def _remove_placed(remaining, placed):
    to_remove = []
    for p in placed:
        for i, r in enumerate(remaining):
            if i not in to_remove:
                if (r.width == p.width and r.height == p.height and
                    r.label == p.label):
                    to_remove.append(i)
                    break

    new_remaining = []
    for i, r in enumerate(remaining):
        if i not in to_remove:
            new_remaining.append(r)

    return new_remaining


def _evaluate_result(result):
    all_placed = len(result.unplaced_parts) == 0
    return (
        all_placed,
        -result.total_cost,
        result.total_efficiency,
        -len(result.layouts)
    )


def optimize(sheets, parts, kerf=2, cut_price=75, min_useful_size=100):
    expanded = _expand_parts(parts)

    strategies = ["area_desc", "long_desc", "short_desc", "perimeter_desc"]

    valid_sheets = [s for s in sheets if _can_fit_any(s, expanded, kerf)]

    if not valid_sheets:
        return CuttingResult(
            cut_price=cut_price, kerf=kerf,
            unplaced_parts=expanded
        )

    best_result = None

    def try_update_best(result):
        nonlocal best_result
        if not result.layouts:
            return
        if best_result is None:
            best_result = result
        elif _evaluate_result(result) > _evaluate_result(best_result):
            best_result = result

    # ВАРИАНТ 1: Однотипные листы
    for strategy in strategies:
        sorted_parts = _sort_parts(deepcopy(expanded), strategy)

        for sheet in valid_sheets:
            result = CuttingResult(cut_price=cut_price, kerf=kerf)
            remaining = list(sorted_parts)

            for _ in range(50):
                if not remaining:
                    break
                if not _can_fit_any(sheet, remaining, kerf):
                    break

                layout, placed = optimize_single_sheet(
                    deepcopy(sheet), remaining, kerf, cut_price, min_useful_size)

                if not placed:
                    break

                result.layouts.append(layout)
                remaining = _remove_placed(remaining, placed)

            result.unplaced_parts = remaining
            try_update_best(result)

    # ВАРИАНТ 2: Жадный смешанный - минимум стоимости
    for strategy in strategies:
        sorted_parts = _sort_parts(deepcopy(expanded), strategy)
        result = CuttingResult(cut_price=cut_price, kerf=kerf)
        remaining = list(sorted_parts)

        for _ in range(50):
            if not remaining:
                break

            best_sheet_layout = None
            best_sheet_placed = None
            best_sheet_score = None

            for sheet in valid_sheets:
                if not _can_fit_any(sheet, remaining, kerf):
                    continue

                layout, placed = optimize_single_sheet(
                    deepcopy(sheet), remaining, kerf, cut_price, min_useful_size)

                if not placed:
                    continue

                total_placed_area = sum(p.width * p.height for p in placed)
                sheet_total_cost = sheet.price + layout.cuts_count * cut_price
                cost_per_area = sheet_total_cost / max(total_placed_area, 1)

                score = (
                    len(placed),
                    -cost_per_area,
                    layout.efficiency,
                )

                if best_sheet_score is None or score > best_sheet_score:
                    best_sheet_score = score
                    best_sheet_layout = layout
                    best_sheet_placed = placed

            if best_sheet_layout is None:
                break

            result.layouts.append(best_sheet_layout)
            remaining = _remove_placed(remaining, best_sheet_placed)

        result.unplaced_parts = remaining
        try_update_best(result)

    # ВАРИАНТ 3: Жадный смешанный - минимум стоимости листа
    for strategy in strategies:
        sorted_parts = _sort_parts(deepcopy(expanded), strategy)
        result = CuttingResult(cut_price=cut_price, kerf=kerf)
        remaining = list(sorted_parts)

        for _ in range(50):
            if not remaining:
                break

            best_sheet_layout = None
            best_sheet_placed = None
            best_sheet_score = None

            for sheet in valid_sheets:
                if not _can_fit_any(sheet, remaining, kerf):
                    continue

                layout, placed = optimize_single_sheet(
                    deepcopy(sheet), remaining, kerf, cut_price, min_useful_size)

                if not placed:
                    continue

                sheet_total_cost = sheet.price + layout.cuts_count * cut_price

                score = (
                    len(placed),
                    -sheet_total_cost,
                    layout.efficiency,
                )

                if best_sheet_score is None or score > best_sheet_score:
                    best_sheet_score = score
                    best_sheet_layout = layout
                    best_sheet_placed = placed

            if best_sheet_layout is None:
                break

            result.layouts.append(best_sheet_layout)
            remaining = _remove_placed(remaining, best_sheet_placed)

        result.unplaced_parts = remaining
        try_update_best(result)

    # ВАРИАНТ 4: Группировка одинаковых деталей
    for strategy in strategies:
        sorted_parts = _sort_parts(deepcopy(expanded), strategy)

        groups = {}
        for p in sorted_parts:
            key = (min(p.width, p.height), max(p.width, p.height), p.label)
            if key not in groups:
                groups[key] = []
            groups[key].append(p)

        sorted_groups = sorted(groups.values(),
                               key=lambda g: g[0].area * len(g), reverse=True)

        result = CuttingResult(cut_price=cut_price, kerf=kerf)
        remaining = []
        for g in sorted_groups:
            remaining.extend(g)

        for _ in range(50):
            if not remaining:
                break

            best_sheet_layout = None
            best_sheet_placed = None
            best_sheet_score = None

            for sheet in valid_sheets:
                if not _can_fit_any(sheet, remaining, kerf):
                    continue

                layout, placed = optimize_single_sheet(
                    deepcopy(sheet), remaining, kerf, cut_price, min_useful_size)

                if not placed:
                    continue

                total_placed_area = sum(p.width * p.height for p in placed)
                sheet_total_cost = sheet.price + layout.cuts_count * cut_price
                waste_area = sheet.area - total_placed_area
                cost_efficiency = total_placed_area / max(sheet_total_cost, 1)

                score = (
                    len(placed),
                    cost_efficiency,
                    -waste_area,
                )

                if best_sheet_score is None or score > best_sheet_score:
                    best_sheet_score = score
                    best_sheet_layout = layout
                    best_sheet_placed = placed

            if best_sheet_layout is None:
                break

            result.layouts.append(best_sheet_layout)
            remaining = _remove_placed(remaining, best_sheet_placed)

        result.unplaced_parts = remaining
        try_update_best(result)

    if best_result is None:
        best_result = CuttingResult(
            cut_price=cut_price, kerf=kerf,
            unplaced_parts=expanded
        )

    return best_result


# ================================================================
# ВИЗУАЛИЗАЦИЯ (оригинал)
# ================================================================

PART_COLORS = [
    '#4CAF50', '#2196F3', '#FF9800', '#9C27B0',
    '#00BCD4', '#F44336', '#8BC34A', '#3F51B5',
    '#FFEB3B', '#795548', '#607D8B', '#E91E63',
    '#009688', '#FF5722', '#CDDC39', '#673AB7',
]

WASTE_COLOR = '#FFCDD2'
USEFUL_WASTE_COLOR = '#FFF9C4'
SHEET_BG = '#F5F5F5'


def _get_font(size):
    paths = [
        'C:/Windows/Fonts/arial.ttf',
        'C:/Windows/Fonts/segoeui.ttf',
        'C:/Windows/Fonts/tahoma.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    ]
    size = max(size, 6)
    for fp in paths:
        try:
            return ImageFont.truetype(fp, size)
        except:
            continue
    return ImageFont.load_default()


def _text_fits(draw, text, font, max_w, max_h):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    return tw <= max_w and th <= max_h


def _find_font_size(draw, text, max_w, max_h, max_size=20, min_size=6):
    for size in range(max_size, min_size - 1, -1):
        font = _get_font(size)
        if _text_fits(draw, text, font, max_w, max_h):
            return font, size
    return None, 0


def _draw_text_if_fits(draw, x, y, text, max_w, max_h,
                       fill='white', max_size=16, min_size=6):
    font, size = _find_font_size(draw, text, max_w, max_h, max_size, min_size)
    if font and size >= min_size:
        draw.text((x, y), text, fill=fill, font=font)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_h = bbox[3] - bbox[1]
        return text_h
    return 0


def render_layout(layout, sheet_index=0, max_w=1600, max_h=1100):
    scale_w = (max_w - 120) / layout.sheet.width
    scale_h = (max_h - 160) / layout.sheet.height
    scale = min(scale_w, scale_h, 1.0)
    scale = max(scale, 0.03)

    margin = 60
    header = 40

    img_w = int(layout.sheet.width * scale) + margin * 2
    img_h = int(layout.sheet.height * scale) + margin * 2 + header + 50

    img = Image.new('RGB', (img_w, img_h), 'white')
    draw = ImageDraw.Draw(img)

    font_title = _get_font(14)
    decor_text = ''
    if hasattr(layout.sheet, 'decor') and layout.sheet.decor:
        decor_text = ' [' + layout.sheet.decor + ']'

    title = ('Лист ' + str(sheet_index + 1) + ': ' +
             str(layout.sheet.width) + 'x' + str(layout.sheet.height) + ' мм' +
             decor_text +
             '  |  Заполнение: ' + str(round(layout.efficiency, 1)) + '%' +
             '  |  Резов: ' + str(layout.cuts_count) +
             '  |  Цена: ' + str(layout.sheet.price) + ' руб')
    draw.text((margin, 8), title, fill='black', font=font_title)

    sx = margin
    sy = margin + header
    sw = int(layout.sheet.width * scale)
    sh = int(layout.sheet.height * scale)

    draw.rectangle([sx, sy, sx + sw, sy + sh],
                   fill=SHEET_BG, outline='#212121', width=2)

    # Обрезки
    for waste in layout.wastes:
        wx0 = sx + int(waste.x * scale)
        wy0 = sy + int(waste.y * scale)
        wx1 = wx0 + int(waste.width * scale)
        wy1 = wy0 + int(waste.height * scale)

        if wx1 - wx0 < 2 or wy1 - wy0 < 2:
            continue

        color = USEFUL_WASTE_COLOR if waste.is_useful else WASTE_COLOR
        draw.rectangle([wx0, wy0, wx1, wy1],
                       fill=color, outline='#BDBDBD', width=1)

        box_w = wx1 - wx0 - 6
        box_h = wy1 - wy0 - 4

        if box_w > 20 and box_h > 10:
            txt = str(waste.width) + 'x' + str(waste.height)
            h_used = _draw_text_if_fits(
                draw, wx0 + 3, wy0 + 2, txt,
                box_w, box_h,
                fill='#757575', max_size=11, min_size=6
            )
            if waste.is_useful and h_used > 0 and box_h - h_used - 2 > 8:
                _draw_text_if_fits(
                    draw, wx0 + 3, wy0 + 2 + h_used + 1,
                    "остаток", box_w, box_h - h_used - 2,
                    fill='#F57F17', max_size=9, min_size=6
                )

    # Детали
    for i, pl in enumerate(layout.placements):
        color = PART_COLORS[i % len(PART_COLORS)]

        px0 = sx + int(pl.x * scale)
        py0 = sy + int(pl.y * scale)
        px1 = px0 + int(pl.width * scale)
        py1 = py0 + int(pl.height * scale)

        if px1 - px0 < 2 or py1 - py0 < 2:
            continue

        draw.rectangle([px0, py0, px1, py1],
                       fill=color, outline='#212121', width=2)

        pad = 4
        box_w = (px1 - px0) - pad * 2
        box_h = (py1 - py0) - pad * 2

        if box_w < 15 or box_h < 8:
            continue

        rot = " R" if pl.rotated else ""
        label_text = pl.part_label + rot
        dim_text = str(pl.width) + 'x' + str(pl.height)

        if box_h > 20:
            half_h = box_h // 2 - 1

            h1 = _draw_text_if_fits(
                draw, px0 + pad, py0 + pad,
                label_text, box_w, half_h,
                fill='white', max_size=14, min_size=6
            )

            if h1 > 0:
                _draw_text_if_fits(
                    draw, px0 + pad, py0 + pad + h1 + 2,
                    dim_text, box_w, box_h - h1 - 2,
                    fill='#E8F5E9', max_size=12, min_size=6
                )
            else:
                _draw_text_if_fits(
                    draw, px0 + pad, py0 + pad,
                    dim_text, box_w, box_h,
                    fill='white', max_size=12, min_size=6
                )
        else:
            _draw_text_if_fits(
                draw, px0 + pad, py0 + pad,
                dim_text, box_w, box_h,
                fill='white', max_size=11, min_size=6
            )

    # Размерные линии
    font_dim = _get_font(10)

    ay = sy + sh + 10
    draw.line([(sx, ay), (sx + sw, ay)], fill='black', width=1)
    draw.line([(sx, ay - 3), (sx, ay + 3)], fill='black', width=1)
    draw.line([(sx + sw, ay - 3), (sx + sw, ay + 3)], fill='black', width=1)

    dim_w_text = str(layout.sheet.width) + " мм"
    bbox = draw.textbbox((0, 0), dim_w_text, font=font_dim)
    tw = bbox[2] - bbox[0]
    draw.text((sx + sw // 2 - tw // 2, ay + 4),
              dim_w_text, fill='black', font=font_dim)

    ax = sx - 10
    draw.line([(ax, sy), (ax, sy + sh)], fill='black', width=1)
    draw.line([(ax - 3, sy), (ax + 3, sy)], fill='black', width=1)
    draw.line([(ax - 3, sy + sh), (ax + 3, sy + sh)], fill='black', width=1)

    dim_h_text = str(layout.sheet.height)
    bbox = draw.textbbox((0, 0), dim_h_text, font=font_dim)
    th = bbox[3] - bbox[1]
    draw.text((5, sy + sh // 2 - th // 2),
              dim_h_text, fill='black', font=font_dim)

    # Легенда
    ly = sy + sh + 30
    font_legend = _get_font(9)
    items = [
        (PART_COLORS[0], "Деталь"),
        (USEFUL_WASTE_COLOR, "Полезный остаток"),
        (WASTE_COLOR, "Отход"),
    ]
    lx = sx
    for color, text in items:
        draw.rectangle([lx, ly, lx + 12, ly + 12],
                       fill=color, outline='#999')
        draw.text((lx + 16, ly), text, fill='black', font=font_legend)
        lx += 150

    return img


# ================================================================
# КАТАЛОГ ДЕКОРОВ
# ================================================================

DEFAULT_DECORS = {
    'Белый': {
        'color_code': '#FFFFFF', 'border_color': '#CCCCCC',
        'sheets': [
            [2700,100,645],[2700,300,1093],[2700,400,1324],[2700,500,1865],[2700,600,2082],
            [2000,300,683],[2000,400,910],[2000,500,1238],[2000,600,1405],
            [1200,300,626],[1200,400,754],[800,200,276],[800,300,335],[800,400,432],
            [600,300,264],[600,200,218],
        ]
    },
    'Белый Премиум': {
        'color_code': '#F5F5F0', 'border_color': '#D4AF37',
        'sheets': [
            [2700,100,710],[2700,300,1200],[2700,400,1456],[2700,500,2050],[2700,600,2290],
            [2000,300,750],[2000,400,1000],[2000,500,1360],[2000,600,1545],
            [1200,300,688],[1200,400,830],[800,200,303],[800,300,368],[800,400,475],
            [600,300,290],[600,200,240],
        ]
    },
    'Дуб Сонома': {
        'color_code': '#C4A882', 'border_color': '#8B6914',
        'sheets': [
            [2700,100,680],[2700,300,1155],[2700,400,1400],[2700,500,1970],[2700,600,2200],
            [2000,300,720],[2000,400,960],[2000,500,1310],[2000,600,1485],
            [1200,300,662],[1200,400,797],[800,200,292],[800,300,354],[800,400,457],
            [600,300,279],[600,200,230],
        ]
    },
    'Бетон': {
        'color_code': '#A0A0A0', 'border_color': '#666666',
        'sheets': [
            [2700,100,695],[2700,300,1180],[2700,400,1430],[2700,500,2015],[2700,600,2250],
            [2000,300,740],[2000,400,985],[2000,500,1340],[2000,600,1520],
            [1200,300,678],[1200,400,816],[800,200,299],[800,300,363],[800,400,468],
            [600,300,286],[600,200,236],
        ]
    },
}


def get_config_path():
    home = os.path.expanduser('~')
    d = os.path.join(home, '.cutting_optimizer')
    if not os.path.exists(d):
        os.makedirs(d)
    return os.path.join(d, 'decors.json')


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


def get_sheets_for_decors(catalog, selected):
    sheets = []
    for name in selected:
        if name in catalog:
            for s in catalog[name]['sheets']:
                label = name + ' ' + str(s[0]) + 'x' + str(s[1])
                sheets.append(Sheet(s[0], s[1], s[2], label, decor=name))
    return sheets


# ================================================================
# ДИАЛОГ РЕДАКТИРОВАНИЯ ДЕКОРА
# ================================================================

class DecorEditorDialog:
    def __init__(self, parent, decor_name, decor_info, is_new=False):
        self.result = None
        self.dlg = tk.Toplevel(parent)
        self.dlg.title('Новый декор' if is_new else ('Редактирование: ' + decor_name))
        self.dlg.geometry('650x550')
        self.dlg.grab_set()

        nf = ttk.LabelFrame(self.dlg, text='Название', padding=5)
        nf.pack(fill=tk.X, padx=10, pady=5)
        self.name_var = tk.StringVar(value=decor_name)
        ttk.Entry(nf, textvariable=self.name_var, width=30, font=('Arial', 12)).pack(fill=tk.X)

        cf = ttk.LabelFrame(self.dlg, text='Цвет', padding=5)
        cf.pack(fill=tk.X, padx=10, pady=5)
        cfr = ttk.Frame(cf)
        cfr.pack(fill=tk.X)
        self.color_canvas = tk.Canvas(cfr, width=60, height=40, highlightthickness=2,
                                       highlightbackground=decor_info.get('border_color', '#999'))
        self.color_canvas.pack(side=tk.LEFT, padx=5)
        self.color_canvas.create_rectangle(2, 2, 58, 38,
            fill=decor_info.get('color_code', '#CCC'), outline='', tags='cr')
        self.color_var = tk.StringVar(value=decor_info.get('color_code', '#CCC'))
        ttk.Label(cfr, textvariable=self.color_var, font=('Consolas', 11)).pack(side=tk.LEFT, padx=5)
        ttk.Button(cfr, text='Выбрать цвет...', command=self.pick_color).pack(side=tk.LEFT, padx=10)

        sf = ttk.LabelFrame(self.dlg, text='Листы', padding=5)
        sf.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        cols = ('Ширина', 'Высота', 'Цена')
        self.tree = ttk.Treeview(sf, columns=cols, show='headings', height=10)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=100, anchor='center')
        sb = ttk.Scrollbar(sf, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        for s in decor_info.get('sheets', []):
            self.tree.insert('', 'end', values=(s[0], s[1], s[2]))

        af = ttk.Frame(self.dlg)
        af.pack(fill=tk.X, padx=10, pady=3)
        ttk.Label(af, text='Ш:').pack(side=tk.LEFT)
        self.nw = ttk.Entry(af, width=6); self.nw.pack(side=tk.LEFT, padx=2)
        ttk.Label(af, text='В:').pack(side=tk.LEFT)
        self.nh = ttk.Entry(af, width=6); self.nh.pack(side=tk.LEFT, padx=2)
        ttk.Label(af, text='Цена:').pack(side=tk.LEFT)
        self.np = ttk.Entry(af, width=7); self.np.pack(side=tk.LEFT, padx=2)

        bf = ttk.Frame(self.dlg)
        bf.pack(fill=tk.X, padx=10, pady=2)
        ttk.Button(bf, text='Добавить лист', command=self.add_s).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text='Удалить', command=self.del_s).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text='Изменить цену', command=self.edit_price).pack(side=tk.LEFT, padx=2)

        okf = ttk.Frame(self.dlg)
        okf.pack(fill=tk.X, padx=10, pady=10)
        tk.Button(okf, text='Сохранить', command=self.on_ok,
                  bg='#4CAF50', fg='white', font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=5, ipadx=20, ipady=5)
        tk.Button(okf, text='Отмена', command=self.dlg.destroy,
                  font=('Arial', 11)).pack(side=tk.LEFT, padx=5, ipadx=20, ipady=5)

    def pick_color(self):
        c = colorchooser.askcolor(initialcolor=self.color_var.get(), title='Цвет декора')
        if c and c[1]:
            self.color_var.set(c[1])
            self.color_canvas.delete('cr')
            self.color_canvas.create_rectangle(2, 2, 58, 38, fill=c[1], outline='', tags='cr')

    def add_s(self):
        try:
            w = int(self.nw.get()); h = int(self.nh.get()); p = float(self.np.get())
        except ValueError:
            messagebox.showerror('Ошибка', 'Введите числа!'); return
        self.tree.insert('', 'end', values=(w, h, p))
        self.nw.delete(0, tk.END); self.nh.delete(0, tk.END); self.np.delete(0, tk.END)

    def del_s(self):
        sel = self.tree.selection()
        if sel: self.tree.delete(sel[0])

    def edit_price(self):
        sel = self.tree.selection()
        if not sel: return
        vals = self.tree.item(sel[0], 'values')
        np = simpledialog.askfloat('Цена', 'Новая цена для ' + str(vals[0]) + 'x' + str(vals[1]) + ':',
                                    initialvalue=float(vals[2]), parent=self.dlg)
        if np is not None:
            self.tree.item(sel[0], values=(vals[0], vals[1], np))

    def on_ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror('Ошибка', 'Введите название!'); return
        sheets = []
        for item in self.tree.get_children():
            v = self.tree.item(item, 'values')
            sheets.append([int(v[0]), int(v[1]), float(v[2])])
        if not sheets:
            messagebox.showerror('Ошибка', 'Добавьте листы!'); return
        self.result = {'name': name, 'info': {
            'color_code': self.color_var.get(), 'border_color': self.color_var.get(), 'sheets': sheets}}
        self.dlg.destroy()


# ================================================================
# GUI ПРИЛОЖЕНИЕ
# ================================================================

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
        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left = ttk.Frame(main, width=520)
        main.add(left, weight=1)
        right = ttk.Frame(main)
        main.add(right, weight=2)

        self.build_left(left)
        self.build_right(right)

    def build_left(self, parent):
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.decor_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.decor_tab, text='  Декоры ЛДСП  ')

        parts_tab = ttk.Frame(self.notebook)
        self.notebook.add(parts_tab, text='  Детали  ')

        params_tab = ttk.Frame(self.notebook)
        self.notebook.add(params_tab, text='  Параметры  ')

        self.build_decor_tab(self.decor_tab)
        self.build_parts_tab(parts_tab)
        self.build_params_tab(params_tab)

        bf = ttk.Frame(parent)
        bf.pack(fill=tk.X, padx=5, pady=5)
        tk.Button(bf, text='РАССЧИТАТЬ РАСКРОЙ', command=self.calculate,
                  bg='#4CAF50', fg='white', font=('Arial', 13, 'bold'),
                  cursor='hand2').pack(fill=tk.X, ipady=12)
        tk.Button(bf, text='Сохранить карты раскроя в PNG', command=self.save_images,
                  bg='#2196F3', fg='white', font=('Arial', 10)).pack(fill=tk.X, pady=5, ipady=6)

    def build_decor_tab(self, parent):
        for w in parent.winfo_children():
            w.destroy()
        self.decor_vars = {}

        top = ttk.Frame(parent)
        top.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(top, text='Декоры ЛДСП:', font=('Arial', 11, 'bold')).pack(side=tk.LEFT)
        ttk.Button(top, text='+ Новый декор', command=self.add_decor).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top, text='Сбросить', command=self.reset_decors).pack(side=tk.RIGHT, padx=2)

        canvas = tk.Canvas(parent, highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))

        for dn, info in self.decor_catalog.items():
            var = tk.BooleanVar(value=False)
            self.decor_vars[dn] = var

            card = ttk.LabelFrame(inner, text=dn, padding=8)
            card.pack(fill=tk.X, padx=10, pady=4)

            tr = ttk.Frame(card)
            tr.pack(fill=tk.X)

            cc = tk.Canvas(tr, width=45, height=45, highlightthickness=2,
                           highlightbackground=info.get('border_color', '#999'))
            cc.pack(side=tk.LEFT, padx=(0, 8))
            cc.create_rectangle(2, 2, 43, 43, fill=info.get('color_code', '#CCC'),
                                outline=info.get('border_color', '#999'), width=1)

            inf = ttk.Frame(tr)
            inf.pack(side=tk.LEFT, fill=tk.X, expand=True)
            cnt = len(info.get('sheets', []))
            prices = [s[2] for s in info.get('sheets', [])]
            if prices:
                ttk.Label(inf, text='Листов: ' + str(cnt)).pack(anchor='w')
                ttk.Label(inf, text='Цены: ' + str(int(min(prices))) + ' - ' +
                          str(int(max(prices))) + ' руб').pack(anchor='w')

            btf = ttk.Frame(tr)
            btf.pack(side=tk.RIGHT)
            ttk.Checkbutton(btf, text='Использовать', variable=var).pack(anchor='e', pady=1)
            br = ttk.Frame(btf)
            br.pack(anchor='e')
            name_copy = dn
            ttk.Button(br, text='Редактировать',
                       command=lambda n=name_copy: self.edit_decor(n)).pack(side=tk.LEFT, padx=1)
            ttk.Button(br, text='Удалить',
                       command=lambda n=name_copy: self.del_decor(n)).pack(side=tk.LEFT, padx=1)

    def add_decor(self):
        dlg = DecorEditorDialog(self.root, 'Новый декор',
                                 {'color_code': '#DDD', 'border_color': '#999', 'sheets': []}, True)
        self.root.wait_window(dlg.dlg)
        if dlg.result:
            n = dlg.result['name']
            if n in self.decor_catalog:
                messagebox.showerror('Ошибка', 'Такой декор уже есть!'); return
            self.decor_catalog[n] = dlg.result['info']
            save_decors(self.decor_catalog)
            self.build_decor_tab(self.decor_tab)

    def edit_decor(self, name):
        if name not in self.decor_catalog: return
        dlg = DecorEditorDialog(self.root, name, self.decor_catalog[name])
        self.root.wait_window(dlg.dlg)
        if dlg.result:
            nn = dlg.result['name']
            if nn != name:
                del self.decor_catalog[name]
            self.decor_catalog[nn] = dlg.result['info']
            save_decors(self.decor_catalog)
            self.build_decor_tab(self.decor_tab)

    def del_decor(self, name):
        if messagebox.askyesno('Удаление', 'Удалить декор "' + name + '"?'):
            if name in self.decor_catalog:
                del self.decor_catalog[name]
                save_decors(self.decor_catalog)
                self.build_decor_tab(self.decor_tab)

    def reset_decors(self):
        if messagebox.askyesno('Сброс', 'Вернуть заводские декоры?'):
            self.decor_catalog = deepcopy(DEFAULT_DECORS)
            save_decors(self.decor_catalog)
            self.build_decor_tab(self.decor_tab)

    def get_selected_decors(self):
        return [n for n, v in self.decor_vars.items() if v.get()]

    # Детали
    def build_parts_tab(self, parent):
        cols = ('Ширина', 'Высота', 'Кол-во', 'Название', 'Вращение')
        self.parts_tree = ttk.Treeview(parent, columns=cols, show='headings', height=10)
        for c in cols:
            self.parts_tree.heading(c, text=c)
            self.parts_tree.column(c, width=(100 if c == 'Название' else 70), anchor='center')
        self.parts_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        af = ttk.LabelFrame(parent, text='Добавить деталь', padding=5)
        af.pack(fill=tk.X, padx=5, pady=3)

        r1 = ttk.Frame(af); r1.pack(fill=tk.X, pady=2)
        ttk.Label(r1, text='Ширина:').pack(side=tk.LEFT, padx=2)
        self.p_w = ttk.Entry(r1, width=7); self.p_w.pack(side=tk.LEFT, padx=2)
        ttk.Label(r1, text='Высота:').pack(side=tk.LEFT, padx=2)
        self.p_h = ttk.Entry(r1, width=7); self.p_h.pack(side=tk.LEFT, padx=2)

        r2 = ttk.Frame(af); r2.pack(fill=tk.X, pady=2)
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
            w = int(self.p_w.get()); h = int(self.p_h.get()); q = int(self.p_qty.get())
            lbl = self.p_label.get().strip() or (str(w) + 'x' + str(h))
            rot = self.p_rotate.get()
        except ValueError:
            messagebox.showerror('Ошибка', 'Введите числа!'); return
        if w <= 0 or h <= 0 or q <= 0:
            messagebox.showerror('Ошибка', 'Значения должны быть > 0!'); return
        self.parts_data.append(Part(w, h, q, lbl, rot))
        self.parts_tree.insert('', 'end', values=(w, h, q, lbl, 'Да' if rot else 'Нет'))
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
            for i in self.parts_tree.get_children(): self.parts_tree.delete(i)

    def load_default_parts(self):
        for w, h, q, l, r in [(160, 690, 2, 'Бок', True), (160, 658, 1, 'Царга', True), (160, 1618, 2, 'Полка', True)]:
            self.parts_data.append(Part(w, h, q, l, r))
            self.parts_tree.insert('', 'end', values=(w, h, q, l, 'Да' if r else 'Нет'))

    # Параметры
    def build_params_tab(self, parent):
        pf = ttk.LabelFrame(parent, text='Настройки', padding=15)
        pf.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(pf, text='Пропил (мм):').grid(row=0, column=0, sticky='w', pady=5)
        self.kerf_var = tk.StringVar(value='2')
        ttk.Entry(pf, textvariable=self.kerf_var, width=8).grid(row=0, column=1, padx=10, pady=5)
        ttk.Label(pf, text='Цена реза (руб):').grid(row=1, column=0, sticky='w', pady=5)
        self.cut_price_var = tk.StringVar(value='75')
        ttk.Entry(pf, textvariable=self.cut_price_var, width=8).grid(row=1, column=1, padx=10, pady=5)
        ttk.Label(pf, text='Мин. остаток (мм):').grid(row=2, column=0, sticky='w', pady=5)
        self.min_useful_var = tk.StringVar(value='100')
        ttk.Entry(pf, textvariable=self.min_useful_var, width=8).grid(row=2, column=1, padx=10, pady=5)

        tf = ttk.LabelFrame(parent, text='Подсказки', padding=10)
        tf.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(tf, text='* Пропил - ширина реза пилы (2-5 мм)\n'
                  '* Цена реза - стоимость одного пропила\n'
                  '* Мин. остаток - минимальный полезный обрезок\n'
                  '* Декоры и цены сохраняются автоматически\n'
                  '* Отключите вращение для направленной текстуры',
                  font=('Arial', 9)).pack(anchor='w')

    # Правая панель
    def build_right(self, parent):
        rf = ttk.LabelFrame(parent, text='Результат', padding=5)
        rf.pack(fill=tk.X, padx=5, pady=5)
        self.report = scrolledtext.ScrolledText(rf, height=12, font=('Consolas', 10))
        self.report.pack(fill=tk.X)

        imf = ttk.LabelFrame(parent, text='Карты раскроя', padding=5)
        imf.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.canvas = tk.Canvas(imf, bg='#E0E0E0')
        sv = ttk.Scrollbar(imf, orient=tk.VERTICAL, command=self.canvas.yview)
        sh = ttk.Scrollbar(imf, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=sv.set, xscrollcommand=sh.set)
        sv.pack(side=tk.RIGHT, fill=tk.Y); sh.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.inner_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner_frame, anchor='nw')
        self.inner_frame.bind('<Configure>',
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))

    # Расчёт
    def calculate(self):
        sel = self.get_selected_decors()
        if not sel:
            messagebox.showwarning('Внимание', 'Выберите хотя бы один декор!'); return
        if not self.parts_data:
            messagebox.showwarning('Внимание', 'Добавьте детали!'); return
        try:
            kerf = int(self.kerf_var.get())
            cut_price = float(self.cut_price_var.get())
            min_useful = int(self.min_useful_var.get())
        except ValueError:
            messagebox.showerror('Ошибка', 'Проверьте параметры!'); return

        all_sheets = get_sheets_for_decors(self.decor_catalog, sel)
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
        sep = '=' * 60
        self.report.insert(tk.END, sep + '\n')
        self.report.insert(tk.END, 'РЕЗУЛЬТАТ РАСКРОЯ\n')
        self.report.insert(tk.END, sep + '\n\n')

        for i, layout in enumerate(r.layouts):
            dec = ''
            if hasattr(layout.sheet, 'decor') and layout.sheet.decor:
                dec = ' [' + layout.sheet.decor + ']'
            self.report.insert(tk.END, '--- Лист ' + str(i+1) + ' ---\n')
            self.report.insert(tk.END, '  Размер: ' + str(layout.sheet.width) + 'x' +
                               str(layout.sheet.height) + ' мм' + dec + '\n')
            self.report.insert(tk.END, '  Цена листа: ' + str(layout.sheet.price) + ' руб\n')
            self.report.insert(tk.END, '  Резов: ' + str(layout.cuts_count) + '\n')
            self.report.insert(tk.END, '  Заполнение: ' + str(round(layout.efficiency, 1)) + '%\n')
            self.report.insert(tk.END, '  Деталей: ' + str(len(layout.placements)) + '\n')

            for pl in layout.placements:
                rot = ' (повернута)' if pl.rotated else ''
                self.report.insert(tk.END, '    * ' + str(pl.width) + 'x' + str(pl.height) +
                                   ' (' + pl.part_label + ')' + rot +
                                   ' -> (' + str(pl.x) + ', ' + str(pl.y) + ')\n')

            useful = [w for w in layout.wastes if w.is_useful]
            trash = [w for w in layout.wastes if not w.is_useful]

            if useful:
                self.report.insert(tk.END, '  Полезные остатки:\n')
                for w in useful:
                    area_m2 = w.area / 1000000.0
                    self.report.insert(tk.END, '    * ' + str(w.width) + 'x' + str(w.height) +
                                       ' мм (' + str(round(area_m2, 4)) + ' м2)\n')
            if trash:
                ta = sum(t.area for t in trash)
                self.report.insert(tk.END, '  Отходы: ' + str(len(trash)) + ' шт (' +
                                   str(round(ta / 1000000.0, 4)) + ' м2)\n')

        self.report.insert(tk.END, '\n' + sep + '\n')
        self.report.insert(tk.END, 'Листов: ' + str(len(r.layouts)) + '\n')
        self.report.insert(tk.END, 'Стоимость листов: ' + str(round(r.total_sheets_cost)) + ' руб\n')
        self.report.insert(tk.END, 'Всего резов: ' + str(r.total_cuts_count) + '\n')
        self.report.insert(tk.END, 'Стоимость резов: ' + str(round(r.total_cuts_cost)) + ' руб\n')
        self.report.insert(tk.END, 'ИТОГО: ' + str(round(r.total_cost)) + ' руб\n')
        self.report.insert(tk.END, 'Эффективность: ' + str(round(r.total_efficiency, 1)) + '%\n')

        if r.unplaced_parts:
            self.report.insert(tk.END, '\n!!! НЕ ПОМЕСТИЛИСЬ (' + str(len(r.unplaced_parts)) + ' шт):\n')
            for p in r.unplaced_parts:
                self.report.insert(tk.END, '  * ' + str(p.width) + 'x' + str(p.height) +
                                   ' (' + p.label + ')\n')

        # Карты раскроя
        for w in self.inner_frame.winfo_children(): w.destroy()
        self.photo_refs.clear(); self.result_images = []

        for i, layout in enumerate(r.layouts):
            img = render_layout(layout, sheet_index=i, max_w=900, max_h=600)
            self.result_images.append(img)
            photo = ImageTk.PhotoImage(img)
            self.photo_refs.append(photo)
            ttk.Label(self.inner_frame, image=photo).pack(padx=5, pady=5)

        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def save_images(self):
        if not self.result_images:
            messagebox.showinfo('Инфо', 'Сначала выполните расчёт!'); return
        folder = filedialog.askdirectory(title='Папка для сохранения')
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
