'use client'

import type { EntityType, RelationType } from '@/lib/api/supply_chain'

export const ENTITY_COLORS: Record<EntityType, string> = {
  Company: '#3B82F6',
  Product: '#10B981',
  Technology: '#8B5CF6',
  Concept: '#F59E0B',
  Resource: '#EF4444',
}

export const ENTITY_BG: Record<EntityType, string> = {
  Company: 'bg-blue-100 text-blue-800 border-blue-300',
  Product: 'bg-emerald-100 text-emerald-800 border-emerald-300',
  Technology: 'bg-purple-100 text-purple-800 border-purple-300',
  Concept: 'bg-amber-100 text-amber-800 border-amber-300',
  Resource: 'bg-red-100 text-red-800 border-red-300',
}

export const RELATION_COLORS: Record<RelationType, string> = {
  HAS_PRODUCT: '#3B82F6',
  SUPPLIED_BY: '#10B981',
  ENABLED_BY: '#8B5CF6',
  CONSTRAINED_BY: '#EF4444',
}

export const RELATION_LABELS: Record<RelationType, string> = {
  HAS_PRODUCT: '拥有产品',
  SUPPLIED_BY: '由…供应',
  ENABLED_BY: '依赖于',
  CONSTRAINED_BY: '受限于',
}

export function EntityTypeBadge({ type }: { type: EntityType }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${ENTITY_BG[type]}`}>
      {type}
    </span>
  )
}

export function RelationBadge({ type }: { type: RelationType }) {
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium text-white"
      style={{ backgroundColor: RELATION_COLORS[type] }}
    >
      {RELATION_LABELS[type]}
    </span>
  )
}

export default function GraphLegend() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">图例</p>

      <div>
        <p className="text-xs text-gray-400 mb-1.5">实体类型</p>
        <div className="flex flex-wrap gap-1.5">
          {(Object.entries(ENTITY_COLORS) as [EntityType, string][]).map(([type, color]) => (
            <div key={type} className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
              <span className="text-xs text-gray-600">{type}</span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <p className="text-xs text-gray-400 mb-1.5">关系类型</p>
        <div className="space-y-1">
          {(Object.entries(RELATION_LABELS) as [RelationType, string][]).map(([type, label]) => (
            <div key={type} className="flex items-center gap-2">
              <div className="w-6 h-0.5 flex-shrink-0" style={{ backgroundColor: RELATION_COLORS[type] }} />
              <span className="text-xs text-gray-500">{type}</span>
              <span className="text-xs text-gray-400">({label})</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
