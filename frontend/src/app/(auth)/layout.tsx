import Link from "next/link";
import { Backdrop, Eyebrow, Wordmark } from "@/components/marketing";

/* Auth shell. Shares its type scale, palette and backdrop with the landing page
   so signing in does not feel like a different product.

   The left panel carries one idea. It used to repeat the landing page's stat
   row, which told a returning user nothing they had not already scrolled past. */

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="surface-dark relative flex min-h-screen bg-bg text-ink">
      <Backdrop />

      <aside className="relative hidden flex-1 flex-col justify-between p-12 lg:flex">
        <Wordmark />
        <div>
          <Eyebrow>Real estate CRM</Eyebrow>
          <p
            className="mt-6 max-w-md font-medium tracking-[-0.035em] text-white"
            style={{ fontSize: "clamp(1.9rem, 3vw, 2.6rem)", lineHeight: 1.1 }}
          >
            The follow-up writes itself.
            <br />
            <span className="text-white/40">You decide if it sends.</span>
          </p>
        </div>
        <p className="font-mono text-[11px] tracking-wide text-white/25">
          © 2026 Shiv Trinetrix AI Labs Pvt. Ltd.
        </p>
      </aside>

      <main className="relative flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-10 lg:hidden">
            <Wordmark />
          </div>
          {children}
          <p className="mt-10 text-center font-mono text-[11px] tracking-wide text-white/25">
            <Link href="/" className="transition-colors hover:text-white/50">
              Back to home
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}
