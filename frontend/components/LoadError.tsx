/** A failed load, said plainly, with a way to try again. */
export function LoadError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="notice load-error" role="alert">
      <p className="error" style={{ margin: 0 }}>{message}</p>
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
