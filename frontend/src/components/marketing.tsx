/* Shared pieces for the public surfaces (landing page, auth screens).
 *
 * These commit to a dark canvas regardless of the app theme. The product UI
 * follows the user's light/dark preference; the front door does not, so the
 * brand reads the same to every visitor and the auth panel and landing page
 * cannot drift apart. */

import Link from "next/link";

/** Small uppercase label. Mono, because it is a tag rather than prose. */
export function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
      {children}
    </p>
  );
}

export function Wordmark({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="group inline-flex items-baseline gap-2">
      <span className="text-[15px] font-medium tracking-tight text-white">
        Pappu
      </span>
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/35 transition-colors group-hover:text-white/55">
        Realty OS
      </span>
    </Link>
  );
}

/** Ambient background: one soft light source, plus a hairline grid that fades
 *  out before it competes with the type. Pure CSS, no image request. */
export function Backdrop() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 overflow-hidden">
      <div
        className="absolute left-1/2 top-[-30vh] h-[70vh] w-[110vw] -translate-x-1/2 rounded-[50%] opacity-[0.22] blur-[120px]"
        style={{ background: "radial-gradient(closest-side, #4d8df0, transparent)" }}
      />
      <div
        className="absolute inset-0 opacity-[0.14]"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(255,255,255,.06) 1px, transparent 1px)," +
            "linear-gradient(to bottom, rgba(255,255,255,.06) 1px, transparent 1px)",
          backgroundSize: "72px 72px",
          maskImage: "radial-gradient(ellipse 80% 55% at 50% 0%, #000 40%, transparent 100%)",
          WebkitMaskImage:
            "radial-gradient(ellipse 80% 55% at 50% 0%, #000 40%, transparent 100%)",
        }}
      />
    </div>
  );
}
