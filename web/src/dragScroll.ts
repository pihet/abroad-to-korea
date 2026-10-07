import { useEffect } from 'react'

// 가로로 넘치는 줄(data-drag)을 PC에서도 마우스로 끌어 넘긴다. 터치는 브라우저 기본 스크롤을 그대로 쓴다.
// 5px 넘게 끌었으면 손을 뗄 때의 클릭은 막는다 (카드를 넘기다가 열리지 않게).
export function useDragScroll() {
  useEffect(() => {
    let el: HTMLElement | null = null, x0 = 0, s0 = 0, moved = false
    const down = (e: PointerEvent) => {
      moved = false
      if (e.pointerType !== 'mouse' || e.button !== 0) return
      const t = (e.target as HTMLElement).closest<HTMLElement>('[data-drag]')
      if (!t || t.scrollWidth <= t.clientWidth) return
      el = t; x0 = e.clientX; s0 = t.scrollLeft
    }
    const move = (e: PointerEvent) => {
      if (!el) return
      const dx = e.clientX - x0
      if (!moved && Math.abs(dx) > 5) { moved = true; el.classList.add('dragging') }
      if (moved) { el.scrollLeft = s0 - dx; e.preventDefault() }
    }
    const up = () => { el?.classList.remove('dragging'); el = null }
    const click = (e: MouseEvent) => { if (moved) { e.preventDefault(); e.stopPropagation(); moved = false } }
    document.addEventListener('pointerdown', down)
    document.addEventListener('pointermove', move)
    document.addEventListener('pointerup', up)
    document.addEventListener('click', click, true)
    return () => {
      document.removeEventListener('pointerdown', down)
      document.removeEventListener('pointermove', move)
      document.removeEventListener('pointerup', up)
      document.removeEventListener('click', click, true)
    }
  }, [])
}
