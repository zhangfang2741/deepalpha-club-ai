import AuthGuard from '@/components/auth/AuthGuard'
import TopNav from '@/components/layout/TopNav'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="min-h-screen bg-gray-50 flex flex-col">
        <TopNav />
        <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8">
          {children}
        </main>
      </div>
    </AuthGuard>
  )
}
