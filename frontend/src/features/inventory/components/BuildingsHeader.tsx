import React from 'react';
import { Building2, Plus, RefreshCw, Shield } from 'lucide-react';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import styles from '../BuildingsPage.module.css';
import { IconButton } from './InventoryPrimitives';

export interface BuildingsHeaderProps {
  t: BuildingsStrings;
  /** The user may only look (employees). */
  viewOnly: boolean;
  canManageInventory: boolean;
  /** "Add building" needs a selected region. */
  canAddBuilding: boolean;
  onRefresh: () => void;
  onAddBuilding: () => void;
}

/** Page title, the view-only marker, refresh and the Add building action. */
export function BuildingsHeader({
  t, viewOnly, canManageInventory, canAddBuilding, onRefresh, onAddBuilding,
}: BuildingsHeaderProps): React.ReactElement {
  return (
    <div className={styles.pageHeader}>
      <div className={styles.pageHeaderLeft}>
        <div className={styles.pageHeaderIcon}>
          <Building2 size={22} />
        </div>
        <div>
          <h1>{t.title}</h1>
          <p>{t.subtitle}</p>
        </div>
      </div>
      <div className={styles.pageHeaderRight}>
        {viewOnly && (
          <span className={styles.viewOnlyIndicator}>
            <Shield size={13} /> {t.viewOnlyIndicator}
          </span>
        )}
        <IconButton icon={RefreshCw} onClick={onRefresh} title={t.refresh} />
        {canManageInventory && (
          <button type="button" className="inv-primaryBtn" onClick={onAddBuilding} disabled={!canAddBuilding}>
            <Plus size={15} /> {t.addBuilding}
          </button>
        )}
      </div>
    </div>
  );
}
