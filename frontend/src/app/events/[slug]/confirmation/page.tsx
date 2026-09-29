"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CheckCircle2, Copy } from "lucide-react";
import { API_BASE, api } from "@/lib/api";

interface StoredRegistration {
  id: string;
  checkin_token: string;
  referral_code: string;
}

export default function EventConfirmationPage() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const [reg, setReg] = useState<StoredRegistration | null>(null);
  const [referralCount, setReferralCount] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const raw = sessionStorage.getItem(`event_reg_${slug}`);
    if (!raw) {
      router.replace(`/events/${slug}`);
      return;
    }
    setReg(JSON.parse(raw));
  }, [slug, router]);

  useEffect(() => {
    if (!reg) return;
    api<{ data: { count: number } }>(`/events/public/${slug}/referrals/${reg.referral_code}/count`)
      .then((r) => setReferralCount(r.data.count))
      .catch(() => {});
  }, [reg, slug]);

  if (!reg) return null;

  const referralLink =
    typeof window !== "undefined"
      ? `${window.location.origin}/events/${slug}?ref=${reg.referral_code}`
      : "";

  function copyLink() {
    navigator.clipboard.writeText(referralLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col items-center justify-center px-6 py-16 text-center text-ink">
      <CheckCircle2 size={40} className="text-success" />
      <h1 className="mt-4 text-xl font-semibold">You&apos;re registered!</h1>
      <p className="mt-1 text-sm text-muted">
        A confirmation with your check-in code has been sent to your email and WhatsApp.
      </p>

      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`${API_BASE}/events/public/${slug}/qr?token=${encodeURIComponent(reg.checkin_token)}`}
        alt="Your check-in QR code"
        className="mt-6 h-40 w-40 rounded-xl border border-edge bg-white p-2"
      />
      <p className="mt-2 text-[11px] text-faint">Show this QR code at the venue to check in.</p>

      <div className="mt-8 w-full rounded-xl border border-edge bg-surface p-4">
        <p className="text-xs font-semibold">Invite a friend</p>
        <p className="mt-1 text-[11px] text-muted">
          {referralCount !== null ? `${referralCount} people have used your link so far.` : ""}
        </p>
        <div className="mt-3 flex items-center gap-2">
          <input
            readOnly value={referralLink}
            className="flex-1 truncate rounded-lg border border-edge-strong bg-bg px-3 py-2 text-xs"
          />
          <button
            onClick={copyLink}
            className="flex items-center gap-1 rounded-lg bg-primary px-3 py-2 text-xs font-medium text-white hover:bg-primary-hover"
          >
            <Copy size={12} /> {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
    </div>
  );
}
