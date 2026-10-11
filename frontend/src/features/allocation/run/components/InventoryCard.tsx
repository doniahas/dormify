import React from 'react';
import { Building2, ChevronDown, ChevronUp, Home, Info } from 'lucide-react';
import { cx } from '../../../../shared/lib/classNames';
import { inventoryItem, occupancyPercent } from '../allocationRunHelpers';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import type { InventoryTypeKey, InventoryTypeView, SummaryView } from '../model';
import pageStyles from '../AllocationPage.module.css';
import styles from './AllocationInventory.module.css';

interface InventoryTypeRowProps {
  typeKey: InventoryTypeKey;
  label: string;
  item: InventoryTypeView;
  expandedType: InventoryTypeKey | null;
  onToggle: (key: InventoryTypeKey) => void;
  t: AllocationRunStrings;
}

function InventoryTypeRow({ typeKey, label, item, expandedType, onToggle, t }: InventoryTypeRowProps): React.ReactElement {
  const total = item.total_beds || 0;
  const available = item.available_beds || 0;
  const occupied = item.occupied_beds || 0;
  const occupancyPct = occupancyPercent(item);
  const isExpanded = expandedType === typeKey;

  return (
    <div className={styles.apInvRow}>
      <button
        type="button"
        className={styles.apInvRowHeader}
        onClick={() => onToggle(typeKey)}
        aria-expanded={isExpanded}
      >
        <div className={styles.apInvRowLeft}>
          <span className={styles.apInvTypeIcon}>
            <Home size={15} />
          </span>
          <span className={styles.apInvTypeName}>{label}</span>
        </div>
        <div className={styles.apInvRowRight}>
          <div className={styles.apInvQuickStats}>
            <span className={cx(styles.apInvQuickStat, styles.available)}>
              <strong>{available}</strong> {t.freeBedsLabel}
            </span>
            <span className={styles.apInvSep}>·</span>
            <span className={styles.apInvQuickStat}>{occupancyPct}% {t.occupied}</span>
          </div>
          <div className={styles.apInvProgressMini}>
            <div
              className={styles.apInvProgressFill}
              style={{ width: `${occupancyPct}%` }}
            />
          </div>
          <span className={styles.apInvChevron}>
            {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
          </span>
        </div>
      </button>

      {isExpanded && (
        <div className={styles.apInvExpanded}>
          <div className={styles.apInvMetricsGrid}>
            <div className={styles.apInvMetric}>
              <div className={styles.apInvMetricVal}>{item.apartments || 0}</div>
              <div className={styles.apInvMetricLbl}>{t.apartmentsLabel}</div>
            </div>
            <div className={styles.apInvMetric}>
              <div className={styles.apInvMetricVal}>{item.rooms || 0}</div>
              <div className={styles.apInvMetricLbl}>{t.roomsLabel}</div>
            </div>
            <div className={styles.apInvMetric}>
              <div className={styles.apInvMetricVal}>{total}</div>
              <div className={styles.apInvMetricLbl}>{t.totalBedsLabel}</div>
            </div>
            <div className={cx(styles.apInvMetric, styles.apInvMetricHighlight)}>
              <div className={styles.apInvMetricVal}>{available}</div>
              <div className={styles.apInvMetricLbl}>{t.freeBedsLabel}</div>
            </div>
            <div className={styles.apInvMetric}>
              <div className={styles.apInvMetricVal}>{occupied}</div>
              <div className={styles.apInvMetricLbl}>{t.occupiedBeds}</div>
            </div>
            <div className={styles.apInvMetric}>
              <div className={cx(styles.apInvMetricVal, styles.apInvMetricPct)}>{occupancyPct}%</div>
              <div className={styles.apInvMetricLbl}>{t.occupancyPct}</div>
            </div>
          </div>
          <div className={styles.apInvOccBarWrap}>
            <div className={styles.apInvOccBar}>
              <div
                className={styles.apInvOccFill}
                style={{ width: `${occupancyPct}%` }}
                title={t.occupancyTitle(occupancyPct)}
              />
            </div>
            <span className={styles.apInvOccLabel}>{occupancyPct}% {t.occupied}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export interface InventoryCardProps {
  t: AllocationRunStrings;
  inventory: SummaryView['inventory_by_type'];
  expandedType: InventoryTypeKey | null;
  onToggle: (key: InventoryTypeKey) => void;
}

/** "Inventory by Housing Type": one expandable row per housing type. */
export function InventoryCard({ t, inventory, expandedType, onToggle }: InventoryCardProps): React.ReactElement {
  const inventoryTypes: Array<[InventoryTypeKey, string]> = [
    ['single', t.singleHousing],
    ['couple', t.coupleHousing],
    ['family', t.familyHousing],
  ];

  return (
    <div className={pageStyles.apCard}>
      <div className={pageStyles.apCardHeader}>
        <div className={pageStyles.apCardTitleRow}>
          <Building2 size={16} />
          <h2 className={pageStyles.apCardTitle}>{t.inventoryTitle}</h2>
        </div>
      </div>

      {inventory ? (
        <div className={styles.apInvList}>
          {inventoryTypes.map(([typeKey, label]) => (
            <InventoryTypeRow
              key={typeKey}
              typeKey={typeKey}
              label={label}
              item={inventoryItem(inventory, typeKey)}
              expandedType={expandedType}
              onToggle={onToggle}
              t={t}
            />
          ))}
        </div>
      ) : (
        <div className={styles.apEmptyHint}>
          <Info size={14} />
          <span>{t.noResultsHint}</span>
        </div>
      )}
    </div>
  );
}
