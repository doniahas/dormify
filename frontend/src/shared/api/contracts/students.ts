// backend/api/serializers/students.py
import type { IsoDate, IsoDateTime } from './common';

export type Gender = 'male' | 'female';
export type StudentCategory = 'new' | 'continuing' | 'transfer' | 'leaving';
/** Student.Religion values as stored (mixed case is the backend's). */
export type Religion = 'Muslims' | 'Jewish' | 'Christian' | 'Druze' | 'not_specified';
export type Religious = 'religious' | 'no_preference' | 'not_specified';
/** Student.HousingType values are the Hebrew labels themselves. */
export type HousingType = string;

/** StudentListSerializer - the list/table shape of /api/students/. */
export interface StudentSummary {
  id: number;
  student_id: string;
  business_partner_id: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  phone: string;
  gender: Gender | '';
  gender_display: string;
  requested_religion: Religion | '';
  requested_religion_display: string;
  category: StudentCategory;
  category_display: string;
  housing_type: HousingType;
  accepted_dorm_type: number | null;
  /**
   * Omitted (not null) when the student has no accepted dorm type: the
   * serializer sources these through accepted_dorm_type without a default.
   */
  accepted_dorm_type_name?: string;
  accepted_dorm_type_code?: number | null;
  is_priority: boolean;
  priority_reason: string;
  assigned_room: number | null;
  is_assigned: boolean;
  current_building: number | null;
  current_apartment: string | null;
  current_room: string | null;
  current_bed: string | null;
}

/** The StudentListSerializer columns that StudentSerializer does not have. */
type ListOnlyStudentFields = 'current_building' | 'current_apartment' | 'current_room' | 'current_bed';

/**
 * StudentSerializer - the detail/create/update shape of /api/students/<id>/.
 * It shares the summary fields except the four list-only current_* columns
 * (the detail reply carries assigned_* / current_bed_* instead).
 */
export interface Student extends Omit<StudentSummary, ListOnlyStudentFields> {
  email_secondary: string;
  phone_secondary: string;
  city: string;
  religious: Religious | '';
  religious_display: string;
  housing_gender: string;
  allocation_group: string;
  region_id: string | null;
  region_name: string | null;
  batch: number | null;
  batch_id: number | null;
  roommate_request_1: string;
  roommate_request_2: string;
  roommate_request_3: string;
  roommate_request_4: string;
  roommate_request_5: string;
  roommate_request_flag_1: boolean;
  roommate_request_flag_2: boolean;
  roommate_request_flag_3: boolean;
  roommate_request_flag_4: boolean;
  roommate_request_flag_5: boolean;
  special_status_1: string;
  special_status_2: string;
  special_status_3: string;
  special_status_4: string;
  accessibility_flag: boolean;
  disability_percent: string | null;
  medical_reason: string;
  study_points: string | null;
  current_address: string;
  current_dorm_type: string;
  move_in_date: IsoDate | null;
  move_out_date: IsoDate | null;
  /**
   * The four assigned_* fields are OMITTED (not null) while the student has
   * no assigned room: DRF skips a read-only dotted-source field without a
   * default when a relation on its path is None.
   */
  assigned_room_id?: number;
  assigned_room_name?: string;
  /** Building.number is nullable. */
  assigned_building_number?: number | null;
  assigned_apartment_number?: string;
  current_bed_id: number | null;
  current_bed_label: string | null;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

/**
 * Payload accepted by POST /api/students/ and PATCH /api/students/<id>/.
 * accepted_dorm_type is a PrimaryKeyRelatedField: the forms submit the
 * select's string value and DRF resolves it, so either form is accepted.
 */
export type StudentWritePayload = Partial<
  Omit<
    Student,
    | 'id'
    | 'full_name'
    | 'housing_gender'
    | 'is_assigned'
    | 'current_bed_id'
    | 'current_bed_label'
    | 'created_at'
    | 'updated_at'
    | 'assigned_room'
    | 'accepted_dorm_type'
  > & { accepted_dorm_type: number | string | null }
>;
