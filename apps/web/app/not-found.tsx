import Link from "next/link";

export default function NotFound() {
  return (
    <div className="wrap stack" style={{ gap: 32 }}>
      <h1 className="display d-xl">404</h1>
      <p className="lead">This page doesn&apos;t exist, or it belongs to another workspace.</p>
      <div className="row">
        <Link className="btn" href="/">Home</Link>
        <Link className="btn-ghost" href="/sample">See the sample run</Link>
      </div>
    </div>
  );
}
