import { Link } from "../app/router";
import { PageHeader } from "../components/PageHeader";

export function ForbiddenPage() {
  return (
    <div className="not-found">
      <PageHeader title="You don't have access" description="Your role doesn't include this page. Ask an admin if you need it." />
      <p><Link to="/" className="btn btn-primary">Back to the overview</Link></p>
    </div>
  );
}
