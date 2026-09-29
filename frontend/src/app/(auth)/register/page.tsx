"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { Button, ErrorNote, Input, PasswordInput } from "@/components/ui";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    full_name: "", company_name: "", email: "", phone: "", password: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/auth/register", {
        method: "POST",
        body: { ...form, phone: form.phone || undefined },
      });
      router.replace("/login?registered=1");
    } catch (err) {
      setError(errorMessage(err, "Registration failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fade-up">
      <h1 className="text-[28px] font-medium tracking-[-0.03em]">Create a workspace</h1>
      <p className="mt-2 text-[13px] leading-relaxed text-muted">
        You become its admin. We send a verification email after signup.
      </p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        {error && <ErrorNote message={error} />}
        <Input label="Full name" required minLength={2} value={form.full_name}
               onChange={set("full_name")} placeholder="Priya Sharma" />
        <Input label="Company name" required minLength={2} value={form.company_name}
               onChange={set("company_name")} placeholder="e.g. Prestige Group" />
        <Input label="Email" type="email" required value={form.email}
               onChange={set("email")} placeholder="you@company.com" />
        <Input label="Phone (optional)" value={form.phone} onChange={set("phone")}
               placeholder="98765 43210" />
        <PasswordInput
          label="Password"
          required
          value={form.password}
          onChange={set("password")}
          placeholder="Min 10 chars, 1 uppercase, 1 number, 1 symbol"
        />
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? "Creating…" : "Create account"}
        </Button>
      </form>
      <p className="mt-4 text-xs text-muted">
        Already have an account?{" "}
        <Link href="/login" className="text-primary hover:underline">Sign in</Link>
      </p>
    </div>
  );
}
