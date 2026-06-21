import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, RefreshCw, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import {
  api,
  type PortfolioConnector,
  type PortfolioOrder,
  type PortfolioOrderRequest,
  type PortfolioSummary,
} from "@/lib/api";

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});
const number = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const pct = (value: number) => `${(value * 100).toFixed(2)}%`;

function MetricCard({ label, value, detail, positive }: {
  label: string;
  value: string;
  detail?: string;
  positive?: boolean;
}) {
  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${positive === undefined ? "" : positive ? "text-success" : "text-danger"}`}>
        {value}
      </p>
      {detail && <p className="mt-1 text-xs text-muted-foreground">{detail}</p>}
    </div>
  );
}

export function Portfolio() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [connectors, setConnectors] = useState<PortfolioConnector[]>([]);
  const [orders, setOrders] = useState<PortfolioOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [ticket, setTicket] = useState<PortfolioOrderRequest>({
    symbol: "",
    side: "buy",
    quantity: 1,
    order_type: "market",
    product: "delivery",
    execution_mode: "simulated",
  });

  const paperTradeConnectors = useMemo(
    () => connectors.filter((item) => item.environment === "paper" && !item.readonly && item.capabilities.includes("orders.place")),
    [connectors],
  );

  const load = async () => {
    setLoading(true);
    try {
      const [portfolio, connectorData, orderData] = await Promise.all([
        api.getPortfolioSummary(),
        api.getPortfolioConnectors(),
        api.listPortfolioOrders(),
      ]);
      setSummary(portfolio);
      setConnectors(connectorData.connectors);
      setOrders(orderData.orders);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load portfolio");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const submitOrder = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      const order = await api.createPortfolioOrder({
        ...ticket,
        symbol: ticket.symbol.trim().toUpperCase(),
        connector_profile: ticket.execution_mode === "connector_paper" ? ticket.connector_profile : undefined,
        limit_price: ticket.order_type === "limit" ? ticket.limit_price : undefined,
      });
      setOrders((current) => [order, ...current]);
      toast.success("Paper order recorded");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Order was rejected");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading && !summary) {
    return <div className="flex h-full items-center justify-center text-muted-foreground">Loading portfolio...</div>;
  }
  if (!summary) {
    return <div className="p-8 text-muted-foreground">Portfolio data is unavailable.</div>;
  }

  const { metrics } = summary;
  return (
    <div className="mx-auto max-w-[1500px] space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">India Equities</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">Portfolio Studio</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Workbook as of {new Date(summary.as_of).toLocaleString("en-IN")}
          </p>
        </div>
        <button onClick={() => void load()} className="flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm hover:bg-muted">
          <RefreshCw className="h-4 w-4" /> Refresh workbook
        </button>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Market value" value={inr.format(metrics.market_value)} detail={`${metrics.positions} positions`} />
        <MetricCard label="Invested" value={inr.format(metrics.invested_value)} />
        <MetricCard label="Total P&L" value={inr.format(metrics.total_pnl)} detail={pct(metrics.total_pnl_pct)} positive={metrics.total_pnl >= 0} />
        <MetricCard label="Day P&L" value={inr.format(metrics.day_pnl)} detail={pct(metrics.day_pnl_pct)} positive={metrics.day_pnl >= 0} />
        <MetricCard label="Top weight" value={pct(metrics.top_position_weight)} detail={`HHI ${metrics.concentration_hhi.toFixed(3)}`} />
      </div>

      {summary.risk_flags.length > 0 && (
        <section className="grid gap-3 lg:grid-cols-3">
          {summary.risk_flags.map((flag) => (
            <div key={`${flag.title}-${flag.detail}`} className="rounded-lg border border-warning/30 bg-warning/5 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold"><AlertTriangle className="h-4 w-4 text-warning" />{flag.title}</div>
              <p className="mt-2 text-sm text-muted-foreground">{flag.detail}</p>
            </div>
          ))}
        </section>
      )}

      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <section className="overflow-hidden rounded-xl border bg-card">
          <div className="border-b px-5 py-4"><h2 className="font-semibold">Holdings and allocation</h2></div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Instrument</th><th className="px-4 py-3 text-right">Qty</th>
                  <th className="px-4 py-3 text-right">Avg cost</th><th className="px-4 py-3 text-right">LTP</th>
                  <th className="px-4 py-3 text-right">Market value</th><th className="px-4 py-3 text-right">P&L</th>
                  <th className="px-4 py-3">Weight</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {summary.holdings.map((holding) => (
                  <tr key={holding.symbol} className="hover:bg-muted/30">
                    <td className="px-4 py-3 font-semibold">{holding.symbol}</td>
                    <td className="px-4 py-3 text-right">{number.format(holding.quantity)}</td>
                    <td className="px-4 py-3 text-right">{inr.format(holding.average_cost)}</td>
                    <td className="px-4 py-3 text-right">{inr.format(holding.ltp)}</td>
                    <td className="px-4 py-3 text-right">{inr.format(holding.market_value)}</td>
                    <td className={`px-4 py-3 text-right font-medium ${holding.total_pnl >= 0 ? "text-success" : "text-danger"}`}>
                      <span className="inline-flex items-center gap-1">
                        {holding.total_pnl >= 0 ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
                        {inr.format(holding.total_pnl)} ({pct(holding.total_pnl_pct)})
                      </span>
                    </td>
                    <td className="min-w-36 px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                          <div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(2, holding.weight * 100)}%` }} />
                        </div>
                        <span className="w-14 text-right text-xs">{pct(holding.weight)}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="space-y-6">
          <form onSubmit={submitOrder} className="space-y-4 rounded-xl border bg-card p-5">
            <div>
              <div className="flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-success" /><h2 className="font-semibold">Paper trade ticket</h2></div>
              <p className="mt-1 text-xs text-muted-foreground">Live order execution is disabled. Dhan and Shoonya are limited to local paper simulation.</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs text-muted-foreground">Symbol<input required value={ticket.symbol} onChange={(e) => setTicket({ ...ticket, symbol: e.target.value })} className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm uppercase" /></label>
              <label className="text-xs text-muted-foreground">Quantity<input required min={1} type="number" value={ticket.quantity} onChange={(e) => setTicket({ ...ticket, quantity: Number(e.target.value) })} className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm" /></label>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs text-muted-foreground">Side<select value={ticket.side} onChange={(e) => setTicket({ ...ticket, side: e.target.value as "buy" | "sell" })} className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"><option value="buy">Buy</option><option value="sell">Sell</option></select></label>
              <label className="text-xs text-muted-foreground">Order type<select value={ticket.order_type} onChange={(e) => setTicket({ ...ticket, order_type: e.target.value as "market" | "limit" })} className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"><option value="market">Market</option><option value="limit">Limit</option></select></label>
            </div>
            {ticket.order_type === "limit" && <label className="block text-xs text-muted-foreground">Limit price<input required min={0.01} step="0.01" type="number" value={ticket.limit_price ?? ""} onChange={(e) => setTicket({ ...ticket, limit_price: Number(e.target.value) })} className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm" /></label>}
            <label className="block text-xs text-muted-foreground">Execution<select value={ticket.execution_mode} onChange={(e) => setTicket({ ...ticket, execution_mode: e.target.value as "simulated" | "connector_paper", connector_profile: undefined })} className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"><option value="simulated">Local simulation</option><option value="connector_paper">Dhan / Shoonya paper connector</option></select></label>
            {ticket.execution_mode === "connector_paper" && <label className="block text-xs text-muted-foreground">Paper connector<select required value={ticket.connector_profile ?? ""} onChange={(e) => setTicket({ ...ticket, connector_profile: e.target.value })} className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"><option value="">Select connector</option>{paperTradeConnectors.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>}
            <button disabled={submitting} className={`w-full rounded-md px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50 ${ticket.side === "buy" ? "bg-success" : "bg-danger"}`}>{submitting ? "Submitting..." : `Record paper ${ticket.side}`}</button>
          </form>

          <section className="rounded-xl border bg-card p-5">
            <h2 className="font-semibold">Recent paper orders</h2>
            <div className="mt-3 space-y-3">
              {orders.length === 0 && <p className="text-sm text-muted-foreground">No paper orders recorded.</p>}
              {orders.slice(0, 8).map((order) => (
                <div key={order.id} className="flex items-center justify-between rounded-md bg-muted/40 p-3 text-sm">
                  <div><p className="font-semibold">{order.side.toUpperCase()} {order.symbol}</p><p className="text-xs text-muted-foreground">{new Date(order.created_at).toLocaleString("en-IN")}</p></div>
                  <div className="text-right"><p>{number.format(order.quantity)} qty</p><p className="text-xs text-muted-foreground">{order.execution_mode.replace("_", " ")}</p></div>
                </div>
              ))}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
