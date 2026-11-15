import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Button, ErrorBox, Field, inputClass } from "../components/ui";
import { api, must, setToken } from "../lib/client";

const PERSONAS = [
  ["ai_ml", "AI / ML engineer"],
  ["fullstack", "Full-stack developer"],
  ["data_analyst", "Data analyst"],
] as const;

type Persona = (typeof PERSONAS)[number][0];

export function Login() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [persona, setPersona] = useState<Persona>("ai_ml");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "register") {
        await must(api.POST("/auth/register", { body: { username, password, persona } }));
      }
      const token = await must(api.POST("/auth/login", { body: { username, password } }));
      setToken(token.access_token);
      navigate(mode === "register" ? "/onboarding" : "/jobs");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-sm px-4 py-16">
      <h1 className="mb-1 text-3xl font-bold text-indigo-700">GigBid</h1>
      <p className="mb-6 text-slate-600">Your freelancer copilot. Nothing is sent without your approval.</p>
      <form onSubmit={submit} className="space-y-4 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold">{mode === "login" ? "Sign in" : "Create an account"}</h2>
        <Field id="username" label="Username">
          <input id="username" autoComplete="username" required value={username}
            onChange={(e) => setUsername(e.target.value.toLowerCase())} className={inputClass} />
        </Field>
        <Field id="password" label="Password">
          <input id="password" type="password" required minLength={8} value={password}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            onChange={(e) => setPassword(e.target.value)} className={inputClass} />
        </Field>
        {mode === "register" && (
          <fieldset className="space-y-1">
            <legend className="text-sm font-medium">Persona</legend>
            {PERSONAS.map(([value, label]) => (
              <label key={value} className="flex items-center gap-2 text-sm">
                <input type="radio" name="persona" value={value} checked={persona === value}
                  onChange={() => setPersona(value)} />
                {label}
              </label>
            ))}
          </fieldset>
        )}
        {Boolean(error) && <ErrorBox error={error} />}
        <Button type="submit" disabled={busy} className="w-full">{mode === "login" ? "Sign in" : "Create account"}</Button>
        <button type="button" className="w-full text-sm text-indigo-700 underline"
          onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
        </button>
      </form>
    </main>
  );
}
