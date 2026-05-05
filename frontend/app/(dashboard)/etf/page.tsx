export default function ETFPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">ETF 资金流</h1>

      <div className="bg-white rounded-xl border border-gray-200 p-12 flex flex-col items-center justify-center text-center">
        <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center mb-4">
          <svg className="w-6 h-6 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            />
          </svg>
        </div>
        <h2 className="text-base font-semibold text-gray-900 mb-2">ETF 资金流数据</h2>
        <p className="text-sm text-gray-500">功能即将上线，敬请期待</p>
      </div>
    </div>
  )
}
