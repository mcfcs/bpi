import type { EmotionCue } from "@/lib/types";

const DETECTED = "Detected from participants’ words";

/**
 * Feelings voiced in a qualitative finding or quote, as small quiet words. They are read from the
 * wording by a lexicon in code, so they say how participants sounded, never how many feel that way.
 * The tone shows in the text colour and in the word itself, never in colour alone.
 */
export function EmotionTags({ emotions, className = "emotions" }: { emotions: EmotionCue[] | null | undefined; className?: string }) {
  if (!emotions?.length) return null;
  return (
    <span className={className}>
      <span className="visually-hidden">Feelings voiced ({DETECTED.toLowerCase()}):</span>
      {emotions.map((e) => (
        <span key={e.key} className={`emotion tone-${e.tone === "positive" || e.tone === "negative" ? e.tone : "neutral"}`} title={DETECTED}>
          {e.label}
        </span>
      ))}
    </span>
  );
}
