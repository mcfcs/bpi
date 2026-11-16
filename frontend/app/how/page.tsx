import Link from "next/link";

/**
 * How to use the app: the four demo personas and what each feature does, for a first-time visitor or a
 * judge. Static and readable without signing in; the homepage links here from the top of the ask band.
 */

const PERSONAS = [
  {
    initials: "BS",
    name: "Ben Santos",
    team: "SME Banking",
    role: "Business unit",
    sees: "Open studies and SME Banking’s own, including its restricted SME loan survey.",
    tryThis: "Ask a question, ask a follow-up, and get told when a new study answers an earlier question.",
  },
  {
    initials: "DC",
    name: "Dino Cruz",
    team: "SME Banking",
    role: "Approver",
    sees: "The same studies as Ben.",
    tryThis: "Decide requests from other teams to read SME Banking’s restricted studies (Access).",
  },
  {
    initials: "CM",
    name: "Carla Mendoza",
    team: "Cards & Payments",
    role: "Business unit",
    sees: "Open studies and Cards & Payments’ own. SME Banking’s restricted survey shows only as a title.",
    tryThis: "Ask the SME question to see permissions at work, then request access to the restricted survey.",
  },
  {
    initials: "AR",
    name: "Ana Reyes",
    team: "Strategy & Insights",
    role: "S&I analyst",
    sees: "Every approved study, plus new reports waiting for review.",
    tryThis: "Review and approve new reports, answer analyst questions, and open the gap map and audit log.",
  },
];

type Feature = { name: string; where?: { href: string; label: string }; body: string };

const EVERYONE: Feature[] = [
  {
    name: "Ask a question",
    where: { href: "/", label: "Ask a question" },
    body: "Type a business question in English, Filipino or Taglish. ALAMKansya searches the approved studies your team may read, by meaning rather than exact words, and writes a brief in about 10 to 20 seconds.",
  },
  {
    name: "Read the brief",
    body: "The answer comes first, in Executive, Analyst or Plain-language wording; the facts are the same in all three. Key figures are copied from the studies, never written by the AI, and every statement cites its study and page. The brief also says how sure it is, who was surveyed, what people said in focus groups, and what the evidence doesn’t cover. Print or save it as a PDF memo.",
  },
  {
    name: "Ask a follow-up",
    body: "Under any brief, ask something like “What about owners in Mindanao?”. The follow-up keeps the original subject and links back to the first brief.",
  },
  {
    name: "An honest “no”, then an alert",
    body: "If no approved study answers a question, the brief says so instead of guessing, and the question is remembered. When S&I later approves a study that answers it, you get a green notice and a badge on Ask a question.",
  },
  {
    name: "Browse studies and request access",
    where: { href: "/studies", label: "Studies" },
    body: "See every approved study. Restricted studies from other teams appear as a title only, with a Request access button; the owning team decides.",
  },
  {
    name: "Ask an analyst",
    where: { href: "/analyst", label: "Ask an analyst" },
    body: "One click from any brief sends it to S&I, with the question already drafted from what the brief couldn’t answer. The reply appears on your brief.",
  },
  {
    name: "Before you commission",
    where: { href: "/commission", label: "Before you commission" },
    body: "Paste the objectives of research you are thinking of ordering. Each one is marked Covered, Covered but old, Partly covered or New problem, with the studies behind it. Nothing is sent until you send it.",
  },
];

const ANALYSTS: Feature[] = [
  {
    name: "Review queue",
    where: { href: "/review", label: "Review queue" },
    body: "New reports wait here before anyone can search them. Each one gets a personal-data check (phone numbers, emails, IDs, names) and an overlap check against approved studies. Edit the study card and findings, then approve or reject with a note.",
  },
  {
    name: "Analyst desk",
    where: { href: "/analyst", label: "Analyst desk" },
    body: "Questions business units sent from their briefs, with the gaps already written up. Reply, and the answer appears on their brief.",
  },
  {
    name: "Access",
    where: { href: "/access", label: "Access" },
    body: "Requests to read restricted studies. S&I decides for its own studies; a team’s approver (Dino, for SME Banking) decides for theirs.",
  },
  {
    name: "Gap map",
    where: { href: "/gaps", label: "Gap map" },
    body: "Coverage by topic and place (Covered, Old, Partial, Gap), how often each topic is asked about, and the questions no study answered yet. It suggests where new research would be used first.",
  },
  {
    name: "Audit log",
    where: { href: "/audit", label: "Audit log" },
    body: "Every brief, review decision, access decision and alert, with who did it and their note. Nobody can edit or delete an entry. The tiles at the top count questions answered without an analyst and research reused across teams.",
  },
];

const WALKTHROUGH = [
  "As Ben, click the example “Why do SME owners drop off during online loan applications?” and read the brief.",
  "Under it, ask the follow-up “What about owners in Mindanao?”.",
  "Ask “How do sari-sari store owners use supplier credit?”. No approved study answers it yet.",
  "Switch to Ana → Review queue → Cebu SME Digital Onboarding Focus Groups 2026: see the personal-data and overlap checks.",
  "Review queue → Mindanao Sari-sari Store Credit Focus Groups 2026 → add a note → Approve.",
  "Switch back to Ben: a green notice says a new study answers his earlier question. Click See the answer.",
  "As Ana, open Gap map and Audit log.",
];

function FeatureList({ items }: Readonly<{ items: Feature[] }>) {
  return (
    <ul className="guide-features">
      {items.map((f) => (
        <li key={f.name}>
          <h3>{f.name}</h3>
          <p>{f.body}</p>
          {f.where && (
            <p className="guide-where">
              Where: <Link href={f.where.href}>{f.where.label}</Link>
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function HowPage() {
  return (
    <>
      <title>How it works · ALAMKansya</title>
      <section className="page-head">
        <h1>How to use ALAMKansya</h1>
        <p>
          ALAMKansya answers business questions from BPI’s approved research, with every statement linked to the study and
          page it came from. This page explains the demo personas and what each feature does. All data here is synthetic.
        </p>
      </section>

      <section className="section guide-first" aria-labelledby="personas-title">
        <div className="section-head"><h2 id="personas-title">1. Pick a persona</h2></div>
        <p className="section-intro">
          Switch personas from the menu at the top right. Each person sees only what their team may read, so the same
          question can give different answers.
        </p>
        <ul className="guide-personas">
          {PERSONAS.map((p) => (
            <li key={p.name}>
              <div className="guide-person">
                <span className="avatar" aria-hidden>{p.initials}</span>
                <span>
                  <strong>{p.name}</strong>
                  <small>{p.team} · {p.role}</small>
                </span>
              </div>
              <p><b>Can read:</b> {p.sees}</p>
              <p><b>Try:</b> {p.tryThis}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="section" aria-labelledby="everyone-title">
        <div className="section-head"><h2 id="everyone-title">2. What everyone can do</h2></div>
        <FeatureList items={EVERYONE} />
      </section>

      <section className="section" aria-labelledby="analysts-title">
        <div className="section-head">
          <h2 id="analysts-title">3. What S&amp;I analysts can do</h2>
          <span className="tag">Ana Reyes; Access also for approvers like Dino</span>
        </div>
        <FeatureList items={ANALYSTS} />
      </section>

      <section className="section" aria-labelledby="walk-title">
        <div className="section-head">
          <h2 id="walk-title">4. Try it in five minutes</h2>
          <span className="tag">Uses fresh demo data; approving the Mindanao report uses it up</span>
        </div>
        <ol className="guide-steps">
          {WALKTHROUGH.map((s) => <li key={s}>{s}</li>)}
        </ol>
      </section>

      <section className="section" aria-labelledby="trust-title">
        <div className="section-head"><h2 id="trust-title">5. Good to know</h2></div>
        <ul className="guide-notes">
          <li><b>The AI writes the wording only.</b> Numbers, charts and confidence come from the studies, and every sentence is checked against its source.</li>
          <li><b>Restricted studies never reach the AI.</b> The database hides what your team may not read before any search.</li>
          <li><b>People decide.</b> An analyst approves every study, owning teams decide access, any brief can go to an analyst, and nothing is commissioned until a person sends it.</li>
          <li><b>All data is synthetic.</b> The studies, people and figures were invented for this prototype.</li>
        </ul>
        <p style={{ marginTop: 24 }}>
          <Link href="/" className="btn btn-primary">Ask a question</Link>
        </p>
      </section>
    </>
  );
}
