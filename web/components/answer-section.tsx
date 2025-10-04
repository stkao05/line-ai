import { MarkdownRenderer } from "./markdown-renderer";

export type TurnReference = {
  title: string;
  description: string;
  href: string;
};

type AnswerSectionProps = {
  content: string;
  references: TurnReference[];
  referencesLabel?: string;
};

export function AnswerSection({
  content,
  references,
  referencesLabel = "References",
}: AnswerSectionProps) {
  const trimmedContent = content.trim();
  const hasContent = trimmedContent.length > 0;
  const hasReferences = references.length > 0;

  return (
    <div className="space-y-6">
      <div className="space-y-4 text-base leading-relaxed text-zinc-200">
        {hasContent ? <MarkdownRenderer content={trimmedContent} /> : null}
      </div>

      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
          {referencesLabel}
        </p>
        {hasReferences ? (
          <div className="grid gap-3 md:grid-cols-3">
            {references.map((reference) => (
              <a
                key={reference.href}
                className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4 transition hover:border-emerald-400/60 hover:text-emerald-200"
                href={reference.href}
                target="_blank"
                rel="noreferrer"
              >
                <p className="text-sm font-semibold break-words">{reference.title}</p>
                <p className="mt-1 text-xs text-zinc-400 break-words">
                  {reference.description}
                </p>
              </a>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
