export function prepareSpeechText(value) {
  const technicalLine = /^\s*(?:traceback\b|caused by\s*:|during handling of the above exception|file\s+["'].*["']\s*,\s*line\s+\d+|at\s+\S+\s*\(|(?:[\w.]+(?:error|exception))\s*:|(?:error|exception|fatal|failed)\s*:|local model unavailable\s*:|local task failed\b|http\/\d(?:\.\d)?\s+\d{3}|(?:http|status)\s+\d{3}\b|ps\s+[a-z]:\\|docker(?:\.exe)?\s+|npm\s+err!|exit\s+code\s+\d+|errno\s*\d+|connection(?:refused|error)\b)/i;
  const technicalFragment = /(?:\b(?:http(?:\s+status)?\s*[45]\d{2}|errno\s*\d+|exit\s+code\s+\d+|connection\s+refused|stack\s+trace|ollama\s+timed\s+out)\b|\b[\w.]+(?:error|exception)\s*:)/i;
  let text = String(value || "").normalize("NFKC").replace(/\r\n/g, "\n");
  text = text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/\[([^\]]+)]\([^\s)]+(?:\s+"[^"]*")?\)/g, "$1")
    .replace(/`[^`\n]+`/g, " ")
    .replace(/\b(?:https?:\/\/|www\.)\S+/gi, " ")
    .replace(/\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b/g, " ")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi, " ")
    .replace(/(?<!\w)(?:[A-Za-z]:\\|\/)(?:[^\s,;:]+[\/\\])*[^\s,;:]+/g, " ");
  text = text.split("\n").flatMap(line => line.replace(/^\s{0,3}(?:#{1,6}|>|[-*+]\s+|\d+[.)]\s+)/, "").trim().split(/(?<=[.!?])\s+/)).filter(line => line && !technicalLine.test(line) && !technicalFragment.test(line) && !/(?:\{.*:.*}|\w+\([^)]*\)\s*(?:\{|=>)|[=<>]{2,}|::)/.test(line)).join(" ");
  return text
    .replace(/(?:-{2,}|={2,}|_{2,}|\*{2,}|~{2,})/g, " ")
    .replace(/\s*(?:→|➜|➡|->|=>)\s*/g, " then ")
    .replace(/&/g, " and ")
    .replace(/%/g, " percent ")
    .replace(/[_|\\/^#@+$*=<>\[\]{}]/g, " ")
    .replace(/[\p{S}\p{C}]/gu, " ")
    .replace(/\.{2,}|!{2,}|\?{2,}/g, ".")
    .replace(/\s+([,.;:!?])/g, "$1")
    .replace(/([,.;:!?])(?=[A-Za-z])/g, "$1 ")
    .replace(/\s+/g, " ")
    .replace(/^[ ,;:-]+|[ ,;:-]+$/g, "")
    .trim();
}
