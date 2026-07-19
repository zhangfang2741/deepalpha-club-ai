"use client";

import type { SupplyNode } from "@/lib/api/supplyGraph";

const propertiesOf = (node: SupplyNode) =>
  Object.fromEntries(
    node.properties.map((property) => [property.name, property.value]),
  );

export default function CompanyResearchDrawer({
  node,
  onClose,
}: {
  node: SupplyNode | null;
  onClose: () => void;
}) {
  if (!node) return null;
  const properties = propertiesOf(node);
  const storedTicker = String(properties.ticker || "")
    .trim()
    .toUpperCase();
  const nodeIdTicker = node.nodeId.toUpperCase();
  const ticker =
    storedTicker ||
    (/^[A-Z0-9.-]{1,12}$/.test(nodeIdTicker) ? nodeIdTicker : "");
  const companyName = String(
    properties.name_zh || properties.name || ticker || node.nodeId,
  );

  return (
    <aside className="absolute right-0 top-0 z-40 flex h-full w-full flex-col overflow-hidden border-l bg-white shadow-2xl sm:w-[560px]">
      <button
        type="button"
        aria-label="关闭企业研究"
        className="absolute right-4 top-4 z-10 flex h-9 w-9 cursor-pointer items-center justify-center rounded-full border border-slate-200 bg-white/95 text-lg text-slate-600 shadow-sm backdrop-blur-sm hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-blue-500"
        onClick={onClose}
      >
        ✕
      </button>
      {ticker ? (
        <iframe
          src={`/company-research?symbol=${encodeURIComponent(ticker)}&embedded=1`}
          title={`${companyName} 企业研究`}
          className="min-h-0 flex-1 border-0"
        />
      ) : (
        <div className="flex flex-1 items-center justify-center p-8 text-center text-sm text-slate-500">
          该企业暂无可用于深度研究的股票代码。
        </div>
      )}
    </aside>
  );
}
