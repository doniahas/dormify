import { useCallback, useEffect, useRef, useState } from 'react';
import { TOAST_DURATION_MS } from '../allocationRunHelpers';
import type { ToastState, ToastType } from '../model';

export interface AllocationToastState {
  toast: ToastState | null;
  showToast: (message: string, type?: ToastType) => void;
}

/** The page's single toast; it clears itself after 4.5 s unless the page unmounted. */
export function useAllocationToast(): AllocationToastState {
  const [toast, setToast] = useState<ToastState | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const showToast = useCallback((message: string, type: ToastType = 'info') => {
    setToast({ message, type });
    setTimeout(() => { if (mountedRef.current) setToast(null); }, TOAST_DURATION_MS);
  }, []);

  return { toast, showToast };
}
