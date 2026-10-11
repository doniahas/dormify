import React from 'react';
import { AlertTriangle, Check, Info, XCircle } from 'lucide-react';
import { cx } from '../../../../shared/lib/classNames';
import type { ToastState, ToastType } from '../model';
import styles from './AllocationOverlays.module.css';

const TOAST_CLASS: Record<ToastType, string> = {
  success: styles.apToastSuccess,
  error:   styles.apToastError,
  info:    styles.apToastInfo,
  warning: styles.apToastWarning,
};

export interface ToastNotificationProps {
  toast: ToastState | null;
}

/** The page's transient notification (top corner, polite live region). */
export function ToastNotification({ toast }: ToastNotificationProps): React.ReactElement | null {
  if (!toast) return null;
  const icons: Record<ToastType, React.ReactElement> = {
    success: <Check size={15} />,
    error:   <XCircle size={15} />,
    info:    <Info size={15} />,
    warning: <AlertTriangle size={15} />,
  };
  return (
    <div className={cx(styles.apToast, TOAST_CLASS[toast.type])} role="alert" aria-live="polite">
      <span className={styles.apToastIcon}>{icons[toast.type] || icons.info}</span>
      <span className={styles.apToastMsg}>{toast.message}</span>
    </div>
  );
}
