export default function ChatPage() {
  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <h1 className="text-2xl font-bold text-gray-900 mb-4">AI 对话</h1>

      {/* 消息区 */}
      <div className="flex-1 bg-white rounded-xl border border-gray-200 flex items-center justify-center mb-4">
        <div className="text-center">
          <div className="w-12 h-12 bg-gray-100 rounded-xl flex items-center justify-center mx-auto mb-3">
            <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
              />
            </svg>
          </div>
          <p className="text-sm text-gray-500">开始与 AI 对话，分析市场动态</p>
        </div>
      </div>

      {/* 输入区（UI 骨架，暂不接 API） */}
      <div className="bg-white rounded-xl border border-gray-200 p-3 flex gap-3 flex-shrink-0">
        <input
          type="text"
          placeholder="输入你的问题..."
          disabled
          className="flex-1 text-sm text-gray-700 outline-none bg-transparent placeholder:text-gray-400 disabled:cursor-not-allowed"
        />
        <button
          disabled
          className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg disabled:opacity-40 transition-colors"
        >
          发送
        </button>
      </div>
    </div>
  )
}
