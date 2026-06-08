type VisualProps = {
  className?: string;
};

const svgClass = "h-auto w-full";

export function ProductPreviewSvg({ className = svgClass }: VisualProps) {
  return (
    <svg
      aria-label="青程 AI 产品预览"
      className={className}
      fill="none"
      role="img"
      viewBox="0 0 720 520"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect width="720" height="520" rx="42" fill="#EFF6FF" />
      <circle cx="612" cy="88" r="74" fill="#DBEAFE" />
      <circle cx="110" cy="442" r="92" fill="#BFDBFE" opacity="0.42" />

      <rect x="54" y="54" width="612" height="412" rx="34" fill="white" stroke="#BFDBFE" strokeWidth="2" />
      <rect x="84" y="88" width="132" height="342" rx="24" fill="#0F172A" />
      <circle cx="118" cy="126" r="18" fill="#2563EB" />
      <text fill="white" fontFamily="Arial, sans-serif" fontSize="18" fontWeight="700" x="106" y="132">
        青
      </text>
      <text fill="white" fontFamily="Arial, sans-serif" fontSize="20" fontWeight="700" x="84" y="178">
        青程 AI
      </text>
      <rect x="108" y="222" width="76" height="16" rx="8" fill="#60A5FA" />
      <rect x="108" y="266" width="58" height="14" rx="7" fill="#334155" />
      <rect x="108" y="306" width="68" height="14" rx="7" fill="#334155" />
      <rect x="108" y="346" width="48" height="14" rx="7" fill="#334155" />

      <rect x="246" y="88" width="372" height="70" rx="22" fill="#F8FAFC" stroke="#E2E8F0" />
      <text fill="#0F172A" fontFamily="Arial, sans-serif" fontSize="24" fontWeight="700" x="276" y="130">
        下一步建议
      </text>
      <rect x="512" y="112" width="76" height="18" rx="9" fill="#2563EB" />

      <rect x="246" y="184" width="160" height="112" rx="28" fill="#DBEAFE" />
      <text fill="#1D4ED8" fontFamily="Arial, sans-serif" fontSize="18" fontWeight="700" x="274" y="226">
        简历
      </text>
      <text fill="#0F172A" fontFamily="Arial, sans-serif" fontSize="42" fontWeight="800" x="274" y="274">
        86
      </text>
      <path d="M348 258c18-38 52-32 52 8" stroke="#2563EB" strokeLinecap="round" strokeWidth="8" />

      <rect x="428" y="184" width="190" height="112" rx="28" fill="#F8FAFC" stroke="#E2E8F0" />
      <text fill="#0F172A" fontFamily="Arial, sans-serif" fontSize="18" fontWeight="700" x="456" y="224">
        岗位
      </text>
      <text fill="#64748B" fontFamily="Arial, sans-serif" fontSize="15" x="456" y="256">
        腾讯 · 深圳
      </text>
      <rect x="456" y="270" width="84" height="14" rx="7" fill="#BFDBFE" />
      <rect x="548" y="270" width="44" height="14" rx="7" fill="#DBEAFE" />

      <rect x="246" y="318" width="160" height="112" rx="28" fill="#F8FAFC" stroke="#E2E8F0" />
      <text fill="#0F172A" fontFamily="Arial, sans-serif" fontSize="18" fontWeight="700" x="274" y="358">
        投递
      </text>
      <rect x="274" y="380" width="94" height="16" rx="8" fill="#2563EB" />
      <rect x="274" y="404" width="62" height="12" rx="6" fill="#CBD5E1" />

      <rect x="428" y="318" width="190" height="112" rx="28" fill="#0F172A" />
      <text fill="white" fontFamily="Arial, sans-serif" fontSize="18" fontWeight="700" x="456" y="358">
        面试
      </text>
      <rect x="456" y="380" width="106" height="16" rx="8" fill="#60A5FA" />
      <rect x="456" y="404" width="132" height="12" rx="6" fill="#334155" />
    </svg>
  );
}

export function ResumeFlowSvg({ className = svgClass }: VisualProps) {
  return (
    <svg
      aria-label="简历解析流程预览"
      className={className}
      fill="none"
      role="img"
      viewBox="0 0 640 420"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect width="640" height="420" rx="38" fill="#F8FAFC" />
      <rect x="52" y="46" width="536" height="328" rx="32" fill="white" stroke="#DBEAFE" strokeWidth="2" />
      <rect x="86" y="82" width="178" height="244" rx="24" fill="#EFF6FF" />
      <rect x="120" y="116" width="110" height="16" rx="8" fill="#2563EB" />
      <rect x="120" y="154" width="92" height="12" rx="6" fill="#BFDBFE" />
      <rect x="120" y="180" width="112" height="12" rx="6" fill="#BFDBFE" />
      <rect x="120" y="206" width="78" height="12" rx="6" fill="#BFDBFE" />
      <text fill="#1D4ED8" fontFamily="Arial, sans-serif" fontSize="22" fontWeight="800" x="120" y="278">
        CV
      </text>

      <path d="M292 162h66" stroke="#BFDBFE" strokeLinecap="round" strokeWidth="8" />
      <path d="M292 258h66" stroke="#BFDBFE" strokeLinecap="round" strokeWidth="8" />
      <circle cx="392" cy="162" r="38" fill="#2563EB" />
      <text fill="white" fontFamily="Arial, sans-serif" fontSize="17" fontWeight="700" textAnchor="middle" x="392" y="168">
        上传
      </text>
      <circle cx="488" cy="162" r="38" fill="#DBEAFE" />
      <text fill="#1D4ED8" fontFamily="Arial, sans-serif" fontSize="17" fontWeight="700" textAnchor="middle" x="488" y="168">
        解析
      </text>
      <circle cx="392" cy="258" r="38" fill="#DBEAFE" />
      <text fill="#1D4ED8" fontFamily="Arial, sans-serif" fontSize="17" fontWeight="700" textAnchor="middle" x="392" y="264">
        评分
      </text>

      <path d="M488 220a58 58 0 1 1-40 100" stroke="#CBD5E1" strokeLinecap="round" strokeWidth="16" />
      <path d="M488 220a58 58 0 0 1 48 88" stroke="#2563EB" strokeLinecap="round" strokeWidth="16" />
      <text fill="#0F172A" fontFamily="Arial, sans-serif" fontSize="34" fontWeight="800" textAnchor="middle" x="488" y="282">
        86
      </text>
    </svg>
  );
}

export function ChatFlowSvg({ className = svgClass }: VisualProps) {
  return (
    <svg
      aria-label="AI 对话流程预览"
      className={className}
      fill="none"
      role="img"
      viewBox="0 0 640 420"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect width="640" height="420" rx="38" fill="#0F172A" />
      <rect x="54" y="52" width="532" height="316" rx="30" fill="white" />
      <rect x="84" y="82" width="140" height="256" rx="24" fill="#F8FAFC" stroke="#E2E8F0" />
      <text fill="#0F172A" fontFamily="Arial, sans-serif" fontSize="18" fontWeight="700" x="108" y="126">
        AI 助手
      </text>
      <text fill="#64748B" fontFamily="Arial, sans-serif" fontSize="15" x="108" y="164">
        岗位面试
      </text>
      <rect x="108" y="196" width="76" height="14" rx="7" fill="#2563EB" />
      <rect x="108" y="226" width="92" height="14" rx="7" fill="#DBEAFE" />
      <rect x="108" y="256" width="64" height="14" rx="7" fill="#DBEAFE" />

      <rect x="254" y="86" width="216" height="54" rx="20" fill="#EFF6FF" />
      <text fill="#1D4ED8" fontFamily="Arial, sans-serif" fontSize="16" fontWeight="700" x="282" y="120">
        帮我准备产品面试
      </text>
      <rect x="312" y="170" width="220" height="86" rx="24" fill="#0F172A" />
      <rect x="340" y="200" width="116" height="12" rx="6" fill="#60A5FA" />
      <rect x="340" y="224" width="156" height="12" rx="6" fill="#334155" />
      <rect x="254" y="286" width="278" height="44" rx="22" fill="#F8FAFC" stroke="#E2E8F0" />
      <rect x="282" y="302" width="142" height="12" rx="6" fill="#CBD5E1" />
      <circle cx="492" cy="308" r="16" fill="#2563EB" />
    </svg>
  );
}
