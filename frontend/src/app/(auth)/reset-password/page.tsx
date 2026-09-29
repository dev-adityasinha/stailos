"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { Button, ErrorNote, PasswordInput, Spinner } from "@/components/ui";

function ResetForm() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/auth/password/reset", {
        method: "POST",
        body: { token, new_password: password },
      });
      router.replace("/login?reset=1");
    } catch (err) {
      setError(errorMessage(err, "Reset failed."));
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <p className="text-xs text-danger">
        Missing reset token. Use the link from your email, or{" "}
        <Link href="/forgot-password" className="text-primary hover:underline">
          request a new one
        </Link>.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-4">
      {error && <ErrorNote message={error} />}
      <PasswordInput
        label="New password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Min 10 chars, 1 uppercase, 1 number, 1 symbol"
      />
      <Button type="submit" disabled={busy} className="w-full">
        {busy ? "Updating…" : "Update password"}
      </Button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="fade-up">
      <h1 className="text-xl font-semibold">Choose a new password</h1>
      <Suspense fallback={<div className="mt-6"><Spinner /></div>}>
        <ResetForm />
      </Suspense>
    </div>
  );
}
