'use client'
import { useSearchParams, useRouter } from 'next/navigation'
import { Suspense, useEffect } from 'react'
import dynamic from 'next/dynamic'
import { useSkillsStore } from '@/lib/store/skills'
import DashboardShell from '@/components/layout/DashboardShell'

const GalleryView = dynamic(() => import('./_components/GalleryView').then(m => ({ default: m.GalleryView })), { ssr: false })
const MineView = dynamic(() => import('./_components/MineView').then(m => ({ default: m.MineView })), { ssr: false })
const NewView = dynamic(() => import('./_components/NewView').then(m => ({ default: m.NewView })), { ssr: false })
const DetailPage = dynamic(() => import('./_components/DetailPage').then(m => ({ default: m.DetailPage })), { ssr: false })

function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
        active ? 'bg-primary text-white' : 'text-gray-500 hover:bg-gray-100'
      }`}
    >
      {label}
    </button>
  )
}

function SkillGeneratorContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const { activeTab, selectedSkillId, setActiveTab } = useSkillsStore()

  const tabParam = (searchParams.get('tab') as 'gallery' | 'mine' | 'new') || 'gallery'

  useEffect(() => {
    if (tabParam !== activeTab) setActiveTab(tabParam)
  }, [tabParam, activeTab, setActiveTab])

  const switchTab = (tab: 'gallery' | 'mine' | 'new') => {
    router.replace(`/skill-generator?tab=${tab}`)
    setActiveTab(tab)
  }

  return (
    <div className="h-full flex flex-col">
      <div className="border-b border-gray-200 bg-white px-6 py-3 flex gap-1 flex-shrink-0">
        <TabButton label="案例馆" active={activeTab === 'gallery'} onClick={() => switchTab('gallery')} />
        <TabButton label="我的因子" active={activeTab === 'mine'} onClick={() => switchTab('mine')} />
        <TabButton label="新建" active={activeTab === 'new'} onClick={() => switchTab('new')} />
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-6">
        {activeTab === 'gallery' && <GalleryView />}
        {activeTab === 'mine' && <MineView />}
        {activeTab === 'new' && <NewView />}
      </div>
      {selectedSkillId && <DetailPage />}
    </div>
  )
}

export default function SkillGeneratorPage() {
  return (
    <Suspense>
      <DashboardShell>
        <SkillGeneratorContent />
      </DashboardShell>
    </Suspense>
  )
}