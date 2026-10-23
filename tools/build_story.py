"""Compile the unpacked QianSe (茜色) scripts into the band instruction stream.

Output (same format as the reference engine):
    src/common/story/index.txt
    src/common/story/chunk-NNN.txt
    src/common/meta_used.json   (asset list for build_assets.py)

Ops:
    s who text        dialogue (who empty = narration)
    b bg              background
    p tag pos expr - - cloth:<cloth>   sprite (expression + outfit)
    h tag             hide sprite
    g image           full-screen CG / title card
    m t1<US>t1 ...    menu
    j index           jump
    c title           chapter card (HUD)
    e                 end
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import rpyclib

SRC = os.environ.get("QIANSE_SRC") or os.path.join(os.path.dirname(ROOT), "unpacked")
OUT = os.path.join(ROOT, "src", "common", "story")
US = "\x1f"
CHUNK = 128

CHAPTERS = [
    ("Chapter_0", "序章 · 归途"),
    ("Chapter_1", "第一章 · 分班"),
    ("Chapter_2", "第二章 · 年级大会"),
    ("Chapter_3", "第三章"),
    ("Chapter_4", "第四章"),
    ("Chapter_5", "第五章"),
    ("Chapter_6", "第六章"),
    ("Chapter_6_1", "第六章 · 后篇"),
    ("Chapter_7", "第七章"),
    ("Chapter_8", "第八章"),
    ("Chapter_9", "第九章"),
    ("Chapter_a", "第十章"),
    ("Chapter_b", "第十一章"),
    ("Chapter_c", "第十二章"),
    ("Chapter_d", "第十三章"),
    ("Chapter_e", "第十四章"),
    ("Memory_x", "回忆 · X"),
    ("bad_memory", "坏结局 · 回忆"),
    ("true_end", "真结局"),
    ("end_1", "结局 1"),
    ("end_1_1", "结局 1 · 后"),
    ("end_2", "结局 2"),
    ("extra", "番外"),
    ("dlc", "DLC"),
    ("demo2", "短篇"),
]

TAG = re.compile(r"\{[^{}]*\}")


def clean_text(s):
    if not isinstance(s, str):
        return ""
    s = s.replace("\\n", "\n")
    s = TAG.sub("", s)
    s = s.replace("[", "［").replace("]", "］")
    s = s.replace("\t", " ").replace("\r", " ").replace("\n", "\\n")
    return s.strip()


def char_names():
    names = {}
    path = os.path.join(SRC, "script.rpyc")
    if os.path.exists(path):
        meta, stmts = rpyclib.load(path)
        for o in rpyclib.walk(stmts):
            if type(o).__name__ != "Define":
                continue
            st = getattr(o.code, "_state", None)
            if not (isinstance(st, tuple) and len(st) > 1 and isinstance(st[1], str)):
                continue
            src = st[1]
            m = re.search(r'_\("([^"]*)"\)', src)
            if not m:
                m = re.search(r'Character\(\s*"([^"]*)"', src)
            if m:
                name = m.group(1).strip().rstrip("：:").strip()
                if name:
                    names[o.varname] = name
    return names


def iter_events(stmts):
    for st in stmts or []:
        yield st
        t = type(st).__name__
        block = getattr(st, "block", None)
        if isinstance(block, list) and t != "Menu":
            yield from iter_events(block)
        entries = getattr(st, "entries", None)
        if isinstance(entries, list):
            for ent in entries:
                for part in ent:
                    if isinstance(part, list):
                        yield from iter_events(part)
        if t == "Menu":
            for item in st.items:
                blk = item[2] if len(item) > 2 else None
                if isinstance(blk, list):
                    yield from iter_events(blk)


class Compiler:
    def __init__(self, names):
        self.ops = []
        self.labels = {}
        self.pending = []
        self.names = names
        self.shown = {}
        self.order = []
        self.chapters = []
        self.used_bg = set()
        self.used_cg = set()
        self.used_title = set()
        self.used_sprites = {}

    def emit(self, *fields):
        self.ops.append(list(fields))
        return len(self.ops) - 1

    def slots(self):
        live = [c for c in self.order if c in self.shown]
        if len(live) == 1:
            return {live[0]: "c"}
        if len(live) == 2:
            return {live[0]: "l", live[1]: "r"}
        out = {}
        for i, c in enumerate(live[:3]):
            out[c] = ("l", "c", "r")[i]
        return out

    def sync_sprites(self):
        slots = self.slots()
        for c in self.order:
            if c not in self.shown:
                continue
            state = self.shown[c]
            expr = state.get("main") or "base"
            cloth = state.get("cloth") or "default"
            self.emit("p", c, slots.get(c, "c"), expr, "-", "-", "cloth:" + cloth)
            self.used_sprites.setdefault(c, set()).add((expr, cloth))

    def show_char(self, tag, attrs):
        state = self.shown.setdefault(tag, {})
        if tag not in self.order:
            self.order.append(tag)
        for a in attrs:
            if a == "flush":
                continue
            for g in LAYERS.get(tag, []):
                if g.get("kind") == "group" and a in g["attrs"]:
                    state[g["name"]] = a
                    break
        self.sync_sprites()

    def scene(self, name):
        for c in list(self.shown):
            self.emit("h", c)
        self.shown.clear()
        self.order.clear()
        if name in BG_IDS:
            self.used_bg.add(name)
            self.emit("b", name)
        elif name in CG_IDS:
            self.used_cg.add(name)
            self.emit("b", "black")
            self.emit("g", name)
        else:
            self.emit("b", "black")

    def cg_show(self, name):
        if name in CG_IDS:
            self.used_cg.add(name)
            self.emit("g", name)

    def compile_file(self, key, title, stmts):
        start = len(self.ops)
        self.chapters.append({"id": key, "title": title, "start": start})
        self.emit("c", title)
        for st in iter_events(stmts):
            self.compile_node(st)

    def compile_node(self, n):
        t = type(n).__name__
        if t == "Label":
            self.labels[getattr(n, "_name", None)] = len(self.ops)
        elif t == "Say":
            who = getattr(n, "who", None)
            text = clean_text(rpyclib.text_of(getattr(n, "what", "")))
            if not text:
                return
            if who == "extend":
                for i in range(len(self.ops) - 1, -1, -1):
                    if self.ops[i][0] == "s":
                        self.ops[i][2] += text
                        break
                return
            if who in (None, "nvle", "narrator", "nvl_narrator"):
                speaker = ""
            else:
                speaker = self.names.get(who, str(who))
            self.emit("s", speaker, text)
        elif t == "Scene":
            im = getattr(n, "imspec", None)
            if im and im[0]:
                tag = im[0]
                if tag[0] in ("bg", "cg"):
                    self.scene(tag[1])
                else:
                    self.scene("black")
        elif t == "Show":
            im = getattr(n, "imspec", None)
            if not im or not im[0]:
                return
            tag = im[0]
            name = tag[0]
            if name == "title":
                tid = tag[1] if len(tag) > 1 else ""
                if tid:
                    self.used_title.add(tid)
                    self.emit("g", "title_" + tid)
            elif name == "cg":
                if len(tag) > 1:
                    self.cg_show(tag[1])
            elif name == "bg":
                if len(tag) > 1:
                    self.scene(tag[1])
            elif name in LAYERS:
                self.show_char(name, tag[1:])
        elif t == "Hide":
            im = getattr(n, "imspec", None)
            tag = im[0][0] if im and im[0] else ""
            if tag in self.shown:
                self.emit("h", tag)
                del self.shown[tag]
                self.sync_sprites()
            elif tag in ("cg", "title"):
                self.emit("h", "@fg")
        elif t == "Menu":
            self.compile_menu(n)
        elif t == "Jump":
            idx = self.emit("j", "")
            self.pending.append((idx, 1, getattr(n, "target", "")))

    def compile_menu(self, n):
        items = getattr(n, "items", None) or []
        real_types = {"Say", "Scene", "Show", "Hide", "Menu", "Jump"}
        opts = []
        caption_text = ""
        for item in items:
            caption = clean_text(item[0] if item else "")
            block = item[2] if len(item) > 2 else None
            if not block:
                if caption and not caption_text:
                    caption_text = caption      # menu caption row
                continue
            if not any(type(x).__name__ in real_types for x in block):
                continue      # bookkeeping-only branch
            if not caption or caption == "...":
                continue
            opts.append((caption, block))
        if not opts:
            return
        if caption_text:
            self.emit("s", "", caption_text)
        menu_idx = self.emit("m", "")
        spec = []
        ends = []
        for caption, block in opts:
            target = len(self.ops)
            spec.extend([caption, str(target)])
            for st in block:
                self.compile_node(st)
            j = self.emit("j", "")
            ends.append(j)
        after = len(self.ops)
        self.ops[menu_idx][1] = US.join(spec)
        for j in ends:
            self.ops[j][1] = str(after)


def load_layers():
    layers = {}
    path = os.path.join(SRC, "script.rpyc")
    meta, stmts = rpyclib.load(path)
    for o in rpyclib.walk(stmts):
        if type(o).__name__ != "RawLayeredImage":
            continue
        groups = []
        for ch in o.children:
            if type(ch).__name__ == "RawAttributeGroup":
                groups.append({"kind": "group", "name": ch.group_name,
                               "attrs": {a.name: str(a.image) for a in ch.children}})
        layers[o.name] = groups
    return layers


def scan_assets():
    bg = set()
    cg = set()
    base = os.path.join(SRC, "images")
    for f in os.listdir(os.path.join(base, "bg")):
        n = f.rsplit(".", 1)[0]
        if n.startswith("bg "):
            n = n[3:]
        bg.add(n)
    for f in os.listdir(os.path.join(base, "cg")):
        n = f.rsplit(".", 1)[0]
        if n.startswith("cg "):
            n = n[3:]
        if n.startswith("cg"):
            cg.add(n)
    return bg, cg


BG_IDS, CG_IDS = set(), set()
LAYERS = {}


def main():
    global BG_IDS, CG_IDS, LAYERS
    BG_IDS, CG_IDS = scan_assets()
    LAYERS = load_layers()
    names = char_names()
    comp = Compiler(names)

    for key, title in CHAPTERS:
        meta, stmts = rpyclib.load(os.path.join(SRC, key + ".rpyc"))
        comp.compile_file(key, title, stmts)

    comp.emit("e")

    for idx, field, label in comp.pending:
        if label not in comp.labels:
            print("warn: unresolved label", label)
            comp.ops[idx][field] = str(len(comp.ops) - 1)
        else:
            comp.ops[idx][field] = str(comp.labels[label])

    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.startswith("chunk-") or f in ("index.json", "index.txt"):
            os.remove(os.path.join(OUT, f))

    lines = ["\t".join(op) for op in comp.ops]
    chunks = []
    for start in range(0, len(lines), CHUNK):
        part = lines[start:start + CHUNK]
        fn = "chunk-%03d.txt" % (start // CHUNK)
        with open(os.path.join(OUT, fn), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(part) + "\n")
        chunks.append({"file": "/common/story/" + fn, "start": start, "count": len(part)})

    index = {"version": 1, "total": len(lines), "chunks": chunks, "chapters": comp.chapters}
    with open(os.path.join(OUT, "index.txt"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, separators=(",", ":"))

    used = {
        "bg": sorted(comp.used_bg),
        "cg": sorted(comp.used_cg),
        "title": sorted(comp.used_title),
        "sprites": {k: sorted(v) for k, v in comp.used_sprites.items()},
    }
    with open(os.path.join(ROOT, "src", "common", "meta_used.json"), "w", encoding="utf-8") as fh:
        json.dump(used, fh, ensure_ascii=False, indent=1)

    kinds = {}
    for op in comp.ops:
        kinds[op[0]] = kinds.get(op[0], 0) + 1
    print("ops", len(lines), kinds)
    print("chunks", len(chunks), "chapters", len(comp.chapters))
    print("bg", len(used["bg"]), "cg", len(used["cg"]), "title", used["title"])
    print("sprites", {k: len(v) for k, v in used["sprites"].items()})
    print("size KB", round(sum(os.path.getsize(os.path.join(OUT, c["file"].split("/")[-1]))
                               for c in chunks) / 1024, 1))


if __name__ == "__main__":
    main()
