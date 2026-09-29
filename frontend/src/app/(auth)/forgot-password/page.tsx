"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { Button, Input } from "@/components/ui";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/auth/password/forgot", { method: "POST", body: { email } });
    } finally {
      setBusy(false);
      setSent(true); // same outcome either way — no account enumeration
    }
  }

  return (
    <div className="fade-up">
      <h1 className="text-xl font-semibold">Reset your password</h1>
      {sent ? (
        <p className="mt-4 rounded-lg border border-success/30 bg-success/10 px-3 py-3 text-xs text-success">
          If an account exists for {email}, a reset link has been sent. The link
          expires in 15 minutes.
        </p>
      ) : (
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <Input label="Email" type="email" required value={email}
                 onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      )}
      <p className="mt-4 text-xs">
        <Link href="/login" className="text-primary hover:underline">Back to sign in</Link>
      </p>
    </div>
  );
}
