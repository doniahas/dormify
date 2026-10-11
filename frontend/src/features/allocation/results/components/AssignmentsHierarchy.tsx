import React from 'react';
import { BedDouble, Building2, ChevronDown, ChevronLeft, DoorOpen, Info } from 'lucide-react';
import type { Language } from '../../../../shared/i18n';
import { cx } from '../../../../shared/lib/classNames';
import { localizeGender } from '../../../../shared/lib/genderLabels';
import type { AllocationResultsStrings } from '../AllocationResultsPage.strings';
import { availabilityState, getBed, sortEntries } from '../allocationResultsHelpers';
import type { HierarchyExpansionState } from '../hooks/useHierarchyExpansion';
import type {
  AllocationHierarchy,
  ApartmentNode,
  AssignmentRow,
  AvailabilityState,
  BuildingNode,
  DormTypeNode,
  RoomNode,
} from '../model';
import { EmptyState } from './ResultsStates';
import styles from './AssignmentsHierarchy.module.css';

const AVAILABILITY_LABEL: Readonly<Record<AvailabilityState, 'empty' | 'hasAvailability' | 'full'>> = {
  empty: 'empty',
  available: 'hasAvailability',
  full: 'full',
};

interface LevelProps {
  t: AllocationResultsStrings;
  language: Language;
  expansion: HierarchyExpansionState;
}

export interface AssignmentsHierarchyProps extends LevelProps {
  hierarchy: AllocationHierarchy;
  /** True when the run produced no assignments at all (the hierarchy is then empty too). */
  isEmpty: boolean;
}

/**
 * The assigned students, grouped dorm type -> building -> apartment -> room,
 * each level a collapsible card with its assigned / available-bed counts;
 * an open room lists its student cards and its free beds.
 */
export function AssignmentsHierarchy({
  t, language, expansion, hierarchy, isEmpty,
}: AssignmentsHierarchyProps): React.ReactElement {
  if (isEmpty) {
    return <EmptyState text={t.noAssignmentsTable} />;
  }

  return (
    <div className={styles.hierarchyList}>
      {sortEntries(hierarchy).map(([dormTypeName, dormNode]) => (
        <DormTypeCard
          key={dormTypeName}
          t={t}
          language={language}
          expansion={expansion}
          dormKey={dormTypeName}
          node={dormNode}
        />
      ))}
    </div>
  );
}

function AvailabilityChip({ t, state }: { t: AllocationResultsStrings; state: AvailabilityState }): React.ReactElement {
  return (
    <span className={cx(styles.availabilityState, styles[state])}>
      {t[AVAILABILITY_LABEL[state]]}
    </span>
  );
}

function CountChips({
  t, assigned, available,
}: { t: AllocationResultsStrings; assigned: number; available: number }): React.ReactElement {
  return (
    <>
      <span className={cx(styles.countChip, styles.assigned)}>
        {assigned}{' '}
        {t.assignedCount}
      </span>

      <span className={cx(styles.countChip, styles.available)}>
        {available}{' '}
        {t.availableBedsCount}
      </span>
    </>
  );
}

function Chevron({ open, size }: { open: boolean; size: number }): React.ReactElement {
  return (
    <span className={styles.chevron}>
      {open ? <ChevronDown size={size} /> : <ChevronLeft size={size} />}
    </span>
  );
}

function DormTypeCard({
  t, language, expansion, dormKey, node,
}: LevelProps & { dormKey: string; node: DormTypeNode }): React.ReactElement {
  const dormIsOpen = Boolean(expansion.open.dormTypes[dormKey]);

  return (
    <div className={cx(styles.hierarchyCard, styles.dormCard)}>
      <button
        type="button"
        className={cx(styles.hierarchyRow, styles.dormRow)}
        aria-expanded={dormIsOpen}
        onClick={() => expansion.toggle('dormTypes', dormKey)}
      >
        <div className={styles.hierarchyMain}>
          <Chevron open={dormIsOpen} size={18} />

          <span className={cx(styles.hierarchyIcon, styles.dormIcon)}>
            <Building2 size={19} />
          </span>

          <div>
            <div className={styles.hierarchyTitle}>
              {node.name}
            </div>

            <div>
              {Object.keys(node.buildings).length}{' '}
              {t.buildingsCount}
            </div>
          </div>
        </div>

        <div className={styles.hierarchyCounts}>
          <CountChips t={t} assigned={node.assignments.length} available={node.availableBeds.length} />
        </div>
      </button>

      {dormIsOpen && (
        <div className={cx(styles.hierarchyChildren, styles.dormChildren)}>
          {sortEntries(node.buildings, true).map(([buildingNumber, buildingNode]) => (
            <BuildingCard
              key={`${dormKey}::${buildingNumber}`}
              t={t}
              language={language}
              expansion={expansion}
              buildingKey={`${dormKey}::${buildingNumber}`}
              node={buildingNode}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function BuildingCard({
  t, language, expansion, buildingKey, node,
}: LevelProps & { buildingKey: string; node: BuildingNode }): React.ReactElement {
  const buildingIsOpen = Boolean(expansion.open.buildings[buildingKey]);

  return (
    <div className={cx(styles.hierarchyCard, styles.buildingCard)}>
      <button
        type="button"
        className={cx(styles.hierarchyRow, styles.buildingRow)}
        aria-expanded={buildingIsOpen}
        onClick={() => expansion.toggle('buildings', buildingKey)}
      >
        <div className={styles.hierarchyMain}>
          <Chevron open={buildingIsOpen} size={17} />

          <span className={cx(styles.hierarchyIcon, styles.buildingIcon)}>
            <Building2 size={18} />
          </span>

          <div>
            <div className={styles.hierarchyTitle}>
              {t.building}{' '}
              {node.number}
            </div>

            <div>
              {Object.keys(node.apartments).length}{' '}
              {t.apartmentsCount}
            </div>
          </div>
        </div>

        <div className={styles.hierarchyCounts}>
          <CountChips t={t} assigned={node.assignments.length} available={node.availableBeds.length} />
        </div>
      </button>

      {buildingIsOpen && (
        <div className={cx(styles.hierarchyChildren, styles.buildingChildren)}>
          {sortEntries(node.apartments, true).map(([apartmentNumber, apartmentNode]) => (
            <ApartmentCard
              key={`${buildingKey}::${apartmentNumber}`}
              t={t}
              language={language}
              expansion={expansion}
              apartmentKey={`${buildingKey}::${apartmentNumber}`}
              node={apartmentNode}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ApartmentCard({
  t, language, expansion, apartmentKey, node,
}: LevelProps & { apartmentKey: string; node: ApartmentNode }): React.ReactElement {
  const apartmentIsOpen = Boolean(expansion.open.apartments[apartmentKey]);
  const apartmentStatus = availabilityState(node.assignments.length, node.availableBeds.length);

  return (
    <div className={cx(styles.hierarchyCard, styles.apartmentCard)}>
      <button
        type="button"
        className={cx(styles.hierarchyRow, styles.apartmentRow)}
        aria-expanded={apartmentIsOpen}
        onClick={() => expansion.toggle('apartments', apartmentKey)}
      >
        <div className={styles.hierarchyMain}>
          <Chevron open={apartmentIsOpen} size={16} />

          <span className={cx(styles.hierarchyIcon, styles.apartmentIcon)}>
            <DoorOpen size={17} />
          </span>

          <div>
            <div className={cx(styles.hierarchyTitle, styles.apartmentTitleRow)}>
              <span>
                {t.apartment} {node.number}
              </span>

              {(node.apartmentTypeDisplay || node.apartmentCategoryDisplay) && (
                <span className={styles.apartmentTypeChip}>
                  {node.apartmentTypeDisplay || node.apartmentCategoryDisplay}
                </span>
              )}
            </div>

            <div>
              {Object.keys(node.rooms).length}{' '}
              {t.roomsCount}
            </div>
          </div>
          <AvailabilityChip t={t} state={apartmentStatus} />

          <CountChips t={t} assigned={node.assignments.length} available={node.availableBeds.length} />
        </div>
      </button>

      {apartmentIsOpen && (
        <div className={cx(styles.hierarchyChildren, styles.apartmentChildren)}>
          {sortEntries(node.rooms, true).map(([roomName, roomNode]) => (
            <RoomCard
              key={`${apartmentKey}::${roomName}`}
              t={t}
              language={language}
              expansion={expansion}
              roomKey={`${apartmentKey}::${roomName}`}
              node={roomNode}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function RoomCard({
  t, language, expansion, roomKey, node,
}: LevelProps & { roomKey: string; node: RoomNode }): React.ReactElement {
  const roomIsOpen = Boolean(expansion.open.rooms[roomKey]);
  const roomStatus = availabilityState(node.assignments.length, node.availableBeds.length);

  return (
    <div className={styles.roomCard}>
      <button
        type="button"
        className={cx(styles.hierarchyRow, styles.roomRow)}
        aria-expanded={roomIsOpen}
        onClick={() => expansion.toggle('rooms', roomKey)}
      >
        <div className={styles.hierarchyMain}>
          <Chevron open={roomIsOpen} size={15} />

          <div>
            <div className={styles.hierarchyTitle}>
              {t.room}{' '}
              {node.name}
            </div>

            <div>
              {node.assignments.length}{' '}
              {t.occupiedBedsCount}
            </div>
          </div>
        </div>

        <div className={styles.hierarchyCounts}>
          <AvailabilityChip t={t} state={roomStatus} />

          <CountChips t={t} assigned={node.assignments.length} available={node.availableBeds.length} />
        </div>
      </button>

      {roomIsOpen && (
        <div className={styles.roomDetails}>
          {node.assignments.length > 0 ? (
            <div className={styles.studentGrid}>
              {node.assignments.map((student, index) => (
                <AssignedStudentCard
                  key={`${student?.student_id || 'student'}-${index}`}
                  t={t}
                  language={language}
                  student={student}
                />
              ))}
            </div>
          ) : (
            <div className={styles.roomEmptyMessage}>
              <Info size={16} />
              <span>
                {t.noStudentsInRoom}
              </span>
            </div>
          )}

          {node.availableBeds.length > 0 && (
            <div className={styles.availableBedList}>
              {node.availableBeds.map((bed, index) => (
                <span
                  className={styles.availableBedChip}
                  key={`${bed?.bed_id || 'bed'}-${index}`}
                >
                  <BedDouble size={14} />

                  {t.availableBed}
                  :{' '}
                  {getBed(bed) || '-'}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AssignedStudentCard({
  t, language, student,
}: { t: AllocationResultsStrings; language: Language; student: AssignmentRow }): React.ReactElement {
  return (
    <div className={styles.studentCard}>
      <div className={styles.studentCardHeader}>
        <div>
          <div className={styles.studentName}>
            {student?.student_name || student?.full_name || '-'}
          </div>

          <div className={styles.studentNumber}>
            {t.studentId}
            :{' '}
            {student?.student_id || '-'}
          </div>
        </div>

        <span className={styles.tableStatus}>
          {student?.assignment_status || student?.status || 'active'}
        </span>
      </div>

      <div className={styles.studentFields}>
        <span>
          <strong>
            {t.bed}
            :
          </strong>{' '}
          {getBed(student) || '-'}
        </span>

        <span>
          <strong>
            {t.gender}
            :
          </strong>{' '}
          {localizeGender(student?.gender, language) || '-'}
        </span>

        <span>
          <strong>
            {t.religion}
            :
          </strong>{' '}
          {student?.religion_display || student?.religion || student?.requested_religion || '-'}
        </span>

        <span>
          <strong>
            {t.housingType}
            :
          </strong>{' '}
          {student?.housing_type_display || student?.housing_type || '-'}
        </span>
      </div>
    </div>
  );
}
