"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useAuth } from "@/lib/auth";
import { errorMessage } from "@/lib/api";
import { Button, ErrorNote, Input, PasswordInput, Spinner } from "@/components/ui";

function LoginBanner() {
  const params = useSearchParams();
  const message = params.get("registered")
    ? "Account created. Check your email for a verification link, then sign in."
    : params.get("reset")
      ? "Password updated. Sign in with your new password."
      : null;
  if (!message) return null;
  return (
    <p className="mt-4 rounded-lg border border-success/30 bg-success/10 px-3 py-2.5 text-xs text-success">
      {message}
    </p>
  );
}

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch (err) {
      setError(errorMessage(err, "Login failed. Try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        {error && <ErrorNote message={error} />}
        <Input
          label="Email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
        />
        <PasswordInput
          label="Password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••••"
        />
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <div className="mt-4 flex justify-between text-xs">
        <Link href="/forgot-password" className="text-primary hover:underline">
          Forgot password?
        </Link>
        <Link href="/register" className="text-muted hover:text-ink hover:underline">
          Create an account
        </Link>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="fade-up">
      <h1 className="text-[28px] font-medium tracking-[-0.03em]">Welcome back</h1>
      <p className="mt-2 text-[13px] text-muted">Sign in to your workspace.</p>
      <Suspense fallback={<div className="mt-6"><Spinner /></div>}>
        <LoginBanner />
        <LoginForm />
      </Suspense>
    </div>
  );
}
