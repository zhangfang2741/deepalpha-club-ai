"use client";

import { useState } from "react";
import type { GroupedRelation } from "./SupplyGraphGrouping";

const propertiesOf = (properties: { name: string; value: unknown }[]) =>
  Object.fromEntries(properties.map((property) => [property.name, property.value]));

const displayValue = (value: unknown) => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
};

const confidencePercent = (value: unknown) => {
  const confidence = Number(value || 0);
  return confidence > 0 && confidence <= 1
    ? Math.round(confidence * 100)
    : Math.round(confidence);
};

export default function GroupedRelationDrawer({
  group,
  onClose,
}: {
  group: GroupedRelation | null;
  onClose: () => void;
}) {
  const [activeIndex, setActiveIndex] = useState(0);
  if (!group) return null;
  const active = group.items[Math.min(activeIndex, group.items.length - 1)];
  const nodeProperties = propertiesOf(active.node.properties);
  const edgeProperties = propertiesOf(active.edge.properties);
  const companyName = String(
    nodeProperties.name_zh ||
      nodeProperties.name ||
      nodeProperties.ticker ||
      active.node.nodeId,
  );
  const product = String(
    edgeProperties.product_text || edgeProperties.product || "产品信息未披露",
  );
  const description = String(
    edgeProperties.relationship_description_zh ||
      edgeProperties.rationale ||
      "暂无进一步关系说明",
  );
  const confidence = confidencePercent(edgeProperties.confidence);
  const title = group.kind === "supplier" ? "低置信度供应商" : "低置信度客户";

  return (
    <aside className="absolute right-0 top-0 z-50 flex h-full w-full flex-col overflow-hidden border-l bg-white shadow-2xl sm:w-[540px]">
      <div className="flex shrink-0 items-center justify-between border-b px-5 py-4">
        <div>
          <h2 className="font-semibold text-slate-900">{title}</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            共 {group.items.length} 条关系，选择公司查看完整信息
          </p>
        </div>
        <button
          type="button"
          aria-label="关闭聚合关系详情"
          onClick={onClose}
          className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-full text-lg text-slate-600 hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-blue-500"
        >
          ✕
        </button>
      </div>

      <div
        role="tablist"
        aria-label="聚合关系公司"
        className="flex shrink-0 gap-2 overflow-x-auto border-b bg-slate-50 px-4 py-3"
      >
        {group.items.map(({ node }, index) => {
          const properties = propertiesOf(node.properties);
          const label = String(
            properties.ticker || properties.name_zh || properties.name || node.nodeId,
          );
          return (
            <button
              key={node.nodeId}
              type="button"
              role="tab"
              aria-selected={index === activeIndex}
              onClick={() => setActiveIndex(index)}
              className={`shrink-0 cursor-pointer rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 ${
                index === activeIndex
                  ? "bg-blue-600 text-white shadow-sm"
                  : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-100"
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
        <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-medium text-slate-500">当前企业</p>
              <h3 className="mt-1 text-lg font-semibold text-slate-900">
                {companyName}
              </h3>
              {nodeProperties.ticker ? (
                <p className="text-sm text-slate-500">{String(nodeProperties.ticker)}</p>
              ) : null}
            </div>
            <span className="rounded-full bg-amber-100 px-3 py-1.5 text-sm font-semibold text-amber-800">
              置信度 {confidence}%
            </span>
          </div>
        </section>

        <section className="rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
          <p className="text-xs font-medium text-blue-600">供应产品 / 服务</p>
          <p className="mt-2 whitespace-pre-wrap break-words text-base font-medium leading-7 text-slate-900">
            {product}
          </p>
        </section>

        <section>
          <h3 className="text-sm font-semibold text-slate-800">关系说明</h3>
          <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-7 text-slate-700">
            {description}
          </p>
        </section>

        <details className="rounded-2xl border border-slate-200 bg-white p-4">
          <summary className="cursor-pointer text-sm font-semibold text-slate-800">
            查看全部原始字段
          </summary>
          <div className="mt-4 space-y-5">
            <section>
              <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
                关系字段
              </h4>
              <dl className="space-y-3">
                {active.edge.properties.map((property) => (
                  <div key={property.name} className="border-b border-slate-100 pb-3 last:border-0 last:pb-0">
                    <dt className="text-xs font-medium text-slate-500">{property.name}</dt>
                    <dd className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-slate-800">
                      {displayValue(property.value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
            <section>
              <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
                企业字段
              </h4>
              <dl className="space-y-3">
                {active.node.properties.map((property) => (
                  <div key={property.name} className="border-b border-slate-100 pb-3 last:border-0 last:pb-0">
                    <dt className="text-xs font-medium text-slate-500">{property.name}</dt>
                    <dd className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-slate-800">
                      {displayValue(property.value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          </div>
        </details>
      </div>
    </aside>
  );
}
