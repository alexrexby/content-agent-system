#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор карточек карусели для @expert_channel
1080x1350 (4:5). Палитра: белый фон, голубые перебивки, серый в тексте.

НОВУЮ КАРУСЕЛЬ ДЕЛАЕШЬ ТАК: добавляешь блок в DECKS внизу файла. Вёрстка считается сама.
Запуск:  python3 build_karusel.py            - собрать все
         python3 build_karusel.py voda       - собрать одну

ФОТО (по желанию): положи рядом файл photo.jpg - он подставится на обложку и финал.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os, math

W, H = 1080, 1350
PAD = 84
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- палитра ----------
BLUE       = (47, 128, 237)
BLUE_DARK  = (31, 95, 196)
BLUE_DEEP  = (14, 52, 120)
BLUE_NIGHT = (9, 34, 82)
BLUE_SOFT  = (234, 242, 254)
BLUE_TINT  = (245, 249, 255)
INK        = (18, 25, 40)
GRAY       = (108, 117, 133)
GRAY_LIGHT = (163, 172, 187)
LINE       = (230, 236, 245)
WHITE      = (255, 255, 255)

MAC_FONTS = {
    "Black": "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "Heavy": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "Bold": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "Semibold": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "Medium": "/System/Library/Fonts/Supplemental/Arial.ttf",
    "Regular": "/System/Library/Fonts/Supplemental/Arial.ttf"
}
def font(style, size):
    linux_p = f"/usr/share/fonts/truetype/lato/Lato-{style}.ttf"
    if os.path.exists(linux_p):
        return ImageFont.truetype(linux_p, size)
    mac_p = MAC_FONTS.get(style, "/System/Library/Fonts/Supplemental/Arial.ttf")
    if os.path.exists(mac_p):
        return ImageFont.truetype(mac_p, size)
    return ImageFont.load_default()
BLACK_, HEAVY, BOLD, SEMI, MED, REG = "Black", "Heavy", "Bold", "Semibold", "Medium", "Regular"

NICK = os.getenv("EXPERT_HANDLE", "@expert_channel")

# ---------- текст ----------
def wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if draw.textlength(t, font=fnt) <= max_w: cur = t
        else:
            if cur: lines.append(cur)
            cur = w_
    if cur: lines.append(cur)
    return lines

def draw_par(draw, text, fnt, x, y, max_w, fill, lh=1.28):
    step = int(fnt.size * lh)
    for ln in wrap(draw, text, fnt, max_w):
        draw.text((x, y), ln, font=fnt, fill=fill); y += step
    return y

def draw_hl(draw, parts, fnt, x, y, max_w, lh=1.06):
    """Заголовок с цветной подсветкой слов."""
    flat = [(w_, c) for txt, c in parts for w_ in txt.split()]
    step = int(fnt.size * lh); space = draw.textlength(" ", font=fnt)
    line, line_w = [], 0
    def flush(line, y):
        cx = x
        for t, c in line:
            draw.text((cx, y), t, font=fnt, fill=c)
            cx += draw.textlength(t, font=fnt) + space
    for w_, col in flat:
        ww = draw.textlength(w_, font=fnt)
        add = ww if not line else ww + space
        if line_w + add > max_w and line:
            flush(line, y); y += step; line, line_w = [(w_, col)], ww
        else:
            line.append((w_, col)); line_w += add
    if line: flush(line, y); y += step
    return y

_scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))
def h_hl(parts, fnt, max_w, lh=1.06):
    flat = [(w_, c) for txt, c in parts for w_ in txt.split()]
    space = _scratch.textlength(" ", font=fnt); rows, line_w = 1, 0
    for w_, _ in flat:
        ww = _scratch.textlength(w_, font=fnt)
        add = ww if line_w == 0 else ww + space
        if line_w + add > max_w and line_w > 0: rows += 1; line_w = ww
        else: line_w += add
    return rows * int(fnt.size*lh)
def h_par(text, fnt, max_w, lh=1.28):
    return len(wrap(_scratch, text, fnt, max_w)) * int(fnt.size*lh)

# ---------- глубина ----------
def orb(img, cx, cy, r, color, alpha=255, blur=90):
    """Размытое пятно - даёт глубину, вместо плоской заливки."""
    lay = Image.new("RGBA", (W, H), (0,0,0,0))
    ImageDraw.Draw(lay).ellipse([cx-r, cy-r, cx+r, cy+r], fill=color+(alpha,))
    lay = lay.filter(ImageFilter.GaussianBlur(blur))
    img.alpha_composite(lay)

def shadow(img, box, radius, blur=28, alpha=42, dy=14, color=(23,44,84)):
    """Мягкая тень под карточкой."""
    lay = Image.new("RGBA", (W, H), (0,0,0,0))
    x0,y0,x1,y1 = box
    ImageDraw.Draw(lay).rounded_rectangle([x0, y0+dy, x1, y1+dy], radius=radius, fill=color+(alpha,))
    img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(blur)))

def card(img, box, radius, fill, outline=None, sh=True, **kw):
    if sh: shadow(img, box, radius, **kw)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=radius, fill=fill+(255,) if len(fill)==3 else fill,
                        outline=outline+(255,) if outline else None, width=2 if outline else 0)

def _photo_path():
    for n in ("photo.jpg", "photo.jpeg", "photo.png", "avatar.jpg", "avatar.png"):
        p = os.path.join(HERE, n)
        if os.path.exists(p): return p
    return None

def has_photo(): return _photo_path() is not None

def photo_slot(img, box, radius, shadow_on=True, top_bias=0.0):
    """Портрет в скруглённой карточке. top_bias=0 - кадрируем от верха (лицо не срезается)."""
    p = _photo_path()
    if not p: return False
    x0,y0,x1,y1 = box; bw, bh = int(x1-x0), int(y1-y0)
    im = Image.open(p).convert("RGB")
    s = max(bw/im.width, bh/im.height)
    im = im.resize((max(int(im.width*s)+1, bw), max(int(im.height*s)+1, bh)), Image.LANCZOS)
    ox = (im.width-bw)//2
    oy = int((im.height-bh)*top_bias)
    im = im.crop((ox, oy, ox+bw, oy+bh))
    if shadow_on: shadow(img, box, radius, blur=34, alpha=95, dy=18, color=(4,20,54))
    m = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(m).rounded_rectangle([0,0,bw,bh], radius=radius, fill=255)
    img.paste(im, (int(x0),int(y0)), m)
    return True

def photo_bleed_right(img, width=470, feather=170, top_bias=0.0, x_bias=0.5):
    """Портрет в правую колонку в упор к краям, с растушёвкой в белое."""
    p = _photo_path()
    if not p: return False
    im = Image.open(p).convert("RGB")
    s = max(width/im.width, H/im.height)
    im = im.resize((max(int(im.width*s)+1, width), max(int(im.height*s)+1, H)), Image.LANCZOS)
    ox = int((im.width-width)*x_bias)   # x_bias<0.5 - лицо уходит правее, из-под растушёвки
    oy = int((im.height-H)*top_bias)
    im = im.crop((ox, oy, ox+width, oy+H))
    m = Image.new("L", (width, H), 255)
    md = ImageDraw.Draw(m)
    for i in range(feather):
        md.line([(i,0),(i,H)], fill=int(255*i/feather))
    img.paste(im, (W-width, 0), m)
    return True

# ---------- элементы ----------
FOOT_H = 76                  # высота подписи внизу
FOOT_Y = H - PAD - FOOT_H    # верх подписи

def footer(img, i, total, dark, meta=True):
    """Подпись внизу: логин слева, прогресс справа."""
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([PAD, FOOT_Y+14, PAD+50, FOOT_Y+19], radius=3,
                        fill=(WHITE if dark else BLUE))
    d.text((PAD, FOOT_Y + 30), NICK, font=font(BOLD, 27),
           fill=(WHITE+(240,)) if dark else INK+(255,))
    if not meta: return
    f_ = font(BOLD, 22); t = f"{i}/{total}"
    tw = d.textlength(t, font=f_)
    bw = 132; bx = W - PAD - bw; by = FOOT_Y + 46
    d.rounded_rectangle([bx, by, bx+bw, by+6], radius=3,
                        fill=(255,255,255,70) if dark else LINE+(255,))
    d.rounded_rectangle([bx, by, bx+bw*i/total, by+6], radius=3, fill=(WHITE if dark else BLUE))
    d.text((W-PAD-tw, FOOT_Y + 10), t, font=f_,
           fill=(255,255,255,220) if dark else GRAY_LIGHT+(255,))

def pill(img, text, x, y, dark):
    d = ImageDraw.Draw(img)
    f_ = font(HEAVY, 21)
    tw = d.textlength(text.upper(), font=f_)
    w_, h_ = tw + 48, 54
    d.rounded_rectangle([x, y, x+w_, y+h_], radius=27,
                        fill=(255,255,255,235) if dark else BLUE_SOFT+(255,))
    d.text((x+24, y+16), text.upper(), font=f_, fill=BLUE_DARK)
    return y + h_

def check(img, x, y, s, dark=False):
    d = ImageDraw.Draw(img)
    if not dark:
        shadow(img, [x, y, x+s, y+s], 13, blur=12, alpha=60, dy=5, color=(47,128,237))
        d = ImageDraw.Draw(img)
    d.rounded_rectangle([x, y, x+s, y+s], radius=13, fill=(WHITE if dark else BLUE)+(255,))
    c = BLUE_DARK if dark else WHITE
    p = s*0.27
    d.line([(x+p, y+s*0.52), (x+s*0.43, y+s-p*0.95), (x+s-p*0.8, y+p*0.95)],
           fill=c+(255,), width=max(3, s//9), joint="curve")

def numbox(img, x, y, s, n):
    shadow(img, [x, y, x+s, y+s], 13, blur=12, alpha=55, dy=5, color=(47,128,237))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x, y, x+s, y+s], radius=13, fill=BLUE+(255,))
    f_ = font(HEAVY, int(s*0.5)); t = str(n)
    tw = d.textlength(t, font=f_); bb = f_.getbbox(t)
    d.text((x+(s-tw)/2, y+(s-(bb[3]-bb[1]))/2 - bb[1]), t, font=f_, fill=WHITE+(255,))

def quote_h(text):
    f_ = font(BOLD, 33)
    return int(f_.size*1.34)*len(wrap(_scratch, text, f_, W-PAD*2-118)) + 84 + FOOT_H + 34

def quote_box(img, text, dark, bottom=None):
    """Плашка-афоризм. То, что скринят и цитируют."""
    if bottom is None: bottom = PAD + FOOT_H + 34
    f_ = font(BOLD, 33)
    lines = wrap(_scratch, text, f_, W-PAD*2-118)
    step = int(f_.size*1.34); bh = step*len(lines) + 84
    y0 = H - bottom - bh
    box = [PAD, y0, W-PAD, y0+bh]
    if dark:
        lay = Image.new("RGBA", (W, H), (0,0,0,0))
        ImageDraw.Draw(lay).rounded_rectangle(box, radius=28, fill=(255,255,255,44))
        img.alpha_composite(lay)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(box, radius=28, outline=(255,255,255,70), width=2)
        qc, tc = (255,255,255,110), WHITE+(255,)
    else:
        card(img, box, 28, WHITE, blur=26, alpha=34, dy=12)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([PAD, y0, PAD+8, y0+bh], radius=4, fill=BLUE+(255,))
        qc, tc = BLUE_SOFT+(255,), INK+(255,)
    d = ImageDraw.Draw(img)
    fq = font(BLACK_, 96)
    d.text((PAD+34, y0+6), "\u201C", font=fq, fill=qc)
    yy = y0+42
    for ln in lines:
        d.text((PAD+72, yy), ln, font=f_, fill=tc); yy += step
    # закрывающая - пара к открывающей, иначе цитата висит незакрытой
    cq = "\u201D"
    cw = d.textlength(cq, font=fq)
    d.text((W-PAD-34-cw, y0+bh-98), cq, font=fq, fill=qc)
    return y0

TOP = 108
GAP = 58

def bg_white(img):
    # чистый круг в углу. Без блюра - размытие на белом даёт грязно-серое пятно
    ImageDraw.Draw(img).ellipse([W-300, -300, W+300, 300], fill=BLUE_TINT+(255,))

def bg_blue(img):
    d = ImageDraw.Draw(img)
    for i in range(H):
        t = i/(H-1)
        d.line([(0,i),(W,i)], fill=(int(BLUE[0]+(BLUE_NIGHT[0]-BLUE[0])*t),
                                    int(BLUE[1]+(BLUE_NIGHT[1]-BLUE[1])*t),
                                    int(BLUE[2]+(BLUE_NIGHT[2]-BLUE[2])*t), 255))
    orb(img, 60, 90, 340, (120,190,255), 90, 130)
    orb(img, W-30, H-140, 300, (30,80,190), 130, 130)

# ---------- слайды ----------
def slide_cover(s, i, total):
    img = Image.new("RGBA", (W, H), WHITE+(255,))
    bg_white(img)
    f_t, f_l = font(BLACK_, 104), font(MED, 35)
    mw_t, mw_l = W-PAD*2-30, W-PAD*2-60
    has_q = bool(s.get("quote"))
    qtop = (H - PAD - quote_h(s["quote"])) if has_q else (FOOT_Y - 34)
    lead_text = s.get("lead", "")
    ch = h_hl(s["title"], f_t, mw_t, 1.02) + (42 + h_par(lead_text, f_l, mw_l, 1.4) if lead_text else 0)
    y = TOP + max(0, (qtop - GAP - TOP - ch)//2)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([PAD, y-34, PAD+86, y-27], radius=4, fill=BLUE+(255,))
    y = draw_hl(d, s["title"], f_t, PAD, y, mw_t, lh=1.02) + 42
    if lead_text:
        draw_par(d, lead_text, f_l, PAD, y, mw_l, GRAY+(255,), lh=1.4)
    if has_q:
        quote_box(img, s["quote"], False)
    footer(img, i, total, False)
    return img.convert("RGB")

def slide_break(s, i, total):
    img = Image.new("RGBA", (W, H), BLUE+(255,))
    bg_blue(img)
    f_t, f_l = font(BLACK_, 72), font(MED, 33)
    mw = W-PAD*2-10
    has_q = bool(s.get("quote"))
    qtop = (H - PAD - quote_h(s["quote"])) if has_q else (FOOT_Y - 34)
    head_h = 200 if s.get("bignum") else (54+44 if s.get("tag") else 0)
    lead_text = s.get("lead", "")
    ch = head_h + h_hl(s["title"], f_t, mw, 1.1) + (32 + h_par(lead_text, f_l, mw-20, 1.42) if lead_text else 0)
    y = TOP + max(0, (qtop - GAP - TOP - ch)//2)
    d = ImageDraw.Draw(img)
    if s.get("bignum"):
        d.text((PAD, y-30), s["bignum"], font=font(BLACK_, 184), fill=WHITE+(255,)); y += 200
    elif s.get("tag"):
        y = pill(img, s["tag"], PAD, y, True) + 44
    d = ImageDraw.Draw(img)
    y = draw_hl(d, s["title"], f_t, PAD, y, mw, lh=1.1) + 32
    if lead_text:
        draw_par(d, lead_text, f_l, PAD, y, mw-20, (214,230,252,255), lh=1.42)
    if has_q:
        quote_box(img, s["quote"], True)
    footer(img, i, total, True)
    return img.convert("RGB")

def slide_list(s, i, total):
    img = Image.new("RGBA", (W, H), WHITE+(255,))
    bg_white(img)
    f_t, f_lb, f_i = font(BLACK_, 68), font(BOLD, 31), font(SEMI, 34)
    mw_t = W-PAD*2-30; S = 48; mw_i = W-PAD*2-S-34
    has_q = bool(s.get("quote"))
    qtop = (H - PAD - quote_h(s["quote"])) if has_q else (FOOT_Y - 34)
    ch = (54+34 if s.get("tag") else 0) + h_hl(s["title"], f_t, mw_t, 1.08) + 40 + (64 if s.get("label") else 0)
    items = s.get("items", [])
    items_h = [max(h_par(it, f_i, mw_i, 1.3), S) for it in items]
    free = qtop - GAP - TOP - ch - sum(items_h)
    gap = min(64, max(20, free // max(len(items), 1)))
    ch += sum(items_h) + gap*max(len(items)-1, 0)
    y = TOP + max(0, (qtop - GAP - TOP - ch)//2)
    if s.get("tag"): y = pill(img, s["tag"], PAD, y, False) + 34
    d = ImageDraw.Draw(img)
    y = draw_hl(d, s["title"], f_t, PAD, y, mw_t, lh=1.08) + 40
    if s.get("label"):
        d.text((PAD, y), s["label"], font=f_lb, fill=INK+(255,)); y += 64
    for n, it in enumerate(items, 1):
        if s.get("numbered"): numbox(img, PAD, y+3, S, n)
        else: check(img, PAD, y+3, S)
        d = ImageDraw.Draw(img)
        draw_par(d, it, f_i, PAD+S+26, y, mw_i, INK+(255,), lh=1.3)
        if n < len(items):
            yl = y + items_h[n-1] + gap//2 - 2
            d.line([(PAD+S+26, yl), (W-PAD, yl)], fill=LINE+(255,), width=2)
        y += items_h[n-1] + gap
    if has_q:
        quote_box(img, s["quote"], False)
    footer(img, i, total, False)
    return img.convert("RGB")

def slide_cta(s, i, total):
    img = Image.new("RGBA", (W, H), WHITE+(255,))
    ph = photo_bleed_right(img, width=470, feather=104, top_bias=0.06, x_bias=0.30) if has_photo() else False
    if not ph: bg_white(img)
    s_word = s.get("word", "СИСТЕМА")

    cx1 = (W-470-26) if ph else (W-PAD)
    PADC = 38
    inner = cx1 - PAD - PADC*2
    f1 = font(SEMI, 25 if ph else 28)
    f3 = font(SEMI, 24 if ph else 27)
    fs = 86
    while fs > 34:
        f2 = font(BLACK_, fs)
        if _scratch.textlength(s_word, font=f2) <= inner: break
        fs -= 2
    h1 = int(f1.size*1.3); hw = int(fs*1.12); h3 = int(f3.size*1.34)
    bh = PADC + h1 + 8 + hw + 14 + 6 + 16 + h3*2 + PADC
    y0 = H - PAD - FOOT_H - 30 - bh

    lead_text = s.get("lead", "")
    f_t = font(BLACK_, 66 if ph else 72)
    f_l = font(MED, 31 if ph else 33)
    mw = (W-470-PAD-30) if ph else (W-PAD*2-10)
    ch = (54+40 if s.get("tag") else 0) + h_hl(s["title"], f_t, mw, 1.08) + 28 + (h_par(lead_text, f_l, mw, 1.4) if lead_text else 0)
    y = TOP + max(0, (y0 - GAP - TOP - ch)//2)
    if s.get("tag"):
        y = pill(img, s["tag"], PAD, y, False) + 40
    d = ImageDraw.Draw(img)
    y = draw_hl(d, s["title"], f_t, PAD, y, mw, lh=1.08) + 28
    if lead_text:
        draw_par(d, lead_text, f_l, PAD, y, mw, GRAY+(255,), lh=1.4)

    card(img, [PAD, y0, cx1, y0+bh], 30, WHITE, blur=40, alpha=60, dy=16, color=(23,44,84))
    d = ImageDraw.Draw(img)
    cc = (PAD + cx1) / 2
    yy = y0 + PADC
    t1 = "Напишите в комментариях слово"
    tw = d.textlength(t1, font=f1); d.text((cc-tw/2, yy), t1, font=f1, fill=GRAY+(255,))
    yy += h1 + 8
    tw = d.textlength(s_word, font=f2)
    d.text((cc-tw/2, yy), s_word, font=f2, fill=BLUE+(255,))
    yy += hw + 14
    d.rounded_rectangle([cc-tw/2, yy, cc+tw/2, yy+6], radius=3, fill=BLUE_SOFT+(255,))
    yy += 6 + 16
    for t in ("и я пришлю ссылку", "в личные сообщения"):
        tw = d.textlength(t, font=f3); d.text((cc-tw/2, yy), t, font=f3, fill=GRAY+(255,))
        yy += h3
    footer(img, i, total, False, meta=not ph)
    return img.convert("RGB")


def normalize_slide(sl):
    sl = dict(sl)
    t = sl.get("title")
    if isinstance(t, str):
        sl["title"] = [(t, WHITE if sl.get("type") == "break" else INK)]
    elif isinstance(t, list):
        normalized_t = []
        for item in t:
            if isinstance(item, str):
                normalized_t.append((item, WHITE if sl.get("type") == "break" else INK))
            elif isinstance(item, (list, tuple)):
                txt = item[0]
                col = item[1] if len(item) > 1 else "INK"
                if isinstance(col, (list, tuple)):
                    color_val = tuple(col)
                elif col in ("BLUE", "blue"):
                    color_val = BLUE
                elif col in ("WHITE", "white"):
                    color_val = WHITE
                else:
                    color_val = INK
                normalized_t.append((txt, color_val))
        sl["title"] = normalized_t
    return sl

RENDER = {"cover": slide_cover, "break": slide_break, "list": slide_list, "cta": slide_cta}

# ================== СБОРКА ==================
import sys, json
from decks import build

DECKS = build(INK, BLUE, WHITE)

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--json":
        json_file = sys.argv[2]
        out_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "karusel_custom")
        os.makedirs(out_dir, exist_ok=True)
        with open(json_file, "r", encoding="utf-8") as f:
            slides = json.load(f)
        total = len(slides)
        for i, sl in enumerate(slides, 1):
            sl = normalize_slide(sl)
            stype = sl.get("type", "list")
            if stype not in RENDER:
                stype = "list"
            RENDER[stype](sl, i, total).save(os.path.join(out_dir, f"{i:02d}.png"), "PNG")
        print(f"custom: {total} карточек -> {out_dir}")
    else:
        only = sys.argv[1] if len(sys.argv) > 1 else None
        names = [only] if only else list(DECKS)
        for name in names:
            slides = DECKS.get(name, [])
            if not slides:
                continue
            out = os.path.join(HERE, "karusel_" + name)
            os.makedirs(out, exist_ok=True)
            total = len(slides)
            for i, sl in enumerate(slides, 1):
                sl = normalize_slide(sl)
                RENDER[sl["type"]](sl, i, total).save(os.path.join(out, f"{i:02d}.png"), "PNG")
            print(f"{name}: {total} карточек -> karusel_{name}/")

