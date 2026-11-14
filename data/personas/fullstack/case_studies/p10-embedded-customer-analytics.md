# Embedded customer analytics

From June to August 2023, I worked hourly with a client in B2B SaaS (name withheld) to build embedded usage dashboards inside their product. The goal was straightforward: give every customer account a clear view of its own activity and usage patterns without forcing the team to maintain a separate analytics surface.

Before this project, the client’s team needed a way to expose account-specific metrics directly in the application experience. I helped design and implement a dashboard layer that could reliably show the right metrics for the right account, using React and TypeScript on the frontend, and Node.js with PostgreSQL on the backend. I used Recharts to render the charts and keep the interface responsive and easy to read.

A big part of the work was making the experience feel native to the SaaS product. The dashboards needed to fit into the existing application, but still be flexible enough to support different customer accounts. I built the data flow so the frontend could request scoped metrics and render them consistently, while the backend handled the account-level queries and returned the right payloads.

Here is a small example of the kind of frontend configuration I used:

```tsx
import { LineChart, Line, XAxis, YAxis, Tooltip } from 'recharts';

export function UsageChart({ data }) {
  return (
    <LineChart width={640} height={320} data={data}>
      <XAxis dataKey="date" />
      <YAxis />
      <Tooltip />
      <Line type="monotone" dataKey="usage" stroke="#2563eb" />
    </LineChart>
  );
}
```

The result was an embedded analytics experience that rolled out to 140 customer accounts, and I delivered it 3 weeks early. More importantly, the client’s team now has a productized way to surface per-account usage information directly inside the app, which means less manual effort and a cleaner experience for customers. The dashboards are part of the product rather than an external add-on, so the team can work with account metrics in the same place their users already operate.
