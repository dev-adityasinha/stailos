"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Spinner } from "@/components/ui";

function VerifyInner() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"working" | "done" | "failed">("working");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setState("failed");
      setMessage("Missing verification token.");
      return;
    }
    api("/auth/verify-email", { method: "POST", body: { token } })
      .then(() => setState("done"))
      .catch((err) => {
        setState("failed");
        setMessage(err instanceof ApiError ? err.message : "Verification failed.");
      });
  }, [token]);

  if (state === "working") return <Spinner />;
  return (
    <div className="fade-up">
      {state === "done" ? (
        <p className="rounded-lg border border-success/30 bg-success/10 px-3 py-3 text-xs text-success">
          Email verified. You can now sign in.
        </p>
      ) : (
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-3 text-xs text-danger">
          {message}
        </p>
      )}
      <p className="mt-4 text-xs">
        <Link href="/login" className="text-primary hover:underline">Go to sign in</Link>
      </p>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Email verification</h1>
      <Suspense fallback={<Spinner />}>
        <VerifyInner />
      </Suspense>
    </div>
  );
}
