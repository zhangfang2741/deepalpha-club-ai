import AuthGuard from '@/components/auth/AuthGuard'
import TopNav from '@/components/layout/TopNav'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="min-h-screen bg-background flex flex-col relative overflow-hidden">
        {/* Subtle background decoration */}
        <div className="absolute top-0 right-0 -z-10 w-[500px] h-[500px] bg-blue-50/50 rounded-full blur-3xl translate-x-1/2 -translate-y-1/2" />
        <div className="absolute bottom-0 left-0 -z-10 w-[400px] h-[400px] bg-blue-50/30 rounded-full blur-3xl -translate-x-1/2 translate-y-1/2" />
        
        <TopNav />
        <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8 relative">
          {children}
        </main>
      </div>
    </AuthGuard>
  )
}
