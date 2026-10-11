import React from 'react';
import { Bed, Building2, DoorOpen, Home } from 'lucide-react';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import styles from '../BuildingsPage.module.css';
import type { InventorySummaryMetrics } from '../model';
import { MiniMetric } from './InventoryPrimitives';

export interface InventorySummaryStripProps {
  t: BuildingsStrings;
  metrics: InventorySummaryMetrics;
}

/** The six counters of the region / dorm type scope. */
export function InventorySummaryStrip({ t, metrics }: InventorySummaryStripProps): React.ReactElement {
  return (
    <div className={styles.summaryStrip}>
      <MiniMetric icon={Building2} value={metrics.buildings} label={t.metricBuildings} />
      <MiniMetric icon={Home} value={metrics.apartments} label={t.metricApartments} />
      <MiniMetric icon={DoorOpen} value={metrics.rooms} label={t.metricRooms} />
      <MiniMetric icon={Bed} value={metrics.beds} label={t.metricBeds} />
      <MiniMetric icon={Bed} value={metrics.occupied} label={t.metricOccupied} />
      <MiniMetric icon={Bed} value={metrics.free} label={t.metricFree} />
    </div>
  );
}
