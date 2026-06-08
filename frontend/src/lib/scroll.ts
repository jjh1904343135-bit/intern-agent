export function isNearBottom(element: HTMLElement, threshold = 96) {
  return element.scrollHeight - element.scrollTop - element.clientHeight <= threshold;
}
