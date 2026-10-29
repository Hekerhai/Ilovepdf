import Link from "next/link";

import { BRAND, SITE_URL } from "@/lib/brand";
import { catalog } from "@/lib/tools";

export const metadata = { title: "Developer API", description: `Every ${BRAND} PDF tool as a REST API.` };

const CURL = `# 1. Start a task (1 credit)
curl -X POST ${SITE_URL}/v1/jobs \\
  -H "Authorization: Bearer fk_live_..." \\
  -F tool=compress \\
  -F 'options={"level":"recommended"}' \\
  -F files=@report.pdf

# 2. Poll until status is "succeeded"
curl ${SITE_URL}/v1/jobs/JOB_ID -H "Authorization: Bearer fk_live_..."

# 3. Download the result
curl -L -o report-small.pdf ${SITE_URL}/v1/jobs/JOB_ID/download -H "Authorization: Bearer fk_live_..."`;

const PY = `import json, time, requests

API = "${SITE_URL}/v1"
H = {"Authorization": "Bearer fk_live_..."}

steps = [{"tool": "ocr", "options": {"languages": ["eng"]}},
         {"tool": "compress", "options": {"level": "recommended"}}]
job = requests.post(f"{API}/jobs", headers=H, data={"steps": json.dumps(steps)},
                    files=[("files", open("scan.pdf", "rb"))]).json()
while job["status"] in ("queued", "running"):
    time.sleep(1)
    job = requests.get(f"{API}/jobs/{job['id']}", headers=H).json()
if job["status"] == "succeeded":
    open("scan-ocr.pdf", "wb").write(requests.get(f"{API}/jobs/{job['id']}/download", headers=H).content)
else:
    print(job["error"])`;

export default function DevelopersPage() {
  return (
    <div className="container-page py-12">
      <div className="max-w-3xl">
        <h1 className="text-4xl font-extrabold tracking-tight">Developer API</h1>
        <p className="mt-3 text-lg text-slate-600 dark:text-slate-400">
          All {catalog.tools.length} tools, the same engines as the web app, one simple REST API. Chain tools in a single call
          with <code>steps</code>. Files are deleted automatically.
        </p>
        <div className="mt-6 flex gap-3">
          <Link href="/account?tab=api" className="btn-primary">Get an API key</Link>
          <a href="/api/docs" className="btn-secondary">OpenAPI reference</a>
        </div>
      </div>
      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="mb-2 font-semibold">cURL</h2>
          <pre className="overflow-x-auto rounded-2xl bg-slate-900 p-5 text-xs text-slate-100">{CURL}</pre>
        </div>
        <div>
          <h2 className="mb-2 font-semibold">Python (workflow in one call)</h2>
          <pre className="overflow-x-auto rounded-2xl bg-slate-900 p-5 text-xs text-slate-100">{PY}</pre>
        </div>
      </div>
      <div className="mt-10 grid gap-4 md:grid-cols-3">
        {[
          ["Auth", "Send Authorization: Bearer <key>. Keys are created and revoked in your account."],
          ["Credits", "One credit per task. Free accounts get 250 a month, Pro 1,000, Business 5,000."],
          ["Errors", 'Errors return {"error": {"code", "message"}} with a meaningful HTTP status (402, 422, 429...).'],
        ].map(([t, d]) => (
          <div key={t} className="card p-5">
            <h3 className="font-semibold">{t}</h3>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{d}</p>
          </div>
        ))}
      </div>
      <h2 className="mt-12 text-2xl font-bold">Tools</h2>
      <div className="card mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr><th className="p-3">tool</th><th className="p-3">Accepts</th><th className="p-3">Options</th></tr>
          </thead>
          <tbody>
            {catalog.tools.map((t) => (
              <tr key={t.id} className="border-t border-slate-100 align-top dark:border-slate-800">
                <td className="p-3"><code className="font-semibold">{t.id}</code><p className="text-xs text-slate-500">{t.name}{t.premium ? " · Pro" : ""}</p></td>
                <td className="p-3 text-xs text-slate-500">{t.accepts.join(" ")}</td>
                <td className="p-3 text-xs text-slate-500">{Object.keys(t.options_schema.properties ?? {}).join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
