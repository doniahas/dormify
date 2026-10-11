import { useCallback, useEffect, useRef, useState } from 'react';
import type { MouseEvent as ReactMouseEvent } from 'react';

export interface SplitterState {
  /** The list pane's width in px (220-640). */
  listWidth: number;
  onSplitterMouseDown: (e: ReactMouseEvent<HTMLDivElement>) => void;
}

const DEFAULT_WIDTH = 430;
const MIN_WIDTH = 220;
const MAX_WIDTH = 640;

/** The draggable splitter between the list and the detail pane (RTL: drag left = wider list). */
export function useSplitter(): SplitterState {
  const [listWidth, setListWidth] = useState(DEFAULT_WIDTH);
  const dragging = useRef(false);
  const dragStart = useRef(0);
  const widthStart = useRef(0);

  const onSplitterMouseDown = useCallback((e: ReactMouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragging.current = true;
    dragStart.current = e.clientX;
    widthStart.current = listWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [listWidth]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const delta = dragStart.current - e.clientX; // RTL: drag left = wider list
      const newW = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, widthStart.current + delta));
      setListWidth(newW);
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  return { listWidth, onSplitterMouseDown };
}
