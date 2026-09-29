"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, errorMessage, setToken } from "@/lib/api";
import { Spinner } from "@/components/ui";
import { User } from "@/lib/auth";

function SsoHandler() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    if (!code) {
      setError("No exchange code provided.");
      return;
    }

    let mounted = true;

    async function redeem() {
      try {
        const res = await api<{ data: { access_token: string; user: User } }>("/auth/exchange/redeem", {
          method: "POST",
          body: { code },
        });

        if (mounted) {
          setToken(res.data.access_token);
          // Force a full reload to the dashboard so auth context refreshes
          window.location.href = "/dashboard";
        }
      } catch (err) {
        if (mounted) {
          console.error("SSO error:", err);
          setError(errorMessage(err, "Single sign-on failed. Please try logging in normally."));
        }
      }
    }

    redeem();

    return () => {
      mounted = false;
    };
  }, [searchParams, router]);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-ink">
        <div className="p-8 rounded-2xl bg-paper/5 border border-line">
          <h1 className="text-xl font-bold mb-4">Authentication Failed</h1>
          <p className="text-danger mb-6">{error}</p>
          <button 
            onClick={() => router.replace("/login")}
            className="px-4 py-2 bg-signal text-ink rounded-lg font-medium"
          >
            Go to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen">
      <Spinner />
      <p className="mt-4 text-muted">Authenticating...</p>
    </div>
  );
}

export default function SsoPage() {
  return (
    <Suspense fallback={
      <div className="flex flex-col items-center justify-center min-h-screen">
        <Spinner />
        <p className="mt-4 text-muted">Loading...</p>
      </div>
    }>
      <SsoHandler />
    </Suspense>
  );
}
