import { useState, type FormEvent, type KeyboardEvent } from "react";

import {
  AnalystPanel,
  DividendsPanel,
  EarningsPanel,
  ProfitabilityPanel,
  ValuationPanel,
} from "./CompanyDataPanels";
import { displayCurrency, displayPercent } from "./companyFormat";
import type { Overview, Tab } from "./companyTypes";
import { tabs } from "./companyTypes";
import { NewsPanel, StatementsPanel, TechnicalsPanel } from "./CompanyResearchPanels";
import { useCompanyData } from "./useCompanyData";

export function CompanyPage() {
  const [tickerInput, setTickerInput] = useState("AAPL");
  const [ticker, setTicker] = useState("AAPL");
  const [tab, setTab] = useState<Tab>("valuation");
  const overview = useCompanyData<Overview>(`companies/${ticker}/overview`);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextTicker = tickerInput.trim().toUpperCase();
    if (nextTicker) setTicker(nextTicker);
  }

  function moveTab(event: KeyboardEvent<HTMLButtonElement>, current: Tab) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const currentIndex = tabs.findIndex((item) => item.id === current);
    const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    const nextTab = tabs[nextIndex].id;
    setTab(nextTab);
    document.getElementById(`company-tab-${nextTab}`)?.focus();
  }

  return <main className="shell company-shell">
    <header className="company-header">
      <div>
        <p className="eyebrow">Company deep dive</p>
        <h1>{overview.data?.name ?? ticker} <span>({ticker})</span></h1>
        <p className="lede">{overview.data?.sector ?? "—"} · {overview.data?.industry ?? "—"} · {overview.data?.currency ?? "—"}</p>
      </div>
      <form className="ticker-form" onSubmit={submit}>
        <label htmlFor="company-ticker">Ticker<input id="company-ticker" value={tickerInput} onChange={(event) => setTickerInput(event.target.value)} spellCheck="false" autoCapitalize="characters" /></label>
        <button type="submit">Load company</button>
      </form>
    </header>
    {overview.error && <p className="notice error" role="alert">{overview.error}</p>}
    {overview.loading ? <div className="skeleton company-summary" aria-busy="true">Loading company summary…</div> : <CompanySummary overview={overview.data} />}
    <div className="tabs company-tabs" role="tablist" aria-label="Company analysis">
      {tabs.map(({ id, label }) => <button id={`company-tab-${id}`} type="button" role="tab" aria-selected={tab === id} aria-controls={`company-panel-${id}`} className={tab === id ? "is-selected" : ""} key={id} onClick={() => setTab(id)} onKeyDown={(event) => moveTab(event, id)}>{label}</button>)}
    </div>
    <div id={`company-panel-${tab}`} role="tabpanel" aria-labelledby={`company-tab-${tab}`} tabIndex={0}>
      {tab === "valuation" && <ValuationPanel ticker={ticker} overview={overview.data} />}
      {tab === "profitability" && <ProfitabilityPanel ticker={ticker} overview={overview.data} />}
      {tab === "analyst" && <AnalystPanel ticker={ticker} overview={overview.data} />}
      {tab === "earnings" && <EarningsPanel ticker={ticker} overview={overview.data} />}
      {tab === "dividends" && <DividendsPanel ticker={ticker} overview={overview.data} />}
      {tab === "statements" && <StatementsPanel ticker={ticker} />}
      {tab === "news" && <NewsPanel ticker={ticker} />}
      {tab === "technicals" && <TechnicalsPanel ticker={ticker} />}
    </div>
  </main>;
}

function CompanySummary({ overview }: { overview: Overview | null }) {
  if (!overview) return null;
  return <section className="metrics company-summary" aria-label="Company summary">
    <SummaryMetric label="Price" value={displayCurrency(overview.price, overview.currency)} hint={overview.pct_1d === undefined ? undefined : displayPercent(overview.pct_1d, 2)} />
    <SummaryMetric label="Market cap" value={overview.mktcap_b === undefined ? "—" : `${overview.mktcap_b.toFixed(1)}B`} />
    <SummaryMetric label="Sector" value={overview.sector ?? "—"} />
    <SummaryMetric label="Next period end" value={overview.next_period_end ?? "—"} />
    <SummaryMetric label="Reporting currency" value={overview.currency ?? "—"} />
  </section>;
}

function SummaryMetric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong>{hint && <small>{hint}</small>}</div>;
}
