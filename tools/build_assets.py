"""Turn the unpacked QianSe art into band-sized assets.

    b/<bg>.png          672x480 (2x screen, panned at runtime)
    s/<tag>/base_<cloth>.png   210x420 full body (outfit baked)
    s/<tag>/face_<cloth>_<expr>.png  210x420 overlay (face only)
    w/<cg>.png          672x480 CG
    t/<cg>.png          96x54 thumbnail
    ui/                 title art, logo, bars, board, locked
"""
import glob
import json
import os
import shutil

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.environ.get("QIANSE_SRC") or os.path.join(os.path.dirname(ROOT), "unpacked")
IMG = os.path.join(ROOT, "src", "common", "img")
W, H = 336, 480
BG_W = 544
SW, SH = 210, 420


def cover(im, w, h):
    sw, sh = im.size
    scale = max(w / sw, h / sh)
    im = im.resize((max(1, round(sw * scale)), max(1, round(sh * scale))), Image.LANCZOS)
    sw, sh = im.size
    return im.crop(((sw - w) // 2, (sh - h) // 2, (sw - w) // 2 + w, (sh - h) // 2 + h))


def load_rgba(p):
    with Image.open(p) as im:
        return im.convert("RGBA")


def find_image(folder, names):
    for n in names:
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = os.path.join(folder, n + ext)
            if os.path.exists(p):
                return p
    for n in names:
        hits = glob.glob(os.path.join(folder, n + ".*"))
        if hits:
            return hits[0]
    return None


def save_bg(im, path, colors=64):
    im = cover(im.convert("RGB"), BG_W, H)
    im.quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG).save(path, optimize=True)


# ---------------------------------------------------------------- sprites
def char_window(paths):
    union = None
    for p in paths:
        box = load_rgba(p).getbbox()
        if not box:
            continue
        union = box if union is None else (min(union[0], box[0]), min(union[1], box[1]),
                                           max(union[2], box[2]), max(union[3], box[3]))
    if union is None:
        union = (0, 0, 740, 1050)
    pad_x = int((union[2] - union[0]) * 0.04)
    pad_y = int((union[3] - union[1]) * 0.02)
    x0, y0 = max(0, union[0] - pad_x), max(0, union[1] - pad_y)
    x1, y1 = union[2] + pad_x, union[3] + pad_y
    cw, ch = x1 - x0, y1 - y0
    if cw / ch < 0.5:
        want = int(ch * 0.5)
        cx = (x0 + x1) // 2
        x0, x1 = cx - want // 2, cx + want // 2
    else:
        want = int(cw / 0.5)
        y0, y1 = y0, y0 + want
    return x0, y0, x1, y1


def build_sprites(used):
    os.makedirs(os.path.join(IMG, "s"), exist_ok=True)
    meta = {}
    for tag, pairs in used.items():
        folder = os.path.join(SRC, "images", tag)
        if not os.path.isdir(folder):
            continue
        cloths = sorted({c for _, c in pairs})
        mains = sorted({m for m, _ in pairs})
        all_paths = [os.path.join(folder, m + ".png") for m in mains if os.path.exists(os.path.join(folder, m + ".png"))]
        all_paths += [os.path.join(folder, c + ".png") for c in cloths if os.path.exists(os.path.join(folder, c + ".png"))]
        win = char_window(all_paths)
        out_dir = os.path.join(IMG, "s", tag)
        os.makedirs(out_dir, exist_ok=True)
        mouth = None
        for f in sorted(os.listdir(folder)):
            if f.startswith("m") and f.endswith(".png") and ("mf1" in f or "smf1" in f or "m1" in f):
                mouth = load_rgba(os.path.join(folder, f))
                break

        ww, wh = win[2] - win[0], win[3] - win[1]
        scale = min(SW / ww, SH / wh)
        dw, dh = max(1, round(ww * scale)), max(1, round(wh * scale))
        ox, oy = (SW - dw) // 2, (SH - dh) // 2

        def to_canvas(im):
            return im.crop(win).resize((dw, dh), Image.LANCZOS)

        groups = {}
        for m, c in pairs:
            groups.setdefault(c, set()).add(m)

        for cloth, group_mains in groups.items():
            cloth_img = None
            cp = os.path.join(folder, cloth + ".png")
            if os.path.exists(cp):
                cloth_img = load_rgba(cp)
            base_main = sorted(group_mains)[0]
            base = Image.new("RGBA", (740, 1050), (0, 0, 0, 0))
            mp = os.path.join(folder, base_main + ".png")
            bimg = None
            if os.path.exists(mp):
                bimg = load_rgba(mp)
                base.alpha_composite(bimg)
            if cloth_img is not None:
                base.alpha_composite(cloth_img)
            if mouth is not None:
                base.alpha_composite(mouth)
            canvas = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
            canvas.alpha_composite(to_canvas(base), (ox, oy))
            canvas.save(os.path.join(out_dir, "base_%s.png" % cloth), optimize=True)

            union = None
            for m in group_mains:
                p = os.path.join(folder, m + ".png")
                if not os.path.exists(p):
                    continue
                im = load_rgba(p)
                if bimg is None:
                    bimg = im
                d = ImageChops.difference(bimg, im).convert("L").point(lambda v: 255 if v > 10 else 0)
                box = d.getbbox()
                if not box:
                    continue
                union = box if union is None else (min(union[0], box[0]), min(union[1], box[1]),
                                                   max(union[2], box[2]), max(union[3], box[3]))
            if union is None:
                union = (win[0], win[1], win[2], win[1] + 120)
            pad = 6
            fb = (max(0, union[0] - pad), max(0, union[1] - pad),
                  min(740, union[2] + pad), min(1050, union[3] + pad))
            for m in group_mains:
                p = os.path.join(folder, m + ".png")
                if not os.path.exists(p):
                    continue
                comp = Image.new("RGBA", (740, 1050), (0, 0, 0, 0))
                comp.alpha_composite(load_rgba(p))
                if mouth is not None:
                    comp.alpha_composite(mouth)
                face = comp.crop(fb)
                fx = ox + round((fb[0] - win[0]) * scale)
                fy = oy + round((fb[1] - win[1]) * scale)
                fw = max(1, round((fb[2] - fb[0]) * scale))
                fh = max(1, round((fb[3] - fb[1]) * scale))
                fcanvas = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
                fcanvas.alpha_composite(face.resize((fw, fh), Image.LANCZOS), (fx, fy))
                fcanvas.save(os.path.join(out_dir, "face_%s_%s.png" % (cloth, m)), optimize=True)
        meta[tag] = {"win": list(win), "scale": scale, "canvas": [SW, SH]}
        print(tag, "outfits", len(groups), "files", len(os.listdir(out_dir)))
    with open(os.path.join(IMG, "s", "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False)
    return meta


# ---------------------------------------------------------------- backgrounds
def build_bgs(ids):
    out = os.path.join(IMG, "b")
    os.makedirs(out, exist_ok=True)
    folder = os.path.join(SRC, "images", "bg")
    missing = []
    for ident in ids:
        if ident in ("black", "white"):
            Image.new("RGB", (BG_W, H), (0, 0, 0) if ident == "black" else (255, 255, 255)).save(
                os.path.join(out, ident + ".png"), optimize=True)
            continue
        p = find_image(folder, ["bg " + ident])
        if not p:
            p = find_image(folder, [ident])
        if not p:
            missing.append(ident)
            Image.new("RGB", (BG_W, H), (0, 0, 0)).save(os.path.join(out, ident + ".png"), optimize=True)
            continue
        save_bg(load_rgba(p), os.path.join(out, ident + ".png"))
    print("bg missing", missing)


# ---------------------------------------------------------------- cg / title
def build_cgs(ids):
    out = os.path.join(IMG, "w")
    th = os.path.join(IMG, "t")
    os.makedirs(out, exist_ok=True)
    os.makedirs(th, exist_ok=True)
    folder = os.path.join(SRC, "images", "cg")
    missing = []
    for ident in ids:
        p = find_image(folder, ["cg " + ident, ident])
        if not p:
            missing.append(ident)
            continue
        wide = load_rgba(p).convert("RGB")
        wide = cover(wide, 576, H)
        wide.quantize(colors=96, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG).save(
            os.path.join(out, ident + ".png"), optimize=True)
        wide.resize((96, 54), Image.LANCZOS).quantize(colors=96).save(
            os.path.join(th, ident + ".png"), optimize=True)
    print("cg missing", missing)


def build_titles(ids):
    out = os.path.join(IMG, "w")
    folder = os.path.join(SRC, "images", "title")
    for ident in ids:
        p = find_image(folder, ["title " + ident])
        if not p:
            continue
        wide = load_rgba(p).convert("RGB")
        wide = cover(wide, 576, H)
        wide.quantize(colors=96, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG).save(
            os.path.join(out, "title_" + ident + ".png"), optimize=True)
        wide.resize((96, 54), Image.LANCZOS).quantize(colors=96).save(
            os.path.join(IMG, "t", "title_" + ident + ".png"), optimize=True)


# ---------------------------------------------------------------- icons / ui
def build_ui():
    ui = os.path.join(IMG, "ui")
    os.makedirs(ui, exist_ok=True)
    # 主界面：原作标题画面 gui/main/main.png，等比缩放到 336×189，整张显示不裁切
    cover_art = load_rgba(os.path.join(SRC, "gui", "main", "main.png")).convert("RGB")
    art = cover_art.resize((W, round(W * cover_art.size[1] / cover_art.size[0])), Image.LANCZOS)
    art.quantize(colors=160, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG).save(
        os.path.join(ui, "title_bg.png"), optimize=True)

    # 图标：直接使用原作窗口图标 gui/window_icon.png（仅缩放 + 圆角）
    icon_src = load_rgba(os.path.join(SRC, "gui", "window_icon.png"))
    ic = icon_src.resize((192, 192), Image.LANCZOS)
    mask = Image.new("L", (192, 192), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 191, 191), radius=44, fill=255)
    ic.putalpha(mask)
    ic.save(os.path.join(ROOT, "src", "common", "icon.png"), optimize=True)

    # 标题：直接使用原作的 logotype gui/main/orangia.png
    logo = load_rgba(os.path.join(SRC, "gui", "main", "orangia.png"))
    lw = 140
    logo = logo.resize((lw, max(1, round(logo.height * lw / logo.width))), Image.LANCZOS)
    logo.save(os.path.join(ui, "logo.png"), optimize=True)

    head = Image.new("RGBA", (W, 72), (0, 0, 0, 0))
    px = head.load()
    for y in range(72):
        a = 232 if y < 52 else int(232 * (1 - (y - 52) / 20.0))
        for x in range(W):
            px[x, y] = (26, 28, 36, a)
    ImageDraw.Draw(head).line((0, 71, W, 71), fill=(255, 255, 255, 46), width=1)
    head.save(os.path.join(ui, "headbar.png"), optimize=True)

    foot = Image.new("RGBA", (W, 56), (0, 0, 0, 0))
    px = foot.load()
    for y in range(56):
        a = int(120 * (y / 55.0) ** 1.5)
        for x in range(W):
            px[x, y] = (14, 16, 22, a)
    foot.save(os.path.join(ui, "footbar.png"), optimize=True)

    board = Image.new("RGBA", (W, 180), (0, 0, 0, 0))
    bpx = board.load()
    for y in range(180):
        if y < 30:
            a = int(8 + 172 * (y / 30.0))
        else:
            a = min(232, int(180 + 52 * ((y - 30) / 40.0)))
        for x in range(W):
            bpx[x, y] = (14, 16, 24, a)
    board.save(os.path.join(ui, "board.png"), optimize=True)

    lock = Image.new("RGB", (96, 137), (32, 26, 40))
    dr = ImageDraw.Draw(lock)
    try:
        f = ImageFont.load_default(size=34)
    except TypeError:
        f = ImageFont.load_default()
    dr.text((34, 48), "?", fill=(120, 104, 128), font=f)
    lock.save(os.path.join(ui, "locked.png"), optimize=True)


def write_manifest():
    bgs = sorted(f[:-4] for f in os.listdir(os.path.join(IMG, "b")) if f.endswith(".png"))
    cgs = sorted(f[:-4] for f in os.listdir(os.path.join(IMG, "w"))
                 if f.endswith(".png") and not f.startswith("title_"))
    sprites = {}
    for tag in sorted(os.listdir(os.path.join(IMG, "s"))):
        d = os.path.join(IMG, "s", tag)
        if not os.path.isdir(d):
            continue
        sprites[tag] = sorted(f for f in os.listdir(d) if f.endswith(".png"))
    wide = {}
    for f in sorted(os.listdir(os.path.join(IMG, "w"))):
        if f.endswith(".png"):
            with Image.open(os.path.join(IMG, "w", f)) as im:
                wide[f[:-4]] = im.size[0]
    js = os.path.join(ROOT, "src", "common", "assets.js")
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("/* generated by tools/build_assets.py — do not edit */\n")
        fh.write("export const BG = %s;\n" % json.dumps(bgs, ensure_ascii=False))
        fh.write("export const CG = %s;\n" % json.dumps(cgs, ensure_ascii=False))
        fh.write("export const SPRITES = %s;\n" % json.dumps(sprites, ensure_ascii=False))
        fh.write("export const CG_WIDE = %s;\n" % json.dumps(wide, ensure_ascii=False))
        fh.write('''
export function bgPath(id) { return '/common/img/b/' + id + '.png' }
export function cgPath(id) { return '/common/img/w/' + id + '.png' }
export function cgThumb(id) { return '/common/img/t/' + id + '.png' }
export function cgWide(id) { return '/common/img/w/' + id + '.png' }
export function spritePath(tag, file) { return '/common/img/s/' + tag + '/' + file }
export function hasSprite(tag, file) {
  return !!(SPRITES[tag] && SPRITES[tag].indexOf(file) >= 0)
}
''')


def main():
    used = json.load(open(os.path.join(ROOT, "src", "common", "meta_used.json"), encoding="utf-8"))
    for sub in ("b", "s", "t", "w"):
        path = os.path.join(IMG, sub)
        if os.path.isdir(path):
            shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)
    build_bgs(used["bg"])
    build_cgs(used["cg"])
    build_titles(used["title"])
    build_sprites(used["sprites"])
    build_ui()
    write_manifest()
    total = 0
    for dp, _, fs in os.walk(IMG):
        for f in fs:
            total += os.path.getsize(os.path.join(dp, f))
    print("images %.2f MB" % (total / 1048576))


if __name__ == "__main__":
    main()
