import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  BarChart3,
  LineChart,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  onLogin: () => void;
}

function useRevealOnScroll() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const items = node.querySelectorAll("[data-reveal]");
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("landing-revealed");
          }
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -8% 0px" }
    );

    items.forEach((item) => observer.observe(item));
    return () => observer.disconnect();
  }, []);

  return ref;
}

export function AnalystIQLandingPage({ onLogin }: Props) {
  const scrollRef = useRevealOnScroll();
  const [isEntering, setIsEntering] = useState(false);

  const handleLogin = () => {
    setIsEntering(true);
    window.setTimeout(onLogin, 520);
  };

  return (
    <div
      className={`landing-shell min-h-screen overflow-x-hidden bg-[#050816] text-slate-100 transition-opacity duration-500 ${
        isEntering ? "pointer-events-none opacity-0" : "opacity-100"
      }`}
    >
      <div className="landing-grid-overlay pointer-events-none fixed inset-0" />
      <div className="landing-orb landing-orb-a pointer-events-none fixed -left-24 top-16 h-72 w-72 rounded-full" />
      <div className="landing-orb landing-orb-b pointer-events-none fixed -right-20 top-1/3 h-96 w-96 rounded-full" />
      <div className="landing-orb landing-orb-c pointer-events-none fixed bottom-0 left-1/3 h-80 w-80 rounded-full" />

      <header className="relative z-10 mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-blue-400/30 bg-blue-500/10">
            <Sparkles className="h-5 w-5 text-blue-300" />
          </div>
          <span className="text-lg font-semibold tracking-wide text-white">AnalystIQ</span>
        </div>
        <Button
          onClick={handleLogin}
          className="landing-login-btn h-10 rounded-full bg-blue-500 px-6 text-sm font-semibold text-white shadow-lg shadow-blue-500/30 hover:bg-blue-400"
        >
          Login
        </Button>
      </header>

      <main ref={scrollRef} className="relative z-10">
        <section className="mx-auto flex min-h-[78vh] w-full max-w-6xl flex-col justify-center px-6 pb-16 pt-8">
          <div data-reveal className="landing-reveal mb-6 inline-flex w-fit items-center gap-2 rounded-full border border-blue-400/25 bg-blue-500/10 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.22em] text-blue-200">
            <Zap className="h-3.5 w-3.5" />
            Institutional Intelligence Platform
          </div>

          <h1 data-reveal className="landing-reveal landing-delay-1 max-w-4xl text-5xl font-semibold leading-tight tracking-tight text-white md:text-7xl">
            Analyst<span className="bg-gradient-to-r from-blue-300 via-cyan-200 to-indigo-300 bg-clip-text text-transparent">IQ</span>
          </h1>

          <p data-reveal className="landing-reveal landing-delay-2 mt-6 max-w-2xl text-lg leading-8 text-slate-300 md:text-xl">
            A sleek research operating system for analyst teams — from investment narratives to agency credit comparisons,
            delivered with evidence-backed precision.
          </p>

          <div data-reveal className="landing-reveal landing-delay-3 mt-10 flex flex-wrap items-center gap-4">
            <Button
              onClick={handleLogin}
              className="landing-login-btn group h-12 rounded-full bg-gradient-to-r from-blue-500 to-indigo-500 px-8 text-base font-semibold text-white shadow-xl shadow-blue-600/35 hover:from-blue-400 hover:to-indigo-400"
            >
              Login to Workspace
              <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Button>
            <span className="text-sm text-slate-400">No credentials required for this preview</span>
          </div>

          <div className="landing-beam-track mt-14 overflow-hidden rounded-full">
            <div className="landing-beam h-1.5 w-full rounded-full" />
          </div>
        </section>

        <section className="mx-auto w-full max-w-6xl px-6 py-20">
          <div data-reveal className="landing-reveal mb-10 max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-300">Capabilities</p>
            <h2 className="mt-3 text-3xl font-semibold text-white md:text-4xl">Built for decision-grade research workflows</h2>
          </div>

          <div className="grid gap-5 md:grid-cols-3">
            {[
              {
                icon: LineChart,
                title: "Signal-rich synthesis",
                copy: "Transform market, financial, and credit evidence into structured narratives analysts can defend in committee.",
              },
              {
                icon: ShieldCheck,
                title: "Citation-backed outputs",
                copy: "Every key claim links to source context so teams can audit conclusions before distribution.",
              },
              {
                icon: TrendingUp,
                title: "Export-ready deliverables",
                copy: "Move from live workspace review to PDF, Word, and presentation exports without rework.",
              },
            ].map((item, idx) => (
              <article
                key={item.title}
                data-reveal
                className={`landing-reveal landing-delay-${idx + 1} landing-card rounded-2xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-sm`}
              >
                <div className="mb-4 inline-flex rounded-lg border border-blue-400/20 bg-blue-500/10 p-2.5">
                  <item.icon className="h-5 w-5 text-blue-300" />
                </div>
                <h3 className="text-lg font-semibold text-white">{item.title}</h3>
                <p className="mt-2 text-sm leading-7 text-slate-300">{item.copy}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="mx-auto w-full max-w-6xl px-6 py-10 pb-24">
          <div data-reveal className="landing-reveal mb-8">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-300">Workspaces</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">Choose your intelligence lane after login</h2>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <article
              data-reveal
              className="landing-reveal landing-delay-1 landing-card group relative overflow-hidden rounded-3xl border border-blue-400/20 bg-gradient-to-br from-blue-950/70 via-slate-900/80 to-slate-950 p-8"
            >
              <div className="landing-card-beam pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-blue-400 to-transparent opacity-70" />
              <div className="mb-5 inline-flex rounded-xl border border-blue-300/25 bg-blue-500/15 p-3">
                <BarChart3 className="h-6 w-6 text-blue-200" />
              </div>
              <h3 className="text-2xl font-semibold text-white">Report IQ</h3>
              <p className="mt-3 max-w-md text-sm leading-7 text-slate-300">
                Generate investment and credit analysis reports with executive summaries, research journey tracking, and
                editable presentation exports.
              </p>
            </article>

            <article
              data-reveal
              className="landing-reveal landing-delay-2 landing-card group relative overflow-hidden rounded-3xl border border-indigo-400/20 bg-gradient-to-br from-indigo-950/70 via-slate-900/80 to-slate-950 p-8"
            >
              <div className="landing-card-beam pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-indigo-400 to-transparent opacity-70" />
              <div className="mb-5 inline-flex rounded-xl border border-indigo-300/25 bg-indigo-500/15 p-3">
                <ShieldCheck className="h-6 w-6 text-indigo-200" />
              </div>
              <h3 className="text-2xl font-semibold text-white">Credit Rating Workspace</h3>
              <p className="mt-3 max-w-md text-sm leading-7 text-slate-300">
                Compare agency rating perspectives side-by-side with period-focused evidence, dynamic comparison
                matrices, and citation-linked exports.
              </p>
            </article>
          </div>

          <div data-reveal className="landing-reveal landing-delay-3 mt-14 rounded-3xl border border-white/10 bg-white/[0.03] p-8 text-center backdrop-blur-sm md:p-12">
            <h3 className="text-2xl font-semibold text-white md:text-3xl">Ready to enter your workspace?</h3>
            <p className="mx-auto mt-3 max-w-xl text-sm leading-7 text-slate-300 md:text-base">
              Click login to access Report IQ and Credit Rating Workspace from a unified AnalystIQ hub.
            </p>
            <Button
              onClick={handleLogin}
              className="landing-login-btn mt-8 h-12 rounded-full bg-blue-500 px-10 text-base font-semibold text-white shadow-lg shadow-blue-600/30 hover:bg-blue-400"
            >
              Login
            </Button>
          </div>
        </section>
      </main>

      <footer className="relative z-10 border-t border-white/10 px-6 py-6 text-center text-xs text-slate-500">
        AnalystIQ · Institutional Research Intelligence
      </footer>
    </div>
  );
}
