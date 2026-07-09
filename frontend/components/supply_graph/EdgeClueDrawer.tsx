"use client";

import type { SupplyEdge, SupplyNode } from "@/lib/api/supplyGraph";

type ProductDetail = {
  short_name?: string;
  full_name?: string;
  full_name_zh?: string;
  description?: string;
  description_zh?: string;
};

const COMPANY_ZH_BY_TICKER: Record<string, string> = {
  NVDA: "英伟达",
  TSLA: "特斯拉",
  AAPL: "苹果公司",
  MSFT: "微软公司",
  AMZN: "亚马逊公司",
  META: "元宇宙平台公司",
  GOOGL: "字母表公司（谷歌）",
  GOOG: "字母表公司（谷歌）",
  TSM: "台积电",
  DELL: "戴尔科技",
  HPE: "慧与公司",
  AMKR: "安靠科技",
  SSNLF: "三星电子",
};

const hasChinese = (value?: unknown) => /[\u4e00-\u9fff]/.test(String(value || ""));

const knownProductCode = (value?: unknown) => {
  const text = String(value || "");
  const codes = text.match(
    /\b(HBM\d*[A-Z]?|H\d{3}|B\d{3}|L\d{2}|EUV|GPU|CPU|CoWoS|DDR\d?|GDDR\d?|ASIC|TPU|EC2|AWS)\b/gi,
  );
  if (!codes?.length) return "产品";
  return [...new Set(codes.map((code) => code.toUpperCase()))].join(" / ");
};

const productNameZh = (product: ProductDetail) => {
  if (hasChinese(product.full_name_zh)) return String(product.full_name_zh);
  const fullName = String(product.full_name || product.short_name || "产品");
  if (/data\s*center.*gpu|gpu.*data\s*center/i.test(fullName)) {
    const codes = knownProductCode(fullName)
      .split(" / ")
      .filter((code) => !["GPU", "AWS", "EC2"].includes(code));
    const codeText = codes.length ? `（${codes.join("、")}）` : "";
    return `数据中心 GPU${codeText}`;
  }
  if (/hbm|gddr|memory/i.test(fullName)) return `高性能显存与 GPU 内存产品（${knownProductCode(fullName)}）`;
  if (/advanced\s*node|semiconductor|foundry|wafer/i.test(fullName)) return "先进制程晶圆代工服务";
  if (/pre-?built|workstation|server|enterprise/i.test(fullName)) return "企业级 AI 服务器与工作站";
  return `供应产品（${knownProductCode(fullName)}）`;
};

const productDescriptionZh = (
  product: ProductDetail,
  sourceName: string,
  targetName: string,
  relationshipDescription: string,
) => {
  if (hasChinese(product.description_zh)) return String(product.description_zh);
  return `该产品是${sourceName}与${targetName}之间的核心业务连接点。${relationshipDescription}`;
};

export default function EdgeClueDrawer({
  edge,
  sourceNode,
  targetNode,
  clues,
  onClose,
}: {
  edge: SupplyEdge | null;
  sourceNode: SupplyNode | null;
  targetNode: SupplyNode | null;
  clues: Record<string, unknown>[];
  onClose: () => void;
}) {
  if (!edge) return null;
  const properties = Object.fromEntries(
    edge.properties.map((property) => [property.name, property.value]),
  );
  const products: ProductDetail[] =
    Array.isArray(properties.products) && properties.products.length
      ? (properties.products as ProductDetail[])
      : [
          {
            short_name: String(properties.product || "产品"),
            full_name_zh: String(
              properties.product_text || properties.product || "产品信息未披露",
            ),
            description_zh: String(properties.rationale || "暂无进一步说明"),
          },
        ];
  const nodeName = (node: SupplyNode | null, fallback: string) => {
    if (!node) return fallback;
    const values = Object.fromEntries(
      node.properties.map((property) => [property.name, property.value]),
    );
    const ticker = String(values.ticker || node.nodeId || fallback).toUpperCase();
    return String(
      values.name_zh ||
        COMPANY_ZH_BY_TICKER[ticker] ||
        values.name ||
        values.ticker ||
        fallback,
    );
  };
  const sourceName = nodeName(sourceNode, edge.srcId);
  const targetName = nodeName(targetNode, edge.dstId);
  const relationshipDescription = String(
    (hasChinese(properties.relationship_description_zh)
      ? properties.relationship_description_zh
      : "") ||
      (hasChinese(properties.rationale) ? properties.rationale : "") ||
      `${sourceName}向${targetName}提供上述产品，这些产品构成两家公司之间的直接业务与供应链联系。`,
  );
  return (
    <aside className="absolute right-0 top-0 z-40 h-full w-full overscroll-contain overflow-auto border-l bg-white p-5 shadow-2xl sm:w-[500px]">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="font-semibold">关系明细</h2>
        <button
          aria-label="关闭产品详情"
          className="cursor-pointer rounded-lg px-2 py-1 hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-blue-500"
          onClick={onClose}
        >
          ✕
        </button>
      </div>
      <section className="mb-6 rounded-xl border border-slate-200 bg-slate-50 p-4">
        <p className="text-xs font-medium text-slate-500">关联企业</p>
        <div className="mt-2 flex items-center gap-2 font-medium text-slate-900">
          <span>{sourceName}</span>
          <span className="text-blue-500">→</span>
          <span>{targetName}</span>
        </div>
        <p className="mt-3 text-sm leading-6 text-slate-700">
          {relationshipDescription}
        </p>
      </section>
      <section className="mb-6">
        <h3 className="mb-3 text-sm font-semibold text-slate-800">供应产品</h3>
        <div className="space-y-3">
          {products.map((product, index) => {
            const nameZh = productNameZh(product);
            const descriptionZh = productDescriptionZh(
              product,
              sourceName,
              targetName,
              relationshipDescription,
            );
            return (
              <article
                key={`${product.short_name}-${index}`}
                className="rounded-xl border border-blue-100 bg-blue-50/50 p-4"
              >
              <div className="flex min-w-0 flex-col items-start gap-2">
                <span className="shrink-0 rounded-md bg-blue-600 px-2 py-1 text-xs font-bold text-white">
                  {knownProductCode(product.short_name || product.full_name)}
                </span>
                <div className="min-w-0 max-w-full">
                  <h4 className="break-words text-base font-medium leading-6 text-slate-900">
                    {nameZh}
                  </h4>
                  {product.full_name && hasChinese(product.full_name_zh) && (
                    <p className="mt-0.5 break-words text-xs text-slate-500">
                      {product.full_name}
                    </p>
                  )}
                </div>
              </div>
              <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">
                {descriptionZh}
              </p>
              {product.description && hasChinese(product.description_zh) && (
                <p className="mt-2 break-words border-t border-blue-100 pt-2 text-xs leading-5 text-slate-500">
                  {product.description}
                </p>
              )}
            </article>
            );
          })}
        </div>
      </section>
      <section>
        <h3 className="mb-3 text-sm font-semibold text-slate-800">证据线索</h3>
        {clues.length ? (
          clues.map((clue, index) => (
            <article key={index} className="mb-3 rounded-xl border p-3 text-sm">
              <span className="rounded bg-slate-100 px-2 py-1 text-xs">
                {String(clue.stance)}
              </span>
              <p className="mt-2 break-words leading-6">
                {String(clue.snippet_text)}
              </p>
            </article>
          ))
        ) : (
          <p className="text-sm text-slate-500">暂无证据线索</p>
        )}
      </section>
    </aside>
  );
}
