import { Badge } from "./ui";

// connected marketplaces
export function Accounts() {
  return (
    <ul className="space-y-2 text-sm">
      <li className="flex items-center justify-between">
        <span>GigSim (simulated marketplace)</span>
        <Badge tone="green">connected</Badge>
      </li>
      <li className="flex items-center justify-between">
        <span>Upwork</span>
        <Badge>not connected</Badge>
      </li>
    </ul>
  );
}
