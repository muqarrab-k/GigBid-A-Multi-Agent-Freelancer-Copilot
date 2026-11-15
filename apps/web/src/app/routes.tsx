import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "../components/Layout";
import { Analytics } from "./Analytics";
import { Inbox } from "./Inbox";
import { JobDetail } from "./JobDetail";
import { Login } from "./Login";
import { Messages } from "./Messages";
import { Onboarding } from "./Onboarding";
import { Pipeline } from "./Pipeline";
import { RunViewer } from "./RunViewer";
import { Settings } from "./Settings";
import { Approvals, Studio } from "./Studio";

export const router = createBrowserRouter([
  { path: "/login", element: <Login /> },
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Navigate to="/jobs" replace /> },
      { path: "/onboarding", element: <Onboarding /> },
      { path: "/jobs", element: <Inbox /> },
      { path: "/jobs/:jobId", element: <JobDetail /> },
      { path: "/runs/:threadId", element: <RunViewer /> },
      { path: "/approvals", element: <Approvals /> },
      { path: "/approvals/:threadId", element: <Studio /> },
      { path: "/pipeline", element: <Pipeline /> },
      { path: "/messages", element: <Messages /> },
      { path: "/analytics", element: <Analytics /> },
      { path: "/settings", element: <Settings /> },
    ],
  },
]);
