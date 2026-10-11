// 위키미디어 커먼즈 작가 칸에는 위키 링크 문법과 긴 이용 안내문이 섞여 있어, 화면에는 이름만 뽑아 보여 준다
export function artistName(raw: string): string {
  let a = raw.replace(/\[\S+\s+([^\]]+)\]/g, '$1')  // [//commons.../User:X X] → X
  a = a.match(/taken by (.+?)\.\s+(?:Feel|Please|You|This|I)\b/i)?.[1] ?? a  // 'This Photo was taken by X. Feel free…' → X
  if (a.length > 50 && a.includes(' - ')) a = a.slice(a.lastIndexOf(' - ') + 3)  // '<업로드 안내> - 이름'
  a = a.trim()
  return a.length > 50 ? a.slice(0, 50).trimEnd() + '…' : a
}
