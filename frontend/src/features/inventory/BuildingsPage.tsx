import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { idOf } from '../../shared/api/normalize';
import { useLanguage } from '../../shared/i18n';
import { cx } from '../../shared/lib/classNames';
import { localizeRegionName } from '../../shared/lib/locationNames';
import { useAuth } from '../auth/AuthContext';
import BuildingSetupWizard from './BuildingSetupWizard';
import { AvailabilityDialog } from './components/AvailabilityDialog';
import { BuildingNavigator } from './components/BuildingNavigator';
import { BuildingsHeader } from './components/BuildingsHeader';
import { BuildingStructurePanel, type StructureActions } from './components/BuildingStructurePanel';
import { DeleteBedDialog } from './components/DeleteBedDialog';
import { InventoryBreadcrumb } from './components/InventoryBreadcrumb';
import { InventoryEditorModal } from './components/InventoryEditorModal';
import { InventoryFilterBar } from './components/InventoryFilterBar';
import { PageAlert, Spinner } from './components/InventoryPrimitives';
import { InventorySummaryStrip } from './components/InventorySummaryStrip';
import { useAvailabilityDialog } from './hooks/useAvailabilityDialog';
import { useBedDeleteDialog } from './hooks/useBedDeleteDialog';
import { useBuildingWizard } from './hooks/useBuildingWizard';
import { useInventoryEditor } from './hooks/useInventoryEditor';
import { useInventoryFilters } from './hooks/useInventoryFilters';
import { useInventoryWorkspace } from './hooks/useInventoryWorkspace';
import { BED_API_CAPABILITIES, editorContextLine, editorTitle, resolveEditorContext } from './inventoryHelpers';
import { buildingsStrings } from './BuildingsPage.strings';
import './BuildingsPage.global.css';
import styles from './BuildingsPage.module.css';

/**
 * The Buildings page: the dormitory inventory tree (region › building ›
 * apartment › room › bed) with its filters and summary, the create/edit
 * modal, the activate/deactivate workflow and the Building Setup Wizard.
 * The page composes the feature hooks and components; state lives with the
 * hook that owns it.
 */
function BuildingsPage(): React.ReactElement {
  const { isCentralAdmin, isRegionBoss, getUserRegion } = useAuth();
  const [searchParams] = useSearchParams();
  const { language, isHe, t: pickStrings } = useLanguage();
  const t = pickStrings(buildingsStrings);

  const canManageInventory = isCentralAdmin() || isRegionBoss();
  const viewOnly = !canManageInventory;
  const userRegionId = idOf(getUserRegion());

  const canCreateBed = canManageInventory && BED_API_CAPABILITIES.create;
  const canDeleteBed = canManageInventory && BED_API_CAPABILITIES.delete;

  const ws = useInventoryWorkspace({
    t,
    language,
    searchParams,
    userRegionId,
    canViewAllRegions: canManageInventory,
  });

  const view = useInventoryFilters({
    regions: ws.regions,
    dormTypesInRegion: ws.dormTypesInRegion,
    buildings: ws.buildings,
    buildingApartments: ws.buildingApartments,
    buildingRooms: ws.buildingRooms,
    roomBeds: ws.roomBeds,
    selectedRegionId: ws.selectedRegionId,
    selectedDormTypeId: ws.selectedDormTypeId,
    selectedBuildingId: ws.selectedBuildingId,
    selectedApartmentId: ws.selectedApartmentId,
    selectedRoomId: ws.selectedRoomId,
    selectedBedId: ws.selectedBedId,
  });

  const editor = useInventoryEditor({
    t,
    selectedBuildingId: ws.selectedBuildingId,
    selectBuilding: ws.selectBuilding,
    refreshCurrentScope: ws.refreshCurrentScope,
  });

  const availability = useAvailabilityDialog({ t, refreshCurrentScope: ws.refreshCurrentScope });

  const bedDelete = useBedDeleteDialog({
    t,
    canDeleteBed,
    selectedRoomId: ws.selectedRoomId,
    fetchBeds: ws.fetchBeds,
  });

  const wizard = useBuildingWizard({
    t,
    selectedRegionId: ws.selectedRegionId,
    loadBuildings: ws.loadBuildings,
    selectBuilding: ws.selectBuilding,
    setPageError: ws.setPageError,
  });

  if (ws.loading) {
    return (
      <div className={cx(styles.page, styles.centerFull)} dir={isHe ? 'rtl' : 'ltr'} aria-busy="true">
        <Spinner size={26} />
      </div>
    );
  }

  const editorCtx = resolveEditorContext(editor.editor, {
    buildings: ws.buildings,
    apartments: ws.buildingApartments,
    rooms: ws.buildingRooms,
    beds: ws.roomBeds,
    selectedBuilding: view.selectedBuilding,
    selectedApartment: view.selectedApartment,
    selectedRoom: view.selectedRoom,
    selectedBed: view.selectedBed,
  });

  const structureActions: StructureActions = {
    onEditBuilding: editor.openEditBuilding,
    onAvailability: (targetType, target, action) => { void availability.open(targetType, target, action); },
    onCreateApartment: () => editor.openCreateApartment(ws.selectedBuildingId),
    onEditApartment: editor.openEditApartment,
    onSelectApartment: ws.selectApartment,
    onCreateRoom: () => editor.openCreateRoom(ws.selectedApartmentId),
    onEditRoom: editor.openEditRoom,
    onSelectRoom: (roomId) => { void ws.selectRoom(roomId); },
    onSelectBed: ws.selectBed,
    onEditBed: editor.openEditBed,
    onDeleteBed: bedDelete.open,
  };

  return (
    <div className={styles.page} dir={isHe ? 'rtl' : 'ltr'}>
      <BuildingsHeader
        t={t}
        viewOnly={viewOnly}
        canManageInventory={canManageInventory}
        canAddBuilding={Boolean(ws.selectedRegionId)}
        onRefresh={() => { void ws.handleRefresh(); }}
        onAddBuilding={wizard.open}
      />

      <InventoryBreadcrumb
        t={t}
        language={language}
        selectedRegion={view.selectedRegion}
        selectedDormType={view.selectedDormType}
        selectedBuilding={view.selectedBuilding}
        selectedApartment={view.selectedApartment}
        selectedRoom={view.selectedRoom}
        selectedBed={view.selectedBed}
      />

      {ws.pageError && <PageAlert onClose={() => ws.setPageError('')}>{ws.pageError}</PageAlert>}
      {ws.actionError && <PageAlert onClose={ws.clearActionError}>{ws.actionError}</PageAlert>}

      <InventoryFilterBar
        t={t}
        language={language}
        regions={ws.regions}
        selectedRegionId={ws.selectedRegionId}
        canChangeRegion={isCentralAdmin() || isRegionBoss()}
        onRegionChange={(regionId) => { void ws.selectRegion(regionId); }}
        dormTypesInRegion={ws.dormTypesInRegion}
        selectedDormTypeId={ws.selectedDormTypeId}
        onDormTypeChange={ws.setSelectedDormTypeId}
        statusFilter={view.statusFilter}
        onStatusChange={view.setStatusFilter}
        searchQuery={view.searchQuery}
        onSearchChange={view.setSearchQuery}
      />

      <InventorySummaryStrip t={t} metrics={view.summaryMetrics} />

      {/* Three-column workspace */}
      <div className={styles.workspace}>
        <BuildingNavigator
          t={t}
          buildings={view.filteredBuildings}
          selectedBuildingId={ws.selectedBuildingId}
          canManageInventory={canManageInventory}
          canAddBuilding={Boolean(ws.selectedRegionId)}
          onAddBuilding={wizard.open}
          onSelect={(buildingId) => { void ws.selectBuilding(buildingId); }}
        />

        <BuildingStructurePanel
          t={t}
          language={language}
          selectedBuilding={view.selectedBuilding}
          loadingStructure={ws.loadingStructure}
          buildingDetailsOpen={ws.buildingDetailsOpen}
          onToggleDetails={ws.toggleBuildingDetails}
          canManageInventory={canManageInventory}
          canCreateBed={canCreateBed}
          canDeleteBed={canDeleteBed}
          apartments={view.apartmentsForSelectedBuilding}
          selectedApartmentId={ws.selectedApartmentId}
          rooms={view.roomsForSelectedApartment}
          selectedRoomId={ws.selectedRoomId}
          roomBeds={ws.roomBeds}
          selectedBedId={ws.selectedBedId}
          loadingBeds={ws.loadingBeds}
          actions={structureActions}
        />
      </div>

      {editor.editor && (
        <InventoryEditorModal
          t={t}
          language={language}
          editor={editor.editor}
          title={editorTitle(editor.editor, t)}
          contextLine={editorContextLine(editor.editor, editorCtx, {
            t, language, selectedDormType: view.selectedDormType, selectedRegion: view.selectedRegion,
          })}
          ctx={editorCtx}
          dormTypesInRegion={ws.dormTypesInRegion}
          onPatch={editor.patchData}
          onClose={editor.closeEditor}
          onSave={() => { void editor.saveEditor(); }}
        />
      )}

      {availability.dialog && (
        <AvailabilityDialog
          t={t}
          dialog={availability.dialog}
          onClose={availability.close}
          onReasonChange={availability.setReason}
          onNoteChange={availability.setNote}
          onConfirm={() => { void availability.confirm(); }}
        />
      )}

      {bedDelete.dialog && (
        <DeleteBedDialog
          t={t}
          dialog={bedDelete.dialog}
          onClose={bedDelete.close}
          onConfirm={() => { void bedDelete.confirm(); }}
        />
      )}

      {wizard.isOpen && (
        <BuildingSetupWizard
          language={language}
          dormTypesInRegion={ws.dormTypesInRegion}
          defaultDormTypeId={ws.selectedDormTypeId !== 'all' ? ws.selectedDormTypeId : ''}
          regionName={view.selectedRegion ? localizeRegionName(view.selectedRegion, language) : ''}
          categoryLabels={t.categoryLabels}
          apartmentTypeLabels={t.apartmentTypeLabels}
          genderRestrictionLabels={t.genderRestrictionLabels}
          onClose={wizard.close}
          onCompleted={wizard.completed}
        />
      )}
    </div>
  );
}

export default BuildingsPage;
