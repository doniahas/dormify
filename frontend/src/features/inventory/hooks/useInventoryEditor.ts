import { useCallback, useState } from 'react';
import type { Apartment, Bed, Building, Id, Room } from '../../../shared/api/contracts';
import { dormInventoryAPI } from '../api';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import {
  apartmentFormFrom,
  bedFormFrom,
  buildApartmentPayload,
  buildBedPayload,
  buildBuildingPayload,
  buildRoomPayload,
  buildingFormFrom,
  editorErrorMessage,
  newApartmentForm,
  newRoomForm,
  roomFormFrom,
  validateEditor,
} from '../inventoryHelpers';
import type { EditorDataPatch, InventoryEditor } from '../model';

export interface InventoryEditorOptions {
  t: BuildingsStrings;
  selectedBuildingId: Id;
  /** Re-selects the building after an apartment is saved (the page's historical flow). */
  selectBuilding: (buildingId: Id) => Promise<void>;
  refreshCurrentScope: () => Promise<void>;
}

export interface InventoryEditorState {
  editor: InventoryEditor | null;
  openEditBuilding: (building: Building) => void;
  openCreateApartment: (buildingId: Id) => void;
  openEditApartment: (apartment: Apartment) => void;
  openCreateRoom: (apartmentId: Id) => void;
  openEditRoom: (room: Room) => void;
  openEditBed: (bed: Bed) => void;
  closeEditor: () => void;
  /** Edits the open form's fields. */
  patchData: (patch: EditorDataPatch) => void;
  /** Validates, POSTs/PATCHes, closes the editor and refreshes the scope. */
  saveEditor: () => Promise<void>;
}

/** The create/edit modal for buildings, apartments, rooms and beds. */
export function useInventoryEditor({
  t, selectedBuildingId, selectBuilding, refreshCurrentScope,
}: InventoryEditorOptions): InventoryEditorState {
  const [editor, setEditor] = useState<InventoryEditor | null>(null);

  const openEditBuilding = useCallback((building: Building) =>
    setEditor({
      type: 'building', mode: 'edit', id: building.id, parentId: null,
      data: buildingFormFrom(building), saving: false, error: '',
    }), []);

  const openCreateApartment = useCallback((buildingId: Id) =>
    setEditor({
      type: 'apartment', mode: 'create', id: null, parentId: buildingId,
      data: newApartmentForm(), saving: false, error: '',
    }), []);

  const openEditApartment = useCallback((apartment: Apartment) =>
    setEditor({
      type: 'apartment', mode: 'edit', id: apartment.id, parentId: apartment.building,
      data: apartmentFormFrom(apartment), saving: false, error: '',
    }), []);

  const openCreateRoom = useCallback((apartmentId: Id) =>
    setEditor({ type: 'room', mode: 'create', id: null, parentId: apartmentId, data: newRoomForm(), saving: false, error: '' }), []);

  const openEditRoom = useCallback((room: Room) =>
    setEditor({
      type: 'room', mode: 'edit', id: room.id, parentId: room.apartment,
      data: roomFormFrom(room), saving: false, error: '',
    }), []);

  const openEditBed = useCallback((bed: Bed) =>
    setEditor({ type: 'bed', mode: 'edit', id: bed.id, parentId: bed.room, data: bedFormFrom(bed), saving: false, error: '' }), []);

  const closeEditor = useCallback(() => setEditor(null), []);

  const patchData = useCallback((patch: EditorDataPatch) => {
    // The patch only ever carries fields of the form that is open; the
    // union is re-asserted because a spread over it loses the pairing of
    // `type` with its form.
    setEditor((prev) => (prev ? ({ ...prev, data: { ...prev.data, ...patch } } as InventoryEditor) : prev));
  }, []);

  const saveEditor = useCallback(async () => {
    if (!editor) return;
    const validationError = validateEditor(editor, t);
    if (validationError) {
      setEditor((prev) => (prev ? { ...prev, error: validationError } : prev));
      return;
    }
    setEditor((prev) => (prev ? { ...prev, saving: true, error: '' } : prev));
    try {
      if (editor.type === 'building') {
        const payload = buildBuildingPayload(editor.data);
        if (editor.mode === 'create' || editor.id === null) await dormInventoryAPI.createBuilding(payload);
        else await dormInventoryAPI.updateBuilding(editor.id, payload);
        closeEditor();
        await refreshCurrentScope();
      } else if (editor.type === 'apartment') {
        if (editor.mode === 'create' || editor.id === null) {
          await dormInventoryAPI.createApartment(buildApartmentPayload(editor.data, editor.parentId));
        } else {
          await dormInventoryAPI.updateApartment(editor.id, buildApartmentPayload(editor.data));
        }
        closeEditor();
        await selectBuilding(selectedBuildingId || editor.parentId || '');
        await refreshCurrentScope();
      } else if (editor.type === 'room') {
        if (editor.mode === 'create' || editor.id === null) {
          await dormInventoryAPI.createRoom(buildRoomPayload(editor.data, editor.parentId));
        } else {
          await dormInventoryAPI.updateRoom(editor.id, buildRoomPayload(editor.data));
        }
        closeEditor();
        await refreshCurrentScope();
      } else if (editor.type === 'bed') {
        if (editor.id !== null) await dormInventoryAPI.updateBed(editor.id, buildBedPayload(editor.data));
        closeEditor();
        await refreshCurrentScope();
      }
    } catch (err) {
      setEditor((prev) => (prev ? { ...prev, saving: false, error: editorErrorMessage(err, t.actionError) } : prev));
    }
  }, [editor, t, closeEditor, selectBuilding, selectedBuildingId, refreshCurrentScope]);

  return {
    editor,
    openEditBuilding, openCreateApartment, openEditApartment, openCreateRoom, openEditRoom, openEditBed,
    closeEditor, patchData, saveEditor,
  };
}
