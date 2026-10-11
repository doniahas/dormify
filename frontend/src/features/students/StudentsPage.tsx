import React, { useCallback, useEffect, useState } from 'react';
import type { Region, Student } from '../../shared/api/contracts';
import { useLanguage } from '../../shared/i18n';
import { useAuth } from '../auth/AuthContext';
import { regionsAPI } from '../inventory/api';
import FiltersDrawer from './FiltersDrawer';
import { ActiveFilterChips } from './components/ActiveFilterChips';
import { AddRequestModal } from './components/AddRequestModal';
import { AssignBedModal } from './components/AssignBedModal';
import { StudentDetail } from './components/StudentDetail';
import { StudentFormModal } from './components/StudentFormModal';
import { StudentList } from './components/StudentList';
import { StudentSearchRow } from './components/StudentSearchRow';
import { StudentStatTabs } from './components/StudentStatTabs';
import { StudentsHeader } from './components/StudentsHeader';
import { useAddRequestModal } from './hooks/useAddRequestModal';
import { useAddStudentModal } from './hooks/useAddStudentModal';
import { useBedAssignment } from './hooks/useBedAssignment';
import { useEditStudentModal } from './hooks/useEditStudentModal';
import { useStudentCounts } from './hooks/useStudentCounts';
import { useStudentDetail } from './hooks/useStudentDetail';
import { useStudentFilters } from './hooks/useStudentFilters';
import { useStudentList } from './hooks/useStudentList';
import type { AddStudentMode, StudentDetailView } from './model';
import { studentsStrings } from './StudentsPage.strings';
import styles from './StudentsPage.module.css';

/**
 * The Students page: the searchable, filterable student list with the stat
 * tabs, the per-student detail view, and the modals that act on a student
 * (add, edit, file a request, assign or move a bed). The page composes the
 * feature hooks and components; state lives with the hook that owns it.
 */
function StudentsPage(): React.ReactElement {
  const { user, isCentralAdmin } = useAuth();
  const { language, t: pickStrings } = useLanguage();
  const t = pickStrings(studentsStrings);
  const central = isCentralAdmin();

  const filters = useStudentFilters();
  const counts = useStudentCounts();
  const listState = useStudentList({
    activeTab: filters.activeTab,
    searchQuery: filters.searchQuery,
    filters: filters.filters,
  });
  const detail = useStudentDetail();

  // Regions for the add/edit student forms (central admins pick one; the
  // backend scopes regional staff to their own region).
  const [regions, setRegions] = useState<Region[]>([]);
  useEffect(() => {
    if (central) {
      regionsAPI.getAll().then(setRegions).catch(() => setRegions([]));
    }
  }, [central]);

  const refreshListAndCounts = useCallback(() => {
    void listState.reload();
    void counts.reload();
  }, [listState.reload, counts.reload]);

  const bedAssignment = useBedAssignment({
    t,
    onAssigned: useCallback(async (studentId) => {
      await detail.refresh(studentId);
      void counts.reload();
    }, [detail.refresh, counts.reload]),
  });

  const addStudent = useAddStudentModal({
    isCentralAdmin: central,
    filterOptions: filters.filterOptions,
    t,
    onCreated: refreshListAndCounts,
    onAfterClose: useCallback((created: Student, mode: AddStudentMode) => {
      if (mode === 'save_and_match') {
        detail.show(created);
        void bedAssignment.open(created);
      }
    }, [detail.show, bedAssignment.open]),
  });

  const selectedStudent = detail.selectedStudent;

  const editStudent = useEditStudentModal({
    isCentralAdmin: central,
    filterOptions: filters.filterOptions,
    t,
    onUpdated: refreshListAndCounts,
    onAfterClose: useCallback((updated: Student, returnToAssign: boolean) => {
      // Refresh whatever is currently showing this student, then re-run
      // matching so the assign flow picks up the field that was just fixed.
      if (selectedStudent && selectedStudent.id === updated.id) {
        detail.show(updated);
      }
      if (returnToAssign) {
        void bedAssignment.open(updated);
      }
    }, [selectedStudent, detail.show, bedAssignment.open]),
  });

  const addRequest = useAddRequestModal({
    student: selectedStudent,
    isCentralAdmin: central,
    t,
    onSubmitted: detail.reloadRequests,
  });

  const openEditFromAssign = useCallback(
    (student: StudentDetailView) => editStudent.open(student, { returnToAssign: true }),
    [editStudent.open]
  );

  return (
    <div className={styles.studentsPage}>
      {!selectedStudent && (
        <>
          <StudentsHeader
            t={t}
            loading={listState.loading}
            listTotal={listState.listTotal}
            onAddStudent={addStudent.open}
          />

          <StudentStatTabs
            t={t}
            activeTab={filters.activeTab}
            counts={counts.counts}
            onSelect={filters.setActiveTab}
          />

          <StudentSearchRow
            t={t}
            searchQuery={filters.searchQuery}
            onSearchChange={filters.setSearchQuery}
            loading={listState.loading}
            listTotal={listState.listTotal}
            activeFilterCount={filters.activeFilterCount}
            onOpenFilters={filters.openFilters}
          />

          {filters.activeFilterCount > 0 && (
            <ActiveFilterChips
              t={t}
              language={language}
              filters={filters.filters}
              filterOptions={filters.filterOptions}
              onRemove={filters.removeFilterValue}
              onClearAll={filters.clearFilters}
            />
          )}

          <StudentList
            t={t}
            loading={listState.loading}
            error={listState.error}
            list={listState.list}
            hasMore={listState.hasMore}
            loadingMore={listState.loadingMore}
            onLoadMore={listState.loadMore}
            onSelect={detail.open}
            onClearFilters={filters.clearFilters}
          />
        </>
      )}

      {selectedStudent && (
        <StudentDetail
          t={t}
          language={language}
          student={selectedStudent}
          loadingDetails={detail.loadingDetails}
          studentRequests={detail.studentRequests}
          loadingStudentRequests={detail.loadingStudentRequests}
          onBack={detail.close}
          onEdit={() => editStudent.open(selectedStudent)}
          onAssignBed={() => bedAssignment.open(selectedStudent)}
          onAddRequest={addRequest.open}
        />
      )}

      {addRequest.isOpen && selectedStudent && (
        <AddRequestModal
          t={t}
          language={language}
          student={selectedStudent}
          isCentralAdmin={central}
          userRegionName={user?.region_name}
          state={addRequest}
        />
      )}

      {addStudent.isOpen && (
        <StudentFormModal
          t={t}
          language={language}
          mode="add"
          isCentralAdmin={central}
          userRegionName={user?.region_name}
          regions={regions}
          dormTypeOptions={addStudent.dormTypeOptions}
          housingTypes={filters.filterOptions?.housing_types || []}
          form={addStudent.form}
          fieldErrors={addStudent.fieldErrors}
          error={addStudent.error}
          success={addStudent.success}
          loading={addStudent.loading}
          onFieldChange={addStudent.setField}
          onClose={addStudent.close}
          onSubmit={addStudent.submit}
        />
      )}

      {editStudent.isOpen && editStudent.target && (
        <StudentFormModal
          t={t}
          language={language}
          mode="edit"
          isCentralAdmin={central}
          userRegionName={user?.region_name}
          regions={regions}
          dormTypeOptions={editStudent.dormTypeOptions}
          housingTypes={filters.filterOptions?.housing_types || []}
          existingStudentId={editStudent.target.student_id || ''}
          form={editStudent.form}
          fieldErrors={editStudent.fieldErrors}
          error={editStudent.error}
          success={editStudent.success}
          loading={editStudent.loading}
          onFieldChange={editStudent.setField}
          onClose={editStudent.close}
          onSubmit={() => { void editStudent.submit(); }}
        />
      )}

      {bedAssignment.isOpen && bedAssignment.student && (
        <AssignBedModal
          t={t}
          language={language}
          isCentralAdmin={central}
          regions={filters.filterOptions?.regions || []}
          student={bedAssignment.student}
          state={bedAssignment}
          onEditStudent={openEditFromAssign}
        />
      )}

      {/* FILTERS DRAWER */}
      <FiltersDrawer
        isOpen={filters.filtersOpen}
        onClose={filters.closeFilters}
        filters={filters.filters}
        onFiltersChange={filters.setFilters}
        filterOptions={filters.filterOptions}
        totalCount={listState.listTotal}
        language={language}
      />
    </div>
  );
}

export default StudentsPage;
