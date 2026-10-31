import { Link } from "../app/router";
import { PageHeader } from "../components/PageHeader";

export function NotFoundPage() {
  return (
    <div className="not-found">
      <PageHeader title="Page not found" description="That address doesn't exist in this console. It may have moved, or the link may be mistyped." />
      <p>
        <Link to="/" className="btn btn-primary">Back to the overview</Link>
      </p>
    </div>
  );
}
