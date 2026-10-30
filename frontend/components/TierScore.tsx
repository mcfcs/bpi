import type { TierBreakdown } from "@/lib/types";

const signed = (points: number) => `${points >= 0 ? "+" : ""}${points}`;

/** How the robustness tier was scored: points for method, sample size and recency, then the tier. */
export function TierScore({ breakdown: b }: { breakdown: TierBreakdown }) {
  return (
    <table className="score">
      <caption className="visually-hidden">How the robustness tier was scored</caption>
      <tbody>
        <tr><td>Method</td><td className="num">{signed(b.method_points)}</td></tr>
        <tr><td>Sample size</td><td className="num">{signed(b.sample_points)}</td></tr>
        <tr><td>Recency ({b.age_months} months since fieldwork)</td><td className="num">{signed(b.recency_points)}</td></tr>
        <tr><td><strong>Score → tier</strong></td><td className="num"><strong>{b.score} → {b.tier}</strong></td></tr>
      </tbody>
    </table>
  );
}
