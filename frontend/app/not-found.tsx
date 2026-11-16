import Link from "next/link";

export default function NotFound() {
  return (
    <section className="page-head">
      <title>Not found · ALAMKansya</title>
      <h1>There is no page here</h1>
      <p>The link may be out of date. Briefs stay under your recent briefs on the question page.</p>
      <div className="actions" style={{ marginTop: 16 }}>
        <Link href="/" className="btn btn-primary">
          Ask a question
        </Link>
      </div>
    </section>
  );
}
