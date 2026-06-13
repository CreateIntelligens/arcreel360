// Small presentational helpers shared across AgentConfigTab sub-components.

export function SectionHeading({ title, description }: { title: string; description: string }) {
  return (
    <div className="mb-4">
      <h3 className="text-base font-semibold text-[color:var(--wb-text-primary)]">{title}</h3>
      <p className="mt-1 text-sm leading-6 text-[color:var(--wb-text-muted)]">{description}</p>
    </div>
  );
}
