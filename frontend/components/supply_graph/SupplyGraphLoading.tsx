const SATELLITE_NODES = [
  [48, 115], [34, 180], [88, 92], [118, 126],
  [170, 85], [164, 202], [232, 80], [252, 194],
  [326, 54], [404, 62], [398, 154], [302, 86],
  [516, 44], [526, 104], [458, 32], [454, 130],
] as const;

export default function SupplyGraphLoading() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="正在加载图谱"
      className="flex h-full min-h-[420px] items-center justify-center bg-[#edf3ff]"
    >
      <div className="w-full max-w-xl px-8">
        <svg
          viewBox="0 0 560 260"
          aria-hidden="true"
          className="h-auto w-full overflow-visible"
        >
          <g fill="none" stroke="#cbd5e1" strokeWidth="1.5">
            <path d="M72 155 48 115M72 155 34 180M72 155 88 92M72 155 118 126" />
            <path d="M206 150 170 85M206 150 164 202M206 150 232 80M206 150 252 194" />
            <path d="M355 112 326 54M355 112 404 62M355 112 398 154M355 112 302 86" />
            <path d="M478 74 516 44M478 74 526 104M478 74 458 32M478 74 454 130" />
          </g>

          <g fill="#b8c5d8">
            {SATELLITE_NODES.map(([cx, cy]) => (
              <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="3.5" />
            ))}
          </g>

          <g fill="none" stroke="#9fb2cc" strokeDasharray="7 7" strokeWidth="1.5">
            <circle cx="104" cy="145" r="56" />
            <circle cx="330" cy="125" r="72" />
            <circle cx="478" cy="77" r="48" />
          </g>

          <path
            d="M48 184 106 140 206 164 287 113 365 72 478 76"
            fill="none"
            stroke="#dbe7f7"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="7"
          />
          <path
            d="M48 184 106 140 206 164 287 113 365 72 478 76"
            fill="none"
            stroke="#2f80ed"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="3.5"
            className="graph-loading-flow"
          />

          <g fill="#2f80ed">
            <circle cx="106" cy="140" r="6" />
            <circle cx="206" cy="164" r="6" />
            <circle cx="287" cy="113" r="6" />
            <circle cx="365" cy="72" r="6" />
          </g>
          <circle cx="48" cy="184" r="8" fill="white" stroke="#2f80ed" strokeWidth="3" />

          <g className="graph-loading-target">
            <circle cx="478" cy="76" r="24" fill="none" stroke="#fb7185" strokeWidth="2" opacity=".28" />
            <circle cx="478" cy="76" r="16" fill="none" stroke="#fb7185" strokeWidth="3" opacity=".55" />
            <circle cx="478" cy="76" r="10" fill="#fff7ed" stroke="#ff8a00" strokeWidth="4" />
          </g>
          <circle cx="500" cy="137" r="10" fill="white" stroke="#ff8a00" strokeWidth="3" />

          <circle className="graph-loading-packet" r="5" fill="#ffffff" stroke="#2f80ed" strokeWidth="3">
            <animateMotion
              dur="2.4s"
              repeatCount="indefinite"
              path="M48 184 106 140 206 164 287 113 365 72 478 76"
            />
          </circle>
        </svg>
        <p className="mt-3 text-center text-sm font-medium tracking-wide text-slate-500">
          正在构建供应链关系…
        </p>
      </div>

      <style jsx>{`
        .graph-loading-flow {
          stroke-dasharray: 10 12;
          animation: graph-loading-dash 1.1s linear infinite;
        }
        .graph-loading-target {
          transform-box: fill-box;
          transform-origin: center;
          animation: graph-loading-pulse 1.6s ease-in-out infinite;
        }
        @keyframes graph-loading-dash {
          to { stroke-dashoffset: -44; }
        }
        @keyframes graph-loading-pulse {
          0%, 100% { opacity: .55; transform: scale(.92); }
          50% { opacity: 1; transform: scale(1.08); }
        }
        @media (prefers-reduced-motion: reduce) {
          .graph-loading-flow,
          .graph-loading-target {
            animation: none;
          }
          .graph-loading-packet { display: none; }
        }
      `}</style>
    </div>
  );
}
