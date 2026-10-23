"""Minimal Ren'Py .rpyc reader: header parsing + stub unpickling + AST walking."""
import io
import pickle
import struct
import zlib

SAFE = {"collections", "builtins", "copyreg", "copy"}

_classes = {}


class Stub:
    def __new__(cls, *a, **k):
        return object.__new__(cls)

    def __init__(self, *a, **k):
        self._args = a

    def __setstate__(self, state):
        if isinstance(state, tuple) and len(state) == 2:
            for part in state:
                if isinstance(part, dict):
                    self.__dict__.update(part)
                elif part:
                    self.__dict__["_state"] = part
        elif isinstance(state, dict):
            self.__dict__.update(state)
        else:
            self.__dict__["_state"] = state

    def __repr__(self):
        return "<%s>" % type(self).__name__


class PyExprStr(str):
    """Stub for renpy.astsupport.PyExpr, which subclasses str."""

    def __new__(cls, s="", *args, **kwargs):
        return str.__new__(cls, s if isinstance(s, str) else str(s))

    def __init__(self, s="", *args, **kwargs):
        self._args = (s,) + args

    def __setstate__(self, state):
        pass


def _base_for(name):
    n = name.lower()
    if n == "pyexpr":
        return PyExprStr
    if n.endswith("dict"):
        return dict
    if n.endswith("list"):
        return list
    if n.endswith("set"):
        return set
    return Stub


def _stubcls(mod, name):
    key = (mod, name)
    if key not in _classes:
        base = _base_for(name)
        if base is PyExprStr:
            _classes[key] = PyExprStr
        else:
            _classes[key] = type(name, (base,), {"_mod": mod, "_name": name})
    return _classes[key]


class _Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module in SAFE or module.startswith("collections"):
            return super().find_class(module, name)
        return _stubcls(module, name)


def read_payload(path):
    """Return the decompressed slot-1 pickle bytes of an .rpyc file."""
    data = open(path, "rb").read()
    hdr = b"RENPY RPC2"
    if not data.startswith(hdr):
        return zlib.decompress(data)
    pos = len(hdr)
    slots = {}
    while True:
        slot, start, length = struct.unpack("III", data[pos:pos + 12])
        if slot == 0:
            break
        slots[slot] = (start, length)
        pos += 12
    start, length = slots[1]
    return zlib.decompress(data[start:start + length])


def load(path):
    """Load an .rpyc file, returning (metadata, statements)."""
    return _Unpickler(io.BytesIO(read_payload(path))).load()


def walk(obj, seen=None):
    """Yield every Stub object reachable from obj (cycles guarded)."""
    if seen is None:
        seen = set()
    if id(obj) in seen:
        return
    seen.add(id(obj))
    if isinstance(obj, dict):
        for v in obj.values():
            yield from walk(v, seen)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from walk(v, seen)
    else:
        if isinstance(obj, Stub):
            yield obj
        for v in getattr(obj, "__dict__", {}).values():
            yield from walk(v, seen)


def text_of(value):
    """Turn a Say.what / PyExpr into plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    s = getattr(value, "s", None)
    if isinstance(s, str):
        return s
    return str(value)
