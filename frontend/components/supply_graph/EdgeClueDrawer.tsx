"use client";

import type { SupplyEdge, SupplyNode } from "@/lib/api/supplyGraph";

type ProductDetail = {
  short_name?: string;
  full_name?: string;
  full_name_zh?: string;
  description?: string;
  description_zh?: string;
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
    return String(values.name_zh || values.name || values.ticker || fallback);
  };
  const sourceName = nodeName(sourceNode, edge.srcId);
  const targetName = nodeName(targetNode, edge.dstId);
  const relationshipDescription = String(
    properties.relationship_description_zh ||
      properties.rationale ||
      `${sourceName}向${targetName}提供上述产品，这些产品构成两家公司之间的直接业务与供应链联系。`,
  );
  const relationshipDescriptionEn = String(
    properties.relationship_description || "",
  );
  return (
    <aside className="absolute right-0 top-0 z-40 h-full w-full overscroll-contain overflow-auto border-l bg-white p-5 shadow-2xl sm:w-[500px]">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="font-semibold">产品与证据详情</h2>
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
        {relationshipDescriptionEn && (
          <p className="mt-2 border-t pt-2 text-xs leading-5 text-slate-500">
            {relationshipDescriptionEn}
          </p>
        )}
      </section>
      <section className="mb-6">
        <h3 className="mb-3 text-sm font-semibold text-slate-800">供应产品</h3>
        <div className="space-y-3">
          {products.map((product, index) => (
            <article
              key={`${product.short_name}-${index}`}
              className="rounded-xl border border-blue-100 bg-blue-50/50 p-4"
            >
              <div className="flex items-start gap-2">
                <span className="shrink-0 rounded-md bg-blue-600 px-2 py-1 text-xs font-bold text-white">
                  {product.short_name || "产品"}
                </span>
                <div className="min-w-0">
                  <h4 className="font-medium text-slate-900">
                    {product.full_name_zh || product.full_name}
                  </h4>
                  {product.full_name && product.full_name_zh && (
                    <p className="mt-0.5 break-words text-xs text-slate-500">
                      {product.full_name}
                    </p>
                  )}
                </div>
              </div>
              <p className="mt-3 break-words text-sm leading-6 text-slate-700">
                {product.description_zh || product.description}
              </p>
              {product.description && product.description_zh && (
                <p className="mt-2 break-words border-t border-blue-100 pt-2 text-xs leading-5 text-slate-500">
                  {product.description}
                </p>
              )}
            </article>
          ))}
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
