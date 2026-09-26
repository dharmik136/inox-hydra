/**
 * The playbook, parsed into blocks.
 *
 * The docs surface used to render every document as one <pre> element. That is
 * a defensible choice for untrusted text and it is the wrong one here: across
 * the 38 files the studio indexes there are 798 table rows, 182 fence lines,
 * 1,266 bullets, 1,226 bold runs and 280 third level headings, and all of it
 * reached the reader as literal markdown characters. The pipe tables were the
 * worst of it, because a six row penalty table is unreadable as raw pipes and
 * that table is the actual content of the algorithmic audit section.
 *
 * So the document becomes a data structure first and pixels second. This
 * module is the data structure: pure, synchronous, no DOM, no dependency, and
 * executable from a test without a browser (tests/test_markdown_rendering.py
 * compiles it with esbuild and runs it over the real corpus).
 *
 * What it deliberately does NOT do is produce HTML. Nothing here emits a
 * string that a parser will later interpret, because a playbook file is
 * allowed to contain markup and several of these files do: angle bracket
 * placeholders like the ones in FIRST_RUN.md appear in prose, and one table
 * cell carries a literal break tag. Spans and blocks are rendered as React
 * elements by DocumentView, so every character that is not structure is a text
 * child and is escaped by construction. That is the reasoning lib/snippet.ts
 * was written under, applied to a whole document instead of one snippet.
 *
 * Three dialect decisions, each forced by what is actually in these files:
 *
 * 1. Underscore never opens emphasis. This corpus is full of snake_case:
 *    word_count, li_at, taplio_vault_archive_backup.json, studio-text-muted.
 *    CommonMark's intraword rules would save most of those and mangle the
 *    rest, so only asterisks emphasise here. Nothing in the corpus uses the
 *    underscore for emphasis, and the cost of getting it wrong is silently
 *    eating an identifier out of a technical document.
 *
 * 2. A table needs its delimiter row. Several files draw ASCII interface mocks
 *    out of pipes with no delimiter under them. GFM already requires the
 *    delimiter and requires the cell counts to agree, and that rule is exactly
 *    what tells a layout sketch apart from a table.
 *
 * 3. Inline math must contain a backslash. There is a small amount of LaTeX in
 *    the audit sections and there is no typesetter in this product. Requiring
 *    a LaTeX command inside the dollars keeps a price out of it. Math is
 *    carried through verbatim and shown as source rather than typeset, because
 *    showing it as prose loses the braces and pretending to typeset it would
 *    be inventing a rendering.
 */

/** Column alignment declared by a table's delimiter row. */
export type Align = "left" | "center" | "right" | null;

export type Span =
  | { kind: "text"; text: string }
  | { kind: "strong"; spans: Span[] }
  | { kind: "em"; spans: Span[] }
  | { kind: "code"; text: string }
  | { kind: "math"; text: string }
  | { kind: "break" }
  | { kind: "link"; spans: Span[]; href: string };

/**
 * The five alert kinds GitHub defines. A tone is only ever set because the
 * document declared one on its first line; a plain blockquote stays a plain
 * blockquote rather than being classified by keyword, which would be the
 * studio inventing a severity the author did not write.
 */
export type CalloutTone = "note" | "tip" | "important" | "warning" | "caution";

const TONES: CalloutTone[] = ["note", "tip", "important", "warning", "caution"];

export interface ListItem {
  /** null when the item is not a task item, true or false when it is. */
  checked: boolean | null;
  /** An item is a document of its own, which is how nesting works. */
  blocks: Block[];
}

export type Block =
  | { kind: "heading"; level: number; spans: Span[]; text: string; slug: string }
  | { kind: "paragraph"; spans: Span[] }
  | { kind: "list"; ordered: boolean; start: number; items: ListItem[] }
  | { kind: "code"; language: string | null; code: string }
  | { kind: "formula"; source: string }
  | { kind: "table"; align: Align[]; head: Span[][]; rows: Span[][][] }
  | { kind: "callout"; tone: CalloutTone | null; blocks: Block[] }
  | { kind: "rule" };

export interface Outline {
  level: number;
  text: string;
  slug: string;
}

export interface ParsedDocument {
  blocks: Block[];
  /** Headings below the title, in document order, for the contents rail. */
  outline: Outline[];
  /** The document's own first level one heading, when it has one. */
  title: string | null;
}

// ---------------------------------------------------------------------------
// Line classifiers
// ---------------------------------------------------------------------------

const FENCE = /^(\s*)(`{3,}|~{3,})\s*([A-Za-z0-9_+#-]*)\s*$/;
const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const RULE = /^\s{0,3}([-*_])[ \t]*(?:\1[ \t]*){2,}$/;
const ITEM = /^(\s*)(?:([-*+])|(\d{1,9})[.)])\s+(.*)$/;
const TASK = /^\[([ xX])\]\s+(.*)$/;
const QUOTE = /^\s{0,3}>\s?(.*)$/;
const ALERT = /^\[!([A-Za-z]+)\]\s*$/;
const DELIMITER = /^\s*\|?(?:\s*:?-+:?\s*\|)+\s*:?-*:?\s*\|?\s*$/;

function indentOf(line: string): number {
  return line.length - line.trimStart().length;
}

function isBlank(line: string): boolean {
  return line.trim().length === 0;
}

function isTableStart(lines: string[], i: number): boolean {
  const head = lines[i];
  const delimiter = lines[i + 1];
  if (!head || !delimiter) return false;
  if (!head.trim().startsWith("|")) return false;
  if (!DELIMITER.test(delimiter)) return false;
  // GFM: the header and the delimiter must declare the same number of cells.
  // This is the rule that keeps an ASCII interface sketch from being read as
  // a table, and several files in this corpus draw one.
  return splitRow(head).length === splitRow(delimiter).length;
}

/** True for any line that ends a paragraph by starting something else. */
function startsBlock(lines: string[], i: number): boolean {
  const line = lines[i];
  if (isBlank(line)) return true;
  if (FENCE.test(line)) return true;
  if (HEADING.test(line)) return true;
  if (RULE.test(line)) return true;
  if (QUOTE.test(line)) return true;
  if (ITEM.test(line)) return true;
  if (line.trim().startsWith("$$")) return true;
  return isTableStart(lines, i);
}

// ---------------------------------------------------------------------------
// Block parsing
// ---------------------------------------------------------------------------

export function parseBlocks(lines: string[]): Block[] {
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (isBlank(line)) {
      i += 1;
      continue;
    }

    const fence = FENCE.exec(line);
    if (fence) {
      const marker = fence[2][0];
      const width = fence[2].length;
      const body: string[] = [];
      i += 1;
      while (i < lines.length) {
        const closing = FENCE.exec(lines[i]);
        if (closing && closing[2][0] === marker && closing[2].length >= width && !closing[3]) {
          i += 1;
          break;
        }
        body.push(lines[i]);
        i += 1;
      }
      blocks.push({ kind: "code", language: fence[3] || null, code: dedent(body).join("\n") });
      continue;
    }

    if (line.trim().startsWith("$$")) {
      const [formula, next] = readFormula(lines, i);
      blocks.push(formula);
      i = next;
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      const spans = parseInline(heading[2]);
      blocks.push({
        kind: "heading",
        level: heading[1].length,
        spans,
        text: spanText(spans),
        slug: "",
      });
      i += 1;
      continue;
    }

    if (RULE.test(line)) {
      blocks.push({ kind: "rule" });
      i += 1;
      continue;
    }

    if (QUOTE.test(line)) {
      const inner: string[] = [];
      while (i < lines.length) {
        const quoted = QUOTE.exec(lines[i]);
        if (!quoted) break;
        inner.push(quoted[1]);
        i += 1;
      }
      let tone: CalloutTone | null = null;
      const alert = inner.length ? ALERT.exec(inner[0].trim()) : null;
      if (alert) {
        const declared = alert[1].toLowerCase() as CalloutTone;
        if (TONES.includes(declared)) {
          tone = declared;
          inner.shift();
        }
      }
      blocks.push({ kind: "callout", tone, blocks: parseBlocks(inner) });
      continue;
    }

    if (isTableStart(lines, i)) {
      const [table, next] = readTable(lines, i);
      blocks.push(table);
      i = next;
      continue;
    }

    if (ITEM.test(line)) {
      const [list, next] = readList(lines, i);
      blocks.push(list);
      i = next;
      continue;
    }

    const paragraph: string[] = [line];
    i += 1;
    while (i < lines.length && !startsBlock(lines, i)) {
      paragraph.push(lines[i]);
      i += 1;
    }
    blocks.push({ kind: "paragraph", spans: parseInline(paragraph.join("\n").trim()) });
  }

  return blocks;
}

/**
 * Display math, carried through verbatim.
 *
 * Opens on a line whose first characters are two dollars and closes on the
 * next pair, which may be the same line. An unterminated opener takes the rest
 * of the document rather than silently dropping it, on the same principle as
 * the unbalanced marker in lib/snippet.ts: this is content, not syntax we are
 * entitled to discard.
 */
function readFormula(lines: string[], start: number): [Block, number] {
  const first = lines[start].trim();
  if (first.length > 4 && first.endsWith("$$")) {
    return [{ kind: "formula", source: first.slice(2, -2).trim() }, start + 1];
  }
  const body: string[] = [first.slice(2)];
  let i = start + 1;
  while (i < lines.length) {
    const text = lines[i];
    const close = text.indexOf("$$");
    if (close !== -1) {
      body.push(text.slice(0, close));
      i += 1;
      break;
    }
    body.push(text);
    i += 1;
  }
  return [{ kind: "formula", source: body.join("\n").trim() }, i];
}

function readTable(lines: string[], start: number): [Block, number] {
  const head = splitRow(lines[start]).map((cell) => parseInline(cell));
  const align = splitRow(lines[start + 1]).map(alignmentOf);
  const rows: Span[][][] = [];
  let i = start + 2;
  while (i < lines.length && lines[i].trim().startsWith("|")) {
    const cells = splitRow(lines[i]).map((cell) => parseInline(cell));
    // A short row is padded rather than dropped. Ragged rows exist in these
    // files and losing the cells that were written is worse than an empty one.
    while (cells.length < head.length) cells.push([]);
    rows.push(cells);
    i += 1;
  }
  return [{ kind: "table", align, head, rows }, i];
}

function alignmentOf(cell: string): Align {
  const text = cell.trim();
  const left = text.startsWith(":");
  const right = text.endsWith(":");
  if (left && right) return "center";
  if (right) return "right";
  if (left) return "left";
  return null;
}

/**
 * Splits one table row into cells.
 *
 * Pipes inside a code span are content, not separators: this corpus has cells
 * carrying code with a pipe in it, and splitting there would shift every later
 * cell one column left, which is a silent corruption rather than a visible
 * break.
 */
export function splitRow(line: string): string[] {
  let text = line.trim();
  if (text.startsWith("|")) text = text.slice(1);
  if (text.endsWith("|") && !text.endsWith("\\|")) text = text.slice(0, -1);

  const cells: string[] = [];
  let buffer = "";
  let inCode = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (char === "\\" && text[i + 1] === "|") {
      buffer += "|";
      i += 1;
      continue;
    }
    if (char === "`") inCode = !inCode;
    if (char === "|" && !inCode) {
      cells.push(buffer.trim());
      buffer = "";
      continue;
    }
    buffer += char;
  }
  cells.push(buffer.trim());
  return cells;
}

/**
 * One list, and everything nested under it.
 *
 * Indentation in these files is not on a grid: children sit three spaces under
 * an ordered marker and two under a bullet, sometimes five. So nesting is
 * decided by "more indented than this marker" and the collected lines are
 * dedented by their own minimum rather than by an assumed step. An item is
 * then parsed as a document in its own right, which is what makes a nested
 * list, a fenced block or a table inside a bullet work without a special case.
 */
function readList(lines: string[], start: number): [Block, number] {
  const first = ITEM.exec(lines[start]) as RegExpExecArray;
  const baseIndent = first[1].length;
  const ordered = Boolean(first[3]);
  const startNumber = ordered ? parseInt(first[3], 10) : 1;
  const items: ListItem[] = [];
  let i = start;

  while (i < lines.length) {
    const marker = ITEM.exec(lines[i]);
    if (!marker) break;
    if (marker[1].length !== baseIndent) break;
    if (Boolean(marker[3]) !== ordered) break;

    const owned: string[] = [];
    const indents: number[] = [];
    let head = marker[4];
    i += 1;

    // A fence inside an item may hold lines at column zero, which would
    // otherwise read as the end of the list. While one is open every line
    // belongs to the item regardless of its indentation.
    let openFence: string | null = null;

    while (i < lines.length) {
      const line = lines[i];

      if (openFence) {
        owned.push(line);
        indents.push(indentOf(line));
        if (line.trim().startsWith(openFence)) openFence = null;
        i += 1;
        continue;
      }

      if (isBlank(line)) {
        // A blank line belongs to this item only when more indented content
        // follows it. Otherwise the list ends here and the blank is the gap
        // before whatever comes next.
        let ahead = i;
        while (ahead < lines.length && isBlank(lines[ahead])) ahead += 1;
        if (ahead >= lines.length || indentOf(lines[ahead]) <= baseIndent) break;
        while (i < ahead) {
          owned.push("");
          i += 1;
        }
        continue;
      }

      if (indentOf(line) <= baseIndent) break;

      const fence = FENCE.exec(line);
      if (fence) openFence = fence[2];
      owned.push(line);
      indents.push(indentOf(line));
      i += 1;
    }

    let checked: boolean | null = null;
    const task = TASK.exec(head);
    if (task) {
      checked = task[1].toLowerCase() === "x";
      head = task[2];
    }

    const trim = indents.length ? Math.min(...indents) : 0;
    const body = [head, ...owned.map((line) => (line.length >= trim ? line.slice(trim) : line.trimStart()))];
    items.push({ checked, blocks: parseBlocks(body) });
  }

  return [{ kind: "list", ordered, start: startNumber, items }, i];
}

/** Removes the shared leading whitespace from a fenced block's body. */
function dedent(body: string[]): string[] {
  const indents = body.filter((line) => !isBlank(line)).map(indentOf);
  if (!indents.length) return body;
  const trim = Math.min(...indents);
  if (trim === 0) return body;
  return body.map((line) => (line.length >= trim ? line.slice(trim) : line.trimStart()));
}

// ---------------------------------------------------------------------------
// Inline parsing
// ---------------------------------------------------------------------------

const ESCAPABLE = /[\\`*_{}[\]()#+\-.!|<>~$]/;
const BREAK_TAG = /^<br\s*\/?>/i;

/**
 * Nesting is bounded rather than trusted. Strong holding em holding a link is
 * as deep as anything real goes, and a depth limit means a pathological string
 * degrades to plain text instead of building a stack until the tab dies.
 */
const MAX_SPAN_DEPTH = 5;

export function parseInline(source: string, depth = 0): Span[] {
  if (!source) return [];
  if (depth >= MAX_SPAN_DEPTH) return [{ kind: "text", text: source }];

  const spans: Span[] = [];
  let buffer = "";
  let i = 0;

  const flush = () => {
    if (buffer) {
      spans.push({ kind: "text", text: buffer });
      buffer = "";
    }
  };

  while (i < source.length) {
    const char = source[i];

    if (char === "\\" && i + 1 < source.length && ESCAPABLE.test(source[i + 1])) {
      buffer += source[i + 1];
      i += 2;
      continue;
    }

    // Code first, always. Everything inside a code span is literal, which is
    // what lets a table cell carry a pipe and a bullet carry an asterisk.
    if (char === "`") {
      let run = 0;
      while (source[i + run] === "`") run += 1;
      const ticks = source.slice(i, i + run);
      const close = source.indexOf(ticks, i + run);
      if (close !== -1) {
        flush();
        spans.push({ kind: "code", text: source.slice(i + run, close).trim() });
        i = close + run;
        continue;
      }
    }

    if (char === "<") {
      const tag = BREAK_TAG.exec(source.slice(i));
      if (tag) {
        flush();
        spans.push({ kind: "break" });
        i += tag[0].length;
        continue;
      }
    }

    if (char === "$") {
      const math = readMath(source, i);
      if (math) {
        flush();
        spans.push({ kind: "math", text: math.text });
        i = math.next;
        continue;
      }
    }

    if (char === "[") {
      const link = readLink(source, i);
      if (link) {
        flush();
        spans.push({ kind: "link", spans: parseInline(link.text, depth + 1), href: link.href });
        i = link.next;
        continue;
      }
    }

    if (char === "*" && source[i + 1] === "*") {
      const close = source.indexOf("**", i + 2);
      if (close > i + 2) {
        flush();
        spans.push({ kind: "strong", spans: parseInline(source.slice(i + 2, close), depth + 1) });
        i = close + 2;
        continue;
      }
    }

    if (char === "*") {
      const close = source.indexOf("*", i + 1);
      const inner = close === -1 ? "" : source.slice(i + 1, close);
      // Flanking, the cheap half of CommonMark's rule: an opener is not
      // followed by whitespace and a closer is not preceded by one. That is
      // what keeps arithmetic and a stray asterisk out of emphasis.
      if (close > i + 1 && !/^\s/.test(inner) && !/\s$/.test(inner) && !inner.includes("\n")) {
        flush();
        spans.push({ kind: "em", spans: parseInline(inner, depth + 1) });
        i = close + 1;
        continue;
      }
    }

    buffer += char;
    i += 1;
  }

  flush();
  return spans;
}

function readMath(source: string, start: number): { text: string; next: number } | null {
  if (source[start + 1] === "$") return null;
  const close = source.indexOf("$", start + 1);
  if (close === -1) return null;
  const inner = source.slice(start + 1, close);
  // A LaTeX command is the evidence that this is math at all. Without it a
  // price, a shell variable or a column of currency becomes an equation.
  if (!inner.trim() || !inner.includes("\\")) return null;
  return { text: inner, next: close + 1 };
}

function readLink(source: string, start: number): { text: string; href: string; next: number } | null {
  let depth = 0;
  let i = start;
  for (; i < source.length; i += 1) {
    const char = source[i];
    if (char === "\\") {
      i += 1;
      continue;
    }
    if (char === "[") depth += 1;
    else if (char === "]") {
      depth -= 1;
      if (depth === 0) break;
    }
  }
  if (i >= source.length || source[i + 1] !== "(") return null;

  const labelEnd = i;
  let parens = 1;
  let j = i + 2;
  for (; j < source.length; j += 1) {
    const char = source[j];
    if (char === "\\") {
      j += 1;
      continue;
    }
    if (char === "(") parens += 1;
    else if (char === ")") {
      parens -= 1;
      if (parens === 0) break;
    }
  }
  if (j >= source.length) return null;

  const href = source.slice(labelEnd + 2, j).trim();
  if (!href) return null;
  return { text: source.slice(start + 1, labelEnd), href, next: j + 1 };
}

// ---------------------------------------------------------------------------
// Document level helpers
// ---------------------------------------------------------------------------

/** The reading text of a run of spans, with the markup taken back out. */
export function spanText(spans: Span[]): string {
  return spans
    .map((span) => {
      switch (span.kind) {
        case "text":
        case "code":
        case "math":
          return span.text;
        case "strong":
        case "em":
        case "link":
          return spanText(span.spans);
        case "break":
          return " ";
        default:
          return "";
      }
    })
    .join("");
}

/** An anchor for a heading, stable enough to link to from another document. */
export function slugify(text: string): string {
  const base = text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return base || "section";
}

/**
 * Parses a document and numbers its headings.
 *
 * Slug collisions are numbered rather than allowed to point at each other,
 * because several of these files repeat a heading and a contents rail whose
 * entries all scroll to the first match reads as broken navigation.
 */
export function parseMarkdown(source: string): ParsedDocument {
  const blocks = parseBlocks((source || "").replace(/\r\n?/g, "\n").split("\n"));
  const seen = new Map<string, number>();
  const outline: Outline[] = [];
  let title: string | null = null;

  const assign = (list: Block[]) => {
    for (const block of list) {
      if (block.kind === "heading") {
        const base = slugify(block.text);
        const count = (seen.get(base) ?? 0) + 1;
        seen.set(base, count);
        block.slug = count === 1 ? base : `${base}-${count}`;
        if (block.level === 1 && title === null) {
          title = block.text;
        } else if (block.level >= 2 && block.level <= 3) {
          outline.push({ level: block.level, text: block.text, slug: block.slug });
        }
      } else if (block.kind === "callout") {
        assign(block.blocks);
      } else if (block.kind === "list") {
        for (const item of block.items) assign(item.blocks);
      }
    }
  };
  assign(blocks);

  return { blocks, outline, title };
}
