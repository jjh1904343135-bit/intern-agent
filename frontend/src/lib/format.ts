export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "未记录";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "未记录";
  }

  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatStatusLabel(status: string | null | undefined): string {
  if (!status) {
    return "未知状态";
  }

  const statusMap: Record<string, string> = {
    saved: "已保存",
    opened: "已打开原站",
    applied_manual: "已确认投递",
    waiting_feedback: "等待反馈",
    interviewing: "面试中",
    closed: "已结束",
    interview_invited: "面试邀请",
    offer_received: "收到 Offer",
    accepted: "已接受",
    declined: "已放弃",
    rejected: "未通过",
    processing: "解析中",
    done: "已完成",
    failed: "失败",
    ready: "已就绪",
    fallback: "规则兜底",
  };

  return statusMap[status] ?? status;
}

export function truncateText(value: string, max = 120): string {
  if (value.length <= max) {
    return value;
  }
  return `${value.slice(0, max).trim()}...`;
}
