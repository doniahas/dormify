import React from 'react';
import {
  ArrowLeft, BedDouble, Building2, Contact2, DoorOpen, FileSearch, FileText, Home,
  Loader2, LogIn, LogOut, Mail, MapPin, Phone, Plus, Star, Tag, User, Users,
} from 'lucide-react';
import type { Language } from '../../../shared/i18n';
import { cx } from '../../../shared/lib/classNames';
import { localizeGender } from '../../../shared/lib/genderLabels';
import type { StudentRequest } from '../../transfers/types';
import type { StudentDetailView } from '../model';
import type { StudentsStrings } from '../StudentsPage.strings';
import {
  fmtDate, getInitial, getName, getRoommateRequests, isRemoved, pickAvatarColor,
} from '../studentHelpers';
import { CategoryBadge } from './StudentBadges';
import styles from './StudentDetail.module.css';

export interface StudentDetailProps {
  t: StudentsStrings;
  language: Language;
  student: StudentDetailView;
  loadingDetails: boolean;
  studentRequests: StudentRequest[];
  loadingStudentRequests: boolean;
  onBack: () => void;
  onEdit: () => void;
  onAssignBed: () => void;
  onAddRequest: () => void;
}

function requestMark(status: string): string {
  return status === 'approved' ? '✓' : status === 'rejected' ? '✕' : '…';
}

/** The student detail view: hero card, current assignment, info cards and requests. */
export function StudentDetail({
  t, language, student, loadingDetails, studentRequests, loadingStudentRequests,
  onBack, onEdit, onAssignBed, onAddRequest,
}: StudentDetailProps): React.ReactElement {
  const removed = isRemoved(student);
  const roommateRequests = getRoommateRequests(student);

  return (
    <div className={styles.detailWrap}>
      <div className={cx(styles.heroCard, removed && styles.heroRemoved)}>
        <div className={styles.heroTopRow}>
          <button type="button" className={styles.backPill} onClick={onBack}>
            <ArrowLeft size={16} /> {t.back}
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className={styles.editStudentPill} onClick={onEdit}>
              <User size={16} />
              {t.editStudentBtn}
            </button>
            {/* Unassigned: Assign Bed directly */}
            {!removed && (
              <button type="button" className={styles.assignBedPill} onClick={onAssignBed}>
                <BedDouble size={16} />
                {student.is_assigned ? t.reassignBed : t.assignBed}
              </button>
            )}
            {/* Assigned: Add Request (room/apartment/other/remove) */}
            {student.is_assigned && (
              <button type="button" className={styles.addRequestPill} onClick={onAddRequest}>
                <Plus size={16} /> {t.addRequest}
              </button>
            )}
          </div>
        </div>

        <div className={styles.heroBody}>
          <div className={styles.heroLeft}>
            <div className={styles.heroAvatar}>{getInitial(student)}</div>
            <div className={styles.heroInfo}>
              <h1>{getName(student)}</h1>
              <div className={styles.heroId}>{t.studentId} <strong>{student.student_id}</strong></div>
              <div className={styles.heroBadges}>
                {removed ? (
                  <span className={styles.heroRemovedBadge}>
                    <LogOut size={13} /> {t.removedFromDorms}
                  </span>
                ) : (
                  <span className={cx(styles.heroStatus, student.is_assigned ? styles.assigned : styles.unassigned)}>
                    {student.is_assigned ? `✓ ${t.assigned}` : t.unassigned}
                  </span>
                )}
                <CategoryBadge student={student} t={t} />
                {student.is_priority && (
                  <span className={styles.heroPriority}><Star size={12} /> {t.priority}</span>
                )}
              </div>
            </div>
          </div>

          <div className={styles.heroMeta}>
            {student.assigned_region && (
              <div className={styles.heroMetaRow}><MapPin size={15} /><span><strong>{t.region}:</strong> {student.assigned_region}</span></div>
            )}
            {student.accepted_dorm_type_name && (
              <div className={styles.heroMetaRow}><Building2 size={15} /><span><strong>{t.dormType}:</strong> {student.accepted_dorm_type_name}</span></div>
            )}
            {student.move_in_date && (
              <div className={styles.heroMetaRow}><LogIn size={15} /><span><strong>{t.moveInDate}:</strong> {fmtDate(student.move_in_date)}</span></div>
            )}
            {student.move_out_date && (
              <div className={styles.heroMetaRow}><LogOut size={15} /><span><strong>{t.moveOutDate}:</strong> {fmtDate(student.move_out_date)}</span></div>
            )}
          </div>
          {loadingDetails && <Loader2 size={20} className={cx(styles.spinner, styles.detailSpinner)} />}
        </div>
      </div>

      {student.is_assigned && (
        <>
          <div className={styles.sectionHeading}>{t.currentAssignment}</div>
          <div className={styles.statsRow}>
            <div className={styles.statCard}><div className={cx(styles.miniStatIcon, styles.blue)}><Building2 size={26} /></div><div className={styles.statLabel}>{t.building}</div><div className={styles.statValue}>{student.assigned_building_number || '—'}</div></div>
            <div className={styles.statCard}><div className={cx(styles.miniStatIcon, styles.green)}><DoorOpen size={26} /></div><div className={styles.statLabel}>{t.apartment}</div><div className={styles.statValue}>{student.assigned_apartment_number || '—'}</div></div>
            <div className={styles.statCard}><div className={cx(styles.miniStatIcon, styles.purple)}><Home size={26} /></div><div className={styles.statLabel}>{t.room}</div><div className={styles.statValue}>{student.assigned_room_name || '—'}</div></div>
            <div className={styles.statCard}><div className={cx(styles.miniStatIcon, styles.orange)}><BedDouble size={26} /></div><div className={styles.statLabel}>{t.bed}</div><div className={cx(styles.statValue, styles.sm)}>{student.current_bed_label || '—'}</div></div>
            <div className={styles.statCard}><div className={cx(styles.miniStatIcon, styles.yellow)}><Star size={26} /></div><div className={styles.statLabel}>{t.priority}</div><div className={styles.statValue}>{student.is_priority ? '★' : '—'}</div></div>
          </div>
        </>
      )}

      <div className={styles.twoCol}>
        <div className={styles.card}>
          <div className={styles.cardHeader}><div className={cx(styles.cardIcon, styles.contact)}><Contact2 size={18} /></div><h3>{t.contact}</h3></div>
          <div className={styles.cardBody}>
            <div className={styles.infoRow}><span className={styles.infoKey}><Mail size={15} /> {t.email}</span><span className={styles.infoVal}>{student.email || '—'}</span></div>
            <div className={styles.infoRow}><span className={styles.infoKey}><Phone size={15} /> {t.phone}</span><span className={styles.infoVal}>{student.phone || '—'}</span></div>
            {student.city && <div className={styles.infoRow}><span className={styles.infoKey}><MapPin size={15} /> {t.city}</span><span className={styles.infoVal}>{student.city}</span></div>}
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.cardHeader}><div className={cx(styles.cardIcon, styles.housing)}><Home size={18} /></div><h3>{t.housing}</h3></div>
          <div className={styles.cardBody}>
            <div className={styles.infoRow}>
              <span className={styles.infoKey}><Home size={15} /> {t.housingType}</span>
              <span className={styles.infoVal}>
                {student.housing_type || (
                  <span className={styles.fieldMissingBadge}>{t.fieldMissing}</span>
                )}
              </span>
            </div>
            {student.is_assigned ? (
              <>
                <div className={styles.infoRow}><span className={styles.infoKey}><Building2 size={15} /> {t.dormType}</span><span className={styles.infoVal}>{student.accepted_dorm_type_name || '—'}</span></div>
                <div className={styles.infoRow}><span className={styles.infoKey}><Building2 size={15} /> {t.building}</span><span className={styles.infoVal}>{student.assigned_building_number || '—'}</span></div>
                <div className={styles.infoRow}><span className={styles.infoKey}><DoorOpen size={15} /> {t.apartment}</span><span className={styles.infoVal}>{student.assigned_apartment_number || '—'}</span></div>
                <div className={styles.infoRow}><span className={styles.infoKey}><Home size={15} /> {t.room}</span><span className={styles.infoVal}>{student.assigned_room_name || '—'}</span></div>
                <div className={styles.infoRow}><span className={styles.infoKey}><BedDouble size={15} /> {t.bed}</span><span className={styles.infoVal}>{student.current_bed_label || '—'}</span></div>
              </>
            ) : (
              <p className={styles.muted}>{t.notAssigned}</p>
            )}
          </div>
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardHeader}><div className={cx(styles.cardIcon, styles.roommates)}><Users size={18} /></div><h3>{t.roommates}</h3></div>
        <div className={styles.cardBody}>
          {Array.isArray(student.roommates) && student.roommates.length > 0 ? (
            <div className={styles.roommatesGrid}>
              {student.roommates.map((r) => {
                const color = pickAvatarColor(r.student_id || r.full_name);
                return (
                  <div key={r.id} className={styles.roommateCard}>
                    <div className={styles.rmAvatar} style={{ background: color.bg, color: color.color }}>{r.full_name ? r.full_name[0] : '?'}</div>
                    <div className={styles.rmInfo}>
                      <div className={styles.rmName}>{r.full_name}</div>
                      {r.bed_label && <div className={styles.rmMeta}><Users size={11} /> {t.bed}: {r.bed_label}</div>}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className={styles.muted}>{t.noRoommates}</p>
          )}
        </div>
      </div>

      <div className={styles.twoCol}>
        <div className={styles.card}>
          <div className={styles.cardHeader}><div className={cx(styles.cardIcon, styles.personal)}><User size={18} /></div><h3>{t.personal}</h3></div>
          <div className={styles.cardBody}>
            <div className={styles.infoRow}><span className={styles.infoKey}>⚥ {t.gender}</span><span className={styles.infoVal}>{localizeGender(student.gender, language) || '—'}</span></div>
            <div className={styles.infoRow}><span className={styles.infoKey}><Star size={15} /> {t.religion}</span><span className={styles.infoVal}>{student.requested_religion_display || '—'}</span></div>
            <div className={styles.infoRow}><span className={styles.infoKey}><Tag size={15} /> {t.category}</span><span className={styles.infoVal}>{student.category_display || '—'}</span></div>
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.cardHeader}><div className={cx(styles.cardIcon, styles.requests)}><FileText size={18} /></div><h3>{t.roommateRequests}</h3></div>
          <div className={styles.cardBody}>
            {roommateRequests.length > 0 ? (
              <ol className={styles.requestsList}>
                {roommateRequests.map((name, i) => (
                  <li key={i}><span className={styles.rqNum}>{i + 1}</span><span className={styles.rqName}>{name}</span></li>
                ))}
              </ol>
            ) : <p className={styles.muted}>—</p>}
          </div>
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardHeader}><div className={cx(styles.cardIcon, styles.requests)}><FileSearch size={18} /></div><h3>{t.studentRequestsTitle}</h3></div>
        <div className={styles.cardBody}>
          {loadingStudentRequests ? (
            <p className={styles.muted}>{t.loading}</p>
          ) : studentRequests.length > 0 ? (
            <ol className={styles.requestsList}>
              {studentRequests.map((r) => (
                <li key={r.id}>
                  <span className={styles.rqNum}>{requestMark(r.status)}</span>
                  <span className={styles.rqName}>
                    {r.request_type_display || r.request_type} — {r.status_display || r.status}
                    {r.created_at ? ` (${new Date(r.created_at).toLocaleDateString()})` : ''}
                  </span>
                </li>
              ))}
            </ol>
          ) : <p className={styles.muted}>—</p>}
        </div>
      </div>

      {student.is_priority && student.priority_reason && (
        <div className={styles.priorityNotice}><Star size={18} /><span>{student.priority_reason}</span></div>
      )}
    </div>
  );
}
