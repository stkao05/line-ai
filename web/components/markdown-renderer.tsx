import type { JSX, ReactNode } from "react";

type MarkdownRendererProps = {
  content: string;
};

function renderInlineMarkdown(text: string): ReactNode[] {
  const segments = text
    .split(/(\*\*[^*]+\*\*|_[^_]+_|`[^`]+`)/g)
    .filter(Boolean);

  return segments.map((segment, index) => {
    if (segment.startsWith("**") && segment.endsWith("**")) {
      return <strong key={index}>{segment.slice(2, -2)}</strong>;
    }

    if (segment.startsWith("_") && segment.endsWith("_")) {
      return <em key={index}>{segment.slice(1, -1)}</em>;
    }

    if (segment.startsWith("`") && segment.endsWith("`")) {
      return (
        <code
          key={index}
          className="rounded bg-zinc-900 px-[6px] py-[2px] text-sm text-emerald-300"
        >
          {segment.slice(1, -1)}
        </code>
      );
    }

    return <span key={index}>{segment}</span>;
  });
}

function renderMarkdown(content: string): ReactNode[] {
  const elements: ReactNode[] = [];
  const lines = content.split("\n");
  let listBuffer: string[] = [];
  let codeBuffer: string[] = [];
  let inCodeBlock = false;

  const flushList = () => {
    if (listBuffer.length === 0) {
      return;
    }

    elements.push(
      <ul key={`list-${elements.length}`} className="list-disc space-y-2 pl-6">
        {listBuffer.map((item, index) => (
          <li key={index} className="text-sm text-zinc-300">
            {renderInlineMarkdown(item)}
          </li>
        ))}
      </ul>
    );

    listBuffer = [];
  };

  const flushCode = () => {
    if (!inCodeBlock) {
      return;
    }

    elements.push(
      <pre
        key={`code-${elements.length}`}
        className="overflow-x-auto rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4 text-sm"
      >
        <code>{codeBuffer.join("\n")}</code>
      </pre>
    );

    codeBuffer = [];
    inCodeBlock = false;
  };

  lines.forEach((line) => {
    const trimmed = line.trim();

    if (trimmed.startsWith("```") || trimmed.startsWith("~~~")) {
      if (!inCodeBlock) {
        flushList();
        inCodeBlock = true;
        codeBuffer = [];
      } else {
        flushCode();
      }
      return;
    }

    if (inCodeBlock) {
      codeBuffer.push(line);
      return;
    }

    if (trimmed.length === 0) {
      flushList();
      return;
    }

    if (/^[-*+]\s+/.test(trimmed)) {
      listBuffer.push(trimmed.replace(/^[-*+]\s+/, ""));
      return;
    }

    flushList();

    if (/^#{1,6}\s+/.test(trimmed)) {
      const level = Math.min(trimmed.match(/^#{1,6}/)?.[0].length ?? 1, 6);
      const HeadingTag = `h${level}` as keyof JSX.IntrinsicElements;
      const text = trimmed.replace(/^#{1,6}\s+/, "");

      elements.push(
        <HeadingTag
          key={`heading-${elements.length}`}
          className="text-lg font-semibold text-zinc-100"
        >
          {renderInlineMarkdown(text)}
        </HeadingTag>
      );
      return;
    }

    elements.push(
      <p
        key={`paragraph-${elements.length}`}
        className="text-base leading-relaxed text-zinc-200"
      >
        {renderInlineMarkdown(line)}
      </p>
    );
  });

  flushList();
  flushCode();

  return elements;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return <>{renderMarkdown(content)}</>;
}

export { renderMarkdown };
