import Link from "next/link";

export function NotFound() {
  return (
    <p className="empty">
      That page doesn&apos;t exist. <Link className="link" href="/">Back to Today</Link>
    </p>
  );
}
