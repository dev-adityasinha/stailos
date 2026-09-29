"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Backdrop, Eyebrow, Wordmark } from "@/components/marketing";

/* Public landing page: the product's own front door, on the same origin as the
   app, so there is no cross-domain auth handoff in the funnel.

   Deliberately not a feature grid. Nine icon cards said less than four
   sentences do, and every card was a claim a prospect had to take on trust.
   What is here instead is the specific mechanic behind each claim. */

const CAPABILITIES = [
  {
    k: "01",
    title: "Scoring you can argue with",
    body: "Every lead is graded across six dimensions with the weight and the reason shown. The number is computed, never generated, so a model cannot talk a cold lead into looking hot.",
  },
  {
    k: "02",
    title: "Setup that builds the product",
    body: "Onboarding is not a survey. Your projects become priced inventory, your cities decide geographic scoring, and the weights you set are the rubric applied to every lead after.",
  },
  {
    k: "03",
    title: "One pass from enquiry to keys",
    body: "Pipeline, site visits, bookings, payments and possession in a single record. Events publish a page, take registrations, and drop them in as leads.",
  },
  {
    k: "04",
    title: "Drafts, never sends",
    body: "AI writes the WhatsApp message, the email and the call opener. A person approves each one. Nothing reaches a customer unread.",
  },
];

const FLOW = [
  ["Register", "You own an isolated workspace from the first click."],
  ["Set up", "Twelve short forms. Skip any of them and finish later."],
  ["Sell", "Pipeline, scoring and analytics are live on the same data."],
];

export default function Home() {
  const { user, loading } = useAuth();

  return (
    <div className="surface-dark relative min-h-screen bg-bg text-white">
      <Backdrop />

      <div className="relative">
        <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-7">
          <Wordmark />
          <nav className="flex items-center gap-6 text-[13px]">
            {!loading && user ? (
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-1.5 text-white/70 transition-colors hover:text-white"
              >
                Open dashboard <ArrowRight size={13} />
              </Link>
            ) : (
              <>
                <Link href="/login" className="text-white/60 transition-colors hover:text-white">
                  Sign in
                </Link>
                <Link
                  href="/register"
                  className="rounded-full bg-white px-4 py-1.5 text-[13px] font-medium text-[#0d0d0f] transition-opacity hover:opacity-90"
                >
                  Start
                </Link>
              </>
            )}
          </nav>
        </header>

        <section className="mx-auto max-w-5xl px-6 pb-24 pt-20 sm:pt-28">
          <Eyebrow>Real estate CRM</Eyebrow>
          <h1
            className="mt-6 max-w-3xl font-medium tracking-[-0.04em] text-white"
            style={{ fontSize: "clamp(2.6rem, 7vw, 5rem)", lineHeight: 1.02 }}
          >
            The follow-up writes itself.
            <br />
            <span className="text-white/40">You decide if it sends.</span>
          </h1>
          <p className="mt-8 max-w-lg text-[15px] leading-relaxed text-white/50">
            Capture leads, score them on evidence, run the pipeline to
            possession, and let AI draft what comes next.
          </p>

          <div className="mt-10 flex flex-wrap items-center gap-3">
            <Link
              href="/register"
              className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-[14px] font-medium text-[#0d0d0f] transition-opacity hover:opacity-90"
            >
              Create a workspace <ArrowRight size={14} />
            </Link>
            <Link
              href="/login"
              className="rounded-full border border-white/15 px-5 py-2.5 text-[14px] text-white/70 transition-colors hover:border-white/30 hover:text-white"
            >
              Sign in
            </Link>
          </div>
          <p className="mt-5 font-mono text-[11px] tracking-wide text-white/30">
            No card. Your own workspace, isolated from every other.
          </p>
        </section>

        <section className="border-t border-white/[0.08]">
          <div className="mx-auto grid max-w-5xl grid-cols-1 sm:grid-cols-2">
            {CAPABILITIES.map(({ k, title, body }, i) => (
              <div
                key={k}
                className={[
                  "border-white/[0.08] px-6 py-12",
                  i % 2 === 0 ? "sm:border-r" : "",
                  i < 2 ? "border-b" : "",
                  i === 2 ? "border-b sm:border-b-0" : "",
                ].join(" ")}
              >
                <span className="font-mono text-[11px] tracking-widest text-white/25">
                  {k}
                </span>
                <h2 className="mt-5 text-[19px] font-medium tracking-tight text-white">
                  {title}
                </h2>
                <p className="mt-3 max-w-sm text-[14px] leading-relaxed text-white/45">
                  {body}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="border-t border-white/[0.08]">
          <div className="mx-auto max-w-5xl px-6 py-20">
            <Eyebrow>Getting started</Eyebrow>
            <ol className="mt-10 space-y-px">
              {FLOW.map(([title, body], i) => (
                <li
                  key={title}
                  className="flex flex-col gap-1 border-t border-white/[0.08] py-6 sm:flex-row sm:items-baseline sm:gap-10"
                >
                  <span className="font-mono text-[11px] tracking-widest text-white/25 sm:w-10">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="text-[16px] font-medium tracking-tight text-white sm:w-44">
                    {title}
                  </span>
                  <span className="text-[14px] leading-relaxed text-white/45">
                    {body}
                  </span>
                </li>
              ))}
            </ol>

            <div className="mt-16">
              <Link
                href="/register"
                className="group inline-flex items-baseline gap-3 tracking-[-0.03em] text-white"
                style={{ fontSize: "clamp(1.6rem, 4vw, 2.4rem)" }}
              >
                Start now
                <ArrowRight
                  size={22}
                  className="translate-y-0.5 text-white/40 transition-transform group-hover:translate-x-1"
                />
              </Link>
            </div>
          </div>
        </section>

        <footer className="border-t border-white/[0.08]">
          <div className="mx-auto flex max-w-5xl flex-col gap-3 px-6 py-8 text-[12px] text-white/30 sm:flex-row sm:items-center sm:justify-between">
            <span>© 2026 Shiv Trinetrix AI Labs Pvt. Ltd.</span>
            <span className="font-mono text-[11px] tracking-wide">Pappu Realty OS</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
