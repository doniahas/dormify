import React from 'react';
import { Loader2, X, type LucideIcon } from 'lucide-react';
import { cx } from '../../../shared/lib/classNames';
import pageStyles from '../BuildingsPage.module.css';
import styles from './InventoryPanels.module.css';

// The small presentational pieces the Buildings page is assembled from.
// The ones with plain "inv-*" class names are styled by
// BuildingsPage.global.css, which BuildingSetupWizard.jsx shares.

export function Spinner({ size = 16 }: { size?: number }): React.ReactElement {
  return <Loader2 className="inv-spin" size={size} />;
}

export interface IconButtonProps {
  icon: LucideIcon;
  onClick: () => void;
  title: string;
  tone?: 'danger' | 'success';
  disabled?: boolean;
}

export function IconButton({ icon: Icon, onClick, title, tone, disabled }: IconButtonProps): React.ReactElement {
  return (
    <button
      type="button"
      className={`inv-iconBtn ${tone ? `inv-iconBtn-${tone}` : ''}`}
      onClick={onClick}
      title={title}
      aria-label={title}
      disabled={disabled}
    >
      <Icon size={14} />
    </button>
  );
}

export interface StatusBadgeProps {
  active: boolean | undefined;
  activeText: string;
  inactiveText: string;
}

export function StatusBadge({ active, activeText, inactiveText }: StatusBadgeProps): React.ReactElement {
  return (
    <span className={cx(styles.statusBadge, active ? styles.isActive : styles.isInactive)}>
      <span className={styles.statusDot} />
      {active ? activeText : inactiveText}
    </span>
  );
}

export interface OccupancyBadgeProps {
  occupied: number;
  total: number;
  label?: string;
}

export function OccupancyBadge({ occupied, total, label }: OccupancyBadgeProps): React.ReactElement {
  const full = total > 0 && occupied >= total;
  return (
    <span className={cx(styles.occupancyBadge, full && styles.isFull)}>
      {occupied} / {total}
      {label ? ` ${label}` : ''}
    </span>
  );
}

export interface MiniMetricProps {
  icon: LucideIcon;
  value: number;
  label: string;
}

export function MiniMetric({ icon: Icon, value, label }: MiniMetricProps): React.ReactElement {
  return (
    <div className={pageStyles.miniMetric}>
      <Icon size={15} />
      <div>
        <div className={pageStyles.miniMetricValue}>{value}</div>
        <div className={pageStyles.miniMetricLabel}>{label}</div>
      </div>
    </div>
  );
}

export interface SectionHeaderProps {
  title: string;
  count?: number | null;
  action?: React.ReactNode;
}

export function SectionHeader({ title, count, action }: SectionHeaderProps): React.ReactElement {
  return (
    <div className={styles.sectionHeader}>
      <h3>
        {title}
        {count !== undefined && count !== null ? ` (${count})` : ''}
      </h3>
      {action}
    </div>
  );
}

export interface EmptyPanelProps {
  icon?: LucideIcon;
  title: string;
  hint?: string;
}

export function EmptyPanel({ icon: Icon, title, hint }: EmptyPanelProps): React.ReactElement {
  return (
    <div className={styles.emptyPanel}>
      {Icon && <Icon size={26} />}
      <div className={styles.emptyPanelTitle}>{title}</div>
      {hint && <p>{hint}</p>}
    </div>
  );
}

export function DetailRow({ label, value }: { label: string; value: React.ReactNode }): React.ReactElement {
  return (
    <div className={styles.detailRow}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export interface FormFieldProps {
  label: string;
  htmlFor?: string;
  hint?: string;
  children: React.ReactNode;
}

export function FormField({ label, htmlFor, hint, children }: FormFieldProps): React.ReactElement {
  return (
    <div className="inv-formField">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <small>{hint}</small>}
    </div>
  );
}

export function ReadOnlyField({ label, value }: { label: string; value: React.ReactNode }): React.ReactElement {
  return (
    <div className="inv-readonlyField">
      <label>{label}</label>
      <div className="inv-readonlyValue">{value ?? '—'}</div>
    </div>
  );
}

export function ModalSection({ title, children }: { title: string; children: React.ReactNode }): React.ReactElement {
  return (
    <div className="inv-modalSection">
      <h4>{title}</h4>
      {children}
    </div>
  );
}

export interface PageAlertProps {
  tone?: 'danger' | 'warning';
  children: React.ReactNode;
  onClose?: () => void;
}

export function PageAlert({ tone = 'danger', children, onClose }: PageAlertProps): React.ReactElement {
  return (
    <div className={`inv-alert inv-alert-${tone}`}>
      <span>{children}</span>
      {onClose && (
        <button type="button" onClick={onClose} aria-label="close">
          <X size={13} />
        </button>
      )}
    </div>
  );
}
