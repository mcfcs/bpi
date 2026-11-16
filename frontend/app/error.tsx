"use client"; // Error boundaries must be Client Components

import Link from "next/link";
import { useEffect } from "react";

export default function Error({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <section className="page-head" role="alert">
      <title>Something went wrong · ALAMKansya</title>
      <h1>This page could not be shown</h1>
      <p>
        Something unexpected came back from the evidence service. Your briefs and requests are saved; try again, or go
        back to your questions.
      </p>
      <div className="actions" style={{ marginTop: 16 }}>
        <button type="button" className="btn btn-primary" onClick={() => retry()}>
          Try again
        </button>
        <Link href="/" className="btn">
          Ask a question
        </Link>
      </div>
    </section>
  );
}
