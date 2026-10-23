// Story interpreter. Pure logic: the caller supplies readText(path, cb) so the
// same code runs inside the Vela quick-app and in the browser simulator.
//
// Stream format is produced by tools/build_story.py:
//   s \t who \t text            dialogue        (who '@' = 常夏's current alias)
//   b \t bg                     background
//   p \t tag \t pos \t eye \t brow \t mouth \t extra
//   h \t tag | @fg              hide character / CG
//   g \t cg                     full screen CG
//   m \t t1 \x1f target1 ...    choice menu
//   j \t index                  jump
//   q \t a \t b \t index        if a <= b jump
//   v \t name \t value          variable (+n or n)
//   n \t name                   alias of 常夏
//   d \t text                   date chip
//   c \t text                   chapter title card
//   e                           end of story

export const CHUNK = 128;

export function blankState() {
  return {
    pc: 0,
    bg: 'black',
    fg: '',
    chars: {},
    name: '常夏',
    date: '',
    chapterTitle: '',
    chapterId: '',
    vars: {},
  };
}

export function createReader(readText) {
  const reader = {
    index: null,
    cache: {},
    pending: {},
    order: [],
    state: blankState(),
    frame: null,

    init(done) {
      readText('/common/story/index.txt', (err, text) => {
        if (err) return done(err);
        try {
          reader.index = JSON.parse(text);
        } catch (e) {
          return done('index.json 解析失败');
        }
        done(null, reader.index);
      });
    },

    chapter(id) {
      const list = reader.index.chapters;
      for (let i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
      return list[0];
    },

    chunkOf(pc) {
      const list = reader.index.chunks;
      let lo = 0;
      let hi = list.length - 1;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (list[mid].start <= pc) lo = mid; else hi = mid - 1;
      }
      return list[lo];
    },

    loadChunk(chunk, done) {
      const hit = reader.cache[chunk.start];
      if (hit) return done(null, hit);
      if (reader.pending[chunk.start]) {
        reader.pending[chunk.start].push(done);
        return;
      }
      reader.pending[chunk.start] = [done];
      const path = chunk.file.charAt(0) === '/' ? chunk.file : '/common/story/' + chunk.file;
      readText(path, (err, text) => {
        const wait = reader.pending[chunk.start] || [];
        delete reader.pending[chunk.start];
        if (err) {
          for (let i = 0; i < wait.length; i++) wait[i](err);
          return;
        }
        const nodes = [];
        const lines = String(text).split('\n');
        for (let i = 0; i < lines.length; i++) {
          if (lines[i]) nodes.push(lines[i].split('\t'));
        }
        if (nodes.length !== chunk.count) {
          for (let i = 0; i < wait.length; i++) wait[i]('分块长度不符 ' + chunk.file);
          return;
        }
        reader.cache[chunk.start] = nodes;
        reader.order.push(chunk.start);
        if (reader.order.length > 4) delete reader.cache[reader.order.shift()];
        for (let i = 0; i < wait.length; i++) wait[i](null, nodes);
      });
    },

    start(chapterId, done) {
      reader.state = blankState();
      const ch = reader.chapter(chapterId);
      reader.state.pc = ch.start;
      reader.state.chapterId = ch.id;
      reader.state.chapterTitle = ch.title;
      reader.frame = null;
      reader.step(done);
    },

    resume(snapshot, done) {
      reader.state = Object.assign(blankState(), snapshot.state || {});
      reader.state.vars = snapshot.vars || {};
      reader.frame = null;
      reader.step(done);
    },

    /** Execute instructions until something needs to be shown. */
    step(done) {
      const s = reader.state;
      const chunk = reader.chunkOf(s.pc);
      reader.loadChunk(chunk, (err, nodes) => {
        if (err) return done(err);
        for (;;) {
          if (s.pc < chunk.start || s.pc >= chunk.start + chunk.count) {
            return reader.step(done);   // pc walked into the next chunk
          }
          const ins = nodes[s.pc - chunk.start];
          if (!ins) return done('节点越界 ' + s.pc);
          const op = ins[0];
          if (op === 's') {
            reader.frame = {
              kind: 'say',
              who: ins[1] === '@' ? s.name : ins[1],
              text: String(ins[2]).replace(/\\n/g, '\n'),
            };
            return done(null, reader.frame);
          }
          if (op === 'm') {
            const parts = ins[1].split('\x1f');
            const options = [];
            for (let i = 0; i < parts.length; i += 2) {
              options.push({ text: parts[i], target: Number(parts[i + 1]) });
            }
            reader.frame = { kind: 'menu', options: options };
            return done(null, reader.frame);
          }
          if (op === 'e') {
            reader.frame = { kind: 'end' };
            return done(null, reader.frame);
          }
          if (op === 'b') { s.bg = ins[1]; s.fg = ''; }
          else if (op === 'g') { s.fg = ins[1]; }
          else if (op === 'p') {
            const prev = s.chars[ins[1]] || {};
            s.chars[ins[1]] = {
              tag: ins[1],
              pos: ins[2] || prev.pos || 'c',
              eye: ins[3] || prev.eye || 'normal',
              brow: ins[4] || prev.brow || 'normal',
              mouth: ins[5] || prev.mouth || 'speak',
              extra: ins[6] || '',
            };
          } else if (op === 'h') {
            if (ins[1] === '@fg') s.fg = '';
            else delete s.chars[ins[1]];
          } else if (op === 'n') { s.name = ins[1]; }
          else if (op === 'd') { s.date = ins[1]; }
          else if (op === 'c') { s.chapterTitle = ins[1]; }
          else if (op === 'v') {
            const cur = Number(s.vars[ins[1]] || 0);
            s.vars[ins[1]] = ins[2].charAt(0) === '+' ? cur + Number(ins[2].slice(1)) : Number(ins[2]);
          } else if (op === 'q') {
            const a = Number(s.vars[ins[1]] || 0);
            const b = Number(s.vars[ins[2]] || 0);
            if (!(a > b)) { s.pc = Number(ins[3]); continue; }
          } else if (op === 'j') { s.pc = Number(ins[1]); continue; }
          s.pc += 1;
        }
      });
    },

    /** Leave the current node and execute the next instruction. */
    next(done) {
      reader.state.pc += 1;
      reader.step(done);
    },

    /** Refresh the chunk window around pc so the next step is cheap. */
    prefetch(pc) {
      const list = reader.index.chunks;
      for (let i = 0; i < list.length; i++) {
        if (list[i].start === reader.chunkOf(pc).start) {
          const next = list[i + 1];
          if (next && !reader.cache[next.start]) reader.loadChunk(next, () => {});
          return;
        }
      }
    },

    choose(index, done) {
      const opt = reader.frame && reader.frame.options[index];
      if (!opt) return done('选项越界');
      reader.state.pc = opt.target;
      reader.step(done);
    },

    snapshot() {
      const s = reader.state;
      return {
        state: JSON.parse(JSON.stringify(s)),
        vars: Object.assign({}, s.vars),
        chapterTitle: s.chapterTitle,
        date: s.date,
        tail: reader.frame && reader.frame.text ? reader.frame.text.slice(0, 34) : '',
        at: Date.now(),
      };
    },
  };
  return reader;
}

/** Split a state.chars map into the three fixed sprite slots. */
export function slotChars(chars) {
  const slots = { l: null, c: null, r: null };
  const keys = Object.keys(chars || {});
  for (let i = 0; i < keys.length; i++) {
    const ch = chars[keys[i]];
    let slot = ch.pos || 'c';
    if (slot === 'cl' || slot === 'fl' || slot === 'l2' || slot === 'l') slot = 'l';
    else if (slot === 'cr' || slot === 'r2' || slot === 'r') slot = 'r';
    else slot = 'c';
    slots[slot] = ch;
  }
  return slots;
}
