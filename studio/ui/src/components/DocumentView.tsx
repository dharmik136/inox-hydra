import { useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  Check,
  Copy,
  Info,
  Lightbulb,
  OctagonAlert,
  Pin,
  Square,
  SquareCheck,
} from "lucide-react";
import type { Align, Block, CalloutTone, ListItem, Span } from "@/lib/markdown";
import { spanText } from "@/lib/markdown";
import { cn } from "@/lib/utils";

/**
 * A parsed playbook, drawn.
 *
 * Every visual in here is a React element built from a typed block, never a
 * string handed to the HTML parser. That is not fastidiousness: these files
 * contain angle bracket placeholders in prose and one table cell with a
 * literal break tag, so a document that went through innerHTML would lose the
 * placeholders and gain whatever else it happened to contain. Text is a text
 * child, so it is escaped by construction and the only markup on screen is the
 * markup this file wrote.
 *
 * Colour is tokens only, per docs/UI_CONVENTIONS.md section 1, so every
 * treatment below follows the theme without a single dark: variant. Two rules
 * from that document shape the layout as much as the palette does: wide content
 * scrolls inside its own container rather than pushing the page sideways, which
 * is what the table wrapper is for, and a glyph that carries meaning gets a
 * name while a decorative one is hidden.
 */

/** What a markdown href turns out to point at, once the library is known. */
export type ResolvedLink =
  | { kind: "document"; id: string; anchor: string | null }
  | { kind: "anchor"; anchor: string }
  | { kind: "external"; href: string }
  | { kind: "missing"; href: string };

export interface DocumentViewProps {
  blocks: Block[];
  /** Turns an href into something this surface can act on. */
  resolve: (href: string) => ResolvedLink;
  /** Opens another document in the library, optionally at one of its headings. */
  onOpenDocument: (id: string, anchor: string | null) => void;
  /** Scrolls to a heading in the document already open. */
  onJumpTo: (slug: string) => void;
}

export function DocumentView({ blocks, resolve, onOpenDocument, onJumpTo }: DocumentViewProps) {
  return (
    <>
      {blocks.map((block, index) => (
        <BlockView
          key={index}
          block={block}
          resolve={resolve}
          onOpenDocument={onOpenDocument}
          onJumpTo={onJumpTo}
        />
      ))}
    </>
  );
}

type BlockProps = Omit<DocumentViewProps, "blocks"> & { block: Block; nested?: boolean };

function BlockView({ block, nested, ...links }: BlockProps) {
  switch (block.kind) {
    case "heading":
      return <HeadingView block={block} {...links} />;

    case "paragraph":
      return (
        <p className={cn("text-[14px] leading-[1.75] text-ink-secondary", nested ? "" : "mt-4 max-w-[74ch]")}>
          <Spans spans={block.spans} {...links} />
        </p>
      );

    case "list":
      return <ListView block={block} {...links} />;

    case "code":
      return <CodeView language={block.language} code={block.code} />;

    case "formula":
      return <FormulaView source={block.source} />;

    case "table":
      return <TableView align={block.align} head={block.head} rows={block.rows} {...links} />;

    case "callout":
      return <CalloutView tone={block.tone} blocks={block.blocks} {...links} />;

    case "rule":
      // The authors use a rule to close a section. It is structure, so it is
      // drawn as the quietest thing on the page rather than a full width line
      // competing with the heading that follows it.
      return <hr className="mx-0 my-9 w-16 border-0 border-t border-edge-strong" />;

    default:
      return null;
  }
}

/**
 * Headings carry the id the contents rail scrolls to.
 *
 * Six levels collapse into four treatments, because past the third level these
 * documents are labelling a short list rather than opening a section, and four
 * distinguishable steps in one column is already the limit of what reads as a
 * hierarchy instead of as noise.
 */
function HeadingView({ block, ...links }: { block: Extract<Block, { kind: "heading" }> } & Omit<DocumentViewProps, "blocks">) {
  const content = <Spans spans={block.spans} {...links} />;

  if (block.level === 1) {
    return (
      <h1 id={block.slug} className="studio-title mt-2 mb-1 max-w-[30ch] text-balance">
        {content}
      </h1>
    );
  }
  if (block.level === 2) {
    return (
      <h2
        id={block.slug}
        className="mt-11 mb-1 max-w-[46ch] font-display text-[22px] leading-tight font-semibold tracking-[-0.01em] text-ink-primary text-balance"
      >
        {content}
      </h2>
    );
  }
  if (block.level === 3) {
    return (
      <h3 id={block.slug} className="mt-7 mb-1 text-[14px] leading-snug font-semibold text-ink-primary">
        {content}
      </h3>
    );
  }
  return (
    <h4 id={block.slug} className="studio-label mt-6 mb-1 text-ink-secondary">
      {content}
    </h4>
  );
}

function ListView({ block, ...links }: { block: Extract<Block, { kind: "list" }> } & Omit<DocumentViewProps, "blocks">) {
  // A task list is a state report rather than a bulleted one, so it drops the
  // marker and shows the box the author actually wrote.
  //
  // "Any item", not "every item". The parser records checked per item, and
  // requiring the whole list to be uniform meant one plain bullet among the
  // tasks sent the entire list down the bullet path, where nothing renders the
  // box and every tick and every empty box silently disappears. Nothing in the
  // corpus mixes them today, which is exactly why that would have gone
  // unnoticed: the state is parsed, so the marker never leaks, and the only
  // symptom is content quietly missing from screen.
  const hasTasks = block.items.some((item) => item.checked !== null);

  if (hasTasks) {
    return (
      <ul className="mt-3 flex max-w-[74ch] list-none flex-col gap-1.5 pl-0">
        {block.items.map((item, index) => (
          <li key={index} className="flex items-start gap-2">
            {item.checked === null ? (
              // Not a task. The marker column is held open so the text of a
              // plain item still lines up with the ones that have a box.
              <span className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            ) : item.checked ? (
              <SquareCheck className="mt-0.5 size-4 shrink-0 text-signal-green-text" strokeWidth={1.75} role="img" aria-label="Done" />
            ) : (
              <Square className="mt-0.5 size-4 shrink-0 text-ink-muted" strokeWidth={1.75} role="img" aria-label="Not done" />
            )}
            <div className="min-w-0 flex-1">
              <ItemBody item={item} {...links} />
            </div>
          </li>
        ))}
      </ul>
    );
  }

  const Tag = block.ordered ? "ol" : "ul";
  return (
    <Tag
      start={block.ordered ? block.start : undefined}
      className={cn(
        "mt-3 max-w-[74ch] marker:text-ink-muted",
        block.ordered
          ? "list-decimal pl-[1.6rem] marker:font-mono marker:text-[12px] marker:tabular-nums"
          : "list-disc pl-[1.15rem]",
      )}
    >
      {block.items.map((item, index) => (
        <li key={index} className="mt-1.5 pl-1.5 first:mt-0">
          <ItemBody item={item} {...links} />
        </li>
      ))}
    </Tag>
  );
}

/**
 * The inside of one list item.
 *
 * A single paragraph item renders inline, so a plain bullet does not gain the
 * leading a paragraph carries. Anything richer, a nested list, a fenced block,
 * a formula, is a document and is drawn as one.
 */
function ItemBody({ item, ...links }: { item: ListItem } & Omit<DocumentViewProps, "blocks">) {
  if (item.blocks.length === 1 && item.blocks[0].kind === "paragraph") {
    return (
      <span className="block text-[14px] leading-[1.7] text-ink-secondary">
        <Spans spans={item.blocks[0].spans} {...links} />
      </span>
    );
  }
  return (
    <>
      {item.blocks.map((block, index) => (
        <BlockView key={index} block={block} nested={index === 0 && block.kind === "paragraph"} {...links} />
      ))}
    </>
  );
}

const TONE_CHROME: Record<CalloutTone, { icon: typeof Info; label: string; edge: string; ink: string }> = {
  note: { icon: Info, label: "Note", edge: "border-l-signal-blue", ink: "text-signal-blue" },
  tip: { icon: Lightbulb, label: "Tip", edge: "border-l-signal-green", ink: "text-signal-green-text" },
  important: { icon: Pin, label: "Important", edge: "border-l-signal-orange", ink: "text-signal-orange-text" },
  warning: { icon: AlertTriangle, label: "Warning", edge: "border-l-signal-orange", ink: "text-signal-orange-text" },
  caution: { icon: OctagonAlert, label: "Caution", edge: "border-l-signal-orange", ink: "text-signal-orange-text" },
};

/**
 * A blockquote, and the five kinds of alert a document may declare.
 *
 * The tone only ever comes from the document's own [!KIND] marker. A quote
 * without one stays a quote: classifying it by keyword would have the studio
 * assigning a severity nobody wrote, which is the same mistake as showing a
 * metric nobody measured.
 */
function CalloutView({ tone, blocks, ...links }: { tone: CalloutTone | null; blocks: Block[] } & Omit<DocumentViewProps, "blocks">) {
  const chrome = tone ? TONE_CHROME[tone] : null;
  const Icon = chrome?.icon;

  return (
    <aside
      className={cn(
        "mt-5 max-w-[76ch] rounded-r-md border-l-2 bg-soft py-3 pr-4 pl-4",
        chrome ? chrome.edge : "border-l-edge-strong",
      )}
    >
      {chrome && Icon && (
        <p className={cn("studio-label mb-1 flex items-center gap-1.5", chrome.ink)}>
          <Icon className="size-3.5" strokeWidth={2} aria-hidden="true" />
          {chrome.label}
        </p>
      )}
      <div className="[&>*:first-child]:mt-0">
        {blocks.map((block, index) => (
          <BlockView key={index} block={block} {...links} />
        ))}
      </div>
    </aside>
  );
}

const ALIGNMENT: Record<string, string> = {
  left: "text-left",
  center: "text-center",
  right: "text-right",
};

/**
 * A table, scrolling inside its own box.
 *
 * 798 rows across this corpus arrived as raw pipes before this existed, and the
 * six row penalty table in module 01 is the actual content of the algorithmic
 * audit section rather than an aside. Alignment is the delimiter row's, digits
 * are tabular so a column of numbers lines up, and cells align to the top
 * because these cells are paragraphs rather than labels.
 */
function TableView({
  align,
  head,
  rows,
  ...links
}: { align: Align[]; head: Span[][]; rows: Span[][][] } & Omit<DocumentViewProps, "blocks">) {
  return (
    <div className="mt-5 overflow-x-auto rounded-md border border-edge">
      <table className="w-full border-collapse text-[13px] tabular-nums">
        <thead>
          <tr className="bg-soft">
            {head.map((cell, index) => (
              <th
                key={index}
                scope="col"
                className={cn(
                  "studio-label border-b border-edge px-3 py-2 align-bottom whitespace-nowrap text-ink-secondary",
                  ALIGNMENT[align[index] ?? ""] ?? "text-left",
                )}
              >
                <Spans spans={cell} {...links} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-b border-edge last:border-b-0">
              {row.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  className={cn(
                    "px-3 py-2.5 align-top leading-[1.6]",
                    cellIndex === 0 ? "text-ink-primary" : "text-ink-secondary",
                    ALIGNMENT[align[cellIndex] ?? ""] ?? "text-left",
                  )}
                >
                  <Spans spans={cell} {...links} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Nine of the 91 fenced blocks in this corpus are mermaid diagrams.
 *
 * There is no diagram renderer in this product and adding one would be a
 * dependency that runs document content. So the chip says what the block is and
 * the source is shown, which is honest. A box captioned "diagram" with nothing
 * in it, or a picture assembled from a guess at the graph, would not be.
 */
const MERMAID = "mermaid";

function CodeView({ language, code }: { language: string | null; code: string }) {
  const [copied, setCopied] = useState<"idle" | "done" | "failed">("idle");
  const lines = code.split("\n").length;

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied("done");
    } catch {
      setCopied("failed");
    }
    window.setTimeout(() => setCopied("idle"), 2000);
  }

  const label = language === MERMAID ? "Mermaid diagram source" : language;

  return (
    <figure className="mt-5 overflow-hidden rounded-md border border-edge bg-ink">
      <figcaption className="flex items-center justify-between gap-3 border-b border-edge px-3 py-1.5">
        <span className="studio-label truncate">{label ?? "Code"}</span>
        <span className="flex items-center gap-3">
          <span className="studio-meta text-[10px] text-ink-muted">
            {lines} {lines === 1 ? "LINE" : "LINES"}
          </span>
          <button
            type="button"
            onClick={() => void copy()}
            className="flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] text-ink-muted transition-colors duration-(--studio-motion-fast) hover:bg-soft hover:text-ink-primary"
          >
            {copied === "done" ? (
              <Check className="size-3" strokeWidth={2} aria-hidden="true" />
            ) : (
              <Copy className="size-3" strokeWidth={1.75} aria-hidden="true" />
            )}
            {copied === "done" ? "Copied" : copied === "failed" ? "Could not copy" : "Copy"}
          </button>
        </span>
      </figcaption>
      <pre className="overflow-x-auto px-3 py-3 font-mono text-[12px] leading-[1.65] text-ink-secondary">
        <code>{code}</code>
      </pre>
    </figure>
  );
}

/**
 * LaTeX, shown as the source it is.
 *
 * There are five display formulas and eleven inline ones in this corpus, and no
 * typesetter in the product. Printing them as prose loses the braces and the
 * fractions; typesetting them from a hand rolled substitution table would be
 * the studio deciding what an equation says. So they are set apart, in mono,
 * labelled as source, and left exactly as written.
 */
function FormulaView({ source }: { source: string }) {
  return (
    <figure className="mt-5 max-w-[76ch] overflow-hidden rounded-md border border-edge bg-soft">
      <figcaption className="studio-label border-b border-edge px-3 py-1.5">Formula, as written</figcaption>
      <pre className="overflow-x-auto px-3 py-2.5 font-mono text-[12px] leading-relaxed text-ink-secondary">
        <code>{source}</code>
      </pre>
    </figure>
  );
}

// ---------------------------------------------------------------------------
// Inline spans
// ---------------------------------------------------------------------------

function Spans({ spans, ...links }: { spans: Span[] } & Omit<DocumentViewProps, "blocks">) {
  return (
    <>
      {spans.map((span, index) => (
        <SpanView key={index} span={span} {...links} />
      ))}
    </>
  );
}

function SpanView({ span, resolve, onOpenDocument, onJumpTo }: { span: Span } & Omit<DocumentViewProps, "blocks">) {
  const links = { resolve, onOpenDocument, onJumpTo };

  switch (span.kind) {
    case "text":
      return <>{span.text}</>;

    case "strong":
      // Bold inside secondary body text lifts to the primary step. That is the
      // hierarchy these documents are using it for: 1,226 bold runs, nearly all
      // of them the subject of the sentence they open.
      return (
        <strong className="font-semibold text-ink-primary">
          <Spans spans={span.spans} {...links} />
        </strong>
      );

    case "em":
      return (
        <em className="italic">
          <Spans spans={span.spans} {...links} />
        </em>
      );

    case "code":
    case "math":
      // Both are source rather than prose, so both get the same treatment. A
      // second style for math would be a distinction without a difference: the
      // reader's question about either one is "this is literal", and that is
      // what the mono face on a tinted ground already says.
      return (
        <code className="rounded-sm bg-soft px-[0.3em] py-[0.1em] font-mono text-[0.86em] text-ink-primary">
          {span.text}
        </code>
      );

    case "break":
      return <br />;

    case "link":
      return <LinkView span={span} {...links} />;

    default:
      return null;
  }
}

/**
 * The four things a link in these documents turns out to be.
 *
 * 43 of the 51 links point at another markdown file in this same corpus, which
 * is the whole reason this is worth doing: the playbook cross references itself
 * and until now every one of those was dead text. Six are anchors within a
 * document and one leaves the machine.
 *
 * An href that resolves to nothing is deliberately NOT a link. The studio can
 * either open a target or it cannot, and offering a control that does nothing
 * is worse than showing the reader the path and saying it is not in the
 * library.
 */
function LinkView({ span, resolve, onOpenDocument, onJumpTo }: { span: Extract<Span, { kind: "link" }> } & Omit<DocumentViewProps, "blocks">) {
  const target = resolve(span.href);
  const label = spanText(span.spans) || span.href;
  const content = <Spans spans={span.spans} resolve={resolve} onOpenDocument={onOpenDocument} onJumpTo={onJumpTo} />;
  const inline =
    "underline decoration-signal-orange decoration-1 underline-offset-2 transition-colors duration-(--studio-motion-fast) hover:text-signal-orange-text";

  if (target.kind === "document") {
    return (
      <button type="button" onClick={() => onOpenDocument(target.id, target.anchor)} className={cn(inline, "text-ink-primary")}>
        {content}
      </button>
    );
  }

  if (target.kind === "anchor") {
    return (
      <button type="button" onClick={() => onJumpTo(target.anchor)} className={cn(inline, "text-ink-primary")}>
        {content}
      </button>
    );
  }

  if (target.kind === "external") {
    return (
      // The one link in this corpus that leaves the machine, marked as doing
      // so. This product's whole claim is that it does not reach the network
      // on its own, and a reader following a link is not the studio phoning
      // home, but they are owed the distinction before they click.
      <a
        href={target.href}
        target="_blank"
        rel="noreferrer noopener"
        title={`Opens ${target.href} in your browser, which leaves this machine`}
        className={cn(inline, "inline-flex items-baseline gap-0.5 text-ink-primary")}
      >
        {content}
        <ArrowUpRight className="size-3 self-center text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
      </a>
    );
  }

  return (
    <span
      title={`${target.href} is not in the offline library`}
      className="underline decoration-edge-strong decoration-dotted decoration-1 underline-offset-2"
    >
      {label}
    </span>
  );
}

/**
 * Spans with no link behaviour, for a fragment shown outside the reader.
 *
 * A library row's excerpt is the document's own opening line, markdown and all,
 * so it needs the parser to read correctly. What it does not need is working
 * cross references: a sidebar entry is a control that opens a document, and a
 * second control nested inside it that opens a different one is a trap. Link
 * text renders, the link does not.
 */
export function InlineText({ spans }: { spans: Span[] }) {
  return (
    <>
      {spans.map((span, index) => {
        switch (span.kind) {
          case "text":
            return <span key={index}>{span.text}</span>;
          case "strong":
            return (
              <strong key={index} className="font-medium text-ink-primary">
                <InlineText spans={span.spans} />
              </strong>
            );
          case "em":
            return (
              <em key={index} className="italic">
                <InlineText spans={span.spans} />
              </em>
            );
          case "link":
            return <InlineText key={index} spans={span.spans} />;
          case "code":
          case "math":
            return (
              <code key={index} className="font-mono text-[0.92em]">
                {span.text}
              </code>
            );
          case "break":
            return <span key={index}> </span>;
          default:
            return null;
        }
      })}
    </>
  );
}
