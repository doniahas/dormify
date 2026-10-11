import React from 'react';
import {
  CheckCircle, Clock, DoorOpen, FileText, Home, Loader2, MapPin, RefreshCw,
  UserMinus, UserPlus, XCircle, type LucideIcon,
} from 'lucide-react';
import { cx } from '../../../shared/lib/classNames';
import type { RequestLike, StatusColor } from '../model';
import { typeMetaFor } from '../transferHelpers';
import type { RequestStatus } from '../types';
import pageStyles from '../TransfersPage.module.css';
import detailStyles from './RequestDetail.module.css';

/** The spinning loader icon; the page module owns the animation. */
export function Spinner({ size = 16 }: { size?: number }): React.ReactElement {
  return <Loader2 size={size} className={pageStyles.spin} />;
}

export interface PillProps {
  color: StatusColor;
  children: React.ReactNode;
}

/** The status pill of the detail header. */
export function Pill({ color, children }: PillProps): React.ReactElement {
  return (
    <span className={cx(detailStyles.pill, detailStyles[`pill${capitalize(color)}`])}>{children}</span>
  );
}

export interface EmptyPaneProps {
  icon: LucideIcon;
  title: string;
  sub?: string;
}

/** The list pane's empty state (no requests at all / nothing matches). */
export function EmptyPane({ icon: Icon, title, sub }: EmptyPaneProps): React.ReactElement {
  return (
    <div className={pageStyles.emptyPane}>
      <div className={pageStyles.epIco}><Icon size={28} /></div>
      <h4>{title}</h4>
      {sub && <p>{sub}</p>}
    </div>
  );
}

const TYPE_ICONS: Readonly<Record<string, LucideIcon>> = {
  room: Home,
  apartment: DoorOpen,
  other: FileText,
  add_student: UserPlus,
  remove_student: UserMinus,
  swap: RefreshCw,
  region_transfer: MapPin,
};

/** The icon of a request type (cross-region transfers show the map pin). */
export function typeIconFor(request: RequestLike): LucideIcon {
  if (typeMetaFor(request).labelKey === 'typeLabelCrossRegion') return MapPin;
  return TYPE_ICONS[request.request_type] || FileText;
}

const STATUS_ICONS: Readonly<Record<RequestStatus, LucideIcon>> = {
  pending: Clock,
  approved: CheckCircle,
  rejected: XCircle,
  cancelled: XCircle,
};

export function statusIconFor(status: string): LucideIcon {
  return STATUS_ICONS[status as RequestStatus] || STATUS_ICONS.pending;
}

/** "amber" -> "Amber", for the colour-suffixed module class names. */
export function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
