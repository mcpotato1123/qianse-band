"""Validate the compiled story and its asset references.

Checks: chunk table integrity, jump/menu targets in range, chapter starts on a
real instruction, every referenced background / CG / sprite exists, and how much
of the story is reachable from the chapter entries.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORY = os.path.join(ROOT, 'src', 'common', 'story')
IMG = os.path.join(ROOT, 'src', 'common', 'img')
US = '\x1f'


def load():
    idx = json.load(open(os.path.join(STORY, 'index.txt'), encoding='utf-8'))
    ops = []
    for c in idx['chunks']:
        path = os.path.join(STORY, c['file'].split('/')[-1])
        ops.extend(line.split('\t') for line in open(path, encoding='utf-8').read().splitlines() if line)
        if len(ops) - c['start'] != c['count']:
            print('!! chunk count mismatch', c['file'], c['count'], len(ops) - c['start'])
    return idx, ops


def main():
    idx, ops = load()
    print('chapters %d  chunks %d  ops %d' % (len(idx['chapters']), len(idx['chunks']), len(ops)))
    if len(ops) != idx['total']:
        print('!! total mismatch: %d vs %d' % (len(ops), idx['total']))

    bad = []
    for i, op in enumerate(ops):
        k = op[0]
        if k == 'j' and not 0 <= int(op[1]) < len(ops):
            bad.append((i, 'j', op[1]))
        elif k == 'q' and not 0 <= int(op[3]) < len(ops):
            bad.append((i, 'q', op[3]))
        elif k == 'm':
            parts = op[1].split(US)
            if len(parts) % 2:
                bad.append((i, 'menu arity', len(parts)))
            for t in parts[1::2]:
                if not 0 <= int(t) < len(ops):
                    bad.append((i, 'menu', t))
    print('bad refs', len(bad))
    for b in bad[:8]:
        print('   ', b)

    bgs = set(f[:-4] for f in os.listdir(os.path.join(IMG, 'b')))
    cgs = set(f[:-4] for f in os.listdir(os.path.join(IMG, 'w')))
    chars = set(os.listdir(os.path.join(IMG, 's')))
    missing = {'b': set(), 'g': set(), 'p': set()}
    for op in ops:
        if op[0] == 'b' and op[1] not in bgs:
            missing['b'].add(op[1])
        elif op[0] == 'g' and op[1] not in cgs:
            missing['g'].add(op[1])
        elif op[0] == 'p' and op[1] not in chars:
            missing['p'].add(op[1])
    print('missing assets', {k: sorted(v) for k, v in missing.items()})

    for c in idx['chapters']:
        if not (0 <= c['start'] < len(ops)):
            print('!! chapter start out of range', c)

    # reachability from every chapter entry
    seen = set()
    stack = [c['start'] for c in idx['chapters']]
    while stack:
        pc = stack.pop()
        while 0 <= pc < len(ops) and pc not in seen:
            seen.add(pc)
            k = ops[pc][0]
            if k == 'j':
                pc = int(ops[pc][1])
                continue
            if k == 'q':
                stack.append(int(ops[pc][3]))
            if k == 'm':
                for t in ops[pc][1].split(US)[1::2]:
                    stack.append(int(t))
            if k == 'e':
                break
            pc += 1
    says = sum(1 for i in seen if ops[i][0] == 's')
    chars_total = sum(len(ops[i][2]) for i in seen if ops[i][0] == 's')
    print('reachable %.1f%%  dialogue %d lines / %d chars' %
          (100.0 * len(seen) / len(ops), says, chars_total))

    size = sum(os.path.getsize(os.path.join(STORY, c['file'].split('/')[-1])) for c in idx['chunks'])
    size += os.path.getsize(os.path.join(STORY, 'index.txt'))
    imgs = 0
    for dp, _, fs in os.walk(IMG):
        for f in fs:
            imgs += os.path.getsize(os.path.join(dp, f))
    print('story %.1f KB   images %.2f MB   package %.2f MB'
          % (size / 1024, imgs / 1048576, (size + imgs) / 1048576))

    ok = not bad and not any(missing.values()) and len(ops) == idx['total']
    print('RESULT', 'OK' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
