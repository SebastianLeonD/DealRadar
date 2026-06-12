import type { ReactNode } from "react";
import { Badge, PageHeader } from "../components/ui";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rise mb-10">
      <h2
        className="mb-4 border-b border-line-strong pb-2 text-xl font-bold text-ink"
        style={{ fontFamily: "var(--font-display)" }}
      >
        {title}
      </h2>
      <div className="space-y-3 text-[15px] leading-relaxed text-ink-soft">{children}</div>
    </section>
  );
}

function Term({ word, children }: { word: string; children: ReactNode }) {
  return (
    <div className="flex gap-4 border-b border-line py-3 last:border-b-0">
      <dt className="w-36 shrink-0 font-semibold text-ink">{word}</dt>
      <dd className="m-0 text-sm leading-relaxed text-ink-soft">{children}</dd>
    </div>
  );
}

function Faq({ q, children }: { q: string; children: ReactNode }) {
  return (
    <details className="group border-b border-line py-3 last:border-b-0">
      <summary className="cursor-pointer list-none font-semibold text-ink transition-colors hover:text-bet">
        {q}
      </summary>
      <div className="mt-2 space-y-2 text-sm leading-relaxed text-ink-soft">{children}</div>
    </details>
  );
}

export function HelpPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="How this all works"
        subtitle="Everything you need to use the system without asking anyone. Five minutes to read."
      />

      <Section title="The idea in one paragraph">
        <p>
          PrizePicks asks you to guess over or under a number. The big sportsbooks — DraftKings,
          FanDuel, BetMGM — set their numbers with far more information than any of us have. This
          system downloads their numbers, converts them into a true win chance for every
          PrizePicks line, and tells you which picks the math actually supports. You only ever
          need to read one column: <strong className="text-ink">the verdict</strong>.
        </p>
      </Section>

      <Section title="Your daily routine">
        <ol className="list-none space-y-3 pl-0">
          {[
            ["Before games — capture PrizePicks.", "Open the PrizePicks projections in your browser, copy the raw data, and save it into data/raw/prizepicks_raw.json. Do this 2–4 hours before kickoff/tip-off, when lineups are out and the books have posted."],
            ["Press “Run everything” on the Update Data tab.", "It downloads bookmaker lines, reads your PrizePicks file, and produces verdicts on Today's Picks. Takes under a minute."],
            ["Bet what says YES.", "MAYBE picks are your judgment call — hover the warning triangle to see why the system hesitated."],
            ["Next morning — press “Grade yesterday.”", "The system looks up real box scores, marks every pick Won or Lost, and your lifetime record updates. This is how the system proves whether it's actually good."],
          ].map(([bold, rest], i) => (
            <li key={bold} className="flex gap-4">
              <span
                className="tnum shrink-0 text-2xl font-bold text-ink-faint"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {i + 1}
              </span>
              <p className="pt-1">
                <strong className="text-ink">{bold}</strong> {rest}
              </p>
            </li>
          ))}
        </ol>
      </Section>

      <Section title="What the verdicts mean">
        <div className="space-y-3">
          <div className="flex items-start gap-3">
            <Badge variant="bet">YES</Badge>
            <p className="text-sm">
              Win chance is 57% or better and nothing looks suspicious. These are the picks worth
              real money.
            </p>
          </div>
          <div className="flex items-start gap-3">
            <Badge variant="maybe">MAYBE</Badge>
            <p className="text-sm">
              The math says profitable (above 54.25%), but either it's a thin edge or there's a
              warning attached — stale data, an injury, or a number the system had to estimate
              rather than verify. Read the warning, then decide.
            </p>
          </div>
          <div className="flex items-start gap-3">
            <Badge variant="skip">SKIP</Badge>
            <p className="text-sm">
              Below break-even. These never even appear on Today's Picks — no pick shown means
              the answer was no.
            </p>
          </div>
        </div>
        <p className="mt-4 rounded-md bg-info-soft px-4 py-3 text-sm text-ink">
          <strong>Why 54.25%?</strong> Because of how PrizePicks pays out, a pick must win more
          than 54.25% of the time to make money long-term. Winning "more than half" is not
          enough — that's the house edge.
        </p>
      </Section>

      <Section title="The warning triangle ⚠ — what each one means">
        <dl className="m-0">
          <Term word="Stale board">
            Your PrizePicks file is older than the bookmaker data. PrizePicks may have already
            changed the line. Re-paste and re-run.
          </Term>
          <Term word="Books disagree">
            The sportsbooks don't agree with each other on this player, which means the market
            hasn't made up its mind. Lower confidence.
          </Term>
          <Term word="Big line gap">
            PrizePicks' number is far from the books' number. Usually that means news broke
            (injury, lineup change) and PrizePicks hasn't caught up — which can be a trap, not a
            gift. Check the news before betting.
          </Term>
          <Term word="Injury report">
            The player is Out, Doubtful, or Questionable. If they sit, the pick refunds — but if
            they play hurt, unders tend to win.
          </Term>
          <Term word="Modeled (1st half)">
            PrizePicks posts soccer picks for the first half only, and no sportsbook offers
            first-half player lines. The win chance is our own estimate (about 45% of a player's
            action happens before halftime). Good math, but not market-verified — that's why
            these never say YES.
          </Term>
          <Term word="Combo">
            A two-player combined pick. We add both players' rates together, but teammates'
            stats rise and fall together in ways the math doesn't fully capture.
          </Term>
        </dl>
      </Section>

      <Section title="Glossary">
        <dl className="m-0">
          <Term word="Line">The number you bet over or under. "24.5 points" — that's the line.</Term>
          <Term word="Win chance">
            Our best estimate of how often this pick wins, built from sportsbook prices with
            their profit margin stripped out.
          </Term>
          <Term word="Edge">
            How far the win chance sits above break-even. "+5%" means a real, if modest,
            advantage. Anything above +3% is good; +10% is rare and worth double-checking.
          </Term>
          <Term word="Push">
            Landing exactly on a whole-number line ("exactly 2 shots" on a 2.0 line). PrizePicks
            refunds the pick — nobody wins.
          </Term>
          <Term word="Drift (Results tab)">
            Whether the bookmakers moved their number toward your pick after you made it. If they
            keep drifting your way, you're beating the market even on nights you lose — the best
            long-term sign there is.
          </Term>
          <Term word="Hit rate">
            Percentage of graded picks that won. Must stay above 54.25% to be making money.
          </Term>
          <Term word="Demons & Goblins">
            PrizePicks' purple/green specials with shifted lines and different payouts. The
            system reads them but won't bet them — PrizePicks doesn't expose their payout math,
            and they're usually priced against you.
          </Term>
          <Term word="API credits">
            Downloading bookmaker lines costs credits from a monthly allowance (about 2–5 per
            game). One update per day is cheap; updating every hour is not. The remaining count
            prints in the run details.
          </Term>
        </dl>
      </Section>

      <Section title="Common questions">
        <Faq q="Why are two terminal windows running?">
          <p>
            The dashboard is two programs: the <strong>brain</strong> (calculates everything, port
            8800) and the <strong>screen</strong> (this website, port 5173). Both must stay
            running. Close them and the site goes blank — nothing is lost, just restart them.
          </p>
        </Faq>
        <Faq q="How do I capture the PrizePicks board?">
          <p>
            Open PrizePicks in your browser with developer tools open (Network tab), find the
            request named <code className="rounded bg-line/60 px-1 font-mono text-xs">projections</code>,
            copy its response, and save it over{" "}
            <code className="rounded bg-line/60 px-1 font-mono text-xs">data/raw/prizepicks_raw.json</code>.
            Then run step 2.
          </p>
        </Faq>
        <Faq q="Why do soccer picks all say MAYBE?">
          <p>
            PrizePicks posts World Cup props as first-half lines, and no sportsbook offers
            first-half player markets to verify against. Our estimate is solid, but the system
            refuses to say YES on a number it can't check against a real market. That's a
            feature.
          </p>
        </Faq>
        <Faq q="My record changed from 70% to 52% — why?">
          <p>
            The old number was double-counting: every pipeline run re-logged the same picks, so
            one winning pick could count as 13 wins. That's fixed — the record now counts each
            pick exactly once. 52.5% is the honest history of the old, simpler system; the
            current verdict engine is what's trying to beat it.
          </p>
        </Faq>
        <Faq q="How do I switch between NBA and World Cup?">
          <p>
            One line in the <code className="rounded bg-line/60 px-1 font-mono text-xs">.env</code>{" "}
            file: <code className="rounded bg-line/60 px-1 font-mono text-xs">ACTIVE_SPORT=world_cup</code>{" "}
            or <code className="rounded bg-line/60 px-1 font-mono text-xs">ACTIVE_SPORT=nba</code>.
            Then run the pipeline again. Old picks from both sports stay in your record.
          </p>
        </Faq>
        <Faq q="When is the best time to run everything?">
          <p>
            2–4 hours before games start. Earlier, the books haven't posted player lines yet
            (especially soccer). Later, lines move fast and your PrizePicks capture goes stale.
            Then grade results the next morning.
          </p>
        </Faq>
        <Faq q="A pick won on PrizePicks but shows Lost here (or vice versa)?">
          <p>
            We grade with ESPN's stats; PrizePicks uses its own provider. They disagree on rare
            borderline calls (was that a shot or a blocked pass?). Trust PrizePicks for your
            money, and treat our record as the system's scoreboard.
          </p>
        </Faq>
        <Faq q="Nothing shows on Today's Picks — is it broken?">
          <p>
            Probably not. If every line was priced below break-even, showing nothing IS the
            answer: no good bets tonight. Check the run details on Update Data — if it says
            "0 picks above break-even," the system did its job. The discipline to not bet is
            where most of the profit lives.
          </p>
        </Faq>
      </Section>

      <p className="rise mb-6 border-t-2 border-ink pt-4 text-xs text-ink-faint">
        Edge Desk · local analysis engine · your data never leaves this computer except to fetch
        public odds and scores.
      </p>
    </div>
  );
}
