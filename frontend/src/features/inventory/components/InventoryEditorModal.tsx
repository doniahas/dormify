import React from 'react';
import { createPortal } from 'react-dom';
import { Bed, Building2, DoorOpen, Home, X } from 'lucide-react';
import type { DormType } from '../../../shared/api/contracts';
import type { Language } from '../../../shared/i18n';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import type { EditorContext, EditorDataPatch, InventoryEditor } from '../model';
import { ApartmentFields, BedFields, BuildingFields, RoomFields } from './InventoryEditorForms';
import { IconButton, PageAlert, Spinner } from './InventoryPrimitives';

export interface InventoryEditorModalProps {
  t: BuildingsStrings;
  language: Language;
  editor: InventoryEditor;
  /** The title and the "where in the tree" line under it. */
  title: string;
  contextLine: string;
  ctx: EditorContext;
  dormTypesInRegion: DormType[];
  onPatch: (patch: EditorDataPatch) => void;
  onClose: () => void;
  onSave: () => void;
}

/**
 * The create/edit modal for a building, apartment, room or bed. Rendered
 * through a portal directly under <body> so its `position: fixed` centers
 * on the true browser viewport and its stacking order is independent of
 * the app shell (sidebar/header), instead of being confined to wherever it
 * happens to be nested.
 */
export function InventoryEditorModal({
  t, language, editor, title, contextLine, ctx, dormTypesInRegion, onPatch, onClose, onSave,
}: InventoryEditorModalProps): React.ReactElement {
  const EditorIcon =
    editor.type === 'building' ? Building2 : editor.type === 'apartment' ? Home : editor.type === 'room' ? DoorOpen : Bed;

  return createPortal(
    <div
      className="inv-modalOverlay"
      dir={language === 'he' ? 'rtl' : 'ltr'}
      onClick={() => (!editor.saving ? onClose() : null)}
    >
      <div className="inv-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="inv-modalHeader">
          <div className="inv-modalHeaderIcon">
            <EditorIcon size={18} />
          </div>
          <div className="inv-modalHeaderText">
            <h3>{title}</h3>
            {contextLine && <p className="inv-modalHeaderContext">{contextLine}</p>}
          </div>
          <IconButton icon={X} onClick={onClose} title={t.cancel} disabled={editor.saving} />
        </div>

        <div className="inv-modalBody">
          {editor.error && <PageAlert>{editor.error}</PageAlert>}

          {editor.type === 'building' && (
            <BuildingFields
              t={t}
              language={language}
              mode={editor.mode}
              data={editor.data}
              ctx={ctx}
              dormTypesInRegion={dormTypesInRegion}
              onPatch={onPatch}
            />
          )}

          {editor.type === 'apartment' && (
            <ApartmentFields t={t} mode={editor.mode} data={editor.data} ctx={ctx} onPatch={onPatch} />
          )}

          {editor.type === 'room' && (
            <RoomFields t={t} mode={editor.mode} data={editor.data} ctx={ctx} onPatch={onPatch} />
          )}

          {editor.type === 'bed' && (
            <BedFields t={t} data={editor.data} ctx={ctx} onPatch={onPatch} />
          )}
        </div>

        <div className="inv-modalFooter">
          <button type="button" className="inv-secondaryBtn" onClick={onClose} disabled={editor.saving}>
            {t.cancel}
          </button>
          <button type="button" className="inv-primaryBtn" onClick={onSave} disabled={editor.saving}>
            {editor.saving ? <Spinner size={14} /> : editor.mode === 'create' ? t.create : t.save}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
